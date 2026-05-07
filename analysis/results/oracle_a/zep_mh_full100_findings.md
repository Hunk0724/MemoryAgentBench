# Zep FC-MH 完整 100 題分析（chunk=512）

> 實驗日期：2026-04-21/22
> 實驗 setup：Zep chunk_size=512 在 FC-MH 6k 100 題

---

## 0. 最重要的發現：Zep 在 MH 上意外勝過 HippoRAG-v2

| 系統 | FC-SH Acc | FC-MH Acc |
|---|:---:|:---:|
| HippoRAG-v2 chunk=512 | 69% | **11%** |
| **Zep chunk=512** | 70% | **28%** (+17pp) |

**這個結果打翻了我們原本的預期**：原本以為 Zep 在多跳更慘（因為無 multi-hop retrieval），
但實際上 Zep MH 整體 Acc 比 HippoRAG-v2 高 17pp，尤其在 2-hop, 2-conflict 上高出 30pp。

---

## 1. Per-group 完整結果對比

| 分組 | N | Zep | HippoRAG | 差距 |
|---|:---:|:---:|:---:|:---:|
| 2-hop, 1-conflict | 25 | 10/25 (40%) | 7/25 (28%) | **+12pp** |
| **2-hop, 2-conflict** | 36 | **12/36 (33%)** | **1/36 (3%)** | **+30pp** 🚀 |
| 3-hop, 1-conflict | 5 | 2/5 (40%) | 2/5 (40%) | 持平 |
| 3-hop, 2-conflict | 9 | 1/9 (11%) | 0/9 (0%) | +11pp |
| 3-hop, 3-conflict | 10 | 1/10 (10%) | 0/10 (0%) | +10pp |
| 4-hop, 1-conflict | 3 | 1/3 (33%) | 1/3 (33%) | 持平 |
| 4-hop, 2-conflict | 3 | 0/3 (0%) | 0/3 (0%) | 持平 |
| 4-hop, 3-conflict | 7 | 1/7 (14%) | 0/7 (0%) | +10pp |
| 4-hop, 4-conflict | 2 | 0/2 (0%) | 0/2 (0%) | 持平 |
| **整體** | **100** | **28%** | **11%** | **+17pp** |

---

## 2. 衝突決策的超高準確率（95.2%）

MH run 中 Zep 標註了 **67 個不同的 edges 為 INVALID**，用嚴格的 (s,r) counterpart 匹配判斷：

| 分類 | 數量 | 佔比 |
|---|:---:|:---:|
| **Correct**（invalidated 較小 seq，符合 FC 規則） | 59 | 88.1% |
| **Wrong**（invalidated 較大 seq，違反 FC 規則） | 3 | 4.5% |
| **False positive**（無 FC counterpart 仍 invalidate） | 4 | 6.0% |
| Unknown（無法匹配 FC 事實） | 1 | 1.5% |

**在有真實衝突對的 62 個決策中：59/62 = 95.2% 正確率**

### 與 SH 的對比（同 FC context，不同 ingestion run）

| 指標 | SH v2（strict） | MH v2（strict） | 差距 |
|---|:---:|:---:|:---:|
| Invalidated unique facts | 48 | 67 | MH 多 40% |
| Correct | 20 | **59** | MH 多 3 倍 |
| Wrong | 25 | **3** | MH 只有 1/8 |
| False positive | 2 | 4 | 接近 |
| **準確率（measurable）** | **44.4%** | **95.2%** | **+50pp** |

### 為何同樣 FC facts，兩次 run 決策準確率差這麼多？

兩次 Zep ingestion 是**不同時間點獨立跑的**（SH 17:56, MH 19:11），Zep 的內部 LLM 有隨機性：

- SH 的 wrong invalidations 多是**強世界知識 entity**：Microsoft CEO Steve Jobs、Bo Ryan basketball、Sandy Alderson baseball
- MH 的 wrong invalidations 只 3 個：Fatah Moshe Kahlon、Sable Czech Republic、Oscar Wilde Guangzhou
- MH 的 correct 涵蓋較「弱世界知識」的 entity：Country Joe McDonald、Olga of Kiev、Steve Sax

**結論**：Zep 的衝突判斷準確率**不穩定**（44-95% 區間），受 LLM randomness + entity fame 影響。這本身就是一個重要研究 finding。

---

## 3. 衝突處理對 Acc 的 per-query 影響（三分法）

對 74 個 has_pair 題目分組：

| 組別 | 題數 | Zep Acc | HippoRAG Acc | 差距 |
|---|:---:|:---:|:---:|:---:|
| **OLD invalidated**（Zep 正確決策） | 44 | **47.7%** (21/44) | 15.9% (7/44) | **+31.8pp** |
| **GT invalidated**（Zep 錯誤決策） | 2 | **0%** | 50% | -50pp（小樣本）|
| 兩者都 active（Zep 未判斷） | 53 | 13.2% (7/53) | 5.7% (3/53) | **+7.5pp** |
| Other | 1 | 0% | 0% | — |

### 核心 insight

1. **當 Zep 正確 invalidate 舊事實時**：MH Acc 47.7%（比 HippoRAG 翻倍 +32pp）
2. **當 Zep 沒做衝突處理時**：MH Acc 13.2%（仍比 HippoRAG 的 5.7% 高 +7.5pp）
3. **Zep 錯誤 invalidate GT 僅 2 題**：影響極小

**關鍵是：MH 上 Zep 不只在「正確處理時」贏，連「沒處理時」都贏 HippoRAG-v2。**

---

## 4. Zep 為何能在「沒處理衝突」時仍贏 HippoRAG-v2？

關鍵是 Zep 的**檢索結果結構比 HippoRAG-v2 豐富**：

### Zep 的 retrieved context 包含三層

1. **Edges**：`subject relation object (Date range: ...)` — 結構化 KG triples
2. **Nodes**：`ENTITY: summary` — 跨 chunk 的 entity 描述
3. **Episodes**：**保留含序號的原始文字**（e.g., "209. The capital of Italy is Duluth"）

### HippoRAG-v2 的 retrieved context

- Passages with `Wikipedia Title: ...` wrapper
- 含序號的原文（同 Zep episodes）
- One-shot example 可能干擾多跳推理

### q12 為何 Zep 贏：episodes 救場

**q12（3-hop, 2-conflict）**：「John Harkes 的運動的起源國家的首都？」GT = Duluth

```
Zep edges（衝突對都沒 invalidate）：
  [ACTIVE] association football → Italy    (seq=389)
  [ACTIVE] association football → England  (seq=272)
  [ACTIVE] capital of Italy → Duluth       (seq=209)
  [ACTIVE] capital of Italy → Rome         (seq=167)

Zep episodes（保留原文含序號）：
  "... 167. The capital of Italy is Rome. ..."
  "... 209. The capital of Italy is Duluth. ..."

→ LLM 看到雙 edges 都 active 無法用時序判斷，
   但 episodes 含序號 → LLM 套用 FC 規則「序號大=新」
   → 答 Duluth ✓
```

---

## 5. Zep 勝出的成功模式分類

| 模式 | 機制 | 佔 Zep 勝出的比例 |
|---|---|:---:|
| **A. Zep 正確 invalidate** | LLM 看到 `invalid_at` 標記 → 只信 active edge | 約 50% |
| **B. Episodes 保留序號** | LLM 從原文讀序號 → 套 FC 規則 | 約 40% |
| **C. Nodes 提供 entity summary** | 多跳推理時的 entity 連結輔助 | 約 10% |

Zep 的設計**碰巧**把這三個機制組合起來：triple + temporal + raw text + entity graph，
對 FC-MH 這種「多跳 + 衝突對」任務意外地 well-suited。

---

## 6. 對 HippoRAG-v2 改進方向的啟示

基於 MH 結果，**HippoRAG-v2 要改進 MH 表現**可以學 Zep 的三個設計：

1. ✅ **保留含序號的原始 passage**（HippoRAG-v2 已有這點）
2. **加入 KG entity summaries**（HippoRAG 有 KG 但沒 summarize entity，每個 entity 只是 node ID）
3. **簡化 inference prompt**：移除 `Wikipedia Title` wrapper 和 one-shot example（可能干擾多跳推理）

或者進階方向：**Conflict Filter 的 chain-aware 版本**

- Zep 對個別衝突對能做 95% 正確判斷（在 MH run 中）
- 但它做的還是 **per-edge pairwise** 判斷
- 真正的改進：**chain-aware conflict resolution**——當 hop 0 選定新事實後，hop 1 的衝突判斷應該基於 hop 0 的 entity 路徑，而不是獨立判斷

---

## 7. Agreement matrix

| 狀態 | 題數 |
|---|:---:|
| 兩者都對 | 6 |
| 兩者都錯 | 67 |
| Zep ✓ HippoRAG ✗ | **22** |
| Zep ✗ HippoRAG ✓ | 5 |

Zep 在 17 題上淨勝（22-5）。

---

## 8. 結論與後續

### 對論文 narrative 的重大修正

原本 narrative（SH 為主）：
> "LLM-based conflict resolution systematically fails on counterfactual tasks"

**修正後**（考慮 MH）：
> "LLM-based conflict resolution has highly variable accuracy (44-95% depending on run)
> due to (a) entity fame-driven world-knowledge bias, and (b) per-edge non-deterministic
> LLM decisions. Even at high accuracy, the system's benefit is limited because most
> conflicts (~70%) are NOT detected at all. The observed Zep-over-HippoRAG advantage on
> MH (28% vs 11%) comes more from **rich retrieval substrate (edges + nodes + episodes)**
> than from conflict resolution per se."

### 研究 positioning 需要調整

1. **不能說 Zep 在 FC 上全面失敗**：事實是 Zep MH 贏 HippoRAG-v2
2. **仍然可以說 LLM-based conflict detection 不可靠**：44-95% 變異巨大
3. **核心論點應轉為**：現有方法都是 **instance-local / per-edge**，缺 chain-aware propagation

### 資料路徑

| 檔案 | 說明 |
|---|---|
| `outputs/rag_retrieved/Structure_rag_zep/k_10/factconsolidation_mh_6k/chunksize_512/FULL_100queries.json` | 100 題完整資料 |
| `analysis/results/oracle_a/zep_mh_invalidation_audit_v2.json` | MH 67 個 invalidations 審核 |
| `analysis/results/oracle_a/zep_sh_invalidation_audit_v2.json` | SH 48 個 invalidations 審核（v2 strict）|
