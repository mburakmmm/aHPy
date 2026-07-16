Direct attribute method calls keep ``HPy_CallMethod`` with the receiver as
``args[0]``. Receiver and positional argument expressions are evaluated in
source order before the call; fault injection covers ``HPy_CallMethod``
cleanup alongside ``HPy_Call`` / ``HPy_CallTupleDict``.
