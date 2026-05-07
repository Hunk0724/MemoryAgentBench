# FC-MH Paper Framing — 整合版工作文件

> **目的**:整合 reviewer 視角的 framing 重構建議,作為論文寫作的策略性參考。
> **基礎**:`motivation_narrative.md` 的所有實驗 evidence + reviewer-style critique 後的重新定位。
> **更新**:2026-05-05

---

## 0. 文件結構

- §1 Executive Summary(1 頁版)
- §2 核心 framing:Emergent vs Multiplicative difficulty
- §3 Evidence 重新分級(Tier 1-4)
- §4 Framing pivot:從 prompt-side 到 memory-side enhancement
- §5 Differentiation strategy(2×2 矩陣)
- §6 預期 reviewer 攻擊 × 防守
- §7 TODO 實驗清單(按優先級)
- §8 論文章節重組建議
- §9 必須誠實 disclose 的 caveats

---

## §1 Executive Summary

### 核心 thesis(一段話版)

在多輪對話 agent memory setting 內,multi-hop reasoning 與 knowledge update 的 *交集* 是被既有研究忽略的子問題。我們的證據顯示這不只是兩種能力的乘積——而是 **emergent intersection difficulty**:KU 與 MH 各自單獨可解(77% / 97%),聯合任務僅 22%,遠低於獨立性預測 47-75%。我們把 gap 拆解為兩個 orthogonal 失敗來源(retrieval-side OLD contamination、inference-side reasoning instability),並論證解決方向應在 memory-side retrieval output restructuring,而非 inference-side prompt engineering。

### 三個 killer evidence(必須出現在 abstract / intro)

1. **Mode C same-question dose-response**:同樣 96 題,單一 chain_old 注入 → 58% → 9%(-49pp)
2. **PureChain construct validity**:同題目移除 OLDs → 97%,證明任務可解
3. **Cross-system replication**:Mem0 + Zep 失敗時 82% output 含 chain_old,完美偵測時 Mem0 仍 23% 錯、Zep 100% 錯

### Method direction(pivot 後)

不做 inference-side prompting(會傷害 memory method 在其他任務上的 portability),改做 **memory-side chain-aware retrieval-output restructuring**——在 retrieval 與 inference 之間的 handoff 層提供結構化線索。

### 2×2 positioning

|  | Inference-side | Memory/Retrieval-side |
|---|---|---|
| **No update handling** | IRCoT, Self-Ask, Plan-and-Solve | GraphRAG, SubgraphRAG, HippoRAG, LightRAG |
| **Update handling** | (sparse, e.g., MeLLo) | Mem0 (filter), Zep (annotation) — *insufficient*; **ours: chain-aware restructuring** |

---

## §2 核心 framing:Emergent vs Multiplicative Difficulty

### §2.1 為什麼這個區分是 reviewer 必問

Reviewer 對「intersection 難解」的標準攻擊有兩類:

- **Multiplicative 解釋**:KU 與 MH 各自有失敗率,串起來自然更難——沒有 emergent 子問題,只是兩個獨立難題的數學疊加
- **Emergent 解釋**:聯合任務的失敗率 *低於* 獨立性預測,代表兩能力在交集處有 *交互失敗模式*,構成獨立的研究問題

我們必須提供 *量化* 證據區分這兩種解釋,否則 framing 會被讀成前者(無新貢獻)。

### §2.2 Multiplicative baseline 計算(必須在 paper body 出現)

**保守版本(用 OracleClean-All 當 MH baseline)**:

$$P_{\text{baseline}} = P_{KU} \times P_{MH \mid \text{noisy}} = 0.77 \times 0.61 = 0.47$$

觀察:**0.22**。Gap = **25pp 低於 multiplicative baseline**。

**寬鬆版本(用 PureChain 當 MH baseline)**:

$$P_{\text{baseline}} = 0.77 \times 0.97 = 0.75$$

觀察:**0.22**。Gap = **53pp 低於**。

**最嚴格版本(Mode C same-question)**:

- $P_{MH}$ on 96 題 = 0.58(n_inject=0)
- $P_{KU}$ ≈ 0.77(FC-SH)
- 獨立性預測:0.58 × 0.77 = **0.447**
- 觀察:**0.09**
- Gap = **35.7pp 低於 multiplicative baseline,在 same-question 控制下**

→ **paper 中報保守版(0.47 vs 0.22, 25pp gap),Mode C 版作為 confirmatory evidence**。

### §2.3 為什麼 Mode C 是 reviewer-proof

Mode C(n_inject=0 vs n_inject=1)是 same 96 questions, single-variable manipulation:
- 沒有題目難度差異(same questions)
- 沒有 hop count confound(same questions)
- 沒有 retrieval randomness(forced context)
- 唯一變數:是否注入 1 個 chain_old

→ 任何「只是兩個 hard task 串起來」的 multiplicative 解釋都被排除。

---

## §3 Evidence 重新分級

### Tier 1 — 升到 abstract / intro(目前都被埋沒)

| Evidence | 目前位置 | 應放位置 | 為什麼 |
|---|---|---|---|
| **Mode C n_inject 0→1 = 58%→9%** | §2.A 的 sub-bullet (b2) | Abstract 第一句 + §2 主圖 | 教科書等級 same-question dose-response,reviewer-proof |
| **Multiplicative baseline 計算** | 不存在(沒算) | §2.A 表格下方 + Abstract | 把 emergent claim 變成可驗算的單一數字 |
| **PureChain 97% construct validity** | §2.A 表格末列,叫「LLM ceiling」 | §1 崩潰結果之後立即出現 | 預先擋掉「benchmark 設計爛」的攻擊 |

**建議的 abstract 開頭(用既有數字,不需新實驗)**:

> "On multi-hop reasoning over update streams, current memory-augmented LLMs collapse from 77% (single-hop with one update) to 22% (multi-hop with chain-distributed updates). This 55-point degradation cannot be explained by independent composition: in the same multi-hop questions, removing conflicting facts yields 97% accuracy, and injecting a single conflicting fact into an otherwise-clean context drops accuracy by 49 points. We characterize this *emergent intersection difficulty* between Knowledge Update and Multi-hop Reasoning, decompose it into two orthogonal failure modes—retrieval-side OLD contamination and inference-side reasoning instability—and argue for memory-side retrieval restructuring as the principled intervention point."

### Tier 2 — 核心機制論證(目前 OK 但需要重新定位)

| Evidence | 目前角色 | 重新定位後角色 |
|---|---|---|
| **Three independent prompt variants(+28-31pp)** | "我們的 method"(Claim 2) | **Diagnostic only**:證明「LLM 需要 structural guidance」是 robust phenomenon。不是我們的 method,而是 method 的 motivation(因為 prompt-side 不 portable,要找 memory-side 替代) |
| **Cross-cleanness × prompt heatmap** | §2.B sub-table | 升到 main figure。展示「太髒救不了、太乾淨飽和、中度乾淨 +28pp」的 pattern,證明 structural guidance 的 leverage 區間 |
| **Channel ceiling ladder(5 setups)** | "filter 重要的證據" | "Performance ceiling under perfect chain-aware retrieval"——告訴 reviewer 我們 method 的 achievable target(55-61%) |
| **兩 claim 加起來逼近 ceiling** | §7 表格,埋在末尾 | 升到 §3 結論。展示 22% → ~83%(combined) → 97%(ceiling)的 gap decomposition |

### Tier 3 — External validity(目前埋在 §4)

| Evidence | 為什麼重要 |
|---|---|
| **Mem0 SH 77% → MH 43%, Zep SH 79% → MH 8%** | 已在 §1,fine |
| **兩系統失敗時 82% output 含 chain_old** | 跨系統一致 failure fingerprint,證明 emergent difficulty 不是 vanilla HippoRAG 特有 |
| **Mem0 完美偵測 MH 仍 23% 錯, Zep 100% 錯** | **新 framing 下這是核心**:既有 production memory-side 機制(filter, annotation)不足以解 KU∩MH,直接 motivate 新 memory-side architecture |
| **q6 / q2 case studies** | **Method design 的 negative spec**:不能只 filter(會漏 satellite leakage)、不能只 annotate(LLM 忽略 metadata) |

### Tier 4 — Supplementary(目前 OK,放對位置即可)

- §1.5 retrieval coverage 96-98% — 從「排除選項」改成「定位介入層」(見 §4.2)
- (b1) OracleClean-Others 的 dose-response — 有 hop confound,作為 (b2) Mode C 的 corroboration,不是主證據
- Mem0/Zep 機制 pseudocode — 放 appendix
- 4 題 rule-violation disclose — 放 caveats section

---

## §4 Framing pivot:從 prompt-side 到 memory-side enhancement

### §4.1 Pivot 動機

**舊方向**:把 §2.B 的 +28-31pp 當 method contribution。

**問題**:Reviewer 標準攻擊「prompt engineering 不算 memory research contribution」。且實際上,改 inference prompt 會影響 memory method 在其他任務的行為,失去 portability。

**新方向**:Memory-side retrieval-output restructuring(在 retrieval 與 inference 之間的 handoff 層介入)。

### §4.2 Evidence 角色變化(重要 — 這決定怎麼寫)

| Evidence | 舊角色 | 新角色 |
|---|---|---|
| §2.B 三 prompt variant | Method contribution | **Diagnostic motivation**:證明 structural guidance 是缺的;但提供 guidance 的正確位置不是 prompt |
| §1.5 retrieval coverage | 排除 retrieval miss | **定義介入層**:retrieval 已 surface chain_new + chain_old,bottleneck 在 retrieval-output 的 *組織方式*,不是 retrieval ranking |
| §4.3.B 完美偵測仍錯 | Mechanism validation | **Contribution 存在性證明**:既有 memory-side 機制(Mem0 filter, Zep annotation)在 KU∩MH 上 documented insufficient |
| q6 / q2 case studies | Illustrative | **Method design constraint**:不能只 filter、不能只 annotate,必須 active subgraph restructuring |
| Mode C n_inject -49pp | Chain_old 危害大 | **High-leverage intervention point**:retrieval-output 是 high-sensitivity 介入層,單一 fact 操作就改 49pp |
| Channel ceiling ladder | Filter 是好主意 | **Achievable performance ceiling**(55-61% under perfect chain-aware filtering) |

### §4.3 Method direction(具體化)

從 §5.2 已提的兩個方向擴展:

1. **Subgraph injection**:從 query entity 出發,沿 KG 結構 traverse,extract chain-aware subgraph,prefer NEW edges over OLD(temporal-aware traversal)
2. **Sequential per-hop retrieval**:每跳基於前一跳 resolved entity 做 retrieval,per-hop 套用 conflict resolution

兩者共同特徵:**利用 KG 結構(HippoRAG-v2 既有 OpenIE-built KG),不依賴 prompt 文字,因此 task-agnostic**。

### §4.4 為什麼 memory-side > prompt-side(三個論點)

1. **Generality**:Prompt 改動是 task-specific,改了會影響 memory 在其他 task 行為;memory-side 改動是 task-agnostic
2. **Compatibility**:不破壞 memory method 的 general-purpose role
3. **Composability**:Retrieval-side enhancement 可 plug into 任何下游 LLM,prompt-side 綁定特定 prompt template

→ **論點 (1) 需要實驗證據**(見 §7 TODO P1.3)

---

## §5 Differentiation Strategy

### §5.1 2×2 矩陣(放 related work 結尾或 §5 開頭)

|  | **Inference-side** | **Memory/Retrieval-side** |
|---|---|---|
| **No update handling** | IRCoT (Trivedi+ 2023), Self-Ask (Press+ 2023), Plan-and-Solve (Wang+ 2023), Decomposed Prompting (Khot+ 2023) | GraphRAG (Edge+ 2024), SubgraphRAG, HippoRAG-v2 (Gutiérrez+ 2025), LightRAG, HyDE |
| **Update handling** | MeLLo (Zhong+ 2023, in-context KE), few KE-prompt works | Mem0 (Chhikara+ 2025) — filter at write; Zep (Rasmussen+ 2025) — annotation at inference; **Ours: chain-aware restructuring** |

### §5.2 對最近競品的 positioning

#### vs Zep(最危險的 competitor)

- Zep 做 **annotation**:加 invalid_at metadata,但 retrieval 同時 surface invalid + valid edges
- 我們做 **active restructuring**:retrieval 階段就只 surface chain-aware、conflict-resolved 子圖
- Evidence:§4.4 q2 case 直接證明 annotation 不夠(LLM 忽略 metadata),Zep MH all_detected EM = 0% / 100% 錯

→ Paper 必須有專門 paragraph "Comparison to Zep",不要避開

#### vs GraphRAG / SubgraphRAG / HippoRAG-v2

- 這些方法假設 KG 是 *static*,沒 conflict 機制
- 我們 contribution = chain-aware subgraph extraction + temporal conflict resolution 的 *組合*

→ **這是 framing 上最弱的差異化**(reviewer 會說「nothing new at component level」)。需要在 method 設計階段刻意製造 component-level novelty(見 §7 TODO P2.1)

#### vs Mem0

- Mem0 做 write-time filter(把舊 fact 從 store 移除)
- 我們做 read-time restructuring(retrieval 階段組織 chain-aware output)
- Mem0 的失敗 case(q6 satellite leak)正好是 read-time 處理可以解的

---

## §6 預期 Reviewer 攻擊 × 防守清單

### 🗡 Attack 1:「Zep 已經做 memory-side enhancement for updates,你做了什麼新的?」

**防守(已有 evidence)**:
- §4.4 q2 case:Zep annotation 對了但 LLM 忽略 metadata
- §4.3.B:Zep MH all_detected EM = 0%
- 機制差異:annotation vs active restructuring

**Action**:§5 必須有專門 paragraph 直接 frame 為 "Comparison to Zep"

### 🗡 Attack 2:「GraphRAG / SubgraphRAG 已做 subgraph retrieval,你做了什麼新的?」

**防守**:
- 這些方法在 *static* KG 上做,沒處理 conflict
- 我們的 contribution 是 *組合*

**弱點**:組合的新穎性是相對弱的 contribution claim

**Action**(見 §7 P2.1):method 設計階段刻意製造 component-level novelty

### 🗡 Attack 3:「§2.B 證明 prompt-side 工作 +28-31pp,為什麼不直接用 prompt?」

**防守**:
- Prompt-side 是 task-specific,會 degrade memory method 在其他任務的表現
- Memory-side 從 KG 結構自動推導,不需要 query-side 知道 chain structure

**弱點**:「會 degrade 其他任務」是 assertion,沒有實驗證據

**Action**(見 §7 P1.3):必須跑 cross-task degradation experiment

### 🗡 Attack 4:「7% / 22% 的低分是 task 設計問題,不是真難」

**防守(已有 evidence)**:
- PureChain 97% 證明 same questions 在 clean context 上可解
- Mode C 證明同 96 題只差 1 chain_old 就崩潰

→ **這個攻擊在新 framing 下完全擋住**,但要把 PureChain 從 §2 表格末列升到 §1 末尾突顯

### 🗡 Attack 5:「FC-MH 的 serial number 規則是不是把 KU 偵測 trivially 告訴 LLM 了?」

**防守**:目前 *沒有* 完整防守

**Action**(見 §7 P1.4):跑「無 serial number hint」的 ablation,看 baseline accuracy

### 🗡 Attack 6:「FC-SH 跟 FC-MH 是不同題目池,你的 multiplicative baseline 是 cross-pool comparison」

**防守**:目前 *沒有* 完整防守

**Action**(見 §7 P1.5):跑 FC-MH 題目降階版的 single-hop accuracy,得到 same-pool $P_{KU}$

### 🗡 Attack 7:「這是 memory research 還是 RAG research?」

**防守**:
- Conversational memory setting 的特殊性:incremental ingestion + temporal ordering + conflict over update streams
- §1.5 chunked input + §4.4 ingestion-order-dependent 機制都是 setting 特徵

**Action**:在 intro 明確聲明 setting 邊界

### 🗡 Attack 8:「Single LLM (Gemini 3.1 FL Preview),結果 model-specific?」

**防守**:目前 partial(三個 system 用同 model 算 cross-system,但不算 cross-model)

**Action**(見 §7 P2.2):至少在 Mode C 跟 PureChain 兩個 killer experiment 上加 GPT-4o-mini 驗證

---

## §7 TODO 實驗清單(按優先級)

### P1 — 擋 reviewer 攻擊必要(必跑)

#### P1.1 計算並寫出 multiplicative baseline 數字
- **工作量**:無新實驗,只是把既有數字寫進 paper
- **產出**:Abstract 一句話 + §2.A 表格下方 paragraph
- **內容**:0.77 × 0.61 = 0.47 vs 觀察 0.22(25pp gap);Mode C 版本 0.58 × 0.77 = 0.447 vs 觀察 0.09(35.7pp gap)

#### P1.2 把 PureChain 從「ceiling」改稱「construct validity proof」
- **工作量**:寫作 framing 改動
- **產出**:§1 末尾一句話擋掉 "task 設計爛" 攻擊

#### P1.3 Cross-task degradation experiment(prompt-side vs memory-side)
- **目的**:支持「memory-side 優於 prompt-side 因為 portability」論點
- **設計**:在 LongMemEval-KU 或一般 dialogue QA 上,用 §2.B 的 V1/V2/V3 prompt 模板,看是否 degrade
- **預期結果**:即使只有「prompt-side 在某非 FC 任務 degrade」一個負面結果,framing 就強很多
- **工作量**:中等(需找對比 benchmark + 跑 ablation)

#### P1.4 No-serial-number ablation
- **目的**:證明 KU 偵測能力不是 serial number artifact
- **設計**:把 FC-MH prompt 的 serial number 提示拿掉,跑 Mode C n_inject=0 跟 n_inject=1
- **預期結果**:
  - 若 baseline 只小幅下降(58% → ~50%),framing 沒問題
  - 若大幅下降(58% → ~10%),framing 需要強化(reviewer 攻擊 valid)
- **工作量**:小(改 prompt 重跑)

#### P1.5 FC-MH same-pool single-hop baseline
- **目的**:驗證 $P_{KU}$ = 0.77 在 FC-MH 題目池上仍然成立
- **設計**:把 FC-MH 每題降階為「只問 chain 最後一跳 + 給對應 chain_new 為唯一相關 fact」,測 accuracy
- **預期結果**:應接近 FC-SH 的 77%(若是,multiplicative argument bulletproof)
- **工作量**:小(用既有資料降階)

### P2 — 強化現有 claim(建議跑)

#### P2.1 Method-side component-level novelty 實作
- **目的**:擋「組合的新穎性」攻擊
- **設計**:在 chain-aware subgraph extraction 演算法本身做設計創新(例如 temporal-aware PPR variant、conflict-resolved subgraph traversal)
- **工作量**:大(method 主要工作)

#### P2.2 Cross-model 驗證(Mode C + PureChain)
- **目的**:排除 Gemini-specific 偏差
- **設計**:在 GPT-4o-mini 上重跑 Mode C n_inject=0/1 跟 PureChain
- **預期結果**:pattern 一致(具體數字可能不同,但 emergent gap 應 robust)
- **工作量**:小(API 跑)

#### P2.3 Ingestion order ablation
- **目的**:強化 conversational memory setting 的特殊性論點
- **設計**:把 FC-MH 同樣的 facts 用 batch input(非 incremental)餵給 LLM,看是否表現不同
- **預期結果**:若 batch input 表現好得多,證明 incremental ingestion 是 setting-specific 困難
- **工作量**:小

### P3 — Nice to have(視時間)

#### P3.1 Generalization 到其他 conversational memory benchmark
- LongMemEval, MemBench, BEAM 上跑同樣 method
- 目的:跨 benchmark 一致性

#### P3.2 Failure mode 細粒度分類
- 把 §4.2 的 82% pulled-by-old 細分(衝突對 OLD vs OLD-entity satellite leak vs mid-chain regression)
- 目的:更精細的 failure taxonomy

#### P3.3 Hybrid detection mechanism prototype
- §5.2 已提:deterministic 高信心 + LLM judge 補 recall
- 目的:address Gap 1(detection coverage)

---

## §8 論文章節重組建議

### 舊結構 → 新結構

| 舊 § | 新 § | 變化說明 |
|---|---|---|
| §1 整體崩潰 | §1 Hook(崩潰 + PureChain construct validity + multiplicative baseline) | **三個數字一頁出現**,reviewer 立刻 buy-in |
| §1.5 排除 retrieval miss | §1.5 → 移到 §2 開頭一句帶過,或 appendix | 從防守變定義介入層 |
| §2.A Channel ladder + Claim 1 | §2 Killer experiment(Mode C 為主)+ ladder 為 supporting | Mode C 升為 §2 核心 figure |
| §2.B 結構化 prompt + Claim 2 | §3 Decomposition(兩 orthogonal claims + combined recovery) | Prompt 證據降為 diagnostic,不是 method |
| §3 兩 claim | 合併到 §3 Decomposition | — |
| §4 Mem0/Zep 分析 | §4 External validity | 標題改為 cross-system validation,82% pattern 拉到開頭 |
| §5 Gap & method direction | §5 Method direction(memory-side restructuring)+ 2×2 positioning + Zep comparison | 重組為 contribution argument |
| §6 Caveats | §9 Caveats(maintain) | 不變 |
| §7 Phase 1+2 | §6 Method preview / §7 Experiments | 把方法跟結果分開 |

### 建議的最終章節結構

```
§1 Introduction
   - Hook: SH 77% → MH 22% collapse
   - Construct validity: PureChain 97%
   - Multiplicative baseline: 0.47 predicted, 0.22 observed
   - Contribution preview: characterize emergent difficulty + memory-side intervention

§2 Background & Related Work
   - Long-term memory in LLM agents
   - Knowledge update / multi-hop reasoning literature
   - 2×2 positioning matrix

§3 The Emergent Intersection Difficulty
   - Mode C killer experiment
   - Channel ceiling ladder (decomposition)
   - Cross-cleanness × prompt heatmap

§4 Cross-system Validation (Mem0, Zep)
   - SH→MH collapse on production systems
   - 82% failure-with-OLD signature
   - Perfect detection insufficient (§4.3.B)
   - Failure mode case studies

§5 Method Direction
   - Memory-side vs inference-side argument
   - Chain-aware retrieval restructuring
   - Comparison to Zep / GraphRAG / Mem0

§6 Experiments
   - Phase 1 / Phase 2 prototype
   - Ablations (no-serial-number, cross-model, etc.)

§7 Discussion
   - Limitations
   - Generalization beyond FC scope

§8 Conclusion
```

---

## §9 必須誠實 Disclose 的 Caveats

1. **FC scope 限制**:FC 衝突 100% 是 explicit triple conflict,在隱式衝突 / aggregation 衝突 scope 上 generalize 待驗證
2. **FC 的 OLD 是 LLM pretrain 內既有真實世界知識**:parametric leakage 是 FC scope 特有放大,personal-facts benchmark 上 gain 可能小
3. **Mem0 fact extraction prompt 修改**:L1 minimal mod,across-cell pattern 不受影響但要 disclose
4. **Zep cloud 黑箱**:機制描述靠 graphiti 開源倒推
5. **4 題 rule-violation**:MQuAKE-CF 跨題 edit collision,以 rule-clean 96 題為主
6. **Single LLM (Gemini 3.1 FL Preview)**:見 P2.2 cross-model TODO
7. **Multiplicative baseline 假設 KU 跟 MH 完全獨立,實務上可能有微小相關性**——這個假設只會讓 emergent gap 估計偏 *保守*,不會 inflate

---

## 附:關鍵數字快速查表

| 量 | 數值 | 出處 | 用途 |
|---|---|---|---|
| FC-SH (HippoRAG-v2) | 77% | §1 | $P_{KU}$ baseline |
| FC-MH vanilla | 22% | §1 / §2.A | 觀察 emergent |
| PureChain | 97% | §2.A | Construct validity / clean MH ceiling |
| OracleClean-All | 61% | §2.A | Noisy MH baseline(用此算保守 multiplicative) |
| OracleClean-ThisChain | 55% | §2.A | Achievable target under perfect chain-aware filter |
| Mode C n_inject=0 | 58% | §2.A (b2) | Same-question MH baseline |
| Mode C n_inject=1 | 9% | §2.A (b2) | Killer evidence: -49pp from 1 fact |
| 三 prompt variants gain | +28-31pp | §2.B | Diagnostic: structural guidance is missing ingredient |
| Mem0 MH | 43% | §1 | Cross-system replication |
| Zep MH | 8% | §1 | Cross-system replication |
| Mem0 失敗時含 chain_old | 82% | §4.2 | Failure fingerprint |
| Zep 失敗時含 chain_old | 82% | §4.2 | Failure fingerprint(一致) |
| Mem0 完美偵測時 MH 仍錯 | 23% | §4.3.B | Detection ≠ correctness(motivates new memory-side) |
| Zep 完美偵測時 MH 仍錯 | 100% | §4.3.B | Annotation 不夠(motivates active restructuring) |
| Multiplicative baseline(保守) | 0.47 | 計算 | $0.77 \times 0.61$ |
| Multiplicative baseline(Mode C) | 0.447 | 計算 | $0.77 \times 0.58$ |
| Emergent gap(保守) | 25pp | 計算 | $0.47 - 0.22$ |
| Emergent gap(Mode C) | 35.7pp | 計算 | $0.447 - 0.09$ |
