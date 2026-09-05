Select alternate complete-module emission through an immutable
``RuntimeModuleEmitter`` contract. ``ModuleNode`` retains the established
CPython writer as its default and no longer hard-codes the Universal backend or
constructs its complete writer; the selected Universal callback owns
validation, rendering and the output-file transaction. Invalid emitter
contracts fail closed.
