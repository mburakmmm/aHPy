#include <hpy.h>

#include "benchmark_external.h"


typedef struct {
    HPyField value;
} AhpyBenchmarkBoxObject;

HPyType_HELPERS(AhpyBenchmarkBoxObject)


HPyDef_SLOT(ahpy_benchmark_box_new, HPy_tp_new)
static HPy ahpy_benchmark_box_new_impl(HPyContext *ctx, HPy type,
                                        const HPy *args, HPy_ssize_t nargs,
                                        HPy kw)
{
    AhpyBenchmarkBoxObject *data;
    HPy self;

    if (nargs != 1 || !HPy_IsNull(kw)) {
        HPyErr_SetString(ctx, ctx->h_TypeError,
                         "BenchmarkBox expects one positional argument");
        return HPy_NULL;
    }
    self = HPy_New(ctx, type, &data);
    if (HPy_IsNull(self)) {
        return HPy_NULL;
    }
    data->value = HPyField_NULL;
    HPyField_Store(ctx, self, &data->value, args[0]);
    return self;
}


HPyDef_METH(ahpy_benchmark_box_identity, "identity", HPyFunc_NOARGS)
static HPy ahpy_benchmark_box_identity_impl(HPyContext *ctx, HPy self)
{
    AhpyBenchmarkBoxObject *data =
        AhpyBenchmarkBoxObject_AsStruct(ctx, self);
    return HPyField_Load(ctx, self, data->value);
}


static int ahpy_benchmark_box_traverse_impl(
    void *object, HPyFunc_visitproc visit, void *arg)
{
    AhpyBenchmarkBoxObject *data = (AhpyBenchmarkBoxObject *)object;
    HPy_VISIT(&data->value);
    return 0;
}
HPyDef_SLOT(ahpy_benchmark_box_traverse, HPy_tp_traverse)


static HPyDef *ahpy_benchmark_box_defines[] = {
    &ahpy_benchmark_box_new,
    &ahpy_benchmark_box_identity,
    &ahpy_benchmark_box_traverse,
    NULL,
};


static HPyType_Spec ahpy_benchmark_box_spec = {
    .name = "ahpy_benchmark_reference.BenchmarkBox",
    .basicsize = sizeof(AhpyBenchmarkBoxObject),
    .itemsize = 0,
    .flags = HPy_TPFLAGS_DEFAULT | HPy_TPFLAGS_BASETYPE | HPy_TPFLAGS_HAVE_GC,
    .builtin_shape = SHAPE(AhpyBenchmarkBoxObject),
    .legacy_slots = NULL,
    .defines = ahpy_benchmark_box_defines,
    .doc = NULL,
};


static int ahpy_require_nargs(HPyContext *ctx, size_t nargs, size_t expected)
{
    if (nargs == expected) {
        return 1;
    }
    HPyErr_SetString(ctx, ctx->h_TypeError, "wrong number of benchmark arguments");
    return 0;
}


HPyDef_METH(ahpy_identity, "identity", HPyFunc_O)
static HPy ahpy_identity_impl(HPyContext *ctx, HPy self, HPy value)
{
    return HPy_Dup(ctx, value);
}


HPyDef_METH(ahpy_add, "add", HPyFunc_VARARGS)
static HPy ahpy_add_impl(HPyContext *ctx, HPy self,
                         const HPy *args, size_t nargs)
{
    if (!ahpy_require_nargs(ctx, nargs, 2)) {
        return HPy_NULL;
    }
    return HPy_Add(ctx, args[0], args[1]);
}


HPyDef_METH(ahpy_make_pair, "make_pair", HPyFunc_VARARGS)
static HPy ahpy_make_pair_impl(HPyContext *ctx, HPy self,
                               const HPy *args, size_t nargs)
{
    HPyListBuilder builder;

    if (!ahpy_require_nargs(ctx, nargs, 2)) {
        return HPy_NULL;
    }
    builder = HPyListBuilder_New(ctx, 2);
    HPyListBuilder_Set(ctx, builder, 0, args[0]);
    HPyListBuilder_Set(ctx, builder, 1, args[1]);
    return HPyListBuilder_Build(ctx, builder);
}


HPyDef_METH(ahpy_get_value, "get_value", HPyFunc_O)
static HPy ahpy_get_value_impl(HPyContext *ctx, HPy self, HPy value)
{
    return HPy_GetAttr_s(ctx, value, "value");
}


HPyDef_METH(ahpy_call_zero, "call_zero", HPyFunc_O)
static HPy ahpy_call_zero_impl(HPyContext *ctx, HPy self, HPy callable_object)
{
    return HPy_Call(ctx, callable_object, NULL, 0, HPy_NULL);
}


HPyDef_METH(ahpy_raise_value, "raise_value", HPyFunc_NOARGS)
static HPy ahpy_raise_value_impl(HPyContext *ctx, HPy self)
{
    HPyErr_SetString(ctx, ctx->h_ValueError, "aHPy benchmark");
    return HPy_NULL;
}


HPyDef_METH(ahpy_external_add, "external_add", HPyFunc_NOARGS)
static HPy ahpy_external_add_impl(HPyContext *ctx, HPy self)
{
    return HPyLong_FromLongLong(
        ctx, ahpy_benchmark_external_add(20, 22));
}


HPyDef_SLOT(ahpy_benchmark_exec, HPy_mod_exec)
static int ahpy_benchmark_exec_impl(HPyContext *ctx, HPy module)
{
    HPy box_type = HPyType_FromSpec(ctx, &ahpy_benchmark_box_spec, NULL);
    int status;

    if (HPy_IsNull(box_type)) {
        return -1;
    }
    status = HPy_SetAttr_s(ctx, module, "BenchmarkBox", box_type);
    HPy_Close(ctx, box_type);
    return status;
}


static HPyDef *ahpy_benchmark_defines[] = {
    &ahpy_identity,
    &ahpy_add,
    &ahpy_make_pair,
    &ahpy_get_value,
    &ahpy_call_zero,
    &ahpy_raise_value,
    &ahpy_external_add,
    &ahpy_benchmark_exec,
    NULL,
};


static HPyModuleDef ahpy_benchmark_module = {
    .doc = "Handwritten Universal HPy performance reference",
    .size = 0,
    .legacy_methods = NULL,
    .defines = ahpy_benchmark_defines,
    .globals = NULL,
};


HPy_MODINIT(ahpy_benchmark_reference, ahpy_benchmark_module)
