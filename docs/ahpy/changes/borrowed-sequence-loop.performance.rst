.. entry:: Borrowed call-scoped sequence loops
   :type: performance

   Dynamic sequence-index loops now borrow only an incoming call argument whose
   HPy frame/tracker lifetime spans the complete loop. Rebindable owned locals
   still materialize their own reference. Normal/Trace/Debug source-name
   rebinding and all 128 fault selectors pass; generated iteration Trace falls
   from 38 to 36 API calls.
