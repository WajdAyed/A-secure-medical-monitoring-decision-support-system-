# Evaluation 3: Workflow Contract and Privacy Robustness

This suite evaluates contracts that are not covered by the latency and retrieval
benchmarks in `evaluation` and `evaluation 2`. It calls the running coordinator
and privacy MCP services and checks whether valid workflows preserve their
expected structure, invalid requests fail cleanly, and raw sensor values are
absent when debug output is disabled.

The reference ranges are project fallback values and are marked for clinician or
supervisor verification. This experiment measures software behavior; it does not
establish clinical validity.

## Run

Start the services first, then run:

```powershell
python "evaluation 3\run_contract_eval.py" --repeats 1
python "evaluation 3\analyze_contract_eval.py"
python "evaluation 3\generate_contract_figures.py"
```

Use `--limit 5 --repeats 1` for a quick smoke test. Service URLs can be supplied
with `--coordinator-url` and `--privacy-url`.

## Outputs

* `results/contract_raw.csv`: one row per workflow, malformed-request, or privacy case.
* `results/contract_summary.csv`: pass rate and latency by case family.
* `results/contract_report.md`: interpretation and limitations.
* `figures/figure_18_contract_pass_rate.png`: pass rate by case family.
* `figures/figure_19_contract_latency.png`: median latency by case family.

The privacy scan is deliberately conservative: it flags keys and serialized
values containing sensor-value terms. The normal privacy path is expected to
return public bounds and proof metadata, but not a raw measurement.