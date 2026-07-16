# aHPy CMake example

Generate `ahpy_cmake_example.c` with the strict `hpy-universal` backend, then
emit a selected-interpreter contract:

```console
python Tools/ahpy/build_system_config.py --python /path/to/python \
  --module ahpy_cmake_example --format cmake --output /tmp/ahpy-config.cmake
cmake -S examples/ahpy_cmake -B /tmp/ahpy-cmake-build \
  -DAHPY_CONFIG=/tmp/ahpy-config.cmake
cmake --build /tmp/ahpy-cmake-build
```

The maintained integration tool performs generation, configuration, build,
source/binary audits, and normal/Debug public-loader execution in a temporary
copy. Never reuse a contract with another Python/HPy toolchain.
