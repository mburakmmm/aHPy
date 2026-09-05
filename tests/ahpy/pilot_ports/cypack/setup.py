from Cython.Build import cythonize
from setuptools import Extension, setup

from ahpy_hpy_compat import install_hpy_universal_loader_compat


install_hpy_universal_loader_compat()


extensions = cythonize(
    [
        Extension("cypack.utils", ["src/cypack/utils.pyx"]),
        Extension("cypack.answer", ["src/cypack/answer.pyx"]),
        Extension("cypack.fibonacci", ["src/cypack/fibonacci.pyx"]),
    ],
    runtime_backend="hpy-universal",
    compiler_directives={"language_level": 3},
)

setup(
    name="ahpy-cypack-pilot",
    version="0.1.7",
    packages=["cypack"],
    package_dir={"": "src"},
    package_data={"cypack": ["data/zen.txt"]},
    hpy_ext_modules=extensions,
)
