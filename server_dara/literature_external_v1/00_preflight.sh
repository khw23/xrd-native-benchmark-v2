#!/bin/bash
set -euo pipefail

glibc_prefix="${GLIBC229_PREFIX:-$HOME/opt/glibc-2.29}"
loader="$glibc_prefix/lib/ld-linux-x86-64.so.2"
test -x "$loader"

dara_root="$(python -c 'from pathlib import Path; import dara; print(Path(dara.__file__).resolve().parent)')"
bgmn_root="$dara_root/bgmn/BGMNwin"
teil="$bgmn_root/teil"
test -x "$teil"

if readelf -d "$loader" | grep -Eq '(RPATH|RUNPATH)'; then
  echo "ERROR: user-space glibc loader contains RPATH/RUNPATH" >&2
  exit 1
fi

readelf -l "$teil" | grep -F "$loader" >/dev/null
readelf -d "$teil" | grep -E '(RPATH|RUNPATH)' | grep -F "$glibc_prefix/lib" >/dev/null
"$loader" --verify "$teil"
link_map="$("$loader" --list "$teil")"
if grep -q 'not found' <<<"$link_map"; then
  echo "$link_map" >&2
  exit 1
fi
grep -F "$glibc_prefix/lib/libm.so.6" <<<"$link_map" >/dev/null
grep -F "$glibc_prefix/lib/libc.so.6" <<<"$link_map" >/dev/null

python - <<'PY'
import dara
import numpy
import pymatgen
import ray
from dara.eflech_worker import EflechWorker

worker = EflechWorker()
assert worker.eflech_path.is_file()
assert worker.teil_path.is_file()
print("DARA_LITV1_PREFLIGHT_PASS")
print(worker.bgmn_folder)
PY
