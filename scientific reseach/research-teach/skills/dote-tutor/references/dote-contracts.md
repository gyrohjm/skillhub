# DOTE project context contract

Use this reference to select evidence without scanning a whole calculation tree. DOTE is a remote-compute workbench: local code handles contracts, transfer, analysis, archival, and visualization; DFT engines run only on configured remote backends.

## Read order

1. Project `AGENTS.md` and DOTE `PROJECT_CONTEXT.md`.
2. `calculation_design.json` or `research_brief.json` for the question, hypothesis, controls, and observables.
3. `task_spec.json` for engine, task kind, inputs, resources, provenance, and approval state.
4. `state.json` for recorded lifecycle state and errors.
5. `result.json` and validated `dft-analysis` products for observables and verdicts.
6. `knowledge/Sources/Verified`, `knowledge/Concepts`, `knowledge/Maps`, and `knowledge/Learning` for source-backed teaching.

## Evidence labels

- `recorded`: directly present in a contract, parsed result, or source note.
- `verified`: checked against the source/contract and accepted into the project knowledge base.
- `proposed`: a relation, interpretation, or graph edge awaiting checking or user confirmation.
- `inferred`: a reasoning step made by the assistant; label it explicitly.
- `unknown`: the project does not contain enough evidence.

## Common task groups

| Group | Typical question | Minimum caution |
|---|---|---|
| `test` / `structure` | Is the structure or setup valid? | Do not treat a geometry check as an energy conclusion. |
| `energy` / `scf` | What is the total energy or ground-state electronic solution? | Compare only compatible references and converged settings. |
| `relax` | Did the geometry optimize? | Check forces, stress, thresholds, constraints, and final electronic state. |
| `electronic` | What is the band/DOS/electronic structure? | Check sampling, smearing, occupations, spin, and analysis provenance. |
| `phonon` | Is the vibrational result reliable? | Check supercell, q-point, forces, imaginary modes, and convergence. |
| `charge` / `spin` | What charge or magnetic distribution is supported? | State partitioning scheme and reference state; do not overinterpret plots. |

## DOTE remote boundary

The default remote task layout is:

```text
<profile.defaultRoot>/.dote/workspace/<project-relative-task-path>
```

Project overrides are read from `.dote/config.json` or `dote.config.json` under `remote.workspacePath`. Agent access remains limited by the SSH profile's `allowedRoots`, and upload generates `DOTE_WORKSPACE.md` at the remote workspace root. A convention file documents the boundary; the backend path guard is the enforcement mechanism.
