#!/usr/bin/env python3
"""Inject deterministic HPy allocation failures into generated code."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from artifact_utils import require_universal_binary
from test_generated_hpy import run, verify_binary_boundary, verify_source_boundary


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "tests" / "ahpy" / "fault_injection.pyx"
HELPER_HEADER = ROOT / "tests" / "ahpy" / "fault_injection_helpers.h"
MODULE_NAME = "fault_injection"

RUNTIME_CASES = (
    ("long", 3),
    ("list-builder-build", 3),
    ("tuple-builder-build", 3),
    ("dict-set-item", 3),
    ("call", 4),
    ("call-tuple-dict", 1),
    ("call-method", 1),
    ("get-attribute", 3),
    ("get-item", 3),
    ("set-attribute", 1),
    ("delete-attribute", 1),
    ("set-item", 1),
    ("delete-item", 1),
    ("buffer-dup", 2),
)

INJECTION = r'''
#include <stdlib.h>
#include <string.h>

static int __pyx_hpy_fault_selected(
        const char *operation, long *call_index) {
    const char *selected = getenv("AHPY_FAIL_OPERATION");
    const char *target_text = getenv("AHPY_FAIL_AT");
    if (selected != NULL && target_text != NULL &&
            strcmp(selected, operation) == 0) {
        char *end = NULL;
        long target = strtol(target_text, &end, 10);
        if (end != target_text && *end == '\0') {
            return (*call_index)++ == target;
        }
    }
    return 0;
}

static HPy __pyx_hpy_real_long_from_long_long(
        HPyContext *ctx, long long value) {
    return HPyLong_FromLongLong(ctx, value);
}

static HPy __pyx_hpy_fault_long_from_long_long(
        HPyContext *ctx, long long value) {
    static long call_index = 0;
    if (__pyx_hpy_fault_selected("long", &call_index))
        return HPyErr_NoMemory(ctx);
    return __pyx_hpy_real_long_from_long_long(ctx, value);
}

static HPy __pyx_hpy_real_list_builder_build(
        HPyContext *ctx, HPyListBuilder builder) {
    return HPyListBuilder_Build(ctx, builder);
}

static HPy __pyx_hpy_fault_list_builder_build(
        HPyContext *ctx, HPyListBuilder builder) {
    static long call_index = 0;
    if (__pyx_hpy_fault_selected("list-builder-build", &call_index)) {
        HPyListBuilder_Cancel(ctx, builder);
        return HPyErr_NoMemory(ctx);
    }
    return __pyx_hpy_real_list_builder_build(ctx, builder);
}

static HPy __pyx_hpy_real_tuple_builder_build(
        HPyContext *ctx, HPyTupleBuilder builder) {
    return HPyTupleBuilder_Build(ctx, builder);
}

static HPy __pyx_hpy_fault_tuple_builder_build(
        HPyContext *ctx, HPyTupleBuilder builder) {
    static long call_index = 0;
    if (__pyx_hpy_fault_selected("tuple-builder-build", &call_index)) {
        HPyTupleBuilder_Cancel(ctx, builder);
        return HPyErr_NoMemory(ctx);
    }
    return __pyx_hpy_real_tuple_builder_build(ctx, builder);
}

static int __pyx_hpy_real_set_item(
        HPyContext *ctx, HPy obj, HPy key, HPy value) {
    return HPy_SetItem(ctx, obj, key, value);
}

static int __pyx_hpy_fault_set_item(
        HPyContext *ctx, HPy obj, HPy key, HPy value) {
    static long dict_call_index = 0;
    static long item_call_index = 0;
    if (__pyx_hpy_fault_selected("dict-set-item", &dict_call_index) ||
            __pyx_hpy_fault_selected("set-item", &item_call_index)) {
        HPyErr_NoMemory(ctx);
        return -1;
    }
    return __pyx_hpy_real_set_item(ctx, obj, key, value);
}

static HPy __pyx_hpy_real_call(
        HPyContext *ctx, HPy callable, const HPy *args,
        size_t nargs, HPy kwnames) {
    return HPy_Call(ctx, callable, args, nargs, kwnames);
}

static HPy __pyx_hpy_fault_call(
        HPyContext *ctx, HPy callable, const HPy *args,
        size_t nargs, HPy kwnames) {
    static long call_index = 0;
    if (__pyx_hpy_fault_selected("call", &call_index))
        return HPyErr_NoMemory(ctx);
    return __pyx_hpy_real_call(ctx, callable, args, nargs, kwnames);
}

static HPy __pyx_hpy_real_call_tuple_dict(
        HPyContext *ctx, HPy callable, HPy args, HPy kw) {
    return HPy_CallTupleDict(ctx, callable, args, kw);
}

static HPy __pyx_hpy_fault_call_tuple_dict(
        HPyContext *ctx, HPy callable, HPy args, HPy kw) {
    static long call_index = 0;
    if (__pyx_hpy_fault_selected("call-tuple-dict", &call_index))
        return HPyErr_NoMemory(ctx);
    return __pyx_hpy_real_call_tuple_dict(ctx, callable, args, kw);
}

static HPy __pyx_hpy_real_call_method(
        HPyContext *ctx, HPy name, const HPy *args,
        size_t nargs, HPy kwnames) {
    return HPy_CallMethod(ctx, name, args, nargs, kwnames);
}

static HPy __pyx_hpy_fault_call_method(
        HPyContext *ctx, HPy name, const HPy *args,
        size_t nargs, HPy kwnames) {
    static long call_index = 0;
    if (__pyx_hpy_fault_selected("call-method", &call_index))
        return HPyErr_NoMemory(ctx);
    return __pyx_hpy_real_call_method(ctx, name, args, nargs, kwnames);
}

static HPy __pyx_hpy_real_get_attr_s(
        HPyContext *ctx, HPy obj, const char *name) {
    return HPy_GetAttr_s(ctx, obj, name);
}

static HPy __pyx_hpy_fault_get_attr_s(
        HPyContext *ctx, HPy obj, const char *name) {
    static long call_index = 0;
    if (__pyx_hpy_fault_selected("get-attribute", &call_index))
        return HPyErr_NoMemory(ctx);
    return __pyx_hpy_real_get_attr_s(ctx, obj, name);
}

static HPy __pyx_hpy_real_get_item(
        HPyContext *ctx, HPy obj, HPy key) {
    return HPy_GetItem(ctx, obj, key);
}

static HPy __pyx_hpy_fault_get_item(
        HPyContext *ctx, HPy obj, HPy key) {
    static long call_index = 0;
    if (__pyx_hpy_fault_selected("get-item", &call_index))
        return HPyErr_NoMemory(ctx);
    return __pyx_hpy_real_get_item(ctx, obj, key);
}

static HPy __pyx_hpy_real_dup(HPyContext *ctx, HPy value) {
    return HPy_Dup(ctx, value);
}

static HPy __pyx_hpy_fault_dup(HPyContext *ctx, HPy value) {
    static long call_index = 0;
    if (__pyx_hpy_fault_selected("buffer-dup", &call_index))
        return HPyErr_NoMemory(ctx);
    return __pyx_hpy_real_dup(ctx, value);
}

static HPy __pyx_hpy_real_type_from_spec(
        HPyContext *ctx, HPyType_Spec *spec, HPyType_SpecParam *params) {
    return HPyType_FromSpec(ctx, spec, params);
}

static HPy __pyx_hpy_fault_type_from_spec(
        HPyContext *ctx, HPyType_Spec *spec, HPyType_SpecParam *params) {
    static long call_index = 0;
    if (__pyx_hpy_fault_selected("type-from-spec", &call_index))
        return HPyErr_NoMemory(ctx);
    return __pyx_hpy_real_type_from_spec(ctx, spec, params);
}

static int __pyx_hpy_real_set_attr_s(
        HPyContext *ctx, HPy obj, const char *name, HPy value) {
    return HPy_SetAttr_s(ctx, obj, name, value);
}

static int __pyx_hpy_fault_set_attr_s(
        HPyContext *ctx, HPy obj, const char *name, HPy value) {
    static long module_call_index = 0;
    static long runtime_call_index = 0;
    if (__pyx_hpy_fault_selected(
            "module-set-attribute", &module_call_index) ||
            __pyx_hpy_fault_selected(
                "set-attribute", &runtime_call_index)) {
        HPyErr_NoMemory(ctx);
        return -1;
    }
    return __pyx_hpy_real_set_attr_s(ctx, obj, name, value);
}

static int __pyx_hpy_real_del_attr_s(
        HPyContext *ctx, HPy obj, const char *name) {
    return HPy_DelAttr_s(ctx, obj, name);
}

static int __pyx_hpy_fault_del_attr_s(
        HPyContext *ctx, HPy obj, const char *name) {
    static long call_index = 0;
    if (__pyx_hpy_fault_selected("delete-attribute", &call_index)) {
        HPyErr_NoMemory(ctx);
        return -1;
    }
    return __pyx_hpy_real_del_attr_s(ctx, obj, name);
}

static int __pyx_hpy_real_del_item(
        HPyContext *ctx, HPy obj, HPy key) {
    return HPy_DelItem(ctx, obj, key);
}

static int __pyx_hpy_fault_del_item(
        HPyContext *ctx, HPy obj, HPy key) {
    static long call_index = 0;
    if (__pyx_hpy_fault_selected("delete-item", &call_index)) {
        HPyErr_NoMemory(ctx);
        return -1;
    }
    return __pyx_hpy_real_del_item(ctx, obj, key);
}

#define HPyLong_FromLongLong(ctx, value) \
    __pyx_hpy_fault_long_from_long_long((ctx), (value))
#define HPyListBuilder_Build(ctx, builder) \
    __pyx_hpy_fault_list_builder_build((ctx), (builder))
#define HPyTupleBuilder_Build(ctx, builder) \
    __pyx_hpy_fault_tuple_builder_build((ctx), (builder))
#define HPy_SetItem(ctx, obj, key, value) \
    __pyx_hpy_fault_set_item((ctx), (obj), (key), (value))
#define HPy_Call(ctx, callable, args, nargs, kwnames) \
    __pyx_hpy_fault_call((ctx), (callable), (args), (nargs), (kwnames))
#define HPy_CallTupleDict(ctx, callable, args, kw) \
    __pyx_hpy_fault_call_tuple_dict((ctx), (callable), (args), (kw))
#define HPy_CallMethod(ctx, name, args, nargs, kwnames) \
    __pyx_hpy_fault_call_method((ctx), (name), (args), (nargs), (kwnames))
#define HPy_GetAttr_s(ctx, obj, name) \
    __pyx_hpy_fault_get_attr_s((ctx), (obj), (name))
#define HPy_GetItem(ctx, obj, key) \
    __pyx_hpy_fault_get_item((ctx), (obj), (key))
#define HPy_Dup(ctx, value) \
    __pyx_hpy_fault_dup((ctx), (value))
#define HPyType_FromSpec(ctx, spec, params) \
    __pyx_hpy_fault_type_from_spec((ctx), (spec), (params))
#define HPy_SetAttr_s(ctx, obj, name, value) \
    __pyx_hpy_fault_set_attr_s((ctx), (obj), (name), (value))
#define HPy_DelAttr_s(ctx, obj, name) \
    __pyx_hpy_fault_del_attr_s((ctx), (obj), (name))
#define HPy_DelItem(ctx, obj, key) \
    __pyx_hpy_fault_del_item((ctx), (obj), (key))
'''


def inject_failure_wrapper(generated):
    source = generated.read_text(encoding="utf8")
    marker = "#include <hpy.h>\n"
    if source.count(marker) != 1:
        raise AssertionError("expected one hpy.h include injection point")
    generated.write_text(
        source.replace(marker, marker + INJECTION + "\n", 1),
        encoding="utf8",
    )


def module_exec_call_count(source, operation):
    start_marker = "static int __pyx_hpy_mod_exec_impl(HPyContext *ctx, HPy m)"
    end_marker = "\nstatic HPyDef *__pyx_hpy_defines[]"
    if source.count(start_marker) != 1:
        raise AssertionError("expected one generated module exec implementation")
    start = source.index(start_marker)
    try:
        end = source.index(end_marker, start)
    except ValueError as exc:
        raise AssertionError("generated module exec end marker is missing") from exc
    count = source[start:end].count(operation)
    if count <= 0:
        raise AssertionError(
            "generated module exec does not call %s" % operation)
    return count


def _runtime_program(debug, operation, target, should_fail):
    prefix = ""
    suffix = ""
    if debug:
        prefix = (
            "from hpy.debug import LeakDetector\n"
            "detector = LeakDetector()\n"
            "detector.start()\n"
        )
        suffix = "detector.stop()\n"
    return (
        "import os\n"
        "from types import SimpleNamespace\n"
        "import fault_injection\n" +
        prefix +
        "operation = %r\n" % operation +
        "target = %d\n" % target +
        "os.environ['AHPY_FAIL_OPERATION'] = operation\n"
        "os.environ['AHPY_FAIL_AT'] = str(target)\n"
        "marker = object()\n"
        "def accept(*args, **kwargs): return marker\n"
        "operations = {\n"
        "    'long': lambda: fault_injection.build_values(),\n"
        "    'list-builder-build': lambda: fault_injection.build_nested_lists(),\n"
        "    'tuple-builder-build': lambda: fault_injection.build_nested_tuples(marker),\n"
        "    'dict-set-item': lambda: fault_injection.build_dictionary(marker),\n"
        "    'call': lambda: fault_injection.call_variants(accept, marker),\n"
        "    'call-tuple-dict': lambda: fault_injection.call_expanded(accept, (marker,), {'named': marker}),\n"
        "    'call-method': lambda: fault_injection.call_method_variants('hpy'),\n"
        "    'get-attribute': lambda: fault_injection.read_attributes(SimpleNamespace(first=marker, second=marker, third=marker)),\n"
        "    'get-item': lambda: fault_injection.read_items({'first': marker, 'second': marker, 'third': marker}),\n"
        "    'set-attribute': lambda: fault_injection.write_attribute(SimpleNamespace(), marker),\n"
        "    'delete-attribute': lambda: fault_injection.delete_attribute(SimpleNamespace(answer=marker)),\n"
        "    'set-item': lambda: fault_injection.write_item({}, marker),\n"
        "    'delete-item': lambda: fault_injection.delete_item({'answer': marker}),\n"
        "    'buffer-dup': lambda: (memoryview(fault_injection.FaultBuffer()), "
        "memoryview(fault_injection.FaultArrayBuffer())),\n"
        "}\n"
        "if %r:\n" % should_fail +
        "    try:\n"
        "        operations[operation]()\n"
        "    except MemoryError:\n"
        "        pass\n"
        "    else:\n"
        "        raise AssertionError('injected operation did not fail: %s[%d]' % (operation, target))\n"
        "else:\n"
        "    result = operations[operation]()\n"
        "    if operation == 'long':\n"
        "        assert result == [101, 102, 103]\n"
        "    elif operation == 'list-builder-build':\n"
        "        assert result == [[101], [102, 103]]\n"
        "    elif operation == 'tuple-builder-build':\n"
        "        assert result == ((marker,), (marker, marker))\n"
        "    elif operation == 'dict-set-item':\n"
        "        assert list(result) == ['first', 'second', 'third']\n"
        "        assert all(value is marker for value in result.values())\n"
        "    elif operation in ('call', 'get-attribute', 'get-item'):\n"
        "        assert result == [marker] * (4 if operation == 'call' else 3)\n"
        "    elif operation in ('call-tuple-dict', 'set-attribute', 'set-item'):\n"
        "        assert result is marker\n"
        "    elif operation == 'call-method':\n"
        "        assert result == 'HPY'\n"
        "    elif operation == 'buffer-dup':\n"
        "        assert [view.format for view in result] == ['l', 'l']\n"
        "        assert [view.shape for view in result] == [(1,), (4,)]\n"
        "        for view in result: view.release()\n"
        "    else:\n"
        "        assert result is None\n" +
        suffix
    )


def _import_fault_program(debug, operation, target, should_fail):
    prefix = ""
    suffix = ""
    if debug:
        prefix = (
            "from hpy.debug import LeakDetector\n"
            "detector = LeakDetector()\n"
            "detector.start()\n"
        )
        suffix = "detector.stop()\n"
    return (
        "import gc, importlib, os, sys\n" +
        prefix +
        "os.environ['AHPY_FAIL_OPERATION'] = %r\n" % operation +
        "os.environ['AHPY_FAIL_AT'] = %r\n" % str(target) +
        "if %r:\n" % should_fail +
        "    try:\n"
        "        importlib.import_module('fault_injection')\n"
        "    except MemoryError:\n"
        "        pass\n"
        "    except BaseException as error:\n"
        "        raise AssertionError('wrong import error for %s[%d]: %%r' %% error) from error\n" % (
            operation, target) +
        "    else:\n"
        "        raise AssertionError('injected module operation did not fail: %s[%d]')\n" % (
            operation, target) +
        "    assert 'fault_injection' not in sys.modules\n"
        "    gc.collect()\n"
        "else:\n"
        "    module = importlib.import_module('fault_injection')\n"
        "    assert module.fault_types() == (module.FaultType, module.FaultTypeSecond, module.FaultTypeThird)\n" +
        suffix
    )


def build_and_run(python):
    with TemporaryDirectory(prefix="ahpy-fault-injection-") as temp_dir:
        temp = Path(temp_dir)
        generated = temp / (MODULE_NAME + ".c")
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(ROOT)
        run([
            python,
            "-m", "cython",
            "--runtime-backend=hpy-universal",
            "-3",
            "-o", str(generated),
            str(SOURCE),
        ], cwd=ROOT, env=environment)
        generated_source = generated.read_text(encoding="utf8")
        type_creation_count = module_exec_call_count(
            generated_source, "HPyType_FromSpec(ctx,")
        publication_count = module_exec_call_count(
            generated_source, "HPy_SetAttr_s(ctx,")
        isolated_case_count = 2 * (
            sum(call_count + 1 for _, call_count in RUNTIME_CASES)
            + type_creation_count + 1
            + publication_count + 1
        )
        verify_source_boundary(
            generated,
            required=(
                "#include <hpy.h>",
                "HPyLong_FromLongLong",
                "HPyListBuilder_New",
                "HPyListBuilder_Cancel",
                "HPyTupleBuilder_New",
                "HPyTupleBuilder_Cancel",
                "HPy_SetItem",
                "HPy_DelItem",
                "HPy_Call",
                "HPy_CallTupleDict",
                "HPy_CallMethod",
                "HPy_GetAttr_s",
                "HPy_DelAttr_s",
                "HPy_GetItem",
                "HPy_Dup",
                "HPy_buffer",
                "HPy_bf_getbuffer",
                "HPyType_FromSpec",
                "HPy_SetAttr_s",
                "HPy_MODINIT",
            ),
        )
        inject_failure_wrapper(generated)
        shutil.copy2(HELPER_HEADER, temp / HELPER_HEADER.name)

        setup = temp / "setup.py"
        setup.write_text(
            "from setuptools import Extension, setup\n"
            "setup(name='ahpy-fault-injection', version='0.0.0', "
            "packages=[], py_modules=[], "
            "hpy_ext_modules=[Extension('fault_injection', "
            "['fault_injection.c'], "
            "include_dirs=[%r])])\n" % str(temp),
            encoding="utf8",
        )
        build_root = temp / "build"
        run([
            python,
            str(setup),
            "--hpy-abi=universal",
            "build",
            "--build-base", str(build_root),
        ], cwd=temp, env=environment, stdout=subprocess.DEVNULL)
        binary = require_universal_binary(build_root, MODULE_NAME)
        verify_binary_boundary(binary)

        runtime_environment = environment.copy()
        runtime_environment["PYTHONPATH"] = str(binary.parent)
        for debug in (False, True):
            mode_environment = runtime_environment.copy()
            if debug:
                mode_environment["HPY"] = "debug"
            for operation, call_count in RUNTIME_CASES:
                for target in range(call_count + 1):
                    should_fail = target < call_count
                    case_environment = mode_environment.copy()
                    run([
                        python, "-c", _runtime_program(
                            debug, operation, target, should_fail),
                    ], cwd=temp, env=case_environment)
            import_operations = (
                ("type-from-spec", type_creation_count),
                ("module-set-attribute", publication_count),
            )
            for operation, call_count in import_operations:
                for target in range(call_count + 1):
                    run([
                        python, "-c", _import_fault_program(
                            debug, operation, target,
                            should_fail=target < call_count),
                    ], cwd=temp, env=mode_environment)
        return isolated_case_count


class FaultInjectionToolTest(unittest.TestCase):
    def test_wrapper_is_inserted_after_hpy_header_once(self):
        with TemporaryDirectory() as temp:
            generated = Path(temp) / "module.c"
            generated.write_text(
                "#include <hpy.h>\nint value;\n", encoding="utf8")
            inject_failure_wrapper(generated)
            output = generated.read_text(encoding="utf8")
        self.assertEqual(output.count("#define HPyLong_FromLongLong"), 1)
        self.assertEqual(output.count("#define HPy_Dup"), 1)
        self.assertLess(
            output.index("#include <hpy.h>"),
            output.index("#define HPyLong_FromLongLong"),
        )

    def test_module_exec_call_count_is_scoped(self):
        source = (
            "HPy_SetAttr_s(ctx, outside, \"before\", value);\n"
            "static int __pyx_hpy_mod_exec_impl(HPyContext *ctx, HPy m)\n"
            "{\n"
            "    HPy_SetAttr_s(ctx, m, \"first\", value);\n"
            "    HPy_SetAttr_s(ctx, type, \"second\", value);\n"
            "}\n"
            "static HPyDef *__pyx_hpy_defines[] = {NULL};\n"
            "HPy_SetAttr_s(ctx, outside, \"after\", value);\n"
        )
        self.assertEqual(
            module_exec_call_count(source, "HPy_SetAttr_s(ctx,"), 2)

    def test_runtime_case_counts_cover_every_boundary(self):
        self.assertEqual(len({name for name, _ in RUNTIME_CASES}), 14)
        self.assertTrue(all(call_count > 0 for _, call_count in RUNTIME_CASES))
        self.assertEqual(
            sum(call_count + 1 for _, call_count in RUNTIME_CASES), 44)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--python", default=sys.executable)
    args = parser.parse_args()
    python_path = Path(args.python)
    if python_path.exists():
        python = os.path.abspath(args.python)
    else:
        python = shutil.which(args.python)
        if python is None:
            parser.error("Python interpreter not found: %s" % args.python)
    isolated_case_count = build_and_run(python)
    print(
        "Generated Universal HPy module: %d isolated API/allocation fault "
        "injection cases passed" % isolated_case_count)


if __name__ == "__main__":
    main()
