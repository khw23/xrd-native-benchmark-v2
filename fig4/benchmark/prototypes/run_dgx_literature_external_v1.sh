#!/bin/bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/../../.." && pwd)
cd "$ROOT"

LOG_ROOT=fig4/benchmark/results/literature_external_v1/logs/dgx
mkdir -p "$LOG_ROOT"
rm -f "$LOG_ROOT/DGX_LITERATURE_EXTERNAL_COMPLETED" \
  "$LOG_ROOT/DGX_LITERATURE_EXTERNAL_FAILED"
trap 'status=$?; if [ "$status" -ne 0 ]; then printf "%s\n" "$status" > "$LOG_ROOT/DGX_LITERATURE_EXTERNAL_FAILED"; fi' EXIT

python3 fig4/benchmark/prototypes/validate_literature_external_runtime_v1.py \
  --cod-root fig4/benchmark/method_inputs/cod_sparse_literature_external_v1 \
  --oqmd-root fig4/benchmark/method_inputs/oqmd_optimade_cache_literature_external_v1

cod-env/bin/python fig4/benchmark/prototypes/prepare_cod_candidate_sets_v3.py \
  --blind-root fig4/benchmark/datasets/literature_external_v1/blind_package \
  --cod-root fig4/benchmark/method_inputs/cod_sparse_literature_external_v1 \
  --output-root fig4/benchmark/method_inputs/cod_native_literature_external_v1 \
  --resume

crystalshift-python/bin/python \
  fig4/benchmark/prototypes/prepare_crystalshift_cod_v3.py \
  --blind-root fig4/benchmark/datasets/literature_external_v1/blind_package \
  --cod-root fig4/benchmark/method_inputs/cod_native_literature_external_v1 \
  --converter fig4/benchmark/third_party/CrystalShift.jl/src/cif_to_input_file.py \
  --output-root fig4/benchmark/method_inputs/crystalshift_cod_literature_external_v1 \
  --snapshot-root fig4/benchmark/results/literature_external_v1/crystaltree_cod_frontend/input_preparation \
  --resume \
  2>&1 | tee -a "$LOG_ROOT/crystalshift_input_preparation.log"

julia +1.12.6 --compiled-modules=no \
  --project=fig4/benchmark/method_envs/crystalshift \
  fig4/benchmark/prototypes/run_crystaltree_cod_v3.jl \
  --blind-root fig4/benchmark/datasets/literature_external_v1/blind_package \
  --input-root fig4/benchmark/method_inputs/crystalshift_cod_literature_external_v1 \
  --cod-root fig4/benchmark/method_inputs/cod_native_literature_external_v1 \
  --result-root fig4/benchmark/results/literature_external_v1/crystaltree_cod_frontend \
  --maxiter 512 --resume \
  2>&1 | tee -a "$LOG_ROOT/crystaltree_full.log"

docker start xerus-mongo-oqmd-pilot >/dev/null 2>&1 || true
docker inspect -f '{{.State.Running}}' xerus-mongo-oqmd-pilot | grep -qx true

env -u PYTHONPATH \
  GSASII_ROOT=xerus-env/lib/python3.12/site-packages \
  MPLBACKEND=Agg \
  xerus-env/bin/python fig4/benchmark/prototypes/run_xerus_native_v3.py \
  --blind-root fig4/benchmark/datasets/literature_external_v1/blind_package \
  --instrument-profile fig4/benchmark/third_party/Xerus/Xerus/inc/RigakuSi.instprm \
  --oqmd-cache-root fig4/benchmark/method_inputs/oqmd_optimade_cache_literature_external_v1 \
  --result-root fig4/benchmark/results/literature_external_v1/xerus_native_default_profile \
  --n-jobs 4 --prepare-candidates-only --resume --retry-failures \
  2>&1 | tee -a "$LOG_ROOT/xerus_candidate_preparation.log"

env -u PYTHONPATH \
  GSASII_ROOT=xerus-env/lib/python3.12/site-packages \
  MPLBACKEND=Agg \
  xerus-env/bin/python fig4/benchmark/prototypes/run_xerus_native_v3.py \
  --blind-root fig4/benchmark/datasets/literature_external_v1/blind_package \
  --instrument-profile fig4/benchmark/third_party/Xerus/Xerus/inc/RigakuSi.instprm \
  --oqmd-cache-root fig4/benchmark/method_inputs/oqmd_optimade_cache_literature_external_v1 \
  --result-root fig4/benchmark/results/literature_external_v1/xerus_native_default_profile \
  --n-jobs 4 --resume --retry-failures \
  2>&1 | tee -a "$LOG_ROOT/xerus_full.log"

touch "$LOG_ROOT/DGX_LITERATURE_EXTERNAL_COMPLETED"
trap - EXIT
