Module, module-function, pure extension-type, ordinary extension-method, and
property docstrings now round-trip through their native Universal HPy
definition fields. Cython's UTF-8-safe C-literal encoder preserves multiline
and control-bearing content; NUL-bearing definition docs receive an explicit
diagnostic because the ABI's C-string fields cannot represent them.
