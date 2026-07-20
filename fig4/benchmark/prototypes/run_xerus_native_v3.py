"""Run XERUS 1.1b on public v3 patterns with its native database workflow."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import math
import os
import platform
import shutil
import sys
import time
import traceback
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[3]
BLIND_ROOT = ROOT / "fig4/benchmark/datasets/atomly_core_v3/native_blind_package_v3"
RESULT_ROOT = ROOT / "fig4/benchmark/results/atomly_core_v3/xerus_native"
PROFILE = BLIND_ROOT / "instrument_metadata/GSASII_reference_profile.instprm"
METHOD_NAME = "XERUS 1.1b native database workflow"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample-id", action="append", default=[])
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--n-jobs", type=int, default=8)
    parser.add_argument("--result-root", type=Path, default=RESULT_ROOT)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--retry-failures", action="store_true")
    parser.add_argument(
        "--prepare-candidates-only",
        action="store_true",
        help=(
            "Populate XERUS's native MongoDB and save the candidate manifest, "
            "but do not simulate, correlate, or refine the pattern."
        ),
    )
    return parser.parse_args()


def as_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, float) and math.isnan(value):
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    if hasattr(value, "tolist") and not isinstance(value, str):
        converted = value.tolist()
        return converted if isinstance(converted, list) else [converted]
    if isinstance(value, str) and value.strip().startswith("["):
        try:
            parsed = ast.literal_eval(value)
            return list(parsed) if isinstance(parsed, (list, tuple)) else [parsed]
        except (SyntaxError, ValueError):
            pass
    return [value]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def repository_path(value: object) -> str:
    path = Path(str(value))
    absolute = path if path.is_absolute() else ROOT / path
    try:
        return str(absolute.absolute().relative_to(ROOT.absolute()))
    except ValueError:
        pass
    path = path.resolve()
    try:
        return str(path.relative_to(ROOT.resolve()))
    except ValueError:
        return str(path)


def prepare_xerus_xy(source: Path, sample_id: str, result_root: Path) -> Path:
    """Create the headerless two-column XY input required by XERUS 1.1b."""
    adapted_root = result_root / "preprocessed_inputs"
    adapted_root.mkdir(parents=True, exist_ok=True)
    target = adapted_root / f"{sample_id}.xy"
    data = pd.read_csv(
        source,
        sep=r"\s+",
        comment="#",
        header=None,
        names=["theta", "intensity"],
        dtype={"theta": float, "intensity": float},
    )
    if len(data) < 2 or data.isna().any().any():
        raise ValueError(f"Invalid numeric XY input: {source}")
    if not data["theta"].is_monotonic_increasing:
        raise ValueError(f"Non-monotonic two-theta values: {source}")
    data.to_csv(target, sep=" ", header=False, index=False)
    return target


def save_state(
    result_root: Path, predictions: list[dict], records: list[dict]
) -> None:
    pd.DataFrame(predictions).to_csv(result_root / "predictions.csv", index=False)
    (result_root / "run_records.json").write_text(
        json.dumps(records, indent=2) + "\n", encoding="utf-8"
    )


def save_candidate_snapshot(
    xray, sample_id: str, result_root: Path
) -> tuple[Path, pd.DataFrame]:
    """Save the provider/ID snapshot actually exposed to XERUS for one sample."""
    snapshot_root = result_root / "candidate_manifests"
    snapshot_root.mkdir(parents=True, exist_ok=True)
    source = getattr(xray, "cif_all", None)
    if not isinstance(source, pd.DataFrame):
        source = xray.cif_info
    snapshot = source.copy()
    if "full_path" in snapshot:
        snapshot["full_path"] = snapshot["full_path"].map(repository_path)
    target = snapshot_root / f"{sample_id}.csv"
    snapshot.to_csv(target, index=False)
    return target, snapshot


def main() -> None:
    args = parse_args()
    result_root = args.result_root.resolve()
    if not PROFILE.exists():
        raise FileNotFoundError("Run unpack_and_verify_v3.py first")

    # Import after the caller has set PYTHONPATH/GSASII_ROOT and patched XERUS.
    import Xerus
    from Xerus import XRay
    from Xerus.settings.settings import INSTR_PARAMS as XERUS_PROFILE

    configured_profile = Path(XERUS_PROFILE)
    if not configured_profile.exists() or sha256(configured_profile) != sha256(PROFILE):
        raise RuntimeError(
            "XERUS config.conf must point to a byte-identical copy of "
            "instrument_metadata/GSASII_reference_profile.instprm before import"
        )

    samples = pd.read_csv(BLIND_ROOT / "sample_manifest.csv")
    if args.sample_id:
        samples = samples[samples["sample_id"].isin(args.sample_id)]
    if args.limit is not None:
        samples = samples.head(args.limit)
    if samples.empty:
        raise SystemExit("No samples selected")

    result_root.mkdir(parents=True, exist_ok=True)
    prediction_path = result_root / "predictions.csv"
    record_path = result_root / "run_records.json"
    if not args.resume and (prediction_path.exists() or record_path.exists()):
        raise FileExistsError(
            f"Result files already exist in {result_root}. Use --resume or choose "
            "a new --result-root; existing results will not be overwritten."
        )
    predictions = (
        pd.read_csv(prediction_path).to_dict("records")
        if args.resume and prediction_path.exists()
        else []
    )
    records = (
        json.loads(record_path.read_text(encoding="utf-8"))
        if args.resume and record_path.exists()
        else []
    )
    recorded = {
        row["sample_id"]: row.get("status")
        for row in records
        if row.get("status") == "ok"
        or (row.get("status") == "error" and not args.retry_failures)
    }

    for sample in samples.itertuples(index=False):
        if sample.sample_id in recorded:
            print(f"{sample.sample_id}: recorded {recorded[sample.sample_id]}; skipped")
            continue
        predictions = [row for row in predictions if row.get("sample_id") != sample.sample_id]
        attempt = (
            sum(row.get("sample_id") == sample.sample_id for row in records) + 1
        )
        work = result_root / "work" / sample.sample_id
        work.mkdir(parents=True, exist_ok=True)
        elements = str(sample.sample_elements).split(";")
        source_pattern = BLIND_ROOT / "patterns" / sample.pattern_filename
        source_pattern_sha256 = sha256(source_pattern)
        started = time.perf_counter()
        try:
            xerus_pattern = prepare_xerus_xy(
                source_pattern, sample.sample_id, result_root
            )
            if sha256(source_pattern) != source_pattern_sha256:
                raise RuntimeError("Original XRD changed while preparing XERUS input")
            xray = XRay(
                name=sample.sample_id,
                working_folder=str(work),
                elements=elements,
                exp_data_file=str(xerus_pattern),
                data_fmt="xy",
                maxsys=len(elements),
                max_oxy=len(elements),
                remove_background=True,
                poly_degree=8,
                standarize_int=True,
                use_preprocessed=True,
            )
            xray.instr_params = str(PROFILE)
            if args.prepare_candidates_only:
                xray.get_cifs(ignore_provider=["AFLOW"])
                if xray.cif_info is None or xray.cif_info.empty:
                    raise RuntimeError("XERUS native providers returned no usable candidates")
                candidate_manifest, candidate_snapshot = save_candidate_snapshot(
                    xray, sample.sample_id, result_root
                )
                elapsed = time.perf_counter() - started
                records.append(
                    {
                        "sample_id": sample.sample_id,
                        "attempt": attempt,
                        "status": "candidates_ready",
                        "runtime_seconds": elapsed,
                        "sample_elements": elements,
                        "source_pattern": str(source_pattern.relative_to(ROOT)),
                        "source_pattern_sha256": source_pattern_sha256,
                        "xerus_input": str(xerus_pattern.relative_to(ROOT)),
                        "xerus_input_sha256": sha256(xerus_pattern),
                        "candidate_database": (
                            "XERUS native MP/COD/OQMD/ODBX cache; AFLOW ignored"
                        ),
                        "candidate_count": int(len(xray.cif_info)),
                        "candidate_snapshot_count": int(len(candidate_snapshot)),
                        "candidate_manifest": str(candidate_manifest.relative_to(ROOT)),
                        "network_stage_only": True,
                    }
                )
                print(
                    f"{sample.sample_id}: candidate snapshot ready "
                    f"({len(xray.cif_info)} usable candidates), {elapsed:.1f} s",
                    flush=True,
                )
                save_state(result_root, predictions, records)
                continue
            result = xray.analyze(
                n_runs=3,
                grabtop=3,
                delta=1.3,
                combine_filter=False,
                select_cifs=True,
                plot_all=False,
                ignore_provider=["AFLOW"],
                solver="box",
                group_method="system_type",
                auto_threshold=10,
                r_ori=False,
                n_jobs=args.n_jobs,
            )
            if result is None or result.empty:
                raise RuntimeError("XERUS returned no phase hypothesis")
            candidate_manifest, candidate_snapshot = save_candidate_snapshot(
                xray, sample.sample_id, result_root
            )
            best = result.iloc[0]
            ids = [str(x) for x in as_list(best.get("id"))]
            providers = [str(x) for x in as_list(best.get("provider"))]
            formulas = [str(x) for x in as_list(best.get("name"))]
            spacegroups = [str(x) for x in as_list(best.get("spacegroup"))]
            spacegroup_numbers = as_list(best.get("spacegroup_number"))
            cif_paths = [Path(str(x)) for x in as_list(best.get("full_path"))]
            weights = [float(x) for x in as_list(best.get("wt"))]
            lengths = {len(ids), len(providers), len(formulas), len(weights)}
            if len(lengths) != 1 or not ids:
                raise RuntimeError(
                    "XERUS best-row field length mismatch: "
                    f"ids={len(ids)}, providers={len(providers)}, formulas={len(formulas)}, "
                    f"weights={len(weights)}"
                )
            positive = [max(0.0, value) for value in weights]
            total = sum(positive)
            if total <= 0:
                raise RuntimeError("XERUS returned no positive phase weight")
            weights = [value / total for value in positive]
            elapsed = time.perf_counter() - started
            selected_root = result_root / "selected_cifs" / sample.sample_id
            selected_root.mkdir(parents=True, exist_ok=True)
            for rank, (db_id, provider, formula, weight) in enumerate(
                zip(ids, providers, formulas, weights, strict=True), start=1
            ):
                source = cif_paths[rank - 1] if rank <= len(cif_paths) else None
                copied = ""
                if source is not None and source.exists():
                    target = selected_root / f"rank{rank}_{provider}_{db_id}.cif"
                    shutil.copy2(source, target)
                    copied = str(target.relative_to(ROOT))
                predictions.append(
                    {
                        "sample_id": sample.sample_id,
                        "method": METHOD_NAME,
                        "solution_rank": 1,
                        "phase_rank": rank,
                        "predicted_formula": formula,
                        "predicted_space_group_symbol": (
                            spacegroups[rank - 1] if rank <= len(spacegroups) else ""
                        ),
                        "predicted_space_group_number": (
                            spacegroup_numbers[rank - 1]
                            if rank <= len(spacegroup_numbers)
                            else ""
                        ),
                        "predicted_database": provider,
                        "predicted_database_id": db_id,
                        "predicted_weight_fraction": weight,
                        "confidence_or_score": float(best.get("rwp")),
                        "runtime_seconds": elapsed,
                        "status_or_note": "ok; score_is_Rwp_percent",
                        "predicted_cif_path": copied,
                        "predicted_cif_sha256": (
                            sha256(ROOT / copied) if copied else ""
                        ),
                    }
                )
            records.append(
                {
                    "sample_id": sample.sample_id,
                    "attempt": attempt,
                    "status": "ok",
                    "runtime_seconds": elapsed,
                    "sample_elements": elements,
                    "source_pattern": str(source_pattern.relative_to(ROOT)),
                    "source_pattern_sha256": source_pattern_sha256,
                    "xerus_input": str(xerus_pattern.relative_to(ROOT)),
                    "xerus_input_sha256": sha256(xerus_pattern),
                    "xerus_input_transform": "numeric parse; remove comment/header lines only",
                    "candidate_database": "XERUS native MP/COD/OQMD/ODBX cache; AFLOW ignored",
                    "candidate_count_after_xerus_filter": int(len(xray.cif_info)),
                    "candidate_count_before_simulation": int(len(candidate_snapshot)),
                    "candidate_manifest": str(
                        (
                            candidate_manifest
                        ).relative_to(ROOT)
                    ),
                    "max_phases": 3,
                    "phase_count_prior": "global upper bound only; per-sample truth hidden",
                    "predicted_phase_count": len(ids),
                    "best_rwp_percent": float(best.get("rwp")),
                }
            )
            print(
                f"{sample.sample_id}: {len(xray.cif_info)} candidates -> {len(ids)} phases, "
                f"Rwp={float(best.get('rwp')):.3f}%, {elapsed:.1f} s",
                flush=True,
            )
        except Exception as error:
            elapsed = time.perf_counter() - started
            predictions.append(
                {
                    "sample_id": sample.sample_id,
                    "method": METHOD_NAME,
                    "runtime_seconds": elapsed,
                    "status_or_note": f"error: {type(error).__name__}: {error}",
                }
            )
            records.append(
                {
                    "sample_id": sample.sample_id,
                    "attempt": attempt,
                    "status": "error",
                    "runtime_seconds": elapsed,
                    "sample_elements": elements,
                    "source_pattern": str(source_pattern.relative_to(ROOT)),
                    "source_pattern_sha256": source_pattern_sha256,
                    "error_type": type(error).__name__,
                    "error": str(error),
                    "traceback": traceback.format_exc(),
                }
            )
            print(f"{sample.sample_id}: ERROR after {elapsed:.1f} s: {error}", flush=True)
        save_state(result_root, predictions, records)

    environment = {
        "python": sys.version,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "xerus_version": getattr(Xerus, "__version__", "unknown"),
        "gsasii_root": (
            repository_path(os.environ["GSASII_ROOT"])
            if os.environ.get("GSASII_ROOT")
            else None
        ),
        "instrument_profile": str(PROFILE.relative_to(ROOT)),
        "xerus_configured_profile": repository_path(configured_profile),
        "n_runs": 3,
        "n_jobs": args.n_jobs,
        "ignore_provider": ["AFLOW"],
        "maxsys": "number of disclosed sample elements",
        "max_oxy": "number of disclosed sample elements",
        "private_truth_used": False,
        "prepare_candidates_only": args.prepare_candidates_only,
    }
    (result_root / "environment.json").write_text(
        json.dumps(environment, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
