from pathlib import Path
import sys

from ahpy_build_config import create_contract, probe_toolchain, render_cmake


output, module_name = sys.argv[1:]
contract = create_contract(probe_toolchain(sys.executable), module_name)
Path(output).write_text(render_cmake(contract), encoding="utf8")
