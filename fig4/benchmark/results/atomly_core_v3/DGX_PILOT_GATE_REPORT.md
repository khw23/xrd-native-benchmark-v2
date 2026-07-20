# DGX parameter audit and three-tier pilot gate

## Scope and blind protocol

This run used only the public blind XRD patterns, `sample_elements`, disclosed
instrument metadata, and public database candidates. Every sample retained the
same global upper bound of three phases. No private truth, per-sample phase count,
accuracy calculation, or manual candidate pruning was used. Dara and both
100-sample full runs were not started.

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

## Current CrystalShift + CrystalTree smokes: passed

The three selected outputs were replaced in the existing result root with
`maxiter=512`. Their latest run records are all `ok` and all current prediction
and top-hypothesis ranks are unique. Old 128 records remain only as superseded
audit history.

| Sample | COD candidates | Current predicted phases | Search seconds | Status |
|---|---:|---:|---:|---|
| XRDV3_0046 | 12 | 1 | 40.8 | ok |
| XRDV3_0054 | 46 | 2 | 26.8 | ok |
| XRDV3_0100 | 216 | 3 | 366.1 | ok |

The complete cold-start run took 475.6 seconds and peaked at 2,685 MiB RSS.
Current predictions, top-three hypotheses, COD IDs, selected CIFs, checksums,
uncalibrated model probabilities, and append-only run records are under
`crystaltree_cod_frontend_v2`. The method name remains
`CrystalShift + CrystalTree with COD front-end`. CrystalShift activation remains
an internal model quantity and is not reported as mass or mole fraction.

## XERUS candidate freeze: blocked at provider gate

The OQMD health endpoint initially recovered to HTTP 200, but its minimal response
took 21.0 seconds. A one-sample freeze smoke then exposed two local integration
problems before a valid freeze could be produced:

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

On the clean retry, XERUS populated native cache entries for Ag, Br, Cl, Ag-Br,
and Ag-Cl. OQMD then timed out for Br-Cl and ended with repeated HTTP 502 responses.
The attempt failed after 286.8 seconds before `get_cifs` returned. Therefore:

- no sample has a latest `candidates_ready` record;
- no frozen candidate manifest is available;
- XRDV3_0054 and XRDV3_0100 were not retried;
- no formal XERUS pilot, simulation, correlation, or refinement was run;
- final IDs/CIFs, Rwp, weight fractions, and formal runtime remain unavailable.

Partial MongoDB/cache contents are local recovery state and are not committed.
The provider failure, import failure, missing-interpreter failure, interrupted
duplicate diagnostic, exact cache repair, and health check are retained and
classified in the result logs. OQMD was not ignored because that would change the
native candidate protocol.

## Decision

The 512 compatibility gate, public paper-fixture sensitivity gate, and three
current CrystalTree smokes passed. This establishes technical eligibility for a
separately authorized resume, but no 100-sample run was launched. XERUS remains
blocked because its native all-provider candidate stage could not be frozen
reliably; the task's stop condition was followed without another retry. No private
benchmark accuracy was computed or inferred.
