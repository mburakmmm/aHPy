Optimize's sequence-safe ``list``/``any``/``all``/``dict`` inlined generator
expressions bind genexp ``.0`` parameters and emit through the existing
sequence-index / list-builder path. Set inlining and GetIter-based generators
stay rejected until a public set/iterator API exists.
