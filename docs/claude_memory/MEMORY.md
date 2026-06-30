# MEMORY INDEX

- [回覆語言偏好](feedback_language.md) — 所有回覆一律使用繁體中文
- [跨系統評估必須先 pipeline 對齊](feedback_research_rigor_pipeline_alignment.md) — bare vs aligned 不對齊 baseline 是論文大忌,事前必驗證 query template + agent_name normalize
- [執行前先確認設計](feedback_confirm_before_execute.md) — 跑測試/執行前先講清楚改動+理由、等使用者確認再動手,別自行開跑
- [Phase 0/2 結構+LLM 分群 KU](project_phase0_structural_result.md) — 0615 主軸**定版(0626)**:P1抽取+保守寫入+(S,P)結構+LLM分群+conflict-type+raw-q檢索+batch-emb;FC-SH 32k EM 89%/has_pair 86%;Path B 不需要(retrieval瓶頸=wrapped-query artifact);方法階段性定版→轉做 baseline三層+廣度;temporal key正確(q8/q9是benchmark標註錯誤非我方);目錄改名 paper_draft&materials
- [KU 分類與戰場定錨](project_ku_taxonomy_battlefield.md) — 0623:KU 分 A明確更正(MemBench,出界)/B newer-wins(FC主+LongMemEval/BEAM泛化);我們=B;keep-all 必要因同store要答temporal;extraction 當正交前提,doc 在 writing_draft/ku_taxonomy_and_scope.md
- [驗證期用便宜模型評估](feedback_cheap_eval_during_validation.md) — judge/eval 驗證階段用 gpt-4o-mini,確認 pipeline 後、進論文前 LongMemEval 的評估才用正式 gpt-4o 重跑
- [LongMemEval Mode B 歷史值失敗模式](project_longmemeval_modeB_historical.md) — 0627:ours LME-KU 83.3%;Mode B(題目要歷史/舊值或新舊雙值,oracle 驗證真設計如此)被 freshness 丟舊→必錯;keep-all 最強論證,只記錄不實作、未來 case study
- [指導教授畫圖規範](feedback_figure_design_advisor.md) — 0628:用 matplotlib/seaborn/SciencePlots/plotnine(非 Excel/HTML);黑白可讀為主、少用色;長字縮寫+caption 註明;bar 不佳(趨勢用 line、無趨勢用 table、不用 pie)
