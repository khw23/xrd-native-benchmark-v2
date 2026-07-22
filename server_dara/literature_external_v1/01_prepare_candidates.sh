#!/bin/bash
set -euo pipefail

python fig4/benchmark/prototypes/validate_literature_external_runtime_v1.py \
  --cod-root fig4/benchmark/method_inputs/cod_sparse_literature_external_v1

python fig4/benchmark/prototypes/prepare_cod_candidate_sets_v3.py \
  --blind-root fig4/benchmark/datasets/literature_external_v1/blind_package \
  --cod-root fig4/benchmark/method_inputs/cod_sparse_literature_external_v1 \
  --output-root fig4/benchmark/method_inputs/cod_native_literature_external_v1 \
  --resume
