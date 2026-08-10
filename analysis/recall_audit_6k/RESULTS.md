# Recall decomposition — local backbones (FC-SH 6k, has_pair N=74)

回應 [`docs/handoff/GX10_gemma_retrieval_check.md`](../../docs/handoff/GX10_gemma_retrieval_check.md)。
把 checklist item-3 的 `gt_new∈top100` 拆成兩個獨立成因,判定「檢索 vs 抽取」哪個是瓶頸。

## 重現方式(零 API 成本,~7.5MB committed 資料)

```bash
conda activate MABench
python analysis/recall_audit_6k/recall_decomposition_6k.py
```

讀取:各 backbone `extraction_cache_p1_6k.json`(bank,A 欄)+ `pools_slim_6k_no_p5.json`(top-100 slim,B 欄)
+ `sh_6k_mquake_analysis.json`(GT)+ `compute_pool_acc_crosstab.classify_pool_state`(matcher v4)。

## 結果

| backbone | cache facts | **A. gt_new∈bank**(抽取 recall)| **B. gt_new∈top100** | **C. retrieval@100 \| in-bank** |
|:--|:--:|:--:|:--:|:--:|
| gemma3-1b | 375 | 78% | 78% | **100%** |
| gemma3-4b | 381 | 86% | 86% | **100%** |
| gemma3-12b | 456 | 100% | 100% | 100% |
| gemma3-27b | 455 | 100% | 100% | 100% |
| gemma2-9b | 455 | 100% | 100% | 100% |
| llama3.1-8b | 338 | 80% | 80% | **100%** |
| qwen2.5-7b | 451 | 100% | 100% | 100% |
| mistral-7b | 452 | 92% | 92% | **100%** |

## 結論

**A 欄 == B 欄,C 欄全部 = 100%(八個 backbone 無一例外)。**

→ **檢索完全不是瓶頸**:只要 gt_new 在 bank 裡,top-100 一定 retrieve 得到(retrieval@100|in-bank = 100%)。所有 `gt_new∈top100` 的 miss **100% 都是抽取 miss**(gt_new 沒被 P1 抽進 bank),與 backbone extraction 品質相關(cache facts:llama 338→80%、gemma3-1b 375→78%),而非檢索器失效(embedder = text-embedding-3-small,與 backbone 無關)。

**論文含義**:此抽取 confound 由各 backbone 內**所有 method 共用同一 per-backbone bank** → 只影響**跨 backbone 絕對值**,不影響**同 backbone 內 method 比較**。

## Bundle 內容(給跨機重現)

| 檔 | 用途 |
|:--|:--|
| `pools_slim_6k_no_p5.json`(7.5MB)| 8 backbone × 74 has_pair 的 top-100 slim:`retrieved_memories[{memory, ordinal}]` + `memories_str`。schema 與原始 dump 相容 |
| `recall_decomposition_6k.py` | 上表的 standalone 重現腳本 |
| `system_prompt.json` | 答題 system prompt(全域 1 份,原本每題重複)|
| `analysis/results/p1_caches__gemma3-{1b,4b,12b,27b}/extraction_cache_p1_6k.json` | A 欄的 bank(4 個 gemma3,本 commit 一併補上;其餘 4 個已在 repo)|

> 已丟棄(冗餘/可還原,見 handoff 討論):`resolved_pool`(文字被 memories_str 涵蓋、metadata 可由 triple_cache 還原)、per-query `system_prompt`(改全域 1 份)、`response`(= results.json output)、hash/score/created_at。
> 保留的 `ordinal` + `memories_str` 非 recall 表所需,而是為了順帶保住 freshness/serial 與 pool-collapse(gemma2 根因)分析。
