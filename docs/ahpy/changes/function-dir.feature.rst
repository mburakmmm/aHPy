Universal HPy supports function-scope ``dir()`` as Cython's compile-time local
name list (sorted), matching the existing ``TransformBuiltinMethods`` rewrite
to a ``ListNode``. Runtime ``del`` after the list is built is a deliberate
CPython parity gap. Module-scope ``dir()`` uses sorted mapping keys (see
``sorted-dict-keys``).
