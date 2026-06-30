# (A) Pipeline Alignment Verification Report

> 對 user 質疑「我是否真的清楚整體運作流程 + 是否真的對齊 MABench default」做完整驗證。
>
> 建立日期: 2026-05-07
> 我先前在這個議題上做了至少兩次錯誤判斷 — 這份報告全部用 dump 出的真實 LLM input 為據,不靠記憶或直覺。

---

## §A.1 三系統 LLM 真實 input 結構 (FC-MH qid=0)

從 MABench main pipeline saved retrieval JSON dump 出 LLM 看到的完整 context:

### A.1.1 HippoRAG-v2 (`Structure_rag_hippo_rag_v2_nv`)

LLM 收到 `retrieval_context` 字串,內容是 `Passage 1: ...\n\nPassage 2: ...` 形式的 chunk-level retrieval。

**樣本** (qid=0, top-10):
```
"Passage 1:
Australia is located in the continent of Oceania. 76. The author of The Birth of Tragedy is Friedrich Nietzsche. 77. The author of The Birth of Tragedy is Stephen Crane. 78. placekicker is associated with the sport of American football. 79. The name of the current head of state in United Kingdom is Elizabeth II. 80. The chairperson of Harvard University is Lawrence S. Bacow. ...
...
258. flanker is associated with the sport of rugby union. 259. Nobuhiro Watsuki is famous for The Fairly OddParents. 260. Kingdom of Ireland is affiliated with the religion of Zoroastrianism. 261. pesäpallo was created in the country of Philippines. 262. Mahmoud Abbas works in the field of politician. 263. George W. Bush is affiliated with the religion of United Methodist Church. 264. Sasanian Empire was founded by Walter Chrysler. 265. Canadair was founded in the city of Tucson. 266. Karen Armstrong is affiliated with the religion of Catholic Church."
```

→ **完整保留原始 chunk 序號** (76. 77. 78. ... 266.)。Wrapper 規則 "序號大=新" 完全可用。

### A.1.2 Zep (`Structure_rag_zep`)

LLM 收到 `retrieved_context_paragraphs` (48 段),分四塊:

```
[ 0] FACTS and ENTITIES represent relevant context to the current conversation.
[ 1] # These are the most relevant facts and their valid date ranges. ...
[ 2] # format: FACT (Date range: from - to)
[ 3-12]   - The author of Our Mutual Friend is Charles Dickens. (2026-04-21T11:11:55.391Z - 2026-04-21T11:11:55.745Z)
         - The author of Our Mutual Friend is Charles Darwin. (2026-04-21T11:11:55.745Z - present)
         - ...

[13] # These are the most relevant entities
[14] # ENTITY_NAME: entity summary
[15-24]   - Our Mutual Friend: The author of Our Mutual Friend is Charles Dickens.
          ...

[25] # These are the most relevant episodes.
[26] # format: EPISODE
[27-47]   - Content: Dialogue between User and Assistant 2026-04-21 19:11:54 \n<User> The following context is the facts I have learned: 
         Frank Zappa died in the city of Los Angeles. 38. Dave Filoni is employed by Lucasfilm. 39. Henri Grégoire is a citizen of France. 40. Christianity was founded in the city of Jerusalem. ...
         62. Yves Montand is married to Simone Signoret. 63. The univeristy where Joan Didion was educated is University of California, Berkeley. ...
         189. Hugh Hefner is famous for The Vampyre. 190. The capital of Czech Republic is Prague. 191. Aristotle's child is Nicomachus. ...
         0. Thomas Kyd was born in the city of London. 1. The chairperson of Fatah is Mahmoud Abbas. ...
         76. The author of The Birth of Tragedy is Friedrich Nietzsche. 77. The author of The Birth of Tragedy is Stephen Crane. ...
```

→ **Zep 的 LLM context 同時含 3 種 ordering signal**:
  - (a) Paraphrased fact 含時間戳 `(valid_at - invalid_at|present)`
  - (b) Entity summary
  - (c) **Episodes (原始 chunks) 含原始序號** (38. 39. 0. 1. 62. 63. 76. 77. 189. 190. ...)

→ **Wrapper 規則 "序號大=新" 在 Zep 上直接可用 (via episodes),不需要靠時間戳類推**。
  - (我前一輪寫的「Zep 沒序號,只能靠時間戳類推」是**錯的**,只看了前 8 段就斷言)

### A.1.3 Mem0 (`Structure_rag_mem0`, MABench main pipeline)

LLM 收到的 system_prompt:
```
"You are a helpful AI. Answer the question based on query and memories.\n{memories_str}\n"
```

**致命發現** — `memories_str` 在 main pipeline 中是**空字串**!`retrieved_memories` count = 0,完全沒 retrieval 結果。

`ingestion_context_0.jsonl` 顯示 12 個 chunks 全部 `"vector_results": {"results": []}`,**Mem0 fact extraction 在 main pipeline 全部失敗 (LLM 全判 facts=[])**。

→ MABench main pipeline 的 Mem0 在 FC-MH 上是 broken state:**1% EM** (gpt-4o-mini, 1/100, 從 `outputs/gpt-4o-mini-mem0/Conflict_Resolution/.../*.json`)。

→ 我自己跑的 Mem0 aligned 用 `make_l1_modified_prompt()` 移除原 `FACT_RETRIEVAL_PROMPT` 中的兩個 anti-knowledge few-shots:
  ```
  Input: Hi.
  Output: {"facts" : []}

  Input: There are branches in trees.
  Output: {"facts" : []}
  ```
  原因: 這兩個 few-shots 在 FC corpus 上會 trigger LLM 把所有 chunks 都判成 `[]`。我的 fix 後 ingest 成功 (442 facts),retrieval 每題回傳 100 facts,EM = 44/100。

→ **如果論文要 fairly compare 三系統**,Mem0 必須用 fixed pipeline (我的 aligned),不能用 broken main pipeline 的 1%。

### A.1.4 三系統 LLM input 序號可用性對照表 (修正版)

| 系統 | LLM context 含原始序號 | LLM context 含時間戳 | wrapper 規則可用性 |
|---|:---:|:---:|:---:|
| HippoRAG-v2 | ✓ (chunks) | ✗ | **直接可用** |
| **Zep** | **✓ (episodes)** | ✓ (paraphrased facts) | **直接可用 (via episodes)** + 額外 timestamp 提示 |
| Mem0 (fixed pipeline, my aligned) | ✗ (LLM-paraphrased facts 無序號) | ✗ | **完全不適用** |
| Mem0 (MABench main, broken) | ✗ (memories_str=空) | ✗ | wrapper 對空 retrieval 無效 |

---

## §A.2 我自己 aligned script 跟 MABench main pipeline 的對齊狀態

### A.2.1 Mem0 aligned (`run_mem0_gemini_aligned.py`) vs `agent.py:_handle_mem0_agent`

| Item | Main pipeline (`agent.py`) | My aligned script | 對齊? |
|---|---|---|---|
| Memory.add user_id | `f'context_{context_id}_{self.sub_dataset}'` (e.g., `context_0_factconsolidation_mh`) | `f'mem0_aligned_{task.lower()}'` | **✗ 不同 user_id**(但 user_id 不影響 EM,只影響 store namespacing) |
| `system_message` for ingestion | `get_template(self.sub_dataset, 'system', self.agent_name)` (= `SYSTEM_MESSAGE`) | `"You are a helpful assistant that can help memorize details in the conversation."` | **✗ 不同 system message** |
| `memorize_template` | `'Dialogue between User and Assistant {time_stamp} \\n<User> The following context is the facts I have learned: \n{context}\n <Assistant> I have learned the facts and I will answer the question you ask.'` | 直接用 chunk 文字無 wrapper | **✗ 不同 ingestion message format** |
| `system_prompt` for inference | `f"You are a helpful AI. Answer the question based on query and memories.\n{memories_str}\n"` | 同樣 | ✓ |
| `user_message` for inference | `wrapper(question) + "\n\nCurrent Time: ..."` | 同樣 | ✓ |
| `FACT_RETRIEVAL_PROMPT` (custom) | 原 mem0 lib 預設 (含 anti-knowledge few-shots) | `make_l1_modified_prompt()` 移除 anti-knowledge few-shots | **✗ 我有改 — 是必須的 fix, 不然 ingest=0** |
| `retrieve_num` | 100 (k_100) | 100 | ✓ |
| `Memory.search` | `self.memory.search(query=message, user_id=user_id, limit=self.retrieve_num)` | 同樣 | ✓ |
| Embedder | (取決於 config; main 應該 OpenAI ada-002 or HF) | HF MiniLM-L6-v2 | **✗ 不同 embedder** |
| Vector store | qdrant | qdrant local | ✓ (一樣) |
| LLM | (config) | Vertex Gemini 3.1 flash-lite, max_tokens=8192 | **✗ 不同 LLM (跟 HippoRAG-v2 對齊但不是 MABench 預設 OpenAI)** |

→ **6 個 ✗ 中,3 個是必要 fix (anti-knowledge few-shot),其他 3 個是 deviation**。

### A.2.2 Zep aligned vs `agent.py:_handle_zep_agent`

我的 Zep aligned 是 cached retrieval + wrapped query inference (`rerun_mem0_zep_aligned_with_wrapper.py`)。retrieval 部分用之前 Zep cloud 跑過的存檔(原始時就用 wrapped query 跑的),inference 部分自己呼 LLM。

| Item | Main pipeline | My aligned | 對齊? |
|---|---|---|---|
| Retrieval (edges/nodes/episodes top-10) | Zep cloud `graph.search` | 用之前 Zep cloud retrieval cache | ✓ (相同 retrieval) |
| `compose_search_context` | `methods/zep.py` | 同樣 | ✓ |
| inference LLM | `methods/zep.llm_response()` 用 OpenAI/Azure | 我自己呼 Vertex Gemini | **✗ 不同 LLM** |
| inference system_prompt | `methods/zep.py:115` "You are a helpful expert assistant..." | 同樣 | ✓ |
| inference user message | `methods/zep.py:118-126` `Your task is to briefly answer ... {context} ... {question}` | 同樣 | ✓ |

→ Zep 主要 deviation = 不同 LLM,但 prompt + retrieval format 對齊。

### A.2.3 HippoRAG-v2 main vs analysis directories 跑的

- main pipeline 在 `outputs/gemini-3.1-flash-lite-preview-hippo_rag_v2_nv/` 有完整存檔
- 我們 §1 表中 22% 數字來自這個 main pipeline 跑的 (跟 chunks + wrapper + Vertex Gemini 對齊)
- **HippoRAG-v2 是唯一三系統中 main pipeline 跑得 EM=22 的、跟我們 narrative 對齊的**

---

## §A.3 對 narrative 影響評估

### A.3.1 §1 表格的數字哪些有問題?

| 系統 | narrative §1 數字 (aligned) | 來源 | 問題? |
|---|:---:|---|---|
| HippoRAG-v2 SH/MH | 77 / 22 | MABench main pipeline gemini run | ✓ 直接 main pipeline 數字 |
| **Mem0 SH/MH** | **85 / 44** | 我的 aligned (FACT_RETRIEVAL_PROMPT 有 fix) | **▲ 不是 main pipeline 數字 (main pipeline 是 1%)** |
| Zep SH/MH | 89 / 28 | 我的 aligned (用 main pipeline retrieval cache + 我的 LLM) | ▲ retrieval 對齊,但 inference LLM 不一致 |

→ **§1 數字陳述不嚴謹**: Mem0 不是 MABench default 數字 (default 是 1%, broken),是我們 fix anti-knowledge few-shots 後的版本。**論文要明確說明這是 fixed Mem0,不是 vanilla Mem0**。

### A.3.2 §4.4 retrieval format 表錯在哪?

我前一輪寫的:
> Zep: `FACT (Date range: from - to)` 格式 ✓ valid_at/invalid_at 時間戳 → 間接可用 (LLM 把「找最新」類推到時間戳)

**錯了**。實際 Zep LLM context 裡面 episodes 段含原始 chunk 文字,序號 (38. 39. 76. 77. 189. ...) 直接可見 → wrapper 規則直接適用,**不需要任何類推**。

### A.3.3 §4.4 wrapper 對 Mem0 +1pp / Zep +20pp 的解釋還對嗎?

**Mem0 +1pp 的解釋仍對**: Mem0 LLM 看到的 `memories_str` 是 paraphrased fact list,完全沒序號 — wrapper 規則對 Mem0 retrieval 真的無從套用,只剩 framing 部分 (Pretend you are a knowledge management system) 還有微弱作用。

**Zep +20pp 的解釋要修**: 不是「靠時間戳類推」,而是 **wrapper 規則直接適用於 episodes 中的原始序號**。但這引出新問題 — 如果 wrapper 直接可用,**Zep MH 為何只有 28%(遠低於 HippoRAG-v2 22% + 17pp 的 retrieval coverage 提升空間,也低於 Mem0 fixed 44%)**?可能原因:
  - Zep retrieval (top-10 edges + top-10 nodes + top-10 episodes) 的 chain coverage 比 HippoRAG-v2 PPR 弱
  - 或 Zep paraphrased fact 跟 episodes 並列時 LLM 更被 paraphrased fact 吸引,而 paraphrased fact 沒序號
  - 這需要 §4.3.A detection coverage + retrieval coverage 進一步驗證

### A.3.4 §1.A construct validity / §1.B emergent / §1.5 retrieval / §2 channel ceiling / §3 V1V2V3 — 不受影響

這些 evidence 都是用 HippoRAG-v2 + chunks + 同一 wrapper-aligned pipeline 跑的,不受 Mem0/Zep retrieval format 修正影響。

---

## §A.4 待 user 決定的 framing 問題

1. **Mem0 main pipeline broken 怎麼處理?**
  - (i) 報告 broken main = 1% 為 vanilla baseline + 我們 fixed = 44% 為 ablation,顯示 "anti-knowledge few-shot 可能是 production 系統的失敗源"
  - (ii) 直接報告 fixed 版作為 Mem0 真實能力下界,在 footnote 說明 fix 細節
  - (iii) 完全 redo 一輪 main pipeline run 跟 paper 中 Mem0 數字對齊

2. **Zep MH 28% 為何遠低於 HippoRAG-v2 22% + 17pp 上限?**
  - 需要查 Zep edges/episodes 是否完整覆蓋 chain_new/chain_old
  - 跟 §4.3.A 的 Zep all_detected 20/100 對應
  - 可能 narrative §4.3 + §4.4 都需要更深一層分析

3. **§4.4 retrieval format 段重寫**
  - Mem0 是唯一不含序號的系統 (而非「Mem0 + Zep 都不含,Zep 用時間戳替代」)
  - Zep 跟 HippoRAG-v2 都直接含序號 → wrapper 規則一樣可用,但兩者 EM 仍不同 → 用 retrieval coverage / chain reasoning 解釋而非 "wrapper 可用性"

4. **method_design §9 portability matrix 重新檢視**
  - V2 cite-source (要求 fact number) 對 Mem0 失效 (Mem0 真的無 fact number) — 仍對
  - 對 Zep 應該可用 (episodes 中有序號),不是「△ 部分」
  - V1 trailer / V3 decompose 對三系統 portable — 仍對

---

## §A.5 結論

**我犯的兩個錯誤**:
1. 沒讀完 Zep retrieval JSON 就下結論「Zep 沒序號」 — 實際上 episodes 段含原始序號
2. 沒查 MABench main pipeline 的 Mem0 是否真的能 retrieve memory — 實際上 ingestion 全失敗,baseline 是 broken state

**對齊狀態 (修正後)**:
- HippoRAG-v2: ✓ 我們的 §1 數字直接是 main pipeline 數字
- Zep: ▲ retrieval 對齊,inference LLM 換成 Vertex Gemini (跨系統一致), prompt 完全對齊
- Mem0: ▲ MABench main 是 broken (1%),我們是 fixed (44%) — 必須在 paper 明確說明

**接下來建議**:
- Step 1: User 看完此報告,選擇 §A.4 的 framing decisions
- Step 2: 根據 decisions 重寫 §1 註腳 + §4.4 retrieval format 段 + method_design §9
- Step 3: 補做 Zep retrieval coverage 分析 (§A.4 第 2 點),確認 Zep MH 28% 的真實 bottleneck
