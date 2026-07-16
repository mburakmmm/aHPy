Document HPy 0.9 immediate failed-import retry without ``gc.collect()`` as an
upstream/loader lifetime gap. The generated oracle keeps an explicit collection
boundary (``retry_case``); GC-free retry is not a Universal support claim.
Effectful argument defaults are evaluated once in ``HPy_mod_exec``; only
``__defaults__`` introspection remains blocked.
