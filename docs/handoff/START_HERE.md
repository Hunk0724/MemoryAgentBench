# START HERE — 新機器 / 新 session 開工指引

> 這份就是「貼進全新 Claude Code session 的 prompt」。新 session 一進來請先讀這份(CLAUDE.md 已指向),依序同步並開工。

---

你接手一個**進行中的碩論專案**(repo `MemoryAgentBench`,branch `exp/v2-llm-judge`)。研究主題:在 mem0 上的 **Knowledge Update (KU) 記憶框架**,主張「**KU 是 query-time 問題,不是 write-time 的 commitment**」。請依下列順序同步並開工。

## 0. 先同步到最新
- `git pull`(branch `exp/v2-llm-judge`;最新 commit 至少到「Migration proof PASSED…」`68292bc`)。
- `conda activate MABench && pip install -r requirements-core.txt`
  - 這版**新增 4 個主路徑必裝套件**:`torch / transformers / langchain-core / editdistance`(`agent.py`、`utils/eval_other_utils.py` 頂層 import,API-only 也需要;torch CPU build 即可)。
  - 裝完跑 `pip freeze | grep -iE 'torch|transformers|langchain-core|editdistance'`,把**確切版本釘回** `requirements-core.txt` 並 commit(目前那 4 行未釘版)。

## 1. 先讀(建立脈絡,務必先讀再動手)
- `CLAUDE.md` — 自動載入:語言規則、研究主張、方法、環境、復現步驟、**migration proof 已過 + 換機兩個雷**。
- `docs/handoff/RESEARCH_CONTEXT.md` — 主張 + 目前成果 + **★研究定位難題(目前最缺的是 framing,不是實驗)** + 下一步 1–5。
- `docs/handoff/EXPERIMENT_RUNLIST.md` — 實驗執行優先序(方法路徑優先於長度廣度)。
- `docs/handoff/competitive_landscape_agentic_memory.md` — agentic memory 生態 + 正交性判讀(定位用)。

## 2. 現況一句話
方法已**定版**;FC-SH 機制+結果**立穩**(ours has_pair **86–92% flat** 6k→262k,贏 mem0/Zep/long-context);LongMemEval KU **83.3%**;**migration proof 兩台(Windows + Mac Studio)從零 clone 已過**。缺的不是「實驗能不能跑」,而是 **(a) 補齊 baseline 廣度、(b) 驗證核心主張的 ablation、(c) 研究定位 framing**。

## 3. 立即要做(已 approved 的下一步:優先序 #1)
**structural-only ablation** —— 驗證「表現是否主要來自 structural 貢獻」(對照證據:FC-SH conflict-type 97% freshness,structural 很可能就是 workhorse)。
- **先 6k 拿快速訊號**(6k `ours` 的 P1 cache 在 proof 時已產生):
  `bash docs/0615_intro_framework_after_problem_statement/scripts/run_fc_sh.sh 6k ours_struct`
  → 比對 `6k ours` 的 **has_pair EM**(`ours_struct` = 同保守寫入,但 query 只走 `(S,P)` group + 確定性 temporal,關掉 LLM grouping + conflict-type)。
- **再跑 32k headline**:先 `run_fc_sh.sh 32k ours`(建 cache,~1.5hr)→ 再 `run_fc_sh.sh 32k ours_struct`(~1.5hr)。
- **鐵則**:同長度**先 `ours` 再 `ours_struct`**(後者重用前者的 `extraction_cache_p1_<L>.json`)。
- **結果出來才決定怎麼 claim**(structural 是否就是主要貢獻)。

## 4. 之後(依 #3 結果決定順序)
- 補 **Phase 1 baseline 廣度**(`vanilla` / `b` / `LCA` / `Zep` × 各長度)、**Phase 2 LongMemEval baselines**(mem0/Zep,可 resume)。
- next-step **#2** weak-model regime(Gemma-3-4B → mid model)、**#3** prior-work 失敗 case study(qid29 起)、**#4** 完整 component ablation、**#5** 寫作 framing(**連動研究定位難題**,協助挑對 baseline/文獻)。

## 工作規則(務必遵守)
- **全程繁體中文**(台灣資工學術用語 + 領域英文術語)。
- **執行前先確認設計**:跑實驗 / 重要改動前,先講清楚「改什麼 + 為什麼」,等我確認再動手,別自行開跑。
- **驗證期用便宜模型**:judge/eval 先用 **gpt-4o-mini**,確認 pipeline、進論文前才用 **gpt-4o** 重跑。
- **跨系統評估先 pipeline 對齊**(raw-q retrieval ungated、同 chunker);不動 metric / query template / GT / baseline prompt。
- **圖表規範**:matplotlib / seaborn / SciencePlots / plotnine(不要 Excel/HTML);黑白可讀為主;長字縮寫 + caption 註明;bar 不佳 → 趨勢用 line、無趨勢用 table、不用 pie。
- **rigor**:不腦補、先查證據。
- **安全**:不要讀 / grep `.env`。

## 5. 收尾待辦(背景知道即可)
- 確認 `exp` 一切正常後,可 `git merge cleanup/archive-stale`(把 462 檔 stale 封存效果併入,工作樹更乾淨;該分支是 fallback,封存全用 `git mv` 可還原)。
