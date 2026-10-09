# FD Phonon Worker Queue

Use dynamic workers for finite-displacement phonons. Do not split 100
displacements into five fixed groups of 20. Submit five workers; each worker
claims the next available displacement from `queue/undo`, runs it, then claims
another until the queue is empty or its wall-time guard is reached.

The finite-displacement taskset is one executable leaf under a project-defined
`pN[_name]` task (and optional parameter variant). Example layout:

```text
p3_phonon/fd_q4/
  README.md
  workflow.json
  input/
    POSCAR
    INCAR.fd
    KPOINTS
    POTCAR
    phonopy.conf
  jobs/
    disp-001/
  queue/
    undo/
    calculating/
    done/
    failed/
  workers/
    worker-001/
  queue.log
  .queue.lock
```

Worker loop:

```text
lock queue
move one queue/undo entry to queue/calculating
atomically update the queue summary in workflow.json
unlock queue
run VASP in jobs/disp-xxx
classify output
lock queue
move entry to queue/done or queue/failed
atomically update the queue summary in workflow.json
unlock queue
repeat
```

The real `jobs/disp-xxx` directory stays in place. Queue directories contain
state markers or symlinks so Slurm working directories are not broken by moving
running directories.

Failed displacement jobs remain in the taskset's internal `queue/failed` until
the user explicitly requests retry. This queue is not the structure-level
`failed/`: move the whole taskset there only after the taskset is confirmed
unrecoverable/rejected and no recovery plan remains. Retry must preserve the
previous failure reason and increment the attempt counter in `workflow.json`.
