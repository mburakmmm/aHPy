Do not classify the exact frontend-only
``from cpython.buffer cimport Py_buffer`` declaration as a runtime CPython C-API
dependency when scanning canonical Universal HPy buffer producers; all other
``cpython.*`` cimports remain rejected and the compiler still validates the
complete producer contract.
