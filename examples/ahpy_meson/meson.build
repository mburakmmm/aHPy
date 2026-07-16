project(
  'ahpy_meson_example',
  'c',
  version: '0.0.0',
  meson_version: '>=1.11.2',
  default_options: ['c_std=c99'],
)

subdir('ahpy_config')
if ahpy_abi != 'universal'
  error('aHPy Meson example requires the Universal ABI')
endif
if ahpy_module_name != 'ahpy_meson_example'
  error('aHPy contract module name does not match this target')
endif

hpy_c_args = []
foreach definition : ahpy_definitions
  hpy_c_args += '-D' + definition
endforeach
foreach include_dir : ahpy_include_dirs
  hpy_c_args += '-I' + include_dir
endforeach

module_kwargs = {
  'c_args': hpy_c_args,
  'link_args': ahpy_runtime_library == '' ? [] : [ahpy_runtime_library],
  'name_prefix': '',
  'name_suffix': ahpy_name_suffix,
  'install': false,
}
if ahpy_windows
  module_kwargs += {'vs_module_defs': files('exports.def')}
endif

shared_module(
  'ahpy_meson_example',
  ['ahpy_meson_example.c'] + ahpy_runtime_sources,
  kwargs: module_kwargs,
)
