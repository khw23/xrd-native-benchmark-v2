# Dara Native Smoke Diagnostic

Date: 2026-07-17

## Scope

This report covers stage D of the native blind benchmark workflow. The run used
only the blind XRD pattern, `sample_elements`, instrument metadata, and the
frozen Dara COD 2024 candidate cache. The global upper bound remained three
phases. No candidate was manually removed, and no truth data or accuracy
calculation was used.

## Failure timeline

The three recorded smoke failures are not equivalent, although the initial
runner classified each under the broad `calculation_failure` label.

1. Attempt 1 failed in the benchmark adapter before Dara search because the
   adapter produced a non-unique phase alias (`NO214`). The adapter now uses
   Dara's filename normalization directly. The corrected interpretation is
   `adapter_failure`.
2. Attempt 2 failed in the benchmark adapter because it eagerly parsed every
   candidate with pymatgen and encountered a CIF with no structure. Metadata is
   now parsed lazily only for phases returned by Dara. The corrected
   interpretation is `adapter_failure`; the candidate set was not pruned.
3. Attempt 3 entered the native Dara search with all 153 frozen candidates and
   ran for 939.997 seconds. Dara 1.3.0 raised `ZeroDivisionError` while computing
   the automatic `eps2` initializer because `rwp_sum` was zero. The corrected
   interpretation is `upstream_calculation_failure` with the more specific
   condition `no_valid_single_phase_results_or_zero_rwp_sum`.

The raw records remain unchanged so the original failure history is preserved.

## What is proven

Dara's Ray refinement worker converts supported refinement exceptions to
`None`; it also returns `None` when a refinement has `RPB == 100`. The zero
denominator proves that no result contributed a nonzero Rwp to the automatic
`eps2` calculation.

One mechanically selected diagnostic candidate completed under BGMN 4.2.23
with `Rwp = 46.09%` and `RPB = 100%`, so Dara rejected that candidate under its
native rule. The current logs do not prove that all other 152 candidates were
rejected for the same reason, because Dara suppresses per-candidate reasons at
DEBUG level. They may include RPB rejection, CIF conversion errors, BGMN
errors, or other supported refinement failures.

## Environment risks

The host is ARM64, while the official BGMN 4.2.23 Linux programs downloaded by
Dara are x86-64. Direct execution failed with `Exec format error`. The official
binaries are therefore executed through an isolated QEMU user-static 8.2.2 and
x86-64 glibc runtime. A retained BGMN work directory verifies that the binary
executes and produces parseable output, but native x86-64 numerical parity has
not been established.

The initial smoke used eight Ray workers while each BGMN job retained Dara's
native `NTHREADS=8`. This can expose up to 64 emulated BGMN threads on a 20-core
ARM host. It is primarily a performance and process-stability risk. Reducing
Ray scheduling concurrency does not change the candidate set or refinement
model.

The current environment also uses Dara's broad dependency constraints rather
than its published `strict` extra. Notable installed versions are Ray 2.56.0,
pymatgen 2026.5.4, NumPy 2.4.6, and jenkspy 0.4.1. Dara 1.3.0's strict pins use
Ray 2.44.0, pymatgen 2025.5.1, NumPy 1.26.4, and jenkspy 0.4.0. The observed
division by zero is in Dara's own source, but a strict environment is preferable
before a full benchmark for reproducibility.

## Required validation before a full run

1. Build a second isolated Dara 1.3.0 environment using the published strict
   dependency versions; do not overwrite the current evidence environment.
2. Repeat the same sample with the same 153 frozen candidates and scientific
   parameters while recording a per-candidate outcome category.
3. Reduce Ray scheduling concurrency to avoid oversubscribing BGMN, then compare
   a mechanically fixed candidate subset across concurrency settings.
4. If possible, compare the retained diagnostic on a native x86-64 host.
5. Do not change `eps2`, the RPB rule, the candidate set, phase ranking, or the
   global maximum of three phases. A robustness guard may only convert the zero
   division into an explicit no-valid-candidate failure; it must not create a
   prediction.

The Dara full run remains paused at the stage D to E confirmation checkpoint.
No final accuracy was computed.
