"""Run Dara on v3 using COD candidates selected only from public elements."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import time
import traceback
from pathlib import Path

import pandas as pd
import ray
from dara.search import search_phases
from dara.utils import load_symmetrized_structure, process_phase_name


ROOT = Path(__file__).resolve().parents[3]
BLIND_ROOT = ROOT / "fig4/benchmark/datasets/atomly_core_v3/native_blind_package_v3"
COD_ROOT = ROOT / "fig4/benchmark/method_inputs/cod_native_v3"
RESULT_ROOT = ROOT / "fig4/benchmark/results/atomly_core_v3/dara_cod_native"
PROFILE = "Rigaku-Miniflex-600-DTEXultra2-fds"
METHOD_NAME = "Dara 1.3.0 + COD 2024"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--blind-root", type=Path, default=BLIND_ROOT)
    parser.add_argument("--cod-root", type=Path, default=COD_ROOT)
    parser.add_argument("--result-root", type=Path, default=RESULT_ROOT)
    parser.add_argument("--instrument-profile", default=PROFILE)
    parser.add_argument(
        "--instrument-profile-map",
        type=Path,
        default=None,
        help="Optional CSV with dataset_family,instrument_profile columns.",
    )
    parser.add_argument("--dataset-family", action="append", default=[])
    parser.add_argument("--sample-id", action="append", default=[])
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--num-cpus", type=int, default=8)
    parser.add_argument(
        "--bgmn-threads",
        type=int,
        default=8,
        help="BGMN threads per refinement; total peak concurrency is num-cpus * bgmn-threads.",
    )
    parser.add_argument("--resume", action="store_true")
    parser.add_argument(
        "--retry-failures",
        action="store_true",
        help="With --resume, rerun recorded failures instead of skipping them.",
    )
    return parser.parse_args()


def system_key(elements: str) -> str:
    return "-".join(sorted(str(elements).split(";")))


def database_id(path: Path) -> str:
    match = re.search(r"\(cod_([^\)]+)\)", path.stem, flags=re.IGNORECASE)
    return match.group(1) if match else path.stem


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def failure_category(error: Exception) -> str:
    if isinstance(error, (TimeoutError, subprocess.TimeoutExpired)):
        return "timeout"
    if isinstance(error, FileNotFoundError):
        return "database_missing"
    if isinstance(error, OSError) and getattr(error, "errno", None) == 8:
        return "installation_failure"
    message = str(error).lower()
    if "exec format" in message or "glibc" in message:
        return "installation_failure"
    return "calculation_failure"


def phase_aliases(cif_paths: list[Path]) -> dict[str, Path]:
    aliases: dict[str, Path] = {}
    for path in cif_paths:
        alias = process_phase_name(path.stem)
        if alias in aliases and aliases[alias] != path:
            raise RuntimeError(f"Dara phase-name collision for {alias}")
        aliases[alias] = path
    return aliases


def structure_metadata(path: Path) -> dict:
    structure, analyzer = load_symmetrized_structure(path)
    return {
        "formula": structure.composition.reduced_formula,
        "space_group_symbol": analyzer.get_space_group_symbol(),
        "space_group_number": analyzer.get_space_group_number(),
        "database_id": database_id(path),
    }


def load_rows(path: Path, resume: bool) -> list[dict]:
    if not resume or not path.exists():
        return []
    try:
        return pd.read_csv(path).to_dict("records")
    except pd.errors.EmptyDataError:
        return []


def main() -> None:
    args = parse_args()
    blind_root = args.blind_root.resolve()
    cod_root = args.cod_root.resolve()
    result_root = args.result_root.resolve()
    manifest_path = blind_root / "sample_manifest.csv"
    samples = pd.read_csv(manifest_path)
    if args.dataset_family:
        samples = samples[samples["dataset_family"].isin(args.dataset_family)]
    if args.sample_id:
        samples = samples[samples["sample_id"].isin(args.sample_id)]
    if args.limit is not None:
        samples = samples.head(args.limit)
    if samples.empty:
        raise SystemExit("No samples selected")

    profile_map = {}
    if args.instrument_profile_map is not None:
        profile_map_path = args.instrument_profile_map.resolve()
        profile_frame = pd.read_csv(profile_map_path, dtype=str)
        required = {"dataset_family", "instrument_profile"}
        if not required.issubset(profile_frame.columns):
            raise ValueError(
                "Instrument profile map requires dataset_family,instrument_profile"
            )
        if profile_frame["dataset_family"].duplicated().any():
            raise ValueError("Instrument profile map contains duplicate families")
        profile_map = dict(
            zip(
                profile_frame["dataset_family"],
                profile_frame["instrument_profile"],
                strict=True,
            )
        )
        missing = sorted(set(samples["dataset_family"]) - set(profile_map))
        if missing:
            raise ValueError(f"Instrument profile map lacks families: {missing}")
    else:
        profile_map_path = None

    result_root.mkdir(parents=True, exist_ok=True)
    work_root = result_root / "work"
    work_root.mkdir(exist_ok=True)
    prediction_path = result_root / "predictions.csv"
    record_path = result_root / "run_records.json"
    failure_history_path = result_root / "failure_history.jsonl"
    environment_path = result_root / "environment.json"
    stable_environment = {
        "blind_manifest_sha256": sha256(manifest_path),
        "cod_root": str(cod_root),
        "instrument_profile": args.instrument_profile,
        "instrument_profile_map_sha256": (
            sha256(profile_map_path) if profile_map_path is not None else None
        ),
    }
    if args.resume and environment_path.exists():
        previous_environment = json.loads(
            environment_path.read_text(encoding="utf-8")
        )
        mismatches = [
            key
            for key, value in stable_environment.items()
            if previous_environment.get(key) != value
        ]
        if mismatches:
            raise RuntimeError(
                "Existing Dara result environment differs for "
                f"{mismatches}; choose a new --result-root"
            )
    if not args.resume and (prediction_path.exists() or record_path.exists()):
        raise FileExistsError(
            f"Result files already exist in {result_root}. Use --resume or choose "
            "a new --result-root; existing results will not be overwritten."
        )
    predictions = load_rows(prediction_path, args.resume)
    records = (
        json.loads(record_path.read_text(encoding="utf-8"))
        if args.resume and record_path.exists()
        else []
    )
    recorded_status = {
        row["sample_id"]: row.get("status")
        for row in records
        if row.get("status") == "ok"
        or (row.get("status") == "error" and not args.retry_failures)
    }
    for sample in samples.itertuples(index=False):
        if sample.sample_id in recorded_status:
            print(
                f"{sample.sample_id}: recorded {recorded_status[sample.sample_id]}; skipped",
                flush=True,
            )
            continue
        if not ray.is_initialized():
            ray.init(num_cpus=args.num_cpus, runtime_env={"working_dir": None})
        predictions = [row for row in predictions if row.get("sample_id") != sample.sample_id]
        records = [row for row in records if row.get("sample_id") != sample.sample_id]
        started = time.perf_counter()
        try:
            instrument_profile = profile_map.get(
                str(getattr(sample, "dataset_family", "")), args.instrument_profile
            )
            key = system_key(sample.sample_elements)
            cif_paths = sorted((cod_root / key / "cifs").glob("*.cif"))
            if not cif_paths:
                raise FileNotFoundError(
                    f"No COD candidates for {key}; run prepare_cod_candidate_sets_v3.py first"
                )
            aliases = phase_aliases(cif_paths)
            sample_work = work_root / sample.sample_id
            sample_work.mkdir(exist_ok=True)
            previous_cwd = Path.cwd()
            os.chdir(sample_work)
            try:
                results = search_phases(
                    blind_root / "patterns" / sample.pattern_filename,
                    cif_paths,
                    max_phases=3,
                    wavelength="Cu",
                    instrument_profile=instrument_profile,
                    express_mode=True,
                    enable_angular_cut=True,
                    refinement_params={"n_threads": args.bgmn_threads},
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
                    info = structure_metadata(path)
                    selected_root = result_root / "selected_cifs" / sample.sample_id
                    selected_root.mkdir(parents=True, exist_ok=True)
                    selected_path = selected_root / (
                        f"solution{solution_rank}_phase{phase_rank}_COD_{info['database_id']}.cif"
                    )
                    shutil.copy2(path, selected_path)
                    predictions.append(
                        {
                            "sample_id": sample.sample_id,
                            "method": METHOD_NAME,
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
                            "predicted_cif_path": str(selected_path.relative_to(ROOT)),
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
                    "ray_num_cpus": args.num_cpus,
                    "bgmn_threads_per_refinement": args.bgmn_threads,
                    "phase_count_prior": "global upper bound only; per-sample truth hidden",
                    "instrument_profile": instrument_profile,
                    "best_rwp_percent": float(best.refinement_result.lst_data.rwp),
                    "n_hypotheses": len(results),
                    "pattern_sha256": sha256(
                        blind_root / "patterns" / sample.pattern_filename
                    ),
                }
            )
            print(
                f"{sample.sample_id}: {len(cif_paths)} candidates, "
                f"Rwp={best.refinement_result.lst_data.rwp:.3f}%, {elapsed:.1f} s",
                flush=True,
            )
        except Exception as error:
            elapsed = time.perf_counter() - started
            category = failure_category(error)
            key = system_key(sample.sample_elements)
            instrument_profile = profile_map.get(
                str(getattr(sample, "dataset_family", "")), args.instrument_profile
            )
            cif_paths = sorted((cod_root / key / "cifs").glob("*.cif"))
            predictions.append(
                {
                    "sample_id": sample.sample_id,
                    "method": METHOD_NAME,
                    "solution_rank": "",
                    "phase_rank": "",
                    "predicted_formula": "",
                    "predicted_space_group_symbol": "",
                    "predicted_space_group_number": "",
                    "predicted_database": "COD",
                    "predicted_database_id": "",
                    "predicted_weight_fraction": "",
                    "confidence_or_score": "",
                    "runtime_seconds": elapsed,
                    "status_or_note": f"{category}: {type(error).__name__}: {error}",
                    "predicted_cif_path": "",
                }
            )
            failure_record = {
                "sample_id": sample.sample_id,
                "status": "error",
                "failure_category": category,
                "runtime_seconds": elapsed,
                "sample_elements": str(sample.sample_elements).split(";"),
                "candidate_database": "Dara COD filtered index 2024",
                "candidate_count": len(cif_paths),
                "max_phases": 3,
                "ray_num_cpus": args.num_cpus,
                "bgmn_threads_per_refinement": args.bgmn_threads,
                "phase_count_prior": "global upper bound only; per-sample truth hidden",
                "instrument_profile": instrument_profile,
                "error_type": type(error).__name__,
                "error": str(error),
                "traceback": traceback.format_exc(),
                "pattern_sha256": sha256(
                    blind_root / "patterns" / sample.pattern_filename
                ),
            }
            records.append(failure_record)
            with failure_history_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(failure_record) + "\n")
            print(f"{sample.sample_id}: ERROR after {elapsed:.1f} s: {error}", flush=True)
        pd.DataFrame(predictions).to_csv(prediction_path, index=False)
        record_path.write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")

    environment_path.write_text(
        json.dumps(
            {
                "method": METHOD_NAME,
                "blind_manifest": str(manifest_path),
                **stable_environment,
                "instrument_profile_map": (
                    str(profile_map_path) if profile_map_path is not None else None
                ),
                "num_cpus": args.num_cpus,
                "bgmn_threads_per_refinement": args.bgmn_threads,
                "private_truth_used": False,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
