Universal HPy now supports sequence unpacking assignment through public
``HPy_Length`` / ``HPy_GetItem_i`` (plus ``HPyListBuilder`` for starred rest
targets), parallel ``a, b = 1, 2`` and cascaded ``a = b = x`` evaluation order,
and fixed list/tuple ``for a, b in [...]:`` unpack targets. Length mismatches
raise ``ValueError`` with CPython-compatible messages and ownership-safe
failure cleanup.
