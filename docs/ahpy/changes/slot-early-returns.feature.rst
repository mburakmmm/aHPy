Extension slot and property bodies reuse module-function returning-``if``
lifetime rules. ``__len__``/``__bool__``/``__hash__``/``__contains__`` unwrap
``CoerceFromPyTypeNode`` and convert through ``native_return_kind``. Early
returns inside conditional slot bodies are supported; ``except as``,
``finally``, and GetIter-based slot iteration stay rejected.
