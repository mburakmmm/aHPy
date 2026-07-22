Bound ordinary Windows Cython test parallelism to four workers and isolated
the ``shared_utility`` end-to-end tests after full hosted C++ matrix jobs
reproduced MSVC's intermittent ``LNK1158`` failure to launch the Windows SDK
resource compiler. The isolated tests retain their own ``build_ext -j3``
coverage without competing outer test trees. The GraalPy two-worker policy
remains independent and a quality contract locks these boundaries.
