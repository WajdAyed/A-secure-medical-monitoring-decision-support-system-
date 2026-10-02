# Evaluation 2

This is the second, thesis-oriented evaluation suite for the Privacy-Preserving CDSS.
The active experiment evaluates RAG only: ChromaDB guideline retrieval for the three
conditions represented by the local guideline PDFs. It measures retrieval latency, correct
source-PDF retrieval, and whether the expected reference bounds occur in the retrieved chunks.

The earlier end-to-end RAG/no-RAG scripts remain available as historical experiments, but they
are not the correct experiment for the RAG-only question because the current RAG implementation
retrieves Chroma chunks and then calls the LLM to synthesize a policy.

## Reproduce RAG-only evaluation

Start the Knowledge MCP service and its embedding dependency, then run:

```powershell
python "evaluation 2\run_rag_only.py" --repeats 30 --k 3
python "evaluation 2\analyze_rag_only.py"
python "evaluation 2\generate_rag_only_figures.py"
python "evaluation 2\run_rag_policy_only.py" --repeats 10
python "evaluation 2\analyze_rag_policy_only.py"
python "evaluation 2\generate_rag_policy_figures.py"
python "evaluation 2\run_rag_comparison.py" --repeats 10
python "evaluation 2\analyze_rag_comparison.py"
python "evaluation 2\generate_rag_comparison_figures.py"
```

Use `--repeats 1` for a smoke test. The benchmark evaluates hypertension, diabetes, and heart
failure because those are the conditions with PDFs in `RAG/guidelines/`.

## Metrics

* **Retrieval latency:** mean, median, and p95 Chroma query time.
* **Retrieval accuracy:** correct source PDF in the top-k metadata results.
* **Content coverage:** expected reference bounds present in the retrieved chunks.
* **RAG policy answer:** valid policy, parameter match, exact reference match, and total
  retrieval-plus-LLM latency. This is RAG-only, but it is not a no-RAG comparison.

The fallback reference ranges are explicitly marked for clinician/supervisor validation in the
repository. They should not be described as clinical ground truth until reviewed.

## Outputs

* `results/rag_only_raw.csv`: raw Chroma retrieval measurements.
* `results/rag_only_summary.csv`: per-condition retrieval latency and accuracy.
* `results/rag_only_report.md`: interpretation and limitations.
* `figures 2/figure_5_rag_only_latency.png`: retrieval latency by condition.
* `figures 2/figure_6_rag_only_accuracy.png`: source-PDF accuracy and content coverage.
* `results/rag_policy_only_raw.csv`: RAG-enabled generated policy answers.
* `results/rag_policy_only_summary.csv`: RAG policy validity, parameter accuracy, and latency.
* `results/rag_policy_only_report.md`: interpretation of generated policy results.
* `figures 2/figure_7_rag_policy_accuracy.png`: generated policy quality by condition.
* `figures 2/figure_8_rag_policy_latency.png`: generated policy latency by condition.
* `results/rag_vs_full_pdf_raw.csv`: paired Chroma versus complete-PDF measurements.
* `results/rag_comparison_summary.csv`: paired latency and policy-accuracy comparison.
* `results/rag_comparison_report.md`: comparison interpretation.
* `figures 2/figure_9_rag_vs_full_pdf_latency.png`: total latency comparison.
* `figures 2/figure_10_rag_vs_full_pdf_accuracy.png`: policy accuracy comparison.
* `figures 2/figure_11_rag_vs_full_pdf_stages.png`: retrieval/PDF-scan and LLM timing breakdown.
* `results/workflow_raw.csv`: checkpointed whole-workflow sample measurements.
* `results/workflow_scalability_raw.csv`: separate measurements at concurrency 8 and 16.
* `results/workflow_summary.csv`: latency, throughput, and exclusion summary for concurrency 1/2/4.
* `results/workflow_extra_summary.csv`: offline speedup, efficiency, timeout, and variability tests.
* `results/workflow_extra_report.md`: interpretation of the additional tests.
* `figures 2/figure_12_workflow_batch_time.png`: batch wall time at each concurrency.
* `figures 2/figure_13_workflow_throughput.png`: patients processed per second.
* `figures 2/figure_14_workflow_latency.png`: mean and p95 per-patient latency.
* `figures 2/figure_15_workflow_speedup.png`: measured versus ideal parallel speedup.
* `figures 2/figure_16_workflow_efficiency.png`: parallel efficiency.
* `figures 2/figure_17_workflow_variability.png`: latency mean and standard deviation.
* `figures 2/figure_18_workflow_scalability.png`: batch elapsed time at concurrency 1/2/4/8/16,
  with successful-request counts and completion rate shown for each level.

The workflow sample uses 20 measured patients per concurrency level, with patient 1 discarded as
warm-up. Requests over 40 seconds are retained in raw data but excluded from reported statistics.
Run `python "evaluation 2\run_workflow_benchmark.py" --sample-size 199` for patients 2-200.

## Figure interpretation

* **Figure 11:** compares where time is spent in Chroma RAG versus complete-PDF processing. The
  RAG bar is based on measured total RAG time plus the separately measured retrieval estimate when
  internal Rule Engine timing metadata is unavailable.
* **Figure 12:** shows total wall-clock time for the measured patient batch. Higher concurrency
  reduces batch completion time.
* **Figure 13:** shows throughput. Concurrency 2 approximately doubles throughput; concurrency 4
  adds little throughput because service contention appears.
* **Figure 14:** shows mean and p95 request latency. Concurrency 4 has the widest latency penalty.
* **Figure 15:** compares measured speedup with ideal linear scaling. The measured speedup reaches
  2.24x at concurrency 4, below ideal 4x.
* **Figure 16:** shows parallel efficiency. The concurrency-4 result is about 53%, indicating
  contention and diminishing returns.
* **Figure 17:** shows latency variability. The standard deviation grows substantially at
  concurrency 4, consistent with its one excluded request.
* **Figure 18:** compares elapsed time for the same 20-patient batch at concurrency 1/2/4/8/16.
  Labels show requests completed within 40 seconds. The 8- and 16-patient runs had transport
  errors and timeouts, so their shorter wall times do not indicate successful scaling.

The previous files `rag_emr_measurements.csv`, `rag_summary.csv`, `process_summary.csv`, and
`zkp_summary.csv` belong to the earlier end-to-end experiment and are not overwritten.
