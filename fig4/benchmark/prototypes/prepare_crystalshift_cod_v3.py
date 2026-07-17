"""Build CrystalShift inputs from the frozen COD front-end and public v3 data."""

from __future__ import annotations

import argparse
import importlib.util
import io
import re
import shutil
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

import numpy as np
import pandas as pd
from pymatgen.core import Structure
from pymatgen.symmetry.analyzer import SpacegroupAnalyzer
from scipy import sparse
from scipy.sparse.linalg import spsolve


ROOT = Path(__file__).resolve().parents[3]
BLIND_ROOT = ROOT / "fig4/benchmark/datasets/atomly_core_v3/native_blind_package_v3"
COD_ROOT = ROOT / "fig4/benchmark/method_inputs/cod_native_v3"
OUT_ROOT = ROOT / "fig4/benchmark/method_inputs/crystalshift_cod_v3"
SNAPSHOT_ROOT = (
    ROOT
    / "fig4/benchmark/results/atomly_core_v3/crystaltree_cod_frontend/input_preparation"
)
DEFAULT_CONVERTER = ROOT / "fig4/benchmark/third_party/crystalshift/src/cif_to_input_file.py"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--converter", type=Path, default=DEFAULT_CONVERTER)
    parser.add_argument("--limit-systems", type=int, default=None)
    return parser.parse_args()


def system_key(elements: str) -> str:
    return "-".join(sorted(str(elements).split(";")))


def database_id(path: Path) -> str:
    match = re.search(r"\(cod_([^\)]+)\)", path.stem, flags=re.IGNORECASE)
    return match.group(1) if match else path.stem


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
    all_failures = []
    for key in systems:
        cif_paths = sorted((COD_ROOT / key / "cifs").glob("*.cif"))
        if not cif_paths:
            raise FileNotFoundError(
                f"No COD candidates for {key}; run prepare_cod_candidate_sets_v2.py first"
            )
        system_root = OUT_ROOT / key
        system_root.mkdir(exist_ok=True)
        blocks = []
        rows = []
        failures = []
        for path in cif_paths:
            try:
                with tempfile.TemporaryDirectory() as temp_dir:
                    temp_output = Path(temp_dir) / "candidate.csv"
                    with redirect_stdout(io.StringIO()):
                        converter.cif_to_input(
                            [path], str(temp_output), q_range=(7.0, 58.0), wvlen=1.5406
                        )
                    block = temp_output.read_text(encoding="utf-8")
                phase_id = len(rows)
                first, rest = block.split(",", maxsplit=1)
                if first.strip() != "0":
                    raise ValueError(f"Unexpected converter phase id: {first!r}")
                structure = Structure.from_file(path)
                analyzer = SpacegroupAnalyzer(structure, symprec=0.1, angle_tolerance=5)
                blocks.append(f"{phase_id},{rest}")
                rows.append(
                    {
                        "crystalshift_phase_id": phase_id,
                        "candidate_cif_filename": path.name,
                        "database_id": database_id(path),
                        "formula": structure.composition.reduced_formula,
                        "space_group_symbol": analyzer.get_space_group_symbol(),
                        "space_group_number": analyzer.get_space_group_number(),
                        "elements": ";".join(
                            sorted(str(e) for e in structure.composition.elements)
                        ),
                    }
                )
            except Exception as error:
                failures.append(
                    {
                        "system_key": key,
                        "candidate_cif_filename": path.name,
                        "database_id": database_id(path),
                        "error_type": type(error).__name__,
                        "error": str(error),
                    }
                )
        all_failures.extend(failures)
        if not rows:
            raise RuntimeError(f"No COD candidate could be converted for {key}")
        (system_root / "candidate_sticks.csv").write_text(
            "".join(blocks), encoding="utf-8"
        )
        pd.DataFrame(rows).to_csv(system_root / "phase_id_map.csv", index=False)
        pd.DataFrame(failures).to_csv(system_root / "conversion_failures.csv", index=False)
        summaries.append(
            {
                "system_key": key,
                "cod_candidate_count": len(cif_paths),
                "converted_candidate_count": len(rows),
                "conversion_failure_count": len(failures),
            }
        )
        print(
            f"{key}: {len(rows)}/{len(cif_paths)} CrystalShift candidates converted",
            flush=True,
        )
    pd.DataFrame(summaries).to_csv(OUT_ROOT / "preparation_summary.csv", index=False)
    pd.DataFrame(all_failures).to_csv(OUT_ROOT / "conversion_failures.csv", index=False)
    SNAPSHOT_ROOT.mkdir(parents=True, exist_ok=True)
    shutil.copy2(
        OUT_ROOT / "preparation_summary.csv", SNAPSHOT_ROOT / "preparation_summary.csv"
    )
    shutil.copy2(
        OUT_ROOT / "conversion_failures.csv", SNAPSHOT_ROOT / "conversion_failures.csv"
    )


if __name__ == "__main__":
    main()
