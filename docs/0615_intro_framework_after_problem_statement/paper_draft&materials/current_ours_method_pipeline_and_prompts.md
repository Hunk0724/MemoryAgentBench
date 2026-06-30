# 方法 Pipeline 與所有 LLM-call Prompt(誠實清單)

> 初擬 2026-06-24,**全面更新 2026-06-26**(對應 ours 在 FC-SH 32k 正式跑期間整理)。
> 對應 `ku_taxonomy_and_scope_zh.md`(戰場定位)、`methodology_materials.md` §10
> (公平性/工程註記)、`project_ku_taxonomy_battlefield`(memory)。
>
> **狀態**:
> - **P1 統一抽取器** — 已接 code(`use_unified_extractor`),**FC-SH 32k smoke 驗證通過**
>   (191 facts vs 完美抽取 GT,micro-recall 97.4%,唯一差異是 P1 修正了 GT 的拼字 typo
>   `univeristy`→`university`,顆粒度一致)。
> - **查詢期解析** — 由舊的 per-predicate「multi-valued arity guard」改為
>   **3-way conflict-type classifier(query-aware)**(現役;arity guard 已停用、保留於 code 供對照)。
> - **檢索** — 新增 **raw-question 檢索修正**(剝掉 qa 模板 boilerplate);原 §4.2「FC retrieval recall」
>   查明為 wrapped-query artifact,已解。
> - **工程** — 寫入端 embedding 改 **batch**(結果不變、只快)。
> - **誠實化(2026-06-27)** — 本檔只描述**現行實際執行**的 ours 實作(`MEM0_ADD_MODE=phase0_structural`
>   + `MEM0_QUERY_MODE=phase2`)。**未使用 / 停用的設計**(含 (S,P) 倒排索引查詢期未讀、
>   `structural_resolve`、arity guard 等)統一移至 **§6** 揭露,不再混入主流程;呼叫點已 grep 驗證。

---

## 0. 模組邊界(誰是我們的貢獻)

| 層 | 誰的 | 內容 |
|---|---|---|
| **Substrate** | mem0(沿用) | vectorDB、embedding、add/search 基礎設施 |
| **Storage(改自 native)** | **ours** | 統一抽取器:user-asserted 忠實抽取(P1) |
| **Update(寫入期)** | **ours** | triple (s,p,o)(P2)+ subject fallback(P2b)+ **保留全版本(保守寫入,無跨筆 LLM 判斷)**;每筆 payload 帶 triple 供查詢期分群。⚠️ 另建之 **(S,P) 倒排索引查詢期未讀**(死碼,見 §6) |
| **Retrieval(查詢期)** | **ours** | **raw-question 向量檢索** → conditional routing → structural grouping +(只對 dynamic_pool)LLM identity grouping(P3)→ **per-group conflict-type 分類(P5,3-way)** → **temporal resolution(deterministic,僅 FRESHNESS 丟舊)** |
| **Inference** | benchmark 標準 | 用解析後記憶答題(P4),套各方法×任務的標準 qa 模板 |

**一句話定位**:KU 是 **query-time 問題**,不是 write-time commitment —— 寫入只做保守、無破壞性的「保留全版本」;誰是權威由查詢時**確定性 temporal argmax** 決定,LLM 全程不挑 recency。

**框架傳承(引用,見末尾「參考文獻」)**:沿用 memory agent 的統一 **Storage–Update–Retrieval–Generation** 流程 [MemoryOS];substrate + native `FACT_RETRIEVAL`(P1 錨點)+ `DEFAULT_UPDATE_MEMORY_PROMPT`((a)/(b) baseline 的破壞性更新)取自 **mem0** [mem0];我們延續**解耦更新(Decoupled Update)**脈絡——以 **Zep** [Zep] 為代表(LLM 只輸出標籤、確定性系統執行)——並推到極致:**寫入時完全消除所有跨筆 LLM 判斷**(Zep 仍須對「新事實 vs 既有」做類別判斷,我們連這也移到 query-time)。查詢期 conflict-type 分型改編自 **Cattan et al. 2025**(*DRAGged into Conflicts*)[Cattan'25]。coupled-update 對照組為 mem0 [mem0] 與 LightMem [LightMem]。

---

## 1. 端到端流程(標出每步是 LLM call 還是 deterministic)

**寫入期(每個 chunk):**
1. **[LLM · P1]** 統一抽取器:role-labeled chunk → 一組 atomic facts(只取 **user 主張**;assistant turn 僅作理解 context)。 *(Storage, ours)*
2. **[LLM · P2]** Triple 抽取:每條 fact → (s,p,o) 或 null;null → **[LLM · P2b]** subject-only fallback(讓查詢期 subject-match guard 普遍適用)。 *(Update, ours)*
3. **[deterministic]** **batch-embed** 整 chunk 的 facts、**保留所有版本寫入**(保守、無破壞性判斷,每筆 payload 帶 `triple` + `ordinal`= ingestion 序,供查詢期分群)。〔註:程式仍會另建 (S,P) 倒排索引,但**查詢期從未讀取** → 見 §6〕 *(Update, ours)*
   - ⚠️ Baseline (a)/(b) 在此改用 mem0 的 **[LLM] `DEFAULT_UPDATE_MEMORY_PROMPT`** 做 ADD/UPDATE/DELETE(**破壞性、不可逆**);**ours 不用**。

**查詢期(每題):**
4. **[deterministic]** **取 raw question**(剝掉 qa 模板 boilerplate)→ embed → 向量檢索 top-K(預設 100)候選。 *(Retrieval, ours;見 §2 檢索註記)*
5. **[deterministic]** conditional structural routing:`structural_pool`(有 triple 且該 `(S,P)` 在候選中 ≥2 競爭者)vs `dynamic_pool`(無 triple、或 `(S,P)` 單例)。 *(Retrieval, ours)*
6. **[LLM · P3,只對 `dynamic_pool`]** identity grouping:找出「同一事實的不同版本」cluster(只判 identity,RARE,不確定就不分群)。 *(Retrieval, ours)*
7. **[LLM · P5,每 group 一次、query-aware、cached]** **conflict-type 分類**:對每個 group(structural 群 + LLM cluster)判 `{NO_CONFLICT, FRESHNESS, COMPLEMENTARY}`。 *(Retrieval, ours)*
8. **[deterministic]** **temporal resolution**:**僅 FRESHNESS** group 以 **ordinal argmax 取最新、丟舊**(平手 keep-all);**NO_CONFLICT / COMPLEMENTARY 全留**。 *(Retrieval, ours)*
9. **[LLM · P4]** 答題:解析後記憶 + 問題 → 答案(各方法×任務標準 qa 模板)。 *(Inference)*

**關鍵誠實點:**
- 「**取哪個版本權威**」是 **deterministic temporal argmax**,**沒有 LLM 在判斷誰勝** —— 這是 query-time 解析可被信任的原因(對比 mem0 write-time 用 LLM 破壞性判斷)。
- LLM 的角色刻意維持「**簡單、local、可 cache**」:P1/P2 = 忠實轉錄不跨筆判斷;P3 = 只判 identity;P5 = 只判 group 的 conflict type(每 group 一次、cached)。**每個 LLM 任務都簡單 local**,扣合「weak-model regime」主張。
- 「丟舊」只發生在 **FRESHNESS**(真版本衝突);NO_CONFLICT(同值不同表面)與 COMPLEMENTARY(多值並存)一律保留 → **precision-safe**(誤判代價偏向「漏解析、下游可救」而非「誤丟合法事實」)。

---

## 2. LLM-call Prompt 全列

### P1 — 統一抽取器(Storage)【現役:`methods/mem0_fc_prompt_fix.py: make_unified_extractor_prompt()`,`use_unified_extractor`】

> 設計:錨定 mem0 native `FACT_RETRIEVAL_PROMPT`,四處 de-overfit —— ①解除「只存個人」限制(不列舉屬性)②faithfulness(照抄、不 fact-check)③保留 selectivity ④**source-based** specificity(存 user 主張、assistant 只當 context)。source-based(而非 knowledge-delta / LLM 自有知識)是為 **backbone-independence**。詳見 `ku_taxonomy_and_scope_zh.md` §6。
> **驗證**:FC-SH 32k 前 5 chunk vs 完美抽取 GT,逐 chunk 對齊 micro-recall 97.4%、數量比 1.00,唯一差異是 P1 修正 GT typo。

```text
You are a Memory Organizer. From a conversation between a user and an assistant,
extract the distinct facts that the USER asserts as true -- about themselves or
about the world -- and record them as separate, atomic facts for later retrieval.
The memory you build holds what the user has told the system; it is authoritative
over the assistant's own knowledge.

Use the whole conversation -- both speakers -- to UNDERSTAND what the user means:
resolve references ("it", "there", "that") and read the assistant's replies as
context that clarifies the user's statements. But RECORD facts ONLY from what the
USER asserts. The assistant's turns are context for understanding, NEVER a source
of facts to store.

What to record (from the user's statements):
- Any fact the user states as true: personal information, preferences, plans,
  relationships, situations, AND general / world facts the user asserts (including
  values that differ from common knowledge).
- Record one fact per statement; split a sentence asserting several facts into
  separate atomic facts.

Faithfulness:
- Transcribe each asserted fact exactly as the user states it, even if it
  contradicts common knowledge or an earlier statement. Do NOT fact-check,
  correct, or judge truth. Conflicting or updated values are expected -- record
  them as given.

What NOT to record (selectivity):
- Greetings, questions, requests, and small talk that assert no fact.
- Anything the ASSISTANT contributes on its own -- advice, recommendations,
  instructions, explanations, or general knowledge. (The assistant is context
  only, never a fact source. If the user later restates something as their own,
  record the user's statement.)
- If the user asserts no fact, return an empty list.

Return JSON with a single key "facts" whose value is a list of strings. Detect the
input language and record the facts in that language.

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

Conversation:
{conversation}
```

**FC 適配說明**:FC 的 memorize 模板把事實清單放進 `<User>` turn(「facts I have learned: …」),assistant 只是 stub →本抽取器把 user turn 的事實全收、stub 無 fact → FC 零損失(已實證)。

### P2 — Triple 抽取(Update)【現役:`methods/phase0_triple_extractor.py`】

```text
You are a triple extractor. For EACH input fact (a single declarative statement
extracted from conversation memory), extract its (subject, predicate, object) triple.

Rules:
- Choose subject = the entity the fact is about, and that stays fixed if the fact
  is later updated; object = the specific value that could change (the answer);
  predicate = the relation linking them. This keeps different versions of the same
  fact under the same (subject, predicate).
- Decompose nominal relations into standard (subject, relation, object) form. When
  the grammatical subject is a noun phrase "the <relation> of <entity>", do NOT use
  that whole phrase as subject and do NOT use "is" as predicate. Instead:
  subject=<entity>, predicate="has <relation>", object=<value>. (standard KG s,r,o)
- predicate is a SHORT natural-language verb phrase; do NOT map to fixed vocab /
  snake_case / canonical form.
- subject / object are named entities or attribute values, verbatim from the fact.
- Pronouns: user/assistant -> "user"/"assistant"; other resolvable -> resolved
  entity; unresolvable -> null.
- Extract regardless of topic (personal, preferences, opinions, world knowledge).
- Never skip/null a fact for seeming false. Facts may be deliberately
  counterfactual; extract anyway, do NOT verify against world knowledge.
- Subjective state / complex narrative / multiple independent facts -> null.
- null is valid and ENCOURAGED.
- Confidence reflects how cleanly the fact fits the triple form (>0.8 only if
  subject/predicate/object unambiguous).

Examples:
Fact: "The user lives in Taipei." -> {"subject":"user","predicate":"lives in","object":"Taipei","confidence":0.95}
Fact: "Marie Curie was born in Warsaw." -> {"subject":"Marie Curie","predicate":"was born in","object":"Warsaw","confidence":0.95}
Fact: "The user feels stressed about work lately." -> null  (subjective state)
Fact: "She moved to Tokyo and got a new job." -> null  (multiple facts + unresolved pronoun)

Input is a numbered list of facts. Return JSON:
{"results":[{"id":0,"triple":{"subject":"...","predicate":"...","object":"...","confidence":0.0}},{"id":1,"triple":null}]}

Facts:
{numbered_facts}
```

> **無 confidence gate**(2026-06-20 起):gpt-4o-mini confidence 近常數 ~0.95,gate 形同 no-op,已移除;confidence 仍記於 payload 供分析。所有 non-null triple 進 (S,P) index。

### P2b — Subject-only fallback(Update,triple=null 時)【現役:`phase0_triple_extractor.py`】

```text
Identify the single entity each fact is primarily ABOUT -- the subject it would
have if rewritten as "<subject> -- <attribute> -- <value>".
- About the user themselves: "user".
- About someone/something tied to the user: that specific entity (e.g. "user's
  spouse", a named friend, pet, org). Do NOT collapse to "user".
- World knowledge: the named entity ("The capital of France is Paris" -> "France").
Return the subject as a short string; if none, null.

Input is a numbered list of facts. Return JSON:
{"results":[{"id":0,"subject":"..."},{"id":1,"subject":null}]}

Facts:
{numbered_facts}
```

### P3 — LLM identity grouping(Retrieval,只對 dynamic_pool)【現役:`methods/phase2_query.py: GROUPING_PROMPT` → `llm_identity_clusters`】

> 只判**身分**(哪些檢索回的記憶是「同一事實的不同版本」),不判 recency、不答題。輸出只給「有信心的 cluster(≥2 成員)」,其餘自動保留(誤分群 false-merge 會藏掉合法值 → 寧可不分群)。

```text
You are analyzing a list of memory entries retrieved for a user query. Your ONLY
task is to find CLUSTERS of entries that are the SAME fact recorded in different
versions. You do NOT answer the query, summarize, or decide which entry is newer.

# THE TEST (apply strictly)
Cluster two entries ONLY IF they are competing answers to the EXACT SAME question
about the EXACT SAME specific entity — same specific subject AND same property —
where only the value (answer) differs across versions.

# HARD RULES — when NOT to cluster (these dominate)
1. DIFFERENT SPECIFIC ENTITY = DIFFERENT FACT. (two different people/places/orgs
   are different facts, even with same wording/attribute/value.)
2. DIFFERENT PROPERTY = DIFFERENT FACT. (its capital vs its head of state; the
   user's city vs the user's job.)
3. MULTI-VALUED PROPERTY = COEXIST. (hobbies, friends, languages, places, skills,
   things liked -> values coexist, not versions. Do NOT cluster.)

# Clustering is RARE
Most or ALL entries form NO clusters. Cluster only when CONFIDENT it is the same
single-valued fact about the same specific entity. When unsure, do not cluster
(a false merge hides a real value; a false split is harmless).

# Identity only — never recency (a separate deterministic step handles recency).

# Output — clusters only (2+ members); unclustered entries omitted; none -> {"groups":[]}.
Return JSON exactly:
{"groups":[{"fact":"<entity+property>","memory_ids":["<id>","<id>"],"reasoning":"<one sentence>"}]}

# Examples (personal + world-knowledge; note the negatives)
Query: Where does the user live now?
[a] used to live in Taipei. [b] now lives in Tainan. [c] enjoys hiking.
-> {"groups":[{"fact":"the user's current city","memory_ids":["a","b"],...}]}
Query: Who is the CEO of Acme Corp?
[d] CEO is Jane Doe. [e] CEO is now John Smith. [f] HQ in Berlin.
-> cluster d,e (f is a different property)
Query: Who is allergic to peanuts? [g] the user [h] the user's son -> {"groups":[]} (different subjects)
Query: Where were these people born? [i] Marie Curie/Warsaw [j] Chopin/Warsaw -> {"groups":[]} (different people)
Query: Tell me about the user. [k] city Tokyo [l] employer Acme -> {"groups":[]} (different properties)
Query: What languages? [m] French [n] Japanese -> {"groups":[]} (multi-valued)

# Now analyze:
Query: {query}
Memory entries:
{entries}
```

### P5 — Conflict-type classifier(Retrieval,每 group 一次、query-aware、cached)【現役:`methods/phase2_query.py: CONFLICT_TYPE_PROMPT` → `_classify_conflict_type`】

> **取代**舊的 per-predicate「multi-valued arity guard」。改用 **3-way、query-aware、per-group** 分類(改編自 **Cattan et al. 2025** [Cattan'25], *DRAGged into Conflicts* 的衝突分型,限縮到「user 主張累積」情境)。理由見 §4.1:arity 不是述詞的絕對屬性、是 **context-dependent**,所以必須**看這一組的 values±query**、而非只看述詞。
> **cache**:key = `sha256(query + 排序後成員文字)`,env `MEM0_CONFLICT_CACHE`;失敗安全預設 `complementary`(keep-all)。

```text
You analyze a group of candidate memory entries that share the same subject and
relation but have different recorded values. Determine which conflict type
applies, so the downstream resolution step knows whether to select the most recent
value or keep all of them.

Apply ONE of the following categories (adapted from Cattan et al., 2025, CONFLICTS
taxonomy, restricted to memory accumulation scenarios where the source is user
assertions):

(1) NO_CONFLICT — The candidates record the SAME value in different surface forms
("Tokyo" vs "Tokyo"; "350,000" vs "$350k"; "PhD" vs "doctorate"). Minor variation
in granularity/phrasing without semantic difference.

(2) FRESHNESS — The candidates are mutually exclusive at any single point in time.
A single subject cannot simultaneously hold all listed values; the newer value
supersedes the older. Examples: current city, current employer, current
count/total, personal best, mortgage amount, marital status.

(3) COMPLEMENTARY — The candidates are mutually compatible. The same subject can
reasonably hold all listed values simultaneously, without contradiction. The
values are accumulating instances, not competing answers. Examples: brands tried,
languages spoken, places visited, hobbies, restaurants visited.

DECISION TEST (apply strictly, in order):
  Step 1: Are these surface variants of one value? YES -> NO_CONFLICT.
  Step 2: Could the subject reasonably hold ALL listed values AT THE SAME TIME,
          right now? YES -> COMPLEMENTARY.  NO -> FRESHNESS.

When uncertain between FRESHNESS and COMPLEMENTARY, default to COMPLEMENTARY
(false-merge into Freshness destroys information; false-split into Complementary is
recoverable downstream).

Query: {query}
Subject: {subject}
Relation: {predicate}
Candidate values (with timestamps):
{candidates_with_timestamps}

Return JSON exactly: {"type": "no_conflict" | "freshness" | "complementary", "reasoning": "<one sentence>"}
```

**resolution 對應(`phase2_resolve`)**:`NO_CONFLICT`→keep all;`FRESHNESS`→`_drop_older`(ordinal argmax,平手 keep-all);`COMPLEMENTARY`→keep all。**只有 FRESHNESS 會丟舊。**

> ⏸ **已停用(保留 code 供對照):P5-old — per-predicate multi-valued arity guard**(`PREDICATE_ARITY_PROMPT` / `_predicate_is_multivalued`)。原本對每個 `predicate_norm` 判 single/multi。問題:同一述詞在 FC(反事實「取最新」全功能)該 single、在 LongMemEval(自然多值)該 multi → 述詞層級無法無條件全開。已由上面 query-aware 的 conflict-type classifier 取代。

### 檢索註記 — raw-question 檢索(deterministic,非 LLM call)【現役:`agent.py: AgentWrapper._retrieval_query()`】

> MemoryAgentBench 預設把「qa 模板包裝後的整段 query」(FC 約 800 字的 "Pretend you are a knowledge management system… Now Answer the Question: …")拿去做 embedding 檢索 → 指令 boilerplate 主導向量、稀釋真問題,使 GT 被擠出 top-K。**修正**:依各 dataset 的 query 模板剝掉 prefix/suffix,**只用真正的 question** 去 embed;inference 仍餵完整 wrapped query(「找最新」指令保留)。
> **效果**:FC-SH 64k has_pair GT_new recall@100 = wrapped **79%** → raw **100%**(rank median 13→2)。
> **公平性**:ungated(vanilla mem0 baseline 同樣套用)、且 zep 本就以 `get_retrieval_query` 做同類剝離 → 屬 pipeline 對齊、非加 buff。論文須揭露。詳見 `methodology_materials.md` §10.1。

### P4 — 答題 / Inference【現役:`agent.py` + qa 模板 `utils/templates.py`】

System(注入解析後記憶):
```text
You are a helpful AI. Answer the question based on query and memories.
{memories_str}
```
User(FC × rag/mem0-based agent 的 qa 模板,實例):
```text
Pretend you are a knowledge management system. ... find the newest fact with the
larger serial number. ... Now Answer the Question: Based on the provided Knowledge
Pool, {question}
Answer:
```

> ⚠️ **公平性注意(重要)**:MemoryAgentBench 的 inference(qa)prompt **不是單一通用**,而是依 **(方法 agent 類型 × 任務類型)** 各自設計 —— `get_template(sub_dataset, 'query', agent_name)`,每種方法在每種題目都有其**公平對應**的答題模板。**我們使用我們方法類型在該任務的標準模板,絕不另行客製**(客製 inference = 不公平,會混淆「贏在記憶還是贏在答題 prompt」)。上面只是 **FC × 我們 mem0-based agent** 的實例;**LongMemEval / BEAM 會各自套用其任務的標準 qa 模板**。寫論文/slide 時這格要逐任務誠實列出對應模板。

### (對照) Baseline 用、ours 不用 — mem0 破壞性更新【`mem0/configs/prompts.py`】

> 列出供誠實對照:(a)/(b) baseline 在寫入期用 `DEFAULT_UPDATE_MEMORY_PROMPT` 做 ADD/UPDATE/DELETE/NONE,**會在 write-time 不可逆地覆蓋/刪除版本**。**ours 完全不用此 prompt**,改為保守保留全版本 + query-time deterministic 解析。

---

## 3. LLM call 統計(每題/每 chunk)

| Prompt | 時機 | 類型 | ours? | 備註 |
|---|---|---|---|---|
| P1 抽取 | write(每 chunk) | LLM | ✓ | self-populating cache(`MEM0_EXTRACTION_CACHE`) |
| P2 triple / P2b subject | write(每 fact) | LLM | ✓ | self-populating cache(triple/subject) |
| 全版本寫入(payload 帶 triple + ordinal) | write | **deterministic** | ✓ | 無 LLM 判斷 |
| ~~(S,P) 倒排索引建立~~ | ~~write~~ | ~~deterministic~~ | ⚠️ | 仍會建立但**查詢期未讀**(死碼,見 §6) |
| **batch embedding** | write | **deterministic** | ✓ | 一次 API embed ≤2048 筆;結果不變、只快(§ `methodology_materials.md` §10.2) |
| **raw-question 檢索** | query | **deterministic** | ✓ | 剝 qa 模板、embed 真問題;ungated |
| conditional routing | query | **deterministic** | ✓ | structural_pool vs dynamic_pool |
| P3 grouping | query | LLM | ✓ | **只對 dynamic_pool**;structural_pool 不需 |
| **P5 conflict-type 分類** | query | LLM(每 group 一次、cached) | ✓ | 3-way、query-aware;簡單 local 任務 |
| **temporal resolution** | query | **deterministic** | ✓ | **僅 FRESHNESS 取最新無 LLM**,方法核心誠實點 |
| P4 答題 | query | LLM | — | benchmark 標準 |
| ~~mem0 destructive update~~ | ~~write~~ | ~~LLM~~ | ✗ | baseline 用,ours 不用 |
| ~~P5-old per-predicate arity guard~~ | ~~query~~ | ~~LLM~~ | ⏸ | 已停用,被 conflict-type classifier 取代 |

---

## 4. 已知挑戰與現況(method 設計層)

### 4.1 一個 fact 可能是版本衝突(取代)也可能是並存(累積)— **已用 query-aware classifier 處理**
query-time 解析的核心難題:**檢索回、同一 `(subject, predicate)` 的多筆,不一定是「同一事實的新舊版本」。**
- **FRESHNESS(版本衝突)**:屬性只有一個當前值,新值**取代**舊值 → argmax 取最新。例:現居城市、PB、房貸、count。
- **COMPLEMENTARY(並存)**:屬性可同時多值,新值**追加**非取代 → 全留。例:用過的品牌、訓練項目、會的語言、去過的地方。
- **NO_CONFLICT(同值不同表面)**:granularity/措辭不同的同一值 → 全留(不需丟)。

**誤判代價不對稱**:把並存當版本 → **誤丟合法事實(precision bug)**;把版本當並存 → 漏解析(下游常可救回)。→ 分類器**不確定時偏 COMPLEMENTARY**、且 `phase2_resolve` **只在 FRESHNESS 丟舊**。

**為何不能用 per-predicate arity guard(已停用)**:arity **是 context-dependent,不是述詞的絕對屬性** —— 同一述詞(`is associated with`/`is famous for`)在 FC(反事實、指令「find the newest」→ 視作全功能 single)與 LongMemEval(自然多值)arity 相反。故改用**看 group 的 values±query** 的 conflict-type classifier(等同先前候選解 **(B)**)。FC-SH 6k smoke 上此 classifier 6/6 正確;LongMemEval 仍在多題觀察中(分類器偶把 query-irrelevant 群判錯,但對 query-relevant 群正確,先續觀察)。

### 4.3 寫入端 latency:P2 triple 抽取主導(backlog,待 64k 檢索分析後決定)
實測(cost log,ours 64k memorize 期):**P2 triple 抽取佔 66–68% LLM latency**(per-chunk 批次、1 call/chunk,但一次生成 ~37–70 triple → ~16s/call);P1 抽取 ~30%;**embedding 因 batch 已只剩 3%**。
- **tension**:為 weak-model robustness 把任務拆成多趟簡單 LLM call(P1→P2→query 期 P3/P5),代價是寫入端多一趟 triple pass。
- **lazy-triple 候選方向**:triple **只在 query-time 對檢索回的 top-100 用到**(routing/grouping),寫入端 eager 抽 triple 不划算 → **改成只在 query-time 對檢索回的 ~100 fact 抽 triple**(1 batch/query)→ 寫入端 68% latency 消失,且更扣合 query-aware 哲學。
- **唯一保留 write-time 結構的理由 = 它能幫 retrieval**(結構檢索 / Path B)。但 raw-q 在 32k recall 98% → 目前 retrieval 非瓶頸。**決策依賴**:64k/262k 檢索分析——若 retrieval 仍 OK → lazy-triple 可行(更優雅);若 at-scale 有 recall 難度 → write-time (S,P) 結構才有保留價值。
- 旁註:`sp_index` JSON 寫了但 query-time **未使用**(routing 讀 payload 內的 triple,非該 JSON)→ 可省該 deterministic 步(非 latency 主因)。

### 4.2 ~~FC-dense 的 retrieval recall~~ — **已查明:wrapped-query artifact,已解**
原假設「FC 密集事實 at-scale 把 GT 擠出 top-100」。**診斷推翻**:用 raw question 檢索,FC-SH 64k has_pair GT_new recall@100 = **100%**(rank median 2);掉到 79% 純粹是 benchmark 拿 **qa 模板包裝後整段 query** 去 embed 的 artifact。修法 = 上面的 raw-question 檢索(trivial)。原「Path B 結構化 (S,P)/subject 檢索」**不需要了**。詳見 `experiment_results.md` §5.6。

---

## 5. 待辦(本檔)

- [x] P1 統一抽取器:接 code + **FC-SH 32k smoke 驗證通過**(97.4% vs 完美抽取 GT)。
- [x] 查詢期解析:per-predicate arity guard → **3-way conflict-type classifier(query-aware)**;`NO_CONFLICT`/`COMPLEMENTARY` keep、僅 `FRESHNESS` 丟舊。
- [x] 檢索:raw-question 修正(ungated);§4.2 retrieval recall 查明為 wrapped-query artifact。
- [x] 工程:寫入端 batch embedding(結果不變、只快)。
- [x] FC-SH 32k 正式跑(ours,fresh P1):overall 89% / has_pair 86%(raw-q 把 has_pair 從舊 78% 拉到 86%)。64k/262k 跑中。
- [x] vanilla mem0 對照(native + raw-q):FC-SH 32k overall 22% / has_pair 3%、64k 26% / 3% → 抽取階段即失敗,突顯 storage 貢獻。
- [x] LCA(long-context)對照:32k 74% / has_pair 71%、64k 65% / 55% → **ours 86% 反勝 LCA 71%**(LCA 有 serial 仍輸)。
- [ ] LongMemEval:conflict-type classifier 多題穩定性 + 換官方 `evaluate_qa.py`(gpt-4o judge)。
- [ ] 補 pipeline 圖(slide);與 `methodology_materials.md` 三張框架圖對齊。

---

## 6. 目前未使用 / 停用的設計(誠實揭露)

> 以下設計**存在於 code 或舊版描述,但現行 ours(`MEM0_ADD_MODE=phase0_structural` +
> `MEM0_QUERY_MODE=phase2`)實際未執行**。集中列出避免方法描述名實不符;清 code 時可一併處理。
> 呼叫點已 grep 驗證(2026-06-27)。

| 設計 / 符號 | 位置 | 現狀 | 備註 |
|---|---|---|---|
| **(S,P) 倒排索引** `self._sp_index` | `mem0/memory/main.py`(建/存:75-80, 1050, 1061) | **寫入期建立並持久化,查詢期從不讀取** | 查詢期 routing 改從「檢索回候選的 `payload.triple`」現場重建 (S,P) 分群(`phase2_query.py:463`),不查此索引 → 可省此寫入步 |
| **`structural_resolve`** | `methods/phase2_query.py` | **定義了,零呼叫點** | 原設計「(S,P) argmax + tie 升級 LLM」;現行 `phase2_resolve` 改走 routing + P5 conflict-type,完全繞過 |
| **P5-old:arity guard** `_predicate_is_multivalued` / `PREDICATE_ARITY_PROMPT` | `methods/phase2_query.py:188-240` | **停用**(只被死碼 `structural_resolve` 呼叫) | 被 P5 conflict-type classifier 取代(理由見 §4.1) |
| **`llm_dynamic_grouping`** | `methods/phase2_query.py` | **停用** | 被 `llm_identity_clusters` 取代(`phase2_query.py:464`) |
| **`hybrid_retrieve` / `analyze_query`** | `methods/phase0_query.py` | **未使用** | Phase-0「structural」模式 helper(semantic ∪ 結構檢索 / query 分析);現行 ours 是 phase2,不走 |
| **`group_and_resolve`(Phase 0 純結構模式)** | `methods/phase0_query.py`(`MEM0_QUERY_MODE=structural`) | **另一條 mode,非現行 ours** | 現行 ours = `MEM0_QUERY_MODE=phase2` |
| **mem0 `DEFAULT_UPDATE_MEMORY_PROMPT`(破壞性更新)** | `mem0/configs/prompts.py` | **baseline 用、ours 不用** | 刻意保留作對照((a)/(b) baseline),非死碼 |

> **對 method 寫作的影響**:(S,P) 倒排索引目前是「建了沒用」。兩條路擇一——(i) **停建並從方法描述移除**(讓 doc 誠實);或 (ii) **真的接成查詢入口**(scale-invariant 結構檢索,見 retrieval 討論線)。在做決定前,方法 §3 不應把 (S,P) 倒排索引列為運作中的貢獻。

---

## 參考文獻(方法設計相關)

> 與 `intro_zh_revised_v2.md` 的 reference list 對齊(編號取自該檔);Cattan'25 為本方法額外引用(不在 intro 清單)。

- **[mem0]** P. Chhikara, D. Khant, S. Aryan, T. Singh, D. Yadav, "Mem0: Building production-ready AI agents with scalable long-term memory," *ECAI*, 2025. — substrate、native `FACT_RETRIEVAL`(P1 錨點)、`DEFAULT_UPDATE_MEMORY_PROMPT`(coupled 破壞性更新,(a)/(b) baseline)。
- **[Zep]** P. Rasmussen, P. Paliychuk, T. Beauvais, J. Ryan, D. Chalef, "Zep: A temporal knowledge graph architecture for agent memory," arXiv:2501.13956, 2025. — 解耦更新(Decoupled Update)代表作;我們延續其精神並把跨筆 LLM 判斷完全移除。亦:`get_retrieval_query` 先例(檢索剝 boilerplate,佐證 raw-q 對齊公平)。
- **[LightMem]** J. Fang *et al.*, "LightMem: Lightweight and efficient memory-augmented generation," *ICLR*, 2026. — coupled update 代表作;§5.6 自承「誤判→不可逆刪除」= 我們要解的痛點。
- **[MemoryOS]** J. Kang, M. Ji, Z. Zhao, T. Bai, "Memory OS of AI agent," *EMNLP*, 2025. — 統一 Storage–Update–Retrieval–Generation 流程框架。
- **[Cattan'25]** Cattan *et al.*, "DRAGged into Conflicts: ... conflicting sources in retrieval-augmented LLMs," 2025. — 3-way 衝突分型(我們的 P5 conflict-type classifier:NO_CONFLICT / FRESHNESS / COMPLEMENTARY 改編自此)。
