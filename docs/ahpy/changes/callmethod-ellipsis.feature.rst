Universal HPy attribute method calls now use ``HPy_CallMethod`` with the
receiver as ``args[0]``, avoiding bound-method materialization through
``HPy_GetAttr``. Ellipsis literals are emitted via ``ctx->h_Ellipsis`` plus
``HPy_Dup``. The context model documents that the bootstrap emitter does not
consume CPython ``Cython/Utility`` helpers.
