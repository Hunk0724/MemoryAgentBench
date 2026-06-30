# FC-MH Diagnostic — Findings

> 對應 methodology: [`diagnostic_methodology.md`](diagnostic_methodology.md)
> Raw 結果: [`results/diagnostic/`](results/diagnostic/)
> 實驗環境: HippoRAG-v2 × Gemini 3.1 Flash-Lite × chunk_size=512 × 6k context (455 facts) × 100 FC-MH 題

---

## TL;DR

**這份 diagnostic 真正的 contribution 是: 把「detection 結果 → inference 端」的不同 information channel 上限量化出來, 為 Mem0 (filter) 與 Zep (annotation) 等 production 系統提供位置定位 benchmark。**

| Channel | 真實系統 | Oracle 對應 | FC-MH 上限 (原 prompt) |
|---|---|---|:---:|
| 強 filter (delete) | Mem0 | OA2 fact-removal | **55%** |
| Soft annotation (timestamp/label) | Zep | PAT label | **36%** |
| 結構 annotation + 強指令 | (少見) | RPT | 68% (FC-overfit) |
| 完美 chain | — | Sim-OB | 98% |

**Multi-hop 不是 chain reasoning 本身難 — 是 retrieved context 的衝突造成。** (但 prompt rigor 修正後, 對 paper 主張要更精細)

- LLM 純 multi-hop chain reasoning 在零噪音零衝突下 = **98%** (Sim-OB)
- 每個 single-hop 在 standalone retrieval 下 = **94.5%** (B)
- 但 chain 在 noisy 6k context 下崩到 **23%** (A1 modified prompt) / **20%** (A1 原 prompt)
- 失敗中 91% 首錯在 conflict hop, 92% 的 in-chain hop 失敗在 ablation 下會恢復

**完整 2×2 對比 (FC-agnostic methods only, FC-MH n=100)**:

| Method | 原 prompt | + intermediate trailer |
|---|:---:|:---:|
| A1 baseline | 20% | 23% |
| PAT (soft label) | 36% | 48% |
| **OA2 fact-level filter** | **55%** | **83%** |
| Sim-OB (chain-only ceiling) | (98% under both) | 98% |

**FC-overfit (不可部署) 對照組** (僅作 in-context 上限參考):
- RPT-min: 60% MH (原 prompt)
- RPT: 68% MH (原 prompt)

**Paper 主張 (修正後)**:
- **OA2 filter > PAT soft label** 在所有 prompt 條件 (FC-agnostic 內) 都成立 (+19 pp 原 prompt, +35 pp modified prompt)
- **Reasoning scaffold prompt (intermediate trailer) 是獨立的大杠桿**, 對 clean context 的 boost 比 noisy context 大 (+28 pp on filter vs +3 pp on baseline) — synergy 不是純疊加
- **Production 建議: filter + trailer (FC-agnostic, 83% MH on full 100), 與 chain-only 98% ceiling 還剩 ~15 pp 屬 retrieval 噪音與 entity confusion**

---

## 1. Headline 對比

所有條件 vs FC-MH 100 題 (同 denominator):

| Condition | EM | 說明 |
|:---|:---:|:---|
| A1 baseline (top-10 retrieved, 6k noisy) | **23/100 = 23.0%** | modified-prompt vanilla |
| C (移除非 chain old facts) | **42/100 = 42.0%** (+19 pp) | 只保留該題自己的 conflict pairs |
| **Oracle A v2** (fact-level 移除 chain olds, full 100) | **83/100 = 83.0%** (+41 pp from C) | passages 內 surgical 移除舊事實句,不丟 GT |
| Sim-OB (chain-only context) | **98/100 = 98.0%** (+15 pp from OA2) | 純 chain reasoning ceiling |
| B all-hops-pass (AND of single-hops) | **87/100 = 87.0%** | 每跳獨立可解的題目比例 |
| B per-hop EM rate | **240/254 = 94.5%** | 254 個 single-hop 子題 |
| (Oracle A v1, prior, passage-level) | 63.6% on 66 usable subset | 整 passage 移除丟失 same-passage GT,僅 subset 適用 |

**Oracle A v1 → v2 改進**: v1 因為移除整個 passage 必須排除 same_passage 題目 (SH 9 題、MH 19 題),僅能跑 subset (66/100)。v2 fact-level surgical removal 保留 passage 內其他 facts,可跑全 100 題。FC-SH 從 v1 81.2% (subset) 升到 **v2 98.0% (full 100)**,FC-MH 從 v1 63.6% (subset, Gemini) 升到 **v2 83.0% (full 100)**。

**v1 → v2 gap 拆解** (FC-MH, 兩者皆 Gemini 3.1 Flash-Lite):

| 比較 | n | v1 | v2 | Δ |
|---|:---:|:---:|:---:|:---:|
| Same 66 usable subset | 66 | 63.6% (42) | **87.9% (58)** | **+24 pp 純演算法收益** |
| 34 v1-excluded (same_passage 等) | 34 | — (無法跑) | 73.5% (25) | — |
| Full 100 | 100 | — | 83.0% (83) | (= 87.9 × 0.66 + 73.5 × 0.34) |

→ **Passage-level 移除為何比 fact-level 低 24pp?** 對 v1=錯 / v2=對 的 17 個 flip case 逐題驗證:

| 失敗類型 | 題數 | 根因 |
|---|:---:|---|
| v1 subset filter cross-hop bug → 連 chain GT 一起丟 | **2** | qid 13 (hop 1 GT seq=94 與某 hop old 同 passage)、qid 22 (hop 0 GT seq=200 同 passage)。v1 篩選邏輯只檢查 per-hop pair (old/GT 不同 passage),沒做 cross-hop 檢查 (移除 hop A 的 old passage 是否殺到 hop B 的 GT) |
| v1 連帶丟 36-109 個 non-chain supporting facts | **15** | passage-level 移除整個 chunk (~25-30 句相鄰序號 facts),即使保住 chain GT,也讓 LLM 失去 chain reasoning 所需的周邊 context。這些 case 中 v1 的失敗模式:7 題 picks older_fact、2 題 partial old chain、6 題 entity confusion / 中段 stop / hallucinate 無關 entity |
| 純粹 fact-level 切除 = passage 切除 | 0 | (chunk_size=512 一塊太大,不存在「乾淨移除」case) |

**所以 v1 vs v2 在 same subset 24 pp gap 拆解: 3 pp 來自 v1 filter bug,21 pp 來自 passage 粒度太粗連帶丟 supporting facts。**

→ 結論: 在 chunk_size=512 下,passage-level 移除幾乎不可能避免「誤傷 supporting context」。fact-level surgical excision 是必要 — 兩者的對比直接示範了「filter granularity」對 LLM chain reasoning 的影響。

**v1-excluded subset 在 baseline 上是更難的, 不是更簡單** (A1 在 66 usable = 25.8%, 在 34 excluded = 17.6%) — same_passage 題目因為新舊 facts 擠同一 chunk,LLM 同視野下更容易混淆。

**這 4 個檢核點 + 2 個輔助 ceiling 把 23% → 98% 的 75pp gap 完整拆解。**

---

## 2. A2 — Per-hop diagnosis (失敗根因)

77 道答錯題的 first-error-hop 分析:

| 首錯 hop 屬性 | 數量 | 比例 |
|---|:---:|:---:|
| **conflict_type = has_pair** | **70** | **91%** |
| conflict_type = no_conflict_pair | 7 | 9% |

| 首錯 prediction class | 數量 | 比例 |
|---|:---:|:---:|
| **older_fact** (採信舊事實) | **55** | **71%** |
| other (entity confusion) | 21 | 27% |
| missing | 1 | 1% |

| 首錯 hop 位置 | 數量 | 比例 |
|---|:---:|:---:|
| **hop 0** | **53** | **69%** |
| hop 1 | 23 | 30% |
| hop 3 | 1 | 1% |

**結論**: failure mode 高度集中 — 在第一個 conflict hop 就被舊事實騙走,根本沒機會展開 chain。

Per-hop 預測類別 (188 個 has_pair hops, 66 個 no_conflict hops):

| conflict_type | correct | older_fact | other | missing |
|---|:---:|:---:|:---:|:---:|
| has_pair | 18% | 32% | 36% | 13% |
| no_conflict_pair | 53% | — | 41% | 6% |

→ has_pair hops 只有 18% 答對,其中 32% 採信舊事實。

---

## 3. B — Hop-by-hop ablation (single-hop ceiling)

每個 hop 當 standalone FC-SH 跑 (新 retrieval + 新 inference):

| 屬性 | EM |
|---|:---:|
| Overall (254 sub-questions) | **94.5%** |
| has_pair hops (n=188) | 92.6% |
| no_conflict_pair hops (n=66) | 100.0% |

按 hop position:

| hop_idx | EM | n |
|:---:|:---:|:---:|
| 0 | 99.0% | 100 |
| 1 | 92.0% | 100 |
| 2 | 94.9% | 39 |
| 3 | 80.0% | 15 |

→ Single-hop 在 isolation 下接近完美。

---

## 4. A2 × B Cross-tab (chain context 干擾量化)

| | B_correct (ablation pass) | B_wrong (ablation fail) |
|:---|:---:|:---:|
| **A2_correct** (in-chain pass) | 27% | 0% |
| **A2_wrong** (in-chain fail) | **67%** ← 干擾損失 | 5% |

**67.3% 的 per-hop 對僅在 in-chain 時答錯,在 ablation 時答對** — 這部分純粹是 chain context 干擾造成,不是 LLM 沒能力。

Of all in-chain failures (185 hops), **92% 的失敗在 ablation 下會恢復**,只有 8% 是真的不會解的。

---

## 5. Sim-OB — Chain-only ceiling

context = 僅 chain 的 N current facts (e.g. 3-hop 題 = 3 句 facts):

| 分組 | EM |
|---|:---:|
| Overall | **98.0%** |
| 2-hop | 96.7% |
| 3-hop | 100% |
| 4-hop | 100% |

→ LLM 純 chain reasoning 沒問題,所有 hop count 在乾淨 context 下都接近完美。

---

## 6. Sim-OB-grad — Noise tolerance curve

chain + k distractors,k ∈ {10, 50, 100, 200, 455}:

| Source \ k | 10 | 50 | 100 | 200 | 455 |
|:---|:---:|:---:|:---:|:---:|:---:|
| **ppr-nearby** (semantic noise) | 97% | 90% | **61%** | **34%** | 21% |
| **random** (length-only) | 96% | 93% | 87% | 76% | 20% |

兩條曲線的關鍵差異:
- **k ≤ 50**: 兩者幾乎一樣 (~ 90-97%) — 少量噪音不影響
- **k = 100**: PPR-nearby 突然從 90% 崩到 61% (-29pp),random 仍維持 87% — **PPR-nearby 在此處達到噪音閾值**
- **k = 200**: PPR-nearby 34%,random 76% — semantic distractor 比 length-only 多傷 42pp
- **k = 455**: 兩者收斂到 ~ 20% (因為兩種來源都包含全部 451 個非 chain facts)

**結論**: 噪音的傷害不是純 length 造成,**semantically nearby 的事實 (即真實 RAG retrieval 給的候選) 才是主因**。`PPR-nearby distractor 中 ~過半比例是其他題目的 has_conflict 對,LLM 對任何 conflict 都會被吸引去採信舊事實。`

---

## 7. C — 移除非 chain old facts

context = 完整 6k - 其他題目的 old facts (僅保留該題 chain 上的 conflict pairs):

| Condition | EM | Δ vs A1 baseline |
|---|:---:|:---:|
| A1 baseline (含所有 olds) | 23.0% | — |
| **C (僅留 chain olds)** | **42.0%** | **+19 pp** |
| Oracle A (移除所有 olds, 僅 usable subset) | ~63.6% | (different denominator) |

→ **單純移除 query-irrelevant conflicts 就讓 Acc 翻倍。**
→ 證實 LLM 對「跟題目無關」的 old facts 也會被誤導,不只 chain 上的。

Per (num_hops, n_conflict) breakdown:

| 分組 | Sim-OB | C | A1 |
|:---|:---:|:---:|:---:|
| 2-hop, 1-conflict | 96.0% | 76.0% | 52.0% (13/25 from A2) |
| 2-hop, 2-conflict | 97.2% | 44.4% | 16.7% (6/36) |
| 3-hop, 3-conflict | 100% | 20.0% | 10.0% (1/10) |
| 4-hop, 3-conflict | 100% | 0.0% | 0.0% (0/7) |

- 2-hop 1-conflict: ceiling 96% → C 76% → baseline 52% — non-chain 噪音貢獻 ~ 24 pp,chain conflict 貢獻 ~ 24 pp
- 3-hop+ 多衝突題即使移除 non-chain olds 仍崩盤,**chain 自身的多衝突解析才是極端情況的 bottleneck**

---

## 8. Paper framing

把 23% → 98% 的 75pp gap 完整拆解 (全 100-題 denominator):

| Component | Gap closed | Mechanism |
|---|:---:|:---|
| **Non-chain conflicts** (query-irrelevant) | **+19 pp** | A1 23% → C 42% |
| **Chain conflicts** (query-relevant) | **+41 pp** | C 42% → OA2 83% |
| **Other retrieval noise** (semantic distractors, no conflict) | **+15 pp** | OA2 83% → Sim-OB 98% |
| **Multi-hop chain accumulation** | ~ 0 pp | Sim-OB ≈ 100%,可忽略 |

**主要發現**:
1. **Chain 衝突是最大的單一原因** (+41 pp) — LLM 在 chain 上的 has_conflict hop 採信舊事實是頭號 failure mode
2. **非 chain 衝突也貢獻了一半** (+19 pp) — 連跟題目無關的 conflict 都會把 LLM 拉去亂選舊事實 (即使其他題目的 conflict)
3. **Multi-hop reasoning 本身不難** (Sim-OB 98%) — 不需要新的 reasoning 機制
4. **PPR-nearby semantic distractor 在 k=100 處突崩** — retrieval ranking 該避免把過多 nearby 衝突一起帶進來
5. **Hop 0 是壓倒性的失敗點** (69%) — chain 在第一個 conflict 就斷,後面都是 cascade

→ 改進方向優先序: **conflict-aware retrieval/re-ranking** ≫ 多跳 reasoning prompt

### FC-SH 對照 (同樣的拆解,但簡單)

| Condition | FC-SH EM |
|---|:---:|
| A1 baseline | 96/100 = 96.0% |
| Oracle A v2 (fact-level) | **98/100 = 98.0%** |

SH baseline 已經接近 ceiling (96%),fact-level removal 只多救 2 題,因為 SH 沒有 chain accumulation 問題,baseline 主要 failure 已經是極少數的 conflict-resolution 失誤。

---

## 9. 數據檔案清單

| 檔案 | 說明 |
|---|---|
| `analysis/a1_modified_prompt_baseline.py` | Task A1 + 共用 prompt 模板 |
| `analysis/a2_per_hop_diagnosis.py` | Task A2 |
| `analysis/b_hop_by_hop_ablation.py` | Task B (HippoRAG retrieval per single-hop) |
| `analysis/sim_ob_chain_only.py` | Task Sim-OB |
| `analysis/sim_ob_grad_noise.py` | Task Sim-OB-grad |
| `analysis/c_no_distractor_conflicts.py` | Task C |
| `analysis/oracle_a_fact_level.py` | Oracle A v2 (fact-level surgical removal) |
| `analysis/diagnostic_summary.py` | 統合 summary |
| `analysis/results/diagnostic/a1_modified_baseline_{mh,sh}.json` | A1 results |
| `analysis/results/diagnostic/a2_per_hop_diagnosis.{json,txt}` | A2 results + summary |
| `analysis/results/diagnostic/b_hop_ablation_results.json` | B results |
| `analysis/results/diagnostic/sim_ob_chain_only_results.json` | Sim-OB results |
| `analysis/results/diagnostic/sim_ob_grad_results.json` | Sim-OB-grad results |
| `analysis/results/diagnostic/c_no_distractor_conflicts_results.json` | C results |
| `analysis/results/diagnostic/oracle_a_fact_level_{mh,sh}_results.json` | Oracle A v2 results |
| `analysis/results/diagnostic/diagnostic_summary.txt` | 文字版 summary 報告 |

---

*產出日期: 2026-04-28*
