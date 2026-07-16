Local extension-type GC stress now covers cyclic ``GcCycleNode`` pairs,
``GcFieldClearBox`` field clearing, ``ResurrectDel`` resurrection, and nested
``NestedFinalizeBox`` / ``NestedFinalizeSink`` finalization ordering. The
generated oracle exercises these paths with ``gc.collect()`` on the local
Python 3.11 / HPy 0.9 lane only; hosted all-interpreter promotion remains a
separate U2 gate.
