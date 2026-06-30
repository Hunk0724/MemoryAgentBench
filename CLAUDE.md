# CLAUDE.md — 專案脈絡與工作規則(Claude Code 自動載入)

> 換機器後新的 Claude Code session 會自動讀這份。完整個人記憶備份在 `docs/claude_memory/`。

## ★ 換機後優先讀(handoff,接續本研究脈絡)
- [`docs/handoff/START_HERE.md`](docs/handoff/START_HERE.md) — **新 session 第一份讀這個**:同步步驟 + 現況 + 已 approved 的下一步(structural-only ablation)+ 工作規則。
- [`docs/handoff/RESEARCH_CONTEXT.md`](docs/handoff/RESEARCH_CONTEXT.md) — 研究脈絡 + 目前成果 + **最關鍵的「研究定位」難題** + 下一步 1–5。**續談實作/寫作前先讀。**
- [`docs/handoff/EXPERIMENT_RUNLIST.md`](docs/handoff/EXPERIMENT_RUNLIST.md) — 換機後實驗執行優先序(方法路徑優先於長度廣度;6k 先跑通即代表該方法可擴各長度)。
- [`docs/handoff/competitive_landscape_agentic_memory.md`](docs/handoff/competitive_landscape_agentic_memory.md) — agentic memory 生態盤點 + 正交性判讀(定位用)。
- **我現在最缺的不是實驗,是「不知道怎麼定位研究」**(KU 窄題 vs 一堆 memory 大題/平台、比較對象太少)→ 見 RESEARCH_CONTEXT 第 3 節,協助 framing 與選對 baseline/文獻。

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
- **圖表規範(指導教授)**:畫圖用 **matplotlib / seaborn / SciencePlots / plotnine**(**不要 Excel、不要 HTML output**);**黑白印出來也要清楚**(少用色,靠 linestyle/marker/hatch/灰階);長字用**縮寫**+ caption 註明 `(xx stands for ...)`;**bar 不是好圖** → 有趨勢用 **line**、無趨勢用 **table**、不用 pie(pie 留簡報)。圖面精簡(只留 axis/legend/data label),判讀寫進 caption(三段論 what/observation/implication)。
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
2. `conda create -n MABench python=3.10 -y && conda activate MABench && pip install -r requirements-core.txt`
   - **用 `requirements-core.txt`(精簡+釘版,純 Python 跨平台)**,不要用 `requirements.txt`(含 flash_attn/deepspeed/faiss-gpu,Windows/無 GPU 會編譯失敗,且只給已停用的 HippoRAG/NV-Embed 用)。
   - repo 內含 patched `mem0/`(本地目錄,從 repo 根目錄執行時會覆蓋 pip 的 mem0ai)→ 寫入/抽取改動隨 git 走,不需另裝。
   - **torch / transformers / langchain-core / editdistance 是主路徑頂層 import**(`agent.py:3,13,14-15`、`utils/eval_other_utils.py:15`)→ **API-only 也必裝**,已列入 `requirements-core.txt`(torch CPU build 即足夠;**不是** weak-model 才裝)。
   - **local Gemma(weak-model)才另裝**:bitsandbytes / Ollama(各裝置自己裝對版本;vLLM 在 Windows 需 WSL2),並把 torch 換成對應 CUDA/Metal build。
3. 建 `.env`(不在 git):`OPENAI_API_KEY_A`..`E`、`ZEP_API_KEY_A`/`B`。
4. 資料:FC 由 `datasets` 自動抓 HF `ai-hyz/MemoryAgentBench`;LongMemEval 需手動下載 `xiaowu0162/longmemeval-cleaned` 的 `longmemeval_s_cleaned.json`/`oracle` 到 `data/longmemeval/`。**官方 judge 已 vendor 進 repo**(`llm_based_eval/evaluate_qa_official.py`,= 我們實際用的那支)→ judge 也不依賴外部。
5. **路徑可攜性(已處理)**:`docs/0615_.../scripts/` 的核心 `*.sh`/`*.py` 與 mem0/zep yaml 已改成 **env 變數帶預設**——`REPO_ROOT` 由 `$(dirname $0)/../../..` 或 `__file__` 自動推、conda 用 `$HOME/miniconda3`、store path 改 relative。換機**通常零改**;若 conda 不在 `$HOME/miniconda3` 或 LME data 放別處,設 `CONDA_SH=` / `LME_DATA_DIR=` 覆蓋即可。(舊 `analyze_*`/`make_figures.py` 等次要腳本仍有寫死路徑,要用再改。)
6. **最快驗證(不需重 ingest)**:`python docs/0615_.../scripts/make_bank_recall.py` 等 `make_*.py`(讀已 commit 的 `analysis/results/phase0/*.json`)→ 圖重生 = python/matplotlib/資料檔 OK。
7. **全鏈驗證(需 API key)**:`RUN_OAI_KEY_NAME=OPENAI_API_KEY_A bash docs/0615_.../scripts/run_fc_sh.sh 6k ours` 跑小量 → 確認 mem0+openai+qdrant 接線。stores/caches 不在 git → 首跑會重新 ingest。

### ★ Migration 驗證 proof(換機後第一個關鍵檢查)
從**全新 clone**(無任何 store/cache)跑 `RUN_OAI_KEY_NAME=OPENAI_API_KEY_A bash docs/0615_.../scripts/run_fc_sh.sh 6k ours`(會自動下載 FC 資料 + 重 ingest + query)→ 算 **has_pair EM**,對照已 commit 的目標 **6k ours = has_pair 68/74、overall 92/100**(temp 0 高度確定,容許 ±2-3)。**跑通且數字吻合 = pipeline(code+env+data+keys+qdrant)完整轉移成功。**

- **✅ 已通過(2026-06-30,兩台從零 clone)**:Windows(i7-13700H/RTX4050)has_pair **67/74**、overall **92/100**(~54min,query 為瓶頸);Mac Studio(M2 Ultra)has_pair **69/74**、no_conflict **25/26**、overall **94/100**(~50min,比 Linux 快 ~14%)。Δ1–2 全在 ±2-3 容許內(OpenAI server bf16 + batch embedding 微小非決定性,§3.3 已記錄)→ **全鏈遷移確認成功**。
- **換機兩個雷(已知,先排查)**:① `.env` 殘留**舊機 HF_* 變數**(指向不存在路徑)會卡 FC 資料載入 → `.env` 只留 API key,清掉 HF_*/SSL_CERT_FILE/*_CA_BUNDLE/路徑類。② **Windows conda 的 SSL_CERT_FILE**:`conda activate` 把它設成 Unix 佈局 `.../envs/MABench/ssl/cacert.pem`(不存在),真實檔在 `.../Library/ssl/cacert.pem` → httpx/openai 建 TLS 會炸;把憑證複製到期望路徑或修正 SSL_CERT_FILE 即可(與 `.env` 無關)。

### 執行順序 caveat（復現必知）
held-fixed baseline(`b`、`ours_struct`)會**重用 `ours` 的 extraction cache**(`extraction_cache_p1_<L>.json`)→ **同一長度必須先跑 `ours`、再跑 `b`/`ours_struct`**,否則 cache 不存在會重抽(雖仍可跑,但失去 held-fixed 一致性)。

### 近期實際在跑的方法(換機後要能重跑這些)
- **FC-SH**:`run_fc_sh.sh <L> <ours|vanilla|b>`(ours / mem0=vanilla / mem0+ours storage=b);**LCA(=gpt-4o-mini full-context)**、**Zep** 走各自路徑(`run_zep_fc.sh`/`run_zep_query_only.py`)。
- **LongMemEval**:`run_lme_ku.sh` / `run_lme_ku_parallel.sh`(ours 已完;baselines 待 resume);Zep-LME=`run_zep_lme_*.sh`。
- **不需要**:`outputs/rag_retrieved/NV-Embed-v2/*`、HippoRAG-v2(已不跑)→ 已從 git 移除、勿重建。
- **未來 local model(Gemma-3-4B,weak-model 主張用)**:目前全 API(gpt-4o-mini);跑 Gemma-3-4B 需另接 vllm/ollama/transformers + 模型權重(本地 RTX 4050 / MacStudio),屬 next-step、非現有環境。

## 下一步(優先序,2026-06-28 更新)
1. **驗證論文核心主張:表現是否主要來自 structural 貢獻** — 先做 **ablation(structural-only:`(S,P)` group + 確定性 temporal,關掉 LLM grouping + conflict-type)vs full phase2**,比 has_pair EM。**已備好腳本**:`run_fc_sh.sh <L> ours_struct`(query=structural、重用 ours 的 P1 cache → 寫入相同)vs `run_fc_sh.sh <L> ours`(phase2)。**結果出來才決定怎麼 claim**(對照證據:FC-SH conflict-type 97% freshness → structural 可能就是 workhorse)。
2. **驗證 weak-model regime 場景前提** — ours 與 baseline 在小模型下是否如預期(**ours 保持平緩、prior work drop**)。跑不同 model size:**Gemma-3-4B(small;先確認 RTX 4050 / MacStudio 能否跑此 local model)→ mid model(Gemma 中型,之後用 Google AI Studio API)**。
3. **找 prior work 的結構性失敗模式** — 手動分析 **mem0 / Zep 的失敗 case**(qid29 是起點:mem0 write-time 把新版刪掉留舊版)。
4. **強化 narrative:完整 ablation** — 量化**每個 component**(identity grouping / conflict-type / temporal)的貢獻。
5. **決定寫作方向** — 依上述結果定 framing;同步補 narrative 所需文獻。
6. **FC-MH 多跳** — 跑 FactConsolidation **multi-hop** 看多跳情況。

> 仍待補(來自 conclusion,視上面結果穿插):LongMemEval baselines(mem0/vanilla/Zep)full、gpt-4o judge paper-final、Zep@4096 公平對照、多 seed variance。
