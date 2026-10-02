# RAG versus full-PDF comparison

Successful measurements: 60; failed measurements: 0.

## Definitions

`rag_chroma` queries the Chroma vector database for the top-k chunks and then uses the Rule Engine's RAG-enabled LLM prompt. `no_rag_full_pdf` bypasses Chroma, loads the complete condition-specific guideline PDF, and sends that full text to the same Ollama model. Both modes use the same three conditions, age, model settings, references, and repeat count.

## Results

Mean total time, Chroma RAG: **6839.29 ms**.
Mean total time, full-PDF no-RAG: **7891.28 ms**.
RAG minus full-PDF: **-1051.99 ms** (-13.3%).
Parameter match: RAG **66.7%**, full-PDF **66.7%**.
Exact reference match: RAG **33.3%**, full-PDF **33.3%**.

## Interpretation

This is the requested architecture comparison: semantic vector retrieval versus reading the complete condition guideline. A lower RAG time supports the efficiency claim, while higher parameter/exact-match rates support the accuracy claim. These references are still project evaluation references and require clinical review before being presented as clinical ground truth.
