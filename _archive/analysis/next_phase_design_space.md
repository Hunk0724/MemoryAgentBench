# 下一階段:從 HippoRAG-v2 出發設計 conflict detection 機制 — design space 地圖

> 此文件接續 [fc_mh_hypotheses.md](fc_mh_hypotheses.md) 的 strategic pivot 與 [SESSION_2026-04-28_diagnostic_summary.md](SESSION_2026-04-28_diagnostic_summary.md) 建立的 channel design space oracle benchmark:把焦點從「inference prompt 設計」轉到「detection mechanism + info 傳遞策略」這個更 leveraged 的方向。
>
> 目的:在從 HippoRAG-v2 開始嘗試新方法之前,把可選的 design choices 整理成一張地圖,讓每個設計選擇都對應到「能驗證什麼假設 / 解什麼具體 gap」。
>
> ⚠️ **2026-04-29 修正**:本文件原版的 Phase 排序與 SESSION doc §7 推薦的 priority 不一致。已改成 SESSION 建議的優先順序(Production baselines on spectrum → Imperfect-detection robustness → Hybrid channels → Generalization)。原 Phase 框架被取代,但設計空間的兩維度與 channel 對照表仍然有效,僅補充 OA2 與 Sim-OB 的 oracle 上限數字。

---

## 兩個正交維度

任何「衝突解決」記憶方法可以分解成兩個正交決策:

| 維度 | 含義 | 失敗會出現在 |
|---|---|---|
| **(A) Detection accuracy** | 寫入 / 檢索時辨識「哪個 fact 是 CURRENT、哪個是 OUTDATED」的準確度 | 如果 detection 錯,後續 inference 拿到錯誤訊號;Zep SH 14 個 misfired counterfactual 是案例 |
| **(B) Info-packaging strategy** | detection 結果怎麼傳遞給 inference LLM | 如果訊號形式 LLM 不採信(Zep date_range 0% 識別),detection 再準也沒用 |

兩個維度都做到極致才能達到 ceiling;單做一邊有 cap。

---

## Channel design space — production methods + oracles 一張地圖

把所有 method 放上「detection-to-inference channel」的 spectrum(per SESSION §★ Contribution table):

| Channel 類型 | 實際系統範例 | Oracle / 實驗對應 | FC-MH EM (gemini) |
|---|---|---|:---:|
| 零 detection | (無記憶系統) | A1 baseline modified | **23%** ← Floor |
| **強 filter**(delete 舊知識)| **Mem0** OOB(被 prompt-rejected,實際 detection 沒運作)| OA2 fact-level 原 prompt | **55%** ← filter ceiling, Layer 1 universal |
| 強 filter + reasoning trailer | (Mem0 + COT prompt)| OA2 + intermediate trailer | **83%** ← Layer 2 QA-only |
| **soft annotation**(timestamp/label)| **Zep** | PAT(`[CURRENT/OUTDATED FACT]`)| **36-48%** |
| 結構 annotation + 強指令 | (production 少見)| RPT-min(inline section labels)| **60%** |
| 結構重組 + DO NOT USE 強指令 | (FC-overfit, 不可部署)| RPT(Section A/B partition)| **68%** ← in-context FC-aware oracle |
| 完美 chain context(理論上限)| **不存在** | Sim-OB chain-only | **98%** ← Absolute ceiling |

**關鍵 trade-off 兩條 dimension**:
- **資訊強度**:filter > strong annotation > soft annotation > 無 → 上限越高
- **Reversibility**:annotation > filter → filter 不可逆,對 historical / counterfactual queries 失效(若需保留歷史版本,annotation 較好)

**Channel-orthogonal 乘數:Reasoning scaffold prompt(intermediate trailer)**
- filter + trailer:**+28 pp synergy**(55% → 83%)
- annotation + trailer:**+12 pp synergy**(36% → 48%)
- baseline + trailer:**+3 pp**(20% → 23%)
- 即:trailer 的 effect 隨 context cleanliness monotonically scale → 只在 context 足夠乾淨時 unlock chain reasoning 能力

### Production system 在 spectrum 上的位置

| 方法 | (A) Detection 設計 | (B) Info-packaging | FC-MH EM | 主要限制 |
|---|---|---|:---:|---|
| **HippoRAG-v2** | ❌ 無顯式 detection,LLM 自推 | passages with seq numbers + FC 序號規則 prompt | 11% (gpt) / 22% (gemini, orig prompt) | LLM 自推訊號失敗(H1+H2)|
| **Zep** | LLM extractor entity-edge supersession,標 `invalid_at` | edges 帶 `(valid_at - invalid_at)` + nodes summary "conflicts with" + episodes 原文 | 25% (gpt;gemini 待補)| detection ~50% per-hop 觸發;date range LLM 0% 識別;trust gap |
| **Mem0** (OOB) | LLM ADD/UPDATE/DELETE 真刪除舊 fact | retrieved memories(已過濾)| 1% (FC OOB)| `FACT_RETRIEVAL_PROMPT` 只抽 personal,FC 知識被拒;customize 後可能改善 |
| **RPT/RPT-min(我們的 oracle)**| 用 MQuAKE GT(perfect detection assumed) | `[CURRENT/OUTDATED FACT]` inline + section A/B + MUST | 68% / 60% (gemini) | **FC-overfit,不可部署**;真實場景無 perfect detection |
| **OA2(我們的 oracle)**| 用 MQuAKE GT(perfect detection assumed) | retrieval-time fact-level 移除舊 fact,**不改 prompt** | 55% (orig) / 83% (modified) | **Layer 1 universal**:不依賴 prompt,可放進多任務 system |

**觀察**:
- Zep 走的是 soft annotation channel(B 維度的 strategy B2,SESSION 對應 PAT-style 上限 36-48%)
- Mem0 走的是 strong filter channel(B 維度的 strategy B1,SESSION 對應 OA2 上限 55-83%)
- RPT 走的是 structured annotation channel(B 維度的 strategy B3-4,FC-overfit 不可部署)
- **OA2 oracle 對應的「strong filter without prompt change」是 production 推薦最強路線**(Layer 1 universal)

---

## 我們的設計選擇空間 — (B) Info-packaging 怎麼做

假設 (A) 已經有某個 detection 機制(後面討論),detection 結果有三種傳給 inference 的方式:

### Strategy B1:Filter at retrieval(Mem0 路線)

```
detect → 標 OUTDATED → 從 retrieval 過濾掉 → LLM 只看 CURRENT
```

| 優點 | 缺點 |
|---|---|
| LLM 不可能誤用 OUTDATED(根本沒看到) | 完全依賴 detection 準確度,detection 錯 = 訊號錯 = 答案錯 |
| Inference prompt 不需特殊設計,可保留 HippoRAG-v2 通用性 | 失去「兩版本都看見讓 LLM 自己判斷」的容錯彈性 |
| 對 (B) 維度的 LLM-side H1/H2/H3 問題完全規避 | detection misfire 災難放大(SH counterfactual 14 案例:Zep 的 7% EM 預測 Mem0 filter 也類似災難) |

### Strategy B2:Show all + temporal signal(Zep 路線)

```
detect → 雙版本都保留,加時間訊號 → LLM 看到全部、自行用訊號選
```

| 優點 | 缺點 |
|---|---|
| Detection 即使部分錯,LLM 仍可能從 raw context 自救 | LLM 對隱式 signal 識別率低(date range 0%,序號 33-46%)|
| 保留 historical context,適合「這 entity 的歷史 X 是什麼」類問題 | 訊號太多反而困惑 LLM;Zep node summary "conflicts with" 並列形式直接讓 LLM 困惑 |
| 沒丟訊息,後續 method 可改進 | 即使 detection 100%,LLM-side 仍受 H1/H2/H3 拖累(Zep MH 25% 是這個 cap)|

### Strategy B3:Show all + explicit marker + soft instruction(我們可走的中庸路線)

```
detect → 雙版本都保留,但用顯式 marker(類 RPT)+ 適度而非 overfit 的指令
```

| 優點 | 缺點 |
|---|---|
| 結合 B1 的「LLM 不必 infer signal」+ B2 的「保留全部資訊」 | 設計平衡點難:marker 太強 → overfit (RPT 路線);marker 太弱 → LLM 仍用世界知識(Zep 路線)|
| 可比 RPT 設計得更通用,不依賴 FC「序號越大越新」這個假設 | 需要 dataset 標 CURRENT vs OUTDATED 的訊號形式適用各任務(temporal vs version-based 不一定都用「serial」)|

> **一個有趣的觀察**:RPT 的 +8pp from MUST 一部分可能來自 LLM 自我過濾不列 OUTDATED(§副發現)——這意味著「marker + 弱指令」也可能達到接近 RPT 的效果,且 generalization 更好。

### Strategy B4(混合):filter for sure cases + show-with-marker for uncertain cases

```
detect → 信心高的 OUTDATED 直接 filter;信心低的雙版本+marker
```

兩個世界的 best:detection 高信心時走 B1(filter,效率最高);低信心時走 B3(保留資訊讓 LLM 判斷)。

需要 detection 機制提供 confidence score。

---

## 我們的設計選擇空間 — (A) Detection accuracy 怎麼做

### 從 HippoRAG-v2 出發的可選方向

HippoRAG-v2 本身沒做 detection,LLM 自己看 chunk 序號推。要加上 detection 層,有幾個切入點:

| 方向 | 描述 | 偵測什麼觸發衝突? |
|---|---|---|
| **(D1) 在 graph 構建時 detect** | KG 抽 triple 時,同 (subject, relation) 多 object 即觸發衝突,以 ingest order 為 currency proxy(類 Zep)| 純 structural,無需 LLM |
| **(D2) 用 embedding similarity detect** | retrieve 時對 top-k chunk 內的 facts 做 entity-relation 匹配,找出「同 (s,r) 不同 o」的對 | retrieval-time,不依賴 ingest order |
| **(D3) LLM-as-detector at ingestion** | ingestion 時 LLM 判斷新 fact 是否 supersede 既有 fact(類 Mem0 的 ADD/UPDATE/DELETE)| LLM-driven,可加 confidence |
| **(D4) LLM-as-detector at retrieval** | retrieval 完成、inference 之前,中介 LLM 看 top-k 並標 CURRENT/OUTDATED | inference-time,完全 LLM-driven |
| **(D5) 混合:structural + semantic** | structural 快速找候選對,LLM 確認 + 標 confidence | 兩階段,平衡速度與準確度 |

### 各方向的預期準確度與限制

| 方向 | 準確度 | 主要限制 |
|---|:---:|---|
| D1 | 中(取決於 ingest order proxy 是否正確,FC 上 100% 但其他 dataset 不一定)| FC artifact: ingest order = recency,在 LongMemEval 等真實 conversational data 上會失效 |
| D2 | 中-低(同 (s,r,?) 容易找,但「哪個是 newer」需要其他訊號)| 仍需 currency signal |
| D3 | 中-高(類 Mem0,LLM 看到一對 facts 通常能判斷)| 需要每次 ingest 都呼叫 LLM,成本高;LLM 對 counterfactual 仍可能誤判(回到 SH 14 案例)|
| D4 | 中-高(retrieval-time 中介,LLM 看到 query 上下文 + 候選對)| 增加 inference latency;與 inference LLM 同 backbone 時可能繼承同 bias |
| D5 | 高(structural 取候選 + LLM 確認)| 最複雜;但分階段較好 debug |

---

## 推薦的優先嘗試順序(per SESSION §7,2026-04-29 reordered)

按 SESSION doc 的 priority(從 oracle ceiling 推到 production claim 的 critical path):

### Phase 1 ★ (最高優先) — Production system baselines on channel spectrum

把 Zep / Mem0 放上 SESSION 已建立的 oracle channel benchmark,讓它們成為真實系統 baseline。現有 GPT-4o-mini 結果不能跟我們的 Gemini oracles fair compare,必須補 Gemini 版本(SESSION §7.A)。

| # | 待做 | 為何重要 |
|---|---|---|
| **1.1** | **重跑 Zep + Mem0 用 Gemini 3.1 Flash-Lite** | LLM 一致才能跟 9 個 Gemini oracles fair compare;現有 Zep 70% / Mem0 15% on FC-SH 都是 GPT 數字 |
| 1.2 | Zep edge invalidation precision/recall vs MQuAKE GT(MH + Gemini)| 量化 Zep detection 精度;[zep_mechanism_deep_dive.md](results/oracle_a/zep_mechanism_deep_dive.md) 已部分做過(SH:correct 7 / wrong 14 / none 52)|
| 1.3 | **Mem0 customization**(改 `custom_fact_extraction_prompt` 讓 FC 通用知識能被 ingest)| 直接測 Strategy B1(filter at write)在 FC 上的真實表現;也是 SESSION §7.A3 的負面 example value |
| 1.4 | 實際送進 LLM 的 inference prompt 結構盤點 | Zep:timestamp + abstract + raw;Mem0:vector retrieval。對照我們的 PAT/RPT,量化「資訊密度」 |
| 1.5 | End-to-end gap analysis | Zep/Mem0 E2E EM vs oracle channel ceiling = detection 改進的潛力空間,paper 核心 motivation |

### Phase 2 — Imperfect-detection robustness(SESSION 認定的「from oracle to production claim」橋樑)

對 OA2 / PAT / RPT 加人為 noise,看 degradation 曲線(SESSION §5.1 + §7.B B2):

- 對 OA2 加 imperfect detection 模擬:隨機保留 r% 的 chain old facts,r ∈ {1.0, 0.8, 0.6, 0.4, 0.2, 0.0}
- 對應 PAT 同曲線比較
- 找 OA2-filter 與 PAT-annotation 的 crossover point — 也就是 detection 多準時 filter 開始輸給 annotation
- **這是 paper 從「oracle ceiling」推到「production claim」的關鍵實驗**

### Phase 3 — Hybrid channel design(SESSION §7.B B1)

- **OA2 + PAT graceful labels 同時用**:retrieval-time filter 移除高信心舊事實,inference-time annotation 標記低信心 / 衝突未解的剩餘 facts
- 上限應介於 OA2(83%)與 Sim-OB(98%)之間
- 同時保留 Zep-style reversibility(historical queries 可從 graceful label 推回原版本)
- **最實用的 production design** 候選

### Phase 4 — 從 HippoRAG-v2 加 detection layer(我們的 method 設計)

設計 real detection algorithm,對應到上面 Phase 2 找到的 robustness 曲線位置:

| 方向 | 描述 | 對應 oracle 上限 |
|---|---|:---:|
| **D1** Structural detect at ingestion | KG 抽 triple 時,同 (s, r) 多 object 即觸發衝突,以 ingest order 為 currency proxy | OA2 filter 路線 |
| D2 Embedding-based at retrieval | 對 top-k chunk 做 (s, r) 相似性匹配 | filter 路線 |
| D3 LLM-as-detector at ingestion | LLM 判斷新 fact 是否 supersede 既有 | 類 Mem0,可加 confidence |
| D4 LLM-as-detector at retrieval | 中介 LLM 看 top-k 標 CURRENT/OUTDATED | inference-time |
| D5 Structural + LLM 混合 | structural 找候選 + LLM 確認 + 標 confidence | 兩階段,適合 Phase 3 hybrid |

**從 D1 開始最便宜:用 ingest order 做 supersession,對 FC 100% 準;但對真實 conversational data 會失效,要看 Phase 2 的 robustness 曲線決定值不值得做下去**。

### Phase 5 — Generalization(SESSION §7.C)

| # | 待做 |
|---|---|
| 5.1 | 擴展到 32k / 64k / 262k 對話歷史(目前全在 6k)|
| 5.2 | chunk_size=4096 重做(本 session 全用 chunk=512;Sim-OB-grad 噪音閾值與 fact-level vs passage-level 差距可能改變)|
| 5.3 | 換 LLM(GPT-4o-mini / Claude / 更大 LLM)看結論可推廣性 |
| 5.4 | 驗證 trailer 對 non-QA 任務(InfBench_sum)的負面影響 — 強化 paper Layer 2 scoping argument |

---

## 開放問題

1. **Mem0 customize 後是否能解 FC?** Detection misfire 比例如何?(Phase 1.3 答案)
2. **Strategy B1 (filter) vs B2 (annotation) 在 imperfect detection 下的 crossover 點在哪?**(Phase 2 答案)
3. **D1 ingest-order proxy 在非 FC 任務上會崩到什麼程度?** 需要 LongMemEval 或類似真實 temporal data 驗證(Phase 4-5)
4. **「per-hop 100% 覆蓋」在 detection 不完美時要怎麼辦?** 部分覆蓋是否仍能 close 大部分 EM gap?(Phase 2 ablation)
5. **Counterfactual robustness 是 detection 維度還是 inference 維度的問題?** RPT vs OA2 在 SH 14 案例上的對比能回答(Phase 1.2 + Phase 2)
6. **Hybrid filter + annotation(Phase 3)的實際 EM 是介於 83% 與 98% 之間,還是會因 design conflict 反而變差?**

---

*文件起始:2026-04-28(strategic pivot from LLM-reasoning analysis to detection mechanism design)*
*2026-04-29 修正:整合 SESSION_2026-04-28_diagnostic_summary.md 的 channel design space framing 與 oracle benchmark 數字*
