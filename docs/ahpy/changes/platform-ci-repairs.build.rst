Hosted platform regressions now keep virtual-environment symlinks alive during
doctor assertions, exclude MSVC ``.lib``/``.exp`` sidecars from Universal
binary discovery, execute large runtime checks from temporary scripts, run
Apple sanitizers through a native ASan-linked Python
launcher, and stage same-binary PyPy/GraalPy imports with explicit native versus
Python-stub loader provenance.
Interpreter-provided ``hpy.universal`` bridges keep using the unchanged loader
stubs; native-only staging is reserved for interpreters without that bridge.
The non-setuptools Windows builder now discovers and activates the installed
MSVC toolchain, resolves the exact ``cl.exe`` exposed by ``vcvarsall``, and
invokes that executable directly.
Failed module execution now preserves arbitrary active exceptions on HPy 0.9;
attribute rollback remains limited to the reconstructable ``MemoryError`` path
so loader retries cannot degrade into exceptionless ``SystemError`` failures.
The large-type ``-O0`` compile remains the required liveness gate while the
pathological hosted GCC ``-O3`` compile is a bounded recorded diagnostic. A
stress artifact upload is skipped when an earlier gate prevents stress from running.
Hosted semantic and portability builds explicitly use ``-O0`` (MSVC ``/Od``),
leaving direct-build and performance optimization profiles independent.
Hosted run ``29685285138`` validates the complete required Linux, macOS,
Windows, sanitizer, portability, pinned-development, and quality matrix; exact
job/image/compiler evidence and portability hashes are recorded in the M8
audit.
The deterministic rejection corpus also follows the versioned HPy 0.9
generator API-gap diagnostic instead of an obsolete generic node error.
