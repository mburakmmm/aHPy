Release evidence now fails closed unless declared source inputs are committed
and every non-generated sdist file is byte-identical to the selected Git
checkout.  The license inventory and SPDX SBOM explicitly cover embedded
Cython and the pinned build frontend, and publication rehearsal validates all
artifact hashes plus byte-exact regenerated evidence documents.
