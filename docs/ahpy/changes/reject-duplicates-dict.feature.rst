``DictNode(reject_duplicates=True)`` and flattened keyword/``**`` merges emit
``TypeError: function() got multiple values for keyword argument`` through the
shared ``HPy_Contains`` check before ``HPy_SetItem``. Unique literal keyword
names skip the runtime scan; known or dynamic duplicates keep the public path.
