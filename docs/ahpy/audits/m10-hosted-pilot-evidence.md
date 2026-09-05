# M10 hosted pilot evidence

Verified on 2026-09-05 from the completed
[aHPy run 31794650087](https://github.com/mburakmmm/aHPy/actions/runs/31794650087)
and its successful
[compiler-and-quality job](https://github.com/mburakmmm/aHPy/actions/runs/31794650087/job/94748966115).
This records the declared pilot ports, not full compatibility with each upstream
library or a production release approval.

## Source and artifact identity

- PR head: `652cd3f66341e08a383fe565ee89849f44eec1a1`.
- Executed PR merge commit: `0871324091539ac2c14c429737fa74f29b34d0a4`.
- Both commits have tree `ffa96cf3a438732869ae32a8e34fb7d44e122dc4`, verified
  against local Git and GitHub's commit API. The merge's other parent is
  `960e357b7bfa881c8952cdfa7271351be28e8128`.
- [Artifact 9216896185](https://github.com/mburakmmm/aHPy/actions/runs/31794650087/artifacts/9216896185):
  `ahpy-pep517-31794650087-1`, GitHub archive digest
  `sha256:0496644d9240c27c3de5c5a0d444ad0f131ca13250315248c005101c585e9b46`.
- GitHub expiration: 2026-11-12. The four unmodified JSON inputs are retained
  in [evidence/pilots-31794650087](evidence/pilots-31794650087) so that dashboard
  regeneration does not depend on artifact retention.

The GitHub archive digest identifies the uploaded archive. The separately
computed payload hashes below identify the retained files; they are not a
claim that the downloaded archive was independently hashed.

| Payload | SHA-256 |
| --- | --- |
| `pilot-matrix.json` | `a61af02f7d9704f097758680c6f8f8d1f4d2b095bcad0d726ba6b410189929bf` |
| `cypack-pilot.json` | `3be8cc6d9ca20304376de5adc530c44c02e2a5190d30850591416580580b17ce` |
| `murmurhash-pilot.json` | `c5bd8eaf87061eef39a772570abc0d09a6ff7480e695e02cb2bf7ef13b26f241` |
| `frozenlist-pilot.json` | `cb5efed50563f1d271d268a95ec0268cf78c9af084c4f1e092532a9c1216a518` |
| `compatibility-dashboard.md` | `bb7608957b35deaa420e41e14c31bdbf47c431772832c1d4e99319faed5d6719` |

## Results and limits

| Pilot | Verified result | Scope |
| --- | --- | --- |
| cypack | pass | Three selected modules; generated/binary audit, wheel build/audit/install, installed Normal/Trace/Debug and semantic oracle |
| murmurhash | partial | Fixed-width `hash_u64` adapter using pinned upstream C++; conversion failures, audits and Normal/Trace/Debug |
| frozenlist | partial | Supported construct/mutate/freeze/hash surface, HPy field GC cycle, same-module inheritance and constructor-failure cleanup |
| bezier | blocked | Exact NumPy C-API diagnostics at upstream `37:1` and `38:1`; build/runtime are not run |

All three executable ports passed their declared generation, native build,
source/binary audit, tests, Normal/Trace/Debug and performance-measurement
gates on Linux x86-64, CPython 3.11.15 and HPy 0.9.0. Performance evidence has
seven repetitions and `budget_enforced = false`: it records comparable costs
but does not satisfy the PRD-7 release budget gate. In particular, the
frozenlist subset's measured cost is about 9.57 times its equivalent Python
list/tuple workload, while cypack's axpy and Fibonacci ratios are about 1.81
and 2.05; these results must remain visible when reviewing release suitability.
The murmurhash scalar adapter ratio is about 0.105.

The retained JSON contains gate outcomes, source provenance where emitted,
timings and performance data. It does not retain every temporary generated C
file or native pilot binary. Rebuilding those requires the pinned source,
port fixtures and documented integration commands in
[pilot-matrix.md](../pilot-matrix.md). Full-library API coverage, user-language
integration, release performance calibration and RC feedback remain separate
work items.

## Reproduce the dashboard

From the repository root:

```console
python3 Tools/ahpy/build_pilot_dashboard.py \
  --evidence docs/ahpy/audits/evidence/pilots-31794650087/pilot-matrix.json \
  --evidence docs/ahpy/audits/evidence/pilots-31794650087/cypack-pilot.json \
  --evidence docs/ahpy/audits/evidence/pilots-31794650087/murmurhash-pilot.json \
  --evidence docs/ahpy/audits/evidence/pilots-31794650087/frozenlist-pilot.json \
  --output /tmp/ahpy-pilot-dashboard.md
cmp /tmp/ahpy-pilot-dashboard.md docs/ahpy/compatibility-dashboard.md
```

Regeneration from the downloaded artifact and from the retained JSON both
match the hosted dashboard byte for byte. Each future dashboard update must
carry its own run, executed commit, artifact identity and payload hashes.
