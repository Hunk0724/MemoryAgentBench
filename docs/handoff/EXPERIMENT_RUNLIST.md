# 換機後實驗執行優先序(per-device runlist)

> 搭配 `CLAUDE.md`(環境/復現步驟)與 [RESEARCH_CONTEXT.md](RESEARCH_CONTEXT.md)。
> 全程:conda env `MABench`、**系統 backbone** gpt-4o-mini temp 0、embedding text-embedding-3-small、chunk 512、top-100。
> **LongMemEval 的 LLM judge**(官方預設 gpt-4o)驗證期暫用 **gpt-4o-mini** 省成本,**最終是否回 gpt-4o 未定**;**FC-SH 用 exact_match、無 LLM judge**。backbone 的 model sweep 方向往「更小」(weak-model,優先測比 gpt-4o-mini 小者),非往 gpt-4o。

## ★ Paper-final 數字 = unified re-run(嚴謹性鐵則)

**論文最終的每個數字,都必須出自「同一台穩定機器、同一份定版 pipeline、完全相同設定(同 backbone / chunk / top-k / judge 決策 / seed 規則)」下的一次性全矩陣重跑——所有方法 × 所有長度 × 兩 benchmark。** 不可混用本機研究演進過程累積的既有數字(那些跨時間、跨中途設定,如 64k overall 曾 65→94)。`paper_draft&materials/experiment_chapter_draft.md` 等草稿的數字皆為 **PROVISIONAL 佔位**,只供敘事/結構;跑完 unified re-run 後才逐格替換為 paper-final。→ 換言之,下面 Phase 1–3 跑出的這一輪結果,才是論文要用的那一份。

## 執行原則(為什麼是這個順序)

**「方法路徑」優先於「長度廣度」。** 一個方法只要在**某一個長度**(取最小的 6k)從零 clone 跑通,就證明該方法的整條管線(extraction→write→retrieve→resolve→EM)在這台機器上 OK;那麼 **32k / 64k / 262k 理論上只是換資料長度、必然也行**。所以:

1. 先讓**一個方法 ×一個長度(6k)** 跑通 → 這同時是 **migration proof**。
2. 同方法**擴長度** 32k→64k→262k(失敗多半是 OOM / rate-limit / 磁碟,不是邏輯)。
3. 一個方法全長度過了,**才換下一個方法**。
4. 所有「方法 × 長度」主結果補齊後,**才進延伸**(ablation / weak-model / case study)。

**相依性鐵則(復現必知)**:held-fixed baseline(`b`、`ours_struct`)會**重用 `ours` 的 extraction cache**(`extraction_cache_p1_<L>.json`)→ **同一長度一定先跑 `ours`,再跑 `b` / `ours_struct`**。

---

## Phase 0 — 管線/環境驗證(= migration proof,第一個關鍵檢查)

- [x] **FC-SH `ours` 6k ✅ 已通過(2026-06-30,Windows + Mac Studio 兩台從零 clone)**:
  `RUN_OAI_KEY_NAME=OPENAI_API_KEY_A bash docs/0615_intro_framework_after_problem_statement/scripts/run_fc_sh.sh 6k ours`
  - 從**全新 clone**(無任何 store/cache)會自動下載 FC 資料 + 重 ingest + query。
  - **對照目標(temp 0,容許 ±2–3)**:has_pair **68/74**、overall **92/100**。
  - 實測:Windows has_pair 67/74、overall 92/100;Mac has_pair 69/74、overall 94/100 → 全鏈遷移成功。
  - **實測 runtime(6k)**:ingest ~6–8min(~31s/chunk × 12)+ query ~44–45min(~27s/q × 100,**query 為瓶頸**,每題多次 LLM 解析)≈ 全程 ~50–54min。→ **32k/64k 會更久,規劃 ablation 時間時參考**(下方 Phase 3 #7 估 32k 各 ~1.5hr)。

## Phase 1 — FC-SH 主結果(逐方法;每方法先 6k 再擴長度)

> 跑法一律 `run_fc_sh.sh <L> <method>`,`<L> ∈ {6k,32k,64k,262k}`。可用不同 `RUN_OAI_KEY_NAME`(A..E)平行跑不同長度避免 rate-limit 撞車。

1. [ ] **ours**:6k(Phase 0 已) → 32k → 64k → 262k
2. [ ] **vanilla**(stock mem0:native extraction + destructive update):6k → 32k → 64k → 262k
3. [ ] **b**(held-fixed P1 + mem0 destructive;隔離 write-time-update loss):**每個長度需先有對應 `ours` 的 cache** → 6k → 32k → 64k → 262k
4. [ ] **LCA**(gpt-4o-mini full-context 上界):各長度(走自己的路徑)
5. [ ] **Zep**:`run_zep_fc.sh` / `run_zep_query_only.py` 各長度。**注意**:chunk512 對 Zep 可能不利 → 之後補 **Zep@4096** 公平對照。

## Phase 2 — LongMemEval(KU,personal facts)

> 資料:`xiaowu0162/longmemeval-cleaned` 的 `longmemeval_s_cleaned.json` + oracle 放 `data/longmemeval/`。官方 judge 已 vendor 進 repo(`llm_based_eval/evaluate_qa_official.py`)。

6. [ ] **ours LME-KU**(已完 83.3%,可重驗) → **baselines**:vanilla/mem0、**Zep**(smoke 過、resume full)。跑法:`run_lme_ku.sh` / `run_lme_ku_parallel.sh`、Zep 走 `run_zep_lme_*.sh`。

## Phase 3 — 論文核心延伸(對應 RESEARCH_CONTEXT 第 4 節 next-step 1–5)

7. [ ] **Ablation:structural-only**:`run_fc_sh.sh <L> ours_struct` vs `run_fc_sh.sh <L> ours`,比 has_pair EM → 驗證 structural 貢獻(next-step #1,**最優先的延伸**)。
8. [ ] **Weak-model regime**:Gemma-3-4B(small)→ mid model(先確認 RTX 4050 / Mac Studio 跑得動 local model;需另接 vLLM/Ollama/transformers + 權重)。
9. [ ] **Prior-work 失敗 case study**:qid29 起,手動分析 mem0 / Zep 失敗 case。
10. [ ] **完整 component ablation**:量化 identity grouping / conflict-type / temporal 各自貢獻。
11. [ ] **FC-MH**(多跳):跑 FactConsolidation multi-hop。

---

## 不需要做 / 不要重建

- `outputs/rag_retrieved/NV-Embed-v2/*`、**HippoRAG-v2**(已不跑,已從 git 移除)。
- 大檔(qdrant stores ~2G、p1_caches、logs)**不在 git** → 首跑自動重生,**勿手動還原**。
- `requirements-core.txt`(釘版、純 Python 跨平台)安裝即可;**不要**用 `requirements.txt`(含 flash_attn/deepspeed/faiss-gpu,Windows/無 GPU 會編譯失敗)。
