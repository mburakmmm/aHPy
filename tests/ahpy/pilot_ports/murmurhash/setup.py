from Cython.Build import cythonize
from setuptools import Extension, setup


extensions = cythonize(
    [Extension(
        "ahpy_murmurhash_pilot",
        [
            "ahpy_murmurhash_pilot.pyx",
            "ahpy_murmur_scalar.cpp",
            "upstream/MurmurHash3.cpp",
        ],
        include_dirs=[".", "upstream"],
    )],
    runtime_backend="hpy-universal",
    compiler_directives={"language_level": 3},
)

setup(
    name="ahpy-murmurhash-pilot",
    version="1.0.13",
    packages=[],
    py_modules=[],
    hpy_ext_modules=extensions,
)
