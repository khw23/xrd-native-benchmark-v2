# DGX conversion repair and three-tier pilot gate

## Scope and blind protocol

This run used only the public blind XRD patterns, `sample_elements`, the disclosed
instrument profile, and public database candidates. The global upper bound was
three phases for every sample. No private truth, per-sample phase count, accuracy,
or manual candidate pruning was used. Dara and the 100-sample full runs were not
started.

## CrystalShift conversion gate: passed

The repaired adapter converted all 6,622 frozen COD candidate records across 84
element-system caches. There were no final failures, structure-validation
failures, or substantive structure changes. All 906 failed attempts remain in the
attempt manifest: 888 direct-converter attempts and 18 symmetry-normalized
attempts. The final strategies were 5,734 direct, 870 symmetry normalized, and 18
P1 normalized.

The audit also retains four front-end element-key mismatches for two COD IDs:
COD 2102787 contains Nb in three system caches and COD 4505652 contains Ge in one.
Their frozen hashes match the manifests; both were retained without modification.
Raw XRD SHA-256 manifests before and after conversion are byte-identical.

The final complete conversion took 555.4 seconds wall time with 325,532 KiB peak
RSS. The normalization rules and detailed checks are in
`CRYSTALSHIFT_CIF_NORMALIZATION_V2.md` and the v2 input-preparation directory.

## Independent parameter gate: passed

The exact production settings were tested on a normalized sum of phases 0 and 1
from CrystalTree's installed public `data/sticks.csv` fixture, SHA-256
`355bdbf3b9db9d43441852c9833e185935ebef9acb15f246c26ce301d6ab07af`.
The fixture has 15 candidates. Search returned 91 finite-residual hypotheses,
included the constructed two-phase hypothesis, and returned no hypothesis above
three phases.

Adopted settings:

- `std_noise=0.1`, `mean_theta=[1.0, 0.5, 0.2]`, and
  `std_theta=[0.05, 2.0, 1.0]` from the upstream CrystalShift README for a
  maximum-normalized spectrum.
- `maxiter=128` from the upstream `OptimizationSettings` constructor default.
- Candidate expansion count 3 from the CrystalShift tree-search README and
  CrystalTree default settings.
- Tree depth 3 from the benchmark-wide maximum-three-phase rule.
- No amorphous phase or fitted background; background length remains the upstream
  value 5.0 but is inactive.

The search itself took 19.1 seconds. Total cold-start wall time was 56.1 seconds
and peak RSS was 2,126,892 KiB.

## CrystalShift + CrystalTree smokes: passed

| Sample | COD candidates | Predicted phases | Search seconds | Status |
|---|---:|---:|---:|---|
| XRDV3_0046 | 12 | 1 | 37.9 | ok |
| XRDV3_0054 | 46 | 3 | 50.4 | ok |
| XRDV3_0100 | 216 | 3 | 294.0 | ok |

The method name is `CrystalShift + CrystalTree with COD front-end`. Predictions,
top-three hypotheses, COD IDs, source CIF copies, checksums, model probabilities,
and run records are saved under `crystaltree_cod_frontend_v2`. CrystalShift
activation is reported only in notes and is not treated as mass or mole fraction.
The resume run skipped XRDV3_0046 and did not duplicate its output.

## XERUS three-tier pilot: blocked at provider gate

XERUS was frozen at `53ed38b6d8437cf61abee270672bd33de75f15a3` and
GSAS-II at `14dd93032174ba9b751539f3be64de69fcb33ab8`, with the two repository
patches, the disclosed instrument profile, MongoDB, and `n_jobs=4`. The
architecture-compatible GSAS-II binary modules loaded successfully after one
separately logged path-configuration failure.

OQMD's public OPTIMADE endpoint returned HTTP 502 during every scientific attempt.
The retry adapter exhausted three HTTP retries within each attempt. XRDV3_0046 was
attempted three times (19.0, 19.2, and 18.0 seconds); XRDV3_0054 and XRDV3_0100
were attempted once (26.8 and 13.6 seconds). A direct endpoint health check also
returned 502. MP and COD requests succeeded before the OQMD failure, but XERUS
aborted before candidate simulation and refinement. Therefore candidate counts,
final IDs/CIFs, Rwp, and weight fractions are unavailable rather than silently
omitted.

OQMD was not added to `ignore_provider`, because doing so would change the frozen
native candidate protocol. All five `RetryError` records and the import failure log
are retained under `xerus_native_pilot_v2`; the API key, downloaded cache,
MongoDB, work directories, and method environment are excluded from the commit.

## Decision

The repaired CrystalShift conversion, independent parameter gate, and three
CrystalTree smokes passed. CrystalTree is technically eligible for a separately
confirmed full run, but no full run was started. XERUS did not pass the provider
gate and must rerun the same three pilots with `--resume --retry-failures` after
OQMD recovers. No accuracy was computed or inferred.
