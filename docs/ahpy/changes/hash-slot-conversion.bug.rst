Fix Universal ``__hash__`` slot conversion for integer results that fit
``HPy_hash_t`` but exceed Python's integer-hash modulus.  Convert fitting
values directly, map ``-1`` to ``-2``, and use ``HPy_Hash`` only as the
overflow fallback for larger integers, matching CPython slot semantics.

The frozenlist pilot exposed the regression when hashing a tuple-backed
extension type.  Compiler-source assertions and generated normal/Trace/Debug
runtime checks now cover fitting large values, overflowing values, ``-1``,
and non-integer returns.
