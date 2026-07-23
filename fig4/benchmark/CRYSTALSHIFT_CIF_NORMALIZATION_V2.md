# CrystalShift COD v3 v2 CIF normalization

## Scope

The adapter applies one frozen, truth-independent rule set to all 6,622 COD
candidate records. It does not inspect predictions, private labels, sample-specific
phase counts, or accuracy. Original COD CIF files are never modified.

## Conversion order

1. Validate the frozen manifest database ID and source CIF SHA-256.
2. Parse the source with pymatgen without primitive-cell conversion.
3. If parsing fails, remove only atom-loop rows lacking a species or fractional
   coordinate and remove an invalid `_atom_site_attached_hydrogens` column. The
   structured cleanup recovered five repeated records for one COD ID.
4. Run the upstream CrystalShift converter on the original CIF.
5. On failure, serialize the parsed structure with pymatgen symmetry metadata and
   run the converter again.
6. On failure, serialize the same structure in P1 explicit-site form and retry.

Normalized CIFs retain eight significant figures. The pymatgen CIF block line
limit is set to 2,048 so that one atom-site loop record is not split across lines.
This fixes xrayutilities interpreting a wrapped occupancy as an element name; it
does not reduce numeric precision.

## Structure gate

Every normalized CIF must preserve the exact element set, site count, and
eight-decimal occupancy signature; composition tolerance is `rtol=1e-6,
atol=1e-6`, maximum absolute cell-parameter delta is `1e-5`, and
`StructureMatcher` must pass without lattice scaling or supercells. Failed
attempts remain in `conversion_attempt_failures.csv` even when a later strategy
succeeds.

The source-declared IT space-group number is used when valid; otherwise the number
computed with `symprec=0.1` and `angle_tolerance=5` is used. The adapter corrects
the converter header's crystal system because the upstream converter recognizes
`_space_group_IT_number` but not pymatgen's `_symmetry_Int_Tables_number`.

Four frozen records (two distinct COD IDs) contain elements not present in their
front-end system key. They are retained without CIF changes, because deleting them
would alter the frozen front-end, and are marked with
`elements_subset_of_system=false` in the audit.

## Final gate

- Candidate records: 6,622
- Converted: 6,622
- Final failures: 0
- Direct: 5,734
- Symmetry normalized: 870
- P1 normalized: 18
- Failed conversion attempts retained: 906
- Structure-validation failures: 0
- Substantive changes: 0
- Original XRD checksum changes: 0
