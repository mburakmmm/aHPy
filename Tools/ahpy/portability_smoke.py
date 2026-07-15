"""Semantic smoke test for one prebuilt Universal HPy artifact."""

import bootstrap_answer
import bootstrap_types


assert bootstrap_answer.return_none() is None
assert bootstrap_answer.return_big_integer() == \
    1234567890123456789012345678901234567890
assert bootstrap_answer.make_list() == [1, None, 2]
assert bootstrap_answer.make_dict() == {
    "one": 1, 2: [None, {"nested": True}]}
assert bootstrap_answer.default_values("required") == [
    "required", 2, (3, None)]
assert bootstrap_answer.identity("portable") == "portable"

marker = bootstrap_types.make_marker()
assert type(marker) is bootstrap_types.Marker
box = bootstrap_types.make_box()
box.value = marker
assert box.value is marker
assert box.owner() is box
assert box.identity(marker) is marker
initialized = bootstrap_types.Initialized(marker)
assert initialized.value is marker

print("Prebuilt Universal HPy artifact: portability smoke passed")
