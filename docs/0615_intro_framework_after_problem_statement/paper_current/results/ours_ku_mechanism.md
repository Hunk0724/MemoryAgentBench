# ours KU mechanism — query-time resolution over faithful storage（canonical 機制檔）

> **用途**:與 [`mem0_ku_mechanism.md`](mem0_ku_mechanism.md)、[`zep_ku_resolution_bitemporal.md`](zep_ku_resolution_bitemporal.md) 對稱的 ours 版機制參考。說明 ours 的 **write（faithful/conservative）→ query-time 解析** pipeline、每個 LLM 子任務的 input/output、確定性 vs LLM 分界,並把 **ablation 變體對映到 code**(供 E-C 直接引)。
> **code source**:`methods/phase0_triple_extractor.py`(write 抽取)、`methods/phase0_query.py`(structural-only 查詢)、`methods/phase2_query.py`(main P3 路徑)、`mem0/configs/prompts.py`(fact 抽取沿用 mem0)。
> **日期**:2026-07-07。

---

## §1 設計立場（三個 commitment,對照 mem0/Zep）

過去派在 **write-time commit KU**(mem0 實刪、Zep 軟失效),一旦 LLM 誤判即不可逆/需 reader 挑。ours **defer KU 到 query-time**:

1. **Faithful / conservative write**:忠實抽取所有 fact、**保留全版本**、write 時**不做跨筆 LLM 判斷**、不刪不覆寫。
2. **Query-time KU resolution**:衝突只在 query 時解(query-aware);錯了下次可重解,庫裡版本還在。
3. **Decomposed, simple LLM tasks**:raw-question retrieval → (S,P) 結構分組 + LLM identity 分組 →（選配）3-way conflict-type → **確定性 temporal argmax**。**LLM 從不挑 recency**(確定性 argmax ordinal 挑)。

**pool_state 對 ours 有效**:query-time 解析輸出乾淨文字(both→new_only 收斂),reader 看到的就是 resolved pool → 文字 pool_state 是有效 mediator（與 mem0 同；只有 Zep 例外）。

---

## §2 Write 側（Phase 0,faithful/conservative）

`methods/phase0_triple_extractor.py`:
- **fact 抽取沿用 mem0** `FACT_RETRIEVAL_PROMPT`（atomic fact texts,不改）。
- **per-fact triple 抽取**（`TRIPLE_EXTRACTION_PROMPT`,batch=1、gpt-4o-mini、frozen cache）：每個 fact → `(subject, predicate, object)`。
  - **subject = 事實所述、且更新後仍固定的實體;object = 會變的值;predicate = 關係** → **同一事實的新舊版落在同一 `(S,P)`**（fact identity 的結構鍵）。
  - **無 predicate canonicalization**（Phase 0）;主觀/多事實/未解代名詞 → **null**（設計的 escape hatch → 僅走 semantic path,其 rate = F1 metric,非失敗）。
- **儲存**:**取代 mem0 的 write-time 跨筆 UPDATE LLM call**。每個 fact 都存、**全版本保留**;**ordinal = fact-level 全域 per-uid 計數器**（larger = newer,write 時賦值 → 同 `(S,P)` 即使同 chunk 也得**相異** ordinal → 後抽版本較新）。建 `(S,P)` inverted index。
- **★ write 端零跨筆 LLM 判斷、零 delete/overwrite** → 無 mem0 的 M1/M2、無 Zep 的軟失效。**非破壞、可回復**。

---

## §3 Query 側

### 3A 結構-only 路徑（`phase0_query.py` = ablation「ours (no P3)」/ struct）
唯一 LLM call 是 null-safe query analyzer(`QUERY_ANALYSIS_PROMPT`,重用與抽取**同一套** decomposition rules → query (S,P) 與 store (S,P) 對齊):
- **M4 `analyze_query`**:question → `{structural_keys:[(S,P)], semantic_query}`。open-ended → 空 keys（Path B 靜默退化為 semantic）。
- **M5 `hybrid_retrieve`**:semantic top-k **∪** 結構 (S,P) index lookup。
- **M6 `group_and_resolve`**:按 (S,P) 分組 → **每組 argmax(ordinal),KEEP-ALL-ON-TIE**（確定性）;無 triple 者 ungrouped、原文保留。

### 3B Phase 2 路徑（`phase2_query.py` = MAIN「ours」= struct + P3 + argmax）
1. **`conditional_structural_routing`**:`(S,P)` 有 ≥2 competitors → **structural_pool**;no-triple + singleton-(S,P) → **dynamic_pool**。（`MEM0_STRUCTURAL_SKIP=1` → 全丟 dynamic = 純 LLM,ablation 用）
2. **`llm_identity_clusters`**（`GROUPING_PROMPT`）:對 dynamic_pool **只判 fact IDENTITY**（哪些是同一事實的不同版本），**不判 recency/正確性**。
   - **HARD rules**:不同 entity = 不同 fact（即使同值）;不同 property = 不同 fact;**multi-valued = COEXIST 不分組**。「clustering is RARE」預設不分。
   - **subject-consistency guard**(`_subject_consistent`)：拒絕跨 ≥2 已知 subject 的 cluster（殺 dominant false-merge）。content-keyed frozen cache。
3. **groups = structural_pool + identity clusters**;逐組解析:
   - **MAIN(`MEM0_P5_SKIP=1`)**:每組 → **確定性 argmax(ordinal),drop older**（freshness by default）。
   - **+P5（appendix「ours (+P5)」）**:先過 `CONFLICT_TYPE_PROMPT`(3-way:`no_conflict`/`freshness`/`complementary`,adapted from Cattan+2025)→ **只有 freshness 才 drop older**,`no_conflict`/`complementary` 全留。為 LongMemEval 多值個人事實用。
   - 另有 per-predicate arity guard(`PREDICATE_ARITY_PROMPT`,single/multi,cached)於 structural_resolve 路徑保護多值不被誤 drop。

**輸出**:retained items（原順序）→ 乾淨 fact lines 餵 answer LLM。

---

## §4 確定性 vs LLM 分界（weak-model 主張的根據）

| 子任務 | 型態 | 輸入 → 輸出 | 為何 weak-model 友善 |
| :--- | :--- | :--- | :--- |
| triple 抽取 | LLM（per-fact）| 1 個 fact → (S,P,O) | 單句、self-contained,frozen cache 一次性 |
| query analyze | LLM | question → (S,P) keys | 與抽取同 rules,對齊即可 |
| (S,P) 分組 | **確定性** | index lookup | 純 hash,無 LLM |
| identity 分組(P3) | LLM | pool → 同事實 clusters | **只判 identity 不判 recency**,HARD rules 收斂 |
| conflict-type(P5,選配) | LLM | group → 3-way | 每組獨立、query-aware 的簡單三分 |
| temporal resolve | **確定性** | group → argmax(ordinal) | **LLM 從不挑 recency**;argmax 純程式 |

核心:**recency / 破壞性決策全確定性**;LLM 只做「identity / arity / conflict-type」這類**簡單、general、可 cache** 的子判斷。誤判**不破壞庫**(全版本仍在)、可下次重解。

---

## §5 Ablation ↔ code 對映（E-C 直接引）

| 變體（objective_data §1 命名）| 開關 | pipeline | 隔離什麼 |
| :--- | :--- | :--- | :--- |
| **ours (main)** | `MEM0_P5_SKIP=1` | struct + P3 identity + **argmax** | 主方法 |
| ours (no P3) / struct | phase0_query 路徑 | 純 (S,P)+argmax（無 LLM 分組）| **結構貢獻**（workhorse 候選）|
| ours (no struct) | `MEM0_STRUCTURAL_SKIP=1` | 純 LLM identity over top-k + argmax | **LLM identity 貢獻** |
| ours (+P5) [appendix] | P5 on | 上 + conflict-type 3-way | conflict-type 的淨效果 |

**E-C 論點**:FC-SH conflict-type **97% freshness** → **確定性 (S,P)+argmax 是 workhorse**;LLM 元件（P3/P5）自身 capability-gated（P3 淨 Δ 隨 backbone 變號:1B −7 → 12B 0 → 27B +4,見 `weak_model_6k_analysis.md` / README E-C）。→ 遞迴論證:連我方 LLM 元件都逃不過「弱 backbone LLM 判斷脆弱」,故把 KU 主幹交給確定性結構。

---

## §6 三派對照（KU locus × 破壞性 × 誰挑 recency）

| 維度 | mem0 | Zep | **ours** |
| :--- | :--- | :--- | :--- |
| KU 位置 | write-time commit | write-time labeling（延後判讀）| **query-time resolve** |
| 對舊版 | 實刪/覆寫（不可逆）| 保留+標 invalid（軟）| **全版本保留（非破壞）** |
| 誰挑 recency | LLM（無時間信號）| answer LLM 讀 date range | **確定性 argmax(ordinal)** |
| 跨筆判斷在 | write（coupled）| write（per-edge）| **query（decoupled: identity↔recency 分離）** |
| pool_state mediator | ✅ 文字 | ❌（bi-temporal）| ✅ 文字 |
| 主要失效 | M1/M2（coupled+world-prior）| 80% additive 不偵測 | **正交軸**（抽取/檢索/reader override,見 §7）|

---

## §7 ours 的誤差落在哪（E-D 責任邊界）

因 write 非破壞 + recency 確定性,ours **沒有** mem0 的 world-prior 刪除(M1)、coupled-output bug(M2)、也沒有 Zep 的 additive 不偵測。誤差改落在**與 KU 解析正交**的軸:
- **抽取**:triple null / (S,P) 抽錯 → 新舊版沒落同組 → 沒被 resolve。
- **檢索**:raw-q top-k 沒撈到某版本（recall ceiling）。
- **reader override**:pool 已乾淨(new_only)但 answer LLM 仍用 world-prior 答錯（強 backbone 亦見,Resolution > EM）。
- **D-flag**:benchmark 本身缺陷。

→ E-D 用這些正交軸**誠實劃界**:ours 只負責 KU 解析這一切片,不宣稱解決抽取/檢索/reader。

---

## §8 rigor caveat
- 行號依本 repo `methods/`;MAIN = `MEM0_P5_SKIP=1`(= 舊名 no_p5),別跑成 +P5(appendix)。
- LLM 子任務用 frozen content-keyed cache（timestamp-independent）→ 跨 run 一致、call 數一次性;weak-model 分析時 cache 需對應 backbone 重建。
- 數字一律回引 `objective_data_consolidated.md`（E2E / ablation）與 `weak_model_6k_analysis.md`（P3 backbone 變號）;本檔不重列 per-qid 數。
