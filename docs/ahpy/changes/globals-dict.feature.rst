Function-scope ``globals()`` and module-scope ``locals()`` duplicate the
module's owned ``__dict__`` via ``HPy_GetAttr_s(module, "__dict__")``. There is
no separate ``HPyGlobal`` storage for this surface. Item assignment through the
returned mapping publishes module attributes with the existing attr model.
