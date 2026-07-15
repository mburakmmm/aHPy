Universal HPy now supports function-scope ``locals()`` and zero-argument
``vars()`` through Cython's ``FuncLocalsExprNode`` (a specialized ``DictNode``
with ``exclude_null_values``). Generated dict construction duplicates live
local/argument handles, omits deleted or unassigned stable ``HPy_NULL`` slots,
and still propagates ``HPy_Dup`` failures via ``HPyErr_Occurred``. Module-scope
``locals()`` and function-scope ``globals()`` now share the owned module
``__dict__`` path; see ``globals-dict.feature.rst``.
