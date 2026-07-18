Hosted platform regressions now keep virtual-environment symlinks alive during
doctor assertions, exclude MSVC ``.lib``/``.exp`` sidecars from Universal
binary discovery, execute large runtime checks from temporary scripts, run
Apple sanitizers through a native ASan-linked Python
launcher, and stage same-binary PyPy/GraalPy imports with explicit native versus
Python-stub loader provenance.
The hosted large-type GCC ``-O3`` liveness guard is now 180 seconds, and a
stress artifact upload is skipped when an earlier gate prevents stress from
running.
The deterministic rejection corpus also follows the versioned HPy 0.9
generator API-gap diagnostic instead of an obsolete generic node error.
