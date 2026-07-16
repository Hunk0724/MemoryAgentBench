# Paper Writing Plan(2026-07-17)

> **定位**:整合外部 AI 對 [`narrative/experiment_source_material_0716.md`](narrative/experiment_source_material_0716.md) 的建議,分為**先寫完一版**的 P0 必做清單 vs **建議必做**的 P1/P2 補充。此檔作為 tables / figures / discussion **交付 checklist**,對接 experiment.md 章節骨架。
> **來源**:2026-07-17 外部 AI 讀完 experiment_source_material_0716.md 後給的分層建議 + 我方(session 內)對 repo 實作端的 audit 結論。
> **狀態**:P0 全 READY(除 2 個小 gap 已解),P1/P2 為建議延伸。

---

## §0. P0 必做清單(先完成一版論文為優先)

### §0.1 Tables(7 個必做)

| # | 內容 | 對應素材 §、experiment.md § | 資料狀態 |
|:--|:--|:--|:--|
| **T1** | Datasets summary,涵蓋 FC-SH 4 length(6k/32k/64k/262k)+ LME-KU N=78 的 statistics / split / KU 子集大小 | experiment.md §4.1.1 有 3-length,COVERAGE.md §1/§1.5 有 backbone × method 覆蓋;**需擴 262k row + 合併 LME 統計** | 🟢 READY |
| **T2** | Baselines summary,列每 baseline 的 KU 判斷 timing(write-time / query-time)、判斷機制、對應引用 | methodology_source_material_0716.md §0.2 有 canonical 命名表;experiment.md §4.1.2 有 3 個 subtable + citations | 🟢 READY |
| **T3** | FC-SH gpt-4o-mini × 4 length overall sEM 主表 | 素材 §1.1 Table E1-1;results/fc_sh_main_table_4length.md canonical;experiment.md §4.2.1 目前僅 3 length,**需 refresh 為 4 length + 10 method 版** | 🟢 READY |
| **T4** | OpenAI 3-tier × 6k backbone convergence | 素材 §2.1 Table E1b-1(gpt-4o-mini / gpt-4.1-mini / gpt-5.4-mini);results/fc_sh_backbone_spectrum_6k.md + results/canonical_fc_sh_metrics.md;experiment.md §4.2.3 / §4.3.5 有部分 | 🟢 READY |
| **T5** | Gemma3 spectrum(1B/4B/12B/27B)@ 6k | 素材 §3.1 Table E2-1;results/weak_model_6k_analysis.md + results/canonical_fc_sh_metrics.md gemma tier;experiment.md §4.2.0 Table G0-G3 已有 | 🟢 READY |
| **T6** | Cross-family 4 系列(Gemma2-9B / Llama3.1-8B / Qwen2.5-7B / Mistral-7B)@ 6k | 素材 §4.1 Table E3-1;raw JSONs 於 `outputs/*__{gemma2-9b,llama3.1-8b,qwen2.5-7b,mistral-7b}/` 全 tracked;experiment.md §4.2.0 Table G5 已有 | 🟢 READY |
| **T7** | LME-KU accuracy(N=78,gpt-4o-mini backbone) | 素材 §5.1 Table E4-1;experiment.md §4.6.4 Table 7 為 2026-07-14 canonical(**比素材 §5 更全**,已含 §4.6.4a rigor correction + `ours (+P5) 83.3%` orphan 已標 drop + Zep deferred rationale + Don't Ask out-of-scope 說明) | 🟢 READY(**source material 應 backport experiment.md §4.6.4**)|

### §0.2 Figures(1 個必做,1 個推薦)

| # | 內容 | 圖檔 + 產 script | 狀態 |
|:--|:--|:--|:--|
| **F1(必做)** | **Backbone spectrum 6-tier line plot**;x=(gemma3-1B → 4B → 12B → 27B → gpt-4o-mini → gpt-5.4-mini);y=FC-SH 6k overall sEM;5 method 各一 line(Ours main / Vanilla-RAG / Don't Ask / Zep / Mem0+P1)。**2026-07-17 決策:drop gpt-4.1-mini,paper strong tier 定案為 gpt-5.4-mini**(見素材 §2.4 caveat + writing_plan §3.1) | [`figures_current/F_backbone_spectrum.pdf/png`](figures_current/F_backbone_spectrum.pdf) + `scripts/make_backbone_spectrum.py`(2026-07-17 重寫為 6-tier line plot;舊 bar chart 已 supersede) | 🟢 **DONE**(2026-07-17 commit)|
| **F2(推薦)** | **Length scaling 4-length line plot**;x=(6k → 32k → 64k → 262k);y=overall sEM;gpt-4o-mini backbone,6 method line(Ours main / Don't Ask / Vanilla-RAG / Zep / Mem0+P1 / Mem0 Vanilla) | [`figures_current/F_length_scaling_gpt4omini_4length.pdf/png`](figures_current/F_length_scaling_gpt4omini_4length.pdf) + `scripts/make_length_scaling_gpt4omini_4length.py` | 🟢 **DONE**(2026-07-17 commit)|

### §0.3 Discussion(3 段必做)

| # | 內容 | 對應素材 §、result file | 狀態 |
|:--|:--|:--|:--|
| **D1** | Per-qid error mode:baseline 於 has_pair 失敗時 95-100% 答成 gt_OLD(世界先驗);直接支撐 abstract § 2 causal claim | 素材 §6.1;results/fc_sh_4method_errormode_diag.md(逐 method:Ours Struct-Only 6k 100%、Don't Ask 6k 100%、Vanilla-RAG 32k 96% 皆答 gt_OLD)| 🟢 READY |
| **D2** | P3 觸發率與貢獻:LLM Fallback 僅 14-32% 案例介入,觸發率隨 context length 上升;支撐 method §3.4「LLM 僅為補救」定位 | 素材 §6.1 Diagnostic 1;**2026-07-17 補齊 262k row**(結構 pool 反轉為 99% ⚠;真 P3-active queries 用 §4a diff-based = +5 rescue,與 6k/32k/64k 趨勢一致);results/fc_sh_4method_errormode_diag.md §Diagnostic 1 | 🟢 **DONE**(gap-1 已解)|
| **D3** | Limitations + scope:誠實承認本方法適用於 counterfactual + single-valued personal 型 KU,於 multi-valued personal 上不 outright 領先;呼應 method §3.2 Assumptions + §5 LME 上輸 Vanilla-RAG(1s)發現 | 素材 §5.2 + §7.6;experiment.md §4.6.4 P5/vanilla/b 三個「意外發現」+ §4.6.5 gap decomposition | 🟢 READY |

---

## §1. 建議必做延伸(P1 核心 tables / figures)

超過 P0 但**建議做**的內容,若時間允許可加,提升論文 discriminating power。

### §1.1 T3 主表的 has_pair sEM 版(素材 §1.2)

- 素材 §1.2 Table E1-2(has_pair 74/65/66/77)是 KU 實際發生的子集分析
- **不進主表**,建議放**discussion 或 appendix**,作為「baselines 失敗模式」段落的分母對照

### §1.2 pool state × accuracy analysis(對應 methodology 「錯誤不進入 persistent memory」)

- Design property 之 evidence:4 類 pool state(PP-New / PP-Both / PP-OldOnly / PP-Missing)× 3 method(Ours / Mem0+P1 / Zep)× accuracy
- **已存在**:experiment.md §4.2.2 Table 2(64k rep)+ Table 2b(12B/27B);圖 [F_crosstab_1227_6k.pdf](figures_current/F_crosstab_1227_6k.pdf) 已 tracked
- **caveat**:§4.2.2 in-bucket Acc 仍為 strict EM,需以官方 sEM 重算(pool state 分佈不受影響,只 in-bucket Acc)

---

## §2. 建議必做延伸(P2 核心分析 evidence)

### §2.1 P3 rescue rate dedicated table

- 對應 method 「LLM 僅於結構配對失效時作為補救」evidence
- 素材 §6.1 Diagnostic 1 已完整覆蓋 4 length(2026-07-17 補 262k);**建議直接以 D2 段呈現,不需另外 dedicated table**
- 或整合成 length × (structural pool coverage % / dynamic P3 pool coverage % / P3 in-bucket accuracy %) 3 欄表

### §2.2 length dependency line plot

- **已由 F2 覆蓋**(推薦 figure);對照 T3 表格的視覺讀取

---

## §3. Repo 實作端 audit 結論(2026-07-17)

### §3.1 P0 資料完整度(所有 P0 已 READY 或 DONE)

| 項目 | Verdict | 說明 |
|:--|:--|:--|
| T1-T7 | 🟢 READY | 數字已在 results/*.md canonical + outputs/ tracked |
| F1 | 🟢 **DONE** | 6-tier line plot,5 method,drop gpt-4.1-mini(paper 定案 gpt-5.4-mini 為 strong tier)|
| F2 | 🟢 **DONE** | 4-length line plot,6 method @ gpt-4o-mini |
| D1 | 🟢 READY | fc_sh_4method_errormode_diag.md commit ee06a71 |
| D2 | 🟢 **DONE** | 262k row + trend-reversal caveat 已補(2026-07-17)|
| D3 | 🟢 READY | 素材 §5.2 + §7.6 現成 |

### §3.2 F1 圖的「drop gpt-4.1-mini」決策依據

- **paper 定案 strong tier = gpt-5.4-mini**(素材 §2 + §7.6):gpt-5.4-mini 於 6k 上讓 baselines 大幅上升(mem0+P1 +18、Don't Ask +16、Zep +11),已足夠驗證 backbone 收斂 claim
- **不使用 gpt-4o(原生高 tier)**:避免 ~$5-8 於 gpt-4o full sweep 的成本估算
- **不補 gpt-4.1-mini × Don't Ask × 6k**(原 Gap-2):x 軸從 7 tier 改為 6 tier,drop gpt-4.1-mini,所有 method 於 6 tier 全覆蓋、無空格
- gpt-4.1-mini 相關數據作為 intermediate 對照,保留於 experiment.md §4.3 章節與素材 §2.2 表,不進 F1 主圖

### §3.3 有 stale 需 refresh 的 experiment.md 位置

以下 4 處 experiment.md 目前數字/命名與 2026-07-16 canonical 不同步,建議寫作時對照素材 update:

1. **§4.2.1 Table 1**:目前 3 length × 4 method → refresh 為 4 length × 10 method(直接 lift results/fc_sh_main_table_4length.md)
2. **§4.2.3 Table 3**:目前 backbone 到 gpt-4.1-mini → **改到 gpt-5.4-mini**(2026-07-16 decision)
3. **§4.5.1 Table 5b**:P3 capability-gate 目前 backbone 到 gpt-4.1-mini → 補 gpt-5.4-mini row(素材 §2.1 有數字)
4. **§4.7 Discussion**:目前引用 6k→64k additive-NoKU 上升趨勢作為 Zep 262k crash 外推 → **修正**為 2026-07-16 finding「262k crash 主因 = query-time retrieval miss(NotBothExtracted 82%)」(見 results/zep_ku_resolution_bitemporal.md §4C)

### §3.4 未解 gap(P0 不擋)

- **Zep 於 LME-KU 未跑完整**(smoke ~15 題):若需 Zep vs Ours 於 personal-KU 對比,需 approve full run
- **Zep 於 cross-family(E3)未跑**:若需完整 4-way(加 Zep)ablation,需 approve
- **Ours (LLM-Identity-Only) 於 cross-family(E3)未跑**:若要 4 系列對稱 4-way ablation,需 approve
- **LME backbone spectrum 未做**(只 gpt-4o-mini):若要對稱 F1 於 LME 上,需 approve
- **LME judge model** 是否回官方 gpt-4o judge(vs 目前 gpt-4o-mini judge):未定

---

## §4. 交付 checklist(給寫作階段)

寫 experiment 章節時對照:

- [ ] §4.1 Setup:引 T1 + T2(datasets + baselines)
- [ ] §4.2 Main Results(FC-SH):引 T3 + T5 + T6 + **F1**(F1 於 §4.2 或 §4.3 起頭作 backbone spectrum headline);**F2**(推薦)於 §4.2 呈現 length scaling
- [ ] §4.3 Backbone Extension:引 T4(OpenAI 3-tier)
- [ ] §4.4 Cross-family:引 T6(4 系列)
- [ ] §4.5 Ablation:P3 capability-gate 表(experiment.md §4.5.1 Table 5b,補 gpt-5.4-mini row)
- [ ] §4.6 LongMemEval-KU:引 T7(experiment.md §4.6.4 已 canonical)
- [ ] §4.7 Discussion:D1 + D2 + D3 三段(**§4.7 現有 Zep 262k 敘述需修正**,見 §3.3)

---

## §5. 素材對接 index

| 論文位置 | Source material | Result canonical file |
|:--|:--|:--|
| §4.1 Datasets(T1)| experiment_source_material_0716.md §0.3 / §0.4 | analysis/results/sh_{6k,32k,64k,262k}_mquake_analysis.json + lme_hyps/ |
| §4.1 Baselines(T2)| methodology_source_material_0716.md §0.2 | narrative/references_bib.md |
| §4.2 FC-SH main(T3, F2)| experiment_source_material_0716.md §1.1 / §1.2 | results/fc_sh_main_table_4length.md |
| §4.3 OpenAI tier(T4)| experiment_source_material_0716.md §2.1 / §2.2 | results/fc_sh_backbone_spectrum_6k.md + results/canonical_fc_sh_metrics.md |
| §4.2/§4.3 Gemma3(T5, F1)| experiment_source_material_0716.md §3.1 / §3.2 | results/weak_model_6k_analysis.md + results/pool_acc_crosstab_gemma_6k.md |
| §4.4 Cross-family(T6, F1)| experiment_source_material_0716.md §4.1 | `outputs/*__{gemma2-9b,llama3.1-8b,qwen2.5-7b,mistral-7b}/` |
| §4.6 LME(T7)| experiment_source_material_0716.md §5.1;**experiment.md §4.6.4 為 canonical** | lme_hyps/*.jsonl.eval-results-gpt-4o-mini |
| §4.7 Discussion(D1)| experiment_source_material_0716.md §6.1 | results/fc_sh_4method_errormode_diag.md |
| §4.7 Discussion(D2)| experiment_source_material_0716.md §6.1 Diagnostic 1 | results/fc_sh_4method_errormode_diag.md §Diagnostic 1(**2026-07-17 補齊 262k row**)|
| §4.7 Discussion(D3)| experiment_source_material_0716.md §5.2 + §7.6 | experiment.md §4.6.4 + §4.6.5 |
| §4.7 Discussion(Zep 262k mechanism)| experiment_source_material_0716.md §1.4 | results/zep_ku_resolution_bitemporal.md §4C(**2026-07-16 修正 story**)|

---

## 更新紀錄

- **2026-07-17**:建檔。整合 2026-07-17 外部 AI 建議 + repo 實作端 audit。P0 全 READY;F1 / F2 完成(2 個 make script + 6 個圖檔);D2 262k gap 補齊。列 §3.3 有 4 處 stale 給寫作階段對照。
