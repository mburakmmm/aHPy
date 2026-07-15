Universal HPy now emits list and dict comprehensions whose ``for`` clauses
iterate sequence-index iterables (literal or dynamic). Lists grow through
public ``HPy_CallMethod`` ``append``; dicts use ``HPyDict_New`` plus
``HPy_SetItem``. Nested for-clauses, ``if`` filters, and unpack targets reuse
the existing loop ownership model, including per-iteration body cleanup so
nested loop locals are closed under HPy Debug Mode. Set comprehensions stay
rejected on HPy 0.9 because no public set construction/add API exists.
