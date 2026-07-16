# Methodology Source Material — 論文 Methodology 章的完整素材(2026-07-16)

> **用途**:寫 Methodology 章的**單一來源**。所有 pipeline 步驟、prompts、hyperparameters、baseline 執行細節皆抄自 canonical run,能直接引用。
> **範疇**:僅收錄**論文實際使用**的方法設計 + prompts。 dead code(HippoRAG、MemoRAG、GraphRAG、Letta、Cognee、mem0g、L1/L2/broadened-native 等)於 §Excluded 明列**不寫進 methodology**。
> **對應敘事**:[`abstract_0716.md`](abstract_0716.md)、[`introduction_0716.md`](introduction_0716.md)、[`related_work_0716.md`](related_work_0716.md)。三個 commitment(faithful write、query-time KU、decomposed simple LLM tasks)於 CLAUDE.md 已定義。

---

## §1. Overview:三個階段(Write / Retrieval / Query-time KU Resolution)

Ours 方法將 KU 分解為三個階段;LLM 僅於 write-time 提取結構(P1 + P2)+ query-time identity 補救(P3 fallback),**不參與 KU 決策**。

```
Write-time (faithful, no KU decision):
  chunker → P1 unified fact extraction → P2 (S,P,O) triple
         → subject/predicate normalization → qdrant + ordinal metadata
         → (S,P) inverted index (in-memory + persist JSON)

Retrieval (query starts):
  raw-question strip → top-100 vector search over stored facts

Query-time KU resolution (deterministic first, LLM fallback):
  Phase 0 — 對 retrieved candidates 按 (S,P) canonical key 分組 → deterministic argmax(ordinal)
  Phase 3 — 對「無 triple」或「(S,P) 未能歸群」的殘餘 candidate 呼叫 LLM 判 identity(補救)
  → 各群 argmax(ordinal) → resolved memories → answer LLM
```

**核心屬性**:
- Write-time **不做任何跨筆判斷**;所有版本永久保留。
- Query-time KU 由 (subject, predicate) 結構 + argmax(ordinal) 決定,**LLM 僅在 P3 補救介入,不判 recency,不改記憶**。
- Ordinal = **per-user 全域 fact-level counter**(不是 chunk-level),`argmax(ordinal) = 最新版本`。

---

## §2. Write-time Pipeline

### §2.1 Chunker(dataset-conditional)

Router at [`conversation_creator.py:271-285`](../../../../conversation_creator.py):

```python
if 'factconsolidation' in self.sub_dataset.lower():
    chunker = chunk_facts_by_line          # fact-aware: 一 numbered fact = 一 atomic unit
else:
    chunker = chunk_text_into_sentences    # prose sentence chunker (nltk sent_tokenize)
```

- **`chunk_facts_by_line`**([utils/eval_other_utils.py:229-273](../../../../utils/eval_other_utils.py#L229-L273)):FC-SH 使用。以 `N. <fact>` 為 atomic unit,絕不跨 unit 切;tiktoken(gpt-4o-mini tokenizer)packs 至 `chunk_size=512`。修正 serial-number boundary stranding。
- **`chunk_text_into_sentences`**:LongMemEval 對話使用。依 sentence 切,packs 至 512 tokens。

### §2.2 P1 — Unified Fact Extraction Prompt

**Function**:`make_unified_extractor_prompt()` at [`methods/mem0_fc_prompt_fix.py:196-238`](../../../../methods/mem0_fc_prompt_fix.py#L196-L238)。
**觸發**:yaml `use_unified_extractor: true` → agent.py:495-504 於 `Agent.__init__` 注入到 mem0 `custom_fact_extraction_prompt`。
**用意**:一個 front-end 同時處理 FC-SH(world/counterfactual fact)與 LME(personal conversation);selectivity + faithfulness 兩條硬規則。

**Prompt 全文**:

```
You are a Memory Organizer. From a conversation between a user and an assistant,
extract the distinct facts that the USER asserts as true -- about themselves or
about the world -- and record them as separate, atomic facts for later
retrieval. The memory you build holds what the user has told the system; it is
authoritative over the assistant's own knowledge.

Use the whole conversation -- both speakers -- to UNDERSTAND what the user
means: resolve references ("it", "there", "that") and read the assistant's
replies as context that clarifies the user's statements. But RECORD facts ONLY
from what the USER asserts. The assistant's turns are context for
understanding, NEVER a source of facts to store.

What to record (from the user's statements):
- Any fact the user states as true: personal information, preferences, plans,
  relationships, situations, AND general / world facts the user asserts
  (including values that differ from common knowledge).
- Record one fact per statement; split a sentence asserting several facts into
  separate atomic facts.

Faithfulness:
- Transcribe each asserted fact exactly as the user states it, even if it
  contradicts common knowledge or an earlier statement. Do NOT fact-check,
  correct, or judge truth. Conflicting or updated values are expected --
  record them as given.

What NOT to record (selectivity):
- Greetings, questions, requests, and small talk that assert no fact.
- Anything the ASSISTANT contributes on its own -- advice, recommendations,
  instructions, explanations, or general knowledge. (As stated above, the
  assistant is context only, never a fact source. If the user later restates
  something as their own, record the user's statement.)
- If the user asserts no fact, return an empty list.

Return JSON with a single key "facts" whose value is a list of strings. Detect
the input language and record the facts in that language.

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
  user: By the way, the CEO of Acme is now Dana Lee, and the capital of
        Australia is Sydney.
Output: {"facts": ["The CEO of Acme is now Dana Lee",
                   "The capital of Australia is Sydney"]}

Remember today's date is {today}.
```

**Cache**:`MEM0_EXTRACTION_CACHE` = per-chunk hash → 已 extract 的 facts JSON,重跑 zero LLM cost。

### §2.3 P2 — Triple (S,P,O) Extraction Prompt

**File**:[`methods/phase0_triple_extractor.py:44-111`](../../../../methods/phase0_triple_extractor.py#L44-L111)(`TRIPLE_EXTRACTION_PROMPT`)。
**觸發**:每次 P1 產出的 fact list 直接進 `extract_triples_batch()`([lines 372-456](../../../../methods/phase0_triple_extractor.py#L372-L456));backend-aware batch(gpt* → 50、local 7b → 1);JSON mode 強制。
**目的**:將 fact 拆為 `(subject, predicate, object)`。**Subject = 不變實體、Object = 可變 value、Predicate = 短動詞片語**——讓同一 fact 的多版本落到同一 (S,P)。

**Prompt 全文**:

```
You are a triple extractor. For EACH input fact (a single declarative
statement extracted from conversation memory), extract its (subject,
predicate, object) triple.

Rules:
- Choose subject = the entity the fact is about, and that stays fixed if the
  fact is later updated; object = the specific value that could change (the
  answer); predicate = the relation linking them. This keeps different
  versions of the same fact under the same (subject, predicate).
- Decompose nominal relations into standard (subject, relation, object) form.
  When the grammatical subject is a noun phrase of the form
  "the <relation> of <entity>" (e.g. "the <ROLE> of <ENTITY>",
  "the <ATTRIBUTE> of <ENTITY>"), do NOT use that whole phrase as the subject
  and do NOT use "is" as the predicate. Instead: subject = <entity>,
  predicate = the relation expressed as a verb phrase (e.g. "has <relation>"),
  object = the stated value. The relation must become the predicate — never be
  swallowed into the subject. This is the standard KG (s, r, o) convention.
- predicate is a SHORT natural-language verb phrase describing the relation.
  Do NOT map it to any fixed vocabulary, snake_case, or canonical form — keep
  the natural wording.
- subject / object are named entities or attribute values, taken verbatim from
  the fact text (do not paraphrase or summarize).
- For pronouns: if the referent is the user/assistant, output "user" or
  "assistant". For other clearly-resolvable pronouns, use the resolved entity
  name. If unresolvable, set triple to null.
- Extract triples regardless of topic, including personal information,
  preferences, opinions, and world knowledge — treat all facts uniformly.
- Never skip or null a fact because it seems factually false. Facts may be
  deliberately counterfactual; extract them anyway and do NOT verify against
  world knowledge. This rule is ONLY about not judging truth — it does NOT
  change how you pick subject/predicate/object; still apply the decomposition
  rules above (e.g. a counterfactual "The R of E is V" still becomes
  subject=E, predicate="has R", object=V).
- If a fact is a subjective state, a complex narrative, OR contains multiple
  independent facts, set its triple to null. Do NOT force a triple.
- null is a valid and ENCOURAGED answer — do not force a triple.
- Confidence reflects how cleanly the fact fits the triple form. Give high
  confidence (>0.8) only when subject, predicate, object are unambiguous.

Examples:
Fact: "The user lives in Taipei."
→ {"subject": "user", "predicate": "lives in", "object": "Taipei",
   "confidence": 0.95}
Fact: "Marie Curie was born in Warsaw."
→ {"subject": "Marie Curie", "predicate": "was born in", "object": "Warsaw",
   "confidence": 0.95}
Fact: "The user feels stressed about work lately."
→ null  (subjective state, not cleanly a triple)
Fact: "She moved to Tokyo and got a new job."
→ null  (multiple independent facts + unresolved pronoun)

Input is a numbered list of facts. Return JSON:
{
  "results": [
    {"id": 0, "triple": {"subject": "...", "predicate": "...", "object": "...",
                          "confidence": 0.0}},
    {"id": 1, "triple": null}
  ]
}

Facts:
{numbered_facts}
```

**Cache**:`MEM0_TRIPLE_CACHE`(per-fact hash)。

### §2.4 Subject-Only Fallback(triple-null 補救)

**Prompt**:[`SUBJECT_EXTRACTION_PROMPT`](../../../../methods/phase0_triple_extractor.py#L119-L142)(triple 判定為 `null` 時使用)。
**用途**(query-time 實際被讀):填入 `metadata.subject_fallback` → 於 [§4.2 P3 identity fallback](#42-phase-3-llm-identity-fallback) 的 `_subject_consistent()` guard 中讀取([`phase2_query.py:143`](../../../../methods/phase2_query.py#L143));**guard 於 P3 LLM 建議的 cluster 內若成員橫跨 ≥2 個不同 subject 就 reject**,對 triple-null 的抽象/敘述性記憶(subjective / narrative / multi-fact),subject_fallback 是這個 guard 唯一能啟用的訊號。移除此 fallback → triple-null 記憶於 P3 分群時 subject 皆為 `None` → guard 失效 → LLM 錯 merge 頻率上升。
**Ablation candidate**(future work,§4.5 可擴):`SUBJECT_EXTRACTION_PROMPT` 停用 → 只比 subject_fallback 有無時 P3 錯 merge rate + 下游 has_pair sEM,量化 subject fallback 的具體貢獻。

```
Identify the single entity each fact is primarily ABOUT — the subject it
would have if rewritten as "<subject> — <attribute> — <value>".

- About the user themselves: "user".
- About someone/something tied to the user: that specific entity
  (e.g. "user's spouse", "user's son", a named friend, pet, or organization).
  Do NOT collapse these to "user" — they are distinct subjects.
- World knowledge: the named entity the fact is about (the entity, not the
  role: "The capital of France is Paris" -> "France", not "the capital").

Return the subject as a short string; if there is genuinely no identifiable
subject, return null.

Input is a numbered list of facts. Return JSON:
{
  "results": [
    {"id": 0, "subject": "..."},
    {"id": 1, "subject": null}
  ]
}

Facts:
{numbered_facts}
```

### §2.5 Subject / Predicate Normalization

**File**:[`methods/phase0_triple_extractor.py:232-259`](../../../../methods/phase0_triple_extractor.py#L232-L259)。

**`normalize_subject(text, user_id)`**:
- Lowercase,unify hyphens/dashes,collapse whitespace
- **User pronouns** `{user, i, me, my, myself}` → `user::<user_id>`(per-user namespace,避免不同 session 的 "user" 互撞)
- **Assistant pronouns** `{assistant, you, claude, agent}` → `assistant`
- Otherwise:spaces → `_`
- **不移除**冠詞 / "of"(避免 "the capital of France" 與 "France" 混淆)

**`normalize_predicate(text)`**:
- Lowercase,unify hyphens/underscores/dashes → space
- **移除冠詞** `the`, `a`, `an`, `of`
- **Copula collapse**:`is/was/are/were/be/been/being` → `be`
- **例**:`"is the capital of"` → `"be capital"`;`"was born in"` → `"be born in"`

**(S,P) key 建構**:`sp_key = f"{subject_id}\x1f{predicate_norm}"`(SEP = `\x1f` US char,跨 mem0/methods/analysis 統一)。此 key **不作為倒排索引 lookup**(見 §10.4),而是**以 canonical string 形式儲存在每則 memory 的 `metadata.triple` 內**,query-time 時 [§4.1 group_and_resolve](#41-phase-0-structural-grouping--deterministic-freshness) 直接從 metadata 讀取後分群。

**Ablation candidate**(future work,§4.5 可擴):normalize_subject / normalize_predicate 於強 backbone 上關掉(直接用 raw subject/predicate 建 SP key)→ 觀察同一 fact 於 (S,P) 分群下的 collision rate 變化(如 `"is the capital of"` vs `"was capital of"` 是否會落到不同群)+ 下游 has_pair sEM,量化 normalization 的具體貢獻。

### §2.6 Storage — qdrant + Per-Memory (S,P) Metadata

**Entry point**:`_add_phase0_structural()` at [`mem0/memory/main.py:985-1103`](../../../../mem0/memory/main.py#L985-L1103)。

**Per-fact write flow**(lines 1026-1067):
1. `fact_ordinal = chunk_ordinal + fact_within_chunk_idx` — per-user global fact-level counter
2. 組 metadata:`md = {**metadata, "ordinal": fact_ordinal, "triple": <see schema below>}`(triple-null 時改填 `subject_fallback`)
3. Batch embed fact text([line 1022](../../../../mem0/memory/main.py#L1022))
4. `_create_memory(fact, embedding, md)` → 寫入 qdrant collection

**Store 隔離**:agent.py:265-273 自動 append `__<sub_dataset>` 於 yaml `path:` 與 `collection_name:`(不同 dataset / length 各自獨立 store)。

**Per-memory metadata schema**(query-time 直接讀取):
```json
{
  "ordinal": <int>,
  "triple": {
    "subject_id": "<normalized>",
    "predicate_norm": "<normalized>",
    "object_text": "<verbatim value>",
    "confidence": <float>,
    "subject_raw": "<pre-norm>",
    "predicate_raw": "<pre-norm>"
  }
}
```
或(triple 抽取為 null 時):
```json
{
  "ordinal": <int>,
  "triple": null,
  "subject_fallback": "<from SUBJECT_EXTRACTION_PROMPT>"
}
```

**核心設計 note — Ordinal**([mem0/memory/main.py:313-317](../../../../mem0/memory/main.py#L313-L317)):
> "Fact-level ordinal: per-uid GLOBAL per-fact counter (not per-chunk) … so query-side max()=newest needs ZERO change while intra-chunk same-(S,P) ties disappear."

**Query-time consumption**([§4.1](#41-phase-0-structural-grouping--deterministic-freshness)):`self.memory.search(query, ..., limit=100)` 取回 top-K memories → 直接於這 100 則 memory 各自的 `metadata.triple.(subject_id, predicate_norm)` 上分群 → 每群 argmax(`metadata.ordinal`)。**沒有額外的 (S,P) inverted-index lookup**;(S,P) canonical form 純粹以 per-memory metadata 呈現。

---

## §3. Retrieval

### §3.1 Raw-Question Strip

**Function**:`_retrieval_query(message)` at [`agent.py:963-994`](../../../../agent.py#L963-L994)。
**問題**:MABench harness 於 query 前將 raw question 用 `rag_agent` template 包成長字串(如 FC 的「Pretend you are a knowledge management system … {question} Answer:」)。若整段 embed 進 vector search → boilerplate 主導 embedding → recall drop(§5.6 experiment_results.md:6k has_pair GT_new recall@100 = 79% wrapped vs 100% raw)。
**解**:strip 已知 template prefix/suffix,只 embed bare question。**下游推論仍用完整 wrapped `message`**(包含 recency instruction)。

### §3.2 Vector Search

**Call**:`self.memory.search(query=retrieval_query, user_id=..., limit=self.retrieve_num)`
- `self.retrieve_num` 從 yaml `retrieve_num:` 讀入(canonical = 100)
- 內部走 mem0 qdrant search
- **Embedding model**:`text-embedding-3-small`(1536 dims)

---

## §4. Query-time KU Resolution

### §4.1 Phase 0 Structural Grouping + Deterministic Freshness

**File**:[`methods/phase0_query.py:129-146`](../../../../methods/phase0_query.py#L129-L146)。
**Function**:`group_and_resolve(cand_ids, id2item)` → `(resolved, ungrouped)`。

```python
def group_and_resolve(cand_ids, id2item):
    # 對每個 candidate,查 metadata.triple.(subject_id, predicate_norm)
    # → 按 (S,P) canonical key 分群
    # 無 triple 的 candidate 進 `ungrouped`(交給 Phase 3 補救)
    for id in cand_ids:
        sp = _sp(id2item[id])
        if sp is None:
            ungrouped.append(id2item[id])
        else:
            groups[sp].append(id2item[id])
    # 每群 argmax(ordinal),tie-safe(全部 max ordinal 留下)
    for members in groups.values():
        mx = max(m.metadata.ordinal for m in members)
        resolved.extend(m for m in members if m.metadata.ordinal == mx)
    return resolved, ungrouped
```

**特性**:
- **Deterministic**:純 dict lookup + argmax,無 LLM
- **Backbone-agnostic**:不呼 LLM → 表現不隨 backbone 能力變動
- **Ordinal = 寫入時序**(chunk 順序 + chunk 內 extraction 順序);對 FC / LME 兩 benchmark 而言,寫入順序 ≈ 對話 turn 順序 ≈ 事實時序

### §4.2 Phase 3 LLM Identity Fallback

**File**:[`methods/phase2_query.py:32-116`](../../../../methods/phase2_query.py#L32-L116)(`GROUPING_PROMPT`)。
**觸發**:對 Phase 0 未歸群的 `dynamic_pool`(triple-null items + singleton (S,P) items)。
**Job**:僅判 identity(哪幾則是「同一 fact 的多版本」),**不判 recency,不改記憶**。

**Prompt 全文**:

```
You are analyzing a list of memory entries retrieved for a user query. Your
ONLY task is to find CLUSTERS of entries that are the SAME fact recorded in
different versions. You do NOT answer the query, summarize, or decide which
entry is newer.

# THE TEST (apply strictly)
Cluster two entries ONLY IF they are competing answers to the EXACT SAME
question about the EXACT SAME specific entity — same specific subject AND
same property — where only the value (answer) differs across versions.

# HARD RULES — when NOT to cluster (these dominate)
1. DIFFERENT SPECIFIC ENTITY = DIFFERENT FACT. If two entries are about
   different named entities (two different people, places, things, or
   organizations), they are DIFFERENT facts. Do NOT cluster them — even if
   they share the same wording, the same attribute type, or the SAME value.
   (A shared answer like many different people each being "a citizen of the
   USA" is NOT one fact.)
2. DIFFERENT PROPERTY = DIFFERENT FACT. Same entity but different property
   (its capital vs its head of state; the user's city vs the user's job) are
   DIFFERENT facts. Do NOT cluster them.
3. MULTI-VALUED PROPERTY = COEXIST. If the property naturally holds several
   values at once (hobbies, friends, languages spoken, places visited,
   skills, things liked), the values COEXIST — they are NOT versions. Do
   NOT cluster.

# Clustering is RARE
In a typical list, most or ALL entries are unrelated and form NO clusters.
Expect zero or very few clusters. Cluster only when you are CONFIDENT the
entries are the same single-valued fact about the same specific entity.
When unsure, do not cluster — unclustered entries are simply kept (a false
merge hides a real value; a false split is harmless).

# Identity only — never recency
Cluster purely by fact identity. Do NOT judge which entry is newer or
correct — a separate deterministic step handles that.

# Output — clusters only
Output ONLY the clusters you are confident about, each with 2+ members.
Entries not placed in a cluster MUST NOT be listed (they are kept
automatically). If you find no clusters, output {"groups": []}.

Return JSON exactly:
{
  "groups": [
    {"fact": "<the specific entity + property>",
     "memory_ids": ["<id>","<id>"],
     "reasoning": "<one sentence>"}
  ]
}

# Examples (span personal and world-knowledge; note the negatives)

Query: Where does the user live now?
[a] The user used to live in Taipei.
[b] The user now lives in Tainan.
[c] The user enjoys hiking.
Output: {"groups": [{"fact": "the user's current city of residence",
                     "memory_ids": ["a","b"],
                     "reasoning": "Same person, single-valued residence; values are versions."}]}

Query: Who is the CEO of Acme Corp?
[d] Acme Corp's CEO is Jane Doe.
[e] Acme Corp's CEO is now John Smith.
[f] Acme Corp is headquartered in Berlin.
Output: {"groups": [{"fact": "Acme Corp's current CEO",
                     "memory_ids": ["d","e"],
                     "reasoning": "Same org, single-valued CEO; f is a different property."}]}

Query: Who is allergic to peanuts?
[g] The user is allergic to peanuts.
[h] The user's son is allergic to peanuts.
Output: {"groups": []}   (different subjects: the user vs the son)

Query: Where were these people born?
[i] Marie Curie was born in Warsaw.
[j] Frederic Chopin was born in Warsaw.
Output: {"groups": []}   (different people; a shared value is not one fact)

Query: Tell me about the user.
[k] The user's current city is Tokyo.
[l] The user's current employer is Acme.
Output: {"groups": []}   (same user, different properties)

Query: What languages does the user speak?
[m] The user speaks French.
[n] The user speaks Japanese.
Output: {"groups": []}   (multi-valued: languages coexist)

# Now analyze:
Query: {query}
Memory entries:
{entries}
```

**Subject-consistency guard**([lines 146-151](../../../../methods/phase2_query.py#L146-L151)):若 LLM 建議的 cluster 有 ≥2 個 distinct KNOWN subject → **reject cluster**(異體不同 fact,LLM 錯 merge)。未知 subject 不阻擋(那才是 P3 該補救的案例)。

### §4.3 Orchestrator — `phase2_resolve`

**File**:[`methods/phase2_query.py:463-492`](../../../../methods/phase2_query.py#L463-L492)。

```python
def phase2_resolve(candidates, query):
    structural_pool, dynamic_pool = conditional_structural_routing(candidates)
    clusters = llm_identity_clusters(dynamic_pool, query)  # P3
    groups = list(structural_pool.values()) + clusters
    p5_skip = os.environ.get("MEM0_P5_SKIP") == "1"
    drop = set()
    for g in groups:
        if len(g) < 2:
            continue
        if not p5_skip and _classify_conflict_type(g, query) != "freshness":
            continue   # NO_CONFLICT / COMPLEMENTARY → keep all
        d, _ = _drop_older(g)   # argmax(ordinal); ties safe
        drop |= d
    return [it for it in candidates if _id(it) not in drop]
```

**於 main method**:設 `MEM0_P5_SKIP=1` → **每個 ≥2 群一律 argmax(ordinal)**,不呼 P5。這是 paper canonical setup(見 §7 ablation)。

### §4.4 Answer LLM Prompt(benchmark-native)

**File**:[`agent.py:1177-1225`](../../../../agent.py#L1177-L1225)。

`ours main`(非 q_llm_recency)於 answer 階段走 else-branch:
- **SYSTEM**:`"You are a helpful AI. Answer the question based on query and memories.\n{memories_str}\n"` 其中 `memories_str = "\n".join(f"- {m}" for m in resolved)`
- **USER**:`{message} + "\n\nCurrent Time: " + <timestamp>`
  - `message` = MABench harness 已用 dataset-native `rag_agent` template 包好的 wrapped question(FC-SH 含 recency instruction、LME 含 chat-history instruction)

---

## §5. Baseline 執行細節(論文實際比較)

### §5.1 (a) vanilla mem0(mem0 native L1 extractor + destructive commit)

**Yaml**:`Structure_rag_gpt-4o-mini-mem0_512_openai_native.yaml`(**沒有** `use_unified_extractor: true` → 走 mem0 內建 L1 `FACT_RETRIEVAL_PROMPT`)。
**Env**:`unset MEM0_ADD_MODE MEM0_QUERY_MODE MEM0_EXTRACTION_CACHE MEM0_TRIPLE_CACHE`(mem0 完整原生 flow:抽取 + 破壞性 UPDATE/DELETE 判斷)。
**Query**:agent.py else-branch(line 1165)raw top-k concatenation,無 query-time resolve。

### §5.2 (b) mem0+P1(held-fixed P1 + mem0 destructive)

**Yaml**:`Structure_rag_gpt-4o-mini-mem0_512_openai_unified_dest.yaml`(**有** `use_unified_extractor: true`)。
**Env**:`MEM0_EXTRACTION_CACHE="$PC/extraction_cache_p1_{L}.json"`(reuse ours 的 P1 cache = held-fixed 相同抽取);`unset MEM0_ADD_MODE MEM0_QUERY_MODE MEM0_TRIPLE_CACHE`。
**用意**:隔離「抽取品質」與「destructive commit damage」——(b) 於 vanilla 抽取崩壞的 FC 上勝過 vanilla,但 damage 仍存在。
**Query**:同 vanilla(raw top-k)。

### §5.3 Zep(decoupled write-time labeling)

**Yaml**:`Structure_rag_gpt-4o-mini-zep_512_temp0.yaml`(`retrieve_num: 10`,Zep 官方推薦)。
**Path**:`agent.py:_handle_zep_agent`([lines 1261-1660](../../../../agent.py#L1261-L1660)) + [`methods/zep.py`](../../../../methods/zep.py):
- **Write-time**:Zep cloud graph service 自行抽取 + 標 duplicate/contradict + 於 edge metadata 加 `invalid_at`/`expired_at` timestamp(**LLM 不直接改記憶,但 timestamp 被永久寫入**)
- **Query-time**:`compose_search_context()`([zep.py:38-45](../../../../methods/zep.py#L38-L45))把 `facts`(edges with valid_at - invalid_at)+ `entities` + `episodes` 折疊為 context;`get_retrieval_query()`([zep.py:146-182](../../../../methods/zep.py#L146-L182))FC-fair strip
- **Answer LLM**:[`zep.py:114-129`](../../../../methods/zep.py#L114-L129)`llm_response` short-answer prompt
- **Top-K**:`ZEP_TOP_K` env(default = yaml `retrieve_num`)

### §5.4 Don't Ask [Reddy & Challaram, 2026]

**Repro script**:[`docs/0615_.../scripts/maxserial_theircode.py`](../../scripts/maxserial_theircode.py) — imports authors' verbatim pipeline as module `A`([line 94](../../scripts/maxserial_theircode.py#L94)),Langfuse instrumentation stubbed with no-op([lines 66-92](../../scripts/maxserial_theircode.py#L66-L92))。
**Fact bank**:reuse **ours' P1 extraction cache**(FC-SH:`extraction_cache_p1_{L}.json`),ordinal = running index over facts。**Cross-backbone P1 held-fixed at gpt-4o-mini**(避免抽取品質干擾比較)。
**Retrieval**:default vector top-100(fair to ours);authors' native = BM25 top-10(available via `--retrieval bm25`)。
**Candidate extraction LLM**:`PIPELINE_MODEL` env(可為 gpt-4o-mini / gpt-4.1-mini / gpt-5.4-mini / gemma via `OLLAMA_CHAT_URL`)。

**Author's `CANDIDATE_PROMPT`**(來自 [`related work/memory-conflict-resolution/scripts/_pipeline.py:279-297`](../../related%20work/memory-conflict-resolution/scripts/_pipeline.py#L279-L297),verbatim):

```
You are given retrieved items from a knowledge pool. Each item has a FRESHNESS
marker (the prefix integer) — higher marker = newer version.

Your job: identify EVERY item that DIRECTLY answers the question, and extract
the answer entity from each.

Do NOT compare freshness markers. Do NOT pick a "best" one. Include ALL items
that match.

Rules:
1. An item directly answers the question only if BOTH its subject AND its
   predicate exactly match what the question asks about. …
2. The subject named in the question must appear verbatim in the matching item. …
3. If a subject has multiple conflicting values …, INCLUDE BOTH …
4. If no item answers the question, return an empty list.
5. Copy the item's text verbatim into `fact_text`.

Question: {hop_query}

Items:
{pool}

Return ONLY valid JSON:
{"candidates": [{"serial": <int>, "fact_text": "<verbatim>",
                 "answer_entity": "<extracted>"}, ...]}
```

**Freshness pick**:`_freshness_pick(candidates)` = `max(candidate.serial)`(deterministic)。
**Metric**:官方 MAB SubEM(`substring_exact_match` + `default_post_process`)。
**Scope caveat(§4.6.7 已寫)**:LME-KU 上未執行——原論文 mechanism 假設 dataset 提供 global-serial fact bank,LME per-session 對話結構不符合。

### §5.5 Q-llm-recency Single-Stage(FC-SH benchmark-native)

**Yaml**:`Structure_rag_gpt-4o-mini-mem0_512_openai_unified_q_llm_recency.yaml`(reuse `ours_no_p5` populated store)。
**Env**:`MEM0_ADD_MODE=phase0_structural`、`MEM0_QUERY_MODE=q_llm_recency`、`MEM0_P5_SKIP=1`、`MEM0_Q_LLM_RECENCY_TOPK=100`(FC-SH canonical)。
**Branch**:[`agent.py:1058-1076`](../../../../agent.py#L1058-L1076)。
**Memories format**:`{ordinal}. {memory}` 對 top-K。
**Prompt template**:走 `factconsolidation.system` + `factconsolidation.rag_agent`(benchmark-native,見 §6),template 內含「serial 大 = 新」recency rule。
**於 FC-SH 上 fair**:此 template 是 dataset 原生設計,ours main / vanilla / (b) 於 answer 階段也用同一 template。
**於 LME-KU 上 NOT fair**:LME 原生 template 沒有 recency rule → 若 override 到 FC template 則 Q-llm-recency 是唯一被 prompt-augment 的 method → 因此 LME 上改用 two-stage(§5.6)。

### §5.6 Q-llm-recency Two-Stage(LME rigor fix)

**Yaml**:同 §5.5(reuse `ours_no_p5` populated store)。
**Env**:`MEM0_QUERY_MODE=q_llm_recency_two_stage`(**NOT** setting `MEM0_Q_LLM_RECENCY_TEMPLATE_DS`;Stage 2 用 LME native template)。
**Branch**:[`agent.py:1077-1164`](../../../../agent.py#L1077-L1164)。

**Stage 1(recency filter)**:mirror FC-SH `factconsolidation.rag_agent` 的 recency 語意,只改 output(從答題改為選 serial),**不為 LME 多值特性 tune**。
- **SYSTEM**:`"You are a helpful assistant that can read the context and memorize it for future retrieval."`(MABench 通用 SYSTEM_MESSAGE)
- **USER**(hardcoded at agent.py:1100-1122):

```
{ordinal}. {memory}
{ordinal}. {memory}
...

Pretend you are a knowledge management system. Each fact in the knowledge pool
above is provided with a serial number at the beginning, and the newer fact
has larger serial number.
You need to solve the conflicts of facts in the knowledge pool by finding the
newest fact with larger serial number. You need to identify the winning fact
based on this rule **only** from the knowledge pool you have memorized rather
than the real facts in real world.

For example:

[Knowledge Pool]
1. The name of the current president of Russia is Vladimir Putin.
5. The name of the current president of Russia is Donald Trump.

Question: Based on the provided Knowledge Pool, what is the name of the
current president of Russia?
Selected serial: 5

Now identify the serial for the Question: Based on the provided Knowledge
Pool, {raw_question}
Selected serial:
```

**Parse**:`re.findall(r"\d+", stage1_resp)` → 過濾到 retrieved ordinals 集合內 → dedup 保序。**Fallback**:0 valid ordinal → winners = full top-K(safe fallback,fallback 率為診斷指標;LME 上實測 1/78 = 1.3%)。
**Stage 2**:winners 用 `- {memory}` 格式(**無 ordinal、無 recency rule**)→ 走 else-branch → LME native `rag_agent` template + `factconsolidation.system`(SYSTEM 相同,USER 為 native template wrapping) → 與 ours main / vanilla / b **byte-identical**。

---

## §6. Benchmark-Native Inference Templates(必用,不改)

**File**:[`utils/templates.py`](../../../../utils/templates.py)。

### §6.1 SYSTEM_MESSAGE(共用,line 2)
```
You are a helpful assistant that can read the context and memorize it for
future retrieval.
```

### §6.2 factconsolidation.rag_agent(FC-SH,lines 78-83)

```
Pretend you are a knowledge management system. Each fact in the knowledge
pool is provided with a serial number at the beginning, and the newer fact
has larger serial number.
You need to solve the conflicts of facts in the knowledge pool by finding
the newest fact with larger serial number. You need to answer a question
based on this rule. You should give a very concise answer without saying
other words for the question **only** from the knowledge pool you have
memorized rather than the real facts in real world.

For example:
 [Knowledge Pool]
 Question: Based on the provided Knowledge Pool, what is the name of the
current president of Russia?
Answer: Donald Trump

 Now Answer the Question: Based on the provided Knowledge Pool, {question}
Answer:
```

### §6.3 longmemeval.rag_agent(LongMemEval,lines 18-21)

```
The history chats are between you and a user. Based on the relevant chat
history, answer the question as concisely as you can, using a single
phrase if possible.

 {question}

 Answer:
```

**注意**:`longmemeval.rag_agent` **沒有 recency rule**——這是 §5.6 兩階段 rigor fix 的核心原因(單階段 override 到 factconsolidation template 於 LME 就是 prompt-side unfair augmentation)。

---

## §7. Ablation Components(不進 main method,但於 §4.5 ablation 使用)

### §7.1 `ours_struct`(no P3):Phase 0 structural only

**Env**:`MEM0_ADD_MODE=phase0_structural`、`MEM0_QUERY_MODE=structural`。
**Branch**:agent.py:1049-1053 → `phase0_query.group_and_resolve` + `assemble_context`。
**Skips**:Phase 3 LLM identity fallback(triple-null / singleton (S,P) 的 candidates 直接 pass through,不 merge)。
**用意**:量化「純 (S,P) structural + argmax」的貢獻。

### §7.2 `ours_p3_only_no_struct`(LLM only):P3 without structural

**Env**:`MEM0_ADD_MODE=phase0_structural`(仍需 P2 抽取 metadata)+ `MEM0_QUERY_MODE=phase2` + `MEM0_STRUCTURAL_SKIP=1`(把所有 candidates 送 dynamic_pool,全交 P3 LLM 分群)。
**用意**:量化「純 LLM P3 分群」的貢獻(無 (S,P) 加速)。

### §7.3 `ours (+P5)` conflict-type classifier

**Env**:`MEM0_ADD_MODE=phase0_structural`、`MEM0_QUERY_MODE=phase2`、**不設** `MEM0_P5_SKIP=1`(P5 啟用)。
**File**:[`methods/phase2_query.py:397-419`](../../../../methods/phase2_query.py#L397-L419)(`CONFLICT_TYPE_PROMPT`)、[`lines 197-249`](../../../../methods/phase2_query.py#L197-L249)(predicate arity guard)。
**Branch(phase2_resolve line 488)**:對每個 ≥2 群,呼 `_classify_conflict_type()` 分三類:
- `NO_CONFLICT` → keep all(非同 fact,無需 resolve)
- `COMPLEMENTARY` → keep all(multi-valued,如 hobbies)
- `FRESHNESS` → `_drop_older()`(argmax(ordinal))

**Paper §4.5.3 結論**:P5 於 FC-SH -1 to -3pp(net-negative);於 LME-KU net-zero(2026-07-07 P5 reuse verification)→ **paper main method drops P5**,保留為 ablation。

---

## §8. Configuration / Hyperparameters(canonical)

| 項目 | 值 | 位置 |
|:--|:--|:--|
| **Backbone(canonical)** | `gpt-4o-mini`,temperature=0 | yaml `model:` + `temperature:` |
| **Backbone(extension)** | gpt-4.1-mini、gpt-5.4-mini、gemma3-{1b/4b/12b/27b}、gemma2-9b、llama3.1-8b、qwen2.5-7b、mistral-7b | 對應目錄下 yaml |
| **P2 extractor model(hold-fixed)** | `MEM0_TRIPLE_MODEL` 預設 `gpt-4o-mini`(跨 backbone 保持不變) | `run_fc_sh.sh:62` |
| **Chunk size** | 512 tokens | yaml `agent_chunk_size:` |
| **Embedding** | `text-embedding-3-small`,1536 dims | yaml `mem0_config.embedder` |
| **Retrieval top-K(ours canonical)** | 100 | yaml `retrieve_num:` |
| **Retrieval top-K(Zep)** | 10(Zep 官方推薦) | yaml `retrieve_num:` + `ZEP_TOP_K` env |
| **Retrieval top-K(Don't Ask fair)** | 100 vector(via our text-embedding-3-small) | `maxserial_theircode.py:188` |
| **Retrieval top-K(Don't Ask author's)** | 10 BM25 | authors' native |
| **Q-llm-recency top-K** | 100 canonical | `MEM0_Q_LLM_RECENCY_TOPK` env |
| **Vector store** | qdrant on_disk | yaml `mem0_config.vector_store` |
| **Store 隔離** | yaml path + `__<sub_dataset>` 後綴(agent.py:265-273 自動加) | `agent.py:265-273` |
| **P5(conflict-type classifier)** | **OFF**(canonical);on 於 ablation | `MEM0_P5_SKIP=1` env |
| **max_tokens patch** | gpt-5.4-mini + o1/o3/o4 系列改 `max_completion_tokens`(by-model-prefix routing) | `mem0/llms/openai.py:92-105`、`agent.py:596-611` |

---

## §9. Evaluation Metric

**FC-SH**:MABench 官方 `substring_exact_match`(sEM;canonical rescore via [`analysis/rescore_canonical.py`](../../../../analysis/rescore_canonical.py))。
`default_post_process`:normalize + `parse_output` + max(raw, parsed)+ max over alias list。
**LME-KU**:LongMemEval 官方 LLM judge(vendored:[`llm_based_eval/evaluate_qa_official.py`](../../../../llm_based_eval/evaluate_qa_official.py))。Judge model = `gpt-4o-mini`(驗證期)。

**分母**:
- **Overall sEM**:全 100 queries per length(FC-SH)、78 queries(LME-KU KU subset)。**headline metric**。
- **has_pair sEM**:FC-SH 100 queries 中真正含 old/new 版本的子集(6k=74、32k=65、64k=66、262k=77)。**mechanism metric**。

---

## §10. Explicit Exclusions — Dead Code(不進 Methodology 章)

以下**存在於 repo 但論文完全未使用**,寫 Methodology 時**不需要提及**:

### §10.1 未使用的 method 檔案
- [`methods/graph_rag.py`](../../../../methods/graph_rag.py)(GraphRAG)— 未跑
- [`methods/hipporag/`](../../../../methods/hipporag/)— 早期實驗,已停用
- [`methods/memorag/`](../../../../methods/memorag/)、[`methods/raptor.py`](../../../../methods/raptor.py)、[`methods/self_rag.py`](../../../../methods/self_rag.py) — 未跑
- Letta 相關:agent.py `_handle_letta_agent` + `_is_agent_type("letta")` — 未跑
- Cognee 相關:agent.py `_handle_cognee_agent` — 未跑
- mem0g(mem0 graph enabled)— agent.py:331-336, 510 code path — 未於 paper 使用

### §10.2 Superseded prompt(被 unified extractor 取代)
[`methods/mem0_fc_prompt_fix.py`](../../../../methods/mem0_fc_prompt_fix.py) 內以下 function **均已淘汰**:
- `make_l1_modified_prompt`(lines 39-55)
- `make_l2_knowledge_prompt`(lines 95-97)
- `make_broadened_native_prompt`(lines 124-175)

`use_unified_extractor: false` 路徑 = 走這些舊 prompt → **論文所有 canonical run 均 `use_unified_extractor: true`**,舊 prompt 不需寫入 Methodology。

### §10.3 未使用的 embedder / retriever
- NV-Embed-v2、OpenAIEmbedding legacy 路徑於 agent.py:1675-1678 — 不進 canonical(canonical 用 `text-embedding-3-small`)

### §10.4 (S,P) 倒排索引與 `hybrid_retrieve`(build-only,query-time dead)

**Implementation-only,論文不寫**:
- `self._sp_index` dict + `MEM0_SP_INDEX_PATH` JSON 持久化([`mem0/memory/main.py:76-79, 1058-1076`](../../../../mem0/memory/main.py#L1058-L1076))
- `methods/phase0_query.py:hybrid_retrieve()`([lines 113-126](../../../../methods/phase0_query.py#L113-L126))— 唯一會讀 `sp_index` 的 function

**驗證**(grep 全 repo):`hybrid_retrieve` **無 call site**;canonical query flow(`_handle_mem0_agent` → `self.memory.search` → `group_and_resolve` / `phase2_resolve`)全部從 **per-memory `metadata.triple`** 讀 (S,P) 分群,不查倒排索引。

**與 §2.6 metadata schema 的關係**:(S,P) canonical form 是必要的(存在 per-memory metadata),但**倒排索引資料結構未被使用**;methodology 章僅寫 metadata schema,不寫倒排索引。

**Code cleanup 建議**(不擋 paper):`_sp_index` build + persist 可移除;`hybrid_retrieve` 可整段刪除。

---

## §11. Canonical Execution Recipes(reproducibility)

### §11.1 FC-SH ours main
```bash
RUN_OAI_KEY_NAME=OPENAI_API_KEY_A \
  bash docs/0615_intro_framework_after_problem_statement/scripts/run_fc_sh.sh 6k ours_no_p5
```
- Env 設 `MEM0_ADD_MODE=phase0_structural`、`MEM0_QUERY_MODE=phase2`、`MEM0_P5_SKIP=1`、`MEM0_TRIPLE_MODEL=gpt-4o-mini`
- Yaml:`Structure_rag_gpt-4o-mini-mem0_512_openai_unified_no_p5.yaml`

### §11.2 LME-KU ours main
```bash
RUN_OAI_KEY_NAME=OPENAI_API_KEY_A SHARD=0 NSHARD=2 \
  bash docs/0615_intro_framework_after_problem_statement/scripts/run_lme_ku.sh ours_no_p5
```
- 2-shard 平行(SHARD=0/1),分別用 Key A/B
- Merge 兩 shard hyps 後跑官方 judge

### §11.3 Backbone extension(gpt-5.4-mini 例)
```bash
MODEL_TAG=gpt-5.4-mini RUN_OAI_KEY_NAME=OPENAI_API_KEY_A \
  bash docs/0615_.../scripts/run_fc_sh.sh 6k ours_no_p5
```
- 自動用 `configs/agent_conf/RAG_Agents/gpt-5.4-mini/*.yaml`
- Cache 於 `p1_caches__gpt-5.4-mini/`(TAG_SFX 自動加)

---

## 更新歷程

- **2026-07-16**:本檔建立;整合 [`abstract_0716.md`](abstract_0716.md) / [`introduction_0716.md`](introduction_0716.md) / [`related_work_0716.md`](related_work_0716.md) 的敘事定位 + 所有實際使用 prompts + hyperparameters + baseline execution paths + explicit exclusion。
