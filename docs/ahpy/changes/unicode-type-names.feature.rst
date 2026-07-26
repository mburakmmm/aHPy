Valid Unicode `cdef class`, property, closure-capture, argument, and public
field names now retain their HPy/Python identity while private generated C
symbols use deterministic UTF-8 encoding. Generated C strings now share
Cython's UTF-8-safe literal encoder, including multiline property docs with
quotes, backslashes, and controls; NUL-bearing HPy definition docs are rejected
explicitly because the ABI cannot represent them.
