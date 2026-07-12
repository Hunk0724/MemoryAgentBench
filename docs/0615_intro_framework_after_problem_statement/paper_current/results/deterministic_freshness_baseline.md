# Deterministic-freshness baseline (Reddy & Challaram 2026) — 公平比較

> **這是什麼**:與我方**思想最近的並行工作** *"Don't Ask the LLM to Track Freshness: A Deterministic Recipe for Memory Conflict Resolution"*(Reddy & Challaram, arXiv 2606.01435, 2026-05)當作 FC-SH 的直接對手。其方法 = **BM25 檢索 → LLM 抽候選 → Python `max(serial)`**(把 freshness 移出 LLM,交確定性 max)。
> **我們怎麼跑**:**直接 import 他們公開 repo 的程式碼**(`scripts/_pipeline.py` 的 `_extract_candidates`(逐字 CANDIDATE_PROMPT)+ `_freshness_pick`),跑在**我們的實驗設定**下。
> **provenance**:repo 已 vendor 於 [`../../related work/memory-conflict-resolution/`](../../related%20work/memory-conflict-resolution/)(MIT license;commit `b6b92b4`;`github.com/cvikasreddy/memory-conflict-resolution`)。driver:[`../../scripts/maxserial_theircode.py`](../../scripts/maxserial_theircode.py)。
> **日期**:2026-07-12。

---

## §1 公平設定(哪些一致、哪些用他們的)

| 面向 | 用誰的 | 說明 |
|:--|:--|:--|
| **candidate extraction prompt + resolution** | **他們(verbatim)** | import `_pipeline._extract_candidates` / `_freshness_pick` |
| fact bank | 我們 P1 抽取 | extraction-controlled(如 `b`)|
| freshness 信號 | 我們 ingestion **ordinal** | = context 序;驗證 new_ord>old_ord **62/62** 6k has_pair |
| 檢索 | 我們 raw-q **vector top-100**(text-embedding-3-small)| = ours 檢索;**recall 非瓶頸**(BM25 top-10 對 gt_answer recall 已 74/74=100%)|
| metric | 我們**官方 overall-100 SubEM** | `default_post_process`(experiment.md §4.1.4)|
| backbone | `PIPELINE_MODEL` | 抽取 LLM = 我們 backbone |

→ **唯一差異 = identity-resolution 機制**(他們 LLM-extract+max vs 我們 (S,P)+argmax)。

**忠實度驗證(重要)**:用他們 code + BM25 top-10(as-designed)跑,得 **overall 71% / has_pair 46/74(62.2%)/ leak 27/28**——**與他們釋出的 `poc_results` 每題數字一模一樣**(逐題 n_candidate 分布、leak 皆同)→ 整合忠實。

---

## §2 結果(FC-SH 6k × gpt-4o-mini,overall-100 官方 SubEM)

| Method | overall | has_pair | 說明 |
|:--|:--:|:--:|:--|
| **ours (main)** | **94%** | ~93% | (S,P) struct + argmax |
| Zep | 82% | — | decoupled write-time labeling |
| **作者 (extract+max)** — **公平版** | **80%** | **73.0% (54/74)** | 他們 code × 我們 vector top-100 |
| 作者 (extract+max) — as-designed | 71% | 62.2% (46/74) | 他們 BM25 top-10(= 他們釋出值)|
| mem0+P1 | 52% | — | write-time destructive |

> 這篇宣稱 deterministic-freshness SOTA 的並行工作,**在我們公平設定下 = 80% overall**,低於 ours(94%)、甚至低於 Zep(82%)。**gap ours−作者 = +14pp overall / ~+20pp has_pair**。

---

## §3 機制:world-prior 從 **extraction** 洩漏(不是 freshness-pick)

作者所有 has_pair 失敗**都是同一機制**:LLM extraction **只抽出舊(真實世界)版、漏掉 counterfactual 新版**(n_candidates=1)→ deterministic `max` 只有舊版可選 → 答舊。

| 檢索 | has_pair | 失敗且只抽 1 版(leak)|
|:--|:--|:--|
| BM25 top-10 | 62.2% | **27/28**(= 他們釋出值)|
| vector top-100(公平)| 73.0% | **20/20** |

- **correct 全部 n_cand=2**(抽到兩版 → max 挑新);**wrong 全部 n_cand=1**(只抽舊版)。無「max 挑錯 distractor」的新錯誤。
- **檢索深度只改 leak 率(27→20),不改機制**。vector top-100 leak 較少是因語意檢索把兩版撈得更均衡 + 更多版本樣式提示 → 較常兩版都抽;但仍 20 個漏。

**根因**:他們把 **freshness** 移出 LLM(→ 確定性 max),但**把 identity/選候選留給 LLM**;counterfactual 與模型參數知識衝突時,**world-prior 讓 extraction 把新版當「錯的」丟掉**(對接知識編輯文獻「prior hard to override by prompting」;他們真 prompt 已有「higher=newer version」+「include both」提示仍擋不住)。

**ours 為何免疫**:identity 用**確定性 (S,P) 結構索引**——同 subject+relation 的所有版本**必然同組**,不受 world-prior 影響 → counterfactual 不可能被丟 → argmax(ordinal) 挑到它。**這 +14~20pp 全來自「LLM extract identity vs 結構 identity」。**

---

## §4 一句話定位(可進 paper related work / discussion)

> 並行工作(Reddy & Challaram 2026)證明「別讓 LLM 追 freshness」對——把 freshness 移出 LLM 交確定性 `max`。但它**只做了一半**:identity(認出同一事實的不同版本)仍由 **LLM extraction** 承擔,於是 world-prior 從 extraction 洩漏(其自身資料 27/28、我們公平設定 20/20 的 has_pair 失敗)。**我們把 identity 也結構化((S,P))**,才真正把 world-prior 擋在門外 → 在同 bank/檢索/metric/backbone 下 +14pp overall,且**弱 backbone 上差距預期擴大**(LLM extraction 隨 backbone 變弱而崩,(S,P) backbone-invariant)。

---

## §5 caveat + 未做

- **retrieval 差異已控**:兩版(BM25 top-10 / vector top-100)機制一致,公平版用 vector top-100(= ours);差異只是 leak 率。
- **backbone spectrum(決勝場,next)**:gpt-4.1-mini 直接可跑(改 `PIPELINE_MODEL`,同 bank);gemma 需 GX10(per-backbone P1 bank + OpenAI client 指 ollama)。預期作者方法於弱 backbone 崩(LLM-extract 脆弱)、ours (S,P) 撐住。
- **其他長度**:32k local 有 P1 cache 可跑;64k 需重建 P1 bank(local 無)或 GX10。
- **忠實度**:extraction prompt/resolution 為作者 verbatim code;唯一非他們的是 bank(我方 P1)、檢索(公平版 vector)、metric(我方官方)、backbone——皆為「公平化」而非改他們方法。
