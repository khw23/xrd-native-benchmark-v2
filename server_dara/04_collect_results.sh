#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
result_dir=fig4/benchmark/results/atomly_core_v3/dara_cod_native
test -f "$result_dir/run_records.json"
tar -czf dara_atomly_core_v3_results.tar.gz "$result_dir"
sha256sum dara_atomly_core_v3_results.tar.gz
