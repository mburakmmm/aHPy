.. entry:: Add a one-function generated PyPy keyword-call reducer
   :type: build

   Insert a minimal generated ``identity(value)`` module before the Fibonacci
   portability rung and execute its import, positional-call, and named-call
   paths independently.  The expanded six-binary, fifteen-stage artifact is
   green on CPython 3.11/HPy 0.9 and awaits hosted PyPy classification.
