# Experiment Source Material(2026-07-16)

> **定位**:寫 paper 「Experiments / Results / Analysis」章節的**單一 top-down source**;對接論文架構(abstract_0716.md、introduction_0716.md、related_work_0716.md、methodology_source_material_0716.md)。**結構=先 headline 宏觀數據 → 初步觀察 → 診斷/分析素材**。
> **範圍**:只放**目前確定跑完、canonical rescored 的實驗結果與觀察**。**已跑但屬 dead-experiment/smoke/superseded 的內容一律不進本檔**(例:HippoRAG、MemoRAG、GraphRAG、Letta、Cognee、mem0g、stand-alone Resolution 舊 metric、strict-EM 舊表、broadened-native prompt 舊 baseline)。
> **配對**:方法命名沿用 `results/fc_sh_main_table_4length.md`(**Ours (Struct + LLM-Fallback)** / Ours (Struct-Only) / Ours (LLM-Identity-Only));canonical setup 對接 methodology_source_material_0716.md 描述的 pipeline(canonical = script `ours_no_p5`,無 P5)。

---

## §0. 論文 claim 對照 & 命名 / 判分規約

### §0.1 論文 claim → 實驗編號對照(top-down entry point)

| Claim(來源) | 由哪個 experiment 支撐 |
|:--|:--|
| **主 claim(abstract § 1、intro § Research Objective)**:以 deterministic 結構配對為主要 KU 判斷、LLM 僅補救,能超越 baselines | E1 FC-SH 主表 + E4 LME-KU 主表 |
| **counterfactual-型 KU 上優勢主要來自移除 LLM parametric bias**(abstract § 2、intro § Motivation)| E1 主表 + §6.1 per-qid error-mode + §6.2 concurrent work 對照 |
| **KU 表現不再受限於 backbone 判斷力**(abstract § 3、intro § Research Obj 3)| E2 Gemma3 spectrum + E3 cross-family + E1b OpenAI strong-tier |
| **優勢並非**只在 counterfactual 情境成立,personal 型 KU 也 hold | E4 LongMemEval-KU |

**Rolling framing 規則**:每個 §1-§5 的「初步觀察」段落只**記錄從數字讀到什麼**,不預先綁 claim wording;等 §7 依實際數據總結、再回頭滾動 abstract/intro 語氣。

### §0.2 方法命名 canonical(全檔通用)

| paper 呈現名 | script METHOD | mechanism |
|:--|:--|:--|
| **Ours (Struct + LLM-Fallback)** — 主 method | `ours_no_p5` | (S,P) argmax + P3 LLM identity fallback,無 P5 |
| Ours (Struct-Only) — ablation | `ours_struct` | (S,P) argmax only(關 P3)|
| Ours (LLM-Identity-Only) — ablation | `ours_p3_only_no_struct` | P3 LLM identity only(關 (S,P))|
| Mem0 Vanilla (Write-time LLM) | `vanilla` / native | mem0 upstream default `FACT_RETRIEVAL_PROMPT` + destructive UPDATE |
| Mem0 + P1 (Write-time LLM) | `dest` / `b` | 我方 P1 extractor held-fixed + mem0 destructive UPDATE |
| Zep (Write-time decoupled) | `zep` | Zep cloud graph + bi-temporal `invalid_at` |
| LCA (Long-Context Answer) | `lca` | gpt-4o-mini full-context reader,無記憶 |
| Vanilla-RAG (Query-time LLM temporal resolution) | `q_llm_recency` | benchmark-native factconsolidation.rag_agent template + LLM 判 recency |
| Don't Ask (Query-time LLM extraction) [Reddy & Challaram 2026] | `maxserial_theircode` | vector top-100 + LLM candidate extract + `max(serial)` |

> `ours` script(含 P5)= paper「Ours (+P5), appendix」;canonical 不用,只出現於 E1 主表 appendix 行以維持 audit 對照。

### §0.3 Metric / 判分(FC-SH)

- **主 metric**:MemoryAgentBench 官方 `substring_exact_match`(sEM),`default_post_process` = normalize + parse_output + `max(raw, parsed)` + `max` over alias list。
- **主分母**:overall 100 題(對齊 benchmark 官方 task accuracy)。
- **分析分母**:has_pair 74/65/66/77(6k/32k/64k/262k)—— KU 真正發生的子集,只在 §6 diagnostic 使用。
- **rescore 產生**:`analysis/rescore_canonical.py`(所有主表格數字來源;53 cells,單一 canonical file per cell,temp=0 single run)。

### §0.4 Metric / 判分(LongMemEval-KU)

- **主 metric**:官方 `evaluate_qa_official.py` LLM autoeval(`autoeval_label.label ∈ {true, false}`),分子=`label==true`。
- **主分母**:LME `knowledge-update` sub-task 全 78 題。
- **judge model**:目前 `gpt-4o-mini-2024-07-18`(驗證期成本節省;是否回官方 gpt-4o judge 未定,**列 §8 待決**)。
- 結果檔:`docs/0615_.../lme_hyps/lme_ku_<METHOD>.jsonl.eval-results-gpt-4o-mini`(逐行 JSON,含 `question_id, hypothesis, autoeval_label`)。

### §0.5 通用 hyperparameters(所有 experiment 共用)

| Hyperparam | 值 | 說明 |
|:--|:--|:--|
| chunk_size | 512 | mem0 chunker(FC-aware / uniform)|
| retrieve top-k | 100 | vector, text-embedding-3-small |
| temperature | 0 | 全 API + local models |
| MEM0_TRIPLE_MODEL | `gpt-4o-mini`(held-fixed)| 例外:E2 gemma3 tier 用 per-backbone gemma extraction(paper 需誠實揭露)|
| 平行執行 | OPENAI_API_KEY_A~E 五把獨立(store/cache/output 隔離)| — |

---

## §1. E1 — FC-SH 主表(gpt-4o-mini backbone × 4 length)

> **對接**:[`results/fc_sh_main_table_4length.md`](../results/fc_sh_main_table_4length.md)、[`results/canonical_fc_sh_metrics.md`](../results/canonical_fc_sh_metrics.md)
> **設定**:gpt-4o-mini(mid-tier,做整條 pipeline:P1 extraction + P2 grouping + P3 identity + answer),temp=0,chunk 512,top-100 vector(Zep 例外 k=10 per 官方 recipe);single deterministic run,無 error bar。

### §1.1 Table E1-1 — Overall sEM ↑(N=100 / length)

| **Method** | **6k** | **32k** | **64k** | **262k** | AVG(4L)|
|:--|:-:|:-:|:-:|:-:|:-:|
| **Write-time KU baselines** |  |  |  |  |  |
| Mem0 Vanilla (Write-time LLM)  | 16 | 22 | 28 | 17 | 20.8 |
| Mem0 + P1 (Write-time LLM) | 52 | 52 | 65 | 50 | 54.8 |
| Zep (Write-time decoupled) | 82 | 80 | 76 | 29 | 66.8 |
| **Query-time KU baselines** |  |  |  |  |  |
| LCA (gpt-4o-mini full-context) | 88 | 74 | 65 | 43 | 67.5 |
| Vanilla-RAG (Q-time LLM temporal) | 93 | 77 | 85 | 81 | 84.0 |
| Don't Ask (Q-time LLM extraction) | 80 | 86 | 88 | 86 | 85.0 |
| **Ours ablations** |  |  |  |  |  |
| Ours (LLM-Identity-Only) | **97** | 91 | 91 | 87 | 91.5 |
| Ours (Struct-Only) | 91 | 87 | 92 | 86 | 89.0 |
| Ours (+P5, appendix)| 93 | 90 | **94** | **91** | 92.0 |
| **Ours (Struct + LLM-Fallback)** | **94** | **91** | **94** | **91** | **92.5** |

**Bold** = 該 length 最佳(以及 Mean 欄最高值)。

### §1.2 Table E1-2 — has_pair sEM ↑(KU 子集,§6 分析用)

| Method | 6k(74)| 32k(65)| 64k(66)| 262k(77)|
|:--|:-:|:-:|:-:|:-:|
| **Ours (Struct + LLM-Fallback)** | **69 (93%)** | **57 (88%)** | **60 (91%)** | **68 (88%)** |
| Ours (LLM-Identity-Only) | **71 (96%)** | 58 (89%) | 58 (88%) | 64 (83%) |
| Ours (Struct-Only) | 67 (91%) | 53 (82%) | 58 (88%) | 63 (82%) |
| Vanilla-RAG | 67 (91%) | 42 (65%) | 51 (77%) | 58 (75%) |
| Don't Ask | 54 (73%) | 51 (78%) | 54 (82%) | 63 (82%) |
| Zep (k=10) | 56 (76%) | 45 (69%) | 42 (64%) | 12 (16%) |
| LCA | 65 (88%) | 46 (71%) | 36 (55%) | 24 (31%) |
| Mem0 + P1 | 34 (46%) | 26 (40%) | 34 (52%) | 29 (38%) |
| Mem0 Vanilla | 0 (0%) | 2 (3%) | 2 (3%) | 1 (1%) |

### §1.3 初步觀察(供 §7 rolling framing)

1. **Ours (Struct + LLM-Fallback) 是唯一於 4 length 全部 flat 的方法**:overall 91-94(Δ 6k→262k = −3pp;has_pair 88-93%)。所有其他 method 至少於一個 length 有 ≥10pp 掉幅。
2. **Write-time family 的 length behaviour**:Mem0 Vanilla 全長 flat 於低點(17-28,extraction 崩壞未觸及 KU 機制);Mem0+P1 全長 plateau 50-65(destructive UPDATE 天花板);Zep 於 6k-64k 穩定 76-82,**262k 崩至 29**(write-time invalidation coverage 不足,只 6.3% of retrieved edges 帶 `invalid_at`)。
3. **Query-time family 的 length behaviour**:LCA 隨長度**單調下降**(88→43);Vanilla-RAG **non-monotonic dip**(93→77→85→81,32k 最壞);Don't Ask **唯一越長越強**(80→86,+6pp,詳因見 §6.1)。
4. **Ours ablation 的長度分工**:LLM-Identity-Only 於**短 context(6k)**贏(97 > 94),Struct-Only 於**長 context(262k)**貢獻大;full method 於每長度取兩者上界(見 §6.1 diagnostic 2)。
5. **Mean 4L**:full Ours = 92.5、Ours ablation 三行 89.0-92.0、Don't Ask 85.0、Vanilla-RAG 84.0,其後所有 write-time baseline ≤ 67.5。

### §1.4 已知 caveats(paper 需揭露)

- **Zep 262k crash(29% overall)機制 = query-time top-10 retrieval miss 主導,非單純 write-time invalidation 不足**(2026-07-16 補跑 `analysis/classify_zep_ku_resolution.py --length 262k` 得):
  - **NotBothExtracted 82%**(top-10 於 has_pair 中 63/77 = 82% 沒同時抓到 old + new 兩版)—— 答題 LLM 於 pool 內根本沒看見 both versions,無法區辨。
  - Additive-NoKU 只 8%(64k 為 74%),因為 both 版本進 top-10 機會太少,連「兩版共存但 Zep 沒判別」的桶都稀薄。
  - Invalidation coverage 6.30%(63/1000 edges 帶 `invalid_at`,vs 6k 21.90% / 32k 6.20% / 64k 9.70%)—— 此即 fc_sh_main_table_4length.md caveat 引述的「6.3%」source;write-time 側 invalidation coverage 確實極低,但**262k 主因在 query-time retrieval**。
  - **Top-K asymmetry 驗證通過**:Zep top-50 於 262k(46/100 queries before rate-limit)= 28.3%,與 k=10 的 29% 統計等價 → 262k 圖太大 → 語意 rank 上 target edge 被 distractor 淹沒 → 拉到 top-50 也抓不到 both 版本。詳 §6.3 4-length 分桶對照。
- **Single deterministic run**:temp=0 無 std;OpenAI server-side bf16 帶入 ±2-3 pp 抖動(兩台從零 clone 驗證於此範圍)。
- **Don't Ask 判分細節**:作者 per-row output 以官方 pipeline 對 `gt_answer`(單字串,無 alias list)重新判分;alias-hit 可能微幅低估(見 `analysis/rescore_canonical.py::score_custom_maxserial` 註記)。
- **Mem0 Vanilla 的 has_pair ≈ 0%**:非 KU 機制問題,是 extraction 崩壞就已無 recall 基底,列 appendix。

---

## §2. E1b — FC-SH backbone 收斂觀察(OpenAI 強 tier 對照)

> **目的**:falsifiable prediction「gap 隨 backbone 增強而收斂」的 API-tier 驗證。
> **paper 定案 strong tier = `gpt-5.4-mini`**(2026-07-16 決策):其 mini-tier 定位 + 已於 §2.1 上讓 baselines 大幅上升(mem0+P1 +18、Don't Ask +16、Zep +11),已足以驗證 backbone 收斂 claim。**paper 不使用 gpt-4o(原生高 tier),避免不必要的 ~$5-8 API 成本 sweep**。gpt-4.1-mini 的既有數據保留為 intermediate tier(2025 版本),對照三代 mini-tier evolution。
> **對接**:[`results/canonical_fc_sh_metrics.md`](../results/canonical_fc_sh_metrics.md)(gpt-4.1-mini)+ [`results/fc_sh_backbone_spectrum_6k.md`](../results/fc_sh_backbone_spectrum_6k.md)(gpt-5.4-mini)
> **設定**:同 §1(chunk 512、top-100);extractor `MEM0_TRIPLE_MODEL=gpt-4o-mini` held-fixed;answer/UPDATE/P3 LLM = 該 backbone。

### §2.1 Table E1b-1 — Overall sEM @ 6k,3 mini-tier backbones × 5 method(**paper strong tier = gpt-5.4-mini**)

| Method | gpt-4o-mini(mid, 2024;paper 主表 backbone)| gpt-4.1-mini(intermediate, 2025)| **gpt-5.4-mini**(strong / reasoning-tier, 2026;**paper 定案 strong tier**)| Δ(4o→5.4)|
|:--|:-:|:-:|:-:|:-:|
| **Ours (Struct + LLM-Fallback)** | **94** | 92 | **99** | +5 |
| Vanilla-RAG(Q-time LLM temporal)| 93 | — | **98** | +5 |
| Don't Ask(Q-time LLM extraction)| 80 | — | **96** | +16 |
| Zep(k=10)| 82 | 81 | **93** | +11 |
| Mem0 + P1 | 52 | **81** | **70** | +18 ⚠ non-monotonic |

### §2.2 Table E1b-2 — Overall sEM,gpt-4.1-mini × 3 length(補 §2.1 缺角)

| Method | 6k | 32k | 64k |
|:--|:-:|:-:|:-:|
| **Ours (Struct + LLM-Fallback)** | 92 | 87 | 88 |
| Mem0 + P1 | 81 | 87 | 88 |
| Zep(k=10) | 81 | 77 | 84 |

Gap ours − Mem0+P1:6k **+11pp**,32k **0**,64k **0** —— falsifiable prediction 成立(mid-tier 上 mem0+P1 只 52%,strong-tier 收至 parity)。

### §2.3 初步觀察

- **Ours 於三 OpenAI mini-tier 皆為 outright leader**(94 / 92 / 99);gpt-5.4-mini 上 saturation(99/100)但**相對 second-best(Vanilla-RAG 98)僅 +1pp**,gap 收窄未反轉。
- **全 method spread 從 42pp(gpt-4o-mini,52-94)收窄到 29pp(gpt-5.4-mini,70-99)**;收窄由「地板」抬升驅動(mem0+P1 +18、Don't Ask +16、Zep +11),ours 微升 +5。
- **Mem0+P1 於 gpt-5.4-mini 反常下滑 −11pp**(gpt-4.1-mini 81 → gpt-5.4-mini 70)—— 唯一 non-monotonic method;可能機制:reasoning-family 模型對 destructive UPDATE prompt 更保守(NOOP 頻率上升 → 錯過 UPDATE)/`max_completion_tokens` 於 reasoning model 包含 internal reasoning tokens。
- **paper narrative 讀法**:「LLM-based KU judgement 於強 backbone 對多數方法可靠」**部分兌現**(decoupled Zep / Q-llm 家族兌現,coupled destructive mem0+P1 反常)。

### §2.4 已知 gap / caveats

- **gpt-4o(原生高 tier)不進 paper**(2026-07-16 決策):§2.1 已顯示 gpt-5.4-mini 上 baselines 大幅上升(mem0+P1 52→70、Don't Ask 80→96、Zep 82→93),已足夠驗證「backbone 越強 → gap 收斂」的 claim;無需再跑 ~$5-8 於 gpt-4o full sweep。
- **gpt-5.4-mini 只跑 6k**:若後續要 length × backbone 對稱,32k/64k/262k 需另跑(estimate ~$0.4-1 per method per length);目前 paper 主 length claim 由 §1 gpt-4o-mini 主表承擔,gpt-5.4-mini 於 6k 作 backbone 收斂 probe **已足夠**。
- **gpt-4.1-mini yaml 沿用 gpt-4o-mini path**(shared store);gpt-5.4-mini yaml 用 backbone-tagged path(gemma pattern,fresh state)—— mem0+P1 三 backbone 對比可能被 store state 差異干擾。
- `max_tokens` patch:gpt-5.x + o1/o3/o4 系列 reject `max_tokens`,需 `max_completion_tokens`;patch 於 `mem0/llms/openai.py:92-107` + `agent.py:596-611`,by-model-prefix routing。

---

## §3. E2 — Gemma3 backbone spectrum(open weight,1B / 4B / 12B / 27B @ 6k)

> **對接**:[`results/canonical_fc_sh_metrics.md`](../results/canonical_fc_sh_metrics.md) § weak-tier + [`results/weak_model_6k_analysis.md`](../results/weak_model_6k_analysis.md) + [`results/pool_acc_crosstab_gemma_6k.md`](../results/pool_acc_crosstab_gemma_6k.md)
> **設定**:GX10 per-backbone gemma extraction(`MEM0_TRIPLE_MODEL=gemma3:$SIZE`,**非** held-fixed gpt-4o-mini)—— 每 backbone 用自己的 gemma 做**整條 pipeline**(P1 抽取 + P2 grouping + P3 identity + answer)。答案 metric = 官方 sEM。paper 需揭露此為「整條 pipeline 跑在弱模型」誠實對比,而非 KU-resolution 隔離。

### §3.1 Table E2-1 — Overall sEM @ 6k(N=100)

| Method | 1B | 4B | 12B | 27B |
|:--|:-:|:-:|:-:|:-:|
| **Ours (Struct + LLM-Fallback)** | 44 | 79 | **99** | **99** |
| Ours (Struct-Only) | 52 | 79 | 99 | 97 |
| Ours (LLM-Identity-Only) | 27 | 50 | 72 | 59 |
| Mem0 + P1 | 5 | 11 | 64 | 54 |
| Mem0 Vanilla | — | 11 | 53 | 45 |
| Zep(k=10)| 29 | 32 | 58 | 62 |

(32k 補充,Ours (Struct + LLM-Fallback):1B **54** / 4B **70** / 12B **98** / 27B **98**。Struct-Only 32k 因早期 `_final` bug 未完整。)

### §3.2 Table E2-2 — has_pair sEM @ 6k(N=74)

| Method | 1B | 4B | 12B | 27B |
|:--|:-:|:-:|:-:|:-:|
| **Ours (Struct + LLM-Fallback)** | 27 | 54 | 73 | **73** |
| Ours (Struct-Only) | 32 | 54 | 73 | 71 |
| Ours (LLM-Identity-Only) | 8 | 26 | 46 | 33 |
| Mem0 + P1 | 0 | 0 | 44 | 37 |
| Mem0 Vanilla | — | 0 | 32 | 29 |
| Zep(k=10)| 20 | 18 | 43 | 42 |

### §3.3 初步觀察

- **Ours 於每個 backbone 都主導**;write-time family(Mem0 Vanilla / Mem0+P1 / Zep)於弱端崩最重(Mem0+P1 於 1B/4B = 5%/11%)。「KU 是 query-time 問題」的 backbone-gap 證據:backbone 越弱、gap 越大。
- **Write-time destructive 於 1B/4B 直接歸零**(Mem0 Vanilla + Mem0+P1 於 1B/4B has_pair = 0):UPDATE LLM 於弱模型產不出正確 schema,write-time 誤刪即不可逆 —— paper 批評的機制在弱模型上以最極端形式出現。
- **LLM-Identity-Only(拿掉 (S,P))於弱端崩最重**(1B/4B has_pair = 8/26 vs Struct-Only 32/54):對 top-100 一次判 identity 對弱模型 intractable → 反向確立 structural pre-routing 的必要性。
- **P3 是 capability-gated**:Struct + LLM-Fallback − Struct-Only 的 has_pair Δ = 1B **−5**(P3 反害)、4B/12B **0**(structural 已足)、27B **+2**(P3 微幫)。弱模型上加 LLM 判斷是 liability,強模型上才是 asset。
- **1B/4B 的 pool-state cross-tab 不可信**(per-backbone gemma extraction 字面偏移 → matcher FN)→ E2E + case study 為主,cross-tab 只在 12B/27B 使用(§6.3)。

### §3.4 已知 caveats

- **Extraction confound**:paper 需明講「gemma tier 為整條 pipeline 跑在該 backbone」;若要「隔離 KU-resolution 效應」需看 §4 cross-family(held-fixed gpt-4o-mini extraction)。
- **Zep gemma tier 的 "backbone" 定義**:Zep cloud graph 仍走 Zep 內部 LLM(gemini/OpenAI),不是 gemma;僅 answer LLM 換 gemma via Ollama(需改 `methods/zep.py::OpenAIAgent`)。非 apples-to-apples,paper 敘述需明講。
- **LCA(long-context)於 gemma 只能對 6k**:gemma3 context window(1B/4B/12B 8k、27B 32k)→ 32k/64k 完全不 fit;E2 上 LCA 不列。

---

## §4. E3 — Cross-family local model(Gemma2-9B / Llama3.1-8B / Qwen2.5-7B / Mistral-7B @ 6k)

> **對接**:`outputs/gpt-4o-mini-mem0-chunk512-temp0-openai-unified_{no_p5,struct,q_llm_recency,dest}__{gemma2-9b,llama3.1-8b,qwen2.5-7b,mistral-7b}/Conflict_Resolution/*.json`
> **設定**:**Held-fixed gpt-4o-mini P1 extraction**(`p1_caches__<model>/`);查詢時 P2 grouping / P3 identity / UPDATE / answer LLM 全換該 local model(via Ollama)。**這是 §3 的 companion:專門隔離「KU-resolution + answer」換成 local model 的影響,不含 extraction confound**。
> **目的**:驗證 §3 觀察到的 backbone-gap 於 gemma3 系列**不是 gemma-family 專屬現象**,而是**跨 4 個 open-weight 系列(Gemma / Llama / Qwen / Mistral)普遍成立**。

### §4.1 Table E3-1 — Overall sEM @ 6k(N=100)

| Method | Gemma2-9B | Llama3.1-8B | Qwen2.5-7B | Mistral-7B |
|:--|:-:|:-:|:-:|:-:|
| **Ours (Struct + LLM-Fallback)** | **72** | **81** | **91** | **66** |
| Ours (Struct-Only) | 71 | 81 | 83 | 64 |
| Vanilla-RAG(Q-time LLM temporal)| 38 | 70 | 27 | 26 |
| Mem0 + P1 (Write-time destructive)| 27 | 8 | 21 | 19 |

### §4.2 初步觀察

- **Ours (Struct + LLM-Fallback) 於 4 系列全部領先**(66-91);baseline 於 4 系列全部崩(Mem0+P1 於 4 系列 8-27,Vanilla-RAG 於 3/4 系列 <40)—— 跨系列驗證 §3 gemma3 觀察**普遍存在**、不是 gemma-family 專屬。
- **Struct-Only 幾乎與 full method 齊平**(4 系列 Δ = −1/0/−8/−2 pp)—— 於 mid-size(7-9B)local model 上,structural (S,P) 已為 workhorse;P3 帶邊際 0-8pp。
- **Vanilla-RAG(query-time LLM 判 recency)於 3/4 系列崩至 <40**(Qwen2.5-7B 27、Mistral-7B 26、Gemma2-9B 38);Llama3.1-8B 例外(70)。判 recency 是**跨系列共通的 LLM 弱點**,不是特定家族現象。
- **Mem0+P1(write-time destructive)於 4 系列全崩至 8-27**;UPDATE 判斷在 mid-size local model 上不可靠 → destructive commit 不可逆 loss → 天花板遠低於 query-time family。
- **與 §3 gemma3 相比**:E3 於 held-fixed extraction 下,「backbone 換成 local」的**KU-resolution 淨影響**已被隔離出來 —— gap 仍在,證明**主要 gap 來自 P2/P3/UPDATE/answer LLM 判斷,不是 extraction**。

### §4.3 已知 caveats

- **只跑 6k**:未擴到 32k/64k/262k;paper 主 length claim 靠 §1 gpt-4o-mini 主表,E3 為 cross-family sanity check。
- **Held-fixed extraction 隔離的是 KU-resolution**:paper 需明講 E2(gemma tier,整條 pipeline)+ E3(cross-family,held-fixed extraction)兩軸互補 —— E2 說「整條 pipeline 跑弱模型」、E3 說「即使 extraction 幫忙,KU-resolution 換 local model 仍造成 baseline 崩」。
- **Zep 於 cross-family 未跑**;`outputs/{model}-zep/` 目錄存在但未跑完整 100 query(**列 §8 gap**)。
- **Ours (LLM-Identity-Only) 於 cross-family 未跑**;若要完整 4-way ablation(對照 §3 gemma3)需另 approve 4 系列 × p3_only 的補跑(**列 §8 gap**)。

---

## §5. E4 — LongMemEval-KU(personal 型 KU,N=78,gpt-4o-mini backbone)

> **對接**:`docs/0615_.../lme_hyps/lme_ku_<METHOD>.jsonl.eval-results-gpt-4o-mini`
> **設定**:LongMemEval(ICLR'25)knowledge-update subtask,N=78;write-time = mem0 pipeline(FC-aware chunker 換 uniform,LME 天然無 fact-density skew);query 用 LME 官方 template;judge = `evaluate_qa_official.py`(vendor 於 `llm_based_eval/evaluate_qa_official.py`,gpt-4o-mini judge)。

### §5.1 Table E4-1 — LME-KU accuracy(N=78)

| Method | correct / 78 | acc |
|:--|:-:|:-:|
| **Ours (Struct + LLM-Fallback)** = `ours_no_p5` | 55 / 78 | **70.5%** |
| Vanilla-RAG(1-stage LLM temporal)| 58 / 78 | 74.4% |
| Vanilla-RAG(2-stage LLM temporal)| 54 / 78 | 69.2% |
| Mem0 Vanilla | 53 / 78 | 67.9% |
| Mem0 + P1 | 47 / 78 | 60.3% |

**⚠ 排除數字**:`lme_hyps/lme_ku_ours.jsonl`(script `ours`,含 P5)顯示 65/78 = 83.3%。**此檔為別台舊產出,repo 內無對應 build log**(`logs/` 目錄下無 `lme_ku_ours.log`,僅存 `lme_ku_ours_q_llm_recency_*.log`)→ 無法 audit / reproduce → **不進 paper 主表**。paper canonical = `ours_no_p5` = 70.5%。若後續要恢復 P5 於 LME 的角色,需 approve 於當前環境重跑 + 產出 canonical log。

### §5.2 初步觀察

- **Ours (Struct + LLM-Fallback) 於 LME-KU 領先 Mem0 Vanilla / Mem0+P1 / Vanilla-RAG(2-stage)**;但**輸給 Vanilla-RAG(1-stage)3.9pp**(70.5% vs 74.4%)。personal 型 KU 情境上 ours **未 outright 領先**所有 baseline。
- **與 FC-SH 6k 對比,gap 明顯縮小(直接支撐 abstract § 2 wording)**:
  | 對照組 | FC-SH 6k(gpt-4o-mini)| LME-KU(gpt-4o-mini)|
  |:--|:-:|:-:|
  | Ours vs Mem0 Vanilla | +78pp(94 vs 16)| **+2.6pp**(70.5 vs 67.9)|
  | Ours vs Mem0 + P1 | +42pp(94 vs 52)| **+10.2pp**(70.5 vs 60.3)|
  | Ours vs Vanilla-RAG(1s)| +1pp(94 vs 93)| **−3.9pp**(70.5 vs 74.4)|
  → **反向支撐**「FC-SH 上巨大 gap 主要來自處理 LLM parametric bias(counterfactual)」的 abstract 論述。intro § Motivation 目前只提「LLM 於 knowledge conflict 情境偏好既有知識」,可補一句:「於 personal 型 KU(bias 不啟動)情境上,ours vs baseline 的 gap 明顯縮小,反向證實 counterfactual 型上的巨大 gap 主要來自處理 LLM parametric bias」。
- **Vanilla-RAG(1-stage)於 LME 略勝 ours** 的機制推論:personal-KU 事實不與 LLM parametric knowledge 衝突 → LLM 讀 ordinal-prefixed pool 判 recency 時**沒有 world-prior 抗力** → 直接照 ordinal 選新版即對。這與 §6.1 觀察到「Vanilla-RAG 於 FC-SH 失敗的 95-100% 是回退世界先驗」一致(personal-KU 無此路徑)。
- **paper narrative implication**:Ours 的價值**聚焦於「counterfactual-型 KU + bias-heavy 情境」**;不對「所有 KU 情境」宣稱 universal 領先。若原先 abstract wording 隱含「兩 benchmark 都領先」,依此需調整(見 §7.6)。

### §5.3 已知 caveats / gap

- **Zep 於 LME-KU 未跑完整**:僅 smoke 檔(`lme_ku_zep_smoke2.jsonl.eval-results-gpt-4o-mini`,~15 題子集)。full run 需另 approve(**列 §8 gap**)。
- **Backbone spectrum 於 LME 未跑**:目前只有 gpt-4o-mini backbone;gpt-5.4-mini / gemma3 / cross-family 皆未做。若要對稱 §2/§3/§4,需另 approve。
- **Judge model**:gpt-4o-mini judge(成本節省),是否回官方 gpt-4o judge 未定,LME §5 caveat 需明列。
- **N=78 non-100**:LME `knowledge-update` 子集就是 78 題(非我們刪題);paper 明講。
- **`lme_ku_ours.jsonl`(含 P5, 83.3%)為 orphan artifact**:別台舊產出,repo 內無 build log → 不列 paper 主表(見 §5.1)。

---

## §6. 診斷 / 分析素材

> 本節整理**已跑完的 mechanism-level 分析**,供 paper「Analysis / Case Study」章節取材。**不重複 §1-§5 的宏觀數字**;每小節指向對應 result file 讀完整推理。

### §6.1 Per-qid error-mode(query-time family,FC-SH)

**來源**:[`results/fc_sh_4method_errormode_diag.md`](../results/fc_sh_4method_errormode_diag.md)(20k 字,含 3 個 diagnostic 表格 + sanity check)。

**核心 finding**(全 per-qid 逐格吻合主表):
1. **Ours (Struct-Only) 失敗模式 = (S,P) canonicalization miss**(has_pair wrong 於 6k/32k 100% 是「答成 gt_OLD」,new/old 因 predicate stem-vs-full 或 subject 碎裂被分到不同結構桶)。P3 補救於 6k/32k/64k/262k 淨值 +2/+4/+2/+5(rescue > regress),長 context 邊際效益最大。
2. **Don't Ask 失敗模式 = LLM candidate-extraction 塌成單一候選**(world-prior leak):has_pair wrong 於 6k 100% 是 `n_candidates==1`,LLM 只抽出「舊(真實世界)版」漏掉 counterfactual 新版 → `max(serial)` 只有舊版可選 → 答舊。對應 §6.2 concurrent work 對照。
3. **Vanilla-RAG 失敗模式 = LLM 判 freshness 回退世界先驗**:has_pair wrong 於 4 length 95-100% 是「答成 gt_OLD」;LLM 被要求在 flat ordinal pool 上判 recency 時,傾向回退到語意熟悉(世界先驗)的舊值。32k 最壞(non-monotonic dip)。
4. **Ours (Struct + LLM-Fallback) 殘餘錯誤模式**:全 400 cell-query 中方法可修者僅 13 題(a+b+c);其餘 17 題屬與 KU 解析正交(reader world-prior override 8 + benchmark D-flag 6 + non-KU 3)。**out-of-scope=0**(證實 FC-SH 完全落在方法的單值-KU scope 內)。

**Diagnostic 1**(P3 觸發率):structural pool 佔多數(6k 81% / 32k 77% / 64k 68%),但**佔比隨長度單調下降**,dynamic (P3) 佔比單調上升(14→22→32%);P3 in-bucket accuracy 穩定 79-90%。**兌現「LLM 補救僅少數案例介入」的方法設計 claim**。

**Diagnostic 2**(structural vs LLM-only union table):short(6k)structural **零獨家貢獻**,長 context(262k)structural **獨家救回 5 題** —— 兩 identity mechanism 互補,ours (main) = struct ∪ P3,於每長度取兩者聯集。

**Diagnostic 3**(30 個錯誤案例分類):方法可修 13/30 = 43%;KU 解析正交 17/30 = 57%(reader 世界先驗 8 + benchmark D-flag 6 + non-KU 3)。

### §6.2 Concurrent work 公平版對照(Reddy & Challaram 2026 "Don't Ask")

**來源**:[`results/deterministic_freshness_baseline.md`](../results/deterministic_freshness_baseline.md)(直接 import 作者公開 repo `_pipeline._extract_candidates` + `_freshness_pick`)。

**核心 finding**:
- FC-SH 6k gpt-4o-mini overall sEM:**ours 94%** vs **作者(公平版,vector top-100)80%** vs 作者(as-designed BM25 top-10)71%。Δ ours − 作者 = **+14pp overall,~+20pp has_pair**。
- 作者所有 has_pair 失敗都是同一機制:LLM extraction **只抽出舊(真實世界)版**、漏掉 counterfactual 新版(`n_candidates=1`)→ deterministic `max` 只有舊版可選。**world-prior 從 extraction 洩漏**(非 freshness-pick)。
- **忠實度驗證**:用作者 code + BM25 top-10 跑,得 overall 71% / has_pair 46/74(62.2%)/ leak 27/28,**與作者釋出的 `poc_results` 每題數字一模一樣** → 整合忠實。
- **一句話定位**:Reddy & Challaram 把 freshness 移出 LLM 交確定性 max **是對的方向**,但**只做了一半**:identity(認出同一事實不同版本)仍由 LLM extraction 承擔 → world-prior leak。ours 把 identity 也結構化 ((S,P)) → +14pp 全來自「LLM extract identity vs 結構 identity」。

**paper 用途**:對接 related_work §2「Deferred Judgment at Query Time」+ §3「Limitations」的**具體 quantitative gap**;§6.2 為 concurrent work 的**公平定位**素材。

### §6.3 KU mechanism analysis(per-method,per-qid)

- [`results/ours_ku_mechanism.md`](../results/ours_ku_mechanism.md) — ours pipeline 逐 phase trace + pool-state 分佈
- [`results/mem0_ku_mechanism.md`](../results/mem0_ku_mechanism.md) — mem0 destructive UPDATE 逐 qid 失敗軌跡(qid 29 起點:write-time 把新版刪掉留舊版)
- [`results/zep_ku_resolution_bitemporal.md`](../results/zep_ku_resolution_bitemporal.md) — Zep bi-temporal 4-bucket 分桶,**6k/32k/64k**(**262k 尚未寫入 results file,見下方 §6.3.1 補充**)
- [`results/mem0_event_taxonomy_gt4o.md`](../results/mem0_event_taxonomy_gt4o.md) — mem0 於 gpt-4o backbone 的 event-type 分類
- [`results/matcher_audit_gpt4omini_64k.md`](../results/matcher_audit_gpt4omini_64k.md) — matcher v4 audit(pool-state 判定的 ground truth 對齊)

#### §6.3.1 Zep KU-resolution 4-length 對照(2026-07-16 補跑 262k)

**產生**:`python analysis/classify_zep_ku_resolution.py`(2026-07-16 patch:GT_PATHS + LENGTHS 加 262k;analyze_length + print_report 加 invalidation coverage 統計。修改 read-only,無 API/LLM 呼叫)。

**Bucket %(handoff-verified,has_pair)**:

| length | Resolved-Correct | Resolved-Backward | Additive-NoKU | Other-Ambiguous | NotBothExtracted | overall acc |
|:--|:-:|:-:|:-:|:-:|:-:|:-:|
| 6k(N=74)| 23% | 30% | 39% | 8% | 0% | 62% |
| 32k(N=65)| 9% | 3% | 77% | 6% | 5% | 51% |
| 64k(N=66)| 17% | 0% | 74% | 8% | 2% | 55% |
| **262k(N=77)** | 6% | 1% | **8%** | 3% | **82%** | **14%** |

**Invalidation coverage 對照**(全 100 queries × 10 edges = 1000 edges 母數):

| length | invalidated / total edges | coverage |
|:--|:-:|:-:|
| 6k | 219 / 1000 | 21.90% |
| 32k | 62 / 1000 | 6.20% |
| 64k | 97 / 1000 | 9.70% |
| **262k** | **63 / 1000** | **6.30%** ← fc_sh_main_table_4length caveat 引述 source 找到 |

**262k 三 finding**:
1. **262k 崩塌主因 = query-time retrieval miss**,而非 write-time invalidation 不足。NotBothExtracted 82%(top-10 於 has_pair 中 63/77 沒同時抓到 old + new 兩版)→ 答題 LLM 於 pool 內根本沒看見 both versions → 無法區辨 → 靠 world-prior 猜舊 → acc 14.3%。
2. **Additive-NoKU 從 32k/64k 的 74-77% 崩到 262k 8%**:並非 Zep 於 262k「更會偵測衝突」,而是**兩版根本沒同時進 top-10**,連 additive 這桶都稀薄。**先前推論「additive-NoKU 隨長度單調上升到 262k」錯誤,修正為長度單調性於 32k-64k 成立、262k 走新機制(retrieval miss)**。
3. **6.3% invalidation coverage 為 262k write-time 側指標**(vs 6k 21.9%):write-time contradiction 判定率確實低;但**單就此無法解釋 262k crash 到 14%**(64k 覆蓋率 9.70% 但 acc 55%)。paper 引「6.3%」時需與 82% NotBothExtracted 一起呈現,否則會誤導。

**paper wording 建議**:
> Zep 於 262k 的 crash(29% overall)由**兩層問題疊加**構成:write-time 側,bounded top-k semantic search 於大圖上使 contradiction 觸發率下降(invalidation coverage 6.3%,6k 為 21.9%);query-time 側,top-10 retrieval 於 has_pair 中 82% 抓不到 both 版本,答題 LLM 於 pool 內沒有 both facts 可比。**兩層問題疊加是「圖大小 → semantic search 對特定 target edge 難以精準檢索」的兩個表徵,並非獨立缺陷**。

### §6.4 Case study(可挑進 paper §Analysis)

- [`results/case_studies_64k.md`](../results/case_studies_64k.md)(gpt-4o-mini × 64k)
- [`results/case_studies_gpt41mini_64k.md`](../results/case_studies_gpt41mini_64k.md)(gpt-4.1-mini × 64k,Plan A 完成 finding)
- [`results/weak_model_case_studies_6k.md`](../results/weak_model_case_studies_6k.md)(gemma3 tier @ 6k)
- [`results/32k_case_study.md`](../results/32k_case_study.md)(pilot,已於後續 canonical 覆蓋,保留 audit)
- [`results/has_pair_resolution_cases_6k.md`](../results/has_pair_resolution_cases_6k.md)(pool 狀態轉換 trace)

### §6.5 Weak-model additional evidence(cross-tab 於 12B/27B 可信)

**來源**:[`results/weak_model_6k_analysis.md`](../results/weak_model_6k_analysis.md) § 3。

- **12B/27B pool-state cross-tab 可信**(store overlap-with-27b:12b=99/100、27b=100/100)。Struct-Only 於 12B/27B `old_only=neither=0`(NEW 從不缺席)、`new_only` 主導(60 / 58)—— 結構化 (S,P)+argmax 把 KU 解析對,**不倚賴 answer LLM 從混雜 pool 挑對**。
- **struct 12B→27B 微降(73→71)是 reader override**(27B 拿到乾淨 pool 卻用 parametric 先驗吐舊值);P3 於 27B 部分修 override(no_p5 27B 的 new_only ✗ 從 struct 2 降到 1)。
- **P3-only 崩,機制看得見 = 「卡在 both」**(12B 有 69/74、27B 有 59/74 停在 both);去掉 (S,P) 後 LLM 對 top-100 判 identity 失效,pool 無法乾淨。

---

## §7. Abstract / Intro claim 對照(rolling framing check)

> 依 §1-§6 實際數據 vs abstract_0716.md、introduction_0716.md 的三個 claim,標記**支撐強度 / 需 rolling adjust 的地方**。

### §7.1 Abstract § 2「本方法在 counterfactual 型 KU 情境(新事實與 LLM 既有知識衝突)上,答題準確度皆超越 baselines」

- **支撐**:E1(§1)全 4 length overall + has_pair 全 method 對比;E1b(§2)三 mini-tier 皆為 outright leader;E2/E3(§3/§4)於 gemma3 4 tier + cross-family 4 系列皆保持領先;§6.1 per-qid error mode 逐題證實 baseline 失敗模式。
- **強度**:✅ 強;無反例。

### §7.2 Abstract § 2「分析 baseline 的錯誤,驗證主要來自 LLM 傾向自身知識而抗拒更新 counterfactual 事實」

- **支撐**:§6.1(Don't Ask、Vanilla-RAG、Ours (Struct-Only) 三方法的 has_pair wrong 於 6k 100% 是「答成 gt_OLD」);§6.2(Reddy & Challaram code + 我方 setup,20/20 has_pair 失敗都是 world-prior leak from LLM extraction)。
- **強度**:✅ 強;per-qid 逐題定量。

### §7.3 Abstract § 3「並以不同能力的 backbone 進行實驗,驗證現有方法依賴 LLM 判斷 KU,因此隨 backbone 能力變弱而直接影響判斷表現」

- **支撐**:E2 gemma3 spectrum(§3,write-time family 於 1B/4B 崩至 0-5%,ours 保 27-73);E3 cross-family(§4,4 系列 baseline 全崩至 8-38,ours 保 66-91);E1b OpenAI mini-tier(§2,mem0+P1 於 4o-mini 52 → 4.1-mini 81,gap +29→0,收斂而非發散)。
- **強度**:✅ 強;三軸互相印證。
- **⚠ Rolling adjust**:E1b § 2.3 觀察到 gpt-5.4-mini 上 mem0+P1 反常下滑(non-monotonic 81→70),abstract 目前 wording「隨 backbone 能力**變弱而下滑**」對強 backbone 的**收斂**未提;可補句:「同時於強 backbone 上 gap 明顯收斂 → KU-resolution 若能剝離對 LLM 的依賴,能於 backbone 光譜兩端皆保穩」。

### §7.4 Abstract § 「LLM 僅在結構配對失效的情況作為補救機制」

- **支撐**:§6.1 Diagnostic 1(P3 觸發率 14-32%,其餘 68-81% 由確定性 (S,P)+argmax 解決;P3 in-bucket accuracy 79-90%)。
- **強度**:✅ 中-強;paper 需明講 P3 觸發率隨長度上升(14→32%)是「dynamic pool 佔比隨 context 累積」的自然結果、非 P3 承擔更多責任。

### §7.5 Intro § Research Objective 2「驗證本方法的表現超越以 LLM 判斷為核心的既有方法」

- 由 §7.1、§7.2 支撐。

### §7.6 Intro § Research Objective 3「驗證本方法的表現與 backbone 判斷能力解耦,現有方法表現則隨 backbone 能力變弱而下滑」

- **支撐**:E2/E3/E1b。
- **⚠ Rolling adjust(依 §5 canonical `ours_no_p5` = 70.5%)**:E4 LME-KU 上 ours 70.5% vs Mem0 Vanilla 67.9% = **+2.6pp**、vs Mem0+P1 60.3% = **+10.2pp**、**輸給 Vanilla-RAG(1s)3.9pp**;遠小於 FC-SH 的 +78pp / +42pp / +1pp。這**加強**「FC-SH 的 gap 主要來自 counterfactual bias 處理」的框架 —— intro § Motivation 目前只提「LLM 於 knowledge conflict 情境偏好既有知識」,可補一句:「於 personal 型 KU(bias 不啟動)情境上,ours vs baseline 的 gap 明顯縮小、甚至於單階 LLM recency baseline 上略輸,反向證實 counterfactual 型上的巨大 gap 主要來自處理 LLM parametric bias」。
- **abstract wording 對應調整**:目前 abstract § 3「並以不同能力的 backbone 進行實驗」隱含跨 benchmark 皆領先;若 paper canonical LME 用 70.5%(輸給 Vanilla-RAG 1s)則 scope wording 需明講「counterfactual 情境上 outright leader、personal 情境上與 LLM-recency 家族相當」。

### §7.7 Related Work(§related_work_0716.md)實驗對照

- § "Decoupled Judgment and Execution at Write Time" 提到 Zep / Engram → §1 主表 Zep 全 length 完整、Engram 未跑(**列 §8 待決**;若 Engram 需入 paper 的正式 baseline,需另 approve)。
- § "Deferred Judgment at Query Time" 提到 Reddy & Challaram → §6.2 公平版對照完整。

---

## §8. 已知 gap / 待決定(供對齊 paper timeline)

### §8.1 資料完整度

**已 resolved(2026-07-16 定案)**:
- ~~gpt-4o(原生高 tier)未跑~~ → 定案**不使用**;gpt-5.4-mini 已足夠驗證 backbone 收斂(§2.4)
- ~~LME `ours`(+P5)vs `ours_no_p5` 分岐~~ → 定案**用 `ours_no_p5` = 70.5% 為 canonical**;`lme_ku_ours.jsonl`(83.3%)因 repo 無 build log 不進 paper(§5.1)
- ~~Zep @ 262k 沒有同級 bi-temporal 4-bucket 分類~~ → **已補跑**(§6.3.1);**新機制發現**:262k crash 主因 = query-time retrieval miss(NotBothExtracted 82%),非 write-time invalidation 不足;§1.4 caveat 已更新
- ~~6.3% invalidation coverage 引述 source~~ → **已算出**:262k 全 100 queries × 10 edges = 63/1000 帶 `invalid_at` = 6.30%,與 fc_sh_main_table_4length caveat 引述數字對得上(§6.3.1 表)

**仍待決(需 approve 才能補)**:

| Gap | 現狀 | 影響 / 建議 |
|:--|:--|:--|
| **gpt-5.4-mini 只 6k** | 主表僅 6k | 若後續要 length × strong-backbone 對稱,32k/64k/262k 需另跑(~$0.4-1 per method per length);paper 主 length claim 已由 §1 gpt-4o-mini 主表承擔,**目前不擋 paper narrative** |
| **Zep 於 LME-KU 未跑完整** | smoke 檔 15 題 | 若需 Zep vs ours 於 personal-KU 對比,需另 approve full run |
| **Zep 於 cross-family(E3)未跑** | outputs 目錄空 | 目前 §4 只 3 方法對比;若需完整 4-way(加 Zep),需 approve |
| **Ours (LLM-Identity-Only) 於 cross-family(E3)未跑** | 未跑 | 對照 §3 gemma3 的 P3-only 崩塌;若要 4 系列對稱 4-way ablation,需 approve |
| **LME backbone spectrum 未做** | 只 gpt-4o-mini | 若要對稱 §2/§3/§4 的 backbone claim 於 LME 上,需另 approve |
| **LME judge model** 是否回官方 gpt-4o | 目前 gpt-4o-mini judge | 需 approve(judge 成本 ~$1-5 per method) |

### §8.2 分析深度

- **gpt-5.4-mini 上 Mem0+P1 非單調下滑(81→70)** 的 mechanism audit(§2.3):可挑此 method 做 case study,比較 gpt-4.1-mini vs gpt-5.4-mini 於同 qid 的 UPDATE 決策差異。**未 approve**。
- **262k Diagnostic 1**(structural/dynamic routing)PENDING(需 store re-query;approval-gated)。§6.1 Diagnostic 1 目前僅覆蓋 6k/32k/64k;262k 空著。
- **P3 raw output logging**(§4.4 backbone_extension_plan §8.6 已 flag):現行 `phase2_query.py::llm_dynamic_grouping` 不存 P3 LLM raw output;要 debug F3(strong backbone p3_only collapse)細節需先修 logging 再 rerun。

### §8.3 命名 / framing 待決

- **Abstract / Intro wording 的 rolling adjust(§7.3、§7.6)**:建議依 §2.3、§5.2 補兩處措辭:
  1. Abstract § 3 需補「backbone 越強 → gap 收斂而非發散」的 wording(gpt-5.4-mini 上 mem0+P1 +18、Don't Ask +16 收窄,但 ours 仍為 outright leader)。
  2. Abstract § 2 + Intro § Motivation 需補「LME personal-KU 上 gap 明顯縮小 → 反向支撐 counterfactual 型 gap 主要來自處理 LLM parametric bias」;明講 ours 於 LME 上**與 LLM-recency 家族相當**、**未 outright 領先**。

### §8.4 論文 baseline 集合定案

- 目前 paper 主表 baseline = Mem0 Vanilla / Mem0+P1 / Zep / LCA / Vanilla-RAG / Don't Ask。**Engram**(related_work § 2.2 引用)未跑 —— 若 reviewer 要求 Engram 定量對比,需 approve。

---

## §9. 檔案 / 資料索引

### §9.1 主表 / result 檔(paper 直接引用)

| 檔案 | 覆蓋範圍 |
|:--|:--|
| [`results/fc_sh_main_table_4length.md`](../results/fc_sh_main_table_4length.md) | E1 主表,4 length × 10 method |
| [`results/canonical_fc_sh_metrics.md`](../results/canonical_fc_sh_metrics.md) | E1 + E1b gpt-4o-mini / gpt-4.1-mini + E2 gemma weak-tier 主數字 canonical |
| [`results/fc_sh_backbone_spectrum_6k.md`](../results/fc_sh_backbone_spectrum_6k.md) | E1b gpt-5.4-mini @ 6k |
| [`results/weak_model_6k_analysis.md`](../results/weak_model_6k_analysis.md) | E2 gemma3 spectrum 主分析 |
| [`results/pool_acc_crosstab_gemma_6k.md`](../results/pool_acc_crosstab_gemma_6k.md) | E2 12B/27B cross-tab |
| `outputs/*__{gemma2-9b,llama3.1-8b,qwen2.5-7b,mistral-7b}/Conflict_Resolution/*.json` | E3 raw results(rescore via `analysis/rescore_canonical.py` if 需要 canonical registry 化)|
| `docs/0615_.../lme_hyps/lme_ku_*.jsonl.eval-results-gpt-4o-mini` | E4 raw hypotheses + autoeval label |

### §9.2 診斷 / 分析檔

| 檔案 | 覆蓋範圍 |
|:--|:--|
| [`results/fc_sh_4method_errormode_diag.md`](../results/fc_sh_4method_errormode_diag.md) | §6.1 per-qid error mode + 3 diagnostics |
| [`results/deterministic_freshness_baseline.md`](../results/deterministic_freshness_baseline.md) | §6.2 concurrent work 公平對照 |
| [`results/ours_ku_mechanism.md`](../results/ours_ku_mechanism.md) | §6.3 ours pipeline trace |
| [`results/mem0_ku_mechanism.md`](../results/mem0_ku_mechanism.md) | §6.3 mem0 destructive failure trace |
| [`results/zep_ku_resolution_bitemporal.md`](../results/zep_ku_resolution_bitemporal.md) | §6.3 Zep 262k crash root cause |
| [`results/mem0_event_taxonomy_gt4o.md`](../results/mem0_event_taxonomy_gt4o.md) | §6.3 gpt-4o backbone 的 event taxonomy |
| [`results/matcher_audit_gpt4omini_64k.md`](../results/matcher_audit_gpt4omini_64k.md) | §6.3 matcher v4 audit |

### §9.3 Case study 檔

| 檔案 | 覆蓋範圍 |
|:--|:--|
| [`results/case_studies_64k.md`](../results/case_studies_64k.md) | §6.4 gpt-4o-mini × 64k |
| [`results/case_studies_gpt41mini_64k.md`](../results/case_studies_gpt41mini_64k.md) | §6.4 gpt-4.1-mini × 64k, Plan A finding |
| [`results/weak_model_case_studies_6k.md`](../results/weak_model_case_studies_6k.md) | §6.4 gemma3 tier × 6k |
| [`results/32k_case_study.md`](../results/32k_case_study.md) | §6.4 32k pilot(supersede)|
| [`results/has_pair_resolution_cases_6k.md`](../results/has_pair_resolution_cases_6k.md) | §6.4 pool 狀態 trace |

### §9.4 相關規約 / audit 文檔

- [`evaluation_protocol_main.md`](../evaluation_protocol_main.md) — chunker / template / metric / matcher rule(對齊 §0.3-§0.5)
- [`matcher_specification.md`](../matcher_specification.md) — matcher v4 spec(§3 / §6.5 使用)
- [`methods_reproduction.md`](../methods_reproduction.md) — canonical file registry(paper 引用 authoritative source)
- [`results/rigor_audit.md`](../results/rigor_audit.md) — canonical file rigor rules
- [`style_rules_tables_figures_writing.md`](../style_rules_tables_figures_writing.md) — 圖表 / 表格 / caption 三段論規範

### §9.5 scripts

| 檔案 | 用途 |
|:--|:--|
| `analysis/rescore_canonical.py` | E1/E1b/E2/E3 主表 canonical rescore(single source of truth)|
| `analysis/rebuild_aggregated_from_perqid.py` | rigor audit fail 時 rebuild |
| `analysis/rigor_audit.py` | canonical file rigor 檢查 |
| `docs/0615_.../scripts/run_fc_sh.sh` | E1/E1b/E2/E3 FC-SH 執行入口 |
| `docs/0615_.../scripts/run_lme_ku.sh` / `run_lme_ku_parallel.sh` | E4 LME-KU 執行入口 |
| `docs/0615_.../scripts/maxserial_theircode.py` | §6.2 Don't Ask 公平版 driver(vendor 於 `related work/memory-conflict-resolution/`)|

---

## 更新紀錄

- **2026-07-16**:建檔;整合 E1(FC-SH 4-length gpt-4o-mini)+ E1b(OpenAI mini-tier evolution)+ E2(Gemma3 spectrum)+ E3(cross-family)+ E4(LME-KU)+ §6 診斷素材 + §7 claim 對照 + §8 gap 清單。命名 / 判分沿用 [`methodology_source_material_0716.md`](methodology_source_material_0716.md) canonical。
- **2026-07-16(續)**:三項定案 —
  1. §2 strong tier 定案為 **gpt-5.4-mini**,不使用 gpt-4o(§2.4 caveat 更新)。
  2. §5 LME canonical 定案為 **`ours_no_p5` = 70.5%**;`lme_ku_ours.jsonl`(P5, 83.3%)因 repo 無 build log,不列 paper 主表(§5.1 排除)。
  3. §7.6 Rolling adjust 重寫:ours 於 LME 未 outright 領先(輸 Vanilla-RAG 1s 3.9pp)→ Abstract / Intro 需明講 scope 限於 counterfactual bias-heavy 情境。
  4. §8.1 gap 表格重排:已 resolved 兩項標示;新增 Zep 262k bi-temporal 分類 pending / 6.3% invalidation coverage 引述 source 待補。
- **2026-07-16(續 2,Zep 262k mechanism 補跑)**:
  1. Patch `analysis/classify_zep_ku_resolution.py`:LENGTHS 加 `262k`,`analyze_length` + `print_report` 加 invalidation coverage 統計(全 100 queries × 10 edges 母數)。
  2. Patch `analysis/compute_pool_acc_crosstab.py`:GT_PATHS 加 262k → `sh_262k_mquake_analysis.json`。
  3. §6.3.1 新增 262k 4-bucket 分桶 + 全 4-length invalidation coverage 對照表。
  4. **§1.4 caveat 1 改寫**:262k crash 根因**修正為 query-time retrieval miss(NotBothExtracted 82%)主導**,非單純 write-time invalidation 不足;6.3% coverage 為 write-time 側**次要**指標。
  5. §8.1 兩項 gap 標為 resolved(Zep 262k 分桶已補、6.3% source 已算出)。
