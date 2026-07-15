#include <hpy.h>


HPyDef_METH(ahpy_answer, "answer", HPyFunc_NOARGS)
static HPy ahpy_answer_impl(HPyContext *ctx, HPy self)
{
    return HPyLong_FromLong(ctx, 42);
}


HPyDef_METH(ahpy_return_none, "return_none", HPyFunc_NOARGS)
static HPy ahpy_return_none_impl(HPyContext *ctx, HPy self)
{
    return HPy_Dup(ctx, ctx->h_None);
}


HPyDef_METH(ahpy_make_pair, "make_pair", HPyFunc_NOARGS)
static HPy ahpy_make_pair_impl(HPyContext *ctx, HPy self)
{
    HPyListBuilder builder = HPyListBuilder_New(ctx, 2);
    HPy first = HPyLong_FromLong(ctx, 1);
    HPy second;
    HPy result;

    if (HPy_IsNull(first)) {
        HPyListBuilder_Cancel(ctx, builder);
        return HPy_NULL;
    }
    second = HPyLong_FromLong(ctx, 2);
    if (HPy_IsNull(second)) {
        HPy_Close(ctx, first);
        HPyListBuilder_Cancel(ctx, builder);
        return HPy_NULL;
    }

    HPyListBuilder_Set(ctx, builder, 0, first);
    HPyListBuilder_Set(ctx, builder, 1, second);
    HPy_Close(ctx, second);
    HPy_Close(ctx, first);
    result = HPyListBuilder_Build(ctx, builder);
    return result;
}


static HPyDef *ahpy_defines[] = {
    &ahpy_answer,
    &ahpy_return_none,
    &ahpy_make_pair,
    NULL,
};


static HPyModuleDef ahpy_module = {
    .doc = "aHPy Universal ABI reference module",
    .size = 0,
    .legacy_methods = NULL,
    .defines = ahpy_defines,
    .globals = NULL,
};


HPy_MODINIT(ahpy_minimal, ahpy_module)
