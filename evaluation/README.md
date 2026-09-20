# Evaluation Suite

This folder evaluates the measurable parts of the Privacy-Preserving CDSS. All
benchmark outputs are written to `evaluation/results/` and are intentionally
ignored by version control so each experiment remains reproducible.

## Prerequisites

Build the ZKP executable once:

```powershell
cd zkp_engine
cargo build --release
cd ..
```

For end-to-end tests, start the system first:

```powershell
docker compose up --build -d
```

## Run the experiments

```powershell
# ZKP correctness and latency (five boundary/out-of-range cases, 30 runs each)
python evaluation/benchmarks/benchmark_zkp.py --runs 30
python evaluation/analysis/analyze_zkp.py

# ZKP throughput under increasing simultaneous clients
python evaluation/benchmarks/benchmark_scalability.py --requests 20 --clients 1 2 4 8

# Architecture-level predicate-only versus proof-enabled validation comparison
python evaluation/benchmarks/benchmark_architecture_comparison.py --requests 30 --clients 1 2 4 8
python evaluation/analysis/analyze_architecture_comparison.py

# End-to-end overhead; requires an otherwise-identical proof-off deployment
python evaluation/benchmarks/benchmark_workflow_overhead.py --baseline-url http://BASELINE_HOST:8007
python evaluation/analysis/analyze_workflow_overhead.py

# End-to-end CDSS latency (requires the Docker services)
python evaluation/benchmarks/benchmark_pipeline.py --concurrency 1
python evaluation/analysis/analyze_pipeline.py

# RAG impact: retrieval latency and whether the correct guideline is returned
python evaluation/benchmarks/benchmark_rag.py --runs 10
python evaluation/analysis/analyze_rag.py

# RAG ablation: compare policy generation with and without retrieved context
python evaluation/benchmarks/benchmark_rag_impact.py
python evaluation/analysis/analyze_rag_impact.py

# Whole-system validation across representative patient records
python evaluation/benchmarks/benchmark_system.py
python evaluation/analysis/analyze_system.py

# Python-side memory allocations incurred by the proof client
python evaluation/profiling/profile_proof_memory.py --runs 30

# Optional PNG plots; install matplotlib first if it is not available
python evaluation/analysis/generate_figures.py
```

Use `--help` on each script to adjust the number of runs, service URL, output
path, or ZKP executable path. For a remote coordinator, set
`$env:LANGGRAPH_URL="http://HOST:8007"` or pass `--url`.

## Outputs

| File | Contents |
| --- | --- |
| `results/zkp_raw.csv` | Per-run ZKP response, expected status, and process latency |
| `results/zkp_summary.csv` | Correctness rate plus mean/median/p95 latency by test case |
| `results/scalability_raw.csv` | Throughput and latency at each client concurrency level |
| `results/architecture_comparison_raw.csv` | Paired predicate-only and proof-enabled validation measurements, throughput, and response-disclosure proxies |
| `results/architecture_comparison_summary.csv` | Correctness, baseline/proof-enabled latency, proof-layer share, throughput, and disclosure-proxy summary by concurrency |
| `results/workflow_overhead_raw.csv` | Paired proof-off/proof-enabled CDSS workflow latency, outcome agreement, and proof-verification results |
| `results/workflow_overhead_summary.csv` | Paired end-to-end latency and overhead summary; valid only for matched deployments |
| `results/pipeline_raw.csv` | Per-run coordinator latency and HTTP outcome |
| `results/pipeline_summary.csv` | End-to-end success rate and latency summary |
| `results/rag_raw.csv` | Per-query RAG latency, returned sources, and source rank |
| `results/rag_summary.csv` | RAG availability, source hit@3, MRR, and latency summary |
| `results/rag_impact_raw.csv` | Policy outputs and latency from paired RAG/no-RAG requests |
| `results/rag_impact_summary.csv` | Quality, bound-error, and latency deltas attributable to RAG |
| `results/system_raw.csv` | Per-patient whole-workflow validation and latency |
| `results/system_summary.csv` | Whole-system validation rate and latency summary |
| `results/proof_memory.txt` | Python wrapper allocation profile |

## RAG and whole-system evaluation

`benchmark_rag.py` uses the ground-truth queries in `fixtures/rag_cases.json`.
It evaluates whether the expected guideline PDF is present in the top three
retrieved chunks (`source_hit_at_k`) and how high it ranks
(`mean_reciprocal_rank`), alongside retrieval latency. The Knowledge MCP now
returns a backward-compatible `sources` field so this can be checked without
trying to infer a PDF from chunk text. Add clinically reviewed query/source
pairs to that fixture as the guideline corpus grows.

`benchmark_rag_impact.py` is the project-level RAG ablation. It sends each
case in `fixtures/policy_reference_cases.json` to the Rule Engine twice: once
with retrieved guideline context and once without it. It then compares JSON
validity, reference-policy match rate, bound error, and latency. The initial
reference policies mirror the project's current hypertension demo values; they
must be reviewed and replaced with clinician-approved targets before making
clinical claims. The no-RAG query option exists only to support this evaluation.

`benchmark_system.py` evaluates the complete patient → RAG-backed policy →
ZKP → decision workflow for multiple patients. A request passes only when every
stage is present, policy bounds are numeric and ordered, the proof is verified
with a valid status, and the final decision agrees with that status. It checks
integration correctness as well as end-to-end latency; it does not establish
clinical validity of LLM-generated limits.

By default, the patient-based benchmarks (`benchmark_pipeline.py`,
`benchmark_system.py`, `benchmark_rag_impact.py`, and
`benchmark_workflow_overhead.py`) load all 200 identifiers from
`datasets/clean/patients_200.json`. They run the first patient once as a
discarded cold-start request, then report patients 2 through 200 plus one
explicitly marked duplicate of patient 200. This preserves 200 reported
patient entries without including the first-patient cold-start time. Use
`--no-exclude-first` to report every patient's own timing, or `--warmup N`
to add discarded runs for each reported entry.

## Important interpretation note

The current `zkp_engine` produces a valid Bulletproof range proof for a
64-bit unsigned value. However, it does **not** cryptographically bind that
proof to the supplied clinical `min` and `max` limits. The `NORMAL`/`ALERT`
status is calculated by ordinary comparison in `zkp_engine/src/main.rs` after
the generic proof verifies. Therefore these benchmarks measure the current
implementation accurately, but they must not be presented as evidence that a
clinical interval is enforced by the zero-knowledge proof itself.

## Architecture-level comparison with zk-MCP

`benchmark_architecture_comparison.py` measures the cost and correctness of
adding the current proof layer to the same range-classification predicate. The
predicate-only baseline is deliberately labelled as a local baseline; the
proof-enabled timing includes executable startup and local IPC. Its
`proof_layer_share_pct` is the fraction of the proof-enabled validation time
attributable to the proof-enabled path, not a whole-CDSS or MCP-communication
overhead. The response-field metrics are interface-level disclosure proxies:
they check whether `value`, `min`, or `max` are returned by the proof API and
record that the `status` classification is public. They do not establish a
formal privacy guarantee.

This experiment supports an architecture-level comparison with Jing and Qi's
zk-MCP work: both evaluate the added cost, correctness, scalability, and
selective disclosure of a ZK verification layer. It is not a numerical
reproduction or ranking against zk-MCP, whose workload is asynchronous MCP
communication auditing with Circom zk-SNARKs rather than clinical decision
validation with Bulletproofs. The current engine returns combined prove-and-
verify results, so proof-generation and verification time cannot be reported
separately without instrumenting `zkp_engine`, which is intentionally outside
this evaluation-only extension.

`benchmark_workflow_overhead.py` measures end-to-end proof overhead only when
the user supplies a separately deployed proof-off coordinator. The two
deployments must differ only in proof handling; otherwise, the measured delta
cannot be attributed to the proof layer. It reports outcome agreement so that a
lower latency is never interpreted as acceptable if it changes the decision.
