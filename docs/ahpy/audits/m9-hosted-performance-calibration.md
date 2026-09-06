# M9 hosted release-performance calibration

Status: five-sample proposal reviewed and promoted; candidate same-HEAD hosted
validation remains required.

## Immutable GitHub evidence

Manual workflow
[`34029830808`](https://github.com/mburakmmm/aHPy/actions/runs/34029830808)
completed successfully on 2026-09-06 for exact main commit
`22d8cbe1b50506f65e01be7ff05081616c656f2d`. Five independent Ubuntu 24.04
CPython 3.11.16 / HPy 0.9.0 samples and proposal job
[`101477446766`](https://github.com/mburakmmm/aHPy/actions/runs/34029830808/job/101477446766)
were green. Every raw report has empty `violations`, passed HPy Debug leak
checking, uses sample ID 1–5, and records the selected source commit equal to
the hosted GitHub SHA.

| Artifact | ID | GitHub archive digest | JSON payload SHA-256 |
|---|---:|---|---|
| proposal | `9988250502` | `d86f0a7e0b5912c3a819184d69599b2eec9ea977ccdf657d6178a6117cd9154d` | `958b0a2d357aa4a81447040c7feacb440f799291b57809ef4aa0831bb053953e` |
| sample 1 | `9988247113` | `8f3130049b5470c85c6d14ed10446f0e67fb5132d3d1b52e4681f42085578eec` | `ae4c724aef562422fe23c2b62c388b379fe85318b408dfcfac8bb2d2c1a21826` |
| sample 2 | `9988245784` | `851f7e36bf0bd4239ed00347fcc7227a472aa32b25f0b837d87e7735e57b7471` | `8e80b207a9c968eec82f4b02073e168cdc68eff9608159812cdd09d38f461862` |
| sample 3 | `9988246678` | `5d95a55e44d741d2ba01d5523181729fbd5df3b58da7d7a9d9460faba17c6627` | `aac050f0f0608b551fe9dda2308cec7498bdbf10e66af99541271acd8fbae1a0` |
| sample 4 | `9988245697` | `b037e9bf1d16360340ab214887db6c86adb8650b127fa79eb0b5430860dbdcc4` | `031ff77b58f1a09b741171291c7b0cde8de06f15f159a99a3059a6d8f19cf72a` |
| sample 5 | `9988244205` | `dde95d2bed21f34a27a3f49bc43c514f1bfd3f173ffd4128a4e1a1843ef86510` | `9d806c3cbeebd3a4344e2f7530357f00cf1bae5f580055b58596d631e17f91fe` |

The proposal was regenerated locally from the five downloaded reports with
the versioned calibrator and compared byte for byte. The reproduced SHA-256 is
the same `958b0a...953e` value.

## Cohort and noise review

All samples share Linux Azure x86-64, GCC 13.3.0, CPython 3.11.16, HPy 0.9.0,
100,000 iterations, seven repeats, two warmups, 10,000 peak-memory iterations,
and a 60-second large-type native timeout. Deterministic source and binary
bytes match across all five reports.

Nine runtime families stayed between 0.979× and 1.054× at their observed
sample extrema. Sequence-index iteration ranged from 1.651× to 1.965× because
the generated trace performs 36 HPy calls per operation versus the handwritten
reference's 18. Native build time had the widest host-noise interval,
2.195–3.753 seconds. Large-type `-O0` stayed within 5.217–5.511 seconds; all
five diagnostic `-O3` attempts reached the documented timeout and remain
non-enforced. Generated/reference peak RSS was exactly 1.0 in every sample.

The proposal applies 20% headroom to the observed maximum, not the median.
The resulting runtime ceilings are 1.21–1.27× except iteration at 2.36×;
generated C, binary, and binary-ratio ceilings are 36,420 bytes, 296,372 bytes,
and 1.42×. Absolute cohort ceilings are 1.77 seconds frontend, 4.51 seconds
native build, 27,726,644 bytes generated peak RSS, 1.20× peak-RSS ratio, 2.92
seconds large-type frontend, and 6.62 seconds large-type `-O0`.

## Promotion decision

The raw distributions support the proposal without weakening the public
semantic or ownership contract. `tests/ahpy/performance-budgets.toml` promotes
all ten runtime, three footprint, and six absolute values exactly, cites the
calibration source, and activates hosted-checkout release enforcement. The
read-only promotion validator reports `status=valid`, `report_count=5`, and
`checked_fields=19`.

This review does not prove the modified candidate commit by itself. Its hosted
benchmark must still bind that new checkout to GitHub SHA and pass every
promoted relative, footprint, and absolute ceiling before PRD-7 closes.
