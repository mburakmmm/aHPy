Enable pure Universal HPy extension types to publish ``__bytes__``,
``__complex__``, and optional-argument ``__round__`` through ordinary
``HPyDef_METH`` definitions. Builtin dispatch, inherited lookup, interpreter
result-type checks, body failures, normal/Trace/Debug execution, and invalid
source arities are covered without inventing unavailable HPy type slots.
