#include <hpy.h>


typedef struct {
    HPyField value;
} ReproducerObject;

HPyType_HELPERS(ReproducerObject)


HPyDef_SLOT(reproducer_new, HPy_tp_new)
static HPy reproducer_new_impl(
    HPyContext *ctx,
    HPy type,
    const HPy *args,
    HPy_ssize_t nargs,
    HPy kw)
{
    ReproducerObject *data;
    HPy self;

    if (nargs != 1 || !HPy_IsNull(kw)) {
        HPyErr_SetString(ctx, ctx->h_TypeError, "Reproducer expects one value");
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


HPyDef_METH(reproducer_identity, "identity", HPyFunc_NOARGS)
static HPy reproducer_identity_impl(HPyContext *ctx, HPy self)
{
    ReproducerObject *data = ReproducerObject_AsStruct(ctx, self);
    return HPyField_Load(ctx, self, data->value);
}


static int reproducer_traverse_impl(
    void *object,
    HPyFunc_visitproc visit,
    void *arg)
{
    ReproducerObject *data = (ReproducerObject *)object;
    HPy_VISIT(&data->value);
    return 0;
}
HPyDef_SLOT(reproducer_traverse, HPy_tp_traverse)


static HPyDef *reproducer_type_defines[] = {
    &reproducer_new,
    &reproducer_identity,
    &reproducer_traverse,
    NULL,
};


static HPyType_Spec reproducer_type_spec = {
    .name = "hpy_dev_type_reproducer.Reproducer",
    .basicsize = sizeof(ReproducerObject),
    .itemsize = 0,
    .flags = HPy_TPFLAGS_DEFAULT | HPy_TPFLAGS_HAVE_GC,
    .builtin_shape = SHAPE(ReproducerObject),
    .legacy_slots = NULL,
    .defines = reproducer_type_defines,
    .doc = NULL,
};


HPyDef_SLOT(reproducer_exec, HPy_mod_exec)
static int reproducer_exec_impl(HPyContext *ctx, HPy module)
{
    HPy type = HPyType_FromSpec(ctx, &reproducer_type_spec, NULL);
    int status;

    if (HPy_IsNull(type)) {
        return -1;
    }
    status = HPy_SetAttr_s(ctx, module, "Reproducer", type);
    HPy_Close(ctx, type);
    return status;
}


static HPyDef *reproducer_module_defines[] = {
    &reproducer_exec,
    NULL,
};


static HPyModuleDef reproducer_module = {
    .doc = "Minimal handwritten HPy heap-type reproducer",
    .size = 0,
    .legacy_methods = NULL,
    .defines = reproducer_module_defines,
    .globals = NULL,
};


HPy_MODINIT(hpy_dev_type_reproducer, reproducer_module)
