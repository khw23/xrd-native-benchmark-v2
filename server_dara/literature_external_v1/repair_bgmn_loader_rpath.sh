#!/usr/bin/env bash
set -euo pipefail

glibc_prefix="${GLIBC229_PREFIX:-$HOME/opt/glibc-2.29}"
loader="$glibc_prefix/lib/ld-linux-x86-64.so.2"
test -x "$loader"

set +u
eval "$(conda shell.bash hook)"
conda activate "${GLIBC_BUILD_ENV:-xrd-glibc229-build}"
set -u
patchelf_bin="$(command -v patchelf)"
"$patchelf_bin" --remove-rpath "$loader"

if readelf -d "$loader" | grep -Eq '(RPATH|RUNPATH)'; then
  echo "ERROR: loader RPATH/RUNPATH removal failed" >&2
  exit 1
fi

set +u
eval "$(conda shell.bash hook)"
conda activate "${CONDA_ENV_NAME:-xrd-dara-v3}"
set -u
dara_root="$(python -c 'from pathlib import Path; import dara; print(Path(dara.__file__).resolve().parent)')"
bgmn_root="$dara_root/bgmn/BGMNwin"
test -d "$bgmn_root"

patched=0
for executable in "$bgmn_root"/*; do
  if file "$executable" | grep -q 'ELF 64-bit'; then
    chmod +x "$executable"
    "$patchelf_bin" --remove-rpath "$executable"
    "$patchelf_bin" --set-interpreter "$loader" "$executable"
    "$patchelf_bin" --set-rpath "$glibc_prefix/lib" "$executable"
    patched=$((patched + 1))
  fi
done
test "$patched" -ge 4

"$loader" --verify "$bgmn_root/teil"
link_map="$("$loader" --list "$bgmn_root/teil")"
if grep -q 'not found' <<<"$link_map"; then
  echo "$link_map" >&2
  exit 1
fi
grep -F "$glibc_prefix/lib/libm.so.6" <<<"$link_map" >/dev/null
grep -F "$glibc_prefix/lib/libc.so.6" <<<"$link_map" >/dev/null

echo "BGMN_LOADER_RPATH_REPAIR_SUCCESS"
