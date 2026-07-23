# DGX CrystalTree and XERUS full-run report

## Scope and blind protocol

This run used only the public blind XRD patterns, `sample_elements`, disclosed
instrument metadata, and public database candidates. Every sample retained the
same global upper bound of three phases. No private truth, per-sample phase count,
accuracy calculation, or manual candidate pruning was used. The Dara 100-sample
full run was not started. The authorized CrystalTree and XERUS 100-sample runs
were completed with the fixed configurations described below.

The branch and existing result roots were reused. The task document referenced
`AGENTS.md` and `fig4/benchmark/benchmark_plan.md`, but neither file exists in the
current branch; the complete `REMOTE_RUN_GUIDE_V3.md`, `DGX_NEXT_TASK.md`, and
previous gate report were read before execution.

## CrystalShift conversion gate: passed previously

The repaired adapter converted all 6,622 frozen COD candidate records across 84
element-system caches. There were no final failures, structure-validation
failures, or substantive structure changes. All 906 failed conversion attempts
remain in the attempt manifest: 888 direct-converter attempts and 18
symmetry-normalized attempts. The final strategies were 5,734 direct, 870
symmetry normalized, and 18 P1 normalized.

The audit retains four front-end element-key mismatches for two COD IDs: COD
2102787 contains Nb in three system caches and COD 4505652 contains Ge in one.
Their frozen hashes match the manifests and both were retained without manual
modification. Raw XRD SHA-256 manifests before and after conversion remain
byte-identical.

## Superseded 128-iteration diagnostic

The earlier exact two-phase fixture and three blind smokes used `maxiter=128`,
which is the `OptimizationSettings` software default rather than the setting in
the closest upstream paper reproduction. Those results remain in Git history and
the append-only run records for audit, but are superseded diagnostics. They must
not be treated as parameter validation or current predictions.

| Sample | COD candidates | Predicted phases at 128 | Search seconds |
|---|---:|---:|---:|
| XRDV3_0046 | 12 | 1 | 37.9 |
| XRDV3_0054 | 46 | 3 | 50.4 |
| XRDV3_0100 | 216 | 3 | 294.0 |

The earlier report's claim that the README-derived priors were independently
validated was too strong. Its exact constructed fixture checked API and numerical
compatibility only.

## 512 compatibility gate: passed

The same constructed two-phase fixture was rerun with `maxiter=512` and the
production runner's README-derived priors. The 15 public candidates returned 91
finite-residual hypotheses, included the constructed exact two-phase hypothesis,
and returned no hypothesis above three phases. Search time was 19.3 seconds;
cold-start wall time was 58.7 seconds and peak RSS was 1,971 MiB.

This is explicitly an API/numerical compatibility result. It is not an accuracy
measurement or scientific parameter-selection result.

## Public paper-fixture parameter audit: passed

The selection rule was fixed in code before execution: take the first four
source-order rows with exactly one, then two, then three nonzero activations from
the upstream public Al-Fe-Li-O `sol.csv`. This selected rows 1, 11, 21, 22; 2, 3,
4, 5; and 31, 33, 34, 35. Public row 6 was used only to remove first-call JIT
compilation from timings and was excluded from all metrics.

The audited upstream paper configuration was LM, Simple rather than EM, least
squares, `std_noise=0.01`, `mean_theta=[1.0, 0.5, 0.5]`,
`std_theta=[0.1, 0.05, 0.1]`, Gaussian peak profile with initial width 0.1,
regularization on, no amorphous phase, and background off. The paper script's
unseeded random positive-noise augmentation was omitted so both iteration settings
received identical public spectra.

| maxiter | Success | Strict combination top-1 | Phase precision | Phase recall | Mean residual | Timed search |
|---:|---:|---:|---:|---:|---:|---:|
| 128 | 12/12 | 7/12 (0.5833) | 0.6667 | 0.7500 | 0.398629 | 51.5 s |
| 512 | 12/12 | 7/12 (0.5833) | 0.7308 | 0.7917 | 0.348128 | 52.9 s |

The pre-registered gate required zero failures in both settings and no reduction
in strict top-1 accuracy at 512. It passed. Precision, recall, residual, and
runtime were reported but did not change the gate. This small public sensitivity
audit supports correcting `maxiter`; it does not scientifically validate the
README-derived production priors or estimate private benchmark accuracy.

## CrystalShift + CrystalTree 100-sample run: passed

The authorized run reused the existing `crystaltree_cod_frontend_v2` result root
and a single writer with `--resume`. All 100 samples have a latest `ok` record
with the identical `simple_fixed_sigma_0p1_maxiter512` configuration,
`maxiter=512`, and the global upper bound of three phases. The three earlier
512-iteration smokes were skipped rather than recomputed. Old 128-iteration
records remain only as superseded audit history.

The frozen COD front-end supplied 8,792 candidates in total: 5 to 629 per
sample, with a median of 46. The current outputs contain 196 predicted phases
across all 100 samples and exactly three stored hypotheses per sample. Predicted
phase counts were one for 24 samples, two for 56, and three for 20. These are
predictions, not comparisons with hidden phase counts.

Summed per-sample search time was 11,987.3 seconds. The resumed full-run process
took 3:13:15 wall time, used 32,062.5 user CPU seconds, and peaked at 3,072,476
KiB RSS. Per-sample search time ranged from 0.2 to 1,132.0 seconds, with a median
of 25.8 seconds. There were no current calculation failures. A post-run invocation
with the identical `--resume --maxiter 512` arguments skipped all 100 samples,
exited successfully, and left the 103-record append-only audit file unchanged.

Current prediction keys and top-hypothesis keys are unique. All 196 referenced
CIFs exist and all 196 regenerated SHA-256 entries verify. Raw XRD SHA-256
manifests before and after preparation are byte-identical. Current predictions,
top-three hypotheses, database IDs, selected CIFs, checksums, uncalibrated model
probabilities, and append-only run records are under
`crystaltree_cod_frontend_v2`. The method name remains
`CrystalShift + CrystalTree with COD front-end`. CrystalShift activation remains
an internal model quantity and is not reported as mass or mole fraction.

## XERUS frozen-cache XRDV3_0046 pilot: passed

The earlier live OQMD candidate attempts remain part of the failure audit. The
OQMD health endpoint initially recovered to HTTP 200, but its minimal response
took 21.0 seconds. Those attempts exposed two local integration problems before
a valid freeze could be produced:

- Adding the GSAS-II package directory itself to `PYTHONPATH` broke relative
  imports. The corrected environment uses the installed package normally and
  records `GSASII_ROOT` separately.
- XERUS launches its CIF validator through a hard-coded `python tcif.py` command.
  The runner now prepends its own isolated interpreter directory to `PATH`.
  The prior attempt is retained as a 109.4-second `FileNotFoundError`.

The failed validator attempt also showed that XERUS provider download directories
are non-transactional: retrying can repeatedly prefix old filenames and corrupt a
database ID. Exactly one malformed Mongo document (`provider=COD`, `id=Ag`) was
removed, changing the Ag cache from 72 to 71 documents; the other 71 had normal
provider/ID fields. The runner now removes only sample-prefixed incomplete
provider directories before a candidate-freeze retry. This cleanup does not alter
provider selection or candidate filtering.

On the clean live retry, XERUS populated native cache entries for Ag, Br, Cl,
Ag-Br, and Ag-Cl. OQMD then timed out for Br-Cl and ended with repeated HTTP 502
responses after 286.8 seconds. The updated task therefore supplied a tracked,
frozen raw OQMD OPTIMADE cache for the seven XRDV3_0046 element systems. Its top
manifest SHA-256 is
`d0a3ac2c04547bd7f49ac6fff75a2a4320148c7b3879b114b9b3ffe1c23c0f5e`;
all 150 unique raw entries and their page/system hashes verified before use.

The pilot used the required isolated `xerus-mongo-oqmd-pilot` MongoDB container
on host port 27018. The candidate-only attempt completed in 95.3 seconds and
wrote a 226-row unique `(provider, id)` snapshot: 149 OQMD, 61 COD, 12 MP, and
4 ODBX candidates. All snapshot CIF paths exist. The candidate log records all
seven frozen OQMD cache loads and contains no live `oqmd.org` request or
connection-pool error marker.

The formal XRDV3_0046 run reused that exact cache and candidate set. It passed 63
candidates through XERUS simulation/filtering and completed in 27.4 seconds with
Rwp 7.0242%. The returned prediction contains two phases:

| Rank | Provider ID | Formula | Space group | Reported weight | CIF SHA-256 |
|---:|---|---|---|---:|---|
| 1 | OQMD 5492459 | AgCl | Fm-3m | 0.93344 | `2fddfb55180159f1611dd2b7bf8b8bff4819acc51d45af55fefd36a974a8edc8` |
| 2 | MP mp-570301 | AgBr | P2_1/m | 0.06656 | `a15eefa72d092f9b74731733f3667a2ec437da53062e743d5b4557003aec32b8` |

Both selected CIF paths exist, their hashes verify, and the reported weights sum
to one. This is a blind prediction, not an accuracy result. The formal log has no
provider-network query marker. The provider failures, import failure,
missing-interpreter failure, interrupted duplicate diagnostic, cache repair, and
health check remain classified in the result logs and append-only records. The
later full run supersedes this pilot as the current prediction set.

## XERUS 100-sample full run: passed

The full run used the tracked archive with SHA-256
`77797b9d064fe8812d57ccf67f5cd17a3541c079b8d4809c71e4215b986e4fb8`.
After extraction, all 470 system manifests, 478 OPTIMADE pages, and 5,315
globally unique OQMD IDs passed manifest/page hashes, provider checks, element
checks, and uniqueness checks. The blind package was reverified as 100 samples,
84 disclosed element systems, and no CIF, truth, phase-pool, or Atomly-COD map.

Candidate preparation completed for all 100 samples with the fixed native
MP/COD/OQMD/ODBX flow and AFLOW ignored. It took 7,531.3 summed sample seconds.
The 100 candidate manifests contain 46,947 unique within-sample `(provider, id)`
rows: 23,663 COD, 18,440 OQMD, 4,612 MP, and 232 ODBX. Per-sample candidate
counts range from 95 to 2,330 with a median of 356.5. Every manifest path existed
at validation time. All full-run logs use `frozen_local_optimade_cache` for OQMD
and contain no `oqmd.org` request or OQMD connection-pool error.

The first formal pass completed 79 samples and retained 21 sample-level errors:
20 GSAS-II `G2Exception` failures where one candidate combination had no
reflections in the measured range, plus one XERUS auxiliary filtered-plot
`AttributeError`. The first detached process stopped at the required 100/100
gate after 4:00:12 wall time. These failures remain in `run_records.json`,
`runtime_failures.csv`, and the original appended logs.

The recovery patch assigns XERUS's existing invalid-fit sentinel
`Rwp=999999` only to the exact failing no-reflection combination; unrelated
exceptions still propagate. It also skips only an empty filtered diagnostic
plot, which is not consumed because the run uses `combine_filter=False`. The
candidate-history resume gate was corrected and stage logs changed to append
mode. No candidate was manually removed, and `n_runs=3`, `n_jobs=4`, the
instrument profile, solver settings, and global three-phase upper bound were
unchanged. Repair smokes for XRDV3_0006 and XRDV3_0077 passed before the
remaining failures were retried. The detached recovery took 16:24 wall time.

The final latest-state gate passed with 100/100 `status=ok`. Current outputs
contain 286 phase rows: two samples returned one phase, ten returned two, and 88
returned three. These are predictions, not hidden phase-count comparisons.
Summed current formal runtime is 7,018.0 seconds; per-sample runtime ranges from
7.9 to 376.8 seconds with a median of 44.0 seconds. All current prediction keys
are unique, per-sample reported weights sum to one, all 286 selected CIF paths
and embedded SHA-256 values verify, and the regenerated 286-entry selected-CIF
checksum manifest passes. The append-only audit contains 228 records: 100
candidate-ready records, 100 successful records, and 28 retained historical
errors including the earlier pilot failures.

## Decision

The 512 compatibility gate, public paper-fixture sensitivity gate, and
CrystalTree 100-sample blind run passed. The frozen-cache XERUS candidate stage
and final 100-sample run also passed after the recorded recovery. The task's
latest-state decision gate is satisfied. No private benchmark accuracy was
computed or inferred.
