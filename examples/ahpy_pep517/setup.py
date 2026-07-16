from setuptools import Extension, setup
from Cython.Build import cythonize


extensions = cythonize(
    [Extension("ahpy_pep517_example", ["ahpy_pep517_example.pyx"])],
    compiler_directives={"language_level": 3},
    runtime_backend="hpy-universal",
)

setup(
    name="ahpy-pep517-example",
    version="0.0.0",
    hpy_ext_modules=extensions,
)
