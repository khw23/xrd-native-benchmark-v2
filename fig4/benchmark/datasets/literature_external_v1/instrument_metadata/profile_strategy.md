# Frozen instrument-profile strategy

This file predeclares instrument handling before predictions are inspected. No
profile is fitted or selected from benchmark answers or method accuracy.

## Source evidence

- Dara source XRDML files record Cu Kalpha1/Kalpha2, a 145 mm radius,
  `PIXcel1D-Medipix3 detector`, and `PANalytical Aeris Instrument Suite` /
  `AERIS`. Dara 1.3.0 also defaults to the bundled
  `Aeris-fds-Pixcel1d-Medipix3` BGMN profile.
- The official [IUCr CPD-QARR data page](https://www.iucr.org/resources/commissions/powder-diffraction/projects/qarr/data)
  records a Philips 3020/PW3710, 173 mm radius, Cu long-fine-focus tube,
  Bragg-Brentano reflection geometry, 1-degree divergence and scatter slits,
  0.3 mm receiving slit, curved graphite monochromator, and proportional
  counter. Dara does not bundle an exact PW3020/PW3710 profile.
- The [AutoXRD paper](https://doi.org/10.1021/acs.chemmater.1c01071)
  specifies Cu Kalpha (`1.5406 Angstrom`) and publishes the ten experimental
  mixtures, but neither the paper nor the distributed two-column spectra
  provide a calibrant-derived instrument profile.
- The official [XERUS repository](https://github.com/pedrobcst/Xerus) states
  that its bundled `RigakuSi.instprm` was fitted to NIST Si on a Rigaku
  MiniFlex 600 and recommends obtaining a profile for the user's own machine.

## Frozen choices

| method | Aeris 60 | IUCr Philips 8 | AutoXRD/XERUS 10 |
|---|---|---|---|
| Dara | source-matched bundled Aeris profile | `pw1800-fds`, closest bundled surrogate | bundled Rigaku MiniFlex surrogate |
| XERUS | bundled `RigakuSi.instprm` native-default baseline | same native-default baseline | same profile used by the distributed XERUS workflow |
| CrystalShift + CrystalTree | no instrument-profile input; frozen fixed-pseudo-Voigt baseline | same | same |

For Dara, use `dara_profile_map.csv` in one 78-pattern run. For XERUS, use one
frozen native-default profile for all 78 patterns because no source-matched
GSAS-II `.instprm` is available for Aeris or PW3020/PW3710. Hand-constructing
different `.instprm` files from nominal hardware geometry would introduce
unvalidated line-shape coefficients and an avoidable method-dependent tuning
degree of freedom.

The profile mismatch must be reported with XERUS results and with the 18 Dara
surrogate-profile results. It is a limitation, not a reason to discard the
experimental external benchmark. If certified calibrant-derived Aeris or
PW3020/PW3710 `.instprm` files become available later, they define a separately
versioned sensitivity analysis rather than a replacement chosen after seeing
accuracy.
