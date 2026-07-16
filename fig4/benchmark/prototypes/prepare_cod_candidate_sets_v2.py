"""Prepare element-conditioned COD candidate sets for Dara and CrystalShift.

This script reads only the public v2 manifest. It never reads Atomly generator
CIFs or private truth. The resulting candidate sets are the native COD front-end
for Dara and the explicitly named external front-end for CrystalShift.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
from dara.structure_db import CODDatabase


ROOT = Path(__file__).resolve().parents[3]
BLIND_ROOT = ROOT / "fig4/benchmark/datasets/atomly_core_v2/native_blind_package_v2"
OUT_ROOT = ROOT / "fig4/benchmark/method_inputs/cod_native_v2"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--cod-root",
        type=Path,
        default=None,
        help="Optional local COD mirror. Without it, Dara downloads required CIFs online.",
    )
    parser.add_argument("--limit-systems", type=int, default=None)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def system_key(elements: str) -> str:
    return "-".join(sorted(str(elements).split(";")))


def main() -> None:
    args = parse_args()
    manifest = pd.read_csv(BLIND_ROOT / "sample_manifest.csv")
    manifest["system_key"] = manifest["sample_elements"].map(system_key)
    systems = manifest[["system_key", "sample_elements"]].drop_duplicates()
    systems.sort_values("system_key", inplace=True)
    if args.limit_systems is not None:
        systems = systems.head(args.limit_systems)

    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    database = CODDatabase(path_to_cifs=args.cod_root)
    records = []
    for row in systems.itertuples(index=False):
        system_root = OUT_ROOT / row.system_key
        cif_root = system_root / "cifs"
        existing = sorted(cif_root.glob("*.cif")) if cif_root.exists() else []
        status = "cached"
        if args.force or not existing:
            cif_root.mkdir(parents=True, exist_ok=True)
            database.get_cifs_by_chemsys(
                str(row.sample_elements).split(";"),
                copy_files=True,
                dest_dir=str(cif_root),
            )
            existing = sorted(cif_root.glob("*.cif"))
            status = "prepared"
        record = {
            "system_key": row.system_key,
            "sample_elements": row.sample_elements,
            "candidate_count": len(existing),
            "status": status,
            "candidate_directory": str(cif_root.relative_to(ROOT)),
            "database": "Dara COD filtered index 2024",
        }
        records.append(record)
        print(f"{row.system_key}: {len(existing)} COD candidates ({status})", flush=True)

    pd.DataFrame(records).to_csv(OUT_ROOT / "candidate_set_summary.csv", index=False)
    provenance = {
        "input_manifest": str((BLIND_ROOT / "sample_manifest.csv").relative_to(ROOT)),
        "database_class": "dara.structure_db.CODDatabase",
        "local_cod_root": str(args.cod_root) if args.cod_root else None,
        "selection_rule": "all database phases whose element set is a nonempty subset of sample_elements, followed by Dara COD preprocessing",
        "private_generator_cifs_used": False,
        "systems_prepared": len(records),
    }
    (OUT_ROOT / "provenance.json").write_text(
        json.dumps(provenance, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
