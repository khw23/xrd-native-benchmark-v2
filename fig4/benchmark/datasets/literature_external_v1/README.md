# Literature external XRD benchmark v1

This is one operational external-literature package containing 78 experimental acquisitions from 58 physical samples. Atomly-Core-100 remains a separate package because its generator and labels may still be revised. All four methods may iterate over this package's `blind_package/sample_manifest.csv`; every row carries a `dataset_family` so results can be separated without reconstructing provenance.

## Included families

| family | acquisitions | physical samples | reference type |
|---|---:|---:|---|
| `autoxrd_xerus_10` | 10 | 10 | published experimental phase-presence labels; all scoring exceptions remain private |
| `iucr_qpa_1a_1h` | 8 | 8 | experimental patterns and independently weighed fractions |
| `dara_precursor_20x2` | 40 | 20 | known added phases and nominal mass fractions; paired 2/8 min scans |
| `dara_reaction_20` | 20 | 20 | human expert reference; 16 fully indexed and 4 partial |

## Runtime and reporting rule

Run these 78 acquisitions as one external package if that is operationally simpler, but do not report a single pooled headline accuracy. Report each family independently because published phase-presence labels, weighed references, nominal preparations and expert interpretations do not have the same evidential strength. Dara 2/8 min scans are repeated acquisitions of one physical mixture and must be clustered by `physical_sample_id` for uncertainty or significance estimates.

## Directory boundary

- `blind_package/`: safe method inputs. It contains anonymized spectra, exact element spaces and acquisition metadata, but no phase count or answer labels.
- `private_scoring/`: source filenames, truth labels, reference strength and scoring exceptions. Do not send this directory to a method operator before predictions are frozen.
- `dataset_summary.json` and `validation_report.json`: frozen counts and package checks.

No spectrum is resampled, background-corrected or intensity-normalized during unification. Only the file container is converted to two-column `.xy` where needed.
