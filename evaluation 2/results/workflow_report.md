# Whole-workflow evaluation

Input: `D:\9raya\memoire 2026\Privacy-Preserving-CDSS\evaluation 2\results\workflow_raw.csv`. Patient 1 was discarded as warm-up before each concurrency level. Patients 2 onward were measured; this run used 20 measured patients per level. Requests over 40 seconds were excluded from statistics but retained in the raw CSV.

## Results

Sequential mean included-patient latency: **14242.46 ms**.
Sequential batch wall time: **284861.83 ms**.
Best measured concurrency: **4**, wall time **127439.23 ms**, throughput **0.15 patients/s**.

## Interpretation

Patient latency is the elapsed time seen by each request; batch wall time is the time to process the measured patient set at that concurrency. Higher concurrency can reduce batch wall time while increasing individual latency or service contention. All stages represent the complete EMR retrieval, policy generation, ZKP validation, and final decision workflow when timing metadata is enabled.

This benchmark measures system performance, not clinical correctness. A successful request means the workflow returned successfully; it does not validate the medical policy itself.
