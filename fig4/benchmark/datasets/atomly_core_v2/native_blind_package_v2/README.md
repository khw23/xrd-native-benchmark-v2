# Atomly-core-v1 blind benchmark package

This package contains **100 synthetic powder XRD patterns** for a native-workflow
phase-identification benchmark. It intentionally does not contain candidate
CIFs, sample-level phase identities, phase fractions, or per-sample phase count.

## Files

- `patterns/XRDV2_XXXX.xy`: two columns, 2theta in degrees and intensity counts.
- `sample_manifest.csv`: sample element sets, pattern filenames, grid and SHA-256 checksums.
- `prediction_template.csv`: requested return format; use one row per predicted phase.
- `instrument_metadata/`: known synthetic measurement metadata for methods that require an instrument profile.

## Fixed data-generation scope

- The dataset contains 50 binary and 50 ternary mechanically mixed powder patterns,
  but the order of each individual sample is hidden. Use one fixed global upper
  bound of three coexisting phases; do not infer order from sample identifiers.
- `sample_elements` is the exact sample-level union of elements and is disclosed
  to every method, matching the chemical-space input used by XERUS and Dara.
- Each method uses its documented native database/search space. No method may use
  the private Atomly generator CIFs as input in the primary end-to-end result.
- Cu Kalpha1 + Kalpha2, fixed Rigaku MiniFlex-600-like reference profile.
- Grid: 10.0-90.0 degrees 2theta, step 0.02 degrees.
- Continuous, non-0.1-grid phase weight fractions; formula-unit mole fractions are private derived labels.
- Global zero shift, additional Gaussian broadening, nonnegative smooth background and Poisson counting noise.
- These are generated benchmark data, not measurements from a named physical instrument.

## Required prediction convention

Return the method's native database and structure identifier, reduced formula,
space group and, if available, the selected CIF. Fractions must be **phase weight
fractions** and should sum to one over the phases in a solution. Do not force a
CrystalShift activation into a weight fraction. Please also report total
per-sample runtime. Do not use external knowledge of the private labels.

## Important fairness note

MatDiffract, XERUS and Dara have database/retrieval workflows. CrystalShift does
not: its paper requires user-prepared candidate CIFs. Any end-to-end result must
therefore be labeled as a composite pipeline such as `CrystalShift + COD
front-end`, with the front-end frozen before predictions are inspected.
