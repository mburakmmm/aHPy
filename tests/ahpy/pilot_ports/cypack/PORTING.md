# cypack pure-Cython pilot port

This fixture derives from `FedericoStra/cython-package-example` 0.1.7 at
commit `7dfb3905259c5c7a82770806e5e558999eef79ce` under the included MIT
license. The selected upstream sources and their Git blob IDs are:

- `src/cypack/answer.pyx`: `bdce7a902844f6e486df1876eb2f68623ad3818c`;
- `src/cypack/fibonacci.pyx`: `26b593572802c3e7318ed93d7985fdef12312825`;
- `src/cypack/utils.pyx`: `f265290731f3023148bf178228e79a8ce1ce3cc4`;
- `src/cypack/data/zen.txt`: `634c12ba1c1db37e264262258492096623da5790`.

The port intentionally makes only three source transformations:

1. typed `cpdef`/`cdef` entry points become Python-visible `def` functions;
2. `answer.pyx` imports `axpy` through the absolute Python module boundary
   instead of the Cython C API (relative imports are outside the current
   Universal subset);
3. C-typed Fibonacci locals become Python locals while retaining the same
   counted loop and simultaneous assignment semantics.

The unrelated `cypack.sub.wrong` helper-C extension is not part of this
pure-Cython pilot. The fixture preserves the selected public results:
`the_answer() == 42`, `axpy(4, 10, 2) == 42`, `fib(7) == 13`, and the Zen data
MD5 value.
