Added an emitter-independent Universal HPy handle model with validated storage,
ownership, move, close, duplicate, load, store, return, and leak transitions.
Every M1 HPy handle operation also has a registry-enforced argument and result
ownership contract. Function temporary slots now track independently owned
handle generations and reject release or exit while an owned handle is live.
The base expression lifecycle allocates owned handle temporaries, closes normal
results, moves absorbed results, and delegates empty-handle spelling to the
runtime contract.
The model is covered without requiring C compilation. A strict bootstrap HPy
emitter now exercises duplicate and scalar-return ownership; broader expression
and control-flow cleanup integration remains gated.
Added a pinned HPy 0.9.0 handwritten Universal execution oracle with normal
loading, Debug Mode, and explicit leak detection.
