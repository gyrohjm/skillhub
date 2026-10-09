# Quantum ESPRESSO backend

Canonical support covers reviewed prebuilt QE inputs, not arbitrary namelist generation
or automatic VASP-to-QE conversion. Use the [short workflow](workflow-order.md);
`initialize --draft` prepares known inputs, `bind-approval` binds the real parameter
review, and `submit` executes authorized ready tasks.

Record the exact executable/version, scalar input parameters, structure and k mesh,
UPF identities, restart dependencies and stage-specific completion evidence.
Do not infer compatibility of restart data from filenames alone.
Use `dft-submit` for the target environment, resource shape and selected script.
MPI and stage launch arguments come from that configuration, not a universal QE rule.
Unresolved input generation or interpretation is a capability gap; report it rather
than inventing parameters or promising an operational backend.

## Compatibility only

`canonical_workflow.py prepare` is the previous one-leaf prepare-only interface.
Legacy `qewf` bundles and their recovery records remain supported separately;
do not use them to create parallel state files in a canonical leaf.
