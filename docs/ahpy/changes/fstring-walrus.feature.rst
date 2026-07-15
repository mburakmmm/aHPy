Universal HPy now emits f-strings through owned ``HPy_Str`` / ``HPy_Repr`` /
``HPy_ASCII`` conversion, ``__format__`` via ``HPy_CallMethod``, and piece
concatenation with ``HPy_Add``. Assignment expressions (walrus) evaluate the
right-hand side once, bind a simple local or module global, and return an
owned ``HPy_Dup`` of the assigned value. Conditional and loop local promotion
tracks walrus targets alongside ordinary assignments. Under Universal handle
ownership, unspecified inferred locals stay Python objects so assignments such
as ``x = len(y)`` remain on the supported handle path.
