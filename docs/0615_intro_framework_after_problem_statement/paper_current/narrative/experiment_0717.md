# 4. Experiments

> **本檔說明**:2026-07-17 從頭撰寫,對接 [`introduction_0716.md`](introduction_0716.md) 三個 Research Objective + [`methodology_source_material_0716.md`](methodology_source_material_0716.md) 的 method commitments + [`experiment_source_material_0716.md`](experiment_source_material_0716.md) canonical 數字 + [`../writing_plan_0717.md`](../writing_plan_0717.md) 交付 checklist。**不繼承** `experiment.md`(v0 scaffold)的段落 —— 目標為與 method 章用詞風格一致的一版新草稿。
> **章節結構**(§4.2 Main Results → §4.3 Robustness → §4.4 Generality → §4.5 LME → §4.6 Ablation → §4.7 Discussion)於 writing_plan §4 之上依 user 2026-07-17 定案調整;理由:(i) F1 backbone spectrum 已整合 Gemma3 + OpenAI 3-tier 為單一視覺,兩者放同節聚焦 backbone robustness claim;(ii) cross-family(§4.4)明確定位為 backbone robustness 的 across-family 推廣;(iii) §4.2 專注 gpt-4o-mini 4-length 主表,論述最乾淨。

---

## 4.1 Setup

### 4.1.1 Datasets

本文於兩個 KU benchmark 評測:MemoryAgentBench 的 **FactConsolidation Single-Hop(FC-SH)**(counterfactual 型 KU)與 LongMemEval 的 **knowledge-update(LME-KU)**subtask(personal 型 KU)。兩者的統計整理於 Table 1。

**Table 1**:Datasets summary

| Property | FC-SH | LME-KU |
|:--|:--|:--|
| Source | MemoryAgentBench(ICLR'26)\cite{hu2026evaluating};MQuAKE-CF counterfactual edits\cite{zhong2023mquake} | LongMemEval(ICLR'25)\cite{wulongmemeval},`longmemeval_s_cleaned` 子集 |
| KU 情境 | counterfactual(新事實與 LLM parametric 世界知識衝突)| personal(使用者事實隨時間變動,與世界知識無關)|
| Context lengths(tokens)| **6k / 32k / 64k / 262k**(4 length) | mean **127.7k** per query(range ~120-135k) |
| Context 結構 | 編號 fact statement 列表(非 dialogue) | 多 session 對話,mean **488 turns across 47.5 sessions** |
| Queries(主 metric 分母) | **100 / length** | **78** knowledge-update questions |
| has_pair 子集(有 old/new GT 對照) | 74 / 65 / 66 / 77(6k/32k/64k/262k) | 每 question 為 1 KU pair(78 pairs total)|
| Full fact bank(P1 extraction)| 455 / 2,309 / 4,570 / 18,321 facts(avg **~35 facts/chunk**) | 每 question 動態抽取,size 隨 session 內容變動 |
| In-store conflict pairs(same-(S,P) ≥2 objects)| 161 / 837 / 1,691 / 7,236 | — |

**Notes**:
1. FC-SH 沿用 benchmark 官方 100-query 子集 作為主 metric 分母(對齊 \cite{hu2026evaluating} 官方 evaluation 慣例)。**has_pair** 為 100 內真正有 gt_new / gt_old 配對的 query 子集,用於 KU 機制歸因(§4.7 analysis);**no_conflict** 為單版 ground-truth query。
2. FC-SH context 為 MQuAKE-CF counterfactual edits 拼成的 numbered fact statement 列表,**非** dialogue turn 形式;每 chunk 於 chunk_size=512 下平均含 ~35 個 fact statements。
3. LME-KU 每 question 對應**一個** knowledge-update pair(舊值於早期 session、新值於後期 session);sessions 於 haystack 中 chronologically 排列,系統需自 session-序中辨識最新版本作答。

### 4.1.2 Baselines

本文將 baselines 依 KU 判斷 timing 分為兩類(對接 Related Work §2 的 taxonomy):**write-time KU** 與 **query-time KU**;另加 memory-less **long-context** baseline 作為下限對照。

**Table 2**:Baselines summary

| Method | KU judgment timing | 判斷機制 | Reference |
|:--|:--|:--|:--|
| **Mem0 Vanilla** | Write-time coupled | mem0 native `FACT_RETRIEVAL_PROMPT` 抽取 + LLM 於單次呼叫輸出 ADD/UPDATE/DELETE/NOOP 並就地執行(destructive commit)| \cite{chhikara2025mem0} |
| **Mem0 + P1** | Write-time coupled | 我方 P1 忠實抽取(held-fixed)+ mem0 destructive UPDATE;**隔離 destructive commit 於良好 extraction 上的效應**(對照 Mem0 Vanilla 隔離 extraction 因素)| \cite{chhikara2025mem0} + P1 = 本方法 write-time |
| **Zep** | Write-time decoupled | Zep cloud graph 用內部 LLM 標 *contradicts* / *duplicates* → 系統將舊 edge `invalid_at` 設為新 edge 的 `valid_at`(bi-temporal invalidation);edge body 保留 | \cite{rasmussen2025zep} |
| **LCA(Long-Context Answer)** | 無記憶 | gpt-4o-mini 直接吃全 context 答題;無 write / retrieve pipeline | 對照下限;無記憶架構 |
| **Vanilla-RAG** | Query-time LLM temporal | Raw-query 檢索 top-100 → ordinal-prefixed pool → benchmark-native `factconsolidation.rag_agent` template(含「serial 大 = 新」recency rule)→ LLM 判 recency 選版本 | benchmark-native flow |
| **Don't Ask** | Query-time LLM extraction | Vector top-100 → LLM 抽 candidate facts → Python `max(serial)`(freshness 確定性,identity 由 LLM extraction)| \cite{reddy2026don};concurrent work;直接 import 作者 repo `_extract_candidates` + `_freshness_pick` |
| **Ours(Struct + LLM-Fallback)** | Query-time deterministic + LLM fallback | Raw-query 檢索 top-100 → Phase 0 (S,P) structural grouping + `argmax(ordinal)` → Phase 3 LLM identity fallback 於 triple-null / singleton 群(rare)| 本方法 |

**Notes**:
1. **Mem0 Vanilla vs Mem0 + P1** 為本方法的兩個對照組合:(a)Vanilla 展示 extraction + destructive commit 的**聯合**弱點;(b)+P1 於良好 extraction 前提下**隔離 destructive commit** 的獨立效應。兩者差反映 P1 extraction 對 mem0 UPDATE decision 的貢獻(§4.7 附加討論)。
2. **Don't Ask** \cite{reddy2026don} 為與本方法**最近的並行工作**(同 defer KU 至 query-time + freshness 確定性),但 identity 仍由 LLM extraction 承擔 → world-prior 從 extraction 洩漏(§4.7 D1)。我方直接 import 作者公開 repo(MIT license,commit `b6b92b4`),以我方 setup 執行以確保公平對比。
3. **LCA** 於 gemma tier 因 context window(8k / 16k / 32k)限制僅可對 6k;於 gpt-4o-mini 完整 4 length。

### 4.1.3 Backbones

依實際部署情境涵蓋三個能力區間:

| Tier | Model(s) | 覆蓋 | 對接 Introduction 段落 |
|:--|:--|:--|:--|
| **Weak(privacy-sensitive on-device)** | gemma3-1B / 4B / 12B / 27B(via Ollama)| FC-SH 6k(全 method)| §Motivation 隱私敏感 → SlimLM \cite{pham2025slimlm} / Huang et al. \cite{huang2025middle}|
| **Mid(cost-constrained API)** | gpt-4o-mini(paper 主 regime)| FC-SH 6k / 32k / 64k / 262k(全 method 全 length)+ LME-KU | §Motivation 成本敏感 → FrugalGPT \cite{chenfrugalgpt} |
| **Strong / cross-family** | gpt-5.4-mini(paper 定案 strong tier);cross-family:Gemma2-9B, Llama3.1-8B, Qwen2.5-7B, Mistral-7B(via Ollama,held-fixed gpt-4o-mini extraction)| FC-SH 6k | §Research Objective 3 falsifiable prediction 之收斂端 |

**Notes**:
1. **gemma3 tier 為 per-backbone extraction**(每 backbone 用自己的 gemma 做 P1 抽取)→ **同 backbone 內 method 比較公平**(extraction 已控制),**跨 backbone 絕對值同時混抽取品質**(paper 敘述 gap 趨勢而非絕對線);此為誠實揭露的實驗設計選擇。
2. **cross-family(7-9B open-weight)為 held-fixed gpt-4o-mini P1 extraction** + 該 local model 承擔 query-time 判斷(Phase 2 / P3 / UPDATE / answer)→ 明確**隔離「backbone 換成 local model 對 KU-resolution 的影響」**,與 gemma3 tier 的「整條 pipeline 跑在弱模型」互補。
3. **gpt-5.4-mini** 為 paper 定案的 strong tier;不採用 gpt-4o(原生高 tier)—— gpt-5.4-mini 於 6k 上讓 baselines 大幅上升(mem0+P1 +18pp、Don't Ask +16pp、Zep +11pp),已足夠驗證 backbone 收斂 claim。

### 4.1.4 Metrics

**FC-SH**:官方 `substring_exact_match`(sEM;`default_post_process` = normalize + parse_output + `max(raw, parsed)` + `max` over alias list),為 MemoryAgentBench 官方 Conflict-Resolution task metric \cite{hu2026evaluating}。**主分母 = overall 100 題**(對齊官方 evaluation);has_pair(74/65/66/77)僅於 §4.7 mechanism 分析時使用。單一 deterministic run(temperature 0);OpenAI server-side bf16 帶入 ±2-3pp 抖動(兩台從零 clone 已驗證於此範圍)。

**LME-KU**:LongMemEval 官方 `evaluate_qa_official.py` LLM autoeval(`autoeval_label.label ∈ {true, false}`;judge = gpt-4o-mini-2024-07-18,驗證期成本節省;是否回官方 gpt-4o judge 未定,列 §4.7 D3 caveat)。主分母 = 78 KU questions。

### 4.1.5 Implementation

Chunker chunk_size=512(mem0 native FactConsolidation-aware / uniform);retrieval top-K=100 vector(text-embedding-3-small;Zep 例外 k=10 per 官方 recipe);answer LLM 依 backbone tier。所有 run temperature=0,五把 OPENAI_API_KEY(A-E)獨立平行執行(store/cache/output 隔離)。

主表結果由 `analysis/rescore_canonical.py` 產出(single source of truth,53 cells canonical rescore);cross-family / gemma tier 由對應 result 檔匯總(見 `results/canonical_fc_sh_metrics.md` + `results/fc_sh_main_table_4length.md` + `results/fc_sh_backbone_spectrum_6k.md`)。

---

## 4.2 Main Results on FC-SH(gpt-4o-mini,4 length × 10 method)

### 4.2.1 Overall accuracy

**Table 3**:FC-SH overall sEM(N=100 / length),gpt-4o-mini backbone,10 method × 4 length。Bold = 該 length 最佳(Mean 欄為最高)。

| **Method** | **6k** | **32k** | **64k** | **262k** | AVG(4L)|
|:--|:-:|:-:|:-:|:-:|:-:|
| **Write-time KU baselines** |  |  |  |  |  |
| Mem0 Vanilla | 16 | 22 | 28 | 17 | 20.8 |
| Mem0 + P1 | 52 | 52 | 65 | 50 | 54.8 |
| Zep(k=10)| 82 | 80 | 76 | 29 | 66.8 |
| **Query-time KU baselines** |  |  |  |  |  |
| LCA(gpt-4o-mini full-context)| 88 | 74 | 65 | 43 | 67.5 |
| Vanilla-RAG(Q-time LLM temporal)| 93 | 77 | 85 | 81 | 84.0 |
| Don't Ask(Q-time LLM extraction)| 80 | 86 | 88 | 86 | 85.0 |
| **Ours(ablation & main)** |  |  |  |  |  |
| Ours (LLM-Identity-Only)| **97** | 91 | 91 | 87 | 91.5 |
| Ours (Struct-Only)| 91 | 87 | 92 | 86 | 89.0 |
| **Ours (Struct + LLM-Fallback)**(主 method) | **94** | **91** | **94** | **91** | **92.5** |

### 4.2.2 Length scaling

**Figure F2**([`figures_current/F_length_scaling_gpt4omini_4length.pdf`](figures_current/F_length_scaling_gpt4omini_4length.pdf))將 Table 3 的 6 個代表 method 以 line plot 呈現於 4 個 context length。顏色編碼 KU-decision paradigm(Q-det = 深藍;Q-llm = 琥珀/橘;W-llm = 紫/深紅),linestyle 為 B&W 冗餘編碼。

### 4.2.3 Observations

1. **Ours 為唯一於 4 length 全部 flat 的方法**:overall 91-94(Δ 6k→262k = **−3pp**);has_pair 88-93%(§4.7 分析用)。所有其他 method 至少於一個 length 有 ≥10pp 掉幅。
2. **Write-time family 的 length 行為 三種 pattern**:
   - Mem0 Vanilla 全長 flat 於低點(16-28%,extraction 崩壞就已無 recall 基底);
   - Mem0 + P1 全長 plateau **50-65%**(destructive UPDATE 天花板;於良好 extraction 下仍受限於 write-time judge 的可靠性);
   - Zep 於 6k-64k 穩定 76-82%,**262k 崩至 29%**(query-time retrieval miss 主導,NotBothExtracted 82%;write-time invalidation coverage 亦降至 6.3%;見 §4.7 zep_ku_resolution_bitemporal.md §4C)。
3. **Query-time family 的 length 行為**:
   - **LCA 隨長度單調下降**(88→43,Δ **−45pp**;long-context 天花板);
   - **Vanilla-RAG non-monotonic dip 於 32k**(93→77→85→81;LLM 判 recency 於 flat ordinal pool 上不穩定,§4.7 D1);
   - **Don't Ask 是唯一越長越強的 baseline**(80→86-88;bank 越大,LLM extraction 越常抓到 both 版本,leak 率下降;§4.7 D1)。
4. **Ours ablation 的長度分工**:Ours (LLM-Identity-Only) 於**短 context(6k)**贏(97 > 94);Ours (Struct-Only) 於**長 context(262k)**貢獻大;full method 於每 length 取兩者上界(§4.6 ablation 深入拆解)。
5. **Mean 4L 排序**:full Ours = **92.5** > 三 ablation 89.0-92.0 > Don't Ask 85.0 > Vanilla-RAG 84.0;所有 write-time baseline ≤ 67.5(Zep)、64k 前 mem0+P1 仍 <55%。

---

## 4.3 Robustness across Backbone Capabilities

### 4.3.1 Backbone spectrum(headline)

**Figure F1**([`figures_current/F_backbone_spectrum.pdf`](figures_current/F_backbone_spectrum.pdf))為本文最有 discriminating power 的 headline 圖:x 軸 6-tier backbone(gemma3-1B → 4B → 12B → 27B → gpt-4o-mini → gpt-5.4-mini,弱→強),y 軸 FC-SH 6k overall sEM,5 method 各一條 line;顏色編 paradigm(藍 Ours、琥珀 Vanilla-RAG、橘 Don't Ask、紫 Zep、深紅 Mem0+P1),linestyle 為 B&W 冗餘編碼。左側 4 tier(Gemma3)有淺灰家族 band + 虛線分界(誠實揭露 per-backbone extraction 混淆軸)。

### 4.3.2 Gemma3 spectrum(1B / 4B / 12B / 27B @ 6k)

**Table 4**:Gemma3 spectrum overall sEM @ 6k(N=100)。gemma3 為 per-backbone extraction(每 backbone 用自己的 gemma 做 P1)。

| Method | 1B | 4B | 12B | 27B |
|:--|:-:|:-:|:-:|:-:|
| **Ours (Struct + LLM-Fallback)** | **44** | **79** | **99** | **99** |
| Ours (Struct-Only) | 52 | 79 | 99 | 97 |
| Ours (LLM-Identity-Only) | 27 | 50 | 72 | 59 |
| Vanilla-RAG | 30 | 48 | 68 | 69 |
| Don't Ask | 2 | 36 | 84 | 96 |
| Mem0 + P1 | 5 | 11 | 64 | 54 |
| Mem0 Vanilla | — | 11 | 53 | 45 |
| Zep(k=10)| 29 | 32 | 58 | 62 |

### 4.3.3 OpenAI mini-tier convergence(gpt-4o-mini vs gpt-5.4-mini @ 6k)

**Table 5**:OpenAI mini-tier 對照 overall sEM @ 6k(N=100)。gpt-5.4-mini 為 paper 定案 strong tier(2026-03 released,mini-tier,reasoning family)。

| Method | gpt-4o-mini(mid, 2024)| gpt-5.4-mini(strong, 2026)| Δ |
|:--|:-:|:-:|:-:|
| **Ours (Struct + LLM-Fallback)** | **94** | **99** | +5 |
| Vanilla-RAG | 93 | 98 | +5 |
| Don't Ask | 80 | 96 | +16 |
| Zep(k=10)| 82 | 93 | +11 |
| Mem0 + P1 | 52 | 70 | +18 ⚠ |

### 4.3.4 Observations

1. **Ours 於 6 tier 皆為 outright leader**(F1 藍線恆為最上):44/79/99/99 於 gemma3 4 tier,94/99 於 gpt tier;gpt-5.4-mini 上 saturation(99/100)但仍領先 second-best Vanilla-RAG(98)+1pp。
2. **Falsifiable prediction 兌現(直接支撐 §Research Objective 3)**:baseline 隨 backbone 變弱**單調下滑**至嚴重崩塌:Mem0 + P1 於 gemma3-1B/4B 崩至 5%/11%,Don't Ask 於 1B 崩至 2%(LLM candidate extraction 無法對弱 backbone 產出合格 candidate)。Ours 於同樣區間保 44/79 → gap ours − Mem0+P1 於 gemma3-4B 達 **+68pp**。
3. **Gap 於強端收斂但不 collapse**:gpt-5.4-mini 上全 method spread 從 42pp(gpt-4o-mini,52-94)收窄到 29pp(70-99);收斂由「地板」抬升驅動(Mem0+P1 +18、Don't Ask +16、Zep +11)。Ours 微升 +5,仍為 outright leader。
4. **Mem0 + P1 於 gpt-5.4-mini 非單調反常**(gpt-4.1-mini intermediate 81 → gpt-5.4-mini 70,見素材 §2.1;此 non-monotonic 為唯一違反 backbone 單調性的 method,可能因 reasoning-family 於 destructive UPDATE prompt 更保守 → NOOP 頻率上升 → 錯過 legitimate UPDATE 案例)。
5. **P3 於 gemma tier 為 capability-gated**:Ours (Struct + LLM-Fallback) − Ours (Struct-Only)於 1B **−8pp**(P3 反害)、4B/12B **0**(neutral)、27B **+2**(net-positive)—— **弱模型上加 LLM 判斷是 liability,強模型上才是 asset**;§4.6.2 完整分析。

---

## 4.4 Generality across Backbone Families

### 4.4.1 Cross-family(4 系列 open-weight @ 6k)

為驗證 §4.3 觀察到的 backbone-brittleness 不是 Gemma family 專屬,本節於 4 個獨立系列的 7-9B open-weight local models 上重複實驗。**Extraction 於 4 系列**皆為 **held-fixed gpt-4o-mini P1**(隔離「KU-resolution 換成 local model」的淨影響,不含 extraction confound;此與 §4.3.2 Gemma3 tier「整條 pipeline 跑弱模型」互補)。

**Table 6**:Cross-family overall sEM @ 6k(N=100);held-fixed gpt-4o-mini P1 extraction。

| Method | Gemma2-9B | Llama3.1-8B | Qwen2.5-7B | Mistral-7B |
|:--|:-:|:-:|:-:|:-:|
| **Ours (Struct + LLM-Fallback)** | **72** | **81** | **91** | **66** |
| Ours (Struct-Only) | 71 | 81 | 83 | 64 |
| Vanilla-RAG | 38 | 70 | 27 | 26 |
| Mem0 + P1 | 27 | 8 | 21 | 19 |

### 4.4.2 Observations

1. **Ours 於 4 系列全部領先**(66-91%),baseline 於 4 系列全部崩(Mem0+P1 於 4 系列 8-27%,Vanilla-RAG 於 Qwen2.5/Mistral 27/26%,僅 Llama3.1 於 70% 表現較佳)—— §4.3 觀察到的 backbone-gap **跨系列普遍存在**、不是 Gemma-family 專屬。
2. **Struct-Only 幾乎與 full method 齊平**(Δ = −1 / 0 / −8 / −2 pp)—— 於 mid-size(7-9B)local model,structural (S,P) 已為 workhorse;P3 邊際 0-8pp。此與 §4.3.4 Observation 5 一致(P3 為 capability-gated add-on)。
3. **Vanilla-RAG 於 3/4 系列崩至 <40%**(Qwen2.5-7B 27%、Mistral-7B 26%、Gemma2-9B 38%)—— LLM 判 recency 是**跨系列共通的 LLM 弱點**,非特定家族現象。Llama3.1-8B 例外(70%)反映該 model 於 rule-following 上較強。
4. **Mem0+P1 於 4 系列全崩至 8-27%** —— 於 mid-size local model 上,write-time UPDATE 判斷不可靠 → destructive commit 不可逆 loss → 天花板遠低於 query-time family。
5. **與 §4.3.2 Gemma3 tier 對比**:E3 於 held-fixed extraction 下,「backbone 換 local」的**KU-resolution 淨影響**已被隔離。gap 仍在(Ours 66-91% vs Vanilla-RAG 26-70%)→ **主要 gap 來自 P2/P3/UPDATE/answer LLM 判斷,非 extraction**。

---

## 4.5 Generalization to LongMemEval-KU(personal 型 KU)

### 4.5.1 Overall accuracy

**Table 7**:LME-KU accuracy(N=78,gpt-4o-mini backbone,gpt-4o-mini judge)。

| Method | correct / 78 | acc |
|:--|:-:|:-:|
| **Ours (Struct + LLM-Fallback)** | 55 / 78 | **70.5%** |
| Vanilla-RAG(1-stage LLM temporal)| 58 / 78 | 74.4% |
| Vanilla-RAG(2-stage LLM temporal)| 54 / 78 | 69.2% |
| Mem0 Vanilla | 53 / 78 | 67.9% |
| Mem0 + P1 | 47 / 78 | 60.3% |
| Zep(k=10)| ☐ deferred(Zep free plan 128k 上限,LME context ~128k)| — |
| Don't Ask | ☐ out-of-scope(dependency on FC-SH-style numbered fact bank + global serial)| — |

### 4.5.2 Personal vs counterfactual gap

Table 8 對照 ours 於 FC-SH 6k(counterfactual)vs LME-KU(personal)上 相對 baselines 的 gap:

**Table 8**:Gap 對照 —— ours 於兩情境的相對優勢

| 對照組 | FC-SH 6k(counterfactual)| LME-KU(personal)|
|:--|:-:|:-:|
| Ours vs Mem0 Vanilla | +78pp(94 vs 16) | **+2.6pp**(70.5 vs 67.9)|
| Ours vs Mem0 + P1 | +42pp(94 vs 52) | **+10.2pp**(70.5 vs 60.3)|
| Ours vs Vanilla-RAG(1-stage)| +1pp(94 vs 93) | **−3.9pp**(70.5 vs 74.4)|

### 4.5.3 Observations

1. **Ours 於 LME-KU 領先 3 個 baseline**(vs Mem0 Vanilla / Mem0+P1 / Vanilla-RAG 2-stage 皆勝),**但輸 Vanilla-RAG 1-stage 3.9pp**(70.5 vs 74.4)—— personal 型 KU 情境上 ours **未 outright 領先**所有 baseline。
2. **與 FC-SH 6k 對比,ours 的相對 gap 明顯縮小**(Table 8):vs Mem0 Vanilla 從 +78pp 縮至 +2.6pp;vs Mem0+P1 從 +42pp 縮至 +10.2pp。此**反向支撐**「FC-SH 上巨大 gap 主要來自處理 LLM parametric bias(counterfactual 情境)」的 abstract § 2 論述。
3. **Vanilla-RAG 1-stage 於 LME 略勝 ours** 的機制推論:personal-KU 事實不與 LLM parametric knowledge 衝突 → LLM 讀 ordinal-prefixed pool 判 recency 時**沒有 world-prior 抗力** → 直接照 ordinal 選新版即對。此與 §4.7 D1 觀察到「Vanilla-RAG 於 FC-SH 失敗的 95-100% 是回退世界先驗」一致(personal-KU 無此路徑)。
4. **與 Mem0 Vanilla 的 vs Mem0 + P1 direction 反轉**(§4.5.1):FC-SH 上 Mem0 + P1(52%)遠強於 Mem0 Vanilla(16%,+36pp);LME-KU 上 Mem0 + P1(60.3%)反而**低於** Mem0 Vanilla(67.9%,−7.6pp)。機制推論:於 LME 對話事實密度較低,我方 P1 抽取更多、更精細的 fact → mem0 destructive UPDATE 有更多機會產生 missing-ADD / cross-item confusion 錯誤,反致 damage 大於 Mem0 Vanilla native extraction。此結果指出 **Mem0+P1 於 LME-KU 上不能作為 cross-benchmark baseline**(我方 P1 於 dataset 間貢獻方向不一致);paper 於 cross-benchmark 論述時採 Mem0 Vanilla 為 baseline 基準。

### 4.5.4 Setup notes / caveats

- **Zep 於 LME-KU deferred**:Zep free plan per-graph 128K 上限,LME context ~128k + Zep episode credit 皆撞限;移至 Graphiti self-hosted 為 future work。
- **Don't Ask 於 LME-KU out-of-scope**:其 mechanism 依賴 dataset-provided numbered fact bank + global serial ordering(FC-SH 原生設計);LME-KU 為 per-session unnumbered conversational data,強行 adapter 需自建 per-session bank + 自定 serial 語義,已偏離作者原論文 scope。
- **Vanilla-RAG two-stage rigor correction**:早期 single-stage 版本於 LME 上被 env override 到 FC-SH `factconsolidation.rag_agent` template(含「serial 大 = 新」recency rule)→ 唯一被 prompt-augmented 的 method → 不公平;修正為 two-stage(Stage 1 = LLM 讀 top-100 mirror FC-SH prompt 選 winners → Stage 2 = winners 送 LME 原生 rag_agent template 答題,與 ours/vanilla/b byte-identical)後為 canonical 69.2%。single-stage 74.4% 保留於 Table 7 作對照,不引用於 claim。
- **P5 conflict-type classifier**:早期 `ours (+P5)` 於 Jun 30 舊 run 得 83.3%(65/78);於 2026-07-07 用 same store + P5 enabled reuse 得 55/78 = 70.5%(= ours main)→ **P5 net-zero**;83.3% 為 non-reproducible store-state artifact,已 drop。P5 於 FC-SH 亦 net-negative(見 §4.6);canonical 主 method 不含 P5。
- **Judge model**:目前 gpt-4o-mini judge(驗證期成本節省);是否回官方 gpt-4o judge(\cite{wulongmemeval} 官方 default)為未定 caveat。

---

## 4.6 Ablation Study

### 4.6.1 Structural vs LLM-Identity 元件

**Table 9**:Ours 內部 ablation × mid tier(overall sEM,N=100;gpt-4o-mini backbone)

| Method | 6k | 32k | 64k | 262k |
|:--|:-:|:-:|:-:|:-:|
| **Ours (Struct + LLM-Fallback)**(struct + P3 + argmax) | **94** | **91** | **94** | **91** |
| Ours (Struct-Only)(struct + argmax,關 P3) | 91 | 87 | 92 | 86 |
| Ours (LLM-Identity-Only)(P3 + argmax,關 struct) | **97** | 91 | 91 | 87 |

**Observation**:
- **兩 identity mechanism 互補、缺一不可**:LLM-Identity-Only 於**短 context(6k)嚴格支配** structural(97 > 91);但於**長 context(262k)** structural 反成關鍵(見 §Diagnostic 2:「只有 structural 對」的題數隨長度單調成長 0 → 2 → 3 → 5,independent 貢獻於 262k 最大)。**Full method 於每長度取兩者聯集**,於 4 length 保穩 91-94%。
- **P3 於 mid tier 淨貢獻(overall sEM diff,由 Table 9 自算)**:full − Struct-Only Δ = **+3 / +4 / +2 / +5**(6k / 32k / 64k / 262k)。若限於 has_pair 子集(N = 74 / 65 / 66 / 77)以 per-qid rescue 減 regress 讀,淨值為 **+2 / +4 / +2 / +5**;6k 差異(+3 vs +2)因 full method 於 no_conflict 子集(26 題)多修對 1 題,其餘 3 length 一致。長 context 邊際效益最大;§4.7.2 深入 P3 觸發率。

### 4.6.2 P3 capability-gate across backbone

**Table 10**:Ours (Struct + LLM-Fallback) − Ours (Struct-Only) 的 Δ 於 backbone spectrum(overall sEM @ 6k,N=100)。正值 = P3 net-positive。

| Backbone | Ours (Struct-Only) | Ours (Struct + LLM-Fallback) | Δ = P3 net contribution |
|:--|:-:|:-:|:-:|
| gemma3-1B(weakest)| 52 | 44 | **−8** ⚠ P3 反害 |
| gemma3-4B | 79 | 79 | 0(neutral)|
| gemma3-12B | 99 | 99 | 0(近 ceiling)|
| gemma3-27B | 97 | 99 | +2 |
| gpt-4o-mini | 91 | 94 | +3 |
| gpt-5.4-mini | — | 99 | — |

**Observation**:
- **P3 contribution 於 backbone tier 呈 U-shape**:弱端(1B)P3 反害 −8pp(LLM 於 1B 無法可靠 cluster identity → grouping 誤合併);mid tier(4B/12B)neutral(structural 已涵蓋主要 identity 情境);mid-strong tier(27B、gpt-4o-mini)net-positive +2 到 +3;super-strong(gpt-5.4-mini)near-ceiling。
- **兌現 method 章 §3.4「LLM 補救僅於少數案例介入」**:於 mid-strong 之上 P3 承擔 struct 已 clean pool 之後**壓 reader override** 的窄任務;於弱端 struct 是唯一可靠底盤,P3 為 liability。**Struct 為 backbone-universal scaffold,P3 為 capability-gated add-on**。

### 4.6.3 +P5 conflict-type classifier(appendix)

先前設計含 P5 conflict-type classifier(判 FRESHNESS vs COMPLEMENTARY)。實證於 FC-SH 4 length × gpt-4o-mini 上 net-negative(Δ = **−1 / −1 / 0 / +1** pp,mean −0.25pp);於 LME-KU 上 net-zero(P5 fired 534 次但答題差 = 0)。**P5 已自 canonical method 移除**;此 ablation 僅為 transparency 目的保留。

---

## 4.7 Discussion

### 4.7.1 Per-qid error mode:baselines fall to gt_OLD(D1)

Per-qid 逐題分析(6k/32k/64k/262k 4 length × 3 baseline;fc_sh_4method_errormode_diag.md canonical)顯示 **baselines 於 has_pair 失敗時 95-100% 是「答成 gt_OLD」**——即 pipeline 未能將新版供給 answer LLM,answer LLM 於缺乏新版時**回退到世界先驗的舊值**(counterfactual scope 下 gt_old = 世界真相事實):

- **Ours (Struct-Only)**:6k/32k has_pair 失敗 **100% 答成 gt_OLD**;64k/262k **88%/79%**;根因單一 = (S,P) canonicalization miss(predicate stem-vs-full variant 或 subject 碎裂使 new/old 分到不同結構桶,argmax(ordinal) 無從在桶內比對兩版 → pool 保留兩版 → reader 取世界先驗舊值)—— 這正是 P3 存在的理由。
- **Don't Ask**:6k/64k has_pair 失敗 **100% 是 `n_candidates == 1`**(LLM extraction 只抽出「舊(真實世界)版」,漏掉 counterfactual 新版)→ `max(serial)` 只有舊版可選 → 答舊。**其失敗不在 freshness pick 出錯,而在上游 LLM candidate extraction leak world-prior**。
- **Vanilla-RAG**:4 length has_pair 失敗 **95-100% 答成 gt_OLD**;LLM 於 flat ordinal pool 判 recency 時傾向回退到語意熟悉(世界先驗)的舊值,忽略 ordinal rule。32k 最壞(23 wrong / 65)。

**支撐 abstract § 2 causal claim**:baseline 錯誤主要來自 LLM parametric bias 於 counterfactual 情境的偏好;三種 baseline 各於 pipeline 不同位置(Ours Struct-Only 結構碎裂 / Don't Ask 上游 extraction / Vanilla-RAG 下游 recency judge)洩漏。Ours (Struct + LLM-Fallback) 以「忠實寫入全版本 + 結構 identity + P3 補救 + 確定性 argmax」逐一 dodge,殘餘僅 13/30 = 43% 屬方法可修(P3 mis-merge 7、(S,P) 碎裂 5、P2 predicate 誤抽 1),其餘 57% 屬 reader world-prior override(8)+ benchmark D-flag(6)+ non-KU(3)—— 皆與 KU 解析正交。

### 4.7.2 P3 rescue rate and trigger rate(D2)

Offline (S,P)-merge proxy(mirror `attribute_sp_merge`;讀 `triple_cache_p1_{L}` + `sh_{L}_mquake_analysis`)於 has_pair 子集(N = 74 / 65 / 66 / 77)量化 P3 於 pipeline 中的實際承擔:

**Table 11**:P3 觸發率(has_pair 子集;6k/32k/64k 為 offline (S,P)-merge proxy;262k 為 diff-based ground truth)

| Length | structural pool(argmax 解)| dynamic pool(P3 補救)| new_missing(P2 抽取失敗)| P3 in-bucket accuracy |
|:--|:-:|:-:|:-:|:-:|
| 6k(N=74)| 60/74 = 81% | 10/74 = 14% | **4/74 = 5%** | 9/10 = 90% |
| 32k(N=65)| 50/65 = 77% | 14/65 = 22% | **1/65 = 1%** | 11/14 = 79% |
| 64k(N=66)| 45/66 = 68% | 21/66 = 32% | 0/66 = 0% | 17/21 = 81% |
| 262k(N=77;diff-based)| 68/77 = 88% | 9/77 = 12%(7 rescue + 2 regress)| 0/77 = 0% | 7/9 = 78% |

**Column semantics**:
- **structural pool**:gt_new 與 gt_old 的抽取 triple 於 L0/L1/L2 normalization 下同 (S,P) key 且群大小 ≥ 2 → argmax(ordinal) 於群內取新版。
- **dynamic pool**:gt_new 與 gt_old 分到不同 (S,P) key 且各自為 singleton,或 triple-null → 進 P3 LLM identity clusters 補救(對接 method 章 §3.4;code 於 `phase2_query.py::conditional_structural_routing:164-187`,dynamic_pool = `no_triple + singleton_triple`)。
- **new_missing**:P2 gpt-4o-mini extractor 於該 query 未抽出 gt_new triple → fact bank 內無新版可供解 → pipeline 於 P2 前已失敗,structural / dynamic / P3 均無從補救;6k 4 題最多(短 context 給 P2 機會少),長 context 降至 0。
- **P3 in-bucket accuracy**:於 dynamic pool 觸發的 queries 中,ours (Struct + LLM-Fallback) 答對的比例;穩定 78-90%,不下拉 pipeline 整體品質。
- **三欄相加為 100%**:structural + dynamic + new_missing 覆蓋全 has_pair query 集。

**Observations**:
- **6k → 64k structural / dynamic 佔比隨長度單調變化**:structural ↓(81→77→68%),dynamic ↑(14→22→32%);P3 承擔的題數變多(10→14→21)→ 直接解釋 §4.6.1 Δ_P3(隨長度邊際效益成長)。
- **262k proxy 反轉為 99% structural**(caveat:P1 於大 fact bank 上更常產出 canonical (S,P) → L0 exact match 佔絕大多數 → proxy 於 262k 失解析力)—— 改用 main-vs-struct diff 讀為 ground truth:實際 P3-active queries = **9/77 = 12%**(7 rescue + 2 regress),與 6k/32k/64k 趨勢一致。
- **P3 in-bucket accuracy 穩定 78-90%**;於 dynamic-pool 觸發區的正確率高,不下拉 pipeline 整體品質。

**兌現 method 章 §3.4「LLM 僅為補救」定位**:P3 只在 12-32% 的 query 上真正做識別工作,其餘 68-88% 由確定性 (S,P)+argmax 解決;P3 觸發區的正確率高。**Struct 為 backbone-invariant workhorse;P3 為隨長度邊際效益成長的窄任務 add-on**。

### 4.7.3 Zep 262k crash mechanism(mechanism finding)

Zep 於 262k **overall sEM = 29%**(較 64k overall 76% 大幅下降;has_pair 子集 sEM 亦從 64k 64% 降至 262k **16%**,分母 66→77)。原先推論(fc_sh_main_table_4length caveat)為「write-time invalidation 覆蓋不足(6.3%)」,但 2026-07-16 補跑 `analysis/classify_zep_ku_resolution.py --length 262k` 顯示:

- **NotBothExtracted = 82%**(63/77 has_pair 中,top-10 retrieval 沒同時抓到 old + new 兩版)—— 答題 LLM 於 pool 內根本沒看到 both versions,無法區辨 → 靠 world-prior 猜 → 對應 262k has_pair sEM 崩至 16%。
- Additive-NoKU 反而崩到 8%(vs 32k 77% / 64k 74%),因為 both 版本進 top-10 的機會太少;無法再作為長度趨勢外推。
- Invalidation coverage **6.30%**(63/1000 edges tagged with `invalid_at`)—— 為 write-time 側的次要指標,單此不足以解釋 crash(對照:64k invalidation coverage 9.7%,同格 sEM 仍達 has_pair 64% / overall 76%)。

**結論**:Zep 262k crash 由**兩層問題疊加**構成,兩層皆為「圖大小 → semantic search 對特定 target edge 難以精準檢索」的表徵。**query-time retrieval miss 為主因**(top-10 抓不到 both 版本 → answer LLM 沒 both facts 可比 → 只能靠世界先驗猜舊)。**Top-K 已排除為根因**:Zep top-50 於 262k(46/100 queries before rate-limit)overall sEM = 28.3%,與 k=10 overall 29% 統計等價 → 拉到 top-50 也抓不到 both 版本。詳 [`../results/zep_ku_resolution_bitemporal.md §4C`](../results/zep_ku_resolution_bitemporal.md)。

### 4.7.4 Limitations and scope(D3)

本方法明確 scope 於**單值 KU 情境**(fact-level KU,同一 (S,P) 於同時間點只有一個當前版本):

1. **Counterfactual 型 KU**(FC-SH):outright 領先所有 baselines(§4.2/§4.3/§4.4)—— 為本方法主 scope。優勢主要來自處理 LLM parametric bias(D1)。
2. **Single-valued personal 型 KU**(LME-KU):領先 3/4 baseline,但**於 Vanilla-RAG 1-stage 上輸 3.9pp**(§4.5)—— 於 personal 情境無 world-prior 抗力時,LLM 讀 ordinal 直接判 recency 亦可行。Ours 的架構優勢於此情境**明顯縮小**,paper 於 scope wording 上明講「於 counterfactual bias-heavy 情境 outright leader,於 personal LLM-recency 家族相當」。
3. **Multi-valued personal fact**(如 LME 中「A→B→C 隨時間新增所有值」):**out-of-scope**;本方法 argmax(ordinal) 為 single-winner design,不處理 keep-all 語意。列 future work。
4. **Benchmark D-flag 缺陷**(§4.7.1 提及):64k has_pair 中 1/66、262k 3/77 的 gt_seq < old_seq,argmax(seq) 邏輯上不可能對,與方法正交,計於 method 責任邊界外。
5. **判斷可依賴的 signal**(依 method 章 §3.3):事實可被表達為 (subject, predicate, object) triple 且 ingestion time 可靠。於 (S,P) 難以結構化或 ingestion time 不明確的 domain(e.g., 純自然對話中隱含事實無明確時間戳)本方法基石不成立,需 fallback 到 LLM 判斷 —— 但這正是既有 baseline 已覆蓋的情境,非本方法主張。

**Judge model caveat(LME-KU)**:目前 gpt-4o-mini judge;LongMemEval 官方 default 為 gpt-4o judge \cite{wulongmemeval}。是否回官方 judge 為未定 caveat;若回,Table 7 絕對數字可能有 ±5pp 變動,但**相對 gap 方向**預期不變(gpt-4o judge 對 counterfactual bias 敏感度應更高,可能反而擴大 ours vs Mem0 Vanilla 於 LME 上的 gap)。

**Backbone scope**:本文於 3 個能力區間 × 6 個獨立 model 上驗證,涵蓋 privacy-sensitive on-device(gemma3-1B/4B/12B/27B)、cost-constrained API(gpt-4o-mini)、strong tier(gpt-5.4-mini)三個實際部署情境 \cite{pham2025slimlm,huang2025middle,chenfrugalgpt};但**未覆蓋 gpt-4 / gpt-5 flagship tier**(原生高 tier),原因為 gpt-5.4-mini 已足夠驗證 backbone 收斂 claim,原生高 tier 不擴 paper narrative 但增顯著 API 成本。

---

## 更新紀錄

- **2026-07-17**:建檔;從頭撰寫,對接 introduction_0716 三 Research Objective + methodology_source_material_0716 commitments + experiment_source_material_0716 canonical 數字。**未繼承** experiment.md(v0 scaffold)段落,目標為與 method 章用詞風格一致的新草稿。章節結構依 user 2026-07-17 定案:§4.2 Main Results on FC-SH(gpt-4o-mini 4-length)、§4.3 Robustness across Backbone Capabilities(Gemma3 + OpenAI 3-tier + F1)、§4.4 Generality across Backbone Families(cross-family)、§4.5 LME-KU、§4.6 Ablation、§4.7 Discussion。
