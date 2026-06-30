# Methodology Materials: vanilla Mem0 vs Ours (Phase 0 / Phase 2)

> 用途:paper **Methodology** 章節 + 口試投影片素材。從 input→output 攤開三條 pipeline,
> 對照框架示意圖的四個模組,逐模組說明「我們改了什麼」,並用一個 example 走一遍。
>
> **三張示意圖(投影片用,本檔對應)**:
> - [introduction_framework_abstract.png](introduction_framework_abstract.png) — intro **抽象框架**(Triple extract / Conflict Resolution = Identity grouping + Temporal resolution)。
> - [Methodoloty_mem0_framework.png](Methodoloty_mem0_framework.png) — **vanilla Mem0**:Update = Categorical update ADD/UPD/DEL/NOOP;Vector store 版本被覆寫;query 直接 Retrieve→Inference,無衝突解析。
> - [Methodology_ours_Overview.png](Methodology_ours_Overview.png) — **Ours 具體版**:Update = Triple extract(per-item→(S,P,O))+ Structural commit;Unified store 全版本保留;query = Identity grouping(Structural (S,P) + LLM-based)+ Temporal resolution(timestamp argmax)。
>
> 投影片敘事:intro 用抽象圖提出「打過去流派」的理念 → methodology 用 mem0 圖 vs ours 圖,**同一個四模組版面**上對照出我們改了哪些 component(Update 換掉、query-time 解析新增)。
> 對應實作:`mem0/memory/main.py`、`methods/phase0_triple_extractor.py`、`methods/phase0_query.py`、
> `methods/phase2_query.py`、`agent.py`。建立 2026-06-22。

---

## 1. 統一框架與四個模組(對照示意圖)

所有 memory-augmented agent 共用 **Storage — Update — Retrieval — Generation** 流程。示意圖把它拆成:

```
Stage 1 (Write-time)                         Stage 2 (Query-time)
 New info                                      Query
   │ [Storage module]                            │ [Retrieval module]
   ▼  Extract entries (atomic memory)            ▼  Retrieve top-K from unified store
   │ [Update module]                             │ [Identity grouping]
   ▼  ...                              ┌──▶       ▼  Structural (S,P) + LLM (fact identity)
   │                          Memory   │          │ [Temporal resolution]
   ▼  ...  ───────────────▶   bank ────┘          ▼  timestamp argmax
                          (Unified store)         ▼
                                                Inference LLM
```

**符號**:每筆事實 fact `f`;其三元組 `t(f)=(s,p,o)`,正規化後 subject id `s`、predicate `p`;
ingestion ordinal `τ(f)`(per-chunk 單調遞增,大者為新)。query `q`。

---

## 2. 三條 pipeline 一覽(差異一眼看)

| 模組 | **vanilla Mem0**(coupled, destructive) | **Ours-Phase0**(structural) | **Ours-Phase2**(structural + LLM) |
|---|---|---|---|
| Storage(抽取) | L1/L2 抽 atomic facts | **相同**(沿用) | **相同** |
| **Update(寫入)** | 候選 top-5 + **1 次 LLM 裁決 ADD/UPDATE/DELETE/NOOP** + **破壞性 commit** | **per-item triple 抽取 + 結構性 conservative ADD;無 cross-item 判斷;建 (S,P) 索引** | **同 Phase0** + triple-null 補 subject |
| Memory bank | 版本被覆寫/刪除 | **全部版本保留** | **全部版本保留** |
| Retrieval | top-K cosine | **相同** top-K cosine | **相同** |
| **Identity grouping** | **無** | (S,P) 結構分群 | **(S,P) 結構 + LLM fact-identity 分群** |
| **Temporal resolution** | **無** | 每組 timestamp(ordinal)argmax | 每組 argmax;tie escalate 給 LLM |
| Generation | top-K 原樣進 prompt | resolved context 進**相同** prompt | 同左 |

> **核心**:我們**只改 Update 模組與新增 query-time 的 Identity grouping + Temporal resolution**;
> Storage / Retrieval / Generation 與 vanilla **逐字相同**。差異 = 「破壞性 write-time 裁決」→「保守結構寫入 + query-time 按需解析」。
>
> **檢索一致性註記**:示意圖上 vanilla 標 "hybrid retrieval"、ours 標 "top-K from unified",但**本 FC 實作兩者都是同一個 cosine top-100(vector-only)**——retrieval 刻意不動,以隔離 memory-side 的貢獻。投影片建議兩邊都標 "top-100 (cosine)" 或在 caption 註明「兩者檢索相同」。

---

## 3. vanilla Mem0 pipeline(baseline,被我們替換的對象)

**Write-time**(每 chunk 一次 `memory.add`):
```
chunk ─▶ (Storage) L1/L2 atomic extraction ─▶ new_facts[]
       ─▶ (Update) 對每個 new_fact f:
              1. embed(f);  vector_store.search(f) ─▶ 候選 top-5 既有記憶
              2. 收集所有 new_facts × 候選池 ─▶ 1 次 LLM 呼叫
                 (DEFAULT_UPDATE_MEMORY_PROMPT) ─▶ [{event∈{ADD,UPDATE,DELETE,NONE}, id, text}]
              3. 執行(破壞性):ADD=create / UPDATE=覆寫 / DELETE=硬刪 / NONE=略過
```
LLM 在此**同時當判斷者與執行者**;任一誤判被**不可逆寫入**。

**Query-time**(`_handle_mem0_agent`):
```
q ─▶ search top-100 ─▶ memories_str = "- "+text 串接 ─▶ system+user prompt ─▶ inference LLM ─▶ answer
```
無任何 query-time 衝突解析。

---

## 4. Ours — Write-time(Update 模組重新設計)

**設計原則**:LLM 只做 **per-item self-contained** 的 triple 抽取(無 cross-item 判斷);commit 純結構、保守、保全。

```
chunk ─▶ (Storage) L1/L2 atomic extraction ─▶ new_facts[]        ← 與 vanilla 相同
       ─▶ (Update, NEW) 對每個 new_fact f:
              1. triple t(f)=(s,p,o) ← per-item LLM(schema-free);抽不出則 t=None
                 (Phase 2) t=None 時補抽 subject_fallback(輕量,泛化用)
              2. _create_memory(f):  embed + 寫入 unified store
                 payload = {data=f, ordinal τ(f), triple=(s,p,o) | None, subject_fallback?}
              3. 若 t≠None:寫入 (S,P) inverted index:  key (s,p) ─▶ [memory_id…] (依 τ DESC)
       ✗ 無候選檢索 · ✗ 無 update-decision LLM · ✗ 無 overwrite/delete  ─▶ 純 ADD,全版本保留
```

**關鍵差異 vs vanilla Update**:
- vanilla:cross-item LLM 裁決 + 破壞性執行 → 不可逆。
- ours:per-item triple(自含)+ 確定性 ADD + 並行 (S,P) 索引 → **零 cross-item 判斷、零資訊損失**。

---

## 5. Ours — Query-time(Identity grouping + Temporal resolution)

### 5.1 Phase 0(純結構)
```
q ─▶ (Retrieval) search top-100 C            ← 與 vanilla 相同
   ─▶ (Identity grouping, 純結構) 把 C 按各自 (s,p) 分組;t=None 的 ungrouped 保留
   ─▶ (Temporal resolution) 每組 argmax τ ─▶ 留最新版(tie 全留);ungrouped 全留
   ─▶ assemble context ─▶ inference LLM(相同 prompt)─▶ answer
```

### 5.2 Phase 2(結構 + LLM 分群)— 完整版
```
q ─▶ (Retrieval) search top-100 C
   ─▶ (Conditional structural routing) 把 C 分兩條路:
        · structural_pool: (s,p) 在 C 內有 ≥2 對手者整組
        · dynamic_pool   : 無 triple、或 (s,p) 在 C 內無對手者
   ─▶ (Structural grouping + argmax) 對 structural_pool 每組 argmax τ;
        最大值唯一 ─▶ 丟舊版;timestamp tie ─▶ 整組 escalate 給 LLM
   ─▶ (LLM dynamic grouping) 對 dynamic_pool + escalated:
        LLM 依 "fact identity" 分群(只輸出 ≥2 的群;單值屬性才當版本;多值 COEXIST 不併)
        ─▶ subject-match guard:跨不同 subject 的群一律否決(防 over-merge)
        ─▶ 每群 argmax τ ─▶ 丟舊版
   ─▶ (Assembly) 從 C 移除「被解析掉的舊版」,其餘保留原檢索順序
   ─▶ inference LLM(相同 prompt)─▶ answer
```

**判斷/執行解耦**:LLM 只判「誰跟誰是同一事實(identity)」;**「選最新版」永遠由 deterministic argmax(τ) 做**,LLM 不碰 recency。

### 5.3 LLM dynamic grouping prompt(具體做法)

LLM 在 query-time 的角色被收斂成**單一任務:在檢索回的記憶裡,找出「同一事實的不同版本」的群**(只分群、不選最新、不改寫)。prompt 的設計重點(完整版見 `methods/phase2_query.py: GROUPING_PROMPT`):

```
任務:找出 SAME fact 的不同版本群。不回答 query、不 summarize、不判斷誰較新。

THE TEST(嚴格):僅當兩筆是「對 EXACT SAME 具體實體、EXACT SAME 屬性的競爭答案」
              (只有 value 不同)才合群。

HARD RULES(主導,防 over-merge):
  ① 不同具體實體 = 不同事實 —— 即使同措辭、同屬性類型、甚至同 value(例如多個
     不同的人都「是 USA 公民」不是同一事實)。不合群。
  ② 同實體、不同屬性 = 不同事實(首都 vs 元首;使用者的城市 vs 職業)。不合群。
  ③ 多值屬性 COEXIST(嗜好、朋友、語言、去過的地方)—— 並存,不是版本。不合群。

稀疏先驗:多數記憶彼此無關,合群是少數;不確定就不合群
         (false split 安全;false merge 會隱藏真實版本)。

只輸出 identity(不選 recency,那由下游 argmax 做)。
只列 ≥2 成員的群;未列入的自動保留(Option B,降 LLM 負擔、conservative-by-default)。

輸出 JSON:{"groups":[{"fact":"<實體+屬性>","memory_ids":["id1","id2"],"reasoning":"..."}]}
```

**兩道結構護欄(prompt 之外,程式強制)**:
- **single-valued 由 prompt 規則 ②③ 約束**(多值/異屬性不併)。
- **subject-match guard**(`_subject_consistent`):LLM 輸出的群,若成員橫跨 **≥2 個不同 subject**(取自 triple.subject_id,triple-null 則取 write-time 的 subject_fallback)→ **整群否決**。這把最主要的 over-merge(跨實體誤併)用結構擋掉。

> 設計動機(實證):大 candidate pool 上,純靠 prompt 仍可能把「不同人同屬性/同 value」誤併;subject_fallback + subject guard 讓「不同 subject = 不同事實」這條鐵則對(幾乎)每筆都可結構強制,故能**泛化到非 triple、對話式的一般 KU**,而非只在 FC 有效。few-shot 與規則皆用 user/Marie Curie/Acme 等通用例,刻意避免 FC-overfit。

---

## 6. 模組層級 diff(展開示意圖,paper 用)

| 示意圖模組 | vanilla | ours | 改動性質 |
|---|---|---|---|
| **Storage**(Extract entries) | L1/L2 atomic | 同 | **KEEP** |
| **Update**(原圖「Triple extract → Structural commit」) | LLM 裁決 ADD/UPDATE/DELETE + 破壞性 | per-item triple + 結構 conservative ADD + (S,P) 索引 | **REPLACE**(核心貢獻 1) |
| **Memory bank**(Unified store) | 版本被刪/覆寫 | **all versions kept** | **CHANGE** |
| **Retrieval**(top-K) | top-K cosine | 同 | **KEEP** |
| **Identity grouping** | 無 | 結構 (S,P) + LLM fact-identity | **ADD**(核心貢獻 2) |
| **Temporal resolution** | 無 | timestamp argmax | **ADD** |
| **Generation**(Inference LLM) | 標準 | 同 prompt | **KEEP** |

> 投影片可用配色:KEEP 灰、REPLACE/ADD 綠(對應示意圖的綠色塊 = 我們的新設計)。

---

## 7. 走查範例(一個 conflict 走完三條 pipeline)

**對話歷史(節選,FC 編號事實)**:
```
…  #3  The official language of Japan is Japanese.        (舊版,先進入,τ=3)
… #18  The official language of Japan is Swedish.         (新版,後進入,τ=8;FC 反事實更新)
```
**Query**:`What is the official language of Japan?`　**GT(最新版)= Swedish**

| 階段 | **vanilla Mem0** | **Ours-Phase2** |
|---|---|---|
| Write #3 | ADD "Japanese" | triple `(japan, has official language, Japanese)` τ=3 → ADD + index |
| Write #18 | 候選撈到 "Japanese" → **1 次 LLM 裁決**:小模型對反事實常誤判 → 例如 **DELETE 新版**(它「知道」是 Japanese)或 NOOP → **新版被不可逆丟棄** | triple `(japan, has official language, Swedish)` τ=8 → **ADD**;(S,P) index `(japan, has official language) → [Swedish@8, Japanese@3]` |
| Memory bank | 只剩 "Japanese"(或被覆寫) | **兩版都在** |
| Retrieve | top-100 撈到 "Japanese" | top-100 撈到 "Japanese" 與 "Swedish" |
| Grouping/Resolve | 無 | 兩者同 (s,p) → 一組 → **argmax τ → Swedish@8 勝**,Japanese 丟棄 |
| Context → answer | "Japanese" → 答 **Japanese ✗** | "Swedish" → 答 **Swedish ✓** |

**若新舊版 (S,P) 字串被抽不一致(F2-split)**,例如 `has official language` vs `official language is`:
- Phase 0:落不同組 → 無法 argmax → 兩版都留(context=both)→ 可能答錯。
- Phase 2:兩者 (s,p) 在候選池各自無對手 → 進 dynamic_pool → **LLM 依 fact identity 判為同事實(同 subject=Japan、同屬性)** → 合群 → argmax → Swedish ✓(且 subject guard 確認都是 Japan,不誤併)。

> 這個範例同時展示三件事:① vanilla 破壞性誤判不可逆;② ours 保守保留 → query-time argmax 取最新;③ Phase 2 的 LLM 分群救回 Phase 0 的結構漏網(F2-split)。

---

## 8. 對應實作(重現/查核)

| 模組 | 檔案:函式 |
|---|---|
| Storage(L2 抽取) | `methods/mem0_fc_prompt_fix.py: make_l2_knowledge_prompt` |
| Update — triple 抽取 | `methods/phase0_triple_extractor.py: extract_triples_batch` / `extract_subjects_batch` |
| Update — 結構 commit + (S,P) index | `mem0/memory/main.py: _add_phase0_structural`（env `MEM0_ADD_MODE=phase0_structural`) |
| Retrieval | `agent.py: _handle_mem0_agent`（`memory.search` top-100,與 vanilla 共用) |
| Query — Phase0 結構解析 | `methods/phase0_query.py: group_and_resolve` |
| Query — Phase2 路由+LLM 分群+guard | `methods/phase2_query.py: phase2_resolve`（env `MEM0_QUERY_MODE=phase2`) |
| 注入點 | `agent.py:931`（依 `MEM0_QUERY_MODE` 切 vanilla/structural/phase2,關閉時 byte-identical) |

> Flag 矩陣(可重現 vanilla / ablation / ours):見 [phase2_three_level_evidence.md](phase2_three_level_evidence.md) §1 與 `scripts/run_phase2_sh_*.sh`。

---

## 9. paper Methodology 章節建議結構

```
3. Method
  3.1 Overview(示意圖 + §1 四模組 + §2 差異表)
  3.2 Building on Mem0:what we keep / replace / add(§6 表)
  3.3 Write-time:Structural Update Module(§4;強調 per-item、no cross-item judgment、conservative)
       3.3.1 Schema-free triple extraction
       3.3.2 Structural commit + (S,P) inverted index(unified store, all versions kept)
  3.4 Query-time:Identity Grouping + Temporal Resolution(§5)
       3.4.1 Conditional structural routing
       3.4.2 Structural grouping(shared (S,P))
       3.4.3 LLM dynamic grouping(fact identity;single-valued guard;subject-match guard)
       3.4.4 Temporal resolution(timestamp argmax;judgment/execution 解耦)
  3.5 Worked example(§7)
  3.6 Implementation details(§8;gpt-4o-mini、embedder、frozen caches)
```

---

## 10. 公平性與工程註記(跨系統比較前的 pipeline 對齊)

主張:**所有 benchmark 預設實驗設定皆未更動**(memorize 模板、inference/answer prompt 模板〔`utils/templates.py: BASE_TEMPLATES[dataset]['query'][agent_type]`,各方法各自的模板〕、chunk=512、top-k=100、LLM-as-judge / exact_match 評分、temp=0、embedding model),差異僅在**記憶方法的設計**(抽取 prompt、保守寫入、query-time 解析)。這些都由 config / env gate,關閉時 byte-identical to upstream。**一個必須在論文寫明的例外**與**一個純效能調整**:

### 10.1 檢索 query 對齊(raw question,ungated)— 必須在論文揭露
- **問題**:MemoryAgentBench 對 mem0 的檢索是把「qa 模板包裝後的整段 query」(FC 約 800 字的 "Pretend you are a knowledge management system… Now Answer the Question: …")拿去做 embedding 相似度。指令 boilerplate 主導向量、稀釋真問題,使 GT fact 被擠出 top-100(FC-SH 64k has_pair:wrapped recall@100 = **79%** vs raw question = **100%**;見 experiment_results.md §5.6)。
- **修正**:`agent.py: AgentWrapper._retrieval_query()` 依各 dataset 的 query 模板剝掉 prefix/suffix,**只用真正的 question 去 embed 檢索**;inference 仍餵完整 wrapped query(「找最新」指令保留)。
- **公平性立場(ungated + 揭露)**:
  1. 此修正**對所有 mem0 agent 一致生效**(vanilla baseline 與 ours 都套用)→ ours vs vanilla 的 ablation 乾淨,只剩記憶設計差異;我們報告的 vanilla mem0 數字即為「檢索對齊後」的真實值。
  2. **非獨厚自己**:`zep` 本來就以 `methods/zep.py: get_retrieval_query()` 剝掉任務 boilerplate 才檢索 → benchmark 早把「檢索 embed 什麼」當各方法內部決定(zep 剝、cognee/rag 用整段)。我們只是把 mem0 拉到與 zep 同等檢索衛生,屬 pipeline 對齊而非加 buff。
  3. 論文應明寫:「我們修正 benchmark 對 embedding 檢索方法的 query 對齊問題,vanilla mem0 baseline 亦同樣套用」。

### 10.2 Batch embedding(純效能,結果不變)
- **瓶頸**:mem0 寫入端逐 fact 各發一次 OpenAI embedding API(`mem0/memory/main.py` vanilla path & phase0 path)→ 數千 facts = 數千次序列 HTTP round-trip,延遲主導(262k 尤甚)。凍結 extraction cache 救不到此處(抽取省了、embedding 仍逐筆)。
- **修正**:`mem0/embeddings/openai.py: OpenAIEmbedding.embed_batch()` 一次 `input=list`(≤2048 筆),寫入迴圈改「迴圈前一次批次預算、迴圈內查表」。
- **品質**:**非宣稱 bit-identical**(OpenAI 回 bf16,同一條文字逐筆重跑本就有 1.22e-4 = 1/8192 的量化抖動)。batch 與逐筆在 **API 精度內等價**:maxdiff 與「逐筆 vs 逐筆重跑」完全同級(1.22e-4),single-vs-batch **cosine = 0.9999995** → 對 top-100 排序零影響。屬純 wall-clock 優化,不影響任何結果或公平性。
