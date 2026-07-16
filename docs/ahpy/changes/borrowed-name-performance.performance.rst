.. entry:: Borrowed direct-name HPy operands
   :type: performance

   Aligned generated and handwritten positional-only benchmark contracts, then
   reused live Name handles for HPy APIs that borrow attribute receivers and
   zero-argument callables. Required multi-argument positional-only functions
   now use ``HPyFunc_VARARGS`` without a keyword tracker, and proven direct-name
   operands are reused by binary operations and fixed sequence builders. Trace
   shows attribute, call, arithmetic, and container paths now match their
   handwritten references with no duplicate/close churn. Closure call slots
   now accept empty ``**{}`` while rejecting actual keywords consistently for
   no-, one-, and multi-argument positional-only nested functions.

   Extension-field owners and direct Name values are likewise borrowed under
   call-lifetime and evaluation-order proofs. Type/module owners are loaded
   lazily, and positional-only initializers avoid keyword trackers. Type method
   Trace now matches the handwritten reference with zero handle churn; type
   construction retains only a separate ``__cinit__`` ``AsStruct`` call.

   Validated external-C scalar calls now lower safely representable numeric
   literals directly to typed portable C constants. Dynamic and non-portable
   values retain checked HPy conversion. External-C Trace consequently matches
   the handwritten one-call reference with zero handle churn.
