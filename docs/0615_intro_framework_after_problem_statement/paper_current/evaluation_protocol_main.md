# Experiments & Evaluation Plan(main,2026-07-04)

> **本文件為當前主 protocol**,對應 paper §Experiments 章節。v1 / v2 已重新定位為 appendix backing(見 §D)。
> **抓大放小**:paper body 優先 E2E Acc 與可解釋的 pool-state × Acc 分析;M1 bank state 等進階指標放 appendix。

---

## § 0 Overview:標準 experiments 章節結構 + priority tier badge

Paper §Experiments 章節將以以下順序敘述,每一節的內容 tie 到 intro / related_work 對應論述:

| § | 內容 | 對應 intro / related_work |
| :---: | :--- | :--- |
| **§1 Datasets** | FC-SH(主評測)+ LongMemEval-KU(泛化)+ 延伸 | intro §KU 定義 + related_work §2.3 KU 評測基準 |
| **§2 Baselines** | 主要對比派別 + ours 自身 ablation | intro §主動派困境 + related_work §2.1 記憶系統 KU 派別 |
| **§3 Backbones** | Strong / Mid / Weak 三檔位 | intro §受限部署(cost / privacy)動機 |
| **§4 Metrics** | E2E has_pair EM + return_context × Acc(主)+ 附錄 metric | intro §記憶如何被檢索用於推論 |
| **§5 Case-study protocol** | 錯誤模式歸因 | intro §write-time commit 不可逆 → 展示具體壞掉的方式 |
| **§6 Matcher** | 判定 gt_new / gt_old 存在的算法 | (實作 rigor,不對應 intro) |

**Priority badge**(貫穿全文):
- **🔴 Tier 1**:body 主故事;現在花時間主軸
- **🟡 Tier 2**:body error analysis;Tier 1 出來後動
- **⚪ Tier 3**:appendix / future work backing;有時間再補

---

## § 1 Datasets(對應 intro KU 問題)

### 1.1 主評測:**FC-SH**(MemoryAgentBench FactConsolidation single-hop)🔴

- **來源**:HF `ai-hyz/MemoryAgentBench` 的 `Conflict_Resolution` split;下載自動化(見 CLAUDE.md)
- **長度**:6k / 32k / 64k / 262k(4 檔對話歷史長度)
- **每長度 100 題** query;分成:
  - `has_pair`(有 GT_old / GT_new 對照):**6k=74 / 32k=65 / 64k=66**(當前主分母)
  - `no_conflict_pair`(單版 GT):約 26 / 35 / 34
- **全 bank conflict-pair 數**(從 ours P1 triple cache (S,P) 分群 ≥2 distinct object):**6k=124 / 32k=631 / 64k=1,295**
- **選擇理由**(對接 intro / related_work §2.3):
  - **高衝突密度**(密集 counterfactual pair)→ 直接壓測 KU 解析機制,不是稀疏檢索
  - **MQuAKE fact-level GT**(每題有 `gt_new / gt_old / gt_seq / old_seq` 標註)→ 支援 pipeline 各階段的細粒度歸因
  - **exact-match 指標**(無 LLM judge)→ 排除評分模型偏誤

### 1.2 泛化檢驗:**LongMemEval-KU**(78 題)🟡

- **來源**:`data/longmemeval/longmemeval_s_cleaned.json`;500 sessions 中 `question_type='knowledge-update'` 的 **78** 題(2026-07-04 verified)
- **選擇理由**:個人事實 KU(personal fact updates)vs FC 世界事實 KU(counterfactual world edits);**證明方法對 KU 的定義涵蓋不同事實類別**
- **判分**:官方 gpt-4o-mini judge(驗證期便宜化,最終回 gpt-4o judge 未定)

### 1.3 延伸(不作主張,視 body 章節穩定後補)⚪

- **BEAM KU** [ICLR'26]:context 1M+ tokens、KU + contradiction resolution 雙能力
- **MemBench FM-ku** [ACL Findings'25]:個人事實 KU 子集
- **策略**:若 paper body 章節穩固後,拓 1-2 個 benchmark 進 generalization 段,不作主張 depth

---

## § 2 Baselines(對應 intro + related_work 對比對手 + ours 自身 ablation)

### 2.1 主要對比 baselines(進主表,🔴 Tier 1)

以**隔離變因**為原則排序 — 每個 baseline 隔離不同的變因,對照 ours 的貢獻:

| Method | Extraction | Write | Query-time KU | 隔離的變因 | 對應 related_work §2.1 派別 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **ours(struct + LLM)** = `ours_no_p5` | ours P1 | conservative ADD | (S,P) + P3 LLM fallback + argmax | **paper 主 method** | 新派:query-time KU resolution |
| **ours(struct only)** = `ours_struct` | ours P1 | conservative ADD | (S,P) + argmax(無 query-time LLM)| P3 LLM identity 貢獻 | 同上 |
| **ours(LLM only)** = `ours_p3_only` | ours P1 | conservative ADD | P3 LLM identity + argmax(無 (S,P))| (S,P) 結構鍵貢獻 | 同上 |
| **(b) mem0+P1** | **共用 ours P1 cache** | mem0 native LLM UPDATE/DELETE | 無(raw top-K)| **write-time commit 破壞性**(extraction 同 ours,差別純寫入層)| 主動派 § coupled/destructive [Mem0] |
| **(a) vanilla mem0** | mem0 native L1 extractor | 同 (b) | 無 | extraction quality(對比 (b) 差異 = extraction 貢獻)| 同上 |
| **Zep**(cloud Graphiti)| Graphiti LLM | LLM `contradicted / duplicate` label → 確定性 invalidate | 無(單輪 graph.search)| **decoupled write-time 派** | 主動派 § decoupled [Zep] |
| **LCA**(gpt-4o-mini full-context)| — | — | — | 無記憶架構下限 | 環境對照(long-context) |

### 2.2 Ablations(進附錄,⚪ Tier 3)

| Method | 對比目的 |
| :--- | :--- |
| **ours(full P3+P5)** = `ours` | 隔離 P5 conflict-type classifier 的**淨貢獻**;預期於 FC 上為負(6k p3_only 95.9% > full 91.9%);paper 主 method 用 `ours_no_p5` |

### 2.3 待決 baseline(暫不進主表,⚪ appendix candidate)

| Method | 狀態 | 意義 |
| :--- | :--- | :--- |
| **LightMem** [ICLR'26] | 不自跑;引 paper §5.6 自承 destructive | 主動派 § coupled/offline-batch 派別代表 |
| **Deterministic write-time pointer** | 待實作 | 隔離「贏 query-time」vs「贏 deterministic」— reviewer 防守用 |

---

## § 3 Backbones(對應 intro §受限部署動機 + paper 核心 empirical claim)

### 3.1 三檔位設計 🔴

| Tier | Model | 角色(對接 intro 動機)| 現況 |
| :--- | :--- | :--- | :--- |
| **Strong** | **gpt-4.1-mini**(primary)/ gpt-4.1(secondary,cost-permitting) | 錨點:**預期 baseline 略勝或平手**;**誠實揭露** — 與主張一致(強 LLM 補足 write-time 判斷)| 未跑 |
| **Mid** | **gpt-4o-mini** | gap 出現(**cost-constrained deployment 主場**,對應 intro FrugalGPT 引用)| ✅ 3 lengths × 4 methods 已跑 |
| **Weak** | gemma3 1B / 4B / 12B / 27B(via Ollama)| **gap 最大**(**privacy-sensitive on-device 主場**,對應 intro SlimLM / on-device 引用)| GX10 6k 已跑;32k / 64k 待跑 |

### 3.2 敘事鏈(paper 章節主軸)

> **(1) Strong-model regime**:LLM 判斷品質高、write-time commit 誤差小 → 現有派別(mem0 / Zep)接近或略勝 ours。paper **誠實揭露** — 與主張一致:ours 的優勢來自「降低對 LLM 判斷品質的依賴」,強模型上此依賴本就低。
>
> **(2) Mid-model regime(gpt-4o-mini)**:ours has_pair 91-96%,(b) mem0+P1 45-46%,gap 46-50 pp。write-time destructive commit 已明顯造成問題。
>
> **(3) Weak-model regime(gemma3 1B-27B)**:GX10 6k struct EM 28/50/69/59(1B/4B/12B/27B),ours 逐漸接近或略輸(取決於 LLM 判斷品質)。**gap 隨 backbone 變弱單調放大**;12B 已追平 gpt-4o-mini(93%);1B/4B 上 ours < ours_struct(query-time LLM component 反害,因判斷品質過差)。
>
> **這是 paper 核心 empirical claim**:constrained deployment(cost 或 privacy)下,ours 的 architectural 優勢直接兌現為 has_pair EM 提升。

### 3.3 圖規則(依 advisor)

- 離散 backbone → **bar chart**(不連折線)
- 或:(ours − best baseline)gap × backbone → 若 gap 單調可用一條線
- **黑白友善**:hatch pattern 區分方法,一個 accent color
- caption 三段論(what / observation / implication)

### 3.4 主圖(paper §Experiments 頭條)

- **F_backbone_gap.png**(**待補完 strong + weak 32k/64k 才畫**):x = backbone tier(strong / mid / weak),y = has_pair EM,群組 = 主要 methods

---

## § 4 Metrics(對應 intro §記憶如何被檢索用於推論)

### 4.1 主指標:E2E has_pair EM 🔴

- **定義**:FC-SH `has_pair` exact-match accuracy(依 MAB 官方判分)
- **分母**:每長度 74/65/66(6k/32k/64k)
- **主圖**:[`figures/F_ours_ablation_haspair.png`](figures/F_ours_ablation_haspair.png)(bar chart,3 methods × 3 lengths)
- **主表**:[`results/fc_sh_has_pair_main_table.md`](results/fc_sh_has_pair_main_table.md)

### 4.2 主分析:return_context × Acc cross-tab 🔴(**Tier 1 待做**)

**目的**:對每 method × 長度,把「pool state」(送進 answer LLM 前的記憶內容)與「Acc」(最終答對錯)交叉分類,**精準呈現答題結果如何被 pool state 預測**。

> ⚠️ **為什麼要這個而不是 Resolution 指標**:「Resolution 對」(pool 只有 gt_new)不等於「Acc 對」(LLM 可能答錯);「pool 兩版都在 (Both)」也可能答對(LLM 從中挑對);「pool 兩版都沒 (Neither)」偶爾也可能答對(LLM 從 world knowledge 猜對)。**只有 Resolution × Acc 的完整 4×2 交叉才能歸因**。

**每 method × 長度,一張 4×2 表**:

| pool state | Acc ✓ | Acc ✗ | 小計 | 詮釋 |
| :--- | ---: | ---: | ---: | :--- |
| **PP-New**(pool 只含 gt_new)| a | b | a+b | 理想:a 高、b ≈ 0(pool 給對答案 → LLM 應該抄對) |
| **PP-Both**(兩版都在)| c | d | c+d | 中間:依賴 answer LLM 從兩版挑對;template hint「取 serial 大者」幫助 |
| **PP-OldOnly**(pool 只含 gt_old)| e | f | e+f | 理想:e ≈ 0、f 高(pool 只給錯 → LLM 只能猜)|
| **PP-Missing**(兩版都不在 pool)| g | h | g+h | 理想:g ≈ 0、h 高(retrieval / write-time miss)|
| **Total** | | | N | |

**主論述**:
- **ours vs baseline 的 Acc 差距,主要來自 PP-New / PP-OldOnly / PP-Missing 分佈的差異**(即 pipeline 是否把 gt_new 送進 pool、把 gt_old 濾掉),**而非 PP-Both 時的 answer LLM 猜對率**
- 這說明 ours 的優勢是「**pipeline 讓 pool 更乾淨**」,不倚賴 LLM 從混雜的 pool 中挑對 → 對應 intro 核心主張:**query-time KU resolution 讓記憶正確地被檢索用於推論**

**資料來源**(全部已存在,不需 API 重跑):
- pool state:ours 用 `memories_str`(actual answer LLM saw)、mem0(b) 用 `retrieved_memories`、Zep 用 `edges`
- Acc:每長度的 `results.json` 的 `exact_match`
- **實作**:`analysis/compute_pool_acc_crosstab.py`(**Tier 1 待寫**,基於 `analysis/compute_m1_m2_m3.py` 的 matcher v3)

**輸出**:除 4×2 表外,列出每 wrong 桶的 qid list → 供 §5 case study 挑選

### 4.3 附錄 metric(⚪ Tier 3,infrastructure 已 ready)

Body 章節穩定後才展開這些;現有 v2 infrastructure 已 ready、隨時可跑:
- **M1 bank state**:NFPR / OFPR / BSPR / DLR — 量化 write-time damage(對應 intro §write-time 不可逆)
- **M3 root-cause 分佈**:mem0 event 5-bucket / Zep(invalid_at, expired_at)3-tuple / ours pool composition
- **N_bank 分母版**:6k=124 / 32k=631 / 64k=1295 pairs — statistical power 補強
- **BJV**(Blind Judgment Volume,v1 保留):write-time LLM 判斷次數 / query 觸及 pair 數
- 詳見 [`../paper_draft&materials/evaluation_protocol_fc_mquake_v2.md`](../paper_draft&materials/evaluation_protocol_fc_mquake_v2.md) 完整 spec

---

## § 5 Case-study Protocol(🟡 Tier 2)

**目的**:對每個 wrong-qid 桶(由 §4.2 cross-tab 產出),挑 3-5 個 qid **展開 pipeline trace**,說明各 method 各自錯在哪一步。

### 5.1 錯誤模式命名(從 32k struct 分析拓展至全 method)

| 模式 | 對 method 的意義 | 已見的 example |
| :--- | :--- | :--- |
| **A. Predicate stem mismatch** | P2 抽 predicate 產生 stem-vs-full 兩版 → struct 分不同 (S,P) 桶 → 兩版並存 | 32k qid=1/3/65/81/87/94(6/7 struct-only-wrong)|
| **B. Subject fragmentation** | 同一實體被抽成不同 subject_id → 完全散架 | 32k qid=51(Ireland 元首,3 個 subject_id)|
| **C. Answer LLM world-knowledge override** | pool 有 gt_new,LLM 答世界知識舊值 | 32k qid=2(power_forward → basketball)|
| **D. Dataset temporal reversal** | gt_seq < old_seq(正確答案在**較早**的 chunk)→ argmax(ord) 邏輯上不可能對 | 32k qid=8/9(London/Rome)|
| **E. Surface variant** | GT_new/GT_old 表面極相似(substring 關係)| 32k qid=21(rugby vs rugby union)|

### 5.2 Case study 流程(每 wrong 桶挑 3-5 qid)

每 qid 拉:
1. **question + gt_new + gt_old**(from `analysis/results/sh_{L}_mquake_analysis.json`)
2. **retrieved_memories top-100**(from `query_*.json` 的 `retrieved_memories`)+ 每項 triple metadata
3. **resolved_pool / memories_str**(from `query_*.json`)
4. **response**(LLM 答什麼)
5. **對照全 method** 這 qid 是對 / 錯

寫成 3 段:
- **What happened**:pipeline 各階段的具體狀態
- **Where it failed**:標明錯誤模式(A/B/C/D/E)
- **Why it matters**:如何對應 method 的設計選擇

### 5.3 論文正文 vs 附錄的 case 數

- **正文**:6-10 個具代表性 case(每模式 1-2 個)
- **附錄**:剩餘 case,+ 分佈統計

已完成的 case study 材料:
- [`results/32k_case_study.md`](results/32k_case_study.md)(struct 32k Cat A 為主)
- [`results/weak_model_case_study.md`](results/weak_model_case_study.md)(GX10 weak-model regime)

---

## § 6 Matcher(rigor,不對應 intro 但實作必要)

**用途**:判定「memory 是否包含 gt_new / gt_old」— M1 / M2 / M3 / cross-tab 都靠這個。

### 6.1 判準(v3,triple-based rigor)

- **shared stem tokens ≥ 60%** 出現在 memory
- AND **target object 100% tokens** 出現在 memory
- AND **non-target object 100% tokens NOT 全在 memory**(排除 ambiguity)
- 屏蔽 stopwords(the / a / an / of / is / was / are / were / be / in / on / to / for / and / or / at)

### 6.2 為何拒絕 Layer-1 SequenceMatcher(v1/v2 遺留)

- Layer-1 SequenceMatcher.ratio() ≥ 0.85 **false-positive**:
  - "goaltender ... pesäpallo" vs "goaltender ... ice hockey" ratio = **0.857 剛好超過閾值**
  - 但兩者是 **不同 object 的不同 fact**,不應算同一 fact
- v3 改用 triple-based 邏輯,對 goaltender 8/8 test cases 全通過

### 6.3 待做:matcher precision audit ⚪

- 30 pair × 3 method = 90 樣本人工核對
- 附錄報 precision / recall
- 預期 v3 precision > 95%

**實作**:`analysis/compute_m1_m2_m3.py` `match_pair()`(見 [../paper_draft&materials/evaluation_protocol_fc_mquake_v2.md §5](../paper_draft&materials/evaluation_protocol_fc_mquake_v2.md) 完整 rationale)

---

## § 7 ☐ 待決問題(Experiment / Evaluation 相關;Method 相關的見 [`method_v1.md`](method_v1.md) §4)

### 7.1 Baseline 定義

- **✅ Q1**:**mem0 (a) vs (b)** — (a) vanilla:mem0 native L1 extractor + native destructive;(b) mem0+P1:共用 ours P1 cache + native destructive。差別 = **extraction quality 隔離**
- **✅ Q2**:**Zep** — 只用 cloud(Phase A),不自跑 Graphiti(Phase B 若 reviewer 挑再做)
- **✅ Q3**:**LightMem** — 不自跑,cite paper §5.6 自承
- **✅ Q8**:**Deterministic pointer baseline** — 降級 appendix,不擋主 pipeline

### 7.2 Backbone / embedding

- **✅ Q4**:**Strong-model = gpt-4.1-mini 主 / gpt-4.1 次**(2026-07-04 決定)
- **✅ Q5**:**Embedding 固定 text-embedding-3-small** 跨所有 backbone,weak-model 換本地 embedding 屬 sensitivity 分析(appendix)

### 7.3 泛化

- **✅ Q6**:**LongMemEval-KU = 78 題** verified(2026-07-04)

### 7.4 code / method 相關

Method 相關 → 見 [`method_v1.md`](method_v1.md) §4:
- **Q7**:(S,P) 倒排索引死碼處理
- **Q9**:P5 程式開關 flag 名稱

---

## § D Appendix / Future Work backing

已有 infrastructure,body 章節穩定後隨時可展開:

| Item | 位置 | 進 paper 的方式 |
| :--- | :--- | :--- |
| M1 bank state metrics(NFPR/OFPR/BSPR/DLR)| `analysis/compute_m1_m2_m3.py` | Appendix 表:write-time damage 量化 |
| N_bank 分母(6k=124 / 32k=631 / 64k=1,299)| 同上 `enumerate_n_bank_pairs()` | Appendix statistical power |
| M3 mem0 event 5-bucket 分佈 | 同上 `m3_mem0_rigorous()` | Appendix mem0 失敗模式歸因 |
| M3 Zep (invalid_at, expired_at) | 同上 `m3_zep()` | Appendix Graphiti label 反推 |
| Matcher precision audit(30 pair × 3 method)| 待做 | Appendix matcher rigor |
| Zep cumulative-state audit | `zep_audit()` | Appendix Zep data sanity |
| Zep-fact-only ablation | 待做(改 `compose_search_context`)| 補 Zep 顆粒度公平對比 |
| Deterministic pointer baseline | 待實作 | Appendix isolate 「query-time」vs「deterministic」 |
| LongMemEval / MemBench / BEAM 泛化 | 待跑 | Generalization 段 |

**參考文件**:
- [`../paper_draft&materials/evaluation_protocol_fc_mquake_v1.md`](../paper_draft&materials/evaluation_protocol_fc_mquake_v1.md) — 終態診斷 EFR/IRR/BJV(語意 ↔ M1 DLR)
- [`../paper_draft&materials/evaluation_protocol_fc_mquake_v2.md`](../paper_draft&materials/evaluation_protocol_fc_mquake_v2.md) — M1/M2/M3 完整 spec + implementation

---

## § E 現在該做什麼(action items,優先序)

**🔴 現在動手(Tier 1 body 頭條)**:
1. **[<1 hr]** 寫 `analysis/compute_pool_acc_crosstab.py` → 產出每 method × 3 length 的 4×2 cross-tab + wrong-qid list per bucket
2. **[<15 min]** 產出結果進 `results/pool_acc_crosstab.md`(進 paper §4.2)

**🟡 Tier 2 body error analysis(Tier 1 出來後動)**:
3. **[<2 hr]** 對 wrong-qid list per bucket 挑 6-10 個 qid 展開 case study → `results/case_studies.md`(進 paper §5)

**中程(1-2 週,Tier 1 主表擴展)**:
4. GX10 gemma3 32k / 64k full × 全 methods → 更新 F_struct_backbone
5. Mac strong-model(gpt-4.1-mini)× 3 lengths × 主 baselines → 產 F_backbone_gap
6. mem0(a) vanilla full × 3 lengths(補上目前只有 6k n=2 smoke)

**⚪ Appendix / defer(body 章節穩定後才做)**:
7. Deterministic pointer baseline 實作 + 3 lengths
8. Matcher precision audit
9. Zep cumulative-state audit + fact-only ablation
10. M1 / M3 完整表(v2 infrastructure 已 ready,直接跑)

**Future work / discussion**:
11. Self-host Graphiti(僅若 reviewer 要求)
12. LongMemEval-KU / MemBench / BEAM 泛化
