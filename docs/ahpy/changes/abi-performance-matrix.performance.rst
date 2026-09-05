.. entry:: Separate ABI performance matrix
   :type: performance

   Added independent classic Cython, HPy CPython ABI, and HPy Universal ABI
   benchmark profiles for the same ten operations. Each profile retains its
   applicable runtime, build, footprint, and clean-process peak-memory evidence
   without publishing a misleading aggregate cross-ABI overhead. The gate also
   records bounded ``-O0``/``-O3`` native compile time for the large extension-
   type corpus.
