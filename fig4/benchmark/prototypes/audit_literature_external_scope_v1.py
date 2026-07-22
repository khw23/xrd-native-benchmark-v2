"""Recompute public element-space coverage for Literature-External-v1."""

from __future__ import annotations

import json
from pathlib import Path
from zipfile import ZipFile

import pandas as pd


ROOT = Path(__file__).resolve().parents[3]
ATOMLY_PACKAGE = (
    ROOT
    / "fig4/benchmark/datasets/atomly_core_v3/native_blind_package_v3.zip"
)
EXTERNAL_MANIFEST = (
    ROOT
    / "fig4/benchmark/datasets/literature_external_v1/blind_package/sample_manifest.csv"
)
COVERAGE_ROOT = (
    ROOT / "fig4/benchmark/database_coverage/literature_external_v1"
)


def read_element_sets(path: Path, zip_member: str | None = None) -> set[tuple[str, ...]]:
    if zip_member is None:
        frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    else:
        with ZipFile(path) as archive, archive.open(zip_member) as handle:
            frame = pd.read_csv(handle, dtype=str, keep_default_na=False)
    return {
        tuple(sorted(set(value.split(";"))))
        for value in frame["sample_elements"]
    }


def oqmd_systems(full_sets: set[tuple[str, ...]]) -> set[str]:
    """Reproduce XERUS's one OQMD query per complete disclosed element set."""
    return {"-".join(elements) for elements in full_sets}


def main() -> None:
    atomly_sets = read_element_sets(
        ATOMLY_PACKAGE, "native_blind_package_v3/sample_manifest.csv"
    )
    external_sets = read_element_sets(EXTERNAL_MANIFEST)
    atomly_elements = set().union(*map(set, atomly_sets))
    external_elements = set().union(*map(set, external_sets))
    atomly_systems = oqmd_systems(atomly_sets)
    external_systems = oqmd_systems(external_sets)

    cod = pd.read_csv(
        COVERAGE_ROOT / "cod/required_cod_audit.csv",
        dtype=str,
        keep_default_na=False,
    )
    oqmd = pd.read_csv(
        COVERAGE_ROOT / "oqmd/required_systems_audit.csv",
        dtype=str,
        keep_default_na=False,
    )
    assert set(oqmd["system"]) == external_systems
    assert len(cod) == 2122
    assert len(external_systems) == 46

    report = {
        "status": "PASS",
        "atomly_unique_full_element_sets": len(atomly_sets),
        "external_unique_full_element_sets": len(external_sets),
        "external_only_full_element_sets": len(external_sets - atomly_sets),
        "overlapping_full_element_sets": len(external_sets & atomly_sets),
        "atomly_unique_elements": len(atomly_elements),
        "external_unique_elements": len(external_elements),
        "external_only_elements": sorted(external_elements - atomly_elements),
        "atomly_oqmd_full_systems": len(atomly_systems),
        "external_oqmd_full_systems": len(external_systems),
        "external_only_oqmd_full_systems": len(external_systems - atomly_systems),
        "overlapping_oqmd_full_systems": len(external_systems & atomly_systems),
        "required_unique_cod_cifs": len(cod),
    }
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
