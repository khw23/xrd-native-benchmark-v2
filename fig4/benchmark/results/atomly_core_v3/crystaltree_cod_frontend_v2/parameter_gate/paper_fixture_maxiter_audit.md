# CrystalTree public Al-Fe-Li-O parameter audit

Status: **passed**

This audit uses only the upstream public paper fixture. No private benchmark truth was read.

## Fixed selection

Before execution, the rule was fixed as the first four source-order rows having exactly 1, 2, and 3 nonzero activations, concatenated by phase count. Selected rows: `1, 11, 21, 22, 2, 3, 4, 5, 31, 33, 34, 35`.

Public row 6 was run once at 128 iterations before timing and was excluded from every metric. This removes first-call JIT compilation from the comparison.

## Published configuration

`LM`, `Simple` (not EM), least squares, `std_noise=0.01`, `mean_theta=[1.0, 0.5, 0.5]`, `std_theta=[0.1, 0.05, 0.1]`, one inactive EM loop, regularization on, no amorphous phase, and background off. The paper script adds unseeded random positive noise; this audit omits that augmentation so both iteration settings receive byte-identical public spectra.

## Results

| maxiter | success | failures | strict top-1 | phase precision | phase recall | mean residual | runtime (s) |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 128 | 12/12 | 0 | 0.5833 | 0.6667 | 0.75 | 0.398629 | 51.5 |
| 512 | 12/12 | 0 | 0.5833 | 0.7308 | 0.7917 | 0.348128 | 52.9 |

## Gate

The pre-registered gate requires zero failures in both settings and strict full-combination top-1 accuracy at 512 iterations to be no lower than at 128. Precision, recall, residual, and runtime are reported but do not alter the gate.

This is a small public sensitivity audit, not validation of the private benchmark or of the README-derived production priors.
