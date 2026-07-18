# Direct Universal HPy build contract

`Tools/ahpy/direct_build.py` is the maintained non-setuptools build API for one
generated aHPy C translation unit. It discovers the selected interpreter's HPy
development package in a child process, so a virtual-environment symlink and
its HPy version remain authoritative.

The version-1 plan contract contains:

- ABI `universal` and the HPy-provided `.hpy0` platform suffix;
- `hpy/forbid_python_h` before the public HPy include directory;
- both `HPY` and `HPY_ABI_UNIVERSAL` compile definitions;
- the selected Universal helper static library, or HPy's helper C sources when
  `--runtime=sources` is requested or no single static library is available;
- argv-vector compile/link commands (never shell text), intermediate objects,
  the exact artifact path, target Python, HPy version, platform, and machine;
- MSVC's explicit `HPyInit_<module>` export contract.

On Windows, an already-active `cl.exe` environment is preserved. Otherwise
the executor locates Visual Studio through `vswhere.exe`, loads the target's
`vcvarsall.bat` environment, and still runs every recorded compiler/linker argv
itself; setuptools is not used as a build driver.

The executor refuses to overwrite an artifact or reuse a non-empty object
directory. Before compilation it applies the generated-source Universal
boundary audit; after linking it rejects forbidden undefined CPython symbols
and writes a SHA-256/size manifest beside the artifact.

## Command-line use

Generate C first, then build it without setuptools:

```console
.venv-hpy09/bin/python -m cython \
    --runtime-backend=hpy-universal -3 \
    -o /tmp/example.c path/to/example.pyx
.venv-hpy09/bin/python Tools/ahpy/direct_build.py \
    --python .venv-hpy09/bin/python \
    --module example \
    --source /tmp/example.c \
    --output-dir /tmp/example-artifact \
    --build-dir /tmp/example-objects
```

`--plan-only --json-output plan.json` emits the complete schema-versioned plan
without compiling. `--runtime=static` requires exactly one shipped Universal
helper library; `--runtime=sources` compiles HPy's helper sources. Repeatable
`--extra-source`, `--cflag`, and `--ldflag` arguments extend the native build
without changing ABI selection. Module names are intentionally restricted to
one C identifier in this first contract.

## Direct loading

This path creates an audited `.hpy0` artifact and manifest, not a wheel or
import stub. HPy 0.9's public loader can load it explicitly:

```python
from importlib.machinery import ModuleSpec
import hpy.universal as universal

path = "/tmp/example-artifact/example.hpy0.so"  # platform suffix varies
spec = ModuleSpec("example", None, origin=path)
module = universal.load(
    "example", path, spec, universal.MODE_UNIVERSAL)
```

Use `universal.MODE_DEBUG` together with `hpy.debug.LeakDetector` for Debug
Mode. `Tools/ahpy/direct_build_integration.py` generates the maintained corpus,
executes this exact non-setuptools build, audits it, and loads it in both normal
and Debug modes.

This contract does not define package layout, import stubs, sdists, wheels, or
PEP 517 isolation. Those remain separate M7 gates; a direct artifact must not
be renamed into a purported portable wheel.
