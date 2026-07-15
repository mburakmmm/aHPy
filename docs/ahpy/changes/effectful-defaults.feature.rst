Universal HPy argument defaults may now be arbitrary expressions the bootstrap
emitter can evaluate. Defaults still evaluate once during ``HPy_mod_exec``:
extension-type method defaults run before type publication, and module-function
defaults run after top-level imports/assignments so source-ordered names are
visible. ``__defaults__`` / ``__kwdefaults__`` introspection remains blocked on
HPy 0.9 because Universal module methods are not Python function objects.
