# Write-time Evaluation

> Confusion matrix at GT-pair level: how each system handled each FC supersession.

---

## Mem0 customized × Gemini (chunk=512)

| Class | SH | MH (hops) |
|---|:---:|:---:|
| W1_correct_UPDATE | 45 | 108 |
| W2_wrong_direction | 0 | 3 |
| W3_ADD_new_only | 6 | 13 |
| W3_ADD_old_only | 5 | 16 |
| W3_ADD_only_both | 6 | 13 |
| W4_missed | 12 | 35 |
| **total has_pair** | **74** | **188** |

Singleton (non-conflict) facts:
| Class | SH | MH |
|---|:---:|:---:|
| S5_correct_ADD | 23 | 49 |
| S6_over_fire | 0 | 6 |
| S7_extraction_miss | 3 | 11 |
| **total singletons** | **26** | **66** |

Over-fire (UPDATE events not matching any GT pair):  SH 388 / 541 total UPDATEs.  MH 230 / 541 total UPDATEs.

---
## Zep × Gemini-inference (chunk=512, edges aggregated from per-question retrievals)

| Class | SH | MH (hops) |
|---|:---:|:---:|
| Z1_correct | 17 | 70 |
| Z2_wrong_direction | 6 | 8 |
| Z3_no_invalidation | 43 | 58 |
| Z4_extraction_miss | 1 | 20 |
| Z4_new_extraction_miss | 4 | 18 |
| Z4_old_extraction_miss | 2 | 13 |
| Z5_both_invalid_ambig | 1 | 1 |
| **total has_pair** | **74** | **188** |

Aggregated unique edges: SH 355 (53 with invalid_at);  MH 349 (67 with invalid_at)
