# Full-program retrieval evaluation

The current fresh run is in `evaluationby5_results/full_program_two_passes/`.
Open `progress.txt` for the current pass, patient, method and stage, or watch:

```powershell
Get-Content 'evaluationbyW/evaluationby5_results/full_program_two_passes/progress.log' -Tail 5 -Wait
```

The active program uses `datasets/clean/patients_200.json`: **200 patients**.
Patient #155 is excluded as requested, leaving **199 patients per method**.
Patient #1 warms each method and is also included in measured processing.

The benchmark executes two complete sequential passes:

1. Every included patient with ChromaDB retrieval.
2. Every included patient with direct cosine search over all 693 chunks.

Each case enters the actual Coordinator MCP `run_cdss` endpoint and compiled
LangGraph. Patient, Ruler, Knowledge, Privacy and Device services communicate
through real HTTP MCP calls. The original LLM prompt, model, normalization,
Rust proving/verifying and final decision logic run in both passes. The services
share a Python process for measurement; this is not a multi-container deployment.

Only retrieval selection differs. Both Knowledge tools return the same response
fields and use the same chunk corpus, embedding model and k=3. Direct search
never calls ChromaDB. PDF hashes, model digests, package versions and index
configuration are recorded. Setup and chunk embedding are outside patient timing.
The existing Chroma default L2 metric is retained; direct search uses cosine.

Before each pass, llama3 is unloaded to reset cross-pass prompt reuse, then the
full workflow for patient #1 warms it. Normal model caching within each pass
remains enabled. The reported duration is actual elapsed time; no minimum time
is imposed. A second run can still differ due to model/runtime variability.

Hard-coded fallback bounds remain disabled for both methods, as originally
requested. Invalid or unsupported model policies are recorded as failures.
Such cases cannot safely continue to a proof or final clinical decision.
An out-of-range device ALERT follows the real program's no-proof path; it is
recorded separately from a failed verification. Deterministic evaluation sensor
readings keep the patient/parameter input identical between methods.

## Outputs

- `progress.txt`, `progress.json`, `progress.log`: live execution status.
- `patient_results.jsonl`: one durable record after every attempted workflow.
- `chroma_results.json`, `direct_results.json`: completed individual passes.
- `patient_comparison.csv`: joined by patient ID, with timings, sources, model
  candidates, accepted bounds, proof results, final decisions and errors.
- `summary.json`: total and mean times for all attempts, successful attempts,
  and the same successful patient cohort for both methods.
- `ragNorag.png`: mean full-workflow and retrieval times on successful pairs,
  annotated with overall patient count and failures.
- `report.md`, `manifest.json`, `warmup.json`, `chunk_manifest.json`,
  `patient_order.json`, `patient_snapshot.json`, `workflow.log`: audit details.

Normalized bounds are compared with absolute tolerance 0.000001 and relative
tolerance zero. Missing bounds are unavailable. Numeric closeness is not
classified as clinical compatibility.

## Run

```powershell
uv run --with langgraph --with langchain-chroma --with langchain-ollama --with langchain-community --with langchain-text-splitters --with pypdf --with matplotlib --with fastapi --with uvicorn --with requests python evaluationbyW/evaluationby5.py
```

Ollama must serve `llama3` and `nomic-embed-text`; the Rust ZKP executable must
be compiled. Each run creates a new output directory. `--output NEW_PATH` sets
one explicitly. `--exclude-patient-numbers` with no numbers includes all 200.

Older directories are historical: `20260925_121544` is a failed setup attempt;
`20260925_122703` and `without_patient_155` used the earlier interleaved protocol
and erroneously included 11 raw-only records outside the active cohort. They
are not the corrected full-program comparison.
