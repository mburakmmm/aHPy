.. entry:: Bound package reproducibility disk usage
   :type: build

   Remove each clean source/build tree after retaining its immutable sdist and
   wheel, so the two-root byte-reproducibility gate does not keep both complete
   build trees on disk simultaneously.
