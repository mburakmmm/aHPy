# aHPy scikit-build-core example

This isolated package pins `aHPy-compiler`, HPy, and scikit-build-core. CMake
invokes the installed aHPy frontend to generate Universal C, consumes the
public `ahpy_build_config` contract, and installs the `.hpy0` artifact plus a
small public-loader stub.

From the repository, run the maintained provenance, wheel, audit, install, and
normal/Debug gate:

```console
.venv-hpy09/bin/python Tools/ahpy/scikit_build_integration.py \
  --python .venv-hpy09/bin/python \
  --output /tmp/ahpy-scikit-build.json
```

The current wheel envelope is host-specific packaging evidence, not a
cross-interpreter Universal wheel claim.
