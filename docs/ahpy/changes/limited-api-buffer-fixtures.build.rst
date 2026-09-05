Apply the existing pre-3.11 Limited API buffer exclusion to the aHPy
``bootstrap_types`` and ``fault_injection`` fixtures. Both declare
``Py_buffer`` and remain selected in ordinary CPython C/C++, Limited API
3.11 and later, and the dedicated Universal HPy suites.
