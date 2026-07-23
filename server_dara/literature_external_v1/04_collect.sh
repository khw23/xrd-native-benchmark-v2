#!/bin/bash
set -euo pipefail

RESULT_ROOT=fig4/benchmark/results/literature_external_v1/dara_cod_native
ARCHIVE=dara_literature_external_v1_results.tar.gz

test -f "$RESULT_ROOT/predictions.csv"
test -f "$RESULT_ROOT/run_records.json"

python - <<'PY'
import json
from pathlib import Path

path = Path("fig4/benchmark/results/literature_external_v1/dara_cod_native/run_records.json")
rows = json.loads(path.read_text())
latest = {}
for row in rows:
    latest[row["sample_id"]] = row
assert len(latest) == 78, f"expected 78 samples, found {len(latest)}"
failures = sorted(key for key, row in latest.items() if row.get("status") != "ok")
print({"samples": len(latest), "ok": len(latest) - len(failures), "failures": failures})
PY

paths=(
  "$RESULT_ROOT/predictions.csv"
  "$RESULT_ROOT/run_records.json"
  "$RESULT_ROOT/environment.json"
  "$RESULT_ROOT/selected_cifs"
)
for optional in \
  "$RESULT_ROOT/failure_history.jsonl" \
  "$RESULT_ROOT/logs" \
  "fig4/benchmark/results/literature_external_v1/logs/server" \
  "fig4/benchmark/results/literature_external_v1/SERVER_DARA_RUN_STATUS.md"; do
  if [ -e "$optional" ]; then
    paths+=("$optional")
  fi
done

tar -czf "$ARCHIVE" "${paths[@]}"

sha256sum "$ARCHIVE" > "$ARCHIVE.sha256"
echo "DARA_LITERATURE_EXTERNAL_PACKAGE_READY $ARCHIVE"
