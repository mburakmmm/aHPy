The focused dual-interpreter coverage gate now requires 100% executable
Python-line coverage for the Universal backend, reports exact missing
lines/ranges in schema 2 artifacts, and traces measured modules from source to
avoid stale-extension blind spots.
Nested coverage self-tests now restore the outer trace function instead of
silently undercounting alphabetically later quality-tool tests.
The corrected dual-interpreter baseline raises the quality-tool CI floor from
41% to 50%.
Reproducibility and direct-build integration control flow now has focused
unit coverage above 97% without replacing their real hosted integration gates.
