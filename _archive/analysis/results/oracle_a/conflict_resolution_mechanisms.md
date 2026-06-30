# mem0 / Zep / AriGraph / HippoRAG-v2 衝突解決機制完整對比

> 最後更新：2026-04-22
> 包含 FC-SH 和 FC-MH 100 題完整實證

---

## 0. 論文核心主張（經 FC-SH + FC-MH 驗證）

現有記憶系統在衝突解決上的設計差異：

| 方法 | Write-time 行為 | Query-time 行為 | 粒度 |
|---|---|---|:---:|
| **AriGraph** | LLM 判斷 → 直接 DELETE 舊 triplet | 無（舊已消失） | Pairwise |
| **Mem0** | LLM 判斷 → ADD/UPDATE/DELETE | 無（舊已消失） | Pairwise |
| **Zep** | LLM 判斷 → 標 `invalid_at` 不刪除 | Search 返回含 invalid edges + metadata | Pairwise / Per-edge |
| **HippoRAG-v2** | 無自動處理 | 無自動處理（靠 inference prompt 序號規則） | — |

**核心論點**：
1. **處理時機不同**（write-time destructive vs write-time non-destructive marking）
2. **但處理粒度相同**：都是 **instance-local**（pairwise 或 per-edge），**沒有 chain-level propagation**
3. 對 multi-hop 衝突任務，instance-local 粒度**理論上不足**

---

## 1. 每個方法的精確描述

### AriGraph — Write-time 破壞性修改

code: `graphs/contriever_graph.py:43-44`
```python
predicted_outdated = parse_triplets_removing(response)
self.delete_triplets(predicted_outdated, locations)  # 從 KG 移除
```

- LLM prompt（`prompt_refining_items`）：判斷新 triplet 是否該取代某既有 triplet
- 若是 → **實際從 KG 刪除**舊 triplet
- 舊資訊**徹底消失**，retrieval 永遠看不到

### Mem0 — Write-time 破壞性修改（兩條路徑相同）

**Vector path**（default，`mem0/memory/main.py`）：
- `FACT_RETRIEVAL_PROMPT` 抽個人事實
- `DEFAULT_UPDATE_MEMORY_PROMPT` 判斷 ADD/UPDATE/DELETE/NONE
- UPDATE 呼叫 `vector_store.update()` → **覆寫**舊 memory
- DELETE 呼叫 `vector_store.delete()` → **移除**舊 memory

**Neo4j path**（`mem0/memory/graph_memory.py`）：
- `EXTRACT_RELATIONS_PROMPT` 抽 triples
- `DELETE_RELATIONS_SYSTEM_PROMPT` 判斷是否刪除
- 實際執行 Cypher `DELETE r` → **徹底移除**關係

### Zep — Write-time 非破壞性標記 + Query-time per-edge metadata

**Write-time**（從 API 行為推測，雲端黑盒）：
- 新 edge 進入時，Zep 搜尋同 subject 相關的既有 edges（**局部 neighborhood**，非 chain-aware）
- LLM 判斷是否衝突、是否為替代語意（moved, became 等）
- 若衝突 → 舊 edge 的 `invalid_at` 設為新 edge 的 `valid_at`（**不刪除**，edges 仍可被 search 返回）

**Query-time**（我們實證確認）：
- `graph.search()` **不過濾** invalid edges，全部返回
- 每個 edge 附帶 `valid_at / invalid_at` metadata
- Inference LLM 在 prompt 中看到 `FACT (Date range: from - to)` 格式
- LLM **per-edge 獨立判斷**採信哪個 edge（無 chain 協調）

### HippoRAG-v2 — 無自動衝突處理

- Passages 以原始含序號文字直接送給 LLM
- Inference prompt 含明確規則：「序號越大越新越正確」
- LLM 自行判斷——類似 Zep 的 query-time，但用**顯式序號**而非 temporal metadata

---

## 2. FC-SH 實證結果（100 題，chunk=512）

### 整體 Acc

| 系統 | Acc | has_pair Acc | no_conflict Acc |
|---|:---:|:---:|:---:|
| HippoRAG-v2 | 69% | 44/74 = 59.5% | 25/26 = 96.2% |
| Zep | 70% | 44/74 = 59.5% | 26/26 = 100% |

**SH 兩者打平**，其中 has_pair Acc 完全相同（44/74）。但 per-question 實際有 37/100 題答案不同，wins/losses 對沖。

### Zep 衝突決策準確率（SH）

| 指標 | 數量 |
|---|:---:|
| Total unique invalidated facts | 48 |
| Correct（symbolic FC rule） | 20 |
| Wrong | 25 |
| False positive（無 counterpart） | 2 |
| **Accuracy（measurable）** | **44.4%** |

### SH Per-query 三分法

| 組別 | 題數 | Zep Acc | HippoRAG Acc | 差距 |
|---|:---:|:---:|:---:|:---:|
| OLD invalidated（Zep 正確） | 7 | **86%** | 43% | +43pp |
| GT invalidated（Zep 錯誤） | 14 | **7%** | 57% | -50pp |
| 兩者都 active（未判斷） | 52 | 71% | 62% | +9pp |

**SH 特徵**：Zep 對沖效應明顯——正確 invalidate 的 7 題大贏，錯誤 invalidate 的 14 題大輸，整體 Acc 被平均到等於 HippoRAG。

---

## 3. FC-MH 實證結果（100 題，chunk=512）

### 整體 Acc

| 系統 | Acc |
|---|:---:|
| HippoRAG-v2 | **11%** |
| **Zep** | **28%** |
| Zep 淨勝 | **+17pp** |

### Per-group breakdown

| 分組 | N | Zep | HippoRAG | 差距 |
|---|:---:|:---:|:---:|:---:|
| 2-hop, 1-conflict | 25 | 40% | 28% | +12pp |
| **2-hop, 2-conflict** | **36** | **33%** | **3%** | **+30pp** 🚀 |
| 3-hop, 1-conflict | 5 | 40% | 40% | 持平 |
| 3-hop, 2-conflict | 9 | 11% | 0% | +11pp |
| 3-hop, 3-conflict | 10 | 10% | 0% | +10pp |
| 4-hop 系列 | 15 | 混雜 | 混雜 | — |

### Zep 衝突決策準確率（MH）

| 指標 | 數量 |
|---|:---:|
| Total unique invalidated facts | 67 |
| Correct | **59** |
| Wrong | 3 |
| False positive | 4 |
| **Accuracy（measurable）** | **95.2%** |

### MH Per-query 三分法

| 組別 | 題數 | Zep Acc | HippoRAG Acc | 差距 |
|---|:---:|:---:|:---:|:---:|
| **OLD invalidated**（正確） | 44 | **47.7%** | 15.9% | **+31.8pp** |
| GT invalidated（錯誤） | 2 | 0% | 50% | -50pp（小樣本）|
| 兩者都 active | 53 | 13.2% | 5.7% | **+7.5pp** |

**MH 特徵**：
- Zep 在所有組別都贏或持平，**沒有 SH 那種「錯誤 invalidate 大輸」的對沖**（因為錯誤決策只有 2 題）
- 即使「沒做判斷」的 53 題，Zep 仍比 HippoRAG 高 +7.5pp
- → Zep 的優勢來自**綜合 retrieval 結構**（edges + nodes + episodes），不只是衝突處理

---

## 4. 關鍵發現：Zep 衝突決策準確率**不穩定**

### SH vs MH 同一 Zep 系統、同一 FC context、不同 run

| 指標 | SH run | MH run |
|---|:---:|:---:|
| Invalidated unique facts | 48 | 67 |
| Correct | 20 (41.7%) | **59 (88.1%)** |
| Wrong | 25 (52.1%) | **3 (4.5%)** |
| **準確率（measurable）** | **44.4%** | **95.2%** |

### 為何差距巨大？（同 FC 455 facts）

1. **LLM randomness**：Zep 內部 LLM 在 ingestion 時判斷，不同時間點 run 結果不同
2. **Entity fame 分布**：
   - SH run 的 invalidations 多涉及強世界知識 entity（Microsoft CEO、Bo Ryan）→ world-knowledge bias 觸發
   - MH run 的 invalidations 多涉及弱世界知識 entity（Country Joe McDonald、Steve Sax）→ bias 未觸發

### 對論文 narrative 的意義

**不能說「Zep 對 FC counterfactual 衝突無效」**，因為 MH 上 Zep 95.2% 準確。
**應該說「Zep 衝突決策受 LLM world-knowledge bias 影響，準確率不穩定（44-95%）」**。

---

## 5. 總結：四方法比較矩陣

| 面向 | AriGraph | Mem0 | Zep | HippoRAG-v2 |
|---|:---:|:---:|:---:|:---:|
| 接受通用知識 | ✅ | ❌（只收個人資訊） | ✅ | ✅ |
| 處理衝突的時機 | Write-time | Write-time | Write-time + Query-time | 無自動處理 |
| 處理方式 | Destructive（刪除） | Destructive | Non-destructive（標記）| — |
| 粒度 | Pairwise | Pairwise | Per-edge / Local neighborhood | — |
| **Chain-aware？** | ❌ | ❌ | ❌ | ❌ |
| FC-SH Acc (100題) | 未跑 | 失效（<30%） | 70% | 69% |
| FC-MH Acc (100題) | 未跑 | 失效 | **28%** | **11%** |
| Oracle A 對應 SH | — | — | — | **81%**（has_pair usable） |
| Oracle A 對應 MH | — | — | — | **42%**（usable） |

---

## 6. 對論文 findings 的最終整合

### Finding 1：現有方法的共通侷限（instance-local）

所有四個方法（AriGraph/Mem0/Zep/HippoRAG-v2）的衝突處理都是 pairwise / per-edge，
**沒有 chain-aware propagation**。multi-hop 衝突要靠 LLM 在 inference 時自行串聯。

### Finding 2：LLM-based 衝突判斷受 world-knowledge bias，準確率不穩定

Zep 在同 FC context 兩次 run 的衝突決策準確率從 **44% 到 95% 變動**，主因是：
- LLM randomness
- Entity fame 決定 world-knowledge bias 強度

**對 FC counterfactual 任務**：可靠性不足以作為唯一的衝突解決機制。

### Finding 3：Mem0 的 extraction prompt 完全阻斷 FC 通用知識

Mem0 的 `FACT_RETRIEVAL_PROMPT` 專為個人資訊設計，**拒收 FC 的通用知識事實**。
衝突判斷機制根本沒啟動。

### Finding 4：HippoRAG-v2 + Oracle A 是最佳實證 upper bound

**Oracle A（移除 old passages）**：
- SH has_pair usable (64題): **81%**
- MH usable (66題): **42%**

這比 Zep MH 的 28%、SH has_pair 的 59.5% 都高，證明：
- **Retrieval 階段做精確衝突處理 > LLM 在 inference 時做**
- **保留原始含序號 passage > 用 KG edges 抽取後的 triples**

### Finding 5：Zep MH 的意外勝出，並非衝突機制立功

Zep MH (28%) 勝過 HippoRAG-v2 (11%)，但：
- 只有 21/74 has_pair 題是因為 Zep **正確 invalidate 舊事實**
- 其餘多是因為 **episodes 保留序號原文** + **nodes 提供 entity summary**（豐富的 retrieval 結構）
- 甚至 53 題「未做判斷」時，Zep 仍比 HippoRAG 高 7.5pp

→ **Zep 的價值來自「綜合 retrieval substrate」多於「衝突機制」本身**。

---

## 7. 對 HippoRAG-v2 + Conflict Filter 的設計建議

從這整套實證得到的設計原則：

### 應該保留 ✅
1. **含序號的原始 passage retrieval**（HippoRAG-v2 已有）
2. **Inference prompt 的序號規則**（壓過 LLM 的 world-knowledge bias）
3. **不自動破壞性修改記憶**（保留歷史）

### 應該改進 ⚠️
1. **Retrieval 階段識別並過濾舊事實 passage**（Oracle A 證實有效，SH 81% / MH 42%）
2. **識別衝突對**：用 `(s, r) 相同 + o 不同` 的結構規則，而非 LLM 語意判斷
3. **Chain-aware 衝突解決**（真正的 novel contribution）：當 hop 0 選定新事實後，
   hop 1 的衝突判斷依據 hop 0 的 entity chain，而不是獨立判斷

### 不應該模仿 ❌
1. **Zep 的 LLM-based temporal 判斷**：世界知識偏見，準確率不穩定
2. **Mem0 的 extraction-first filtering**：會過濾掉通用知識
3. **AriGraph 的破壞性刪除**：失去 multi-version 資訊，無法做 Oracle-style 上界實驗

---

## 8. 實驗資料完整索引

| 檔案 | 內容 |
|---|---|
| `outputs/gpt-4o-mini-hippo_rag_v2_nv/Conflict_Resolution/factconsolidation_sh_6k_..._k10_chunk512_results.json` | HippoRAG SH baseline |
| `outputs/gpt-4o-mini-hippo_rag_v2_nv/Conflict_Resolution/factconsolidation_mh_6k_..._k10_chunk512_results.json` | HippoRAG MH baseline |
| `outputs/rag_retrieved/Structure_rag_zep/k_10/factconsolidation_sh_6k/chunksize_512/FULL_100queries.json` | Zep SH 100 題 |
| `outputs/rag_retrieved/Structure_rag_zep/k_10/factconsolidation_mh_6k/chunksize_512/FULL_100queries.json` | Zep MH 100 題 |
| `analysis/results/oracle_a/oracle_a_sh_results.json` | Oracle A SH |
| `analysis/results/oracle_a/oracle_a_mh_results.json` | Oracle A MH |
| `analysis/results/oracle_a/zep_sh_invalidation_audit_v2.json` | Zep SH 衝突決策審核 |
| `analysis/results/oracle_a/zep_mh_invalidation_audit_v2.json` | Zep MH 衝突決策審核 |
| `analysis/results/oracle_a/zep_full100_final_findings.md` | Zep SH 詳細分析 |
| `analysis/results/oracle_a/zep_mh_full100_findings.md` | Zep MH 詳細分析 |

---

## 9. Disclaimer for paper writing

> Zep 為 closed-source cloud service，我們的機制分析基於 public API 的 observable behavior
> （edge metadata、search results），並非 internal implementation。per-edge / instance-local
> 的刻畫反映的是使用者視角可觀察、可操作的行為。
