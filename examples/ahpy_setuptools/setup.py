from Cython.Build import cythonize
from setuptools import Extension, setup


extensions = cythonize(
    [Extension(
        "ahpy_setuptools_example",
        ["ahpy_setuptools_example.pyx", "ahpy_external.c"],
    )],
    runtime_backend="hpy-universal",
    compiler_directives={"language_level": 3},
)

setup(
    name="ahpy-setuptools-example",
    version="0.0.0",
    packages=[],
    py_modules=[],
    hpy_ext_modules=extensions,
)
