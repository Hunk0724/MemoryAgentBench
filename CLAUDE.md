# CLAUDE.md — 專案脈絡與工作規則(Claude Code 自動載入)

> 換機器後新的 Claude Code session 會自動讀這份。完整個人記憶備份在 `docs/claude_memory/`。

## 語言
- **所有回覆一律繁體中文(台灣資工學術用語 + 領域英文術語)。**

## 研究主題(一句話)
碩論:在 mem0 上的 **Knowledge Update (KU) 記憶框架**,主張 **KU 是 query-time 問題,而非 write-time 的 commitment**。評測於 **MemoryAgentBench(ICLR'26)FC-SH**(general fact)與 **LongMemEval(ICLR'25)KU**(personal fact)。

## 核心理念(method)
過去記憶系統在 **write-time commit KU**,一旦 LLM 誤判即**不可逆刪掉正解**。我們 **defer KU 到 query-time**,三個 commitment:
1. **Faithful / conservative write**:忠實抽取所有 fact、保留全版本、write 時不做跨筆 LLM 判斷。
2. **Query-time KU resolution**:衝突只在 query 時解(query-aware)。
3. **Decomposed, simple LLM tasks**(for weak model):raw-question retrieval → identity grouping((S,P) 結構 + LLM)→ 3-way conflict-type → 確定性 temporal(僅 FRESHNESS 取最新)。

## 目前進度(2026-06-28)
- **FC-SH 機制+結果已立穩**:ours has_pair 86–92% flat(6k→262k),贏 mem0/Zep/long-context。
  - 機制證據:write-time 不可逆性(L0 庫缺新版、L0==L1 → 非檢索問題)、recall-ceiling vs EM 兩道關卡、both→new_only resolution、additive ablation。
  - **核心現象**:FC-SH conflict-type 97% freshness → **structural (S,P)+temporal 是 workhorse**;conflict-type 是給 LongMemEval 多值個人事實(complementary 29%)用的。
- **LongMemEval**:ours KU 83.3%(gpt-4o-mini judge),泛化已驗證;**baselines(mem0/vanilla/Zep)full run 尚未完成**(smoke 過、可 resume)。Mode B(問歷史/雙值)強化 keep-all,列 future work。
- **Fairness audit 已做**:metric/template/GT/baseline-prompt 全未動;chunker(fact-aware, FC-only, uniform)+ raw-q retrieval(ungated)+ gen_max 256 是 uniform 合理 deviation;**唯一 flag = chunk_size 512 對 Zep 可能不利 → 建議補 Zep@4096**。

## 工作規則(來自累積回饋)
- **執行前先確認設計**:跑實驗/重要改動前先講清楚改動+理由,等確認再動手。
- **驗證期用便宜模型**:judge/eval 先用 gpt-4o-mini,確認 pipeline、進論文前才用 gpt-4o 重跑。
- **跨系統評估必先 pipeline 對齊**(raw-q retrieval ungated、同 chunker);baseline 不對齊是論文大忌。
- **圖面精簡**:figure 只留 axis/legend/data label,判讀寫進 caption(三段論 what/observation/implication)。頂會用 line/bar、不用 pie(pie 留簡報)。
- rigor:不腦補、先查證據(q8/q9 標註錯誤的教訓)。

## 關鍵位置
- 方法:`methods/phase0_*.py`、`methods/phase2_query.py`;入口 `agent.py`(`_handle_mem0_agent`、`_retrieval_query`);寫入 `mem0/memory/main.py`。
- 論文材料:`docs/0615_intro_framework_after_problem_statement/paper_draft&materials/`(experiment_results.md、paper_tables_and_figures.md、conclusion_and_next_step.md、ku_taxonomy_and_scope_zh.md)。
- 圖 + caption:`docs/0615_.../figures_current/`(make_*.py + figure_captions.md)。
- run/分析 scripts:`docs/0615_.../scripts/`(run_fc_sh.sh、run_lme_ku*.sh/py、l0_bank_state.py、state_extractor.py、make_*.py)。

## 環境
- conda env **MABench**;API model **gpt-4o-mini temp 0**、embedding text-embedding-3-small;chunk **512**、top-**100**。
- `.env`(不進 git)放 OPENAI_API_KEY_A..E、ZEP_API_KEY_A/B 等;換機器需重建。
- 大檔(qdrant stores 2G、outputs、p1_caches)**不進 git** → 需要時重跑;已存的分析 JSON(analysis/results/phase0/、sh_*_mquake_analysis.json)與 figures 已 commit,圖可直接重生。

## 換機器後的重建步驟(reproduce)
1. `git clone -b exp/v2-llm-judge https://github.com/Hunk0724/MemoryAgentBench.git && cd MemoryAgentBench`
2. `conda create -n MABench python=3.10 -y && conda activate MABench && pip install -r requirements.txt`
   - repo 內含 patched `mem0/`(本地目錄,從 repo 根目錄執行時會覆蓋 pip 的 mem0ai)→ 我們的寫入/抽取改動隨 git 走,不需另裝。
3. 建 `.env`(不在 git):`OPENAI_API_KEY_A`..`E`、`ZEP_API_KEY_A`/`B`。
4. 資料:FC 由 `datasets` 自動抓 HF `ai-hyz/MemoryAgentBench`;LongMemEval 需手動下載 `xiaowu0162/longmemeval-cleaned` 的 `longmemeval_s_cleaned.json`/`oracle` 到本機 data 夾。
5. **⚠ 路徑可攜性**:`docs/0615_.../scripts/*.sh`、`run_longmemeval_ku.py`、`l0_bank_state.py` 等內有 **hardcoded `/home/yhchiang/...` 絕對路徑**(repo 與 LongMemEval data 位置)→ 新機器需 sed 改成新路徑(或在新家目錄建同名結構)。
6. **最快驗證(不需重 ingest)**:`python docs/0615_.../scripts/make_bank_recall.py` 等 `make_*.py`(讀已 commit 的 `analysis/results/phase0/*.json`)→ 圖重生 = python/matplotlib/資料檔 OK。
7. **全鏈驗證(需 API key)**:`RUN_OAI_KEY_NAME=OPENAI_API_KEY_A bash docs/0615_.../scripts/run_fc_sh.sh 6k ours` 跑小量 → 確認 mem0+openai+qdrant 接線。stores/caches 不在 git → 首跑會重新 ingest。

## 下一步(優先序)
- **P0**:LongMemEval full baselines(resume)+ all-in-one-call ablation(證 decomposition 的貢獻)。
- **P1**:qid29 case study、weak-model × method dose-response、gpt-4o judge 重跑。
- **P2/future**:query-aware resolver(Mode B)、retrieval-at-scale、Zep@4096、多 seed。
