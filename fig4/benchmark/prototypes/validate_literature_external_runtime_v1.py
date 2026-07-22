"""Validate Literature-External-v1 public data and optional COD/OQMD caches."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATASET_ROOT = ROOT / "fig4/benchmark/datasets/literature_external_v1"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-root", type=Path, default=DEFAULT_DATASET_ROOT)
    parser.add_argument("--cod-root", type=Path, default=None)
    parser.add_argument("--oqmd-root", type=Path, default=None)
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_cod(root: Path, errors: list[str], expected_ids: set[str]) -> dict:
    manifest_path = root / "sparse_mirror_manifest.csv"
    if not manifest_path.exists():
        errors.append(f"missing COD mirror manifest: {manifest_path}")
        return {}
    frame = pd.read_csv(manifest_path, dtype=str, keep_default_na=False)
    if len(frame) != 2122:
        errors.append(f"COD mirror has {len(frame)} rows, expected 2122")
    actual_ids = set(frame["cod_id"])
    if actual_ids != expected_ids:
        errors.append(
            "COD mirror ID set differs from frozen public-scope audit: "
            f"missing={len(expected_ids - actual_ids)}, "
            f"extra={len(actual_ids - expected_ids)}"
        )
    for row in frame.itertuples(index=False):
        path = root / row.relative_path
        if row.status != "present" or not path.is_file():
            errors.append(f"COD {row.cod_id} is not present")
            continue
        if sha256(path) != row.sha256:
            errors.append(f"COD {row.cod_id} SHA-256 mismatch")
    return {
        "manifest": str(manifest_path),
        "manifest_sha256": sha256(manifest_path),
        "required_unique_cod_cifs": len(frame),
        "all_present": not any("COD " in error for error in errors),
    }


def validate_oqmd(root: Path, errors: list[str], expected_systems: set[str]) -> dict:
    top_path = root / "cache_manifest.json"
    if not top_path.exists():
        errors.append(f"missing OQMD cache manifest: {top_path}")
        return {}
    top = json.loads(top_path.read_text(encoding="utf-8"))
    if top.get("complete") is not True:
        errors.append("OQMD top-level cache is not marked complete")
    expected_count = len(expected_systems)
    if int(top.get("complete_system_count", -1)) != expected_count:
        errors.append(
            f"OQMD cache has {top.get('complete_system_count')} systems, "
            f"expected {expected_count}"
        )
    seen_systems = set()
    for item in top.get("systems", []):
        system = str(item.get("system", ""))
        seen_systems.add(system)
        manifest_path = root / str(item.get("manifest", ""))
        if not manifest_path.is_file():
            errors.append(f"OQMD {system}: missing manifest")
            continue
        if sha256(manifest_path) != item.get("manifest_sha256"):
            errors.append(f"OQMD {system}: manifest SHA-256 mismatch")
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("complete") is not True:
            errors.append(f"OQMD {system}: incomplete system manifest")
        entry_count = 0
        for page in manifest.get("pages", []):
            page_path = manifest_path.parent / page["file"]
            if not page_path.is_file() or sha256(page_path) != page.get("sha256"):
                errors.append(f"OQMD {system}: page hash mismatch for {page['file']}")
                continue
            data = json.loads(page_path.read_text(encoding="utf-8"))
            entry_count += len(data.get("data", []))
        if entry_count != int(manifest.get("entry_count", -1)):
            errors.append(f"OQMD {system}: entry-count mismatch")
    if len(seen_systems) != expected_count:
        errors.append(f"OQMD top manifest lists {len(seen_systems)} unique systems")
    if seen_systems != expected_systems:
        errors.append(
            "OQMD system set differs from public element-space requirement: "
            f"missing={len(expected_systems - seen_systems)}, "
            f"extra={len(seen_systems - expected_systems)}"
        )
    return {
        "manifest": str(top_path),
        "manifest_sha256": sha256(top_path),
        "complete_system_count": len(seen_systems),
        "complete": top.get("complete"),
    }


def main() -> None:
    args = parse_args()
    dataset_root = args.dataset_root.resolve()
    blind_manifest = pd.read_csv(
        dataset_root / "blind_package/sample_manifest.csv",
        dtype=str,
        keep_default_na=False,
    )
    expected_oqmd_systems = {
        "-".join(sorted(set(value.split(";"))))
        for value in blind_manifest["sample_elements"]
    }
    coverage_root = (
        dataset_root.parents[1] / "database_coverage/literature_external_v1"
    )
    cod_scope_path = coverage_root / "cod/required_cod_audit.csv"
    if not cod_scope_path.is_file():
        raise FileNotFoundError(f"Missing frozen COD scope: {cod_scope_path}")
    expected_cod_ids = set(
        pd.read_csv(cod_scope_path, dtype=str, keep_default_na=False)["cod_id"]
    )
    public_validator = Path(__file__).with_name(
        "validate_literature_external_public_v1.py"
    )
    public = subprocess.run(
        [sys.executable, str(public_validator), "--dataset-root", str(dataset_root)],
        text=True,
        capture_output=True,
    )
    errors = []
    if public.returncode != 0:
        errors.append("public blind-package validator failed")

    report = {
        "status": "PASS",
        "public_validator_stdout": public.stdout.strip(),
        "cod": {},
        "oqmd": {},
        "errors": errors,
    }
    if args.cod_root is not None:
        report["cod"] = validate_cod(
            args.cod_root.resolve(), errors, expected_cod_ids
        )
    if args.oqmd_root is not None:
        report["oqmd"] = validate_oqmd(
            args.oqmd_root.resolve(), errors, expected_oqmd_systems
        )
    report["status"] = "PASS" if not errors else "FAIL"
    print(json.dumps(report, indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
