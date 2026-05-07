# Mem0 vs Zep — Inference Prompt 結構對比

> 目的：拆解兩系統最終餵給 inference LLM 的 prompt 內容差異，作為「detection 訊號是否傳到 inference」的審視。

---

## 1. Mem0 (custom + Gemini, our run)

### Source
- `agent.py:_handle_mem0_agent` line 612-619
- 我們的 [run_mem0_gemini.py](../scripts/run_mem0_gemini.py) 完全 mirror 這個 prompt

### 流程
```python
# Step 1: vector search (no LLM)
relevant_memories = memory.search(query=question, user_id=user_id, limit=100)

# Step 2: format as bullet list
memories_str = "\n".join(f"- {entry['memory']}" for entry in relevant_memories["results"])

# Step 3: build prompt
system_prompt = f"You are a helpful AI. Answer the question based on query and memories.\n{memories_str}\n"
user_msg = question + "\n\nCurrent Time: 2026-05-02 07:35:12"

# Step 4: send to Gemini
```

### 餵給 LLM 的具體格式

```
[system]
You are a helpful AI. Answer the question based on query and memories.
- Charles Darwin is the author of Our Mutual Friend
- Charles Darwin's spouse is Amala Paul
- Amala Paul is a citizen of Belgium
- Charles Dickens is a British novelist
- ...（共 top-100 facts）

[user]
What is the country of citizenship of the spouse of the author of Our Mutual Friend?

Current Time: 2026-05-02 07:35:12
```

### 訊息密度
- ✗ **沒有時間戳**
- ✗ **沒有 supersession 標記**（"current" / "outdated" 都沒）
- ✗ **沒有 fact-vs-episode 區分**（只有單一層 facts list）
- **LLM 只看到一份 "current memories" bullet list** — 假設前提是 Mem0 已經把 outdated 都 UPDATE 掉或 DELETE 了，retrieve 回來的就是 current

→ **Mem0 的 detection 透過「直接刪/改 vector store 內容」生效**（filter at write）。LLM 永遠看不到 outdated 版本，detection 訊號是 implicit。

### 含義
- 若 Mem0 detection 正確（UPDATE 到 current）→ retrieve 回來都是 current → LLM 答對機率高
- 若 Mem0 detection 失敗（沒 UPDATE，old 跟 new 都在 store）→ retrieve 回來混合 old+new → LLM 看到 conflicting list 但**沒任何 metadata 提示哪個是 current**，要靠 LLM 自己 reason / 用 world knowledge → 大機率錯

→ 這解釋為什麼 Mem0 detection × answer **強相關**（無偵測時 LLM 沒線索可選）。

---

## 2. Zep (existing + Gemini inference, our run)

### Source
- `agent.py:_handle_zep_agent` line 720-742 + `methods/zep.py:llm_response` line 114
- 我們的 [run_zep_gemini.py](../scripts/run_zep_gemini.py) 完全 mirror

### 流程
```python
# Step 1: 三 scope 各 search top-10（共最多 30 個結構物 + 1 個 thread context block）
edges = zep.graph.search(query=q, scope="edges", limit=10).edges
nodes = zep.graph.search(query=q, scope="nodes", limit=10).nodes
episodes = zep.graph.search(query=q, scope="episodes", limit=10).episodes
context_block = zep.thread.get_user_context(thread_id).context

# Step 2: compose（從 methods/zep.py:compose_search_context）
context = TEMPLATE.format(
    facts='\n'.join(f'  - {edge.fact} ({edge.valid_at} - {edge.invalid_at or "present"})' for edge in edges),
    entities='\n'.join(f'  - {node.name}: {node.summary}' for node in nodes),
    context_block=context_block,
    episodes='\n'.join(f'  - Content: {episode.content}' for episode in episodes),
)

# Step 3: build prompt
system_prompt = "You are a helpful expert assistant answering questions from users based on the provided context."
user_msg = f"""
    Your task is to briefly answer the question. ...

        {context}

        {question}

    Answer:
"""
```

### 餵給 LLM 的具體格式

```
[system]
You are a helpful expert assistant answering questions from users based on the provided context.

[user]
Your task is to briefly answer the question. You are given the following context from the previous conversation. ...

FACTS and ENTITIES represent relevant context to the current conversation.

# These are the most relevant facts and their valid date ranges. ...
# format: FACT (Date range: from - to)

  - Charles Darwin is the author of Our Mutual Friend (2026-04-21T13:42:11Z - present)
  - Charles Dickens is the author of Our Mutual Friend (2026-04-21T13:42:11Z - 2026-04-21T13:43:09Z)   ← 標 invalid_at!
  - Charles Darwin's spouse is Amala Paul (2026-04-21T13:42:11Z - present)
  - ...（共 top-10 edges）


# These are the most relevant entities
# ENTITY_NAME: entity summary

  - Charles Darwin: A scientist who wrote Our Mutual Friend...
  - Charles Dickens: An English novelist...
  - ...（共 top-10 nodes）


# These are the most relevant episodes.
# format: EPISODE

  - Content: <整段 raw chunk 文字>
  - Content: <整段 raw chunk 文字>
  - ...（共 top-10 episodes）

[最後再加 Zep thread.get_user_context 自動 summarize 的 context_block]


What is the country of citizenship of the spouse of the author of Our Mutual Friend?

Answer:
```

### 訊息密度
- ✓ **時間戳明確**（`valid_at - invalid_at`，invalid 表示已被 supersede）
- ✓ **三層訊息**（structured facts / entities / raw episodes）
- ✓ **Zep 自動 summary**（context_block）
- ✗ 但沒有 explicit `[CURRENT]/[OUTDATED]` 文字標記 — 要 LLM 自己解析 timestamp

→ **Zep 的 detection 透過「給 timestamp metadata，讓 inference LLM reason」**（annotation at inference）。LLM 看到 old + new 都在 prompt，靠 timestamp 推哪個 active。

### 含義
- Zep detection 正確（valid/invalid_at 設對）→ LLM 看到雙版本 + timestamp → 但要靠 LLM 解析時間 → 中等機率對
- Zep detection 失敗（時間戳設錯/沒設）→ LLM 看到雙版本但沒線索 → 機率錯

→ 這對應 SESSION_2026-04-28 §13.2 的「**LLM 對 invalid_at date_range 訊號 0% 識別**」— Zep 給的 timestamp 訊號 LLM 大半看不懂或忽略，所以即使 detection 對，answer 也不一定對。**這就是 Zep MH「all detected → 0% EM」反例的根本原因**。

---

## 3. 結構性差異對 paper 主張的意義

| 維度 | Mem0 | Zep |
|---|---|---|
| Detection 在哪生效 | Write-time（vector store 直接刪/改）| Inference-time（給 timestamp metadata 給 LLM）|
| LLM 看到 outdated? | ✗ 看不到（被 UPDATE/DELETE 掉） | ✓ 看得到（靠 invalid_at 區分）|
| 訊號明確度 | implicit（"看不到就是被刪了"）| explicit timestamp 但要 LLM 解析 |
| Failure mode (detection wrong) | LLM 完全沒線索 → 大機率錯 | LLM 仍看到雙版本，可能用 world knowledge 救 |
| Failure mode (detection right) | retrieved 都是 current → 大機率對 | LLM 看到雙版本仍可能採信 outdated（trust gap）|

→ 這對應我們之前 RPT vs OA2 oracle 的 13 pp 落差（83% vs 68%）。**Mem0 設計貼近 OA2 path（filter）；Zep 設計貼近 RPT path（annotation）**。Mem0 在 detection 對的時候 fully unlocks LLM，Zep 即使 detection 對也卡 trust gap。

→ Paper 修正：**Mem0/Zep 不只是「detection 表現不同」，他們是「衝突解析的 channel paradigm 不同」**。Mem0 的 paradigm 跟 OA2 oracle 同 family；Zep 跟 RPT family。我們的 method 設計（v2 KG subgraph augmentation）需要決定走哪 family — 或如 §0.6 brainstorm 提的 hybrid。

---

## 4. 對「Mem0 表現過好」的另一個解釋

從 prompt 結構看，**Mem0 在 FC 上強的部分原因是 paradigm 適合**：
- FC 是「6k 含眾多 numbered facts，問題只需 lookup current 版本」
- Mem0 的 vector retrieval + filter-based 處理 fits 這個結構
- 反之 Zep 的 multi-layer + timestamp inference 對 FC 反而是 overhead

**但這不一定 generalize**：
- 真實對話（LongMemEval）每 fact 都摻雜在 dialogue 中，extraction 變難
- 長 context（32k+）下，vector retrieval 的 noise 變多，UPDATE step 累積過大會 truncate
- Mem0 customized 在 FC 6k 跑得好 ≠ 在 LongMemEval 跑得好

→ 這就是為什麼要做 §B sanity test（context size scaling + LongMemEval）才能確認 Mem0 是「真強」還是「FC artifact」。
