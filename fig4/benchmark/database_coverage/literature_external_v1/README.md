# Literature-External-v1 database-scope audit

This directory records only public-input-derived database scope. It contains no
phase labels, source filenames, sample-specific phase counts, or private CIFs.

## Scope comparison

| item | Atomly-Core-100 | Literature-External-v1 | external-only / overlap |
|---|---:|---:|---:|
| acquisitions | 100 | 78 | — |
| unique disclosed full element sets | 84 | 46 | 45 / 1 |
| unique elements | 38 | 30 | 9 new elements |
| XERUS native OQMD full-element queries | 84 | 46 | 45 / 1 |

The nine elements absent from Atomly-Core-100 but present in the external set
are `Bi`, `Cr`, `Ge`, `H`, `In`, `Mo`, `Pb`, `V`, and `Y`.

## COD audit

Using Dara's bundled 2024 COD index and its frozen selection semantics, the 46
external full element sets require 2,122 unique COD CIFs. The existing
Atomly-Core sparse mirror can reuse 665 of them; 1,457 additional CIFs are
required. See `cod/coverage_audit.json` and `cod/required_cod_audit.csv`.

The selection is all non-gas phases indexed under every nonempty subset of the
disclosed sample element set, with `e_hull <= 0.1 eV/atom` when the bundled
index provides an energy-above-hull value. This is candidate-database scope,
not ground truth.

## OQMD audit

XERUS's official
[`multiquery.py`](https://github.com/pedrobcst/Xerus/blob/53ed38b6d8437cf61abee270672bd33de75f15a3/Xerus/queriers/multiquery.py)
creates exactly one OQMD `OptimadeQuery` from the complete disclosed element
list for each sample. Reproducing that native logic therefore gives 46 unique
OQMD queries, not every nonempty subset. Relative to the 84 Atomly full-element
sets, 45 are new and one overlaps. The older Atomly cache also happens to
contain one additional external full system because that system occurred as a
subset in the earlier over-expanded cache, so 2/46 cache folders can be reused
and 44 must be downloaded. See `oqmd/coverage_audit.json` and
`oqmd/required_systems_audit.csv`.

OQMD currently translates the query to containment of every listed element plus
`ntypes=len(elements)`, so each cached response is validated against the exact
full element set. Expanding all subsets would not reproduce XERUS and would send
hundreds of redundant requests to the public API.

These counts are frozen against the SHA-256 of the public
`blind_package/sample_manifest.csv`. Re-run the two audit commands in the
external run guide if the manifest changes.

The manifest-level comparison is independently reproducible with:

```bash
python fig4/benchmark/prototypes/audit_literature_external_scope_v1.py
```

Expected status is `PASS`. The per-COD and per-OQMD CSV files retain every ID or
element-system decision, so the headline counts are not accepted on count alone.
