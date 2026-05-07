# mem0 深度機制分析：為何在 FC 上失效

> 實驗日期：2026-04-20
> 目的：徹底釐清 mem0 的完整工作流程、prompt 內容、以及在 FC 通用知識衝突上失效的根本原因，
> 以及是否能處理單跳/多跳衝突。

---

## 1. mem0 的整體架構（default Memory()）

```
                    ┌─────────────────────────┐
                    │   memory.add(messages)  │
                    └───────────┬─────────────┘
                                │
          ┌─────────────────────┴──────────────────────┐
          │                                            │
          ▼                                            ▼
   [Vector Store Path]                        [Graph Store Path]
          │                                            │
          ▼                                            ▼
┌─────────────────────┐                    ┌──────────────────────┐
│ 1. Fact Extraction  │                    │ _add_to_graph()      │
│    (LLM call #1)    │                    │ default: DISABLED    │
│    FACT_RETRIEVAL_  │                    │ (enable_graph=False) │
│    PROMPT           │                    │ → 返回空              │
└──────────┬──────────┘                    └──────────────────────┘
           │
           ▼ new_retrieved_facts
┌─────────────────────┐
│ 2. 對每個新 fact 做  │
│    embedding 並在    │
│    vector store     │
│    搜尋既有相似 mem  │
│    (embedding call) │
└──────────┬──────────┘
           │
           ▼ retrieved_old_memory
┌─────────────────────┐
│ 3. Memory Update    │
│    (LLM call #2)    │
│    DEFAULT_UPDATE_  │
│    MEMORY_PROMPT    │
│    → 決定 ADD/UPDATE/│
│    DELETE/NONE      │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ 4. 對每個動作執行：   │
│    - ADD: 創建新 mem │
│    - UPDATE: 更新    │
│    - DELETE: 刪除    │
│    - NONE: 不動      │
└─────────────────────┘
```

### 關鍵元件

| 元件 | 預設值 | 備註 |
|---|---|---|
| LLM | OpenAI GPT (用於 fact extraction + update memory) | 需 `OPENAI_API_KEY` |
| Embedding | OpenAI text-embedding-3-small | 需 `OPENAI_API_KEY` |
| Vector Store | **Qdrant**（本地 embedded，存在 `/tmp/qdrant`） | 完全本地運行 |
| Graph Store | **預設 DISABLED**（`enable_graph=False`） | 需要額外設 Neo4j 等 |
| Fact Extraction Prompt | `FACT_RETRIEVAL_PROMPT`（專為 personal info） | **FC 失效的主因** |
| Update Memory Prompt | `DEFAULT_UPDATE_MEMORY_PROMPT`（ADD/UPDATE/DELETE/NONE） | 邏輯通用，但仰賴上游 extraction |

**Search 流程（memory.search）**：簡單的 vector similarity search — 將 query 轉成 embedding，
在 Qdrant 中搜尋 top-k 最相似的 memories。**不涉及 graph traversal、re-ranking、或 multi-hop reasoning**。

---

## 2. 阻擋通用知識儲存的具體原因（逐句分析）

以下是 `FACT_RETRIEVAL_PROMPT`（位於 `mem0/configs/prompts.py`）。**加粗部分**是導致 FC 失效的具體片段：

### 2.1 System message 的範圍限定

> "You are a **Personal Information Organizer**, specialized in accurately storing facts,
> **user memories**, and preferences. Your primary role is to extract **relevant pieces of
> information from conversations** and organize them into distinct, manageable facts."

**阻擋點**：把 LLM 的角色定位為「個人資訊整理員」，從源頭就排除了通用世界知識。

### 2.2 明確列出的「值得記憶」類型

> Types of Information to Remember:
> 1. Store **Personal** Preferences
> 2. Maintain **Important Personal Details** (names, relationships, dates)
> 3. Track **Plans and Intentions**
> 4. Remember **Activity and Service Preferences**
> 5. Monitor **Health and Wellness Preferences**
> 6. Store **Professional Details**
> 7. Miscellaneous Information Management (**favorite** books, movies, brands)

**阻擋點**：七大類型 **全部以使用者為中心**（personal / preferences / favorite）。
「goaltender is associated with pesäpallo」這種第三方事實根本不在範圍內。

### 2.3 Few-shot 示範直接教 LLM 拒絕通用知識

```
Input: There are branches in trees.
Output: {"facts": []}        ← 通用事實 → 空

Input: Hi, my name is John. I am a software engineer.
Output: {"facts": ["Name is John", "Is a Software engineer"]}   ← 個人資訊 → 抽取
```

**阻擋點**：這是 LLM 最強的訊號。"There are branches in trees" 是最直接的通用知識範例，
它被明確標為「不抽取」。FC 的 "goaltender is associated with pesäpallo" 與此類型完全相同。

### 2.4 Footer instruction 再次強調

> "Following is a **conversation between the user and the assistant**. You have to extract the
> **relevant facts and preferences about the user**, if any, from the conversation and return
> them in the json format as shown above."

**阻擋點**：再次強調要抽取 **about the user** 的事實。FC 的事實與特定使用者無關。

### 2.5 為何不是 prompt 細節問題？

我們的 sanity test 證明 mem0 可以正確處理以下情境：

| 輸入 | 抽取結果 |
|---|:---:|
| "I've had my cat Luna for 5 months." | 1 fact (ADD) |
| "Luna has been with me for 9 months now."（同 user） | 1 fact ([**UPDATE**]，正確偵測衝突） |
| "goaltender is associated with pesäpallo." | **0 facts** |
| "1. goaltender is... 2. The author of... "（FC 格式） | **0 facts** |

所以：**mem0 的衝突偵測機制本身是 work 的（UPDATE 正確觸發），只是對 FC 這類通用知識事實，
extraction 階段就已經把它們過濾掉了，根本沒機會進入 update memory 流程。**

---

## 3. 關鍵洞察：mem0 有兩段 LLM 呼叫，衝突邏輯在第二段

| 階段 | LLM Prompt | 決定什麼 | 對 FC 的影響 |
|---|---|---|---|
| **① Fact Extraction** | `FACT_RETRIEVAL_PROMPT` | 哪些資訊「值得存入 memory」 | ❌ **FC 事實全部被 reject，整條 pipeline 到此停止** |
| **② Update Memory** | `DEFAULT_UPDATE_MEMORY_PROMPT` | 新 fact 是 ADD/UPDATE/DELETE/NONE | ✅ 對 personal info work（sanity test 證實），但 FC 到不了這一步 |

**UPDATE 判斷邏輯**（從 `DEFAULT_UPDATE_MEMORY_PROMPT` 第 101-106 行）：
> "If the retrieved facts contain information that is **already present in the memory but the
> information is totally different**, then you have to update it."

**DELETE 判斷邏輯**（第 149 行）：
> "If the retrieved facts contain information that **contradicts** the information present in
> the memory, then you have to delete it."

注意：UPDATE 和 DELETE 的觸發條件在概念上重疊（都處理「與既有 memory 矛盾」），這對 FC 的
新舊事實衝突來說有歧義——是要 UPDATE（改寫成新值）還是 DELETE（刪掉舊的）？

---

## 4. mem0 能否處理單跳 vs 多跳衝突？

### 4.1 單跳衝突（FC-SH 情境）

| 條件 | 預期 | 需要驗證 |
|---|---|---|
| 通用知識（mem0 原生設定） | ❌ 不可能，因為 extraction 失敗 | 已確認 |
| 通用知識（用 custom prompt 讓 extraction 通過） | ⚠️ 看 step ② 是否能正確 UPDATE | **待實驗** |
| Personal info 單跳 | ✅ 已驗證（Luna 5→9 個月） | 已確認 |

### 4.2 多跳衝突（FC-MH 情境）

這裡有**結構性問題**，即使 extraction 通過也未必能 handle：

**問題 1：mem0 沒有多跳推理機制**
- `memory.search(query)` 只做一次 vector similarity search，**不做 multi-hop traversal**
- 對「author of Our Mutual Friend 的 spouse 的 citizenship」這種問題，mem0 只會搜一次，
  無法自動串接「Our Mutual Friend → Charles Darwin → Amala Paul → Belgium」的鏈

**問題 2：Graph store 預設 disabled**
- 雖然 mem0 有 `_add_to_graph()` 的 code path，但需要設定 Neo4j 才會啟用
- 預設 `Memory()` 不建 KG，也就沒有 relation 可以 traverse

**問題 3：fact 間的關聯會在 extraction 時被拆散**
- mem0 每個 fact 獨立存為一條 memory，entity 間的關聯不保留
- 當問題是多跳時，LLM 只能在 top-k memories 中 「猜」 怎麼串聯

### 4.3 小結

| 衝突類型 | mem0 原生可否處理 | 用 custom extraction prompt 後可否處理 |
|---|:---:|:---:|
| Personal info，單事實更新 | ✅ | ✅ |
| Personal info，多事實串聯 | ❌（無多跳） | ❌（無多跳） |
| 通用知識，單跳衝突（FC-SH） | ❌（extraction 拒絕） | ⚠️ 可能可以，需實驗 |
| 通用知識，多跳衝突（FC-MH） | ❌ | ❌（無多跳機制） |

---

## 5. 完整流程總覽（哪些用 LLM、哪些用檢索、哪些做衝突解決）

### Ingestion (`memory.add`)

| 步驟 | 機制 | 資源消耗 |
|---|---|---|
| 1. 解析訊息為 user/assistant 對話 | 本地 Python | - |
| 2. 抽取 facts | **LLM call（OpenAI）** | 1 API call per `add()` |
| 3. 對每個 fact 做 embedding | **Embedding call（OpenAI）** | N embeddings per `add()` |
| 4. 對每個 fact 在 Qdrant 搜尋相似既有 memories（top 5） | **Vector search（Qdrant 本地）** | N searches |
| 5. 判斷 ADD/UPDATE/DELETE/NONE | **LLM call（OpenAI，function calling JSON）** | 1 API call per `add()` |
| 6. 執行 ADD → 新 embedding + Qdrant insert | Embedding call + Qdrant | 每個 ADD 1 次 |
| 7. 執行 UPDATE → Qdrant update | Qdrant | 每個 UPDATE 1 次 |
| 8. 執行 DELETE → Qdrant delete | Qdrant | 每個 DELETE 1 次 |
| 9. Graph path（_add_to_graph） | **DEFAULT DISABLED** | 0 |

### Retrieval (`memory.search`)

| 步驟 | 機制 |
|---|---|
| 1. 對 query 做 embedding | Embedding call |
| 2. 在 Qdrant 搜尋 top-k similar memories | Vector search |
| 3. 返回結果 | - |

**沒有**：re-ranking、multi-hop traversal、graph search、LLM-based reasoning over memories。

### QA Inference（在 MABench 的 agent.py）

| 步驟 | 機制 |
|---|---|
| 1. 將 retrieved memories 串成 `memories_str` | 字串拼接 |
| 2. 組成 system prompt + user message | 字串拼接 |
| 3. 呼叫 gpt-4o-mini 回答 | **LLM call** |

---

## 6. 為何這個發現重要

1. **mem0 的「衝突偵測」是 LLM 對一對小清單做判斷，不是結構化的時序推理**
   - 不像 Zep 有 `valid_at / invalid_at`
   - 不像 HippoRAG-v2 有 KG + PPR
   - 效果完全仰賴兩個 prompt 的品質和 LLM 的判斷力

2. **FC 在 mem0 上是「偽實驗」，除非修改 extraction prompt**
   - 直接跑只是測 LLM 的 parametric knowledge，測不到 mem0 的記憶能力

3. **多跳衝突對 mem0 是結構性難題**
   - 即使解決 extraction 問題，也沒有多跳機制
   - 這是 HippoRAG-v2 結構性優勢的來源

4. **UPDATE vs DELETE 的 prompt 邏輯對 FC 不理想**
   - UPDATE: "already present but totally different" → 改寫
   - DELETE: "contradicts the information" → 刪除
   - 對 FC 的「goaltender sport 從 ice hockey 變成 pesäpallo」這種 fact-replacement 場景，
     LLM 可能會猶豫該 UPDATE 還是 DELETE，需要實驗觀察

---

## 7. 後續實驗建議

### 實驗 A：custom_fact_extraction_prompt on FC-SH

設計一個通用版 extraction prompt（例如「抽取所有事實知識，不限於使用者個人資訊」），
在 FC-SH 上重跑，觀察：

- **Ingestion**：mem0 是否能抽取 FC 事實？每個 chunk 抽出幾個？
- **Update events**：當餵入衝突對的第二個事實時，mem0 的決策是 ADD / UPDATE / DELETE / NONE？
- **Final memory state**：跑完 ingestion 後，memory 裡實際留下什麼？
- **Retrieval quality**：對 has_pair 問題，取回的是新事實、舊事實、還是兩者？
- **QA accuracy**：整體 Acc 比 HippoRAG-v2 如何？

### 實驗 B：Per-fact ingestion on FC

把 455 個事實逐句餵入（模擬真實對話），觀察衝突偵測是否比一次塞 chunk 更有效。

### 實驗 C：FC-MH 上的表現預測

基於 mem0 沒有 multi-hop 機制，FC-MH 上的 Acc 可能非常低。但如果驚訝地有效，代表
LLM 在有限 top-k 記憶下仍能做多跳推理（這本身是有趣的發現）。

---

## 附錄：Prompt 完整對比

### mem0 的 FACT_RETRIEVAL_PROMPT（阻擋）

位於 `mem0/configs/prompts.py:14-59`。關鍵限定字眼：

- "**Personal** Information Organizer"
- "**user memories**, and preferences"
- "relevant pieces of information from **conversations**"
- Types: Personal Preferences, Personal Details, Plans, Activity Preferences, Health, Professional, Miscellaneous
- Few-shot: "There are branches in trees" → `{"facts": []}`
- Footer: "extract the relevant facts and preferences **about the user**"

### FC query template（含衝突規則，但 mem0 用不到）

位於 `utils/templates.py`（`factconsolidation > query > rag_agent`）：

> "Pretend you are a knowledge management system. Each fact in the knowledge pool is provided
> with a serial number at the beginning, and the newer fact has larger serial number. You need
> to solve the conflicts of facts in the knowledge pool by finding the newest fact with larger
> serial number..."

**問題**：這個 prompt 是在 inference 時給 mem0 用的，但因為 mem0 的 memory 為空，
`memories_str` 沒內容，整個 query template 失去意義。LLM 最終是靠自己的世界知識回答。
