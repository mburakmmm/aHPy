Closures (nested ``def`` slice)
===============================

Status
------

Partial support for one-level nested ``def`` closures in Universal HPy mode.

Supported
---------

- Nested ``def`` inside a module-level outer function.
- Captured Python locals stored in a synthesized env type as ``HPyField`` values.
- Outer reassignment into a captured name updates the shared env field.
- Callable objects are pure HPy extension types with ``HPy_tp_call``; no code
  objects, ``CyFunction``, or ``Python.h``.

Oracle examples::

    make_adder(2)(3) == 5
    make_mutated_reader(1)() == 11

Rejected
--------

- Nested-nested closures (inner function with its own nested ``def``).
- Default arguments on nested ``def``.
- ``*args`` / ``**kwargs`` on nested ``def``.
- Generators and ``yield`` inside nested ``def``.
- Decorators on nested ``def``.
- Nested ``def`` without ``InnerFunctionNode`` synthesis.

References
----------

- ``docs/ahpy/adr/0005-closure-capture-model.md``
- ``docs/ahpy/context-model.md``
