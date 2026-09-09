.. entry:: Isolate the PyPy keyword-call crash in handwritten HPy
   :type: build

   Add positional and named-call stages for a handwritten
   ``HPyFunc_KEYWORDS`` method ahead of generated modules in the build-once
   portability artifact.  This distinguishes the target interpreter's
   keyword-vector contract from aHPy-generated argument handling without
   changing the unsupported early-warning status.

   Hosted run ``34266960354`` passes both handwritten keyword-call stages and
   retains the later generated Fibonacci ``SIGSEGV`` with its bounded native
   trace, proving that the remaining fault is generated-module-specific.
