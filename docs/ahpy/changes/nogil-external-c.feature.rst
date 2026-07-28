Extend the Universal HPy ``with nogil`` slice to ``noexcept nogil`` calls and
exact signed-integer ``except -1 nogil`` errno contracts with validated scalar
arguments and Python local/global, attribute, item, or slice scalar result
targets. Generated code
performs source-ordered HPy evaluation, checked native conversion, error
propagation, and temporary closure before leaving execution, then boxes a
retained native result and writes its validated target only after re-entry;
errno is cleared before a sentinel call and snapshotted before re-entry so
``OSError`` is raised afterward, with missing errno reported as
``RuntimeError``. Explicit non-empty ``with gil`` islands may run supported
Python code between native intervals; implicit, conditional, and empty islands
remain rejected. The maintained linked example passes normal, HPy Trace, and
HPy Debug callback and native success/failure execution.
