Extend the Universal HPy ``with nogil`` slice to ``noexcept nogil`` calls with
validated scalar arguments and simple-local scalar results. Generated code
performs source-ordered HPy evaluation, checked native conversion, error
propagation, and temporary closure before leaving execution, then boxes a
retained native result only after re-entry; the maintained linked example
passes normal and HPy Debug success/failure execution.
