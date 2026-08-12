from Cython.Build import cythonize
from setuptools import Extension, setup


extensions = cythonize(
    [Extension("frozenlist_port", ["frozenlist_port.pyx"])],
    runtime_backend="hpy-universal",
    compiler_directives={"language_level": 3},
)

setup(
    name="ahpy-frozenlist-pilot",
    version="2.0.0",
    packages=[],
    py_modules=[],
    hpy_ext_modules=extensions,
)
