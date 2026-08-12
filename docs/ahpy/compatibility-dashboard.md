# aHPy third-party compatibility dashboard

This file is generated from the pinned PRD-8 manifest and retained pilot evidence. `not-run` is preserved when no artifact proves a gate; an expected initial rejection is shown as `blocked`, not as a compatible library pass.

- Manifest selection date: `2026-08-02`
- Evidence timestamp: `none`
- Evidence artifacts: `0`

| Pilot | Category | Commit | Contract | Overall | Checkout | Initial scan | Generate | Build | Tests | Normal | Trace | Debug | Performance |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `cypack-pure-cython` | `pure-cython` | `7dfb3905259c` | `none` | **not-run** | not-run | not-run | not-run | not-run | not-run | not-run | not-run | not-run | not-run |
| `murmurhash-external-c` | `external-c` | `58831632dab7` | `none` | **not-run** | not-run | not-run | not-run | not-run | not-run | not-run | not-run | not-run | not-run |
| `frozenlist-extension-type` | `extension-type-gc-inheritance` | `351ad4bb62b3` | `none` | **not-run** | not-run | not-run | not-run | not-run | not-run | not-run | not-run | not-run | not-run |
| `bezier-numpy-blocked` | `cpython-numpy-blocked` | `cf18953a491e` | `none` | **not-run** | not-run | not-run | not-run | not-run | not-run | not-run | not-run | not-run | not-run |

A production pass additionally requires the port patch, source audit and binary audit gates even though the compact table omits those columns. See `pilot-matrix.md` for the full evidence contract.
