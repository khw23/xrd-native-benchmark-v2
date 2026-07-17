#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
python -u fig4/benchmark/prototypes/run_dara_native_v3.py \
  --num-cpus "${RAY_CPUS:-8}" \
  --bgmn-threads "${BGMN_THREADS:-8}" \
  --resume --retry-failures
