# License Decision

Date: 2026-07-15
Decision: Apache License 2.0

DreamCycle is intended to be embedded by vendors, shipped as a sidecar, and
used in commercial local-model products. Apache-2.0 is the better product fit
than LGPL-3.0 because it permits proprietary integration without weak-copyleft
library replacement and relinking obligations. It also adds an explicit patent
grant and preserves project attribution through `NOTICE`.

LGPL-3.0 remains a valid choice when the primary goal is requiring downstream
changes to the library itself to remain available under LGPL terms. That goal
would add legal review and distribution friction for the vendors DreamCycle is
trying to attract.

Psycopg remains a separate LGPL-3.0-only dependency. Depending on that package
does not change DreamCycle's own Apache-2.0 license; distributors still need to
comply with each dependency's terms. Direct dependency licenses are recorded in
`THIRD_PARTY.md` and should be rechecked for each release.

The project changed licenses before its first commit or release while it had
one copyright holder. Future relicensing may require contributor permission or
an appropriate contributor agreement.

This document records a product and engineering decision, not legal advice.

Authoritative terms:

- [Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0)
- [GNU Lesser General Public License 3.0](https://www.gnu.org/licenses/lgpl-3.0.en.html)
