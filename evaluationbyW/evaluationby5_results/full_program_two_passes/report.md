# ChromaDB versus exhaustive direct retrieval

Patients: 199. Paired successful workflows: 132.
Bounds: 132 identical within absolute tolerance 1e-06 (relative tolerance 0); 0 different; 67 unavailable.
Decisions: 132 identical; 0 different; 67 unavailable.
Numeric agreement is not a clinical compatibility assessment.

| Method | Errors | Paired mean total (s) | Paired mean retrieval (s) | Paired mean bounds (s) |
|---|---:|---:|---:|---:|
| ChromaDB retrieval | 67 | 14.827070 | 0.213423 | 14.488642 |
| Direct search over all chunks | 67 | 15.029003 | 0.189784 | 14.748497 |

All attempted patients (failures are timed up to the actual failing stage):

| Method | Attempts | Completed decisions | Total patient time (s) | Mean attempt time (s) |
|---|---:|---:|---:|---:|
| ChromaDB retrieval | 199 | 132 | 2862.340323 | 14.383620 |
| Direct search over all chunks | 199 | 132 | 2924.790356 | 14.697439 |

Mean Chroma minus direct time differences (positive means direct was faster):
{"retrieval_s": 0.0236388492426296, "bound_generation_s": -0.2598541181822096, "proof_s": 0.03324415530294738, "total_workflow_s": -0.20193304393951372}
These are single-run stage differences, not a causal estimate. LLM generation, prompt reuse, and system load can dominate elapsed time.

Ordered retrieved chunks: 199 identical pairs and 0 different pairs.
Among pairs with identical retrieved chunks, 0 had different accepted bounds and 0 had different decisions.
There were 0 pairs where only one method failed. Missing bounds are unavailable, not agreement or disagreement. Differences with identical retrieved text cannot be attributed to chunk selection; fixed generation settings do not guarantee identical model outputs.

## Protocol and limitations
- Uses the active application's datasets/clean/patients_200.json only: 200 patients, or 199 with requested exclusion #155. Raw-only records are not members of the active cohort.
- Every patient is submitted through the real Coordinator run_cdss MCP endpoint and compiled LangGraph. Patient, Ruler, Knowledge, Privacy and Device calls all use real loopback HTTP MCP transport. Services share a Python process for instrumentation; they are not separate Docker containers.
- A fresh isolated Chroma index uses the builder's PDF loader, chunk_size=1000, chunk_overlap=200, default collection and distance metric. The project's existing persistent index is untouched. Both methods receive identical chunks and current nomic-embed-text vectors; indexing is setup, not patient time.
- Chroma uses default squared L2 distance, direct search uses exhaustive cosine similarity. Rankings can differ for non-unit vectors and ties; this metric distinction in the existing path is retained and disclosed.
- Both methods use the existing llama3 prompt, temperature=0 and seed=42, normalization and supported parameters. Hard-coded fallback is disabled for both; invalid model output is an error. This explicit strict mode differs from production fallback behavior.
- All original coordinator nodes, Ruler RPC, condition policies, proof requests, Rust proving/verifying and final decision logic are retained. The Ruler selects one of two Knowledge retrieval tools; generation and strict validation are shared.
- Device CDSS_EVAL uses the existing deterministic patient/parameter sensor simulation. Fresh proof nonces remain random. ALERT means the device reported an out-of-range value and produced no proof; it is not a technical error or successful proof verification.
- Two full sequential passes: all Chroma patients, then all direct-search patients, in identical original order. Before each pass llama3 is unloaded to reset cross-pass prompt reuse, then patient #1 warms the full workflow and is measured again. Natural within-pass model caching remains enabled for both methods. No artificial minimum duration or application response cache is used.
- Figure means use paired successful workflows; failed and incomplete attempts have separate statistics. Missing stage times are null, never zero. One run per patient is insufficient for statistical speed claims.
- The direct pass stopped after 133 measured patients and was resumed from the saved prefix. Restart setup rebuilt direct vectors from the saved chunks with the same model digest, verified retrieval agreement for every prior distinct query, and warmed patient #1 again. Prior timings are unchanged. This interruption and renewed model cache state limit whole-pass timing comparisons.
- The direct pass stopped after 133 measured patients and was resumed from the saved prefix. Restart setup rebuilt direct vectors from the saved chunks with the same model digest, verified retrieval agreement for every prior distinct query, and warmed patient #1 again. Prior timings are unchanged. This interruption and renewed model cache state limit whole-pass timing comparisons.

See summary.json for setup durations, totals, stage sample counts, all-attempt means, successful-only means, and paired means. Errors and partial outputs are retained in patient_results.json and patient_comparison.csv.
