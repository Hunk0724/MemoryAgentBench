---
name: feedback_paper_final_unified_rerun
description: 論文最終每個數字都要由穩定機器、定版統一 pipeline + 完全相同設定下「一次性重跑全矩陣」取代;不可混用本機演進過程累積的既有數字;草稿數字一律 PROVISIONAL 佔位
metadata:
  type: feedback
---

2026-06-30 使用者明確要求:**論文要報的數字,必須是「公平嚴謹、同個狀況下跑出來」的結果。**

具體:**paper-final 數字 = 在「同一台穩定機器、同一份定版 pipeline、完全相同設定(同 backbone / chunk / top-k / judge 決策 / seed 規則)」下,把全矩陣(所有方法 × 所有長度 × 兩 benchmark)一次性重跑**取代。**不可混用**本機研究演進過程累積的既有數字——它們跨時間、跨中途設定(例:64k overall 曾因 raw-q/L2 版本變動 65→94),交叉比較不公平。

因此本機 distill 出的 experiment 章草稿(`paper_draft&materials/experiment_chapter_draft.md`、`experiment_ch_5_4_mechanism_draft.md`、`conflict_type_distribution.md`、`experiment_chapter_outline_and_gaps.md`)的所有數字一律標 **PROVISIONAL(佔位)**,只提供敘事/結構骨架;`docs/handoff/EXPERIMENT_RUNLIST.md` 頂部已把「unified re-run」訂為 paper-final goal。

**Why:** 草稿數字混用不同 pipeline 版本 → reviewer 質疑公平性/可重現性;一次性統一重跑才能交叉比較、附 ±variance。
**How to apply:** 寫作時把骨架與數字分離,數字當佔位;真正要填表時,跑 EXPERIMENT_RUNLIST 的 Phase 1–3 那一輪 unified 結果。延伸自 [[feedback_research_rigor_pipeline_alignment]](baseline 對齊)、[[feedback_cheap_eval_during_validation]](judge model 另議);與 [[project_research_positioning]] 的寫作階段連動。
