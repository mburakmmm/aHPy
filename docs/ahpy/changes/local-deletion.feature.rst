Universal HPy now supports ``del`` of Python locals and arguments. Deletion
closes the previous value and stores ``HPy_NULL`` in a stable owned slot.
Later reads raise public ``UnboundLocalError`` with CPython's
``local variable '...' referenced before assignment`` message. Conditional
and loop ``del`` promote that stable slot before the ``if``/``for``/``while``
so branch and iteration lifetime restores keep pointing at the nullled slot.
Module-global ``del`` is unchanged.
