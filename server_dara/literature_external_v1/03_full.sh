#!/bin/bash
set -euo pipefail

python fig4/benchmark/prototypes/run_dara_native_v3.py \
  --blind-root fig4/benchmark/datasets/literature_external_v1/blind_package \
  --cod-root fig4/benchmark/method_inputs/cod_native_literature_external_v1 \
  --result-root fig4/benchmark/results/literature_external_v1/dara_cod_native \
  --instrument-profile-map fig4/benchmark/datasets/literature_external_v1/instrument_metadata/dara_profile_map.csv \
  --num-cpus "${RAY_CPUS:-8}" --bgmn-threads "${BGMN_THREADS:-8}" \
  --resume --retry-failures
