.. entry:: Isolate PyPy range length in handwritten public HPy
   :type: build

   Add a frontend-independent ``range_length`` method that imports and calls
   ``range`` through public HPy, then applies ``HPy_Length`` to the result.
   Run it before generated modules as its own portability stage; normal, Debug,
   and all sixteen CPython 3.11/HPy 0.9 stages pass locally.
