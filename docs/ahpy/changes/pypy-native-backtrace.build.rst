.. entry:: Capture signal-failing portability backtraces
   :type: build

   Re-run a signal-terminated cross-interpreter stage under bounded, offline
   ``gdb`` when explicitly requested, retain structured signal/frame/output
   evidence in schema-v2 portability JSON, and leave ordinary nonzero exits
   untouched.  This prepares the reduced PyPy Fibonacci failure for a native
   upstream backtrace without changing its unsupported early-warning status.
