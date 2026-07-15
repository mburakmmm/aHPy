Universal HPy now deduplicates ``None``, boolean, integer, and float literals
into interpreter-owned module attributes (``__pyx_hpy_const_*``), matching the
existing Unicode/bytes/tuple cache path. Function bodies load owned
``HPy_GetAttr_s`` handles; ``HPy_mod_exec`` constructs each unique value once
with the public HPy literal APIs. Nested tuple members may publish unused
singleton cache entries so identity of top-level scalar returns stays stable
under normal and HPy Debug Mode.
