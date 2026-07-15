from pathlib import Path

from setuptools import Extension, setup


HERE = Path(__file__).resolve().parent


def main():
    setup(
        name="ahpy-minimal-reference",
        version="0.0.0",
        packages=[],
        py_modules=[],
        hpy_ext_modules=[
            Extension("ahpy_minimal", [str(HERE / "minimal_universal.c")]),
        ],
    )


if __name__ == "__main__":
    main()
