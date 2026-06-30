# Critical Findings — 2026-05-29 evening (Mem0/Mem0g pipeline trace)

> **Status**: F1 / F2 / F3 三個重大發現都會直接改寫 paper §6.3 故事與後續分析方向
> **Trigger**: 完整 trace mem0/mem0g 從 `add()` 到 `final inference` 的 pipeline,對照 LCA/HippoRAG-v2
> **Related**: [[CRITICAL_F1_mem0g_graph_unused]]、[[CRITICAL_F2_inference_prompt_minimal]]、[[CRITICAL_F3_temperature_deviation]]

---

## F1 — Mem0g 的 graph relations **從未進入** final inference prompt

### 證據鏈

**agent.py:865-939 `_handle_mem0_agent`**(mem0 + mem0g 共用 handler):

```python
# L896 — 拿到 mem0 search 結果(若 graph 啟用,含 relations)
relevant_memories = self.memory.search(query=message, user_id=user_id, limit=self.retrieve_num)

# L899 — 組 memories_str **只用 ["results"](vector),不用 ["relations"]**
memories_str = "\n".join(f"- {entry['memory']}" for entry in relevant_memories["results"])

# L903-907 — final prompt
system_prompt = f"You are a helpful AI. Answer the question based on query and memories.\n{memories_str}\n"
llm_messages = [
    {"role": "system", "content": system_prompt},
    {"role": "user", "content": message + "\n\nCurrent Time: " + ...}
]

# L930 — relations 只「存到 disk 給分析」,不會回到 LLM
"retrieved_relations": relevant_memories.get("relations", []),  # mem0g only
```

**mem0/memory/main.py:489-503 `search()`**:

```python
future_memories = executor.submit(self._search_vector_store, query, filters, limit)
future_graph_entities = (
    executor.submit(self.graph.search, query, filters, limit) if self.enable_graph else None
)
...
if self.enable_graph:
    return {"results": original_memories, "relations": graph_entities}  # 兩者分開
```

→ `results` 和 `relations` 是 **separate dict keys**,從未 merge。

### 含義 — 直接改寫 paper story

1. **目前的 Mem0g vs Mem0 對比根本不是 graph vs vector**
   - 兩者 final inference 拿到的 context **完全一樣**(都是 vector store top-k)
   - Mem0g 41% MH 6k vs Mem0 50% MH 6k 的 **9pp 差距 ≠ graph 比較差**
   - 真實原因:graph 抽取 + 寫入 Neo4j 的額外 LLM call **干擾了 vector store ingestion**(可能 LLM token budget 競爭、parallel write conflict、或 fact extraction 路徑被 graph 影響)

2. **無法 claim「圖層扣 9pp」**(spec §27.2 finding #2 必須收回)
   - 正確說法:「啟用 mem0g graph 模組 → vector ingestion **品質下降** → 答題下降」
   - 真正的 graph 貢獻無法從目前實驗讀出

3. **是 vendored MABench bug?還是 mem0 設計?**
   - 對照 `mem0/` upstream:v3 已完全移除 graph 層,所以無法對照
   - 對照 MABench `methods/baseline_RAG.py`:同樣只取 `["results"]`(已驗證)
   - **判斷**:這應該是 MABench 整合 mem0g 的 **implementation 缺陷**,不是 mem0 設計缺陷
   - mem0g 原版設計應該要在 inference 時 verbalize relations 進 prompt

### Action item

**選項**:

| 選項 | 描述 | 推薦度 |
|---|---|---|
| **A** | 修補 agent.py:899 → 把 `relations` 也 verbalize 進 prompt,重跑 mem0g,得到真正的 graph 評估 | ⭐⭐⭐ paper 公平性高 |
| **B** | 保持原樣,在 paper 註明「MABench-vendored mem0g 不在 prompt 中使用 graph」 → 把 mem0g 結果重新詮釋為「graph build 對 vector 的副作用」 | ⭐⭐ 故事不漂亮但誠實 |
| **C** | 雙軌:同時跑 A 修補版(mem0g-prompt-aware)與 B 原版,paper 兩個都報 → 直接顯示 graph 貢獻量 | ⭐⭐⭐⭐ 最 rigorous,但要再多跑 |

→ **推薦 C**,把「mem0g-原版」改名 `mem0g-MABench-as-is`,新增 `mem0g-prompt-aware` 列出 graph 真正貢獻。

---

## F2 — Final inference prompt **沒有任何 conflict / temporal / sequence 提示**

### 證據

agent.py:903:
```python
system_prompt = f"You are a helpful AI. Answer the question based on query and memories.\n{memories_str}\n"
```

`memories_str` 是純 bullet list,**無 timestamp、無 ingestion order、無「以最新為準」hint**。

### 對照 HippoRAG-v2

[[../baseline_methods/baseline_methods_paper_vs_impl.md]] 列過 HippoRAG-v2 的 inference prompt 有 phase 3 scaffold:

> "When the answer requires connecting multiple facts, briefly list the intermediate entities or facts you use, and ensure that any entity appearing in multiple steps is referenced consistently."

對照 LCA(直接給原文長 context):LLM 看到對話的時序順序,**implicit** 有 "after X said Y, X said Z" 的時序訊號。

### 含義

1. **反事實 FC 題目對 mem0/mem0g 是最壞情境**:
   - GT 同時包含 old fact(原 MQuAKE)+ counterfact(被 FC 翻案)
   - vector store 同時 ADD 兩個事實(如果 detection miss)
   - LLM 看到 bullet list 沒有時序,**隨機選一個**
   - **EM 命中率 ≈ 「事實對」的隨機抽樣** + 模型偏向常識(老事實)

2. **這也解釋為什麼 mem0 在 MH 6k EM=50%**:
   - 不是因為 mem0 偵測到衝突,而是因為 vector ADD 把 new fact 也存了,LLM 抽到時 5/5 機率(估)
   - All-CLEAN→EM 90% finding 還是有效(因為真正 detect 到衝突 + 把 old 刪掉的話,LLM 只看到 new,當然對),但 conflict-NOT-clean 時 EM 40% 主要是 LLM 隨機猜對

3. **Paper §6.4 mechanism evidence 要 reframe**:
   - 不能單純說「detection → EM」,要拆「detection → memory state(無 stale fact)→ LLM 沒選擇困難 → EM」
   - 反過來說:「detection miss → memory state 有兩個 fact → LLM 隨機猜 → EM ≈ 50%」

### Action item

**選項**:

| 選項 | 描述 |
|---|---|
| **A** | 保留原 prompt(MABench-as-is)當主結果 |
| **B** | 加 conflict-aware prompt(「If multiple memories conflict, prefer the most recent」)當 ablation,看 EM 提升多少 |
| **C** | Ours method 主打 "conflict-aware inference"(對抗 mem0 弱點) |

→ **推薦 A+B 雙跑**,B 是 ablation 證明「method 弱點不是 prompt 沒提示而是 memory state 本身」。如果 B 跟 A 差不多,那證明 mem0 memory state 真的 broken;如果 B 大幅提升,那 mem0 弱點主要在 inference prompt,不在 detection。

---

## F3 — Temperature 偏離 benchmark 預設

### 證據

| 設定層 | Benchmark 預設 | 我們現在 |
|---|---|---|
| Top-level yaml `temperature` | **0.7**(所有 RAG/agentic method) | **0** |
| mem0 internal LLM(facts/update)| ~0(mem0 default 也是 0)| **0.1** |
| 最終 inference 走的路徑 | mem0 內部 chat completion | mem0 內部(走 VertexGeminiLLM with 0.1) |

證據:`MemoryAgentBench_original/configs/agent_conf/RAG_Agents/gpt-4o-mini/Structure_rag_gpt-4o-mini-mem0.yaml:3` = `temperature: 0.7`

我們的 yaml:`configs/agent_conf/RAG_Agents/Gemini/Structure_rag_mem0*_gemini-3.1-flash-lite_chunk512.yaml:7` = `temperature: 0`

### 含義

1. **嚴格 EM benchmark 用 temp=0.7 本來就奇怪**(GPT-era 慣例 leftover),用 temp=0 反而合理
2. 但我們 vs benchmark 的「公平比較」會被質疑:mem0 paper 跑 GPT-4o-mini @ 0.7,我們跑 Gemini @ 0/0.1
3. **影響 EM variance** — temp=0 的 EM 是 1-trial 確定值,temp=0.7 至少要 3-5 trials 取平均

### Action item

**選項**:

| 選項 | 描述 | 推薦度 |
|---|---|---|
| **A** | 改回 0.7 對齊 benchmark,跑 3-trial 取平均 | ⭐ 但變很貴 |
| **B** | 維持 0,在 paper 明確 disclose「Using temp=0 for deterministic EM evaluation; benchmark default 0.7 used multi-trial averaging」 | ⭐⭐⭐ 推薦 |
| **C** | 雙跑(temp=0 主結果 + temp=0.7 ablation 顯示穩定) | ⭐⭐⭐⭐ 最 rigorous |

→ **推薦 B**,並加一行 ablation 比對(只跑 mem0 × MH 6k × temp=0.7 × 3 trials)看是否與 temp=0 有顯著差異。

---

## 總結 — 對 paper 與下一步的影響

### Paper-level 影響

| Finding | Paper 影響 | 緊迫度 |
|---|---|---|
| F1 (graph 沒進 prompt) | **§27.2 的「圖層扣 9pp」claim 必須收回**,改為「mem0g implementation 的 inference 缺 graph」 | 🔥 立刻 |
| F2 (prompt 無 conflict 提示)| §6.4 mechanism 故事要 reframe,從「detection→EM」改為「detection→memory state→EM」 | ⭐⭐ |
| F3 (temp deviation)| Appendix disclosure 需註明,加 1 trial ablation 確認 robust | ⭐ |

### 下一步分析 reframe(取代 update_gap)

User 指出 update_gap 沒用,改為 **detection-as-action 三向拆分**:

1. **Detection-precision**(方法 perspective):
   - 對 mem0:UPDATE/DELETE 操作 vs GT 真衝突 → precision / recall / 新舊判斷正確率
   - 對 mem0g:DELETE entity 操作同理
   - 資料源:`outputs/rag_retrieved/.../ingestion_context_<ctx>.jsonl`(已存在,P8 SQLite 隔離後可信)

2. **Retrieval-correctness**(query-time perspective):
   - 給定 query,top-k retrieved memories 是否包含 "正確答案的 supporting fact"?
   - 資料源:`query_<qid>_context_<ctx>.json` 中 `retrieved_memories`(已存在)

3. **Answer-correctness**(EM)— 已有

3-way contingency table(✓/✗ × 3 = 8 cells):
- (D✓, R✓, A✓): clean win
- (D✓, R✓, A✗): inference failure(prompt 沒提示 / LLM 不會判讀)
- (D✓, R✗, A✗): retrieval failure(detect 對但取錯)
- (D✗, R✓, A✓): 幸運 — detect miss 但取對
- (D✗, R✓, A✗): retrieval 取到但 LLM 選錯
- (D✗, R✗, A✗): full failure
- (D✗, R✗, A✓): noise win
- (D✓, R✗, A✓): noise win

→ 寫一個 `analysis/compute_3way_breakdown.py` 統合三層。

### Decision needed from user

1. F1 處理:選 A / B / C(推薦 C 雙跑)
2. F2 處理:選 A / B / C(推薦 A+B 雙跑)
3. F3 處理:選 A / B / C(推薦 B,加 1 trial ablation)
4. 新分析腳本是否現在開始實作?

---

**End of CRITICAL_FINDINGS_2026-05-29_evening.md**
