.. entry:: Exact package source provenance
   :type: build

   Bound frontend sdist and wheel Core Metadata to the exact aHPy source
   commit, embedded Cython base commit, and HPy compatibility contract; added
   a validated archive ``.gitrev`` and fail-closed release-artifact audits.
   Dependency wheelhouses now retain declared PEP 517 build isolation so an
   uncached HPy 0.9 sdist cannot be mis-versioned as ``0.0.0``.
   Release evidence now retains the validated artifacts with ``SHA256SUMS``,
   an SPDX 2.3 SBOM, license inventory, and exact build provenance.
