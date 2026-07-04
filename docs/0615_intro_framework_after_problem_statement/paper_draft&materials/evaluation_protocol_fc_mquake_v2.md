# Evaluation Protocol + Experiments Plan(v2,2026-07-04,rigor-first)

> ⚠️ **重新定位:APPENDIX / IMPLEMENTATION SPEC**
> 當前主 protocol 已改為 [`evaluation_protocol_main.md`](evaluation_protocol_main.md)(Tier 1/2/3 priority)。
> 本文的 M1 / M2 / M3 完整體系 **rigor 準備仍成立**;M2 被 main 選為 Tier 1 主 metric(return_context × Acc cross-tab)、M1 / M3 挪至 Tier 3 appendix backing。
> 本文是 **implementation spec + full metric family backing**,供:
> (a) `analysis/compute_m1_m2_m3.py` 對應的完整 metric 定義文件
> (b) Appendix 若要展開 M1 bank state / M3 root-cause 完整分佈時的參考
> **不再是主 protocol**。

---

> **v2 對 v1 的差異**:
> 1. **從 metric 提案拓展為完整 experiments plan**(併入 method_experiments_draft_v1 §4 的 backbone / baselines / ablations,method_v1 從此僅描述方法本身)
> 2. Metric 體系從 v1 EFR/IRR/BJV → **M1/M2/M3 三層**,補上 pool-state(v1 缺)
> 3. **Baseline 排序**:優先 ours(struct)/ ours(LLM)/ ours(struct+LLM),ours(full P3+P5) 降級至 ablation 尾段(P5 對 FC 為淨負收益,不是主 method)
> 4. Zep 判準精確化:透過 cloud (invalid_at, expired_at) 二元組反推 Graphiti LLM label(subagent 調查已釘死,見 §3.3)
> 5. Backbone 敘事鏈明確化:strong → mid → weak 三檔,預期 gap 隨 backbone 變弱單調放大
>
> **Rigor commitment**:每個 metric 有精確定義、每個 threshold 有 justification、每個 claim traceable to code+data、每個 caveat explicit。

---

## 0. Baseline Roster(以隔離變因為原則)

### 0.1 主要對比 baselines(進主表)

| Method | Extraction | Write | Query-time KU | 隔離的變因 |
| :--- | :--- | :--- | :--- | :--- |
| **ours(struct + LLM)** = `ours_no_p5` | ours P1 | conservative ADD | (S,P) routing + P3 LLM fallback + argmax | **paper 主 method** |
| **ours(struct only)** = `ours_struct` | ours P1 | conservative ADD | (S,P) + argmax(無 LLM at query)| **P3 貢獻**(對比 ours_no_p5)|
| **ours(LLM only)** = `ours_p3_only_no_struct` | ours P1 | conservative ADD | P3 LLM identity + argmax(無 (S,P) routing)| **(S,P) 結構鍵貢獻**(對比 ours_no_p5)|
| **(b) mem0+P1**(destructive)| **共用 ours P1 cache** | native LLM UPDATE/DELETE/ADD/NOOP | 無(raw top-K)| **write-time commit 破壞性**(extraction 與 ours 相同 → 差異純粹在此)|
| **(a) vanilla mem0** | mem0 native L1 extractor | 同 (b) | 無 | **extraction quality**(對比 (b) 差異 = extraction 差異)|
| **Zep**(cloud Graphiti)| Graphiti-side LLM | LLM `contradicted / duplicate` label → 確定性 invalidation | 無(單輪 graph.search)| **decoupled write-time 派** |
| **Deterministic pointer** ☐ | ours P1 cache | Append-all + 寫入時維護 (S,P) pointer 指向 argmax(ordinal) | 無(讀 pointer)| **「贏在 query-time」vs「贏在 deterministic」**;若接近 ours → 主張下修為「conservative ADD + deterministic 就夠」 |
| **LCA**(gpt-4o-mini full-context)| — | — | — | **無記憶架構下限**(long-context 上限)|

### 0.2 Ablations(進附錄)

| Method | 對比目的 |
| :--- | :--- |
| **ours(full P3+P5)** = `ours` | 隔離 P5 conflict-type classifier 的**淨貢獻**;預期於 FC 上為負(97% conflicts 為 FRESHNESS,P5 邊際)|

**排除理由(P5 為何非主 method)**:
- FC-SH 上 conflict-type 97% 為 FRESHNESS,P5 邊際貢獻 <2 pp
- Mac Studio 已 empirical:6k p3_only 71/74(95.9%)> full 68/74;32k 亦然
- P5 的 downside case(qid 21 rugby/rugby-union 被誤判 COMPLEMENTARY)已釘死
- **Paper 主 claim 走 "structural 為骨,P3 LLM 為補救 fallback,P5 for 多值 KU 是 future work"**

### 0.3 待決事項

- ☐ Deterministic pointer baseline 是否納入(強烈建議納入,見上表)
- ☐ mem0-vanilla 是否對稱跑 4 個長度(目前只有 6k n=2 smoke;需 full 100q × 3 長度)
- ☐ Zep 是否 reset + 重跑(等 §5 audit 結果決定)

---

## 1. Backbone Sweep(paper narrative 主軸)

### 1.1 三檔位設計

| Tier | Model | 角色 | 現況 |
| :--- | :--- | :--- | :--- |
| **Strong** | GPT-4o 或 Claude Opus 4.x(擇一)☐ | 敘事錨點:**預期 baseline 略勝或平手**(強 LLM 補足 write-time 判斷) | 未跑 |
| **Mid** | **gpt-4o-mini**(cost-constrained deployment)| gap 開始出現,ours 已顯示優勢 | 已跑完整 3 lengths × 4 methods |
| **Weak** | gemma3 1B / 4B / 12B / 27B(via ollama)| **gap 最大**,ours 保持平緩、baseline 崩塌 | GX10 6k 已跑;32k/64k 待跑 |

### 1.2 敘事鏈(paper 章節主軸)

> 「(1) **Strong-model regime**:LLM 判斷品質高、write-time commit 誤差小 → 現有派別(mem0/Zep)接近或略勝 ours。paper **誠實揭露** — 這與我們主張一致:ours 的優勢來自「降低對 LLM 判斷品質的依賴」,強模型上此依賴本就低。
> (2) **Mid-model regime(gpt-4o-mini)**:ours 各長度 has_pair 68-71/74(91-96%),(b) mem0+P1 33-34/74(45-46%),gap 46-50 pp。write-time destructive commit 已明顯造成問題。
> (3) **Weak-model regime(gemma3 1B-27B)**:GX10 6k struct EM 28/50/69/59(1B/4B/12B/27B),ours(full P3+P5)10/50/(?)/59。**gap 隨 backbone 變弱單調放大;12B 已追平 gpt-4o-mini(93%);1B/4B 上 ours < ours_struct(LLM component 反害,因判斷品質過差)**。
> **這是 paper 核心 empirical claim**:constrained deployment(cost 或 privacy)下,ours 的 architectural 優勢直接兌現為 has_pair EM 提升。」

### 1.3 backbone 圖規則(依 advisor:離散變數用 bar,不連折線)

- 主圖:**bar chart** × backbone tier(x)× has_pair EM(y),多方法群組
- 或:(ours − best baseline) gap × backbone → 一條線也可以(gap 是有趨勢的連續變數 → 折線適用)
- **黑白友善**:hatch pattern 區分方法,只 accent color 標主 method
- caption 三段論(what / observation / implication)

### 1.4 待決事項

- ☐ Strong-model 選哪顆(至少 1 顆定錨):GPT-5.x / GPT-4o / Claude Opus 4.x
- ☐ 各檔位 embedding model 是否固定同一顆(當前 = OpenAI text-embedding-3-small);若 weak-model 情境要換本地 embedding → 需 sensitivity 分析
- ☐ LongMemEval 泛化檢驗:是否跑 mid + strong,或只跑 mid 就夠

---

## 2. 三層 Metric 體系(rigor 版)

### 2.1 M1 — Bank State per pair(以 write-time commit 是否破壞性為主張)

**分子 / 分母**:

| Metric | 定義 |
| :--- | :--- |
| **NFPR**(New-Fact Presence Rate)| bank 內能從 memory 讀出 gt_new 的 pair 數 / 全 pair 數 |
| **OFPR**(Old-Fact Presence Rate)| bank 內能讀出 gt_old 的 pair 數 / 全 pair 數 |
| **BSPR**(Both-Present Rate)| 兩版都能讀出的 pair 數 / 全 pair 數;**ours by construction = 100%** |
| **DLR**(Destructive-Loss Rate)= 1 − NFPR | gt_new 不可還原比例;**對應 v1 IRR** |

**分母(pair 母體)兩層報告**:

| 母體 | 定義 | 6k | 32k | 64k |
| :--- | :--- | ---: | ---: | ---: |
| **N_query**(queried subset)| sh_{L}_mquake_analysis.json has_pair | 74 | 65 | 66 |
| **N_bank**(全 bank pairs)| ours P1 triple cache 內 (S,P) 群 with ≥2 distinct objects | **124** | **631** | **1,295** |

**Rigor caveat**:
- N_bank 的「pair」不必然對應 MQuAKE 原始 counterfactual pair,可能包含**同 (S,P) 但語意上是 COMPLEMENTARY**(如「languages spoken」多值)。對 6k 需**手動 audit 30 個** N_bank pair 判是否為真 counterfactual FRESHNESS pair(非 COMPLEMENTARY)。若 audit 顯示 > 90% 為真 counterfactual → N_bank 分母可信;否則需 filter。
- N_query 分母無此問題(GT 直接標明 has_pair vs no_conflict_pair),但樣本數較小。
- **Paper 主表用 N_query**(GT 直接,無 audit risk);**附錄用 N_bank**(統計顯著性,搭 audit 結果)。

### 2.2 M2 — Pool State per query(以 pipeline KU effectiveness 為主張)

**分子 / 分母**:

| Metric | 定義 |
| :--- | :--- |
| **PP-New**(Pool Purity, New only)| pool 只含 gt_new(gt_old 已被 pipeline drop)/ N_query |
| **PP-Both** | pool 內兩版都在 / N_query |
| **PP-OldOnly** | pool 只含 gt_old(gt_new 已被 destroy 或未 retrieve)/ N_query |
| **PP-Missing** | 兩版都不在 pool / N_query |

**資料來源(per query JSON 各 method)**:

| Method | Pool field |
| :--- | :--- |
| ours(all variants)| `resolved_pool`(agent.py:1102 patch 後儲存)|
| mem0(b)/vanilla | `retrieved_memories`(raw top-100)|
| Zep | `edges`(top-10)|

**Rigor caveat**:
- Zep 只回 top-10(cloud rate 限制)vs 其他 top-100 → PP-Missing 於 Zep 上會 upper-bound 較低。此不對稱要在 caption 標明。
- Zep-fact-only ablation:改 `compose_search_context` 讓 nodes/episodes 可 gate → 加一列進 M2 表格,fact 顆粒度 apples-to-apples 對比 mem0/ours。

### 2.3 M3 — Root-cause attribution(以歸因至 baseline 具體設計選擇為主張)

#### 2.3.1 M3-mem0:LLM Event 分佈

**Rigor 定義**(採用 user 的洞察 + 我原有的 state simulation):

| Bucket | 分子條件(**必須全部成立**)| 語意 |
| :--- | :--- | :--- |
| **UPDATE_kept_new** | (i) gt_old NOT in final bank AND (ii) gt_new IS in final bank AND (iii) 該 pair 的 UPDATE event 曾發生 | **KU 判斷正確**(LLM 識別衝突並取代)|
| **ADD_both_coexist** | (i) gt_new IS in bank AND (ii) gt_old IS in bank AND (iii) 該 pair 只有 ADD events(無 UPDATE / DELETE)| LLM 未識別衝突 → 並存 |
| **DELETE_dropped_new** | (i) gt_new NOT in bank AND (ii) 該 pair 的 gt_new memory 曾被 DELETE | **new fact 反被刪**(FC 反事實特有病理)|
| **DELETE_lost_new** | (i) gt_new NOT in bank AND (ii) gt_old NOT in bank AND (iii) 該 pair 的 gt_old 曾被 DELETE(但無 gt_new ADD)| 刪舊沒補新 |
| **NONE_silent** | (i) gt_new NOT in bank AND (ii) 該 pair 無任何 UPDATE/DELETE event | silent drop / LLM NONE 或抽取 miss |
| **Ambiguous** | 上述均不滿足 | 手動 audit case |

**Rigor 保證**:每個 bucket 條件互斥且 collectively exhaustive;bucket 命中需 event trace 直接證據,不靠 fuzzy state inference。

#### 2.3.2 M3-Zep:(invalid_at, expired_at) 二元組

| Bucket | 條件 | 對應 Graphiti LLM label |
| :--- | :--- | :--- |
| **valid** | gt_new edge 存在 AND `invalid_at = None` | 未判為衝突 |
| **contradicted-invalidated** | gt_new edge 存在 AND `invalid_at ≠ None ∧ expired_at ≠ None` | LLM `contradicted_facts` label |
| **temporal-extraction** | gt_new edge 存在 AND `invalid_at ≠ None ∧ expired_at = None` | source 內事件時間(非 KU 判斷)|
| **missing** | 該 (S,P) 完全沒 gt_new edge | 兩個成因不可分辨:(a) LLM `duplicate_facts` label(邊沒建),(b) Graphiti extraction miss。需 self-host 才能分辨。 |

**Graphiti 反推依據**(subagent 調查):
- `graphiti_core/prompts/dedupe_edges.py` `EdgeDuplicate` schema 只有 2 個 label
- `edge_operations.py:451-466` `resolve_edge_contradictions`:label=contradicted → 設 invalid_at + expired_at(同時)
- `extract_edge_dates` prompt:從 source 抽時間 → 只設 invalid_at(不設 expired_at)
- label=duplicate:根本不建新 edge → cloud API 看不到

**Rigor 保證**:反推依據來自 Graphiti 源碼路徑,file:line 已釘。**caveat**:duplicate label 不可反推,對「gt_new missing」需標明「不可分辨兩個成因」。

#### 2.3.3 M3-ours:Pool composition

| Bucket | 條件 |
| :--- | :--- |
| **gt_new_only_kept** | pool 只含 gt_new(理想:P3/struct 群成功、argmax drop 舊)|
| **both_kept_argmax_didnt_drop** | 兩版都在 pool(P3 未群、struct 未群、或群後 tie / P5 判 non-freshness)|
| **gt_new_dropped_gt_old_kept** | argmax 反選 gt_old(dataset temporal-reversal artifact,如 6k qid=8/9 gt_seq < old_seq)|
| **neither_in_pool** | 兩版都不在 top-K(retrieval miss)|

### 2.4 End-to-end has_pair EM(主指標)

- 沿用 FC-SH 官方 exact-match
- M1/M2/M3 是 EM 的**歸因鏈**;歸因於「write-time damage / retrieval miss / KU-resolution / answer LLM 世界知識覆寫」四個階段之一

---

## 3. Matcher 三層設計(rigor:matcher precision 必須 audit)

### 3.1 三層 matching

1. **String full-sentence match**(嚴格):normalize(memory)包含 normalize(gt_text) OR SequenceMatcher.ratio() ≥ 0.85
2. **Subject+Object token match**(語意 fallback):從 gt_text 提取 normalize(subject) + normalize(object) → 兩者都在 memory → 命中(對抗 mem0 UPDATE merge)
3. **LLM judge fallback**(僅第一、二層 miss):固定 prompt 用 **gpt-4o**(強模型、與被測系統無關)→ 「這段 memory 是否記載了 <triple>?」→ yes/no

### 3.2 Matcher precision audit

- 每長度隨機抽 **30 個 pair × 3 methods = 90 個 matcher 判定**(6k 全 30、32k 全 30、64k 全 30)
- **人工核對**:matcher 判 hit 是否真的正確?matcher 判 miss 是否真的沒 hit?
- 論文附錄報 precision / recall,若 < 90% → 調整第 2 層 token overlap 邏輯或第 3 層 LLM prompt

### 3.3 threshold justification

- **SequenceMatcher.ratio() = 0.85**:對「Rap rock was created in the country of Russian Empire」vs「Rap rock is a genre created in Russia」→ ratio ~0.72,合理判 miss(不同 fact)。對「Elvis Presley is married to Priscilla Presley」vs「Elvis Presley married Priscilla Presley」→ ratio ~0.93,合理判 hit。
- 此 threshold 於本 protocol 從始至終**固定**;若 audit 顯示 miss 過多 → 修訂需在附錄記錄調整過程

---

## 4. Zep Cumulative-State Audit(rigor:必做)

### 4.1 風險

Zep cloud 對同一 (context_id, sub_dataset) 的 graph 累積寫入(agent.py:1129-1141 catches "already exists" 卻不 delete)。多次 ingest 產生重複 edges。

### 4.2 Audit 步驟

1. 拉全 graph edges via `client.graph.search(query="", limit=very_large)`
2. 對比 P1 extraction cache 的 fact count(N_bank facts:455/2309/4570)
3. **判準**:
   - edges ≤ 1.2× N_bank → **clean**,現有 Zep results 可信
   - edges > 1.5× N_bank → **dirty**,需 reset + 重跑

### 4.3 若 dirty 的 reset 策略

改 agent.py:1131-1141:
```python
# Reset graph before create (Zep cumulative-state fix)
try: self.client.graph.delete(graph_id=graph_id)
except: pass  # not exists is OK
self.client.graph.create(graph_id=graph_id)
```

**成本**:每長度重跑 Zep 約 6-10 min(cloud async);3 長度總 30 min。

---

## 5. 執行計畫

### 5.1 metric 計算

1. **Matcher precision audit**(30×3=90 判定,人工)- 釘住品質
2. **N_bank pair audit**(手動 audit 30 個 6k pair 判 counterfactual vs COMPLEMENTARY)- 釘住母體
3. **Zep cumulative-state audit** - 決定是否 reset 重跑
4. **compute_m1_m2_m3.py** 全 length × 全 method:
   - 主表用 N_query 分母(rigor primary)
   - 附錄用 N_bank 分母(power secondary)

### 5.2 缺的實驗 cell

- ☐ mem0-vanilla 3 lengths full
- ☐ Deterministic pointer baseline 3 lengths(若納入)
- ☐ Zep 3 lengths 重跑(若 audit 顯示 dirty)
- ☐ Strong-model 1 顆 × 3 lengths × 主 baselines(gap 敘事錨點)
- ☐ Weak-model gemma3 × 32k/64k 全方法 × has_pair EM(GX10 上跑)

### 5.3 論文材料產出

- **主表(§5.1)**:EM × 6 lengths × 6-8 methods × 3 backbone tiers(可能 3D → 或分成 mid 主表 + strong/weak 對照小表)
- **子表 A**:M1 DLR × 6k/32k/64k × 5 baselines(N_query 分母,附錄補 N_bank)
- **子表 B**:M2 PP-New × 同上
- **子表 C**:M3 分佈 × mem0/Zep/ours 三方 × 3 lengths
- **附錄**:matcher precision audit / N_bank vs N_query 比較 / Zep audit 結果 / BJV(v1 保留輔助)

---

## 6. Backbone × Metric 交叉 narrative(給 paper 用)

三個 backbone tier × 三層 metric 的交叉解釋:

| Backbone × Metric | Strong | Mid(gpt-4o-mini)| Weak(gemma3 1B-27B)|
| :--- | :--- | :--- | :--- |
| **M1 DLR(mem0+P1)** | 預期 20-30%(LLM 判斷準確度較高) | ~35-45%(first cut)| 預期 50-70%(LLM 判斷崩)|
| **M2 PP-New(ours)** | 預期 > 95% | > 90%(first cut,待 patch fix) | 預期 struct alone 60-80% + P3 上補 15pp |
| **M3 mem0 UPDATE_kept_new %** | 高(強 LLM 常正確 UPDATE)| 中 | 低(常誤判成 NOOP/DELETE)|

**論文 headline claim**:「三層 metric 全部顯示 gap 隨 backbone 變弱單調放大,體現 ours 的 architectural 承諾(write-time 不做跨筆 LLM 判斷)在 constrained deployment 情境的**兌現 value**。」

---

## 7. v2 vs v1 差異總表

| Item | v1 | v2 | 理由 |
| :--- | :--- | :--- | :--- |
| Scope | Metric protocol only | Metric + Experiments plan(併入)| method_v1 專注 method 描述;evaluation_protocol 專注 experiments + evaluation |
| Metric | EFR / IRR / BJV | M1 / M2 / M3(3 層)| 補上 pool-state(v1 缺);M3 三方 baseline 對稱處理 |
| EFR | 各 baseline 自定義正確終態 | 併入 M3 各 bucket 分佈,不再單獨報 | 避免「用他們沒承諾的標準打分」 |
| IRR | 直接指標 | 沿用為 DLR,語意相同 | 命名靠近 KE 文獻(Efficacy 系)|
| BJV | 主指標 | 輔助指標(附錄)| 主表位置留給更直接的 DLR/PP-New |
| Matcher | 2 層(string + LLM)| 3 層(string / subject+object token / LLM)+ audit protocol | 對抗 mem0 UPDATE merge;audit 釘住 precision |
| Pair 母體 | N_query only | N_query(主表)+ N_bank(附錄)| 增加統計顯著性 |
| Baseline 主序 | 未明說 | ours(struct) / ours(LLM) / ours(struct+LLM) / mem0(b)+P1 / mem0(a) / Zep / Det.pointer | user 明確排序,P5 降級至 ablation |
| Backbone | 未論述 | 3 檔位 × 敘事鏈 | 為 paper 核心 empirical claim 定錨 |
| Zep 判準 | 未細化 | (invalid_at, expired_at) 二元組 + 反推依據來自 Graphiti file:line | subagent 調查已釘死 |

---

## 8. 待決事項與時間規劃

**技術決策**:
- ☐ Deterministic pointer baseline 納入?
- ☐ Strong-model 選一顆
- ☐ Zep-fact-only ablation 實作優先度

**Audit 待做**:
- ☐ Matcher precision(30×3=90 樣本)
- ☐ N_bank pair counterfactual 純度(30 個 6k)
- ☐ Zep cumulative-state

**實驗待跑**:
- ☐ mem0-vanilla full × 3 lengths
- ☐ Deterministic pointer(若納入)× 3 lengths
- ☐ Strong-model × mid baselines × 3 lengths
- ☐ GX10 gemma3 × 32k/64k full

**估工作量**:audit 全部 <2 天;實驗待跑約 1 週(cloud 為 wall-clock 主導,可 parallelize 3+ key)。
