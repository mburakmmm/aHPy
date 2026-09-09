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


HPyDef_METH(ahpy_keyword_count, "keyword_count", HPyFunc_KEYWORDS)
static HPy ahpy_keyword_count_impl(
    HPyContext *ctx,
    HPy self,
    const HPy *args,
    size_t nargs,
    HPy kwnames)
{
    HPy_ssize_t keyword_count = 0;

    (void)self;
    (void)args;
    (void)nargs;
    if (!HPy_IsNull(kwnames)) {
        keyword_count = HPy_Length(ctx, kwnames);
        if (keyword_count < 0) {
            return HPy_NULL;
        }
    }
    return HPyLong_FromSsize_t(ctx, keyword_count);
}


HPyDef_METH(ahpy_range_length, "range_length", HPyFunc_O)
static HPy ahpy_range_length_impl(HPyContext *ctx, HPy self, HPy arg)
{
    HPy builtins;
    HPy range_callable;
    HPy call_arg;
    HPy range_object;
    HPy_ssize_t length;

    (void)self;
    builtins = HPyImport_ImportModule(ctx, "builtins");
    if (HPy_IsNull(builtins)) {
        return HPy_NULL;
    }
    range_callable = HPy_GetAttr_s(ctx, builtins, "range");
    HPy_Close(ctx, builtins);
    if (HPy_IsNull(range_callable)) {
        return HPy_NULL;
    }
    call_arg = HPy_Dup(ctx, arg);
    if (HPy_IsNull(call_arg)) {
        HPy_Close(ctx, range_callable);
        return HPy_NULL;
    }
    range_object = HPy_Call(ctx, range_callable, &call_arg, 1, HPy_NULL);
    HPy_Close(ctx, call_arg);
    HPy_Close(ctx, range_callable);
    if (HPy_IsNull(range_object)) {
        return HPy_NULL;
    }
    length = HPy_Length(ctx, range_object);
    HPy_Close(ctx, range_object);
    if (length < 0) {
        return HPy_NULL;
    }
    return HPyLong_FromSsize_t(ctx, length);
}


static HPyDef *ahpy_defines[] = {
    &ahpy_answer,
    &ahpy_return_none,
    &ahpy_make_pair,
    &ahpy_keyword_count,
    &ahpy_range_length,
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
