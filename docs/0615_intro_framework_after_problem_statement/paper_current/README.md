# paper_current/ — 論文主用資料夾(Mac + GX10 共用)

> **這個資料夾只放進 paper body 一定會用到的檔案**。中途探索、appendix candidate、未定案的東西 → 放 [`../need_discuss/`](../need_discuss/)。
> 舊 draft、archive 檔留在 [`../paper_draft&materials/`](../paper_draft&materials/) 不動。

---

## 🎯 現在該做什麼(body 優先,非 appendix)

**Tier 1 — body 主故事(現在的重心)**:
- **E2E has_pair EM**(主 metric,已有數字)
- **`return_context × Acc` cross-tab**(每 method × 3 length 的 4×2 表,**待做**)
- **Backbone gap 敘事**(strong = gpt-4.1-mini / mid = gpt-4o-mini / weak = gemma3 各 size,**待補完 strong + weak 32k/64k**)

**Tier 2 — body error analysis**(當 Tier 1 出來後動)`:
- Case study on wrong-qid buckets(3-5 個 qid × 錯誤模式 A/B/C/D/E)

**Tier 3 — appendix 材料(現階段不擋主 pipeline,有時間再做)**:
- M1 bank state(NFPR / DLR / BSPR),N_bank 分母(v2 protocol infrastructure 已 ready)
- M3 root cause 完整分佈,mem0 write-event 5-bucket
- Matcher precision audit(30 pair × 3 method)
- Zep full graph dump / Zep-fact-only ablation
- Deterministic write-time pointer baseline
- LongMemEval / MemBench / BEAM 泛化

**⚠️ 提醒**:paper 讀者第一眼看**答題對不對**,第二眼看**為什麼**。M1/M3 是「為什麼中的為什麼」— 有價值但**不是頭條**。花時間先在 Tier 1/2,Tier 3 等 body 章節穩住再補。

---

## 資料夾結構

```
paper_current/
├── README.md                    ← 本檔:分流規則 + 工作流程
├── narrative/                   ← paper 敘事三主軸
│   ├── intro_zh_revised_v5.md
│   ├── related_work_zh_v2.md
│   └── vocabulary_v2.md
├── method_v1.md                 ← Method spec + Appendix A(實際 prompts)
├── evaluation_protocol_main.md  ← Tier 1/2/3 priority protocol + baseline / backbone / matcher
├── results/                     ← 進 body 的實驗結果 MD
│   ├── fc_sh_has_pair_main_table.md   ← 主表(6/32/64k has_pair EM,4 methods + baselines)
│   ├── weak_model_case_study.md       ← GX10 weak-model regime(Resolution / Reader / Cat A)
│   └── 32k_case_study.md              ← struct 32k Cat A 深入 case study
└── figures/                     ← 進 body 的圖(從 figures_current/ 拉的 curated 版本)
    ├── F_ours_ablation_haspair.{png,pdf}   ← ours ablation 主圖(Mac)
    ├── F_struct_backbone_6k.{png,pdf}      ← weak-model backbone(GX10)
    ├── F_struct_vs_p3_overall_6k.{png,pdf} ← struct vs P3(GX10)
    └── F_resolution_vs_em_6k.{png,pdf}     ← Resolution-vs-EM 分離(GX10)
```

---

## 分流規則(Mac + GX10 共用)

### ✅ 進 `paper_current/` 的判準

要進主資料夾,**兩個條件都要成立**:
1. **對應到 paper body 某章某節某段**(intro / related_work / method / experiments / discussion 有明確位置)
2. **內容已定案**(數字已跑過、caption 寫過、論述邏輯 stable)

如果不確定屬於哪一節、或者只是「跑起來看看好像有用」 → **先進 `need_discuss/`**,等定位清楚再搬。

### 🔀 分流到 `need_discuss/` 的例子

- 中途 metric 探索(如 M1 bank state 全 baseline 表 — 目前是 appendix candidate,還沒進 body)
- diagnostic 圖(不是 body 主圖的變體)
- 未定案的 baseline(如 Deterministic pointer,還在討論)
- rollup 分析檔(給團隊 review 用,不是給 reviewer 看)

### 🗑️ 進 `paper_draft&materials/` archive(舊 draft,不搬)

- 舊版 intro / related_work(v2 系列)
- 早期 experiment_plan.md / experiment_chapter_draft.md
- 已被 method_v1 取代的 method_pipeline_and_prompts.md
- v1 / v2 evaluation protocol(已標 appendix,實作 spec 用)

---

## 對 Mac / GX10 兩台機器的分工約定

**Mac 端(主 backbone = gpt-4o-mini + gpt-4.1-mini)**:
- 主跑 mid + strong-model 實驗(gpt-4o-mini 已完 / gpt-4.1-mini 待跑)
- 產出:main table + ours ablation 圖 → 進 `paper_current/results/` + `figures/`

**GX10 端(主 backbone = gemma3 1B / 4B / 12B / 27B)**:
- 主跑 weak-model regime(6k 已完 / 32k / 64k 待跑)
- 產出:F_struct_backbone / F_struct_vs_p3 / F_resolution_vs_em → 進 `paper_current/figures/` + 對應 case study MD

**共同約定**:
1. **跑實驗前**先看本 README「該做什麼」的 Tier 1/2/3 優先序,不做 appendix 專屬實驗除非 Tier 1/2 已交付
2. **產出後**先問「這對應到 paper body 哪一節?」— 明確 → `paper_current/`;不明確 → `need_discuss/`
3. **更新 shared log**:每個 cell 跑完填 [`../../handoff/experiment_results_shared.md`](../../handoff/experiment_results_shared.md) 主表(繼續作跨機器實驗記錄的 source of truth)
4. **branch 同步**:兩台都在 `exp/v2-llm-judge`,常用 `git pull` + `git push`;重大改動先 discuss

---

## 現在缺什麼(待補到 `paper_current/`)

**Tier 1**:
- ☐ `analysis/compute_pool_acc_crosstab.py`(script)+ 產出 4×2 cross-tab 表(結果進 `results/`)
- ☐ `F_backbone_gap.png`(主圖,x = backbone tier,y = has_pair EM,需 strong + weak 32k/64k 補完才畫)

**Tier 2**(當 Tier 1 出來後):
- ☐ `results/case_studies.md`(6-10 個 qid × Cat A/B/C/D/E)

**參考文件位置**(不在 `paper_current/`,但重要):
- `../../handoff/experiment_results_shared.md` — 跨機器實驗 log(source of truth)
- `../../handoff/reproduction_log_mac_studio.md` / `reproduction_log_gx10.md` — 每台 reproduction 紀錄
- `../paper_draft&materials/current_ours_method_pipeline_and_prompts.md` — 完整 method 實作參考(method_v1 是精煉版)
- `../paper_draft&materials/references.md` — 論文引用清單
- `../paper_draft&materials/ku_taxonomy_and_scope_zh.md` — KU scope 定義(vocabulary 相關)

---

## v1 → v2 → main protocol 演進脈絡(供 reviewer / 團隊查閱)

- **v1**(2026-07-04 早):EFR / IRR / BJV 終態診斷 3 個指標 → 已被降級為 appendix(語意等於現在 M1 的 DLR)
- **v2**(2026-07-04 中):M1 / M2 / M3 完整 3 層體系 + backbone / baseline / matcher rigor 全 spec → 已被降級為 **implementation spec + appendix backing**
- **main**(2026-07-04 現在):**優先順序改為 Tier 1(E2E + pool×Acc)/ Tier 2(case study)/ Tier 3(appendix)**;v1 / v2 的 rigor 仍成立、當 backing。

過去版本檔案(不搬到這裡,archive 用):
- `../paper_draft&materials/evaluation_protocol_fc_mquake_v1.md`(header 已標 APPENDIX)
- `../paper_draft&materials/evaluation_protocol_fc_mquake_v2.md`(header 已標 APPENDIX / IMPL SPEC)
