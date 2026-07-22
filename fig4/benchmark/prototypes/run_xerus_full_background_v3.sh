#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
cd "$ROOT"

CACHE_ROOT="fig4/benchmark/method_inputs/oqmd_optimade_cache_v3_full"
RESULT_ROOT="fig4/benchmark/results/atomly_core_v3/xerus_native_pilot_v2"
LOG_ROOT="$RESULT_ROOT/logs"
PYTHON="xerus-env/bin/python"
RUNNER="fig4/benchmark/prototypes/run_xerus_native_v3.py"

mkdir -p "$LOG_ROOT"
rm -f "$LOG_ROOT/XERUS_FULL_COMPLETED" "$LOG_ROOT/XERUS_FULL_FAILED"

finish() {
  status=$?
  if [ "$status" -eq 0 ]; then
    date -u +'%Y-%m-%dT%H:%M:%SZ' > "$LOG_ROOT/XERUS_FULL_COMPLETED"
  else
    printf 'exit_code=%s\n' "$status" > "$LOG_ROOT/XERUS_FULL_FAILED"
    date -u +'%Y-%m-%dT%H:%M:%SZ' >> "$LOG_ROOT/XERUS_FULL_FAILED"
  fi
}
trap finish EXIT

test -x "$PYTHON"
test -f "$RUNNER"
test -f "$CACHE_ROOT/cache_manifest.json"

python3 - "$CACHE_ROOT/cache_manifest.json" <<'PY'
import json
import sys
from pathlib import Path

manifest = json.loads(Path(sys.argv[1]).read_text())
assert manifest['complete'] is True, manifest
assert manifest['requested_system_count'] == 470, manifest
assert manifest['complete_system_count'] == 470, manifest
assert manifest['failed_system_count'] == 0, manifest
print('OQMD_FULL_CACHE_OK', manifest['complete_system_count'], flush=True)
PY

docker start xerus-mongo-oqmd-pilot >/dev/null 2>&1 || true
docker inspect -f '{{.State.Running}}' xerus-mongo-oqmd-pilot | grep -qx true

echo "XERUS_STAGE=candidate_preparation"
env -u PYTHONPATH \
  GSASII_ROOT=xerus-env/lib/python3.12/site-packages \
  MPLBACKEND=Agg \
  "$PYTHON" "$RUNNER" \
  --prepare-candidates-only --resume --retry-failures --n-jobs 4 \
  --oqmd-cache-root "$CACHE_ROOT" \
  --result-root "$RESULT_ROOT" \
  2>&1 | tee "$LOG_ROOT/full_candidate_preparation.log"

python3 - "$RESULT_ROOT/run_records.json" <<'PY'
import json
import sys
from collections import Counter
from pathlib import Path

records = json.loads(Path(sys.argv[1]).read_text())
latest = {}
for row in records:
    latest[row['sample_id']] = row
statuses = Counter(row.get('status') for row in latest.values())
assert len(latest) == 100, (len(latest), statuses)
assert set(statuses) <= {'candidates_ready', 'ok'}, statuses
print('XERUS_CANDIDATE_PREPARATION_OK', dict(statuses), flush=True)
PY

echo "XERUS_STAGE=formal_analysis"
env -u PYTHONPATH \
  GSASII_ROOT=xerus-env/lib/python3.12/site-packages \
  MPLBACKEND=Agg \
  "$PYTHON" "$RUNNER" \
  --resume --retry-failures --n-jobs 4 \
  --oqmd-cache-root "$CACHE_ROOT" \
  --result-root "$RESULT_ROOT" \
  2>&1 | tee "$LOG_ROOT/full_formal_analysis.log"

python3 - "$RESULT_ROOT/run_records.json" "$RESULT_ROOT/predictions.csv" <<'PY'
import csv
import json
import sys
from collections import Counter
from pathlib import Path

records = json.loads(Path(sys.argv[1]).read_text())
latest = {}
for row in records:
    latest[row['sample_id']] = row
statuses = Counter(row.get('status') for row in latest.values())
assert len(latest) == 100, (len(latest), statuses)
assert statuses == Counter({'ok': 100}), statuses
with Path(sys.argv[2]).open(newline='', encoding='utf-8-sig') as handle:
    prediction_samples = {row['sample_id'] for row in csv.DictReader(handle)}
assert len(prediction_samples) == 100, len(prediction_samples)
print('XERUS_FULL_OUTPUT_OK', dict(statuses), flush=True)
PY

echo "XERUS_STAGE=completed"
