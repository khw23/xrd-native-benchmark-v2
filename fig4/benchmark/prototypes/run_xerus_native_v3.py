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
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--retry-failures", action="store_true")
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


def save_state(predictions: list[dict], records: list[dict]) -> None:
    pd.DataFrame(predictions).to_csv(RESULT_ROOT / "predictions.csv", index=False)
    (RESULT_ROOT / "run_records.json").write_text(
        json.dumps(records, indent=2) + "\n", encoding="utf-8"
    )


def main() -> None:
    args = parse_args()
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

    RESULT_ROOT.mkdir(parents=True, exist_ok=True)
    prediction_path = RESULT_ROOT / "predictions.csv"
    record_path = RESULT_ROOT / "run_records.json"
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
        records = [row for row in records if row.get("sample_id") != sample.sample_id]
        work = RESULT_ROOT / "work" / sample.sample_id
        work.mkdir(parents=True, exist_ok=True)
        elements = str(sample.sample_elements).split(";")
        started = time.perf_counter()
        try:
            xray = XRay(
                name=sample.sample_id,
                working_folder=str(work),
                elements=elements,
                exp_data_file=str(BLIND_ROOT / "patterns" / sample.pattern_filename),
                data_fmt="xy",
                maxsys=len(elements),
                max_oxy=len(elements),
                remove_background=True,
                poly_degree=8,
                standarize_int=True,
                use_preprocessed=True,
            )
            xray.instr_params = str(PROFILE)
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
            candidate_snapshot_root = RESULT_ROOT / "candidate_manifests"
            candidate_snapshot_root.mkdir(parents=True, exist_ok=True)
            candidate_snapshot = (
                xray.cif_all.copy()
                if isinstance(xray.cif_all, pd.DataFrame)
                else xray.cif_info.copy()
            )
            candidate_snapshot.to_csv(
                candidate_snapshot_root / f"{sample.sample_id}.csv", index=False
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
            selected_root = RESULT_ROOT / "selected_cifs" / sample.sample_id
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
                    "status": "ok",
                    "runtime_seconds": elapsed,
                    "sample_elements": elements,
                    "candidate_database": "XERUS native MP/COD/OQMD/ODBX cache; AFLOW ignored",
                    "candidate_count_after_xerus_filter": int(len(xray.cif_info)),
                    "candidate_count_before_simulation": int(len(candidate_snapshot)),
                    "candidate_manifest": str(
                        (
                            candidate_snapshot_root / f"{sample.sample_id}.csv"
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
                    "status": "error",
                    "runtime_seconds": elapsed,
                    "sample_elements": elements,
                    "error_type": type(error).__name__,
                    "error": str(error),
                    "traceback": traceback.format_exc(),
                }
            )
            print(f"{sample.sample_id}: ERROR after {elapsed:.1f} s: {error}", flush=True)
        save_state(predictions, records)

    environment = {
        "python": sys.version,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "xerus_version": getattr(Xerus, "__version__", "unknown"),
        "gsasii_root": os.environ.get("GSASII_ROOT"),
        "instrument_profile": str(PROFILE.relative_to(ROOT)),
        "xerus_configured_profile": str(configured_profile),
        "n_runs": 3,
        "ignore_provider": ["AFLOW"],
        "maxsys": "number of disclosed sample elements",
        "max_oxy": "number of disclosed sample elements",
        "private_truth_used": False,
    }
    (RESULT_ROOT / "environment.json").write_text(
        json.dumps(environment, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
