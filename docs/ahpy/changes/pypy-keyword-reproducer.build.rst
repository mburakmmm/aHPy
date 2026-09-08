.. entry:: Isolate the PyPy keyword-call crash in handwritten HPy
   :type: build

   Add positional and named-call stages for a handwritten
   ``HPyFunc_KEYWORDS`` method ahead of generated modules in the build-once
   portability artifact.  This distinguishes the target interpreter's
   keyword-vector contract from aHPy-generated argument handling without
   changing the unsupported early-warning status.
