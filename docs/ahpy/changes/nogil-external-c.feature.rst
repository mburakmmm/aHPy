Extend the Universal HPy ``with nogil`` slice to ``noexcept nogil`` calls with
validated scalar arguments and Python local/global, attribute, item, or slice
scalar result targets. Generated code
performs source-ordered HPy evaluation, checked native conversion, error
propagation, and temporary closure before leaving execution, then boxes a
retained native result and writes its validated target only after re-entry;
the maintained linked example passes normal and HPy Debug success/failure
execution.
