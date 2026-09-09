.. entry:: Add a one-function generated PyPy keyword-call reducer
   :type: build

   Insert a minimal generated ``identity(value)`` module before the Fibonacci
   portability rung and execute its import, positional-call, and named-call
   paths independently.  The expanded six-binary, fifteen-stage artifact is
   green on CPython 3.11/HPy 0.9; hosted run ``34331675408`` passes all three
   reducer stages and leaves the failure in the later Fibonacci execution.
