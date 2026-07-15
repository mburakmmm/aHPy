Universal HPy for-loops and list/dict comprehensions now accept any owned
expression whose runtime value supports the public sequence index protocol
(``HPy_Length`` plus ``HPy_GetItem_i``). Empty sequences take the ``else``
clause correctly. Generator expressions and iterator-protocol loops remain
rejected on HPy 0.9 because no public ``GetIter``/``IterNext`` exists.
