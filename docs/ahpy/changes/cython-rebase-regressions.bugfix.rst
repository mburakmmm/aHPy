Fixed two regressions exposed by the Cython 3.3.0b1 baseline validation.
Astral Unicode constants now compare their numeric code point, rather than a
one-character string, while constructing ``Py_UNICODE`` data.  C++ template
argument deduction now applies the standard function-to-pointer decay for
non-reference parameters, which restores calls into current libc++ algorithm
templates.  Existing Unicode C/C++ tests and a dedicated templated-function
regression cover both repairs; Universal HPy support claims are unchanged.
