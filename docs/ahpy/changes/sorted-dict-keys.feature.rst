``SortedDictKeysNode`` materializes mapping ``keys()``, normalizes through
``ListType``, and calls ``sort`` via ``HPy_CallMethod`` to own the result.
Module-scope ``dir()`` uses this path over ``module.__dict__``.
