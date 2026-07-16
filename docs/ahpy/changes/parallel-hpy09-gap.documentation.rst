Document and enforce the Universal HPy parallel-worker boundary. HPy 0.9 has
no public arbitrary-worker attachment or exception-transport contract, so
``prange`` and ``cython.parallel.parallel()`` now fail with an actionable
diagnostic instead of reaching CPython thread-state machinery.
