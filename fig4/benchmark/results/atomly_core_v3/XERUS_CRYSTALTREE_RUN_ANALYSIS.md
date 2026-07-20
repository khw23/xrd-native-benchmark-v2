# XERUS and CrystalShift/CrystalTree diagnostic run analysis

## Scope

This report analyzes only blind inputs, candidate manifests, runtime records, and
method outputs. It does not use private truth and does not estimate accuracy.

## CrystalShift conversion loss

The frozen COD front-end contains 6,622 candidate records across 84 element-system
caches. These records represent 2,429 distinct COD IDs; repeated IDs occur when a
structure is compatible with more than one disclosed element system. Conversion to
CrystalShift input succeeded for 5,591 records (1,853 distinct COD IDs) and failed
for 1,031 records (576 distinct COD IDs), giving an 84.4% record-level conversion
rate.

The loss is not uniform:

- 64 of 84 element systems and 77 of 100 samples lose at least one candidate.
- 55 samples lose at least 5% of their candidate records.
- 26 samples lose at least 10%, 10 lose at least 20%, and 2 lose at least 30%.
- The largest losses are XRDV3_0099 at 49.1%, XRDV3_0032 at 33.0%, and
  XRDV3_0003/XRDV3_0058 at 28.9%.
- Of the 1,031 failure records, 877 are invalid or unsupported atom-label errors,
  129 are other `ValueError` parse failures, 20 are symmetry-determination
  failures, 3 are converter `NameError` failures, and 2 lack a required CIF field.

This can affect the final predictions because CrystalTree cannot select a structure
that failed conversion. The effect is a potential loss of candidate recall and is
most material for the high-loss systems. The failures are systematic CIF/parser
compatibility failures rather than random sampling, so the surviving library may be
biased toward CIFs that are easier for the converter to parse.

The current 100-sample output is reproducible for the reduced, converted library,
but it is a diagnostic artifact rather than the definitive benchmark result. It must
not be presented as a fair evaluation against the complete frozen COD candidate
front-end. Without private truth or a deterministic repaired conversion rerun, the
direction and magnitude of any accuracy change cannot be determined. In particular,
conversion loss alone does not prove that any individual prediction is wrong.

For a future definitive comparison, repair the conversion adapter using a uniform
CIF normalization rule, validate structure/cell preservation, freeze the repaired
conversion manifest, and rerun all samples. Do not repair or exclude candidates in
response to prediction quality.

## XERUS server scaling

The local smoke used an ARM64 host with 20 logical CPUs, 121 GiB RAM, and
`--n-jobs 4`. It took 1,849 seconds wall time, 515 seconds user CPU, and 42 seconds
system CPU, with 0.75 GiB peak RSS. The native workflow performed 25 COD/OQMD/ODBX
subsystem query cycles, logged nine OQMD timeout retries, then simulated 1,297
patterns and refined candidate combinations.

XERUS uses multiprocessing for pattern simulation and combination refinement, so a
faster x86-64 server and a larger `n_jobs` may accelerate those compute stages.
However, database requests, retry backoff, CIF download, MongoDB operations, and
serial orchestration do not scale with core count. CPU time from one multiprocessing
run cannot be subtracted from wall time to form a valid speedup bound, so this smoke
does not support a numerical acceleration estimate.

Expected consequences:

- Single-sample and full-dataset speedup remain unknown until a controlled pilot is
  run on the target machine with the same samples and provider conditions.
- Outer sample concurrency may improve throughput, but each process must write to a
  separate result directory because the current runner state files are not safe for
  concurrent writers. Provider rate limits must be monitored before increasing it.
- Stable outbound networking is required. CPU, memory, and disk requirements for a
  full run should be projected from the three-sample pilot rather than asserted from
  this one sample. More GPU does not directly accelerate this workflow.
- Provider rate limits and timeouts can make aggressive concurrency slower or less
  reliable. Failed attempts must remain recorded and resumed rather than silently
  retried outside the run manifest.

The one-sample result is insufficient for a precise scaling curve. Before committing
to the full 100 samples, benchmark three disclosed element systems with low, median,
and high native candidate counts on the target server and record query, simulation,
and refinement stage times separately.

## Published artifact scope

The repository includes normalized predictions, selected predicted CIFs, candidate
IDs, audit summaries, failure manifests, conversion-impact tables, environment
versions, and resumability hashes. It excludes method environments, MongoDB data,
downloaded candidate caches, XERUS work products, API keys, and verbose transient
logs.
