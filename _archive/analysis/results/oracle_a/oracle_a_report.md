# Oracle A 實驗報告

> 實驗日期：2026-04-17
> 目的：驗證「retrieved context 中新舊事實混雜是 HippoRAG-v2 在知識衝突任務失敗的主因」

---

## 1. 實驗設計

### 1.1 核心思路

Oracle A 是一個 **上界實驗 (upper-bound experiment)**：假設有一個完美的 Conflict Filter，
能在 retrieval 後精確移除所有含舊事實的 passage，只保留新事實，觀察 LLM 的 Acc 能提升多少。

### 1.2 操作定義

- **移除對象**：含有舊版事實 (old fact) 的 passage（整個 passage 移除，不做 sentence-level 編輯）
- **保留對象**：其餘 passage，包含新版事實 (GT/new fact) 的 passage
- **Passage 編號**：移除後不重新編號，保留原始 Passage N 編號
- **Prompt 格式**：與原始 HippoRAG-v2 實驗完全一致

### 1.3 Prompt 格式（與原始實驗一致）

```
System: "As an advanced reading comprehension assistant, your task is to analyze
         text passages and corresponding questions meticulously..."

User (one-shot): [Wikipedia Title example docs + question]
Assistant (one-shot): [example answer]

User: "Wikipedia Title: {passage_text_1}\n\n
       Wikipedia Title: {passage_text_2}\n\n
       ...\n\n
       Question: Pretend you are a knowledge management system. Each fact in the
       knowledge pool is provided with a serial number at the beginning, and the
       newer fact has larger serial number...{question}\nAnswer:\nThought: "
```

### 1.4 LLM 參數

| 參數 | 值 | 備註 |
|---|---|---|
| Model | gpt-4o-mini | 與原始實驗一致 |
| Temperature | 0 | HippoRAG BaseConfig default |
| max_completion_tokens | 2048 | HippoRAG BaseConfig default |
| Seed | 0 | |

---

## 2. 題目篩選

### 2.1 篩選流程

Oracle A 需要精確定位每題的舊事實 passage 並移除。篩選條件：

1. **Old fact 已被 HippoRAG-v2 檢索到**：舊事實存在於 top-10 retrieved passages 中
2. **GT (new) fact 已被檢索到**：新事實也在 top-10 中
3. **Old 和 GT 不在同一個 passage**：移除 old passage 後，GT passage 仍保留

### 2.2 事實定位方法

使用兩階段 matching 定位事實在 passage 中的位置：

1. **Word-boundary 序號匹配**（主要）：用 regex `(?:^|[\s])SEQ\.\s` 搜尋序號，
   避免 `31.` 誤匹配 `331.` 等情況
2. **Exact text fallback**（備用）：當序號因 chunk 邊界被切斷時，
   以事實文字做 substring matching

此方法修正了原始分析腳本中 `find_fact_in_passages_numbered()` 的序號匹配 bug
（該函式未使用 word boundary，導致部分 `old_passage_rank` 指向錯誤的 passage）。

### 2.3 篩選結果

#### FC-SH（74 題 has_conflict_pair）

| 狀態 | 數量 | 說明 |
|---|:---:|---|
| **usable** | **64** | 可執行 Oracle A |
| same_passage | 9 | Old 與 GT 在同一 chunk，移除會連帶丟失 GT |
| gt_not_retrieved | 1 | GT 事實不在 top-10 passages |

#### FC-MH（100 題）

| 分組 | 題數 | Usable | 排除原因 |
|---|:---:|:---:|---|
| 2-hop, 1-conflict | 25 | **21** | same_passage: 4 |
| 2-hop, 2-conflict | 36 | **24** | gt_not_safe: 3, old_not_all_found: 2, same_passage: 7 |
| 3-hop, 1-conflict | 5 | **5** | — |
| 3-hop, 2-conflict | 9 | **5** | gt_not_safe: 3, same_passage: 1 |
| 3-hop, 3-conflict | 10 | **5** | gt_not_safe: 2, same_passage: 3 |
| 4-hop, 1-conflict | 3 | **3** | — |
| 4-hop, 2-conflict | 3 | **1** | gt_not_safe: 1, same_passage: 1 |
| 4-hop, 3-conflict | 7 | **2** | old_missing+same_passage: 1, old_not_all_found: 2, same_passage: 2 |
| 4-hop, 4-conflict | 2 | **0** | gt_not_safe: 1, same_passage: 1 |
| **整體** | **100** | **66** | 排除 34 題 |

#### 排除原因說明

| 原因 | SH | MH | 說明 |
|---|:---:|:---:|---|
| same_passage | 9 | 19 | chunk_size=512 導致新舊事實在同一 chunk |
| old_not_all_found | 0 | 4 | 舊事實未被 HippoRAG-v2 檢索到 top-10 |
| gt_not_safe | 1 | 10 | 新事實未被檢索到，或移除 old 後 GT 也不在 remaining |
| old_missing+same_passage | 0 | 1 | 複合原因 |

**重要驗證**：所有 not-found 的事實均已確認存在於完整 6k context（455 facts, seq 0-454）中，
文字完全匹配。這些是 HippoRAG-v2 的 retrieval 限制（top-10 未涵蓋），非 dataset 問題。

---

## 3. 實驗結果

### 3.1 FC-SH 結果

| | Acc | 正確數 / 總數 |
|---|:---:|:---:|
| Baseline | 57.8% | 37/64 |
| **Oracle A** | **81.2%** | **52/64** |
| **提升** | **+23.4pp** | **+15** |

答題狀態變化：

| 變化 | 數量 | 佔比 |
|---|:---:|:---:|
| 維持正確 (correct→correct) | 29 | 45.3% |
| 翻轉為正確 (wrong→correct) | 23 | 35.9% |
| 翻轉為錯誤 (correct→wrong) | 8 | 12.5% |
| 維持錯誤 (wrong→wrong) | 4 | 6.2% |

### 3.2 FC-MH 結果

| | Acc | 正確數 / 總數 |
|---|:---:|:---:|
| Baseline | 16.7% | 11/66 |
| **Oracle A** | **42.4%** | **28/66** |
| **提升** | **+25.8pp** | **+17** |

#### Per-group breakdown

| 分組 | N | Baseline Acc | Oracle A Acc | Δ |
|---|:---:|:---:|:---:|:---:|
| 2-hop, 1-conflict | 21 | 7/21 (33%) | 11/21 (52%) | +4 |
| 2-hop, 2-conflict | 24 | 1/24 (4%) | 10/24 (42%) | +9 |
| 3-hop, 1-conflict | 5 | 2/5 (40%) | 3/5 (60%) | +1 |
| 3-hop, 2-conflict | 5 | 0/5 (0%) | 3/5 (60%) | +3 |
| 3-hop, 3-conflict | 5 | 0/5 (0%) | 0/5 (0%) | +0 |
| 4-hop, 1-conflict | 3 | 1/3 (33%) | 1/3 (33%) | +0 |
| 4-hop, 2-conflict | 1 | 0/1 (0%) | 0/1 (0%) | +0 |
| 4-hop, 3-conflict | 2 | 0/2 (0%) | 0/2 (0%) | +0 |

答題狀態變化：

| 變化 | 數量 |
|---|:---:|
| 翻轉為正確 (wrong→correct) | 20 |
| 翻轉為錯誤 (correct→wrong) | 3 |

翻轉為錯誤的 case：

- query_1（2-hop, 1-conflict）：
  GT=Rodez, Oracle A 預測=Moscow.
- query_26（2-hop, 1-conflict）：
  GT=Peter Diamandis, Oracle A 預測=None.
- query_45（2-hop, 1-conflict）：
  GT=London, Oracle A 預測=Gads Hill Place.

---

## 4. 分析與討論

### 4.1 假說驗證：新舊混雜確實是主要失敗原因之一

SH +23.4pp、MH +25.8pp 的提升證實，retrieved context 中新舊事實的混雜
是導致 HippoRAG-v2 在知識衝突任務上失敗的重要原因。LLM 即使在 prompt 中
被指示「序號越大越新越正確」，面對同時出現的新舊事實仍大量採信舊版本。

### 4.2 Oracle A ceiling 遠低於 100%：存在其他失敗因素

即使在完全沒有舊事實干擾的理想條件下：

- **SH Oracle A = 81.2%**（仍有 12/64 題答錯）
- **MH Oracle A = 42.4%**（仍有 38/66 題答錯）

這表明除了知識衝突外，還有其他因素限制了 Acc：

1. **LLM 多跳推理能力不足**：MH 2-hop 在無衝突下也只有 ~50%，
   3-hop 3-conflict 和 4-hop 始終為 0%
2. **Entity confusion**：同 passage 中的其他相似事實可能造成干擾
3. **Parametric knowledge override**：LLM 的內建知識可能覆蓋 context 中的反事實

### 4.3 Conflict hops 數量的影響

MH 結果顯示，Oracle A 的改善幅度與 conflict hops 數量相關：

- **低 conflict hops（1-2）**：改善顯著（2-hop 2-conflict: 4%→42%）
- **高 conflict hops（3+）**：幾乎無改善（3-hop 3-conflict: 0%→0%）

這暗示當每一跳都存在衝突時，問題已不僅是「context 有舊事實」，而是多跳鏈式推理
本身的能力瓶頸——LLM 無法在多個推理步驟中持續正確選擇。

---

## 5. 檔案清單

| 檔案 | 說明 |
|---|---|
| `analysis/oracle_a_phase1_validate.py` | Phase 1：passage 定位與篩選驗證腳本 |
| `analysis/oracle_a_phase2_inference.py` | Phase 2：LLM inference 腳本 |
| `analysis/results/oracle_a_corrected_ranks.json` | 修正後的 passage rank（SH + MH） |
| `analysis/results/oracle_a/oracle_a_sh_results.json` | SH Oracle A per-question 結果 |
| `analysis/results/oracle_a/oracle_a_mh_results.json` | MH Oracle A per-question 結果 |

---

## 6. 實驗設置回顧

| 項目 | 值 |
|---|---|
| RAG 系統 | HippoRAG-v2（NV-Embed-v2 + KG + PPR） |
| LLM | GPT-4o-mini |
| Chunk size | 512 tokens |
| Top-k | 10 |
| Context | 6k（455 個有序事實句，seq 0-454） |
| SH 題數 | 100 題（74 has_pair → 64 usable） |
| MH 題數 | 100 題（66 usable） |
| 資料來源 | MQuAKE-CF.json（知識衝突 ground truth） |