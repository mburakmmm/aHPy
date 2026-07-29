aHPy: a Universal HPy backend for Cython
========================================

**aHPy** is a downstream Cython compiler project that adds an explicitly
selected ``hpy-universal`` code-generation backend.  Its goal is to help
extension authors move Cython modules away from the CPython C API and produce
portable C that uses HPy's public Universal ABI.

The backend reuses Cython's parser, semantic analysis, type system, and
optimisation pipeline.  Supported source is emitted through ``hpy.h`` without
including ``Python.h``; unsupported or ABI-dependent constructs fail at their
source location instead of silently falling back to CPython or HPy Hybrid mode.

Project status
--------------

aHPy's frozen product level is **preview**: active, unpublished pre-release
compiler work rather than beta, release-candidate, or stable software.  The
exact CPython 3.11/HPy 0.9.0 platform and build-frontend envelope is recorded
in `the preview support contract <docs/ahpy/release-contract.md>`_.  aHPy
already has an executable
Universal subset, pure-HPy extension types, Python-independent external-C
integration including a narrow ``nogil`` transition lane with explicit
``with gil`` islands, multiple build-system examples, and normal/Trace/Debug,
fault-injection, fuzz, coverage, ABI, footprint, and reproducibility gates.
It is **not yet a claim that arbitrary Cython or NumPy C-API code can compile
unchanged**, and the frontend has not been published to PyPI.

The exact implemented, partial, blocked, and rejected surfaces are maintained
in `the support matrix <docs/ahpy/support-matrix.md>`_.  The authoritative work
queue and agent hand-off are `TODO.md <TODO.md>`_ and
`AGENTTODO.md <AGENTTODO.md>`_.

Core guarantees
---------------

* ``hpy-universal`` is an explicit module/build choice.
* Universal mode never silently switches to a legacy CPython or Hybrid ABI.
* Generated Universal translation units are audited against ``Python.h`` and
  forbidden CPython symbols.
* HPy handles have explicit borrowed/owned lifetime and failure-path cleanup.
* Mutable module/type state is interpreter-owned rather than process-global.
* A supported feature needs semantic, HPy Debug, failure-path, and ABI evidence.
* Existing Cython C/C++ generation retains a separate regression oracle.

Quick start for contributors
----------------------------

The current validated local lane uses CPython 3.11, HPy 0.9.0, and a working C
compiler.  From a clean checkout::

   python3.11 -m venv .venv-hpy09
   .venv-hpy09/bin/python -m pip install \
       -r tests/ahpy/requirements-hpy09.txt \
       -r tests/ahpy/requirements-build-systems.txt
   .venv-hpy09/bin/python Tools/ahpy/doctor.py \
       --python .venv-hpy09/bin/python
   CFLAGS='-O0 -g0' .venv-hpy09/bin/python \
       Tools/ahpy/test_generated_hpy.py \
       --python .venv-hpy09/bin/python

On Windows, use ``.venv-hpy09\Scripts\python.exe`` and omit the POSIX
``CFLAGS`` assignment.  The maintained clean-artifact onboarding flow is
documented in `docs/ahpy/onboarding.md <docs/ahpy/onboarding.md>`_.

Using the backend
-----------------

Generate Universal HPy C directly::

   .venv-hpy09/bin/python -m cython \
       --runtime-backend=hpy-universal -3 module.pyx

Or select it through ``cythonize()``::

   from Cython.Build import cythonize

   extensions = cythonize(
       ["module.pyx"],
       language_level=3,
       runtime_backend="hpy-universal",
   )

The extension must then be built with HPy's Universal ABI tooling.  Maintained
working examples are provided for
`setuptools <examples/ahpy_setuptools/README.md>`_,
`isolated PEP 517 <examples/ahpy_pep517/README.md>`_,
`CMake <examples/ahpy_cmake/README.md>`_,
`Meson <examples/ahpy_meson/README.md>`_, and
`scikit-build-core <examples/ahpy_scikit_build/README.md>`_.

Validation snapshot
-------------------

The current local M9 snapshot records:

* 432 focused compiler tests and 160 quality-tool tests (two expected
  platform skips);
* 592 focused coverage tests on CPython 3.11 and 3.14;
* 100% executable Python-line coverage for the three Universal backend
  implementation modules on both interpreters, with separate 45% frontend-seam
  and 41% quality-tool floors;
* normal, HPy Trace, and HPy Debug execution;
* 128 isolated allocation/API fault selectors;
* nine generated-versus-handwritten Universal HPy performance budgets;
* reproducible frontend wheel/sdist and portability artifacts.

The CPython 3.11/HPy 0.9 stable baseline is green on hosted Linux x86-64 and
ARM64, macOS Intel and ARM64, and Windows x64.  Same-binary PyPy and GraalPy
executions are recorded as allowed-failure early warnings: their selected
runtimes currently fail before aHPy's Universal module semantics can run, so
neither interpreter is a support claim.  See
`the validation matrix <docs/ahpy/validation-matrix.md>`_ and
`the focused-coverage audit
<docs/ahpy/audits/m8-focused-backend-coverage.md>`_; performance evidence
remains in the
`M9 ABI audit <docs/ahpy/audits/m9-abi-performance-baseline.md>`_.

The schedule/manual Linux Valgrind definite-leak job is a required native
memory gate.  A separate Windows Application Verifier and GFlags full-page-
heap diagnostic is declared with a native overrun positive control and five
real generated-runtime checks, but remains allowed-failure until its first
hosted artifact is reviewed; it does not expand the supported baseline.

Production branch-policy validation is green on repair commit
``8ed77677ee6bd69fdc93a81bdfe3e704ea7d924b``: the aHPy, benchmark, full
Cython, coverage, and sanitizer aggregate contexts all passed on the same
HEAD.  Exact run and job links are recorded in
`the validation matrix <docs/ahpy/validation-matrix.md>`_.

Documentation map
-----------------

* `Production readiness roadmap <production-todo.md>`_
* `Project contract and architecture <docs/ahpy/README.md>`_
* `Preview support contract <docs/ahpy/release-contract.md>`_
* `Support matrix <docs/ahpy/support-matrix.md>`_
* `Known limitations <docs/ahpy/known-limitations.md>`_
* `Validation and release gates <docs/ahpy/validation-matrix.md>`_
* `Machine-readable CI policy <docs/ahpy/ci-policy.md>`_
* `Production branch ruleset <.github/rulesets/production-branches.json>`_
* `Handle ownership model <docs/ahpy/handle-model.md>`_
* `Runtime API seam <docs/ahpy/runtime-api.md>`_
* `External-C contract <docs/ahpy/external-c.md>`_
* `Direct build contract <docs/ahpy/direct-build.md>`_
* `PEP 517 frontend <docs/ahpy/pep517.md>`_
* `Build-system integrations <docs/ahpy/build-systems.md>`_
* `Architecture decisions <docs/ahpy/adr/>`_

Relationship to Cython and HPy
------------------------------

This repository is based on upstream `Cython <https://github.com/cython/cython>`_
and preserves its copyright and Apache-2.0 licensing.  aHPy is an independent
downstream effort; it is not an official Cython or HPy release.  HPy itself is
developed at `hpyproject.org <https://hpyproject.org/>`_.  Neutral compiler
seams should remain suitable for focused upstream contributions.

License
-------

The original Pyrex program, which Cython is based on, was licensed "free of
restrictions".  Cython and this downstream work use the permissive Apache
License.  See `LICENSE.txt <LICENSE.txt>`_.

Contributing
------------

Read `CONTRIBUTING.md <CONTRIBUTING.md>`_, then start with
`AGENTTODO.md <AGENTTODO.md>`_ for the verified snapshot and exact
validation commands, then use `TODO.md <TODO.md>`_ for normative milestone and
release criteria.  Keep unsupported Universal features fail-closed and include
ownership, failure-path, CPython-regression, documentation, and audit evidence
with each change.  Upstream Cython contribution guidance remains available in
`docs/CONTRIBUTING.rst <docs/CONTRIBUTING.rst>`_.

Security vulnerabilities must not be posted publicly; follow
`SECURITY.md <SECURITY.md>`_ for the private reporting path.

Upstream Cython background
--------------------------

Cython is an optimising Python compiler that translates Python/Cython source
to C or C++ and supports direct native types and external-library calls.  The
following upstream comparison is retained because aHPy builds on that compiler
rather than replacing its frontend.

Differences to other Python compilers
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Started as a project in the early 2000s, Cython has outlived
`most other attempts <https://wiki.python.org/moin/PythonImplementations#Compilers>`_
at producing static compilers for the Python language.

Similar projects that have a relevance today include:

* `PyPy <https://www.pypy.org/>`_, a Python implementation with a JIT compiler.

  * Pros: JIT compilation with runtime optimisations, fully language compliant,
    good integration with external C/C++ code
  * Cons: non-CPython runtime, relatively large resource usage of the runtime,
    limited compatibility with CPython extensions, non-obvious performance results

* `Numba <http://numba.pydata.org/>`_, a Python extension that features a
  JIT compiler for a subset of the language, based on the LLVM compiler
  infrastructure (probably best known for its ``clang`` C compiler).
  It mostly targets numerical code that uses NumPy.

  * Pros: JIT compilation with runtime optimisations
  * Cons: limited language support, relatively large runtime dependency (LLVM),
    non-obvious performance results

* `Pythran <https://pythran.readthedocs.io/>`_, a static Python-to-C++
  extension compiler for a subset of the language, mostly targeted
  at numerical computation.  Pythran can be (and is probably best) used
  as an additional
  `backend for NumPy code <https://cython.readthedocs.io/en/latest/src/userguide/numpy_pythran.html>`_
  in Cython.

* `mypyc <https://mypyc.readthedocs.io/>`_, a static Python-to-C extension
  compiler, based on the `mypy <http://www.mypy-lang.org/>`_ static Python
  analyser.  Like Cython's
  `pure Python mode <https://cython.readthedocs.io/en/latest/src/tutorial/pure.html>`_,
  mypyc can make use of PEP-484 type annotations to optimise code for static types.

  * Pros: good support for language and PEP-484 typing, good type inference,
    reasonable performance gains
  * Cons: no support for low-level optimisations and typing,
    opinionated Python type interpretation, reduced Python compatibility
    and introspection after compilation

* `Nuitka <https://nuitka.net/>`_, a static Python-to-C extension compiler.

  * Pros: highly language compliant, reasonable performance gains,
    support for static application linking (similar to
    `cython_freeze <https://github.com/cython/cython/blob/master/bin/cython_freeze>`_
    but with the ability to bundle library dependencies into a self-contained
    executable)
  * Cons: no support for low-level optimisations and typing

In comparison to the above, Cython provides

* fast, efficient and highly compliant support for almost all
  Python language features, including dynamic features and introspection
* full runtime compatibility with all still-in-use and future versions
  of CPython
* "generate once, compile everywhere" C code generation that allows for
  reproducible performance results and testing
* C compile time adaptation to the target platform and Python version
* support for other C-API implementations, including PyPy and Pyston
* seamless integration with C/C++ code
* broad support for manual optimisation and tuning down to the C level
* a large user base with thousands of libraries, packages and tools
* more than two decades of bug fixing and static code optimisations


The following is from Pyrex:
------------------------------------------------------
Cython was originally based on `Pyrex <https://www.cosc.canterbury.ac.nz/~greg/python/Pyrex/>`_
by Greg Ewing, with the following written in the Pyrex readme document:

This is a development version of Pyrex, a language
for writing Python extension modules.

For more info, take a look at:

* Doc/About.html for a description of the language
* INSTALL.txt    for installation instructions
* USAGE.txt      for usage instructions
* Demos          for usage examples

Comments, suggestions, bug reports, etc. are most
welcome!

Copyright stuff: Pyrex is free of restrictions. You
may use, redistribute, modify and distribute modified
versions.

The latest version of Pyrex can be found `here <https://www.cosc.canterbury.ac.nz/~greg/python/Pyrex/>`_.

| Greg Ewing, Computer Science Dept
| University of Canterbury
| Christchurch, New Zealand

 A citizen of NewZealandCorp, a wholly-owned subsidiary of USA Inc.
