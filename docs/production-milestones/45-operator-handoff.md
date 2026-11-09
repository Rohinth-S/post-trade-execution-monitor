# Milestone 45: operator handoff

This milestone records a concrete operating decision for **post-trade-execution-monitor**. It is kept beside the implementation so future changes can be reviewed against an explicit contract.

## Decision
- Keep the boundary explicit in code, tests, and reports.
- Fail closed when the required input or runtime assumption is absent.
- Preserve deterministic offline execution while keeping live adapters opt-in.

## Acceptance checks
- The relevant test suite covers the happy path and one failure path.
- CLI/report output remains machine-readable and reproducible.
- Credentials and live provider state are never embedded in fixtures or committed files.
