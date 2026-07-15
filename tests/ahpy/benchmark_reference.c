#include <hpy.h>


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


static HPyDef *ahpy_benchmark_defines[] = {
    &ahpy_identity,
    &ahpy_add,
    &ahpy_make_pair,
    &ahpy_get_value,
    &ahpy_call_zero,
    &ahpy_raise_value,
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
