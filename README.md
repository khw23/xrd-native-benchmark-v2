# XRD native-workflow benchmark runner

Private cross-device runner for Atomly-core-v2.

This repository contains 100 blind synthetic powder-XRD patterns, exact sample
element sets, measurement metadata, and public-method adapters. It contains no
generator CIFs, sample-level phase count, phase identity, fraction, difficulty
label, or private evaluation table.

Start with `fig4/benchmark/REMOTE_RUN_GUIDE_V2.md`.

Scientific contract:

- each sample receives XRD + `sample_elements`;
- every method uses one global upper bound of three phases;
- MatDiffract, XERUS and Dara use preregistered native database workflows;
- CrystalShift has no native database retrieval layer, so this repository names
  its pipeline `CrystalShift + CrystalTree with COD front-end`;
- Dara and CrystalShift share the same frozen Dara-COD front-end, but never use
  the private 84 Atomly generator CIFs;
- physical composition is phase weight fraction; CrystalShift activation is not
  reported as a weight or mole fraction.

Blind package SHA-256:

```text
48f1a2486bab1b82bd0c4f8035925a4cb5ac2c7abdfba754b6a985d424cfde26
```
