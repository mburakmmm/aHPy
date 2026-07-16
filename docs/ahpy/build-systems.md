# CMake, Meson, and scikit-build-core

`ahpy_build_config` exposes the selected interpreter's versioned Universal HPy
contract. The command wrapper can render it for CMake or Meson:

```console
python Tools/ahpy/build_system_config.py --python /path/to/python \
  --module my_module --format cmake --output /tmp/ahpy-config.cmake
python Tools/ahpy/build_system_config.py --python /path/to/python \
  --module my_module --format meson --output ./ahpy_config/meson.build
```

The contract contains exact include order, Universal definitions, helper
static/source runtime selection, extension suffix, platform identity, and
initializer export. It is native-toolchain state: do not commit it or reuse it
with another Python/HPy installation.

Maintained examples:

- [`examples/ahpy_cmake`](../../examples/ahpy_cmake/README.md)
- [`examples/ahpy_meson`](../../examples/ahpy_meson/README.md)
- [`examples/ahpy_scikit_build`](../../examples/ahpy_scikit_build/README.md)

Run the direct build-system gates after installing the pinned tools:

```console
python -m pip install -r tests/ahpy/requirements-build-systems.txt
python Tools/ahpy/build_system_integration.py --python /path/to/python \
  --system all --output /tmp/ahpy-build-systems.json
python Tools/ahpy/scikit_build_integration.py --python /path/to/python \
  --output /tmp/ahpy-scikit-build.json
```

The scikit-build command creates a closed wheelhouse and disables index access
inside the real PEP 517 resolver. Both produced packaging wheels retain
host-specific tags under HPy 0.9; ADR 0004 forbids treating them as portable
Universal wheels.
