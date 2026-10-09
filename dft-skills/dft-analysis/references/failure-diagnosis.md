# Failure diagnosis and evidence boundary

Run `scripts/analysis_decision.py diagnose` for existing output evidence.
Report `failure_class`, exact source/log signature, confidence, completion facts and
the smallest next action. Missing evidence remains unknown; a scheduler state alone
does not prove engine termination, convergence or scientific acceptance.

Keep `scheduler_complete`, `artifact_complete`, `scientifically_accepted` independent.
A technically finished result may contradict expectations; that is not a runtime bug.
Technical failure retries in place through dft-workflow after preserving replaced evidence.
Scientifically unexpected completion creates a `rerun_NNN` branch with `derived_from`.
Analysis itself does not edit inputs, archive attempts, submit, cancel or delete files.

`submission_authorized: false` in a diagnostic report means the report grants no new
authority; it does not revoke the user's existing bounded workflow authorization.
Ordinary revisions within that scope go through workflow reconciliation. A major
physical-model conflict returns to dft-design/user; routine retries do not need another
submission review. Resource/launcher conventions belong to dft-submit.
