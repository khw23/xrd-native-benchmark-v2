"""Prepare element-conditioned COD candidate sets for Dara and CrystalShift.

This script reads only the public v3 manifest. It never reads Atomly generator
CIFs or private truth. The resulting candidate sets are the native COD front-end
for Dara and the explicitly named external front-end for CrystalShift.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
import traceback
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
from dara.structure_db import CODDatabase


ROOT = Path(__file__).resolve().parents[3]
BLIND_ROOT = ROOT / "fig4/benchmark/datasets/atomly_core_v3/native_blind_package_v3"
OUT_ROOT = ROOT / "fig4/benchmark/method_inputs/cod_native_v3"
ORIGINAL_COD_DOWNLOAD = CODDatabase._download_cod


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--blind-root", type=Path, default=BLIND_ROOT)
    parser.add_argument("--output-root", type=Path, default=OUT_ROOT)
    parser.add_argument(
        "--cod-root",
        type=Path,
        default=None,
        help="Optional local COD mirror. Without it, Dara downloads required CIFs online.",
    )
    parser.add_argument("--limit-systems", type=int, default=None)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--resume", action="store_true")
    return parser.parse_args()


def system_key(elements: str) -> str:
    return "-".join(sorted(str(elements).split(";")))


def database_id(path: Path) -> str:
    match = re.search(r"\(cod_([^\)]+)\)", path.stem, flags=re.IGNORECASE)
    return match.group(1) if match else path.stem


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_records(records: dict[str, dict], output_root: Path) -> None:
    frame = pd.DataFrame(sorted(records.values(), key=lambda row: row["system_key"]))
    frame.to_csv(output_root / "candidate_set_summary.csv", index=False)


def write_candidate_manifest(system_root: Path, cif_paths: list[Path]) -> list[dict]:
    rows = []
    for candidate_index, path in enumerate(cif_paths, start=1):
        rows.append(
            {
                "candidate_index": candidate_index,
                "database": "COD",
                "database_id": database_id(path),
                "cif_path": str(path.relative_to(ROOT)),
                "cif_sha256": sha256(path),
            }
        )
    pd.DataFrame(rows).to_csv(system_root / "candidate_manifest.csv", index=False)
    return rows


def download_with_retries(cod_id: str, attempts: int = 3):
    for attempt in range(1, attempts + 1):
        try:
            return ORIGINAL_COD_DOWNLOAD(cod_id)
        except Exception:
            if attempt == attempts:
                raise
            time.sleep(2**attempt)


def failure_category(error: Exception) -> str:
    name = type(error).__name__.lower()
    if "timeout" in name:
        return "database_timeout"
    if "connection" in name or "ssl" in name:
        return "database_network"
    if isinstance(error, FileNotFoundError):
        return "database_missing"
    return "candidate_preparation_failure"


def append_failure(record: dict, output_root: Path) -> None:
    with (output_root / "failure_history.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=True) + "\n")


def main() -> None:
    args = parse_args()
    blind_root = args.blind_root.resolve()
    output_root = args.output_root.resolve()
    cod_root = args.cod_root.resolve() if args.cod_root is not None else None
    if cod_root is not None and not cod_root.is_dir():
        raise FileNotFoundError(f"Local COD mirror not found: {cod_root}")
    manifest_path = blind_root / "sample_manifest.csv"
    manifest = pd.read_csv(manifest_path)
    manifest["system_key"] = manifest["sample_elements"].map(system_key)
    systems = manifest[["system_key", "sample_elements"]].drop_duplicates()
    systems.sort_values("system_key", inplace=True)
    if args.limit_systems is not None:
        systems = systems.head(args.limit_systems)

    output_root.mkdir(parents=True, exist_ok=True)
    CODDatabase._download_cod = staticmethod(download_with_retries)
    database = CODDatabase(path_to_cifs=cod_root)
    summary_path = output_root / "candidate_set_summary.csv"
    if args.resume and summary_path.exists():
        records = {
            row["system_key"]: row
            for row in pd.read_csv(summary_path).to_dict("records")
        }
    else:
        records = {}
    for row in systems.itertuples(index=False):
        system_root = output_root / row.system_key
        cif_root = system_root / "cifs"
        success_path = system_root / "_SUCCESS.json"
        started = time.perf_counter()
        try:
            existing = sorted(cif_root.glob("*.cif")) if cif_root.exists() else []
            status = "cached"
            if args.force or not (args.resume and success_path.exists() and existing):
                cif_root.mkdir(parents=True, exist_ok=True)
                previous_cwd = Path.cwd()
                os.chdir(output_root)
                try:
                    database.get_cifs_by_chemsys(
                        str(row.sample_elements).split(";"),
                        copy_files=True,
                        dest_dir=str(cif_root.resolve()),
                    )
                finally:
                    os.chdir(previous_cwd)
                existing = sorted(cif_root.glob("*.cif"))
                status = "prepared"
            if not existing:
                raise RuntimeError("Dara COD front-end returned zero candidates")
            candidate_rows = write_candidate_manifest(system_root, existing)
            elapsed = time.perf_counter() - started
            success_path.write_text(
                json.dumps(
                    {
                        "system_key": row.system_key,
                        "candidate_count": len(existing),
                        "candidate_manifest": str(
                            (system_root / "candidate_manifest.csv").relative_to(ROOT)
                        ),
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            record = {
                "system_key": row.system_key,
                "sample_elements": row.sample_elements,
                "candidate_count": len(existing),
                "status": status,
                "runtime_seconds": elapsed,
                "candidate_directory": str(cif_root.relative_to(ROOT)),
                "candidate_manifest": str(
                    (system_root / "candidate_manifest.csv").relative_to(ROOT)
                ),
                "database": "Dara COD filtered index 2024",
                "first_database_id": candidate_rows[0]["database_id"],
                "last_database_id": candidate_rows[-1]["database_id"],
            }
            print(
                f"{row.system_key}: {len(existing)} COD candidates "
                f"({status}, {elapsed:.1f} s)",
                flush=True,
            )
        except Exception as error:
            elapsed = time.perf_counter() - started
            record = {
                "system_key": row.system_key,
                "sample_elements": row.sample_elements,
                "candidate_count": len(list(cif_root.glob("*.cif"))),
                "status": "error",
                "runtime_seconds": elapsed,
                "candidate_directory": str(cif_root.relative_to(ROOT)),
                "database": "Dara COD filtered index 2024",
                "error_type": type(error).__name__,
                "failure_category": failure_category(error),
                "error": str(error),
                "traceback": traceback.format_exc(),
            }
            append_failure(
                {
                    "timestamp_utc": datetime.now(UTC).isoformat(),
                    **record,
                },
                output_root,
            )
            print(
                f"{row.system_key}: ERROR after {elapsed:.1f} s: {error}", flush=True
            )
        records[row.system_key] = record
        write_records(records, output_root)

    manifests = []
    for path in sorted(output_root.glob("*/candidate_manifest.csv")):
        frame = pd.read_csv(path)
        frame.insert(0, "system_key", path.parent.name)
        manifests.append(frame)
    if manifests:
        pd.concat(manifests, ignore_index=True).to_csv(
            output_root / "candidate_manifest.csv", index=False
        )
    systems_successful = sum(
        row.get("status") in {"prepared", "cached"} for row in records.values()
    )
    provenance = {
        "input_manifest": str(manifest_path.relative_to(ROOT)),
        "input_manifest_sha256": sha256(manifest_path),
        "database_class": "dara.structure_db.CODDatabase",
        "local_cod_root": str(cod_root) if cod_root else None,
        "selection_rule": "all database phases whose element set is a nonempty subset of sample_elements, followed by Dara COD preprocessing",
        "private_generator_cifs_used": False,
        "systems_recorded": len(records),
        "systems_successful": systems_successful,
        "resume_supported": True,
        "download_attempts_per_cod_id": 3,
    }
    (output_root / "provenance.json").write_text(
        json.dumps(provenance, indent=2) + "\n", encoding="utf-8"
    )
    print(
        "COD_CANDIDATE_PREPARATION_SUMMARY "
        f"{systems_successful}/{len(records)} systems successful",
        flush=True,
    )
    if systems_successful != len(records):
        raise RuntimeError(
            "COD candidate preparation incomplete: "
            f"{systems_successful}/{len(records)} systems successful"
        )
    print("COD_CANDIDATE_PREPARATION_OK", flush=True)


if __name__ == "__main__":
    main()
