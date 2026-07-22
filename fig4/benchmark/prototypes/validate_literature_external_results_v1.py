"""Validate 78-sample method outputs without opening private benchmark truth."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[3]
BLIND_ROOT = ROOT / "fig4/benchmark/datasets/literature_external_v1/blind_package"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--result-root", type=Path, required=True)
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def resolve_output_path(value: str, result_root: Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    repository_path = ROOT / path
    if repository_path.exists():
        return repository_path
    return result_root / path


def main() -> None:
    args = parse_args()
    result_root = args.result_root.resolve()
    manifest_path = BLIND_ROOT / "sample_manifest.csv"
    manifest = pd.read_csv(manifest_path, dtype=str, keep_default_na=False)
    expected_ids = set(manifest["sample_id"])
    family_by_id = dict(zip(manifest["sample_id"], manifest["dataset_family"], strict=True))
    errors: list[str] = []

    record_path = result_root / "run_records.json"
    prediction_path = result_root / "predictions.csv"
    environment_path = result_root / "environment.json"
    for path in (record_path, prediction_path, environment_path):
        if not path.is_file():
            errors.append(f"missing result file: {path.name}")
    if errors:
        print(json.dumps({"status": "FAIL", "errors": errors}, indent=2))
        raise SystemExit(1)

    records = json.loads(record_path.read_text(encoding="utf-8"))
    latest = {}
    for row in records:
        sample_id = str(row.get("sample_id", ""))
        if sample_id:
            latest[sample_id] = row
    if set(latest) != expected_ids:
        errors.append(
            "latest record sample set differs: "
            f"missing={sorted(expected_ids - set(latest))}, "
            f"extra={sorted(set(latest) - expected_ids)}"
        )

    predictions = pd.read_csv(prediction_path, dtype=str, keep_default_na=False)
    prediction_ids = set(predictions.get("sample_id", pd.Series(dtype=str)))
    if not prediction_ids.issubset(expected_ids):
        errors.append(f"predictions contain unknown sample IDs: {sorted(prediction_ids - expected_ids)}")
    successful_ids = {
        sample_id for sample_id, row in latest.items() if row.get("status") == "ok"
    }
    predicted_phase_rows = predictions[
        predictions.get("predicted_database_id", pd.Series(index=predictions.index, dtype=str))
        .astype(str)
        .str.strip()
        .ne("")
    ]
    predicted_ids = set(predicted_phase_rows.get("sample_id", pd.Series(dtype=str)))
    if not successful_ids.issubset(predicted_ids):
        errors.append(
            f"successful samples without a predicted phase: {sorted(successful_ids - predicted_ids)}"
        )

    if "predicted_cif_path" in predicted_phase_rows.columns:
        for row in predicted_phase_rows.itertuples(index=False):
            value = str(row.predicted_cif_path).strip()
            if not value:
                errors.append(f"{row.sample_id}: predicted phase lacks a CIF path")
                continue
            path = resolve_output_path(value, result_root)
            if not path.is_file():
                errors.append(f"{row.sample_id}: selected CIF does not exist: {value}")

    environment = json.loads(environment_path.read_text(encoding="utf-8"))
    if environment.get("private_truth_used") is not False:
        errors.append("environment must record private_truth_used=false")
    if environment.get("blind_manifest_sha256") != sha256(manifest_path):
        errors.append("environment blind-manifest SHA-256 mismatch")

    family_status = {}
    for family in sorted(set(family_by_id.values())):
        family_status[family] = dict(
            Counter(
                latest[sample_id].get("status", "missing")
                for sample_id in expected_ids
                if family_by_id[sample_id] == family and sample_id in latest
            )
        )
    report = {
        "status": "PASS" if not errors else "FAIL",
        "result_root": str(result_root),
        "latest_sample_count": len(latest),
        "successful_sample_count": len(successful_ids),
        "family_status": family_status,
        "errors": errors,
    }
    print(json.dumps(report, indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
