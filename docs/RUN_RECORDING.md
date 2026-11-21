# Simulation run recordings

Dashboard runs and `uv run mahanya run` create a unique run in the local SQLite
file `api/data/processed/runs.sqlite3`. Each completed simulation tick records the
observed traffic state, vehicle positions and dimensions, model recommendation
when present, and the scheduler's applied decision and reason. The write happens
after SUMO accepts the signal and advances. The existing
`api/data/processed/decision_log.jsonl` is retained; older JSONL entries are not
imported into the new database and may mix scenarios and repeated tick numbers.

The database includes a run ID, scenario, seed, start/end times, status, config,
model-loaded flag and hashes of the network, scenario, routes, checkpoint and
raw-count file as they existed at run start. The raw-count hash is a snapshot,
not proof those counts were used to produce the loaded scenario. A process crash
can leave a run marked `running`; inspect its last tick and end time rather than
assuming it is still active. The database is local, gitignored and is not a
backup. SQLite uses WAL; use SQLite's backup facility when copying an active DB.

While the relay is running, browse `http://127.0.0.1:8000/docs` or query:

- `GET /api/runs?limit=100&offset=0` — list runs, newest first.
- `GET /api/runs/{run_id}` — run details and input hashes.
- `GET /api/runs/{run_id}/ticks?after_tick=-1&limit=100` — ordered records;
  pass the last returned `state.tick` as `after_tick` for the next page. Limits
  are 1–500, and records can be queried while the run is active.

For offline inspection, from `api/`:

```powershell
uv run mahanya export-run <run_id> --output data/processed/my-run.jsonl
```

This creates the tick JSONL and a `.metadata.json` sidecar, and refuses to
overwrite either. Exporting an active run captures the records available during
the export; export again to a new filename for a later snapshot.

The records are simulated observations and **applied scheduler decisions**. They
are useful source data for future training and evaluation, but they are not
independent ground-truth labels or real Sapon field observations. The current
training command still consumes the Parquet sequences produced by `generate`;
these raw run exports are not automatically fed into training. Prepare and
validate labels, prevent overlapping runs from leaking across train/test splits,
and record the dataset version before using them for a model. The supplied field
counts and turning proportions are synthetic or assumed until surveyed.
