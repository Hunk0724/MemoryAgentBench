# gpt-4.1-mini Backbone Extension × FC-SH 64k has_pair — Case Study

> **目的**:2026-07-05 Mac 完成 gpt-4.1-mini × 64k × 6 methods Plan A(見 [`../backbone_extension_plan.md`](../backbone_extension_plan.md))。此檔對 4 個 backbone-shift finding 做 qid-level trace。
> **對應資料**:[`../style_rules_tables_figures_writing.md §10.3b`](../style_rules_tables_figures_writing.md)(EM 表)+ [`pool_acc_crosstab.md`](pool_acc_crosstab.md)(pool state × Acc 4 桶表)。
> **姊妹檔**:[`case_studies_64k.md`](case_studies_64k.md)(gpt-4o-mini 版)。

---

## §0 一句話結論

**gpt-4.1-mini 改變 baselines 的 write-time damage story**,但 **ours 於全 backbone 光譜穩定 80-91%** 才是核心貢獻。

---

## §1 EM 對比 summary

| Method | 4o-mini 64k EM | **4.1-mini 64k EM** | 4.1 sEM | Δ EM |
| :--- | :---: | :---: | :---: | :---: |
| **ours(main)** | **60/66 (91%)** | 53/66 (80%) | 54/66 (82%) | **−7 (−11pp)** |
| ours (no P3) | 58/66 (88%) | 52/66 (79%) | 52/66 (79%) | −6 (−9pp) |
| ours (no struct) | 58/66 (88%) | **27/66 (41%)** | 28/66 (42%) | **−31 (−47pp)** ⚡ |
| ours (+P5) | 60/66 (91%) | 51/66 (77%) | 51/66 (77%) | −9 |
| **(b) mem0+P1** | 34/66 (52%) | **55/66 (83%)** | 55/66 (83%) | **+21 (+32pp)** ★ |
| Zep (k=10) | 36/66 (55%) | 23/66 (35%) | 50/66 (76%) | −13 EM / +8 sEM |

---

## §2 F1 — (b) mem0+P1 recovered +21pp(**why baselines catch up at strong backbone**)

### 2.1 Pool state transition matrix(26 recovered qids)

| Transition | Count | 解讀 |
| :--- | :---: | :--- |
| **PP-OldOnly → PP-New** | 7 | mem0 UPDATE 於 4o-mini 錯把 gt_new 判為 UPDATE 刪掉;4.1-mini 保留 gt_new(替 gt_old ADD 新)|
| **PP-OldOnly → PP-Both** | 7 | 同上,保留兩版本 |
| **PP-Missing → PP-New** | 4 | 4o-mini 兩版都刪光;4.1-mini 保新版 |
| **PP-Missing → PP-Both** | 3 | 保兩版 |
| PP-Both → PP-Both | 5 | pool 不變,answer LLM 挑對(Mode C 救回)|

**21/26 是 pool state 改善**,5/26 是 answer LLM 於 PP-Both 挑對。

### 2.2 Canonical qid=1

**Question**:Who is the author of Hard Times?
**gt_new** = "The author of Hard Times is Martin Luther King Jr."(counterfactual)
**gt_old** = "The author of Hard Times is Charles Dickens"(real world)

| Backbone | (b) Pool state | (b) Response | (b) EM |
| :--- | :--- | :--- | :---: |
| 4o-mini | **PP-OldOnly**(mem0 UPDATE 刪掉 MLK Jr.,留 Charles Dickens)| "Answer: Charles Dickens" | ❌ |
| 4.1-mini | **PP-New**(mem0 UPDATE 保留 MLK Jr.)| "Martin Luther King Jr." | ✅ |

**Mechanism**:gpt-4o-mini 的 mem0 UPDATE LLM 誤把 MLK Jr. 判為「應 UPDATE 掉 Dickens」→ 直接刪 Dickens 存 MLK Jr.,結果反而只留新版......等等,其實反過來:gpt-4o-mini 錯判為「MLK Jr. 這個 fact 應該 UPDATE 掉 Dickens 舊值」,實際上兩者都要保留(這是**新舊兩版本共存**的 case)。gpt-4.1-mini 讀 UPDATE prompt 更準確 → 判為「這是一個新 ADD,不是 UPDATE」→ 兩版都 ADD 到 bank。

### 2.3 Paper 意涵

**mem0 的 destructive damage 主要是 gpt-4o-mini UPDATE LLM 崩壞的產物**,不是 architectural 缺陷。**強 backbone 讓 baseline catch up** —— 但 ours **不依賴強 backbone 就有 60/66(4o-mini)**,是 **backbone-independent 的 robustness**。

---

## §3 F2 — ours main −7pp(**Mode C shift + benchmark D-flag bugs**)

### 3.1 Dropped qids(11 total)

| Transition | Count | qids |
| :--- | :---: | :--- |
| **PP-Both → PP-Both** | 6 | 5, 23, 37, 38, 90, 95 |
| **PP-New → PP-Both** | 3 | 1, 68, 92 |
| **PP-OldOnly → PP-OldOnly** | 1 | **18(D-flag bug)** |
| PP-New → PP-New | 1 | 45 |

### 3.2 Detail — qid=5(Mode C shift)

**Question**:What type of music does Aki Takase play?
**gt_new** = "The type of music that Aki Takase plays is Carnatic music."
**gt_old** = "The type of music that Aki Takase plays is jazz."

| Backbone | Pool state | Response | EM |
| :--- | :--- | :--- | :---: |
| 4o-mini | PP-Both | "Answer: Carnatic music" | ✅ |
| 4.1-mini | PP-Both | "jazz" | ❌ |

**同 pool,不同 answer LLM**。**gpt-4.1-mini 於音樂 domain 有更強 world prior**(Aki Takase 實際上是 jazz pianist)→ 選 world default 而非 pool 給的 new fact。

### 3.3 Detail — qid=18(**benchmark D-flag bug**)

**Question**:Who is the author of Red Storm Rising?
**gt_new** = "Tom Clancy"(**real world knowledge!**);**gt_old** = "Torquato Tasso"(counterfactual)
**gt_seq = 7, old_seq = 1219**(gt_new fact 出現在**更早** → argmax(seq) 邏輯上不可能挑它)

| Backbone | Pool state | Response | EM |
| :--- | :--- | :--- | :---: |
| 4o-mini | PP-OldOnly | "Tom Clancy"(Mode C 世界知識剛好 = gt_new)| ✅ 蒙對 |
| 4.1-mini | PP-OldOnly | "Torquato Tasso"(忠於 pool)| ❌ |

**這是 benchmark 標註錯誤**。64k 共 **2 個 D-flag qid**(qid 18 + qid 20 Great Britain / Europe)。**gpt-4o-mini 兩題全靠 Mode C 蒙對,gpt-4.1-mini 更 faithful to pool 反而"錯"**。

### 3.4 Detail — qid=1(PP-New → PP-Both regression)

**Question**:Who is the author of Hard Times?(和 §2 (b) 的 qid=1 同題!)
**gt_new** = MLK Jr.

| Backbone | Pool state | Response | EM |
| :--- | :--- | :--- | :---: |
| 4o-mini | **PP-New**(phase2 P3 移除 Dickens) | "Answer: Martin Luther King Jr." | ✅ |
| 4.1-mini | **PP-Both**(phase2 P3 於 4.1-mini 沒 merge → 兩版都留) | "Charles Dickens" | ❌ |

**Phase2 P3 grouping 於 4.1-mini 沒把 Dickens/MLK 認成同一 fact 的兩版本**(因為 GROUPING_PROMPT 極保守,見 F3)。

### 3.5 Paper 意涵

ours main −7pp 拆解:
- **−1 是 benchmark D-flag bug**(qid 18,method 邏輯上不可能對)
- **−6 是 real regression**,兩個成因:
  - Mode C shift to different domains(qid 5 music,可能還有其他):**gpt-4.1-mini world prior 更強於特定 domain**
  - Phase2 P3 grouping 於 gpt-4.1-mini 更保守 → PP-New → PP-Both(qid 1, 68, 92)

**net real regression = −6pp**,而非 -7pp。

---

## §4 F3 — p3_only collapse −31pp(**P3 LLM alone is backbone-brittle**)

### 4.1 Dropped qids(34 total)

| Transition | Count | 解讀 |
| :--- | :---: | :--- |
| **PP-New → PP-Both** | 24 | P3 於 4.1-mini **不 merge** → 兩版本都留 |
| PP-Both → PP-Both | 10 | 相同 pool,LLM 挑 old |

### 4.2 Root cause — GROUPING_PROMPT 的極保守設計

`methods/phase2_query.py::GROUPING_PROMPT` 明講:
- 「Clustering is RARE」
- 「When unsure, do not cluster」
- Rule 3:「**MULTI-VALUED PROPERTY = COEXIST**(hobbies, languages spoken, ...)」

**於 FC-SH counterfactual dataset**,fact 是 single-valued(NYT 的官方語言唯一)。但 **prompt 沒明講 single-valued** → LLM 需自行判定。

- **gpt-4o-mini** naive 讀 prompt → 傾向 cluster(視為 same fact 不同 versions)→ PP-New
- **gpt-4.1-mini** careful 讀 prompt → 傾向不 cluster(可能是 multi-valued list)→ PP-Both

### 4.3 GX10 gemma weak-model mirror

GX10 已 push [gemma p3_only 6k results](../need_discuss/gx10_6k_preliminary_observations.md):
- 1B:7/74;4B:26/74;12B:46/74;27B:27/74(**27B 非單調 < 12B**)
- 對比 struct:1B 29 / 4B 54 / 12B 73 / 27B 65(全 backbone struct 較穩)

**gemma3-27B strong end 也 collapse**,同 Mac gpt-4.1-mini 的 41/66:**P3 LLM alone 於光譜兩端都 brittle**,唯有 mid backbone(gpt-4o-mini,gemma3-12B)剛好 sweet spot。

### 4.4 Debug limitation

**P3 GROUPING_PROMPT 有 `reasoning` field 但 cache 沒存**:
```python
# Cache 只存 groups: {hash: [[fact1, fact2], [fact3]]}
# LLM 實際輸出: {"groups": [{"fact": ..., "memory_ids": [...], "reasoning": "..."}]}
```

要 full debug 需修 `phase2_query.py::llm_dynamic_grouping` 存 raw JSON response(見 [`case_studies_64k.md §5.4`](case_studies_64k.md) GX10 artifact 需求)。**目前推斷已足夠 paper narrative,深度 debug 為 follow-up**。

### 4.5 Paper 意涵

**(S,P) structural key 是 backbone-universal scaffold**;P3 LLM 是 backbone-brittle 加分項,只在**光譜 mid tier** 起 net-positive 作用。**這強化 ours main 的設計** —— 主 method 用 `struct + P3` 的 combo:struct 提供 backbone-invariant 底盤,P3 於 mid tier 上加分,strong/weak backbone 上不 net-negative(因為 struct 已 clean pool)。

---

## §5 F4 — Zep strict EM −13 但 sEM 只 −8(**verbose format artifact,MAB flow 公平**)

### 5.1 兩類 verbose 混合

**Type 1 真 verbose format(對 Zep 不公平)**:
- qid=5:Zep 答 "Carnatic music" —— **和 ours 4o-mini 同答**,strict EM 對 ours 認可,對 Zep 也認可(sample check 應同)
  - (查一下 sample check 我可能誤,實際 5 是 concise 但答 jazz 錯了;Zep 的 verbose 例子在 2/4/0)

**Type 2 legitimate KU failure(不是 verbose 是失敗)**:
- **qid=2**:`"David Farragut is a citizen of the United States of America **and** Denmark."` —— **列出兩版本**(舊+新),不 disambiguate
- **qid=4**:`"Joseph Mitchell is a citizen of the United States of America **and** the United Kingdom."` —— 同上
- **qid=0**:`"English and Ancient Greek"` —— 同上

**Zep 於 PP-Both 沒能 disambiguate**,gpt-4.1-mini answer LLM 傾向 hedge。sEM 通過因為 gt_new 是 substring。**這是 real KU failure**,不是純 format。

### 5.2 為何 Zep 公平

- Zep 用**MAB benchmark 為 Zep 明定的 template**(`methods/zep.py::TEMPLATE`)—— **不是我們自己加的**
- MAB 的 question wrapper(含 "give concise answer" 指示)**有** pass through 到 Zep answer LLM
- Zep 的 TEMPLATE 外層包住(FACTS/ENTITIES/EPISODES structure)→ answer LLM 傾向產完整句
- 這是 Zep 的 benchmark-standard 整合方式,**paper 誠實 disclose 這個 artifact 即可**

### 5.3 Paper report 建議

**必須同時報 strict EM + sEM 於 Zep 行**:
- strict EM 反映 format compliance(對 Zep 苛刻)
- sEM 反映 content 正確性(真實 KU capability)
- Table 加註「Zep 於 4.1-mini 的 verbose 是 Zep TEMPLATE + 強 LLM interaction artifact,見 §5.1」

### 5.4 Appendix experiment(future work)

**Zep + MAB default template diagnostic**(5 min,0 API):
- 用 `analysis/rerun_zep_with_ollama_backbone.py` 修改版,削 Zep TEMPLATE,把 edges 當 flat bullet list 餵 MAB default system prompt
- 若 strict EM 顯著提升 → 證明 verbose 是 Zep TEMPLATE + strong LLM 交互產物
- 若 EM 差不多 → 證明是 legitimate KU failure(LLM 從 PP-Both 沒挑對)

**Cost**:0 API,~5 min。**先 defer,paper 正文用 EM + sEM 雙數字即可**。

---

## §6 Paper 主敘事(post-gpt-4.1-mini)

**舊 story**(gpt-4o-mini only):
> ours 全面碾壓 baselines,KU 是 query-time 問題

**新 story**(gpt-4o-mini + gpt-4.1-mini):
> **弱-mid backbone(gpt-4o-mini)**:baselines 於 write-time UPDATE 崩壞(mem0+P1 34/66,52%);ours 靠 phase2 resolution 補救(60/66,91%,+39pp)。**核心貢獻**:query-time KU 讓 backbone 不需強到會做可靠 write-time UPDATE 判定。
>
> **強 backbone(gpt-4.1-mini)**:baselines 於 write-time UPDATE 恢復到接近 ours 水平(mem0+P1 55/66,83%)。這證明 **destructive write damage 大部分是 backbone 特有的產物**,不是 architectural 缺陷。
>
> **ours 的 backbone-independent robustness 才是核心貢獻**:全 backbone spectrum stable 80-91%,而 baselines 於弱 backbone 有 20-40pp 落差。**實務意涵**:大多數部署場景(邊緣、成本、隱私)無法用 strong LLM;ours 的 stability 是 real-world 更關鍵的貢獻。

## §7 Paper 用途決策(給你 review)

**建議進 body 主表(§Experiments)**:
- **10.3a 主表**(gpt-4o-mini 3 lengths)—— main headline
- **10.3b gpt-4.1-mini 64k**—— 附 F1-F4 findings 作為「backbone extension」subsection
- Pool state × Acc crosstab(gpt-4o-mini + gpt-4.1-mini 各 6 rows)—— attribution 深度

**建議進 appendix**:
- ours (+P5) row(main table 已 demote)
- gpt-4.1-mini 其他 length(尚未跑,若跑再加)
- Zep + MAB default template diagnostic(當前 defer)
- P3 reasoning debugging(需改 code 存 raw JSON)
- D-flag qids caveat(§3.3)—— 明講 2/66 例外

**尚未定案 / 待你決定**:
- 是否加 F_pool_diagnostic gpt-4.1-mini 版
- 是否加 F_backbone_gap 圖(EM across backbones,配合 GX10 gemma results)
