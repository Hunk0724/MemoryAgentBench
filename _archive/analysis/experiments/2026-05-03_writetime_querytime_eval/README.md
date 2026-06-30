# Write-time + Query-time 分別評估 Mem0 / Zep Detection Mechanism

> **日期**：2026-05-03
> **目的**：拆分 Mem0/Zep 的 detection 表現為 write-time（confusion matrix at GT-pair level）+ query-time（retrieval recall），不再用混淆的 event-level / pair-level mixed metric
> **接續**：[2026-05-02 full 100q E2E run](../2026-05-02_mem0_zep_gemini_full100/README.md) — 補上具體偵測指標的清晰拆分

---

## 0. 為什麼做這個

之前的 detection F1 / audit 數字混了兩個分析單位（event-level vs pair-level），不好懂也不好比。這次拆乾淨：

- **Write-time**：對每個 GT supersession pair 看「系統的儲存內部狀態」是否正確標 — 這是 detection mechanism 的直接評估
- **Query-time**：對每個 question 看「系統實際 retrieve 給 LLM 的內容」涵蓋率 — 這是 detection signal 是否傳到 inference 的評估

---

## 1. Write-time（confusion matrix at GT-pair level）

### 1.1 Mem0 customized × Gemini

對每個 has_pair GT (old, new) 從 `~/.mem0/history.db` 找事件分類：

| Class | 含義 | SH (74) | MH (188 hops) |
|---|---|:---:|:---:|
| **W1 correct UPDATE** | UPDATE 事件 old→new 方向對 | **45 (60.8%)** | **108 (57.4%)** |
| **W2 wrong direction** | UPDATE 事件 new→old 反向 | 0 (0%) | 3 (1.6%) |
| **W3 ADD only** (3 sub-classes) | 兩版本都 ADDed 沒 UPDATE 橋接 | 17 (23.0%) | 42 (22.3%) |
| **W4 missed** | 完全沒事件涉及這 pair | 12 (16.2%) | 35 (18.6%) |
| Total has_pair | | **74** | **188** |

對 non-has_pair singleton fact：

| Class | 含義 | SH (26) | MH (66) |
|---|---|:---:|:---:|
| S5 correct ADD | 純 ADD，無多餘 UPDATE/DELETE | 23 (88%) | 49 (74%) |
| S6 over-fire | 系統觸發了 UPDATE/DELETE | 0 | 6 (9%) |
| S7 extraction miss | 沒被抽取 | 3 (12%) | 11 (17%) |

**Over-fire 全局**：
- SH ingestion 共 fired 541 個 UPDATE，其中 **388 個（72%）不對應任何 has_pair pair**
- MH ingestion 共 fired 541 個 UPDATE，其中 **230 個（42%）不對應任何 has_pair pair**

→ Mem0 在 6k FC chunks 上**極度激進 UPDATE**（72% SH 是 spurious 跨對的 update），可能來自：
- Cross-MQuAKE-case 重疊（兩 SH 案例的相同 relation 被當成 supersession）
- Embedding similarity 把 paraphrase 當衝突
- LLM Update Memory 步驟過度判定「contradicts」

**這是「Mem0 fit FC 的 artifact」的具體證據**：高 over-fire rate 顯示 Mem0 把任何相似 fact 都當成 supersession 候選，FC 高密度 fact pool 觸發特別多。在真實對話（LongMemEval）這個過度行為可能反向（reject 太多 fact）。

### 1.2 Zep × Gemini-inference

對每個 has_pair GT 從 retrieval 跨 100 questions aggregated 的 unique edges 找：

| Class | 含義 | SH (74) | MH (188 hops) |
|---|---|:---:|:---:|
| **Z1 correct** | old edge 有 invalid_at, new edge present | 17 (23.0%) | **70 (37.2%)** |
| **Z2 wrong direction** | new edge 有 invalid_at, old edge present | 6 (8.1%) | 8 (4.3%) |
| **Z3 no invalidation** | 兩 edges 都 present, 沒設 invalid_at | **43 (58.1%)** | 58 (30.9%) |
| Z4 extraction miss (any side) | edge 沒抽出 | 7 (9.5%) | **51 (27.1%)** |
| Z5 both invalid (ambig) | 兩邊都標 invalid | 1 (1.4%) | 1 (0.5%) |
| Total has_pair | | **74** | **188** |

→ **Zep 主要失敗模式**：
- SH：58% no_invalidation — Zep 看到兩 facts 但**沒判定為衝突**（無 state-change 詞彙觸發 supersession，吻合 [zep_mechanism_deep_dive.md §Q2](../../results/oracle_a/zep_mechanism_deep_dive.md)）
- MH：27% extraction miss — Zep ingestion 漏掉很多 has_pair hop 的 fact extraction
- 兩 task wrong-direction 都 < 10%，比 Zep × GPT 既有 audit 的 SH 25/48=52% 改善很多

### 1.3 兩系統 write-time 對比

| | Mem0 W1 correct | Zep Z1 correct | Mem0 missed/W3+W4 | Zep no/extraction miss |
|---|:---:|:---:|:---:|:---:|
| FC-SH | **61%** | 23% | 39% | 67% |
| FC-MH (hops) | **57%** | 37% | 41% | 58% |

→ **Mem0 detection 顯著強於 Zep**（SH +38pp / MH +20pp），但 Mem0 over-fire 嚴重（72% / 42% 的 UPDATE 是 spurious）。

---

## 2. Query-time（retrieval recall per question）

對每個 has_pair question 看 top-K retrieved 內容：

| System / Task | n | new_recall @K | old_recall @K | both_in_topK | Zep old_invalid_signal |
|---|:---:|:---:|:---:|:---:|:---:|
| Mem0 SH (K=100) | 74 | **87.8%** | **5.4%** | 2.7% | — |
| Mem0 MH (K=100) | 100 | **77.1%** | **9.2%** | 2.8% | — |
| Zep SH (K=10) | 74 | **100%** | **100%** | **100%** | 24.3% |
| Zep MH (K=10) | 100 | **90%** | **94.8%** | **87.7%** | 22.4% |

### 2.1 Mem0 paradigm = filter at write

- new_recall 78-88%：Mem0 把 current fact 給 LLM 看到的比例
- **old_recall 只 5-9%**：outdated fact 被 UPDATE/DELETE 後不在 vector store top-100 → **LLM 幾乎看不到 outdated**
- both_in_topK 只 3%：絕少數情況同時看到 old+new
- 對應 1.1 W1 60% rate：當 UPDATE 對的時候 outdated 完全清乾淨
- 風險：當 UPDATE 沒對（W3/W4 共約 40%），retrieved 可能完全沒 new fact（19%-23%）→ LLM 答錯

### 2.2 Zep paradigm = annotation at inference

- new_recall 90-100%：Zep 幾乎都把 current fact 給 LLM
- **old_recall 也 95-100%**：但 outdated 也都在 retrieved — Zep 沒 filter
- **both_in_topK 88-100%**：LLM 88%+ 機率同時看到 old + new
- **old_invalid_signal 只 22-24%**：但只 22% 那 23% 的 old fact 被正確標 invalid_at — **77% 的 has_pair LLM 看到雙版本卻沒清楚的 timestamp 訊號**

→ **Zep MH E2E 8% 的根本原因明確了**：87.7% 題目 LLM 都看到 old + new 兩版本，但只 22.4% 有正確的 invalid_at 訊號 → 77% 機率 LLM 看到雙版本但沒線索選 current → 大半依賴 world knowledge → 對 counterfactual GT 必錯。

---

## 3. 對應 E2E 結果（從 [2026-05-02 run](../2026-05-02_mem0_zep_gemini_full100/)）

| | Mem0 customized × Gemini | Zep × Gemini |
|---|:---:|:---:|
| FC-SH E2E | 77% | 79% |
| FC-MH E2E | 43% | 8% |
| FC-MH W1/Z1 correct (write) | 57% | 37% |
| FC-MH new_recall@K (query) | 77% | 90% |
| FC-MH old_recall@K (query) | 9% | 95% |
| FC-MH old_invalid signal (query) | n/a | 22% |

→ Mem0 paradigm work 的時候完全 unlock LLM（57% detect → 77% retrieve → 43% E2E，loss 主要在 detection）
→ Zep paradigm 卡在 inference signal interpretation（37% detect → 90% new retrieve 但 87% both → 8% E2E，loss 主要在 LLM 不信 timestamp）

---

## 4. 對 Mem0 「fit FC artifact」的判讀

從 1.1 的 W3+W4 = 40% missed + 72% over-fire 兩個指標看：

**Mem0 在 FC 上的特殊行為**：
- 高 W1 (60%) + 高 W3 ADD-only (22%) + 高 over-fire (72%) 同時出現
- 解釋：Mem0 的 LLM Update Memory step 在 FC 高密度 fact pool 上**過度敏感** — 同時觸發很多正確的 UPDATE（W1）+ 很多 spurious UPDATE（over-fire）+ 漏掉一些 has_pair（W3/W4）
- 這個行為跟 FC structure 強相關（每 chunk 25 facts，所有都是 X is associated with Y 結構）

**真實 LongMemEval 對話下的預測**：
- chunks 不再是純 fact list（含 dialogue / context / questions）→ extraction 抽 fact 數會降
- LLM Update Memory 的判斷對「分散在 dialogue 中的 fact」可能更保守 → over-fire 降，但 W1 也降
- → Mem0 的 detection 強處（W1 60%）可能是 FC 限定，true over-fit 假設**未排除**

**驗證實驗**（待跑）：
- 32k FC：context 變大但仍是純 fact list，看 W1 是否保持 60%
- LongMemEval-KU：完全不同 chunk 結構，是 fit-FC 假設的關鍵反證測試

---

## 5. 檔案地圖

```
2026-05-03_writetime_querytime_eval/
├── README.md                           ← 本檔
├── scripts/
│   ├── rerun_full_retrieval.py         ← 重新 ingest + 全 retrieval dump (Mem0+Zep)
│   ├── eval_writetime.py               ← write-time confusion matrix (W1-W4 / Z1-Z4)
│   └── eval_querytime.py               ← query-time recall metrics
└── results/
    ├── mem0_full_retrieval_{sh,mh}.json    ← per-question top-100 retrieved memories
    ├── zep_full_retrieval_{sh,mh}.json     ← per-question top-10 edges/nodes/episodes + context_block
    ├── writetime_eval.json + .md
    └── querytime_eval.json + .md
```

外部依賴：
- `~/.mem0/history.db` (Mem0 events)
- `analysis/results/{sh,mh}_512_mquake_analysis.json` (FC GT)
- `.cache/mem0_eval_qdrant_{sh,mh}/` (持久化 qdrant store, 用 `on_disk=True`)

重跑：
```bash
cd /home/yhchiang/MemoryAgentBench
# Re-ingest + full retrieval (Mem0 + Zep, ~10 min)
conda run -n MABench --no-capture-output python \
  analysis/experiments/2026-05-03_writetime_querytime_eval/scripts/rerun_full_retrieval.py

# Analysis (純 local, 無 LLM call)
python analysis/experiments/2026-05-03_writetime_querytime_eval/scripts/eval_writetime.py
python analysis/experiments/2026-05-03_writetime_querytime_eval/scripts/eval_querytime.py
```

---

## 6. 對 paper 主張的影響

1. **「Mem0/Zep detection F1 < 50%」更精確的描述**：Mem0 W1 57-61%，Zep Z1 23-37%。Mem0 detection 顯著強於 Zep
2. **paradigm 差異 quantified**：Mem0 (filter) 把 LLM 看到 outdated 的機率從 100% 降到 5-9%；Zep (annotation) 維持 95-100% old visibility，靠 22% invalid_at signal 區分
3. **Mem0 over-fire 警示**：72% of UPDATE events 是 spurious，Mem0 detection performance 在 FC 上有 over-fit 風險，需 32k / LongMemEval 驗證
4. **Zep 的「inference trust gap」**：87.7% 題目 LLM 看到 old+new 但只 22% 有 invalid_at 訊號 — Zep design 把責任丟給 LLM 但 LLM 解讀 timestamp 能力弱
