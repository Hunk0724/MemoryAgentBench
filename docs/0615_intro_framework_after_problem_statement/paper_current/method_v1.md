# Method 草稿（v1,2026-07-04,無 P5 核心版）

> 依據:`current_ours_method_pipeline_and_prompts.md`(實作現況)+ intro v5 + vocabulary v2。
> **本文件僅描述 Method 本身**;Experiments / Baselines / Evaluation Protocol 已移至
> [`evaluation_protocol_fc_mquake_v2.md`](evaluation_protocol_fc_mquake_v2.md)。
> 與實作現況的差異用 ⚠️ 標出;待你決定的問題用 ☐ 標出(彙整於 §5)。

---

# 3. Method

## 3.1 問題設定與符號

記憶庫 M 隨對話流累積原子事實；同一事實可能以多個版本存在。依 §0 Scope（LongMemEval / MemoryAgentBench-FC / BEAM / MemBench 的共同定義），KU 的正確行為是：查詢觸及某事實時，以其**時序最新**版本作答。每筆記憶條目為 (text, triple, ordinal)：text 為抽取後的原子事實、triple 為 (subject, predicate, object) 或 null、ordinal 為寫入時序。

本方法圍繞兩個結構性承諾：**忠實寫入 (Faithful Writes)** 與**查詢時 KU 解析 (Query-Time KU Resolution)**。設計原則貫穿全篇：LLM 任務一律**單筆之內、窄範圍、可 cache**；凡可確定性者交精確運算子；**LLM 全程不參與新舊 (recency) 判斷**。

## 3.2 忠實寫入 (Faithful Writes)

**(1) 統一抽取（P1，LLM，per-chunk）。** 自 role-labeled 對話 chunk 抽取 USER 主張的原子事實。三個設計錨點：(a) **source-based**——只收 user 主張、assistant turn 僅作理解上下文，此為 backbone-independence 的來源（不依賴 LLM 自有知識判斷什麼值得存）；(b) **faithfulness**——照抄、不 fact-check，反事實與互相矛盾的值都如實記錄（衝突是預期會發生的，解析是查詢時的事）；(c) selectivity——無事實主張則回空。已驗證：FC-SH 32k 前 5 chunk 對完美抽取 GT 的逐 chunk micro-recall 97.4%、數量比 1.00。

**(2) 三元組抽取（P2 + P2b fallback，LLM，per-fact）。** 每條事實抽 (s, p, o)：subject 取「更新後仍固定的實體」、object 取「會變動的值」，使同一事實的不同版本落在同一 (S, P) 之下。名詞化關係分解為標準 s-r-o 形；複雜敘事/多事實/主觀狀態允許 null（P2b 對 null 再補 subject-only，使查詢期的 subject guard 普遍適用）。不對世界知識驗證、反事實照抽。⚠️ confidence gate 已於 2026-06-20 移除（4o-mini 的 confidence 近常數），confidence 僅記錄供分析。

**(3) 確定性提交（deterministic）。** 整 chunk batch-embed 後**保留所有版本寫入**，每筆 payload 帶 triple + ordinal。**寫入端不存在任何跨筆 LLM 判斷**：無候選檢索、無衝突偵測、無操作決策——這不是省略，而是承諾：持久記憶狀態不是任何一次 LLM 判斷的函數。
⚠️ 實作註記：程式仍另建 (S, P) 倒排索引但查詢期從未讀取（死碼）。**論文 method 不描述此索引**；☐ 建議直接從程式移除或註明 disabled，避免審稿人對照 code 時混淆。

## 3.3 查詢時 KU 解析 (Query-Time KU Resolution)

**(4) 檢索（deterministic）。** 剝除 qa 模板 boilerplate、以 **raw question** 做 embedding 檢索 top-K（預設 100）。理由：模板指令主導向量會稀釋真問題（FC-SH 64k：GT_new recall@100 由 wrapped 79% → raw 100%，rank 中位數 13→2）。公平性：ungated（vanilla mem0 baseline 同樣套用），且 Zep 的 `get_retrieval_query` 本就做同類剝離——屬 pipeline 對齊而非加 buff，論文於 setup 揭露。

**(5) 條件式結構路由（deterministic）。** 候選集內：有 triple 且該 (S, P) 有 ≥2 競爭者 → `structural_pool`（該 (S, P) 群即為一個事實識別分群）；無 triple 或 (S, P) 單例 → `dynamic_pool`。

**(6) 事實識別分群補救（P3，LLM，僅對 dynamic_pool）。** 只判**身分**（哪些候選是同一事實的不同版本），不判 recency、不答題；只輸出有信心的 cluster（≥2 成員），其餘自動保留。設計偏保守：false-merge 會藏掉合法值、false-split 無害，故 cluster 是 RARE、不確定就不分群。硬規則：不同實體＝不同事實、不同屬性＝不同事實、多值屬性＝並存不分群。

**(7) 時序解析（deterministic）。** 對每個分群（structural 群 + P3 cluster）以 **ordinal argmax 取最新、丟舊**（平手 keep-all）；未入任何群的候選一律保留。在本文 scope 的 KU 定義下，同一事實的多版本即互斥、以最新為準——**衝突判斷退化為分群的直接推論，無須額外 LLM 呼叫**；「誰是權威版本」由 argmax 決定，與 LLM 無關。表面變體群（同值不同寫法）經 argmax 仍得同值，無損。
⚠️ 與實作現況的差異：現行 pipeline 在 (6)(7) 之間有 P5 conflict-type 分類（3-way、query-aware、cached）。**本文核心方法不含 P5**；含 P5 的變體降級為 ablation 之一（§4.4），其結果用以實證核心版的選擇。☐ 對應程式開關：`ours(full)` 保留現行路徑、核心版走 group→argmax 直連。

**(8) 推論（P4，LLM）。** 解析後記憶 + 問題 → 答案。使用 MemoryAgentBench 對（方法類型 × 任務）的**標準 qa 模板**，絕不客製 inference prompt（客製會混淆「贏在記憶還是贏在答題 prompt」）；各任務所用模板逐一列於附錄。

## 3.4 設計性質（一段話收束）

寫入端 LLM 只做單筆轉錄（P1/P2），查詢端 LLM 只剩一個窄任務（P3 身分分群補救，且僅在結構失效的少數案例觸發）；分群主要由 (S, P) 精確比對承擔、解析由 argmax 承擔。因此：(i) 持久記憶狀態與任何 LLM 判斷無關——誤判從永久變暫時；(ii) 系統對 backbone 判斷品質的依賴被壓到最低——此為 weak/frozen backbone 部署宣稱的機制基礎；(iii) 解析用畢即棄、不回寫，每次查詢在完好的記憶上重解。

---

# 4. ☐ 待決問題（僅 Method 部分）

> Experiment / Evaluation / Baseline 相關的待決問題已移至 [`evaluation_protocol_main.md`](evaluation_protocol_main.md) §6。此處只留與 method spec 本身相關的兩個。

1. **(S,P) 倒排索引死碼**（現行 pipeline 在寫入時另建 (S,P) 倒排索引但查詢期從未讀取，見 §3.2 註記）：
   - 選項 (a) 從 method 描述完全隱藏 + 在程式碼移除
   - 選項 (b) 保留程式但在 repo README 註明 disabled（避免 reviewer 對照 code 時混淆）
   - **建議** (b)：最小改動、誠實揭露 dead-code

2. **P5 程式開關 flag 名稱**（核心版 group→argmax 直連 vs ablation 加 P5）：
   - **現行實作**：env var `MEM0_P5_SKIP`
     - `unset`（default）→ P5 on = `ours(full)`（現降級 ablation）
     - `=1` → P5 skip = `ours(no_p5)`（paper 主 method）
   - 見 `methods/phase2_query.py:483`
   - **建議**：保留現行、不改；paper method spec 就以「無 P5」為主敘述，ablation 表格再列 `ours(full)`

<!-- items 1-6, 8（實驗/baseline/backbone/embedding 相關）→ evaluation_protocol_main.md §6 -->

---

# Appendix A. Actual prompts used in pipeline(從 source code 直接抽取)

> **來源**：`methods/mem0_fc_prompt_fix.py`（P1）、`methods/phase0_triple_extractor.py`（P2）、`methods/phase2_query.py`（P3 / P5）。任何 prompt 改動請同步更新本 appendix。
> **論文對接**：P1 / P2 / P3 為主 method 使用；P5 僅供 ablation（`ours(full)`）用。P4 使用 MemoryAgentBench 官方 qa 模板（不客製，論文正文於 setup 揭露）。

## A.1 P1 — Unified extraction prompt（`make_unified_extractor_prompt()`）

抽取 USER 主張的原子事實；source-based / faithfulness / selectivity 三個錨點。

```text
You are a Memory Organizer. From a conversation between a user and an assistant, extract the distinct facts that the USER asserts as true -- about themselves or about the world -- and record them as separate, atomic facts for later retrieval. The memory you build holds what the user has told the system; it is authoritative over the assistant's own knowledge.

Use the whole conversation -- both speakers -- to UNDERSTAND what the user means: resolve references ("it", "there", "that") and read the assistant's replies as context that clarifies the user's statements. But RECORD facts ONLY from what the USER asserts. The assistant's turns are context for understanding, NEVER a source of facts to store.

What to record (from the user's statements):
- Any fact the user states as true: personal information, preferences, plans, relationships, situations, AND general / world facts the user asserts (including values that differ from common knowledge).
- Record one fact per statement; split a sentence asserting several facts into separate atomic facts.

Faithfulness:
- Transcribe each asserted fact exactly as the user states it, even if it contradicts common knowledge or an earlier statement. Do NOT fact-check, correct, or judge truth. Conflicting or updated values are expected -- record them as given.

What NOT to record (selectivity):
- Greetings, questions, requests, and small talk that assert no fact.
- Anything the ASSISTANT contributes on its own -- advice, recommendations, instructions, explanations, or general knowledge. (As stated above, the assistant is context only, never a fact source. If the user later restates something as their own, record the user's statement.)
- If the user asserts no fact, return an empty list.

Return JSON with a single key "facts" whose value is a list of strings. Detect the input language and record the facts in that language.

Examples:
Input:
user: Hi there!
assistant: Hello! How can I help?
Output: {"facts": []}

Input:
user: My name is John and I just moved to Boston.
Output: {"facts": ["Name is John", "Moved to Boston"]}

Input:
user: Can you suggest a good 5K training plan?
assistant: Sure -- try interval sprints of 20-30 seconds with 1-2 min recovery.
Output: {"facts": []}

Input:
user: By the way, the CEO of Acme is now Dana Lee, and the capital of Australia is Sydney.
Output: {"facts": ["The CEO of Acme is now Dana Lee", "The capital of Australia is Sydney"]}

Remember today's date is {YYYY-MM-DD}.  # 動態插入
```

## A.2 P2 — Triple extraction: DECOMPOSITION_RULES

引導 P2 LLM 抽 (subject, predicate, object)：subject 是「更新後仍固定的實體」、object 是「會變動的值」。

```text
- Subject = the entity the fact/question is about, and that stays fixed if the
  fact is later updated; object = the specific value that could change (the
  answer); predicate = the relation linking them.
- Decompose nominal relations into standard (subject, relation, object) form.
  When the phrasing is "the <relation> of <entity>" (e.g. "the author of X",
  "the capital of Y"), do NOT use that whole noun phrase as the subject and do
  NOT use "is" as the predicate. Instead: subject = <entity>, predicate = the
  relation as a verb phrase (e.g. "has <relation>"). The relation must become
  the predicate, never be swallowed into the subject.
- predicate is a SHORT natural-language verb phrase; do NOT map it to a fixed
  vocabulary, snake_case, or canonical form — keep the natural wording.
- subject is a named entity or attribute value, taken verbatim (do not
  paraphrase). For user/assistant referents output "user"/"assistant".
```

## A.3 P2 — subject / predicate normalize（deterministic post-LLM）

```python
# normalize_subject: Level-1 ONLY（entity name 不做 article/of stripping）
def normalize_subject(subject_text: str, user_id: str | None = None) -> str:
    s = (subject_text or "").lower().strip()
    s = re.sub(r"[-‐-―]", " ", s)                 # L1: hyphens/dashes -> space
    s = re.sub(r"\s+", " ", s).strip()            # L1: collapse whitespace
    if s in {"user", "i", "me", "my", "myself"}:
        return f"user::{user_id}" if user_id else "user"
    if s in {"assistant", "you", "claude", "agent"}:
        return "assistant"
    return re.sub(r"\s+", "_", s)

# normalize_predicate: L1 + L2（drop articles/of + normalize copula tense）
_PRED_ARTICLES = {"the", "a", "an", "of"}
_PRED_COPULA   = {"is", "was", "are", "were", "be", "been", "being"}

def normalize_predicate(predicate_text: str) -> str:
    s = (predicate_text or "").lower().strip()
    s = re.sub(r"[-_‐-―]", " ", s)                # L1: hyphen/underscore/dash -> space
    toks = re.sub(r"\s+", " ", s).strip().split() # L1: collapse whitespace
    # L2: drop articles/of; normalize copula/tense (is/was/are/... -> be).
    out = [("be" if t in _PRED_COPULA else t) for t in toks if t not in _PRED_ARTICLES]
    return " ".join(out) or " ".join(toks) or (predicate_text or "").lower().strip()
```

## A.4 P3 — Identity grouping（LLM,僅對 dynamic_pool）

```text
You are analyzing a list of memory entries retrieved for a user query. Your ONLY
task is to find CLUSTERS of entries that are the SAME fact recorded in different
versions. You do NOT answer the query, summarize, or decide which entry is newer.

# THE TEST (apply strictly)
Cluster two entries ONLY IF they are competing answers to the EXACT SAME question
about the EXACT SAME specific entity — same specific subject AND same property —
where only the value (answer) differs across versions.

# HARD RULES — when NOT to cluster (these dominate)
1. DIFFERENT SPECIFIC ENTITY = DIFFERENT FACT. If two entries are about different
   named entities (two different people, places, things, or organizations), they
   are DIFFERENT facts. Do NOT cluster them — even if they share the same wording,
   the same attribute type, or the SAME value. (A shared answer like many
   different people each being "a citizen of the USA" is NOT one fact.)
2. DIFFERENT PROPERTY = DIFFERENT FACT. Same entity but different property
   (its capital vs its head of state; the user's city vs the user's job) are
   DIFFERENT facts. Do NOT cluster them.
3. MULTI-VALUED PROPERTY = COEXIST. If the property naturally holds several
   values at once (hobbies, friends, languages spoken, places visited, skills,
   things liked), the values COEXIST — they are NOT versions. Do NOT cluster.

# Clustering is RARE
In a typical list, most or ALL entries are unrelated and form NO clusters. Expect
zero or very few clusters. Cluster only when you are CONFIDENT the entries are the
same single-valued fact about the same specific entity. When unsure, do not
cluster — unclustered entries are simply kept (a false merge hides a real value;
a false split is harmless).

# Identity only — never recency
Cluster purely by fact identity. Do NOT judge which entry is newer or correct —
a separate deterministic step handles that.

# Output — clusters only
Output ONLY the clusters you are confident about, each with 2+ members. Entries
not placed in a cluster MUST NOT be listed (they are kept automatically). If you
find no clusters, output {"groups": []}.

Return JSON exactly:
{
  "groups": [
    {"fact": "<the specific entity + property>", "memory_ids": ["<id>","<id>"], "reasoning": "<one sentence>"}
  ]
}

# Examples（含正/負範例,略 — 全文見 methods/phase2_query.py:32-116）

# Now analyze:
Query: {query}
Memory entries:
{entries}
```

## A.5 P5 — Conflict-type classifier（**ablation only,`ours(full)` 用**;paper 主 method 已 skip）

```text
You analyze a group of candidate memory entries that share the same subject and relation but have different recorded values. Determine which conflict type applies, so the downstream resolution step knows whether to select the most recent value or keep all of them.

Apply ONE of the following categories (adapted from Cattan et al., 2025, CONFLICTS taxonomy, restricted to memory accumulation scenarios where the source is user assertions):

(1) NO_CONFLICT — The candidates record the SAME value expressed in different surface forms (e.g., "Tokyo" vs "Tokyo"; "350,000" vs "$350k"; "PhD" vs "doctorate"). Minor variations in granularity or phrasing without semantic difference.

(2) FRESHNESS — The candidates are mutually exclusive at any single point in time. A single subject cannot simultaneously hold all listed values; the newer value supersedes the older. Examples: current city, current employer, current count/total, personal best, mortgage amount, marital status.

(3) COMPLEMENTARY — The candidates are mutually compatible. The same subject can reasonably hold all listed values simultaneously, without contradiction. The values are accumulating instances, not competing answers. Examples: brands tried, languages spoken, places visited, hobbies, restaurants visited.

DECISION TEST (apply strictly, in order):
  Step 1: Are these surface variants of one value? YES -> NO_CONFLICT.
  Step 2: Could the subject reasonably hold ALL listed values AT THE SAME TIME, right now? YES -> COMPLEMENTARY.  NO -> FRESHNESS.

When uncertain between FRESHNESS and COMPLEMENTARY, default to COMPLEMENTARY (false-merge into Freshness destroys information; false-split into Complementary is recoverable downstream).

Query: {query}
Subject: {subject}
Relation: {predicate}
Candidate values (with timestamps):
{candidates_with_timestamps}

Return JSON exactly: {"type": "no_conflict" | "freshness" | "complementary", "reasoning": "<one sentence>"}
```

## A.6 P4 — Answer LLM prompt

**不客製,使用 MemoryAgentBench 官方 qa template**(依 `sub_dataset` × `agent_name` 決定,見 `get_template()`)。避免「贏在記憶還是贏在答題 prompt」的混淆。實際 template 於論文正文 setup 揭露、各任務所用 template 列於 paper appendix。

