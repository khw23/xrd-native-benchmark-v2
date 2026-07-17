"""Audit the frozen public-element COD front-end before any method run."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[3]
BLIND_ROOT = ROOT / "fig4/benchmark/datasets/atomly_core_v3/native_blind_package_v3"
COD_ROOT = ROOT / "fig4/benchmark/method_inputs/cod_native_v3"
SNAPSHOT_ROOT = (
    ROOT / "fig4/benchmark/results/atomly_core_v3/database_snapshots/cod_frontend"
)


def system_key(elements: str) -> str:
    return "-".join(sorted(str(elements).split(";")))


def main() -> None:
    samples = pd.read_csv(BLIND_ROOT / "sample_manifest.csv")
    expected = {
        system_key(elements) for elements in samples["sample_elements"].unique()
    }
    summary = pd.read_csv(COD_ROOT / "candidate_set_summary.csv")
    recorded = set(summary["system_key"].astype(str))
    if expected != recorded:
        raise RuntimeError(
            f"System mismatch: missing={sorted(expected-recorded)}, extra={sorted(recorded-expected)}"
        )
    bad = summary[~summary["status"].isin(["prepared", "cached"])]
    if not bad.empty:
        raise RuntimeError(f"Candidate preparation failures:\n{bad.to_string(index=False)}")
    if (summary["candidate_count"] <= 0).any():
        raise RuntimeError("At least one public element system has zero COD candidates")

    duplicate_id_total = 0
    duplicate_hash_total = 0
    manifest_rows = 0
    for key in sorted(expected):
        manifest = pd.read_csv(COD_ROOT / key / "candidate_manifest.csv")
        expected_count = int(summary.loc[summary["system_key"] == key, "candidate_count"].iloc[0])
        if len(manifest) != expected_count:
            raise RuntimeError(f"Candidate count mismatch for {key}")
        duplicate_id_total += int(manifest["database_id"].duplicated().sum())
        duplicate_hash_total += int(manifest["cif_sha256"].duplicated().sum())
        manifest_rows += len(manifest)

    counts = summary["candidate_count"].to_numpy(dtype=int)
    report = {
        "status": "passed",
        "samples": len(samples),
        "unique_element_systems": len(expected),
        "candidate_rows_across_system_caches": manifest_rows,
        "candidate_count_min": int(counts.min()),
        "candidate_count_median": float(np.median(counts)),
        "candidate_count_p90": float(np.quantile(counts, 0.9)),
        "candidate_count_max": int(counts.max()),
        "systems_at_least_500_candidates": int((counts >= 500).sum()),
        "systems_at_least_2000_candidates": int((counts >= 2000).sum()),
        "duplicate_database_ids_within_systems": duplicate_id_total,
        "duplicate_cif_hashes_within_systems": duplicate_hash_total,
        "scientific_note": (
            "Large candidate counts are reported, not silently pruned. Freeze any "
            "deterministic shortlist rule before inspecting predictions."
        ),
    }
    (COD_ROOT / "audit_report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    SNAPSHOT_ROOT.mkdir(parents=True, exist_ok=True)
    for filename in [
        "candidate_set_summary.csv",
        "candidate_manifest.csv",
        "provenance.json",
        "audit_report.json",
    ]:
        source = COD_ROOT / filename
        if source.exists():
            shutil.copy2(source, SNAPSHOT_ROOT / filename)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
