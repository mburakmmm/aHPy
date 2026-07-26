Extend the Universal HPy ``with nogil`` slice to discarded ``noexcept nogil``
calls with validated scalar arguments. Generated code performs source-ordered
HPy evaluation, checked native conversion, error propagation, and temporary
closure before leaving execution; the maintained linked example passes normal
and HPy Debug success/failure execution.
