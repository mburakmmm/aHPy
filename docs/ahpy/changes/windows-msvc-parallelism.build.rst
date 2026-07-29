Bound ordinary Windows Cython test parallelism to four workers and isolated
the ``shared_utility`` end-to-end tests after full hosted C++ matrix jobs
reproduced MSVC's intermittent ``LNK1158`` failure to launch the Windows SDK
resource compiler. The isolated tests retain their own ``build_ext -j3``
coverage without competing outer test trees. A later isolated run reproduced
the same failure inside that fixture-local ``-j3`` pool, so all eight
shared-utility build commands are now ``-j1`` as well. Parallel build coverage
remains in other fixtures, the GraalPy two-worker policy remains independent,
and a quality contract locks both serialization boundaries.
