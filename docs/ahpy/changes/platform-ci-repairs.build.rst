Hosted platform regressions now keep virtual-environment symlinks alive during
doctor assertions, exclude MSVC ``.lib``/``.exp`` sidecars from Universal
binary discovery, run Apple sanitizers through a native ASan-linked Python
launcher, and stage same-binary PyPy/GraalPy imports with explicit native versus
Python-stub loader provenance.
The deterministic rejection corpus also follows the versioned HPy 0.9
generator API-gap diagnostic instead of an obsolete generic node error.
