# Additional workflow tests

These tests are calculated from the completed workflow benchmark; no new service calls are made.

## Tests

- **Speedup:** sequential batch wall time divided by each concurrent batch wall time.
- **Parallel efficiency:** speedup divided by concurrency; 1.0 would be ideal linear scaling.
- **Timeout rate:** requests excluded because they exceeded 40 seconds.
- **Latency variability:** standard deviation and p95 request latency.

Best batch level: concurrency 4 with 127.44 seconds.
Higher concurrency improves total batch completion but can increase per-request latency because the model and services contend for resources.
