Hosted platform regressions now keep virtual-environment symlinks alive during
doctor assertions, exclude MSVC ``.lib``/``.exp`` sidecars from Universal
binary discovery, execute large runtime checks from temporary scripts, run
Apple sanitizers through a native ASan-linked Python
launcher, and stage same-binary PyPy/GraalPy imports with explicit native versus
Python-stub loader provenance.
PyPy and GraalPy now always select their native HPy importer instead of a
discoverable CPython-oriented loader stub.
The non-setuptools Windows builder now discovers and activates the installed
MSVC toolchain before invoking ``cl.exe`` directly.
The large-type ``-O0`` compile remains the required liveness gate while the
pathological hosted GCC ``-O3`` compile is a bounded recorded diagnostic. A
stress artifact upload is skipped when an earlier gate prevents stress from running.
The deterministic rejection corpus also follows the versioned HPy 0.9
generator API-gap diagnostic instead of an obsolete generic node error.
