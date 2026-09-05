Add a machine-readable maintenance policy and validator covering ownership,
bus factor, supported-line lifetime, EOL, branches, backports, deprecation,
security reporting and periodic dependency/upstream/platform review.  Publish
the corresponding maintainer procedure and CODEOWNERS without overstating the
current single-maintainer capacity.

Add fail-closed dependency-review and CodeQL ``security-extended`` automation
for Python and C/C++, pin every action to an immutable release commit, and
expand monthly Dependabot coverage to the root and aHPy validation dependency
sets.  Hosted scan evidence remains required before the production checklist
can call the automation published.

Add an append-only Cython baseline/rebase log and validator.  Distinguish the
initial baseline from actual transitions, chain every accepted full commit,
require path-specific conflict classifications and decisions, and reject drift
from the package or release-contract Cython base.

Add an aHPy-specific debugging guide that preserves the first failing
source/compiler/generated-C/native-link/import/runtime/ownership boundary and
routes only handwritten public-HPy reproductions upstream.  Centralize current
HPy, PyPy, GraalPy, Python 3.15 and public-API gaps in an inventory that clearly
distinguishes hosted evidence, prepared reports, filed links and support state.
