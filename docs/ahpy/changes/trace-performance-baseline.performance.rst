.. entry:: HPy Trace performance baseline
   :type: performance

   Extended the Universal benchmark history with per-operation HPy Trace API
   deltas, total calls per iteration, and ``ctx_Dup``/``ctx_Close`` churn for
   generated and handwritten reference modules, including extension-type
   creation/method calls and a shared Python-independent external-C function.
   The measurements expose ownership-optimization candidates without
   weakening cleanup contracts. Separate clean children now record peak RSS
   for each implementation without sharing a process high-water mark.
