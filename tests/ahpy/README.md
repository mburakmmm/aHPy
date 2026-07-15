# Universal HPy reference corpus

`minimal_universal.c` is a handwritten public-HPy oracle, not generated aHPy
output. It proves that the pinned HPy toolchain can build and load a Universal
module and gives generated-code tests a known-good structural target.

Create the isolated pinned environment and run it from the repository root:

```console
.venv-hpy09/bin/python -m pip install -r tests/ahpy/requirements-hpy09.txt
.venv-hpy09/bin/python Tools/ahpy/test_minimal_hpy.py
```

The test builds outside the worktree, scans out legacy C-API spellings, loads
the `.hpy0` binary normally, and repeats the same semantic checks in HPy Debug
Mode.

`bootstrap_answer.pyx` is the first strict generated-code vertical slice. Run
`Tools/ahpy/test_generated_hpy.py` to compile it through Cython's
`hpy-universal` backend, reject legacy C-API spellings, build its `.hpy0`
binary, and execute it in both normal and HPy debug modes.
