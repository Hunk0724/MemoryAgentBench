# Evaluation Protocol — Main(priority-ordered,2026-07-04)

> **本文件為當前主 protocol**。v1(EFR/IRR/BJV 終態診斷)與 v2(M1/M2/M3 完整體系)已重新定位為 **appendix / future work backing**;它們的 rigor 準備仍成立,但**不是主論述**,詳見文末 §D。

> **抓大放小原則**:paper 讀者第一眼看**答題對不對**,第二眼看**為什麼**。M1(bank state)是「為什麼中的為什麼」,對支持論述有價值但非頭條,放 appendix。

---

## § 0 Priority tiers(這決定花時間的先後)

| Tier | 內容 | paper 位置 | 現況 |
| :---: | :--- | :--- | :--- |
| **Tier 1**(主故事)| **E2E has_pair EM** + **return_context × Acc cross-tab** | 主圖 + 主表 | E2E 已有;cross-tab 待做 |
| **Tier 2**(主文 error analysis)| **Case study**(3-5 個 wrong-qid × 錯誤模式)| 主文分析章 | 32k struct 已做 partial,擴至全 method 待做 |
| **Tier 3**(appendix / future work)| M1 bank state / N_bank 分母 / matcher precision audit / Zep full graph dump / Deterministic pointer baseline | appendix + future work | v2 已完成大部分 infrastructure |

---

## § 1 Tier 1 — 主 metric

### 1.1 E2E has_pair EM(paper 頭條)

- 指標:FC-SH `has_pair` exact-match accuracy(依 MAB 官方)
- 分母:每長度 74/65/66(6k/32k/64k)
- 主圖:F_ours_ablation_haspair(bar chart,3 methods × 3 lengths,已有)
- 主 backbone 對比:F_backbone_gap(尚未產出;bar × backbone tier,見 §3)

### 1.2 return_context × Acc cross-tab(**Tier 1 待做**)

**目的**:每個 method 內部,把「pool state」與「Acc」交叉分類,呈現**答題結果如何被 pool state 預測**。

**每個 method × 長度**,一張 4×2 表:

| pool state | Acc✓ | Acc✗ | 小計 | 詮釋 |
| :--- | ---: | ---: | ---: | :--- |
| **PP-New**(只新)| a | b | a+b | 理想:a 高、b ≈ 0(pool 給對答案,LLM 應該抄對)|
| **PP-Both**(新舊都在)| c | d | c+d | 中間:依賴 answer LLM 從兩版挑對;template hint 幫助 |
| **PP-OldOnly**(只舊)| e | f | e+f | 理想:e ≈ 0、f 高(pool 只給錯的,LLM 只能猜)|
| **PP-Missing**(兩版都無)| g | h | g+h | 理想:g ≈ 0、h 高(retrieval / write-time miss)|
| **Total** | | | N | |

**主論述**(paper 對讀者說的 story):
- ours vs baseline 的 **Acc 差距,主要來自 PP-New / PP-OldOnly / PP-Missing 分佈的差異**(即 pipeline 有沒有把 gt_new 送進 pool、把 gt_old 過濾掉),**而非 PP-Both 時的 answer LLM 猜對率**。
- 這說明 ours 的優勢是「**pipeline 讓 pool 更乾淨**」(不倚賴 LLM 從混雜的 pool 中挑對),即論文的核心主張:**query-time KU resolution 讓記憶正確地被檢索**。

**資料來源**(全部已存在,不需 API 重跑):
- pool state:對 ours 用 `memories_str`(actual answer LLM saw)、對 mem0(b) 用 `retrieved_memories`、對 Zep 用 `edges`。
- Acc:每長度的 `results.json` 的 `exact_match`。
- 具體實作:見 `analysis/compute_pool_acc_crosstab.py`(待寫,基於 compute_m1_m2_m3.py 的 matcher v3)。

**輸出**:除 4×2 表外,**列出每 wrong 桶的 qid list**,供 Tier 2 case study 挑選。

---

## § 2 Tier 2 — Case study 錯誤模式歸因

**目的**:對每個 wrong-qid 桶,**挑 3-5 個 qid 展開 pipeline trace**,說明各 method 各自錯在哪一步。這是**定性補充**,不用做全 population。

### 2.1 錯誤模式命名(從 32k struct 分析拓展至全 method)

| 模式 | 對 method 的意義 | 前一輪已見的 example |
| :--- | :--- | :--- |
| **A. Predicate stem mismatch** | P2 抽 predicate 產生 stem-vs-full 兩版 → struct 分不同 (S,P) 桶 → 兩版並存 | 32k qid=1/3/65/81/87/94(6/7 struct-only-wrong) |
| **B. Subject fragmentation** | 同一實體被抽成不同 subject_id → 完全散架 | 32k qid=51(Ireland 元首,3 個 subject_id)|
| **C. Answer LLM world-knowledge override** | pool 有 gt_new,LLM 答世界知識舊值 | 32k qid=2(power_forward → basketball 世界知識)|
| **D. Dataset temporal reversal** | gt_seq < old_seq(正確答案在**較早**的 chunk) → argmax(ord) 邏輯上不可能對 | 32k qid=8/9(London/Rome)|
| **E. Surface variant** | GT_new/GT_old 表面極相似(substring 關係) → 分不出或誤合 | 32k qid=21(rugby vs rugby union)|

### 2.2 Case study 流程(每 wrong 桶挑 3-5 qid)

對每個 qid,拉:
1. **question + gt_new + gt_old**(from sh_{L}_mquake_analysis.json)
2. **retrieved_memories top-100**(from query_*.json 的 `retrieved_memories`)+ 每項的 triple metadata
3. **resolved_pool / memories_str**(from query_*.json)
4. **response**(LLM 答什麼)
5. **對照 4 model** 這 qid 是對/錯

寫成 3-段:
- **What happened**:pipeline 各階段的具體狀態
- **Where it failed**:標明錯誤模式(A/B/C/D/E)
- **Why it matters**:如何對應 method 的設計選擇

### 2.3 需要 case study 的最少 qid 集

**每 method × 每長度 × 每桶,挑 2-3 qid**,總共約:
- 4 methods × 3 lengths × 4 wrong 桶 × 2 qids = **96 case slots**(上限)
- 實際上很多桶會空(如 ours PP-Missing 很少),真正要寫 20-40 個 qid case
- 論文正文只放 **6-10 個具代表性的 case**;其餘進附錄

---

## § 3 Backbone Sweep(paper 核心 empirical claim)

### 3.1 三檔位

| Tier | Model | 現況 | 敘事定位 |
| :--- | :--- | :--- | :--- |
| **Strong** | ☐ GPT-4o / GPT-5.x / Claude Opus 4.x(擇一至二) | 未跑 | 錨點:**預期 baseline 平手或略勝**;誠實揭露(與主張一致)|
| **Mid** | gpt-4o-mini | ✅ 3 lengths × 4 methods 已跑 | gap 出現(cost-constrained 主場) |
| **Weak** | gemma3 1B / 4B / 12B / 27B | GX10 6k 已跑;32k/64k 待跑 | **gap 最大**(privacy-sensitive on-device 主場) |

### 3.2 敘事鏈

> 「Strong → Mid → Weak:**gap 隨 backbone 變弱單調放大**。ours 保持平緩(bank 從不 destructive),baseline 隨 LLM 判斷品質下降而崩塌。此 gap 曲線是「delegating fewer write-time LLM judgments 的架構承諾」在 constrained deployment 情境的**兌現 value**。」

### 3.3 圖規則

- 離散 backbone:**bar chart**(不連折線)
- 或:(ours − best baseline)gap × backbone,若 gap 單調可用一條線
- **黑白友善**:hatch pattern 區分方法,一個 accent color
- caption 三段論(what / observation / implication)

---

## § 4 Baselines(對比對象,已定案)

### 4.1 主要對比

| Method | 對比目的 | 現況 |
| :--- | :--- | :---: |
| **ours(struct + LLM)** = `ours_no_p5` | **paper 主 method**;struct routing + P3 補救 + argmax | ✅ 3 lengths |
| **ours(struct only)** = `ours_struct` | 隔離 P3 LLM 貢獻 | ✅ |
| **ours(LLM only)** = `ours_p3_only` | 隔離 (S,P) 結構鍵貢獻 | ✅ |
| **(b) mem0+P1** | write-time commit 破壞性隔離 | ✅ |
| **(a) vanilla mem0** | extraction quality 隔離 | ☐ full 3 lengths 待跑 |
| **Zep**(cloud Graphiti)| decoupled write-time 派 | ✅ 有數字(k=10 caveat)|
| **Deterministic pointer** | 「贏 query-time」vs「贏 deterministic」隔離 | ☐ 待實作 + 跑 |
| **LCA**(gpt-4o-mini full-context)| 無記憶架構下限 | ✅ |

### 4.2 Ablation(降級至附錄)

- **ours(full P3+P5)** = `ours`:P5 conflict-type classifier。**FC 上 P5 為淨負收益(6k p3_only=95.9% > full=91.9%)**,主 method 用 `ours_no_p5` 或 `ours_p3_only`。

---

## § 5 Matcher(rigor-tight,triple-based)

**已於 v2 確立、compute_m1_m2_m3.py 內實作 matcher v3**:

- 拒絕 Layer-1 SequenceMatcher 的 false positive(goaltender→pesäpallo vs goaltender→ice_hockey ratio=0.857 誤過關)
- 判準:**shared stem tokens ≥60%** AND **target object 100% tokens 在 mem** AND **non-target object 100% tokens NOT 全在 mem**
- 屏蔽 stopwords(the/a/an/of/is/was/...)避免虛匹配

**Matcher precision audit(Tier 3 appendix)**:
- 每長度隨機抽 30 pair × 3 methods = 90 判定
- 人工核對 → 附錄報 precision / recall
- 目前實作預計 precision > 95%(基於 goaltender 手動測 8/8)

---

## § 6 ☐ 待決問題(Experiment / Evaluation 相關;Method 相關的見 method_v1 §4)

### 6.1 baseline 定義

- **☐ Q1**:**mem0 baseline (a)/(b) 差異** — **我的建議**:
  - **(a) vanilla mem0**:mem0 native L1 extractor + mem0 native destructive UPDATE/DELETE
  - **(b) mem0+P1**:**共用 ours P1 extraction cache**(=同抽取)+ mem0 native destructive
  - **差別 = extraction quality 的隔離**:(a)-(b) 的 Acc 差 = mem0 extraction 品質差
  - 論文表格列名:「mem0(vanilla)」與「mem0+P1」

- **☐ Q2**:**Zep 自跑 Graphiti** — **我的建議 NO(Phase A cloud 就夠)**:
  - Cloud 就能觀察 `(invalid_at, expired_at)` 反推 `contradicted / temporal_extraction / valid` 三態
  - `duplicate_facts` label 不可反推(邊沒建)是唯一 gap → 對主論述**非 critical**
  - Phase B 自跑 Graphiti 若 reviewer 要求再做(1-2 週工程)
  - **待你 confirm**

- **☐ Q3**:**LightMem 是否自跑** — **我的建議 NO(cite paper §5.6 自承 destructive)**:
  - LightMem 屬 coupled 破壞派,§5.6 已自承 destructive loss
  - Paper 主論述引 LightMem 為「他們自己說會不可逆丟失」的 evidence
  - 自跑成本高但 marginal value 低,除非 reviewer 挑
  - **待你 confirm**

- **✅ Q8**:**Deterministic write-time pointer baseline** — **決策:降級為 appendix 實驗**:
  - user 判定為 appendix 材料,不進主表
  - 保留 rationale:隔離「贏 query-time」vs「贏 deterministic」對 reviewer 質疑 point 有防守價值
  - 實作簡單,若有閒時間可跑;現階段不擋主 pipeline

### 6.2 Backbone / embedding

- **☐ Q4**:**大模型檔位選哪顆** — **我的建議 GPT-4o**:
  - 熟悉、穩定、成本可控
  - 若 GPT-5.x 已發布可考慮換(2026-07 未定)
  - Claude Opus 4.x 也可,但 API 呼叫更貴
  - 最少跑 1 顆 × 3 lengths × 主 baselines 定錨

- **☐ Q5**:**Embedding model 全檔位固定同一顆?** — **我的建議 YES(text-embedding-3-small)**:
  - 減少變因,好對比
  - 小模型情境要換本地 embedding 屬 sensitivity 分析(appendix)
  - Weak-model regime 的核心是 backbone,不是 embedding

### 6.3 泛化

- **✅ Q6**:**LongMemEval-KU = 78 題**(已 verify):
  - `data/longmemeval/longmemeval_s_cleaned.json` 內 `question_type='knowledge-update'` 直接 count = **78**
  - 全 500 session 分佈:multi-session 133 / temporal-reasoning 133 / knowledge-update 78 / single-session-user 70 / single-session-assistant 56 / single-session-preference 30
  - 舊文件寫 45 可能是有進一步 filter 的舊子集

### 6.4 code 清理

- **☐ Q7**:**(S,P) 倒排索引死碼** — **我的建議:REPO README 註明 disabled + 加 dead-code TODO 標記**,不主動移除(避免 reviewer 對照 code 時混淆,但也不誤導 method 描述有此功能)

- **☐ Q9**:**P5 程式開關 flag 名稱** — **實作已有:`MEM0_P5_SKIP=1`**(見 phase2_query.py:483):
  - 預設 `unset`(等於 P5 on)= ours(full)
  - `=1` 時 skip P5 = ours(no_p5)= paper 主 method
  - 保持這個約定,不改

---

## § D Appendix / Future Work backing(現有 M1/M2/M3 infrastructure 全留)

**下列全部 infrastructure 已存在、可隨時 activate**:

| Item | 位置 | 進 paper 的方式 |
| :--- | :--- | :--- |
| M1 bank state metrics(NFPR/OFPR/BSPR/DLR)| `analysis/compute_m1_m2_m3.py` | Appendix 表:每 baseline 的 write-time damage 量化 |
| N_bank 分母(6k=124/32k=638/64k=1299 pairs)| `analysis/compute_m1_m2_m3.py` `enumerate_n_bank_pairs()` | Appendix statistical power 補強 |
| M3-mem0 rigorous buckets | 同上 `m3_mem0_rigorous()` | Appendix:mem0 各失敗模式分佈 |
| M3-Zep (invalid_at, expired_at) | 同上 `m3_zep()` | Appendix:Zep 反推 Graphiti LLM label |
| Matcher precision audit | 待做,30×3 樣本 | Appendix:matcher 品質保證 |
| Zep cumulative-state audit | `zep_audit()` | Appendix:Zep 資料 sanity |
| Zep full graph dump / Zep-fact-only ablation | 待做 | Phase B,若 reviewer 挑 |
| Deterministic pointer baseline | 待實作 | 主表對比(若納入)|
| LongMemEval / MemBench / BEAM 泛化 | 待跑 | 論文泛化章 |

**參考文件**:
- [evaluation_protocol_fc_mquake_v1.md](evaluation_protocol_fc_mquake_v1.md) — 終態診斷 EFR/IRR/BJV(語意 ↔ 現在的 M1 DLR)。**位置:appendix reference**
- [evaluation_protocol_fc_mquake_v2.md](evaluation_protocol_fc_mquake_v2.md) — M1/M2/M3 完整體系 + Backbone/Baseline/Matcher rigor。**位置:appendix + implementation spec**

---

## § E 現在該做什麼(action items,順序 = 執行優先)

**現在動手**:
1. **[<1 hr]** 寫 `analysis/compute_pool_acc_crosstab.py` → 產出每 method × 3 length 的 4×2 表 + wrong-qid list per bucket
2. **[<15 min]** 更新 `docs/handoff/m1_m2_m3_results.md` 加上 Tier 1 主表(cross-tab),M1 挪至下方
3. **[<2 hr]** 對 wrong-qid list per bucket,挑 6-10 個 qid 展開 case study,寫入 `docs/handoff/case_studies.md`

**中程(1-2 週)**:
4. GX10 gemma3 32k/64k full × 全 methods
5. Strong-model backbone(定 1 顆)× 3 lengths × 主 baselines
6. mem0(a) vanilla full × 3 lengths(補上目前只有 6k n=2 smoke)
7. Deterministic pointer baseline 實作 + 3 lengths

**Appendix / defer**:
8. Matcher precision audit
9. Zep cumulative-state audit + fact-only ablation
10. M1/M3 全 baseline 完整表(v2 protocol 已有 infrastructure,直接跑)

**Future work / discussion**:
11. Self-host Graphiti(僅若 reviewer 要求)
12. LongMemEval-KU / MemBench / BEAM 泛化
