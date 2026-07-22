"""Validate the public-only Literature-External-v1 blind package."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATASET_ROOT = (
    ROOT / "fig4/benchmark/datasets/literature_external_v1"
)
EXPECTED_FAMILY_COUNTS = {
    "autoxrd_xerus_10": 10,
    "iucr_qpa_1a_1h": 8,
    "dara_precursor_20x2": 40,
    "dara_reaction_20": 20,
}
REQUIRED_COLUMNS = {
    "sample_id",
    "physical_sample_id",
    "dataset_family",
    "measurement_domain",
    "sample_elements",
    "element_count",
    "pattern_filename",
    "acquisition_variant",
    "instrument_family",
    "radiation",
    "n_grid_points",
    "two_theta_min_deg",
    "two_theta_max_deg",
    "median_step_deg",
    "pattern_sha256",
}
FORBIDDEN_COLUMN_TOKENS = {
    "answer",
    "candidate",
    "cif",
    "database_id",
    "formula",
    "phase_count",
    "space_group",
    "source_filename",
    "truth",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-root", type=Path, default=DEFAULT_DATASET_ROOT)
    parser.add_argument(
        "--write-checksums",
        action="store_true",
        help="Write public_checksums_sha256.csv after all checks pass.",
    )
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_pattern(path: Path) -> np.ndarray:
    data = np.loadtxt(path, comments="#")
    if data.ndim != 2 or data.shape[1] != 2:
        raise ValueError(f"Pattern must contain exactly two numeric columns: {path}")
    if not np.isfinite(data).all():
        raise ValueError(f"Pattern contains non-finite values: {path}")
    if len(data) < 2 or not np.all(np.diff(data[:, 0]) > 0):
        raise ValueError(f"Two-theta must be strictly increasing: {path}")
    return data


def public_files(dataset_root: Path) -> list[Path]:
    excluded = {dataset_root / "public_checksums_sha256.csv"}
    return [
        path
        for path in sorted(dataset_root.rglob("*"))
        if path.is_file() and path not in excluded
    ]


def main() -> None:
    args = parse_args()
    dataset_root = args.dataset_root.resolve()
    blind_root = dataset_root / "blind_package"
    manifest_path = blind_root / "sample_manifest.csv"
    errors: list[str] = []

    if (dataset_root / "private_scoring").exists():
        errors.append("private_scoring must not exist in the public repository package")
    if not manifest_path.exists():
        raise SystemExit(f"Missing manifest: {manifest_path}")

    manifest = pd.read_csv(manifest_path, dtype=str, keep_default_na=False)
    missing_columns = sorted(REQUIRED_COLUMNS - set(manifest.columns))
    if missing_columns:
        errors.append(f"missing required columns: {missing_columns}")
    forbidden = sorted(
        column
        for column in manifest.columns
        if any(token in column.lower() for token in FORBIDDEN_COLUMN_TOKENS)
    )
    if forbidden:
        errors.append(f"answer-bearing manifest columns are forbidden: {forbidden}")

    if len(manifest) != 78:
        errors.append(f"expected 78 acquisitions, found {len(manifest)}")
    if manifest["sample_id"].duplicated().any():
        errors.append("sample_id values are not unique")
    if manifest["physical_sample_id"].nunique() != 58:
        errors.append(
            "expected 58 physical samples, found "
            f"{manifest['physical_sample_id'].nunique()}"
        )
    family_counts = Counter(manifest["dataset_family"])
    if dict(family_counts) != EXPECTED_FAMILY_COUNTS:
        errors.append(
            f"family counts differ: {dict(family_counts)} != {EXPECTED_FAMILY_COUNTS}"
        )
    if set(manifest["measurement_domain"]) != {"experimental"}:
        errors.append("all Literature-External-v1 patterns must be experimental")

    expected_names = {f"LITV1_{index:04d}" for index in range(1, 79)}
    if set(manifest["sample_id"]) != expected_names:
        errors.append("sample IDs are not exactly LITV1_0001 through LITV1_0078")

    manifest_patterns = set(manifest["pattern_filename"])
    actual_patterns = {path.name for path in (blind_root / "patterns").glob("*.xy")}
    if manifest_patterns != actual_patterns:
        errors.append(
            "pattern file set differs from manifest: "
            f"missing={sorted(manifest_patterns - actual_patterns)}, "
            f"extra={sorted(actual_patterns - manifest_patterns)}"
        )

    for row in manifest.itertuples(index=False):
        expected_filename = f"{row.sample_id}.xy"
        if row.pattern_filename != expected_filename:
            errors.append(
                f"{row.sample_id}: filename {row.pattern_filename} != {expected_filename}"
            )
            continue
        if not re.fullmatch(r"[A-Z][a-z]?(;[A-Z][a-z]?)*", row.sample_elements):
            errors.append(f"{row.sample_id}: malformed sample_elements")
        elements = row.sample_elements.split(";")
        if elements != sorted(set(elements)):
            errors.append(f"{row.sample_id}: elements are not sorted and unique")
        if int(row.element_count) != len(elements):
            errors.append(f"{row.sample_id}: element_count mismatch")

        pattern_path = blind_root / "patterns" / row.pattern_filename
        if not pattern_path.exists():
            continue
        try:
            data = parse_pattern(pattern_path)
        except ValueError as error:
            errors.append(str(error))
            continue
        checks = {
            "n_grid_points": (len(data), int(row.n_grid_points), 0),
            "two_theta_min_deg": (data[0, 0], float(row.two_theta_min_deg), 5e-6),
            "two_theta_max_deg": (data[-1, 0], float(row.two_theta_max_deg), 5e-6),
            "median_step_deg": (
                float(np.median(np.diff(data[:, 0]))),
                float(row.median_step_deg),
                5e-6,
            ),
        }
        for label, (actual, expected, tolerance) in checks.items():
            if abs(actual - expected) > tolerance:
                errors.append(
                    f"{row.sample_id}: {label} {actual} != manifest {expected}"
                )
        actual_hash = sha256(pattern_path)
        if actual_hash != row.pattern_sha256:
            errors.append(f"{row.sample_id}: pattern SHA-256 mismatch")

    precursor = manifest[manifest["dataset_family"] == "dara_precursor_20x2"]
    paired_counts = Counter(precursor["physical_sample_id"])
    if len(paired_counts) != 20 or set(paired_counts.values()) != {2}:
        errors.append("Dara precursor rows are not exactly 20 paired acquisitions")
    if set(precursor["acquisition_variant"]) != {"2min", "8min"}:
        errors.append("Dara precursor acquisition variants must be 2min and 8min")

    profile_root = dataset_root / "instrument_metadata"
    profile_map_path = profile_root / "dara_profile_map.csv"
    strategy_path = profile_root / "profile_strategy.md"
    if not strategy_path.is_file():
        errors.append("missing frozen instrument profile strategy")
    if not profile_map_path.is_file():
        errors.append("missing Dara instrument profile map")
    else:
        profile_map = pd.read_csv(profile_map_path, dtype=str, keep_default_na=False)
        required_profile_columns = {
            "dataset_family",
            "instrument_profile",
            "match_status",
            "rationale",
        }
        if not required_profile_columns.issubset(profile_map.columns):
            errors.append("Dara profile map is missing required columns")
        elif profile_map["dataset_family"].duplicated().any():
            errors.append("Dara profile map contains duplicate dataset families")
        elif set(profile_map["dataset_family"]) != set(EXPECTED_FAMILY_COUNTS):
            errors.append("Dara profile map does not cover exactly four families")
        elif (profile_map["instrument_profile"].str.strip() == "").any():
            errors.append("Dara profile map contains an empty profile name")

    validation_report_path = dataset_root / "validation_report.json"
    if not validation_report_path.is_file():
        errors.append("missing public validation report")
    else:
        public_report = json.loads(validation_report_path.read_text(encoding="utf-8"))
        forbidden_report_keys = {
            "truth_rows",
            "phase_counts",
            "truth_phase_count",
            "truth_phase_counts",
        }
        leaked_keys = sorted(forbidden_report_keys & set(public_report))
        if leaked_keys:
            errors.append(f"validation report leaks truth-derived keys: {leaked_keys}")
        if public_report.get("phase_count_disclosed") is not False:
            errors.append("validation report must state phase_count_disclosed=false")

    checksum_path = dataset_root / "public_checksums_sha256.csv"
    if checksum_path.exists() and not args.write_checksums:
        checksums = pd.read_csv(checksum_path, dtype=str)
        expected_paths = {
            str(path.relative_to(dataset_root)): path
            for path in public_files(dataset_root)
        }
        if set(checksums["relative_path"]) != set(expected_paths):
            errors.append("public checksum file list does not match public package files")
        else:
            for row in checksums.itertuples(index=False):
                path = expected_paths[row.relative_path]
                if sha256(path) != row.sha256 or path.stat().st_size != int(row.size_bytes):
                    errors.append(f"public checksum mismatch: {row.relative_path}")

    report = {
        "status": "PASS" if not errors else "FAIL",
        "dataset_root": str(dataset_root),
        "n_acquisitions": len(manifest),
        "n_physical_samples": int(manifest["physical_sample_id"].nunique()),
        "family_counts": dict(family_counts),
        "n_pattern_files": len(actual_patterns),
        "private_scoring_present": (dataset_root / "private_scoring").exists(),
        "errors": errors,
    }
    print(json.dumps(report, indent=2))
    if errors:
        raise SystemExit(1)

    if args.write_checksums:
        rows = [
            {
                "relative_path": str(path.relative_to(dataset_root)),
                "sha256": sha256(path),
                "size_bytes": path.stat().st_size,
            }
            for path in public_files(dataset_root)
        ]
        pd.DataFrame(rows).to_csv(
            dataset_root / "public_checksums_sha256.csv", index=False
        )
        print(
            f"Wrote {len(rows)} public-only checksums to "
            f"{dataset_root / 'public_checksums_sha256.csv'}"
        )


if __name__ == "__main__":
    main()
