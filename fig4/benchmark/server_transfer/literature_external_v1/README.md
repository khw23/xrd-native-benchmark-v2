# Literature-External-v1 offline database snapshots

These archives are public-input-derived runtime caches. They contain no benchmark
answers or Atomly credentials.

| archive | required scope | use |
|---|---:|---|
| `cod_sparse_literature_external_v1_20260722.tar.gz` | 2,122 checksummed COD CIFs | Dara and CrystalShift/CrystalTree candidate preparation |
| `oqmd_optimade_cache_literature_external_v1_20260722.tar.gz` | 46 complete OQMD OPTIMADE full-element systems | frozen offline XERUS-native queries |

Verify each archive with its adjacent `.sha256` file before unpacking. Expanded
cache directories are runtime artifacts and must not be committed. The public
scope and exact selection rules are recorded under
`fig4/benchmark/database_coverage/literature_external_v1/`.

The frozen OQMD archive was produced by GitHub Actions run `29932078483` from
commit `8d23bb0`, then independently re-downloaded and checked locally. Its
archive SHA256 is
`110318be5630be7eeefb6ef4a7db89d41686ea49b408078f72ebd186d17135bc`;
the extracted cache manifest SHA256 is
`62de256aa65f869d8614bfa099665d0b3a63f73ae8244ab0ee8a98f932eaf738`.
`validate_literature_external_runtime_v1.py` reports all 46 required systems
complete.
