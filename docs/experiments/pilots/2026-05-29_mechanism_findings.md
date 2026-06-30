# Mechanism Findings — 2026-05-29 night

> **目的**:把 detection-action × retrieval × answer 三向分析的 pilot 結果記錄為 paper §6.4 的初稿
> **資料源**:既有 Mem0g MH 6k pilot(temp=0/0.1,backtick wrap),align/mcore 已 ready
> **新分析工具**:[analysis/compute_detection_action.py](../../analysis/compute_detection_action.py)、[analysis/compute_3way.py](../../analysis/compute_3way.py)

---

## 1. Mem0g MH 6k — Detection-as-action 結果

### 1.1 Operation-level 統計

330 ingestion events 從 12 chunks 抽出。事件型態分佈:

| Event 型態 | n | 占比 |
|---|---:|---:|
| ADD | 255 | 77.3% |
| UPDATE | 75 | 22.7% |
| DELETE | 0 | 0% |
| NONE | 0 | 0% |

→ **mem0g 偏好「UPDATE replace」而不是「DELETE old + ADD new」** — 上游 L2 update_memory prompt 引導出來的行為。

### 1.2 與 GT(188 has_pair hops)對照

| 指標 | n | 解讀 |
|---|---:|---|
| **TP**(UPDATE 在 GT 老事實)| **71** | 正確識別衝突 |
| FP_kill_new(UPDATE 在 GT 新事實)| 2 | ⚠️ **catastrophic** — 把對的答案刪了 |
| FP_other(UPDATE 在無關事實)| 2 | 假警報 |
| **FN**(GT 老事實沒被 UPDATE)| **72** | 漏偵測,事實留在 vector store |

| 比率 | 值 | Paper 意義 |
|---|---:|---|
| **Precision** | **0.947** | mem0g 出手 95% 對 — 判斷品質高 |
| **Recall** | **0.497** | **只抓到一半 GT 衝突** ← paper 核心 limitation |
| **F1** | 0.651 | |
| **UPDATE 內容正確率** | **100%(71/71)** | 出手對的情況下,替換文字 100% 匹配 GT |

### 1.3 Paper §6.4 mechanism story 初稿

> **Write-time conflict detection in mem0g exhibits a sharp precision/recall asymmetry**. When triggered, mem0g UPDATEs the correct memory 94.7% of the time, and the replacement content matches the ground-truth new fact 100% of the time. However, recall is only 49.7% — half of the GT conflict pairs never trigger any UPDATE/DELETE event during ingestion, leaving stale facts in the vector store. **This is a fundamental limitation of per-chunk write-time detection: each ingestion call sees only the current chunk's content plus a small slice of existing memories (top-5 vector neighbours), which is insufficient to spot cross-chunk semantic conflicts.**

---

## 2. Mem0g MH 6k — D × R × A 三向 contingency

100 queries(全 has_pair):

### 2.1 Marginal rates

| | rate |
|---|---:|
| D rate(any UPDATE/DELETE on this query's pair)| 77.0% |
| R rate(retrieval clean: gt_in_memories 全 ✓ AND old_in_memories 全 ✗)| 55.0% |
| A rate(EM)| 43.0% |

### 2.2 8 cells

| Cell | n | % | 詮釋 |
|---|---:|---:|---|
| **D✓R✓A✓ clean win** | 34 | 34.0% | 方法 work |
| D✓R✓A✗ inference fail | 11 | 11.0% | 給 LLM 對的 context 但仍錯 |
| D✓R✗A✗ **retrieval fail** | **32** | **32.0%** | **debug 對但 retrieval 還是漏**(cross-pair contamination)|
| D✓R✗A✓ noise win | 0 | 0.0% | |
| D✗R✓A✓ retrieval-only win | 8 | 8.0% | 沒 detect 但碰巧 retrieval 對 |
| D✗R✓A✗ retrieval-only fail | 2 | 2.0% | retrieval 對 LLM 仍錯 |
| D✗R✗A✓ noise win | 1 | 1.0% | |
| D✗R✗A✗ full fail | 12 | 12.0% | |

### 2.3 條件機率(mechanism evidence,paper 核心數字)

| 條件 | 機率 | 樣本 | 解讀 |
|---|---:|---:|---|
| **P(A \| R=1)** | **76.4%** | n=55 | 給 LLM 乾淨 context,76% 答對 |
| **P(A \| R=0)** | **2.2%** | n=45 | 給髒 context,基本上不可能對 |
| P(A \| D=1, R=1)| 75.6% | n=45 | 兩者皆對 |
| P(A \| D=1, R=0)| 0.0% | n=32 | detect 對但 retrieval 漏 → **零回答正確** |
| P(A \| D=0, R=1)| 80.0% | n=10 | 沒 detect 但 retrieval 乾淨,還是 80% 對 |
| P(A \| D=0, R=0)| 7.7% | n=13 | 兩者皆失 → 噪音作答 |
| P(R \| D=1)| 58.4% | n=77 | detect 對提升 retrieval 乾淨機率 |
| P(R \| D=0)| 43.5% | n=23 | 沒 detect 也可能 retrieval 乾淨(運氣)|

### 2.4 Paper §6.4 mechanism story 延伸

> **The dominant causal chain is D → R → A**. Retrieval cleanliness is the single strongest predictor of answer correctness: P(A|R=1)=76.4% vs P(A|R=0)=2.2% — a 74-percentage-point gap. Detection contributes to A only **indirectly** via R: P(R|D=1)=58.4% vs P(R|D=0)=43.5% (a modest 15-pp shift). The most striking failure mode is "**detected but leaked**" (32% of queries, D✓R✗A✗): mem0g correctly identified the conflict and emitted an UPDATE, but cross-pair contamination — other stale facts from semantically-related conflict pairs — still surfaced at retrieval time and confused the LLM. **This vindicates moving conflict detection from per-chunk write-time to per-query query-time**, where the method can see the actual retrieval candidates and filter them cross-pair before passing context to the LLM.

---

## 3. 對 paper §6.4 mechanism table 的 implication

整理 paper §6.4 主表(initial draft):

| Method | EM | D-precision | D-recall | P(R=1) | P(A\|R=1) | P(A\|R=0) | dominant failure cell |
|---|---:|---:|---:|---:|---:|---:|---|
| LCA | 16% | n/a | n/a | n/a | n/a | n/a | (no D/R framework)|
| Mem0(vector)| 50% | TBD | TBD | TBD | TBD | TBD | TBD |
| **Mem0g**(KG, MABench-as-is)| **43%**(這份分析)| **0.947** | **0.497** | **55%** | **76.4%** | **2.2%** | **D✓R✗A✗ 32%** |
| Mem0g-prompt-aware | 待跑 | 同 mem0g(D 不變)| 同 | TBD | TBD(預期 R 不變,但 LLM 收 relations 可能更好)| TBD | TBD |
| HippoRAG-v2 | 29% | n/a(無 detection)| n/a | TBD | TBD | TBD | 大量 R✗(無 conflict mechanism)|
| Ours(目標)| > 50% | ≥ 0.95(維持 precision)| **≥ 0.85**(query-time 解 recall)| ≥ 75% | ≥ 80% | ≥ 5%(query-time filter)| 大幅減少 D✓R✗A✗ |

**Ours 的成功條件**(從這次分析推導):
1. **Recall ≥ 0.85**(query-time 補 mem0g write-time 漏的 50%)
2. **P(R=1) ≥ 75%**(query-time filter 把 cross-pair contamination 也清掉)
3. **EM > 50%**(at least 打贏 Mem0 vector baseline)

### 3.1 為什麼這個 frame 對 paper 有用

- 不只報「我們 EM 高」,也報「我們因為什麼機制 EM 高」
- 把 D(write-time) → R(retrieval cleanliness) → A(answer) 的 causal chain 顯式拆出來
- 直接給 ablation table 可預測的格子:
  - Ours-no-detection vs Ours → 看 D 的真實貢獻
  - Ours-write-time vs Ours-query-time → 看 detection-timing 的貢獻
  - Ours-no-graph vs Ours → 看 multi-hop graph 的貢獻

---

## 4. 下一步分析 TODO

### 4.1 立刻可做(資料 ready)

- ✅ Mem0g MH 6k(已完成,上面數字)

### 4.2 跑完 b9nad0ox1 + smoke 後

- Mem0 × MH 6k × temp=0.7 × 3 trials(算 mean ± std + detection-action + 3way)
- Mem0g-prompt-aware × MH 6k × temp=0.7 × 1 trial(detection-action + 3way)
- 比較 Mem0(flat) vs Mem0g(graph as-is) vs Mem0g(prompt-aware)— 三者 detection 應一致(因 ingestion 不變),但 R/A 可能不同

### 4.3 後續(等更多 cells)

- HippoRAG-v2 × MH 6k × temp=0.7 — R 應低、無 D 訊號
- 全部 cells 用 detection-action + 3way 跑一遍 → 主表 §6.4 ready

---

## 5. 開放問題(對 chat 討論)

1. **D 信號定義**:我們現在用 "any UPDATE/DELETE on this query's hop pair" = D=1。是否要嚴格成 "all has_pair hops 都被 detect" = D-strict?(影響 D rate 與 conditional 數字)
2. **R 信號定義**:我們用 "all has_pair hops gt_in_memories 且 old_not_in_memories"。是否要 hop-level 算 R rate(不是 query-level)?(更細,但會弱化 query-level mechanism narrative)
3. **D ✓ R ✗ 32% 的成因**:目前是「cross-pair contamination」假說。是否要寫個 sub-analysis,展示具體 contamination 事件(哪些 query 的 hop A 的舊事實污染了 hop B 的 retrieval)?

---

**End of 2026-05-29 mechanism findings**
