# FD Phonon Worker Queue

Use dynamic workers for finite-displacement phonons. Do not split 100
displacements into five fixed groups of 20. Submit five workers; each worker
claims the next available displacement from `queue/undo`, runs it, then claims
another until the queue is empty or its wall-time guard is reached.

Taskset layout:

```text
phonon/fd/fd-001/
  input/
    POSCAR
    INCAR.fd
    KPOINTS
    POTCAR
    phonopy.conf
    submission_review.dat
  jobs/
    disp-001/
  queue/
    undo/
    calculating/
    done/
    failed/
  workers/
    worker-001/
  state.json
  queue.log
  .queue.lock
```

Worker loop:

```text
lock queue
move one queue/undo entry to queue/calculating
update state.json
unlock queue
run VASP in jobs/disp-xxx
classify output
lock queue
move entry to queue/done or queue/failed
update state.json
unlock queue
repeat
```

The real `jobs/disp-xxx` directory stays in place. Queue directories contain
state markers or symlinks so Slurm working directories are not broken by moving
running directories.

Failed jobs remain in `queue/failed` until the user explicitly requests retry.
Retry must preserve the previous failure reason and increment the attempt
counter.
