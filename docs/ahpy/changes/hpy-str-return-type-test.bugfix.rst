Support the exact-``str`` return type check that current Cython inserts around
object-typed ``str.format()`` results when generating Universal HPy code.  The
check uses only public HPy type and identity APIs, retains ``None`` semantics,
and leaves all other unproven Python type-test families fail-closed.  A
generated normal/Trace/Debug oracle and the frozenlist pilot cover the repair.
