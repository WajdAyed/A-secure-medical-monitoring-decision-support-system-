# CDSS evaluation

Run only after restarting all CDSS services with `CDSS_EVAL=1` in their environment:

From the repository root, run `..\evaluation\run_all.ps1`; or run the same
script from inside `evaluation/`. The launcher resolves its own paths.

The harness calls `POST http://127.0.0.1:8007/rpc` directly and never invokes `doctor_console.py`; its cosmetic sleeps are excluded. Results checkpoint after every record. Patient 1 is retained as raw warm-up data but is excluded by analysis; the duplicate timing rule is applied by the analysis export step.
