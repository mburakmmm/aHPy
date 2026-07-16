.. entry:: Reproducible frontend package archives
   :type: build

   Added two-independent-root byte comparison for the ``aHPy-compiler`` sdist
   and wheel, fixed sdist directory/metadata timestamp nondeterminism through a
   deterministic streaming tar/gzip normalizer, and recorded exact build
   provenance plus archive hashes in CI JSON evidence.
