#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
args=(--resume)
if [[ -n "${COD_ROOT:-}" ]]; then
  args+=(--cod-root "$COD_ROOT")
fi
python fig4/benchmark/prototypes/prepare_cod_candidate_sets_v3.py "${args[@]}"
python fig4/benchmark/prototypes/audit_cod_candidate_sets_v3.py
