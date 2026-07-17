"""Extract the public v3 blind package and verify its frozen checksums."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
DATASET_ROOT = ROOT / "fig4/benchmark/datasets/atomly_core_v3"
ARCHIVE = DATASET_ROOT / "native_blind_package_v3.zip"
BLIND_ROOT = DATASET_ROOT / "native_blind_package_v3"
EXPECTED_ARCHIVE_SHA256 = (
    "dde24eb5b1553f005c5da99a4bd2adf242ba6360ced0f8e4fed42238835e6243"
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    archive_hash = sha256(ARCHIVE)
    if archive_hash != EXPECTED_ARCHIVE_SHA256:
        raise RuntimeError(
            f"Blind archive checksum mismatch: {archive_hash} != {EXPECTED_ARCHIVE_SHA256}"
        )

    with zipfile.ZipFile(ARCHIVE) as archive:
        names = archive.namelist()
        lowered = [name.lower() for name in names]
        forbidden = ("ground_truth", "phase_pool", "atomly_cod", ".cif")
        leaked = [name for name, low in zip(names, lowered) if any(x in low for x in forbidden)]
        if leaked:
            raise RuntimeError(f"Blind archive leakage check failed: {leaked[:10]}")
        if args.force and BLIND_ROOT.exists():
            shutil.rmtree(BLIND_ROOT)
        if not BLIND_ROOT.exists():
            archive.extractall(DATASET_ROOT)

    manifest_path = BLIND_ROOT / "sample_manifest.csv"
    with manifest_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != 100:
        raise RuntimeError(f"Expected 100 samples, found {len(rows)}")
    for row in rows:
        pattern = BLIND_ROOT / "patterns" / row["pattern_filename"]
        actual = sha256(pattern)
        if actual != row["pattern_sha256"]:
            raise RuntimeError(f"Pattern checksum mismatch: {pattern}")

    report = {
        "status": "passed",
        "archive": str(ARCHIVE.relative_to(ROOT)),
        "archive_sha256": archive_hash,
        "samples": len(rows),
        "unique_element_systems": len({row["sample_elements"] for row in rows}),
        "blind_root": str(BLIND_ROOT.relative_to(ROOT)),
        "leakage_check": "no CIF, truth, phase pool, or Atomly-COD map",
    }
    (DATASET_ROOT / "public_input_validation.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
