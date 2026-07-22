Bound Windows Cython test parallelism to four workers after a full hosted C++
matrix job reproduced MSVC's intermittent ``LNK1158`` failure to launch the
Windows SDK resource compiler under seven concurrent end-to-end build trees.
The GraalPy two-worker policy remains independent and a quality contract locks
both limits.
