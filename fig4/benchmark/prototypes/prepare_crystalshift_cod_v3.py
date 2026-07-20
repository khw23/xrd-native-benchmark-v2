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
    parser.add_argument("--system-key", action="append", default=[])
    parser.add_argument("--resume", action="store_true")
    return parser.parse_args()


def system_key(elements: str) -> str:
    return "-".join(sorted(str(elements).split(";")))


def database_id(path: Path) -> str:
    match = re.search(r"\(cod_([^\)]+)\)", path.stem, flags=re.IGNORECASE)
    return match.group(1) if match else path.stem


def normalize_crystalshift_block(block: str) -> str:
    """Make the unquoted CrystalShift header safe for its comma parser."""
    header, separator, remainder = block.partition("\n")
    fields = header.split(",")
    if len(fields) < 9:
        raise ValueError(f"CrystalShift header has {len(fields)} fields; expected >= 9")
    crystal_system_index = len(fields) - 7
    phase_name = "_".join(fields[1:crystal_system_index])
    crystal_system = fields[crystal_system_index]
    if crystal_system not in {
        "triclinic",
        "monoclinic",
        "orthohombic",
        "tetragonal",
        "trigonal",
        "hexagonal",
        "cubic",
    }:
        raise ValueError(f"Unsupported CrystalShift crystal system: {crystal_system!r}")
    for value in fields[crystal_system_index + 1 :]:
        float(value)
    normalized = [fields[0], phase_name, *fields[crystal_system_index:]]
    return ",".join(normalized) + separator + remainder


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
    if args.system_key:
        requested = set(args.system_key)
        unknown = requested.difference(systems)
        if unknown:
            raise ValueError(f"Unknown system keys: {sorted(unknown)}")
        systems = [key for key in systems if key in requested]
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
                f"No COD candidates for {key}; run prepare_cod_candidate_sets_v3.py first"
            )
        system_root = OUT_ROOT / key
        system_root.mkdir(exist_ok=True)
        sticks_path = system_root / "candidate_sticks.csv"
        map_path = system_root / "phase_id_map.csv"
        failure_path = system_root / "conversion_failures.csv"
        if args.resume and sticks_path.is_file() and map_path.is_file():
            existing_rows = pd.read_csv(map_path).to_dict("records")
            existing_failures = (
                pd.read_csv(failure_path).to_dict("records")
                if failure_path.is_file() and failure_path.stat().st_size
                else []
            )
            expected_names = {path.name for path in cif_paths}
            recorded_names = {
                str(row["candidate_cif_filename"])
                for row in existing_rows + existing_failures
            }
            phase_ids = [int(row["crystalshift_phase_id"]) for row in existing_rows]
            if (
                existing_rows
                and sticks_path.stat().st_size
                and recorded_names == expected_names
                and phase_ids == list(range(len(existing_rows)))
            ):
                all_failures.extend(existing_failures)
                summaries.append(
                    {
                        "system_key": key,
                        "cod_candidate_count": len(cif_paths),
                        "converted_candidate_count": len(existing_rows),
                        "conversion_failure_count": len(existing_failures),
                    }
                )
                print(
                    f"{key}: recorded {len(existing_rows)}/{len(cif_paths)}; skipped",
                    flush=True,
                )
                continue
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
                    block = normalize_crystalshift_block(
                        temp_output.read_text(encoding="utf-8")
                    )
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
        sticks_path.write_text("".join(blocks), encoding="utf-8")
        pd.DataFrame(rows).to_csv(map_path, index=False)
        pd.DataFrame(
            failures,
            columns=[
                "system_key",
                "candidate_cif_filename",
                "database_id",
                "error_type",
                "error",
            ],
        ).to_csv(failure_path, index=False)
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
    pd.DataFrame(
        summaries,
        columns=[
            "system_key",
            "cod_candidate_count",
            "converted_candidate_count",
            "conversion_failure_count",
        ],
    ).to_csv(OUT_ROOT / "preparation_summary.csv", index=False)
    pd.DataFrame(
        all_failures,
        columns=[
            "system_key",
            "candidate_cif_filename",
            "database_id",
            "error_type",
            "error",
        ],
    ).to_csv(OUT_ROOT / "conversion_failures.csv", index=False)
    SNAPSHOT_ROOT.mkdir(parents=True, exist_ok=True)
    shutil.copy2(
        OUT_ROOT / "preparation_summary.csv", SNAPSHOT_ROOT / "preparation_summary.csv"
    )
    shutil.copy2(
        OUT_ROOT / "conversion_failures.csv", SNAPSHOT_ROOT / "conversion_failures.csv"
    )


if __name__ == "__main__":
    main()
