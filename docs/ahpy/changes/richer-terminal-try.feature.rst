Terminal ``try``/``except`` (current-error-only) allows pre-terminal
``if``/``while``/sequence|range ``for`` plus handler ``return`` of any
bootstrap-owned expression after ``HPyErr_Clear``. Nested ``try``,
``except as``, ``else``, and ``finally`` remain rejected on HPy 0.9.
