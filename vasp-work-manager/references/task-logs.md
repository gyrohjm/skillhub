# Local Task Logs

Use this reference when a source project has `docs/records/task_logs/`. The
project log is an agent-readable execution trail; the SQLite ledger and archive
remain the authoritative manager records.

## Files And Timing

- Append one row to `project_log.md` after each manager registration, state or
  review update, archive creation, verification result, or cleanup plan.
- Append the same event to `daily/YYYY-MM-DD.md` for the current work date.
- If the current daily file does not exist, create it before the first entry
  with an Activity table and a Daily Closeout section matching the local task
  log format.
- Before ending work for the day, complete the daily closeout with completed
  work, blocked work, artifacts, and next action.

## Required Fields

Record timestamp, actor, task/case, manager action, resulting status, and an
evidence path such as ledger, archive, manifest, SHA256 verification result, or
project summary. State the next action or handoff.

Do not copy POTCAR content, secrets, large output, or unverified physical
interpretation into task logs. Record science decisions in `decisions.md` and
analysis conclusions in the case report.
