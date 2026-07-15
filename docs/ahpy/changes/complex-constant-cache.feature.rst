Imaginary literals (``ImagNode``) join the interpreter-owned module constant
cache. Repeated ``nj`` returns in a module share one ``complex`` construction
in ``HPy_mod_exec``; function bodies load the cached handle. Identity oracle:
``imag_literal_a() is imag_literal_b()``.
