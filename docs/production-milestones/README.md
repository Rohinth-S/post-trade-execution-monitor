# Production milestone index

The monitor reconciles normalized fills, flags quantity and price drift, and keeps venue connectors outside the deterministic core.

The numbered milestone files in this directory are the review trail for the operational decisions that support that boundary. They are grouped in the same order used by the implementation:

1. **Input and data contracts** — src validates records before calculations.
2. **Deterministic research path** — tests exercises fixtures, empty inputs, invalid rows, and edge cases.
3. **Live adapter boundary** — network clients are opt-in and credentials are read only from environment variables.
4. **Reports and operations** — CLI output stays machine-readable, while README.md documents assumptions and limits.
5. **Release controls** — CI, container, secret-handling, incident, and handoff milestones are evidence for a production review.

The milestone files are deliberately small: each one names a single decision so a reviewer can trace a change to a focused commit instead of one opaque rewrite.

