"""Audit and download the frozen COD subset required by a public blind set."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
import requests
from dara.data import COMMON_GASES
from dara.structure_db import CODDatabase


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_BLIND_ROOT = (
    ROOT / "fig4/benchmark/datasets/atomly_core_v3/native_blind_package_v3"
)
DEFAULT_OUTPUT = ROOT / "fig4/benchmark/cache/cod_sparse_atomly_core_v3"
COD_URL = "https://www.crystallography.net/cod/{cod_id}.cif"
THREAD_LOCAL = threading.local()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--blind-root", type=Path, default=DEFAULT_BLIND_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--seed-root",
        type=Path,
        default=None,
        help="Optional reusable sparse COD mirror with the same nested layout.",
    )
    parser.add_argument(
        "--seed-flat",
        type=Path,
        default=None,
        help="Optional flat directory containing reusable <COD_ID>.cif files.",
    )
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--attempts", type=int, default=4)
    parser.add_argument(
        "--audit-only",
        action="store_true",
        help="Write required-COD coverage without copying or downloading CIFs.",
    )
    return parser.parse_args()


def cod_path(root: Path, cod_id: str) -> Path:
    code = str(cod_id).ljust(7, "0")
    return root / code[0] / code[1:3] / code[3:5] / f"{code}.cif"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def provenance_path(path: Path) -> str:
    """Keep repository inputs portable while retaining external absolute paths."""
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(ROOT.resolve()))
    except ValueError:
        return str(resolved)


def required_records(
    manifest_path: Path,
) -> dict[str, tuple[str, str, float | None]]:
    manifest = pd.read_csv(manifest_path)
    database = CODDatabase(path_to_cifs="/path/that/does/not/exist")
    records: dict[str, tuple[str, str, float | None]] = {}
    for element_text in sorted(manifest["sample_elements"].unique()):
        elements = sorted(set(str(element_text).split(";")))
        for size in range(1, len(elements) + 1):
            for subset in itertools.combinations(elements, size):
                key = "-".join(subset)
                for formula, cod_id, space_group, e_hull in database.preparsed_info.get(
                    key, []
                ):
                    if formula in COMMON_GASES:
                        continue
                    if e_hull is not None and e_hull > 0.1:
                        continue
                    records[str(cod_id)] = (formula, space_group, e_hull)
    return records


def session() -> requests.Session:
    if not hasattr(THREAD_LOCAL, "session"):
        THREAD_LOCAL.session = requests.Session()
    return THREAD_LOCAL.session


def download_one(cod_id: str, destination: Path, attempts: int) -> str:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and destination.stat().st_size > 0:
        return "cached"
    url = COD_URL.format(cod_id=cod_id)
    for attempt in range(1, attempts + 1):
        try:
            response = session().get(url, timeout=(10, 60))
            response.raise_for_status()
            content = response.content
            if b"data_" not in content[:4096]:
                raise ValueError("response does not look like a CIF")
            temporary = destination.with_suffix(".cif.part")
            temporary.write_bytes(content)
            temporary.replace(destination)
            return "downloaded"
        except Exception:
            if attempt == attempts:
                raise
            time.sleep(2**attempt)
    raise RuntimeError("unreachable")


def seed_source(args: argparse.Namespace, cod_id: str) -> Path | None:
    if args.seed_root is not None:
        candidate = cod_path(args.seed_root.resolve(), cod_id)
        if candidate.is_file():
            return candidate
    if args.seed_flat is not None:
        candidate = args.seed_flat.resolve() / f"{cod_id}.cif"
        if candidate.is_file():
            return candidate
    return None


def write_audit(
    output: Path,
    manifest_path: Path,
    records: dict[str, tuple[str, str, float | None]],
    args: argparse.Namespace,
) -> dict:
    rows = []
    for cod_id, (formula, space_group, e_hull) in sorted(records.items()):
        destination = cod_path(output, cod_id)
        source = seed_source(args, cod_id)
        rows.append(
            {
                "cod_id": cod_id,
                "formula": formula,
                "space_group": space_group,
                "e_hull_eV_atom": e_hull,
                "destination_present": destination.is_file(),
                "seed_available": source is not None,
                "relative_path": str(destination.relative_to(output)),
            }
        )
    pd.DataFrame(rows).to_csv(output / "required_cod_audit.csv", index=False)
    summary = {
        "audit_timepoint": "before_seed_copy_and_download",
        "input_manifest": provenance_path(manifest_path),
        "input_manifest_sha256": sha256(manifest_path),
        "database_index": "Dara bundled COD index 2024",
        "selection_rule": (
            "all non-gas COD phases in every nonempty subset of disclosed "
            "sample_elements with e_hull <= 0.1 eV/atom when available"
        ),
        "required_unique_cod_cifs": len(rows),
        "already_present": sum(row["destination_present"] for row in rows),
        "reusable_from_seed": sum(row["seed_available"] for row in rows),
        "missing_after_seed": sum(
            not row["destination_present"] and not row["seed_available"]
            for row in rows
        ),
    }
    (output / "coverage_audit.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    return summary


def main() -> None:
    args = parse_args()
    if args.workers <= 0 or args.attempts <= 0:
        raise ValueError("--workers and --attempts must be positive")
    blind_root = args.blind_root.resolve()
    manifest_path = blind_root / "sample_manifest.csv"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Missing public manifest: {manifest_path}")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    records = required_records(manifest_path)
    summary = write_audit(output, manifest_path, records, args)
    print(json.dumps(summary, indent=2), flush=True)
    if args.audit_only:
        return

    seeded = 0
    for cod_id in records:
        source = seed_source(args, cod_id)
        destination = cod_path(output, cod_id)
        if source is not None and not destination.exists():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            seeded += 1

    failures: dict[str, str] = {}
    counts = {"cached": 0, "downloaded": 0}
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(
                download_one, cod_id, cod_path(output, cod_id), args.attempts
            ): cod_id
            for cod_id in records
        }
        for completed, future in enumerate(as_completed(futures), start=1):
            cod_id = futures[future]
            try:
                counts[future.result()] += 1
            except Exception as error:
                failures[cod_id] = f"{type(error).__name__}: {error}"
            if completed % 100 == 0 or completed == len(futures):
                print(
                    f"completed={completed}/{len(futures)} "
                    f"downloaded={counts['downloaded']} cached={counts['cached']} "
                    f"failed={len(failures)}",
                    flush=True,
                )

    rows = []
    for cod_id, (formula, space_group, e_hull) in sorted(records.items()):
        path = cod_path(output, cod_id)
        rows.append(
            {
                "cod_id": cod_id,
                "formula": formula,
                "space_group": space_group,
                "e_hull_eV_atom": e_hull,
                "relative_path": str(path.relative_to(output)),
                "sha256": sha256(path) if path.is_file() else None,
                "status": "present" if path.is_file() else "failed",
                "error": failures.get(cod_id),
            }
        )
    pd.DataFrame(rows).to_csv(output / "sparse_mirror_manifest.csv", index=False)
    if failures:
        raise RuntimeError(f"{len(failures)} COD downloads failed; rerun to resume")
    (output / "_SUCCESS.txt").write_text(
        f"required_unique_cod_cifs={len(records)}\nseeded_this_run={seeded}\n",
        encoding="utf-8",
    )
    print(f"Sparse COD mirror ready: {output} ({len(records)} CIFs)")


if __name__ == "__main__":
    main()
