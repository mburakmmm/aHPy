Enable pure Universal HPy extension types to publish synchronous
``__enter__`` and ``__exit__`` context-manager methods through ordinary
``HPyDef_METH`` definitions. Successful entry/exit, exception suppression and
propagation, inherited lookup, body failures, normal/Trace/Debug execution,
and invalid source arities are covered without inventing unavailable HPy type
slots.
