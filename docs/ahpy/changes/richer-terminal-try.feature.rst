Terminal ``try``/``except`` (current-error-only) allows pre-terminal
``if``/``while``/sequence|range ``for`` in both protected and handler bodies;
matched handlers may run linear supported statements after ``HPyErr_Clear``
and end in a return or explicit raise. Nested ``try``, ``except as``, bare
reraise, ``else``, and ``finally`` remain rejected on HPy 0.9.
