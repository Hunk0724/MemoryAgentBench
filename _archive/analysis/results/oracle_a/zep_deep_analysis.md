# Zep 深度機制分析

> 實驗日期：2026-04-20
> 目的：釐清 Zep 在知識衝突任務上的行為，特別是其 temporal knowledge graph
> （valid_at / invalid_at）是否能自動處理新舊事實更新。

---

## 1. Zep 的整體架構

Zep 是 **Knowledge Graph + temporal invalidation** 的雲端服務：

```
                  ┌────────────────────────┐
                  │ client.graph.add(text) │
                  └───────────┬────────────┘
                              │
                              ▼ (async processing on Zep cloud)
         ┌────────────────────────────────────┐
         │ 1. 從 text 抽取 triples (entities   │
         │    + relationships)                 │
         │    → 建 episodes (原文)、nodes、edges│
         └────────────────┬───────────────────┘
                          │
                          ▼
         ┌────────────────────────────────────┐
         │ 2. Temporal extraction:             │
         │    - 分析文字中的時間線索            │
         │    - 給每個 edge 分配 valid_at       │
         │    - 比對是否與既有 edge 衝突        │
         │    - 若衝突，給舊 edge 設 invalid_at │
         └────────────────┬───────────────────┘
                          │
                          ▼
         ┌────────────────────────────────────┐
         │ 3. 結果存入 Zep Cloud 的 graph DB    │
         │    (3 種 scope: edges/nodes/episodes)│
         └────────────────────────────────────┘

Retrieval:
client.graph.search(graph_id, query, scope='edges'|'nodes'|'episodes', limit=N)
→ 返回 top-N 的 edges/nodes/episodes（基於文字相似度 + graph structure）
```

### 關鍵特性

| 元件 | 行為 |
|---|---|
| **Ingestion** | 接受所有文字（**不像 mem0 會過濾通用知識**） |
| **Fact extraction** | LLM 從文字抽取 triples，存為 edges |
| **Temporal tracking** | 每個 edge 有 `valid_at` / `invalid_at`（ISO 8601 時間戳） |
| **Conflict resolution** | 宣稱能自動偵測新舊衝突，給舊 edge 設 `invalid_at` |
| **Retrieval** | 語意搜尋 edges / nodes / episodes |
| **Cost** | 每個 episode（一次 `graph.add`）消耗 1+ credits；>350 bytes 按倍數計 |

---

## 2. Sanity Test 結果（5 個 tests）

### Test 1: Ingestion 範圍

所有類型的 text 都被接受（ingest 成功）：

| 輸入類型 | 成功 ingest | 成功抽取 edges |
|---|:---:|:---:|
| Personal info（"Hi my name is John, cat Luna"） | ✅ | ✅ 2 edges |
| Personal update（"Luna been with me 5 months"） | ✅ | ✅ 1 edge |
| Generic fact（"goaltender → pesäpallo"） | ✅ | ✅ 1 edge |
| Generic fact 多句帶序號（FC-style） | ✅ | ✅ 2 edges（但少一個） |

**與 mem0 的關鍵差異**：Zep **不會過濾**通用知識，任何文字都會嘗試抽 triples。

### Test A: 分開餵入衝突對（無序號，較長間隔）

```python
# 先餵 ice hockey，等 5 秒，再餵 pesäpallo
graph.add("Goaltender is associated with the sport of ice hockey.")  # 時間 T
sleep(5)
graph.add("Goaltender is associated with the sport of pesäpallo.")  # 時間 T+5
```

**結果**：Zep **偵測到衝突！**

| Edge | valid_at | invalid_at | 狀態 |
|---|---|---|---|
| "Goaltender → ice hockey" | 2026-04-20T07:50:10.576Z | **None** | **當前有效** |
| "Goaltender → pesäpallo" | 2026-04-20T00:00:00Z | 2026-04-20T07:50:10.576Z | **已失效** |

注意：**Zep 判定的「新舊順序與我們的 ingestion 順序相反」**。我們先送 ice hockey 後送 pesäpallo，但 Zep 把 pesäpallo 標為已失效、ice hockey 標為有效。

**可能原因**（待進一步驗證）：
1. async 處理順序與 call 順序不一致
2. Zep 的 LLM 判斷「哪個是較新/較正確」用了其他訊號（如 entity canonicalization）
3. 兩次 ingestion 時間太接近，Zep 隨機選擇

### Test C: 一次 ingestion 多句含衝突

```python
graph.add("""Goaltender is associated with ice hockey.
Some time later: Goaltender is now associated with pesäpallo.
...""")  # 一個 call
```

**結果**：**未偵測衝突**，兩個 edges 都是 `invalid_at: None`

| Edge | invalid_at |
|---|---|
| "Goaltender → ice hockey" | None（active） |
| "Goaltender → now pesäpallo" | None（active） |

**重要發現**：**Zep 只在不同 ingestion 呼叫間做衝突偵測**。同一次 ingestion 中的多個衝突 fact，Zep 都當作並列的 edges 儲存。

### Test D: FC 格式帶序號（分開餵入）

```python
graph.add("223. goaltender is associated with the sport of ice hockey.")
sleep(10)
graph.add("310. goaltender is associated with the sport of pesäpallo.")
```

**結果**：**未偵測衝突！**

| Edge | invalid_at |
|---|---|
| "goaltender → ice hockey" | None |
| "goaltender → pesäpallo" | None |

**重要發現**：**FC 的序號數字（223, 310）干擾了 Zep 的 temporal extraction**。可能是 Zep 嘗試把「223」、「310」解析為 date/time 但失敗，結果兩個事實都以預設時間存入，沒有觸發衝突邏輯。

---

## 3. 關鍵發現總結

### 3.1 與 mem0 的對比

| 能力 | mem0 | Zep |
|---|:---:|:---:|
| 接受 personal info | ✅ | ✅ |
| 接受 generic fact（通用知識） | ❌（extraction reject） | ✅ |
| Fact 儲存為結構化 | vector embedding | **KG edges (subject/predicate/object)** |
| 有時序 metadata | ❌（只有 created_at） | ✅ `valid_at / invalid_at` |
| 衝突偵測 | ✅（對 personal） | ⚠️（對 generic 部分成功） |
| 多跳推理 | ❌ | ⚠️（可 traverse graph，但取決於 query） |
| 自動建 KG | ❌ | ✅ |

### 3.2 Zep 衝突偵測的可靠性問題

| 情境 | 衝突偵測？ |
|---|:---:|
| 分開餵 personal info 更新（e.g., Luna 5→9 個月） | **待驗證**（Test E 尚未完成） |
| 分開餵 generic fact 衝突（e.g., goaltender 無序號） | ✅ 偵測（但時序反向） |
| 分開餵 generic fact 帶 FC 序號（e.g., 223 vs 310） | ❌ **未偵測** |
| 同一 ingestion 中的衝突 | ❌ **未偵測** |

### 3.3 對 FC 任務的預測

**預期 Zep 在 FC 上的行為**：

1. **Ingestion**：Zep 會成功從 context 抽出 edges（比 mem0 好，至少不會全空）
2. **衝突偵測**：
   - 若照 MABench 預設 `chunk_size=4096` 一次塞很多事實 → **不會偵測衝突**（Test C 證實）
   - 若改成 per-fact ingestion → **可能偵測**（但 FC 的序號會干擾，Test D 證實）
3. **序號格式是障礙**：FC 的「223. goaltender → ice hockey」、「310. goaltender → pesäpallo」被 Zep 當成平行事實，失去時序意義
4. **Retrieval**：Zep 返回所有 active edges（包括衝突的兩個版本），最終 LLM 仍要自己判斷

**預期整體 Acc**：比 mem0 原生高（至少有 context 給 LLM 看），但因為衝突偵測失效，LLM 看到新舊兩版事實，效果可能與 HippoRAG-v2 原始（非 Oracle）接近，甚至更差（Zep 無 PPR ranking）。

---

## 4. Zep 完整流程（哪些用 LLM、哪些用 graph、哪些做衝突解決）

### Ingestion (`graph.add`)

| 步驟 | 在哪裡執行 | 用什麼技術 |
|---|---|---|
| 1. 接收 text | Zep Cloud | API |
| 2. 抽取 entities + relationships | Zep 內部 LLM | **LLM call（內部）** |
| 3. 分配 `valid_at` 時間戳 | Zep 內部 | 文字時序分析 + 預設 |
| 4. 搜尋既有 edges 是否衝突 | Zep graph DB | **Graph search** |
| 5. 判斷是否設定 `invalid_at` | Zep 內部 LLM / 規則 | **LLM or heuristic** |
| 6. 儲存 episode（原文）、nodes、edges | Zep graph DB | Graph DB write |

**注意**：Zep 是閉源的雲端服務，內部用哪個 LLM、用什麼規則做衝突偵測，我們無法看到。

### Retrieval (`graph.search`)

| 步驟 | 技術 |
|---|---|
| 1. 接收 query + scope (edges/nodes/episodes) | API |
| 2. 語意搜尋（可能是 embedding 或 BM25 + graph structure） | Graph + vector |
| 3. 返回 top-N 結果（**edges 會包含 valid_at / invalid_at**） | API response |

### QA Inference（MABench 的 agent.py）

```python
retrieved_context = compose_search_context(edges, nodes, context_block, episodes)
# compose_search_context 會把 edges 格式化為:
#   - FACT (Date range: valid_at - invalid_at)
# 把 nodes 格式化為:
#   - ENTITY_NAME: summary
# 把 episodes 格式化為:
#   - Content: raw_text

# 然後塞給 gpt-4o-mini 回答
```

**這裡有個關鍵點**：`compose_search_context` 把 `valid_at` / `invalid_at` 寫進 context string，
**所以 LLM 是有機會看到時序資訊的**。但要真正有效，需要：
1. Zep 真的在 edges 上設了有意義的 `valid_at / invalid_at`
2. 衝突對的新舊 edge 都被 retrieve 回來
3. LLM 能理解「invalid_at: not None 表示這個 fact 已失效」

---

## 5. 對 HippoRAG-v2 改進的啟發

從 Zep 的設計可以看到：

1. **結構化時序 metadata** 是一個有用的方向 —— 比起 FC 用序號當隱式時間戳，Zep 的 `valid_at / invalid_at` 更明確
2. **但 Zep 的衝突偵測不可靠**（對 FC 格式尤其失敗）—— 這告訴我們：**只靠一般的 KG + temporal metadata 不足以解決 FC 這類衝突**
3. **HippoRAG-v2 優勢**：它直接把含序號的 passage 送給 LLM，讓 LLM 明確用序號規則判斷，而不是靠 KG 的 valid_at
4. **可能的改進方向**：HippoRAG-v2 + 顯式時序 metadata（像 Zep 那樣在 retrieval 時標註每個 fact 的「新舊」），但需要 retrieval 階段能識別衝突對

---

## 6. 後續實驗建議

### 實驗 1: Zep 原生 FC-SH/MH 10 題 pilot

用 MABench 預設 config（`agent_chunk_size=4096`）跑 10 題 FC-SH，觀察：
- Ingestion 產生多少 edges？
- 衝突對的新舊 edge 是否都存在？哪個有 `invalid_at`？
- Retrieval 是否同時回傳新舊版本？
- LLM 最終答題 Acc？

### 實驗 2: Per-fact ingestion

把 455 個事實逐句餵入 Zep，測試：
- 每次餵入是否觸發衝突偵測？
- 最終 KG 中衝突對的狀態（有多少正確標記 `invalid_at`）

### 實驗 3: 去掉 FC 序號

把「223. goaltender → ice hockey」的序號拿掉，改成「Goaltender is associated with ice hockey.」
看 Zep 是否能基於 ingestion 順序做衝突偵測。

---

## 附錄：資料路徑

| 項目 | 路徑 |
|---|---|
| Zep sanity test 腳本 | 直接在 shell 中執行（未存檔） |
| Zep code 修改記錄 | `agent.py` `_initialize_zep_agent` + `_handle_zep_agent`（已加 OpenAI fallback + 結構化保存） |
| Test graph IDs（可用於後續查詢） | `graph_test_1776671267`, `graph_zeptest2_1776671409`, `graph_zeptest2_1776671409_batch`, `graph_zeptest3_1776671790_serial`, `graph_zeptest3_1776671790_luna` |
