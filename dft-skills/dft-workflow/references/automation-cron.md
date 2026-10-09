# Optional automation

Only set up monitoring or automatic progression on explicit request. The product's
automation mechanism runs the normal workflow entrypoint; it does not bypass draft
approval, input reconciliation, dependency decisions, snapshots or durable receipts.
No duplicate approval queue or task-state file is needed.

Program-first decisions may advance work inside the user's existing authorization.
Use an Agent only for unresolved evidence; major conflicts pause the affected branch.
Preserve user edits and completed outputs, and obey finite retry/iteration bounds.
A parameter hash change is not an automatic new user-review requirement.

## Compatibility only

The bundled `vwf automation` derives old paths and writes legacy records.
Do not install it for canonical v2 leaves or claim it implements an autonomous v2
driver. A future driver must pass concurrency, no-duplicate-submit and recovery tests.
The present short-flow changes do not introduce a new unattended scheduler service.
