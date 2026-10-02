# RAG-only policy evaluation results

Successful RAG policy generations: 30; failed: 0.

This experiment calls the Rule Engine only with `use_rag=True`. It measures retrieval plus LLM policy generation and scores the answer against the documented condition reference. It does not establish that RAG is faster or more accurate than no-RAG because no control group was run.

Mean total RAG policy time: **6970.15 ms**; median: **6233.41 ms**; p95: **15867.40 ms**.
Overall valid-policy rate: **100.0%**.
Overall parameter-match rate: **70.0%**.
Overall exact-reference rate: **36.7%**.

Reference ranges remain clinician-reviewable project references, not clinical ground truth. Use the paired historical experiment only when a no-RAG control is needed.
