"""Run Dara on v2 using COD candidates selected only from public elements."""

from __future__ import annotations

import argparse
import json
import os
import re
import time
import traceback
from pathlib import Path

import pandas as pd
import ray
from dara.cif import Cif
from dara.search import search_phases
from dara.utils import process_phase_name
from pymatgen.core import Structure
from pymatgen.symmetry.analyzer import SpacegroupAnalyzer


ROOT = Path(__file__).resolve().parents[3]
BLIND_ROOT = ROOT / "fig4/benchmark/datasets/atomly_core_v2/native_blind_package_v2"
COD_ROOT = ROOT / "fig4/benchmark/method_inputs/cod_native_v2"
RESULT_ROOT = ROOT / "fig4/benchmark/results/atomly_core_v2/dara_cod_native"
PROFILE = "Rigaku-Miniflex-600-DTEXultra2-fds"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample-id", action="append", default=[])
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--num-cpus", type=int, default=8)
    parser.add_argument("--resume", action="store_true")
    return parser.parse_args()


def system_key(elements: str) -> str:
    return "-".join(sorted(str(elements).split(";")))


def database_id(path: Path) -> str:
    match = re.search(r"\(COD_([^\)]+)\)", path.stem)
    return match.group(1) if match else path.stem


def phase_metadata(cif_paths: list[Path]) -> tuple[dict[str, Path], dict[Path, dict]]:
    aliases: dict[str, Path] = {}
    metadata: dict[Path, dict] = {}
    for path in cif_paths:
        structure = Structure.from_file(path)
        analyzer = SpacegroupAnalyzer(structure, symprec=0.1, angle_tolerance=5)
        metadata[path] = {
            "formula": structure.composition.reduced_formula,
            "space_group_symbol": analyzer.get_space_group_symbol(),
            "space_group_number": analyzer.get_space_group_number(),
            "database_id": database_id(path),
        }
        for alias in {process_phase_name(Cif.from_file(path).name), process_phase_name(path.stem)}:
            if alias in aliases and aliases[alias] != path:
                raise RuntimeError(f"Dara phase-name collision for {alias}")
            aliases[alias] = path
    return aliases, metadata


def load_rows(path: Path, resume: bool) -> list[dict]:
    if not resume or not path.exists():
        return []
    try:
        return pd.read_csv(path).to_dict("records")
    except pd.errors.EmptyDataError:
        return []


def main() -> None:
    args = parse_args()
    samples = pd.read_csv(BLIND_ROOT / "sample_manifest.csv")
    if args.sample_id:
        samples = samples[samples["sample_id"].isin(args.sample_id)]
    if args.limit is not None:
        samples = samples.head(args.limit)
    if samples.empty:
        raise SystemExit("No samples selected")

    RESULT_ROOT.mkdir(parents=True, exist_ok=True)
    work_root = RESULT_ROOT / "work"
    work_root.mkdir(exist_ok=True)
    prediction_path = RESULT_ROOT / "predictions.csv"
    record_path = RESULT_ROOT / "run_records.json"
    predictions = load_rows(prediction_path, args.resume)
    records = (
        json.loads(record_path.read_text(encoding="utf-8"))
        if args.resume and record_path.exists()
        else []
    )
    completed = {row["sample_id"] for row in records if row.get("status") == "ok"}
    if not ray.is_initialized():
        ray.init(num_cpus=args.num_cpus, runtime_env={"working_dir": None})

    for sample in samples.itertuples(index=False):
        if sample.sample_id in completed:
            print(f"{sample.sample_id}: already complete; skipped", flush=True)
            continue
        predictions = [row for row in predictions if row.get("sample_id") != sample.sample_id]
        records = [row for row in records if row.get("sample_id") != sample.sample_id]
        started = time.perf_counter()
        try:
            key = system_key(sample.sample_elements)
            cif_paths = sorted((COD_ROOT / key / "cifs").glob("*.cif"))
            if not cif_paths:
                raise FileNotFoundError(
                    f"No COD candidates for {key}; run prepare_cod_candidate_sets_v2.py first"
                )
            aliases, metadata = phase_metadata(cif_paths)
            sample_work = work_root / sample.sample_id
            sample_work.mkdir(exist_ok=True)
            previous_cwd = Path.cwd()
            os.chdir(sample_work)
            try:
                results = search_phases(
                    BLIND_ROOT / "patterns" / sample.pattern_filename,
                    cif_paths,
                    max_phases=3,
                    wavelength="Cu",
                    instrument_profile=PROFILE,
                    express_mode=True,
                    enable_angular_cut=True,
                )
            finally:
                os.chdir(previous_cwd)
            if not results:
                raise RuntimeError("Dara returned no phase hypotheses")
            elapsed = time.perf_counter() - started
            for solution_rank, result in enumerate(results[:3], start=1):
                weights = result.refinement_result.get_phase_weights()
                for phase_rank, (raw_name, weight) in enumerate(
                    sorted(weights.items(), key=lambda item: float(item[1]), reverse=True),
                    start=1,
                ):
                    alias = process_phase_name(raw_name)
                    if alias not in aliases:
                        raise KeyError(f"Unmapped Dara phase name: {raw_name} -> {alias}")
                    path = aliases[alias]
                    info = metadata[path]
                    predictions.append(
                        {
                            "sample_id": sample.sample_id,
                            "method": "Dara 1.3.0 + COD 2024",
                            "solution_rank": solution_rank,
                            "phase_rank": phase_rank,
                            "predicted_formula": info["formula"],
                            "predicted_space_group_symbol": info["space_group_symbol"],
                            "predicted_space_group_number": info["space_group_number"],
                            "predicted_database": "COD",
                            "predicted_database_id": info["database_id"],
                            "predicted_weight_fraction": float(weight),
                            "confidence_or_score": float(result.refinement_result.lst_data.rwp),
                            "runtime_seconds": elapsed,
                            "status_or_note": "ok; score_is_Rwp_percent",
                            "predicted_cif_path": str(path.relative_to(ROOT)),
                        }
                    )
            best = results[0]
            records.append(
                {
                    "sample_id": sample.sample_id,
                    "status": "ok",
                    "runtime_seconds": elapsed,
                    "sample_elements": str(sample.sample_elements).split(";"),
                    "candidate_database": "Dara COD filtered index 2024",
                    "candidate_count": len(cif_paths),
                    "max_phases": 3,
                    "phase_count_prior": "global upper bound only; per-sample truth hidden",
                    "best_rwp_percent": float(best.refinement_result.lst_data.rwp),
                    "n_hypotheses": len(results),
                }
            )
            print(
                f"{sample.sample_id}: {len(cif_paths)} candidates, "
                f"Rwp={best.refinement_result.lst_data.rwp:.3f}%, {elapsed:.1f} s",
                flush=True,
            )
        except Exception as error:
            elapsed = time.perf_counter() - started
            records.append(
                {
                    "sample_id": sample.sample_id,
                    "status": "error",
                    "runtime_seconds": elapsed,
                    "error_type": type(error).__name__,
                    "error": str(error),
                    "traceback": traceback.format_exc(),
                }
            )
            print(f"{sample.sample_id}: ERROR after {elapsed:.1f} s: {error}", flush=True)
        pd.DataFrame(predictions).to_csv(prediction_path, index=False)
        record_path.write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
