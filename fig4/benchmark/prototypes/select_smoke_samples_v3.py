"""Select low/median/high candidate-count smoke samples without using truth."""

from __future__ import annotations

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
    samples["system_key"] = samples["sample_elements"].map(system_key)
    counts = pd.read_csv(COD_ROOT / "candidate_set_summary.csv")[
        ["system_key", "candidate_count"]
    ]
    merged = samples.merge(counts, on="system_key", validate="many_to_one")
    merged.sort_values(["candidate_count", "sample_id"], inplace=True)
    targets = [0.1, 0.5, 0.9]
    selected = []
    used = set()
    values = merged["candidate_count"].to_numpy(dtype=float)
    for label, quantile in zip(["low", "median", "high"], targets, strict=True):
        target = float(np.quantile(values, quantile))
        options = merged.assign(distance=(merged["candidate_count"] - target).abs())
        options = options[~options["sample_id"].isin(used)]
        row = options.sort_values(["distance", "candidate_count", "sample_id"]).iloc[0]
        used.add(row["sample_id"])
        selected.append(
            {
                "smoke_tier": label,
                "sample_id": row["sample_id"],
                "sample_elements": row["sample_elements"],
                "system_key": row["system_key"],
                "candidate_count": int(row["candidate_count"]),
            }
        )
    output = COD_ROOT / "smoke_samples.csv"
    pd.DataFrame(selected).to_csv(output, index=False)
    SNAPSHOT_ROOT.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(selected).to_csv(SNAPSHOT_ROOT / "smoke_samples.csv", index=False)
    print(pd.DataFrame(selected).to_string(index=False))


if __name__ == "__main__":
    main()
