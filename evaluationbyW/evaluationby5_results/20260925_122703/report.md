# ChromaDB versus exhaustive direct retrieval

Patients: 211. Paired successful workflows: 131.
Bounds: 124 identical within absolute tolerance 1e-06 (relative tolerance 0); 7 different; 80 unavailable.
Decisions: 131 identical; 0 different; 80 unavailable.
Numeric agreement is not a clinical compatibility assessment.

| Method | Errors | Paired mean total (s) | Paired mean retrieval (s) | Paired mean bounds (s) |
|---|---:|---:|---:|---:|
| ChromaDB retrieval | 79 | 11.123232 | 0.096566 | 10.944728 |
| Direct search over all chunks | 78 | 10.814209 | 0.082216 | 10.655350 |

Mean Chroma minus direct time differences (positive means direct was faster):
{"retrieval_s": 0.014349725190936108, "bound_generation_s": 0.2893781175572041, "proof_s": 0.004916232060938747, "total_workflow_s": 0.3090227702291255}
These are single-run stage differences, not a causal estimate. LLM generation, prompt reuse, and system load can dominate elapsed time.

## Protocol and limitations
- All distinct FHIR Patients under datasets are included, cleaned records first then raw-only records. The EMR's existing default condition is hypertension for records without condition; provenance identifies them.
- Uses the existing Knowledge MCP search_guidelines handler in process. Both retrieval methods and policy generation run in the same process; patient, privacy and device calls retain real loopback MCP HTTP transport. This does not benchmark a deployed Knowledge MCP network hop.
- A fresh isolated Chroma index uses the builder's PDF loader, chunk_size=1000, chunk_overlap=200, default collection and distance metric. The project's existing persistent index is untouched. Both methods receive identical chunks and current nomic-embed-text vectors; indexing is setup, not patient time.
- Chroma uses default squared L2 distance, direct search uses exhaustive cosine similarity. Rankings can differ for non-unit vectors and ties; this metric distinction in the existing path is retained and disclosed.
- Both methods use the existing llama3 prompt, temperature=0 and seed=42, normalization and supported parameters. Hard-coded fallback is disabled for both; invalid model output is an error. This explicit strict mode differs from production fallback behavior.
- The original coordinator nodes execute in order, with only the ruler RPC replaced by the shared local generator. All condition policies, proof requests, Rust proving/verifying and final decision logic are retained.
- Device CDSS_EVAL uses the existing deterministic patient/parameter sensor simulation. Fresh proof nonces remain random. ALERT means the device reported an out-of-range value and produced no proof; it is not a technical error or successful proof verification.
- Warm-up repeats the first valid dataset patient once for each method; that patient is still measured in the full evaluation. Methods alternate first/second within each pair, preserving identical patient order. No response cache or per-condition shortcut is introduced.
- Figure means use paired successful workflows; failed and incomplete attempts have separate statistics. Missing stage times are null, never zero. One run per patient is insufficient for statistical speed claims.

See summary.json for setup durations, totals, stage sample counts, all-attempt means, successful-only means, and paired means. Errors and partial outputs are retained in patient_results.json and patient_comparison.csv.
