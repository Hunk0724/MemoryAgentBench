# Repo 檔案盤點 — Active / Reference / Stale(2026-06-28)

> **判準建議:用「角色(role)」而非「2 週 mtime」。** 因為很多**必用但很久沒改**的檔(`agent.py`、`conversation_creator.py`、`utils/`、patched `mem0/`)mtime 都很舊,純 mtime 會誤殺;反之舊研究線(`docs/0612`)最近才動過卻已非主軸。所以下面按「是否為近期研究實際會用到」分類。

## ✅ ACTIVE — 現役,務必保留(不論 mtime)
- **Benchmark 核心**:`agent.py`、`main.py`、`conversation_creator.py`、`initialization.py`、`utils/`(eval_other_utils / eval_data_utils / templates)
- **patched mem0**:`mem0/`(整個目錄;import 會載這個)
- **我們的方法**:`methods/phase0_triple_extractor.py`、`methods/phase2_query.py`、`methods/cost_logger.py`、`methods/phase0_query.py`、`methods/zep.py`
- **現役 configs**:`configs/.../mem0_512_openai_{unified,unified_dest,native,unified_struct}.yaml`、zep yaml、data_conf/Factconsolidation_*
- **主研究線**:`docs/0615_intro_framework_after_problem_statement/`(paper_draft&materials、figures_current、scripts 的 make_*/run_fc_sh/run_lme_ku*/run_zep_lme_*/l0_bank_state/state_extractor/run_longmemeval_ku/zep_lme_*/current_figures/e4)
- **遷移/復現**:`CLAUDE.md`、`requirements-core.txt`、`llm_based_eval/evaluate_qa_official.py`、`docs/claude_memory/`、`analysis/results/phase0/*.json`、`analysis/results/sh_*_mquake_analysis.json`

## 📚 REFERENCE — 舊但仍引用,保留勿刪
- `docs/0612_research_method_improve_with_evidence/`(**qid29 case study**、U5 設計;next-step #3 會用)
- `docs/0603_current_research_main_evidence/`(早期 mem0 失敗拆解證據,部分仍引用)

## 🗄️ STALE-candidate — 可封存(分兩類)
**(a) 安全可搬**(純 docs/舊腳本/舊 yaml,沒有被 import):
- `bash_files/`(0531,舊 run script,已被 0615/scripts 取代)
- `docs/current_focus/`(0511)、`docs/paper_draft/`(0603,被 0615/paper_draft&materials 取代)、`docs/ground_truth/`(0528)
- 舊 mem0 yaml 變體:`configs/.../mem0_l2_*.yaml`、`*_rerun*.yaml`、`*_u5*.yaml`(9 支,被 unified/dest/native 取代)
- 舊分析腳本:`docs/0615_.../scripts/analyze_*.py`、`make_figures.py`(5 支,被 make_* 取代)

**(b) 風險較高,先別搬**(是 code、會被 agent handler lazy-import,雖然我們不跑):
- `cognee/`(550 檔,0406)、`methods/hipporag/`(66 檔,0530)、`outputs/rag_retrieved/NV-Embed-v2/*`(已移除)
  → `agent.py` 的 `_handle_hippo_rag`/`_handle_cognee` 會 import 它們;**只有跑那些 baseline 才會載入**(我們不跑)。搬走前要確認沒有 top-level import,否則 `import agent` 可能壞。

## 建議流程(低風險優先)
1. **現在**:只刪確定沒用的(MIGRATION.md ✓);其餘**先留清單、不大搬**——repo 能跑,clutter 無害。
2. **要整理時**:把 (a) 類搬到 `_archive/`,搬完跑一次 `run_fc_sh.sh 6k ours` 確認沒壞。
3. (b) 類(cognee/hipporag)**保留**或最後處理:它們是 benchmark fork 的一部分,搬走的好處小、風險大。
