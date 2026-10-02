# Workflow contract and privacy robustness

This report measures software contracts against the running local services. It is not clinical validation.

## Results

- **privacy_invalid**: 5/5 passed (100.0%); median latency 9.1 ms.
- **privacy_normal**: 1/1 passed (100.0%); median latency 81.4 ms.
- **unknown_patient**: 1/1 passed (100.0%); median latency 21189.3 ms.
- **valid_workflow**: 0/1 passed (0.0%); median latency 30022.5 ms.

## Limitations

- Valid workflows use one representative patient per condition and the local service configuration.
- Fallback ranges are explicitly unverified project reference values.
- The privacy scan checks returned JSON only; it cannot prove that a running process log or network intermediary did not retain a value.

## Failed cases

- `valid_workflow/depression:100001:r1`: HTTPConnectionPool(host='127.0.0.1', port=8007): Read timed out. (read timeout=30.0)
