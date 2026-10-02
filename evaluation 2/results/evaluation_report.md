# Evaluation 2 results

Source: `D:\9raya\memoire 2026\Privacy-Preserving-CDSS\evaluation\results\rag_vs_norag.jsonl`; successful paired measurements: 196; discarded failed rows: 4.

## Main result

Mean end-to-end time without RAG: **5218.42 ms**.
Mean end-to-end time with RAG: **13797.63 ms**.
RAG minus no-RAG: **8579.21 ms** (164.4%).
Decision agreement for paired EMRs: **98.5%**.

## Interpretation

RAG policy accuracy by interval IoU was 0.212 versus 0.277 without RAG.
The measured ZKP stage averaged 71.04 ms with RAG and 66.01 ms without RAG; its share of total processing was 0.55% and 1.29%, respectively.

The current measurements do not support the claim that RAG is faster or more accurate: RAG is slower and has lower IoU on these fallback references. These are software/system evaluation results, not clinical validation. The reference ranges in this repository are documented as fallback ranges and require clinician review before thesis claims about clinical accuracy. ZKP timing includes the privacy service, device call, process startup/IPC, proving, and verification; it is not a pure cryptographic microbenchmark.
