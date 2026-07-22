# M8 Windows native-memory diagnostic declaration

Date: 2026-07-22
Status: declared as an allowed-failure schedule/manual job; hosted evidence
pending

## Scope

The Windows lane is a heap-corruption diagnostic, not a native leak gate.
Microsoft describes Application Verifier as a user-mode runtime verifier for
heap, handle, lock, and related Win32 API misuse, and recommends the Basics
layer as the minimum. Microsoft also documents GFlags full page heap as placing
an inaccessible page at the end of allocations, and requires `/p /disable`
after testing so registry-backed page-heap settings do not persist.

Primary references:

- <https://learn.microsoft.com/windows-hardware/drivers/devtest/application-verifier>
- <https://learn.microsoft.com/windows-hardware/drivers/devtest/application-verifier-testing-applications>
- <https://learn.microsoft.com/windows-hardware/drivers/debugger/gflags-commands>

## Fail-closed contract

`Tools/ahpy/run_appverifier_hpy.py`:

1. Requires 64-bit Windows, an administrator account, AppVerifier, GFlags, and
   MSVC. Candidate paths and existence are written before missing tools fail.
2. Copies the selected Python executable beside itself under a unique image
   name, preventing verifier registry settings from affecting unrelated
   `python.exe` processes.
3. Enables Application Verifier Basics plus GFlags full page heap for that
   image and for an independently compiled native heap-overrun control. Query
   output and the GFlags enable result must prove both settings before either
   target runs. The aggregate `gflags /p` listing is retained for diagnosis but
   is not authoritative when AppVerifier owns the same image settings.
4. Requires the native control to terminate nonzero and export at least one
   AppVerifier XML error. A disabled or ineffective detector cannot pass.
5. Runs the unchanged five-process generated Universal corpus through a prefix
   wrapper. A temporary `sitecustomize` probe records the loaded verifier
   modules and rejects every child lacking `verifier.dll`.
6. Requires exactly five process reports, five injection markers, and five XML
   logs, and rejects every runtime XML error severity.
7. Copies the raw AppVerifier log directory and records settings queries,
   commands, stdout/stderr, counts, environment, source hash, and cleanup.
8. Disables page heap and deletes AppVerifier settings for both image names in
   `finally`, even after a positive-control or corpus failure.

The workflow uploads the evidence with `if: always()`. It deliberately remains
`continue-on-error: true` until a manual hosted run proves the runner actually
contains compatible 64-bit tools, the injection marker and positive control
work, all five runtime logs are clean, and cleanup succeeds. Only then may a
separate reviewed change promote it to a required schedule/manual gate.

## First hosted probe

Manual run
[29945115651](https://github.com/mburakmmm/aHPy/actions/runs/29945115651),
job
[89008424404](https://github.com/mburakmmm/aHPy/actions/runs/29945115651/job/89008424404),
proved that the `windows-2025` image contains 64-bit AppVerifier 10.0.26100 at
`C:\Windows\System32\appverif.exe` and x64 GFlags under the Windows Kits
debugger directory. AppVerifier reported `Test [Heaps] enabled.` and
`Full = true`; however, the aggregate `gflags /p` listing said no application
was enabled, so the first implementation rejected the run before launching
either target. The uploaded cleanup record shows successful page-heap disable
and AppVerifier settings deletion for both unique image names.

The follow-up records and validates the direct GFlags `/enable` output while
retaining the AppVerifier full-heap query and aggregate listing. A replacement
hosted run is still required; this probe is tool-discovery and cleanup evidence,
not a clean-corpus or positive-control result.
