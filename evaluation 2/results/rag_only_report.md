# RAG-only evaluation results

Source: `D:\9raya\memoire 2026\Privacy-Preserving-CDSS\evaluation 2\results\rag_only_raw.csv`; successful retrievals: 30; failed retrievals: 0.

## Scope

This experiment evaluates only ChromaDB guideline retrieval for the three conditions with local PDFs. It does not compare against no-RAG, does not call the policy-generation LLM, and does not claim that retrieval alone generates a personalized clinical policy.

## Results

Mean Chroma retrieval latency: **62.46 ms**; median: **60.50 ms**; p95: **79.80 ms**.
Mean correct-source rate across conditions: **100.0%**.
Mean expected-bound presence rate in retrieved text: **0.0%**.

## Interpretation

A correct source hit means that Chroma returned the expected guideline PDF in the top-k result metadata. Bound presence means both documented reference numbers were visible in the returned chunks; it is a retrieval-content check, not clinical validation. The next valid comparison is to measure this retrieval-only path against a PDF full-scan baseline, using the same queries and machine.
