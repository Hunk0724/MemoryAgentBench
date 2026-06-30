# Query-time Retrieval Evaluation

> For each FC has_pair question, check whether top-K retrieved content
> covers the GT chain new/old facts.

---

## Aggregate metrics

| System / Task | n questions | new_recall @K | old_recall @K | both_in_topK | old_invalid_signal (Zep only) |
|---|:---:|:---:|:---:|:---:|:---:|
| Mem0 SH (K=100) | 74 | 87.8% | 5.4% | 2.7% | — |
| Mem0 MH (K=100) | 100 | 77.1% | 9.2% | 2.8% | — |
| Zep SH (K=10) | 74 | 100.0% | 100.0% | 100.0% | 24.3% |
| Zep MH (K=10) | 100 | 90.0% | 94.8% | 87.7% | 22.4% |

**Interpretation**:
- new_recall = fraction of GT new facts the LLM gets to see
- old_recall = fraction of GT old facts also leaked into prompt (distractor)
- both_in_topK = LLM sees both — needs metadata to disambiguate (Zep) or relies on store-cleanup (Mem0)
- old_invalid_signal_rate (Zep only) = fraction where Zep correctly tagged the old as invalid_at

---