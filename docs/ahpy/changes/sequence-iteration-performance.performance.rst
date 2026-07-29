.. entry:: Sequence-index iteration performance
   :type: performance

   Added equivalent generated, handwritten HPy, and classic Cython
   sequence-index iteration measurements to the release corpus. True
   iterator-protocol loops and typed memoryviews remain explicitly
   blocked/non-comparable on HPy 0.9 and receive no synthetic performance
   number.
