# Blind runtime package

For every row of `sample_manifest.csv`, provide the method with:

1. `patterns/<pattern_filename>`;
2. `sample_elements` as the allowed elemental composition space.

`dataset_family` and instrument fields are used only for the predeclared profile
mapping and stratified reporting. `physical_sample_id` and
`acquisition_variant` are reporting metadata; methods must process each
acquisition independently and must not transfer a prediction between paired
2/8 min scans.

Do not provide the phase count, answer phase formulas, database IDs, source filename or candidate CIFs. Each method uses its documented native database/search workflow and its predeclared phase-count stopping rule; the sample-specific phase count remains hidden.

Patterns retain their original 2theta grids and count scales. Methods may apply only the preprocessing defined and frozen for that method; any resampling/background removal must be recorded in the returned metadata. Use `prediction_template.csv` with one row per predicted phase.
