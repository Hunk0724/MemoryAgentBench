# Detection × Retrieval × Answer cascade by num_hops

> Only has_pair questions (n_has_pair > 0). 100 qualifying questions.

---

## MEM0

| num_hops | detect bucket | n questions | avg detect % | avg retrieve_new % | EM |
|:---:|:---:|:---:|:---:|:---:|:---:|
| 2 | all_correct | 23 | 100% | 93% | 13/23 = 57% |
| 2 | partial | 19 | 50% | 82% | 8/19 = 42% |
| 2 | none | 19 | 0% | 58% | 6/19 = 32% |
| 3 | all_correct | 7 | 100% | 100% | 6/7 = 86% |
| 3 | partial | 12 | 57% | 85% | 5/12 = 42% |
| 3 | none | 5 | 0% | 50% | 1/5 = 20% |
| 4 | all_correct | 4 | 100% | 100% | 2/4 = 50% |
| 4 | partial | 7 | 54% | 51% | 1/7 = 14% |
| 4 | none | 4 | 0% | 46% | 1/4 = 25% |

## ZEP

| num_hops | detect bucket | n questions | avg detect % | avg retrieve_new % | EM |
|:---:|:---:|:---:|:---:|:---:|:---:|
| 2 | all_correct | 14 | 100% | 89% | 3/14 = 21% |
| 2 | partial | 17 | 50% | 88% | 0/17 = 0% |
| 2 | none | 30 | 0% | 95% | 5/30 = 17% |
| 3 | all_correct | 5 | 100% | 100% | 0/5 = 0% |
| 3 | partial | 11 | 52% | 92% | 0/11 = 0% |
| 3 | none | 8 | 0% | 69% | 0/8 = 0% |
| 4 | all_correct | 1 | 100% | 100% | 0/1 = 0% |
| 4 | partial | 7 | 51% | 81% | 0/7 = 0% |
| 4 | none | 7 | 0% | 95% | 0/7 = 0% |

## Aggregate by num_hops only (detection bucket merged)

| num_hops | n | Mem0 detect % | Mem0 new in retrieval % | Mem0 EM | Zep detect % | Zep new in retrieval % | Zep both visible % | Zep EM |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| 2 | 61 | 53% | 79% | 27/61 = 44% | 37% | 92% | 90% | 8/61 = 13% |
| 3 | 24 | 58% | 82% | 12/24 = 50% | 44% | 86% | 84% | 0/24 = 0% |
| 4 | 15 | 52% | 63% | 4/15 = 27% | 31% | 89% | 83% | 0/15 = 0% |