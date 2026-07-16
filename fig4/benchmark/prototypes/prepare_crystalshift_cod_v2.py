"""Build CrystalShift inputs from the frozen COD front-end and public v2 data."""

from __future__ import annotations

import argparse
import importlib.util
import io
from contextlib import redirect_stdout
from pathlib import Path

import numpy as np
import pandas as pd
from pymatgen.core import Structure
from pymatgen.symmetry.analyzer import SpacegroupAnalyzer
from scipy import sparse
from scipy.sparse.linalg import spsolve


ROOT = Path(__file__).resolve().parents[3]
BLIND_ROOT = ROOT / "fig4/benchmark/datasets/atomly_core_v2/native_blind_package_v2"
COD_ROOT = ROOT / "fig4/benchmark/method_inputs/cod_native_v2"
OUT_ROOT = ROOT / "fig4/benchmark/method_inputs/crystalshift_cod_v2"
DEFAULT_CONVERTER = ROOT / "fig4/benchmark/third_party/crystalshift/src/cif_to_input_file.py"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--converter", type=Path, default=DEFAULT_CONVERTER)
    parser.add_argument("--limit-systems", type=int, default=None)
    return parser.parse_args()


def system_key(elements: str) -> str:
    return "-".join(sorted(str(elements).split(";")))


def baseline_asls(
    intensity: np.ndarray,
    smoothness: float = 1e7,
    asymmetry: float = 0.001,
    iterations: int = 10,
) -> np.ndarray:
    n_points = len(intensity)
    difference = sparse.diags(
        [np.ones(n_points), -2 * np.ones(n_points), np.ones(n_points)],
        [0, 1, 2],
        shape=(n_points - 2, n_points),
    )
    penalty = (smoothness * difference.T @ difference).tocsc()
    weights = np.ones(n_points)
    result = np.zeros(n_points)
    for _ in range(iterations):
        matrix = sparse.spdiags(weights, 0, n_points, n_points, format="csc")
        result = spsolve(matrix + penalty, weights * intensity)
        weights = asymmetry * (intensity > result) + (1 - asymmetry) * (
            intensity <= result
        )
    return result


def main() -> None:
    args = parse_args()
    if not args.converter.exists():
        raise FileNotFoundError(
            f"CrystalShift converter not found: {args.converter}. Clone CrystalShift.jl "
            "and pass --converter /path/to/CrystalShift.jl/src/cif_to_input_file.py"
        )
    spec = importlib.util.spec_from_file_location("crystalshift_converter", args.converter)
    converter = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(converter)

    manifest = pd.read_csv(BLIND_ROOT / "sample_manifest.csv")
    manifest["system_key"] = manifest["sample_elements"].map(system_key)
    systems = sorted(manifest["system_key"].unique())
    if args.limit_systems is not None:
        systems = systems[: args.limit_systems]
    OUT_ROOT.mkdir(parents=True, exist_ok=True)

    pattern_root = OUT_ROOT / "patterns_preprocessed"
    pattern_root.mkdir(exist_ok=True)
    for path in sorted((BLIND_ROOT / "patterns").glob("*.xy")):
        raw = np.loadtxt(path)
        corrected = np.clip(raw[:, 1] - baseline_asls(raw[:, 1]), 0.0, None)
        corrected /= max(float(corrected.max()), np.finfo(float).tiny)
        selected = np.arange(0, len(raw), 4)
        np.savetxt(
            pattern_root / path.name,
            np.column_stack([raw[selected, 0], corrected[selected]]),
            fmt=["%.5f", "%.10g"],
            header="2theta_deg baseline_corrected_normalized_intensity; CrystalShift adapter",
        )

    summaries = []
    for key in systems:
        cif_paths = sorted((COD_ROOT / key / "cifs").glob("*.cif"))
        if not cif_paths:
            raise FileNotFoundError(
                f"No COD candidates for {key}; run prepare_cod_candidate_sets_v2.py first"
            )
        system_root = OUT_ROOT / key
        system_root.mkdir(exist_ok=True)
        with redirect_stdout(io.StringIO()):
            converter.cif_to_input(
                cif_paths,
                str(system_root / "candidate_sticks.csv"),
                q_range=(7.0, 58.0),
                wvlen=1.5406,
            )
        rows = []
        for phase_id, path in enumerate(cif_paths):
            structure = Structure.from_file(path)
            analyzer = SpacegroupAnalyzer(structure, symprec=0.1, angle_tolerance=5)
            rows.append(
                {
                    "crystalshift_phase_id": phase_id,
                    "candidate_cif_filename": path.name,
                    "formula": structure.composition.reduced_formula,
                    "space_group_symbol": analyzer.get_space_group_symbol(),
                    "space_group_number": analyzer.get_space_group_number(),
                    "elements": ";".join(sorted(str(e) for e in structure.composition.elements)),
                }
            )
        pd.DataFrame(rows).to_csv(system_root / "phase_id_map.csv", index=False)
        summaries.append({"system_key": key, "candidate_count": len(rows)})
        print(f"{key}: {len(rows)} CrystalShift candidates", flush=True)
    pd.DataFrame(summaries).to_csv(OUT_ROOT / "preparation_summary.csv", index=False)


if __name__ == "__main__":
    main()
