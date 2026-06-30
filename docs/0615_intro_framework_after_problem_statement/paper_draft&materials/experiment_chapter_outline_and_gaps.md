# Experiment 章節:Outline + Gap Analysis(2026-06-30 蒸餾)

> ⚠️ **數字嚴謹性原則**:此 roadmap 引用與 `experiment_chapter_draft.md` / `experiment_ch_5_4_mechanism_draft.md` 的數字皆為 **PROVISIONAL**(本機演進過程既有結果)。**論文最終所有數字必須由穩定機器在定版統一 pipeline + 同一設定下重跑全矩陣取代**(見 `EXPERIMENT_RUNLIST.md` 的 unified re-run)。「[完整可寫]」指**結構/敘事**可寫,**非數字 paper-final**。
>
> 本 session 用多 agent 盤點全 repo 後產出。**method 章已有材料,experiment 章尚未組裝**;此檔是組裝 roadmap。標記:**[完整可寫]**=既有 committed 材料足夠寫結構;**[阻塞:需跑]**=卡在未跑的實驗;**[部分]**=主體有、補強待跑。
> 路徑基準 `docs/0615_intro_framework_after_problem_statement/`;`P&M/` = `paper_draft&materials/`。

## 1. 已有(現成可用,多數靠 committed data)

**主結果 / ablation / cost(§5.2 / §5.5 / §5.7)**
- **Table 1 主結果** FC-SH has_pair EM:ours 92/86/91/88%(6k/32k/64k/262k)flat,LCA 88→71→55→31% 崩塌。`P&M/paper_tables_and_figures.md:9-17`;原始 `analysis/results/phase0/l3_state_em.json`(committed)。
- **Table 2 additive ablation**:(a) native 0/3% →(b) mem0+P1 extraction 46/45% →(c) ours 92/86%。`P&M/paper_tables_and_figures.md:23-30`。
- **Table 3 latency**:ours 262k M.C.=4.7hr 實測;Q.E. ~27–36s/q。`P&M/experiment_results.md:98-121`。

**機制 evidence chain(§5.4,全 deterministic、不靠 LLM judge → 最強且最穩)**
- E-L0 write-time irreversibility:ours bank recall 100/98/95/92% vs mem0+P1 51/49/41%、vanilla 0%;**L0==L1 證明 loss 在 write 非 retrieval**。`figures_current/F_bank_recall`;`analysis/results/phase0/{l0_bank_state,l1_retrieval_eval,l2_resolution_eval,state_eval_current}.json`(committed)。
- E-L1/L2 resolution:both 92–100% → new_only 70–86%;E4 state→EM(new_only 95% / both 66% / old_only 2% / neither 6%)。`F_ours_L1L2_pie`、`F_state_to_em`。
- Error-mode 診斷:retrieval-caused EM=0、method-caused 5–7/length、benchmark label error 0–2。`P&M/experiment_results.md:64-93`(committed)。
- **conflict-type 跨 benchmark 對比**:FC freshness 85→98%、LME complementary 29% → **已 freeze 進 `P&M/conflict_type_distribution.md`**(來源 cache 為 gitignored,已搶救)。

**Setup / scope(§5.1)**:metric 來源已驗(FC-SH=DRQA exact_match `utils/eval_other_utils.py:91-102`,**非 LLM judge**;LME=官方 judge `llm_based_eval/evaluate_qa_official.py`);baseline 定義 `P&M/experiment_plan.md:23-51`;reproducibility=migration proof(Win+Mac)+ fairness audit。

**圖**(PNG+PDF 已 render,committed):`figures_current/F_{robust_haspair,overall,ablation,bank_recall,recoverable,em_vs_ceiling,L1_state_pie,ours_L1L2_pie/bar,state_to_em}`;caption `figures_current/figure_captions.md`;生成 script 全在 `P&M/scripts/`。

## 2. 缺口

| 缺口 | 類型 | 備註 |
|---|---|---|
| structural-only ablation(`ours_struct`) | **[需跑]** | `analysis/results/` 內**無** `*struct*` 結果檔(已查證)。**approved priority #1**;6k cache 已在 → 跑最快。 |
| LongMemEval baselines(mem0/vanilla/Zep×78) | **[需跑]** | **無 LME baseline 結果檔**(只有 ours)。「dataset 2 也贏」的硬阻塞。 |
| 官方 gpt-4o judge 重跑(LME;**是否做未定**) | **[需跑]** | 現 gpt-4o-mini。**注意:回 gpt-4o 是選項非既定**;FC-SH 無 judge 不受影響。 |
| weak-model dose-response(往比 gpt-4o-mini **更小**) | **[需跑]** | intro narrative 的核心證據,目前零數據。 |
| Zep@4096 fairness 補測 / 多 seed variance / 262k 補格(mem0+P1、Zep) | **[需跑]** | |
| FC-MH 整合(部分 `mh_*` 檔已在) | **[需跑/整理]** | |
| qid29 case study(mem0 write-time destructive 質化) | **[只需寫]** | 從既有 store dump 寫;但 store 是 gitignored → 若要做趁本機。 |
| figure caption audit(舊 caption 是否仍引用 old L2+wrapped-q) | **[只需寫]** | |

## 3. 建議章節 outline(每節標可寫性)

- **5.1 Setup** [完整可寫] — benchmarks / metrics / models / baselines / reproducibility。caveat:judge 現 gpt-4o-mini,是否回 gpt-4o 未定。
- **5.2 FC-SH Main Results** [完整可寫] — Table 1 + F_robust_haspair + F_overall。narrative:ours flat vs LCA collapse(262k gap +57pp)。缺角:mem0+P1/Zep 的 262k 格。
- **5.3 LongMemEval Generalization** [部分] — ours 83.3% 可寫 + conflict-type 對比(已 freeze)可寫;**baseline 全缺 → 誠實標待補**。
- **5.4 Mechanism Analysis** [完整可寫] **✅ 已草擬全文 → `experiment_ch_5_4_mechanism_draft.md`**(E-L0 → E-L1/L2 → E-ceiling → E4 → error-mode,全 committed-data backed)。補強(可選):qid29 case study [只需寫,store 為 gitignored → 趁本機]。
- **5.5 Ablation** [部分] — additive(a→b→c)[完整可寫];structural-only / component-level [阻塞:需跑]。
- **5.6 Weak-Model Regime** [阻塞:需跑] — 視機器算力決定獨立小節或併 limitations。
- **5.7 Cost / Latency** [完整可寫] — Table 3:write-time cost ↔ query accuracy 換算。
- **5.8 Limitations & Future** [只需寫] — Mode B resolver、FC-MH、多 seed、Zep@4096、gpt-4o judge。`P&M/conclusion_and_next_step.md`。

## 4. 立即可 distill(零新實驗,靠 committed data)

優先寫死(資料都在 git,不依賴未來重跑):**§5.4 機制章全文、§5.2/5.5-additive/5.7 三表、§5.3 conflict-type 對比段、error-mode 表**。
已搶救(本機 gitignored 來源):**conflict-type 分佈 → `P&M/conflict_type_distribution.md`**(done)。
若要做 qid29 case study:**趁本機**(store dump 是 gitignored)。

**硬阻塞、必須有算力才做**:structural-only/component ablation、LME baselines、(可選)gpt-4o judge、weak-model、Zep@4096、多 seed、262k 補格。

> 一句話:機制章 + 三表 + conflict-type 對比可現在用 committed data 寫死;LME baselines 與 structural-only ablation 是兩個硬阻塞,確認過無結果檔,須等有算力時重跑。
