# Zep 機制深度探究：時序與衝突處理完整解析

> 實驗日期：2026-04-20
> 方法：Black-box 行為探測（Zep 是閉源雲端服務），透過 controlled experiments 反推機制
> 共跑 15+ 個 controlled test graphs

---

## TL;DR（核心結論）

| 問題 | 答案 |
|---|---|
| **Q1: `valid_at` 怎麼分配？** | 三層規則：ISO 明確日期 → 解析；模糊時間詞 → 今日 0:00；無時間詞 → ingestion 時間戳 |
| **Q2: 怎麼判斷衝突？** | 用 LLM 語意判斷：**替代型**（moved, relocated）→ 衝突；**累加型**（loves X, loves Y）→ 不衝突 |
| **Q3: 什麼時候設 `invalid_at`？** | 偵測到衝突時，給舊 edge 設 `invalid_at` = 新 edge 的 `valid_at` |
| **Q4: 查詢是否過濾 invalid？** | ❌ **不過濾**，`search()` 同時返回 active + invalid edges，由下游 LLM 根據 metadata 自行判斷 |

---

## Q1: `valid_at` 分配規則（Test Q1 驗證）

| 輸入文字 | valid_at | 機制 |
|---|---|---|
| "Alice likes chocolate ice cream." | 2026-04-20T09:07:46.911Z（ingestion 秒級時間） | **無時間詞 → ingestion 時間戳** |
| "On 2025-03-10, Dave moved to Tokyo." | 2025-03-10T00:00:00Z | **ISO 日期 → 精確解析** |
| "In ancient Rome, Eve was a senator." | 2026-04-20T00:00:00Z（今日 0:00） | **模糊時間詞 → 預設今日 midnight** |
| "On January 15, 2022, Carol got married." | 2022-01-15T00:00:00Z（預期） | **自然語言日期 → 解析** |

**關鍵觀察**：Zep 有 LLM-based 的時間解析，能抓 ISO 和自然語言日期，但模糊表達（"ancient Rome", "yesterday" 沒有明確 anchor 時）fallback 到今日 0:00。

**對 FC 的影響**：
- FC 的序號 "223.", "310." **不是時間表達**，Zep 的時間解析不會識別
- 所有 FC 事實會被標成**同一個 ingestion timestamp**，在時序上完全無法區分

---

## Q2: 衝突偵測的觸發條件（Test Q2 驗證）

這組實驗**最精華**，揭示 Zep 用**語意理解**區分衝突與累加：

| 情境 | 輸入 A → B | 結果 | Zep 判斷 |
|---|---|---|---|
| **Q2-e** 累加偏好 | "Ubor loves pizza" → "Ubor loves burgers" | 兩者都 ACTIVE | ✅ **累加型，不衝突** |
| **Q2-d** 不同 subject | "Wendell lives Paris" → "Vorbeck lives London" | 兩者都 ACTIVE | ✅ 不同實體，不衝突 |
| **Q2-c** 不同 predicate | "Xander lives Paris" → "Xander works teacher" | 都 active（不同資訊） | ✅ 不同面向，不衝突 |
| **Q2-f** 替代語意 | "Tolstov lives Qorvath" → "Tolstov has **moved** to Plerion" | Qorvath INVALID, Plerion ACTIVE | ✅ **偵測到 state change** |

### 關鍵洞察：Zep 用 LLM 語意區分兩類情境

```
累加型（no conflict）              替代型（conflict）
─────────────────────              ──────────────────────
"X loves pizza"                    "X lives in A"
"X loves burgers"      ≠           "X moved to B"
↓                                  ↓
X 同時喜歡兩者                     X 狀態變了
不應 invalidate                    舊狀態應 invalidate
```

這比 mem0 的「totally different」/「contradicts」判斷更細緻。Zep 明確抓 **state-change 語意詞彙**（moved, relocated, became, transitioned 等）。

### 對 FC 的影響（關鍵問題）

FC 的新舊事實**沒有明確的 state-change 語意詞彙**：
- 舊：「223. goaltender is associated with the sport of ice hockey.」
- 新：「310. goaltender is associated with the sport of pesäpallo.」

這兩句都是 stative 陳述（is associated with），**沒有 "moved", "became", "now" 等訊號**。Zep 的 LLM 可能會：
1. 認為這是累加（goaltender 同時與兩個運動有關）→ 都 ACTIVE
2. 或認為是替代，但**由於 world-knowledge 偏見**，錯誤地 invalidate 新的（counterfactual）

---

## Q3: `invalid_at` 的設定邏輯（Test Q4 Part 2 驗證）

**三連衝突的完美處理**：
```
Ingest 1: "Ralvoz is a writer from Oakland."
Ingest 2: "Ralvoz is a writer from Portland."  （8 秒後）
Ingest 3: "Ralvoz has moved, now from Seattle." （再 8 秒後）

→ Zep 處理結果：
  Oakland:  valid 00:00:00, invalid 09:16:09  ← 被 Portland 覆蓋
  Portland: valid 09:16:09, invalid 09:16:17  ← 被 Seattle 覆蓋
  Seattle:  valid 09:16:17, invalid None      ← ACTIVE
```

**機制**：
- 每次新 edge ingest 時，Zep 會搜尋既有衝突 edge
- 若發現衝突，把**舊 edge 的 `invalid_at` 設成新 edge 的 `valid_at`**
- 形成「時序鏈」：Oakland → Portland → Seattle，每段有明確的起始與結束時間

**但有兩種失敗模式**：

### 失敗模式 A：世界知識偏見（Test H）
```
Ingest 1: "Goaltender → ice hockey" (world truth)
Ingest 2: "Goaltender → badminton" (counterfactual)

→ ice hockey: valid, ACTIVE
   badminton: valid=None, invalid=None  ← 沒被 invalidate，但也沒有明確時序
```

LLM 的世界知識壓倒 ingestion 順序。FC 最容易踩到這個雷。

### 失敗模式 B：同一 ingestion 內衝突
```
Ingest 一次：
"Goaltender is associated with ice hockey. Some time later: Goaltender is now associated with pesäpallo."

→ 兩 edges 都 ACTIVE，完全沒觸發衝突邏輯
```

Zep 只在**不同 ingestion 呼叫間**比對衝突。FC 預設 `chunk_size=4096` 一次餵大段，多個衝突對在同 chunk 內，**衝突偵測全部失效**。

---

## Q4: 查詢檢索的行為（Test Q4 驗證）

### 關鍵發現：`graph.search()` **不過濾 invalid edges**

用 Q2-f graph 查詢：

```
Query "Tolstov Qorvath":
  [INVALID] Tolstov resides in Qorvath.
  [ACTIVE] Tolstov has moved to Plerion.

Query "Tolstov Plerion":
  [ACTIVE] Tolstov has moved to Plerion.
  [INVALID] Tolstov resides in Qorvath.
```

無論 query 怎麼下，**兩個 edges 都會返回**，只是排序不同。Zep 把時序過濾的責任交給下游 LLM。

### Zep 如何把時序訊息給 LLM？（看 `methods/zep.py` 的 `compose_search_context`）

```python
def compose_search_context(edges, nodes, context_block, episodes):
    facts = [f'  - {edge.fact} ({format_edge_date_range(edge)})' for edge in edges]
    # format_edge_date_range: f"{valid_at} - {invalid_at or 'present'}"
    ...
```

LLM 最終看到的 context 格式：
```
FACTS and ENTITIES represent relevant context to the current conversation.

# These are the most relevant facts and their valid date ranges.
# format: FACT (Date range: from - to)

  - Tolstov resides in Qorvath. (Date range: 2026-04-20T09:12:46Z - 2026-04-20T09:12:54Z)
  - Tolstov has moved to Plerion. (Date range: 2026-04-20T09:12:54Z - present)
```

**LLM 需要自己**：
1. 判讀 ISO 日期格式
2. 比較 "present" 與具體時間哪個較新
3. 識別 `invalid_at` 有值代表 fact 已過期
4. 選擇使用 present 的 fact

**對 FC 的根本問題**：FC 的所有 edges 的 `valid_at` 都是**同一個 ingestion timestamp**（或今日 0:00），**沒有時序可供 LLM 區分**。序號資訊在 KG 抽取時已經丟失。

---

## Zep 完整處理流程（端到端）

```
┌───────────────────────────────────────────────────────────┐
│               Ingestion: graph.add(text)                  │
├───────────────────────────────────────────────────────────┤
│                                                           │
│  1. Episode 儲存（原文完整保存）                           │
│                                                           │
│  2. Entity extraction（LLM call #1）                      │
│     → nodes (entities + summary)                          │
│                                                           │
│  3. Relation extraction（LLM call #2）                    │
│     → edges (subject, predicate, object)                  │
│                                                           │
│  4. Temporal extraction（LLM call #3，猜測）              │
│     → 每 edge 分配 valid_at                               │
│       - ISO 日期 → 直接解析                                │
│       - 自然語言日期 → LLM 解析                            │
│       - 模糊詞 → 今日 0:00                                │
│       - 無時間詞 → ingestion 時間                          │
│                                                           │
│  5. Conflict detection（LLM call #4，猜測）               │
│     對每個新 edge，搜尋既有 edges 中 subject 相關的         │
│     用 LLM 判斷：                                          │
│       - 累加型（loves X + loves Y） → 不衝突               │
│       - 替代型（moved, became）→ 衝突                      │
│       - 世界知識檢查（隱藏規則）→ 偏向世界真相              │
│                                                           │
│  6. Invalidation                                          │
│     若衝突：舊 edge.invalid_at = 新 edge.valid_at         │
│                                                           │
└───────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────┐
│               Retrieval: graph.search(query)              │
├───────────────────────────────────────────────────────────┤
│                                                           │
│  1. 語意匹配 query 與 edges/nodes/episodes                 │
│  2. 返回 top-N（**包含 INVALID edges**）                   │
│  3. 每個 edge 帶 valid_at / invalid_at metadata           │
│                                                           │
└───────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────┐
│           Inference: LLM(retrieved_context + query)       │
├───────────────────────────────────────────────────────────┤
│                                                           │
│  1. compose_search_context 把 edges 格式化為：             │
│     "  - FACT (Date range: valid - invalid|present)"      │
│  2. LLM 需自己判讀日期、過濾 invalid edges                  │
│  3. LLM 綜合所有 facts + 自己世界知識作答                  │
│                                                           │
└───────────────────────────────────────────────────────────┘
```

---

## 對 FC 任務的預期失敗模式（基於以上機制的推論）

### Mode 1: Chunk 內衝突不偵測（預設 chunk_size=4096）
- FC 455 facts 分 2 chunks，每 chunk ~230 facts 含多個衝突對
- 每 chunk 一次 `graph.add()`，**衝突對都被當獨立 edges 並列儲存**
- 結果：KG 裡新舊事實兩個 edges 都 ACTIVE，`invalid_at = None`

### Mode 2: 時間戳無區分度
- 所有 edges 的 `valid_at` 都是同一個 ingestion time
- LLM 看 "Date range: 2026-04-20T... - present" 每個都一樣
- **時序資訊對 FC 完全無用**

### Mode 3: 序號在抽取時丟失
- Zep 的 edges 是 LLM 抽取的 triple（如 "Goaltender is associated with ice hockey"）
- FC 的 "223. ", "310. " 序號前綴**不會進入 edge.fact 文字**
- LLM inference 時看不到序號，無法套用「序號大 = 新」規則

### Mode 4: 世界知識偏見（即使做 per-fact ingestion）
- 若改成逐句 ingest：Zep 仍會因 world-knowledge bias 把 counterfactual 標 invalid
- 「223. goaltender → ice hockey」（世界真相）會被 Zep 保留
- 「310. goaltender → pesäpallo」（counterfactual）會被標 invalid 或無時序
- **與 FC 規則完全相反**

---

## 對 HippoRAG-v2 的啟示

| Zep 設計 | HippoRAG-v2 對應 | 哪個在 FC 上較好？ |
|---|---|---|
| KG-level temporal metadata | 無自動時序，靠 passage 序號 | **HippoRAG-v2 勝**（FC 序號能進 prompt） |
| `graph.search()` 不過濾 invalid | 返回含序號的 passages | **HippoRAG-v2 勝**（原始資訊完整） |
| LLM 用 Date range 判斷 | LLM 用序號 + inference rule 判斷 | **HippoRAG-v2 勝**（明確規則壓倒 world bias） |
| 自動 conflict 偵測（`invalid_at`） | 不自動偵測 | **HippoRAG-v2 勝**（避免 Zep 的偏見錯誤） |

**核心洞察**：
1. Zep 的「自動時序管理」看似比 HippoRAG-v2 進階，但對 FC counterfactual 反而有害
2. HippoRAG-v2 的「不自動解衝突」其實是優勢——保留原始資訊 + 明確 inference 規則
3. 這印證了之前 Oracle A 的發現：HippoRAG-v2 的失敗主因是 **retrieval 把新舊事實都取回**，不是解衝突機制本身爛
4. 真正的改進方向不是學 Zep 做 temporal metadata，而是在 **retrieval 階段識別衝突對 + 優先保留新事實**

---

## 後續實驗建議

### 實驗 I：真實跑 Zep on FC-SH 10 題 pilot
驗證以上預測的失敗模式 1-3 是否真實發生。重點觀察：
- 有幾個 edges 被抽取？
- 衝突對的 edges 是否都 ACTIVE（無 `invalid_at`）？
- LLM 最終 Acc 是多少？

### 實驗 II：Per-fact ingestion 對比
把 455 facts 逐句餵入 Zep（單次 1 fact），驗證失敗模式 4：即使單句 ingest，world-knowledge bias 仍讓 counterfactual 被 invalidate。

### 實驗 III：去世界知識干擾的測試
用 fictional entities 替換 FC 的真實 entities，看 Zep 能否正確用 ingestion 順序判斷。若能，則進一步證實 world-knowledge bias 是主因。

---

## 附錄：Zep 三層衝突判斷的優先順序（整合所有實驗）

```
Priority 1: 顯式時序標記（ISO date, 自然語言日期）
            → 按解析出的時間排序
            Test I ✓, Q1 explicit_iso ✓

Priority 2: 語意是累加還是替代
            → 累加（loves X, loves Y）：都保留
            → 替代（moved, became）：舊的 invalidate
            Test Q2-e ✓, Q2-f ✓

Priority 3: 中性事實（無世界知識偏見）
            → 按 ingestion 順序
            Test F ✓

Priority 4: 與世界知識衝突時
            → 世界知識壓倒 ingestion 順序
            Test G ✗ (對 FC 而言), Test H ✗
```
