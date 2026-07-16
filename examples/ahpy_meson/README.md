# aHPy Meson example

Generate `ahpy_meson_example.c` with the strict `hpy-universal` backend, then
write the selected interpreter contract into the copied source tree:

```console
python Tools/ahpy/build_system_config.py --python /path/to/python \
  --module ahpy_meson_example --format meson \
  --output examples/ahpy_meson/ahpy_config/meson.build
meson setup /tmp/ahpy-meson-build examples/ahpy_meson
meson compile -C /tmp/ahpy-meson-build
```

The generated `ahpy_config/meson.build` is toolchain-specific and must not be
committed. The maintained integration performs the complete temporary build,
ABI audits, and normal/Debug public-loader execution.
