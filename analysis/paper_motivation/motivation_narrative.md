# FC-MH Multi-hop Knowledge Update — motivation narrative_v2

> **目的**:給不熟此領域的資工系教授看的論述版本。從 high-level 觀察逐步引導到核心 claim。所有結論皆有 ≥3 data point 撐 (除特別標註)。
>
> **更新**:2026-05-04
> **資料來源**:MemoryAgentBench/analysis/results/ + paper_motivation/figures/
> **Setup naming convention** (本文使用):
> - `Vanilla`: HippoRAG-v2 production retrieval, corpus 含全 old+new
> - `OracleClean-Others`: 只保留**本題** chain_old, 全清其他 olds (165 olds 中 1-4 個保留)
> - `OracleClean-ThisChain`: 移**本題** chain_old (1-4), 其他 olds 全留 (= OA2)
> - `OracleClean-All`: 全 olds 移除 (165 個) (= NC)
> - `PureChain`: context 只含本題 chain_new, 無任何 distractor (= Sim-OB chain-only)。**雙重角色**: (a) LLM 多跳推理 ceiling, (b) **construct validity proof** — 證明同 100 題 in clean context 可解,任務本身不是 broken
> - `PureChain+Olds`: context 含 chain_new + chain_old, 無其他 distractor (= Mode A)

---

## §1 整體表現:FC-SH → FC-MH 全面崩潰

### Setup
我們在 MemoryAgentBench 的 FactConsolidation 任務評估 3 個記憶方法 — `HippoRAG-v2`、`Zep`、`Mem0` — 在 6k 對話歷史上的表現。任務有兩 split:
- **FC-SH** (Single-Hop): 一個事實被另一個取代,query 涉及 1 個 fact 的衝突解決
- **FC-MH** (Multi-Hop): query 需鏈接多個事實,且 chain 中每跳都可能有衝突

模型 = Gemini 3.1 Flash-Lite Preview (跨方法 inference 對齊)。

### 結果 — SH 接近飽和,MH 全面崩潰

跨 3 個方法皆採 **MABench default pipeline** (FC seq-rule wrapper 包在 query template 中,inference-time 提示「serial number 較大 = 新」):

| System | FC-SH | FC-MH | drop |
|---|:---:|:---:|:---:|
| HippoRAG-v2 (vanilla, 無衝突機制) | 77% | 22% | **-55pp** |
| Mem0 customized (filter at write) | 85% | 44% | **-41pp** |
| Zep (annotation at inference) | 89% | 28% | **-61pp** |

**觀察**: 3 個方法 SH 都 ≥77% (single-hop 衝突解決基本能解),但 MH 落差巨大 (從 -41 到 -61pp)。**Multi-hop 衝突解決是現有方法的共同弱點**。

> **註 1 (評估嚴謹度 — wrapper 對齊)**:全部數字來自 **MABench-aligned pipeline** (FC seq-rule wrapper 包在 query template 中)。MABench [`utils/templates.py`](../../utils/templates.py) 的 `AGENT_TYPE_MAPPING` 將任何含 `rag` substring 的 agent_name (含 `Structure_rag_mem0` / `Structure_rag_zep` / `Structure_rag_hippo_rag_v2_nv`) normalize 成 `rag_agent`,對 FC-MH/SH 套同一個 wrapper。我們確認所有 3 系統在 query template + system_prompt + max_tokens + temperature 上都對齊 MABench main pipeline。
>
> **註 2 (Mem0 baseline 必要 fix)**:MABench main pipeline 用原 mem0 套件預設的 `FACT_RETRIEVAL_PROMPT` 在 FC corpus 上 ingest **0 facts** (12 chunks 全部 LLM 判 `[]`),原因是 prompt 中含兩個 anti-knowledge few-shots:`Input: Hi. → []` / `Input: There are branches in trees. → []` — 這在 personal-fact corpus 上合理,但在 FC 全是世界事實的 corpus 上會把所有 chunks 都判成「常識不抽 fact」。直接用原 prompt 跑 Mem0 的結果是 **EM = 1/100 = 1%** (見 [outputs/gpt-4o-mini-mem0/Conflict_Resolution/...](../../outputs/gpt-4o-mini-mem0/Conflict_Resolution/)),不能反映 Mem0 系統能力。我們 fix 是僅移除這兩個 few-shots ([analysis/run_mem0_gemini_aligned.py:`make_l1_modified_prompt`](../run_mem0_gemini_aligned.py)),其餘 mem0 邏輯全保留。Fix 後 ingest 442 facts,retrieval top-100 正常工作,EM = 44%。**這個 fix 是讓 Mem0 系統可運作,跟 wrapper 對齊是兩個獨立的修正**。
>
> **註 3 (wrapper 構成解構)**:wrapper text 包含 4 條規則,理解三系統提升幅度差異需區分:
>   - **R1 序號規則**:"newer fact has larger serial number" — 對 retrieval 含序號的系統 (HippoRAG-v2 chunks / Zep episodes) 直接可用;對 Mem0 (LLM-paraphrased fact, 序號被丟棄) 不適用
>   - **R2 解衝突規則**:"solve conflicts ... by finding the newest fact with larger serial number" — 用 R1 的 actionable 形式
>   - **R3 anti-parametric**:"only from the knowledge pool ... rather than the real facts in real world" — 對所有系統適用,告訴 LLM 不要 fall back to pretrain 知識
>   - **R4 counterfactual example**:Russia president = Trump 範例 — 示範要採用 retrieval 的 counterfactual 答案而非真實答案
>
>   Mem0 提升 +8pp/+1pp 的來源主要是 **R3+R4** (anti-parametric stance);Zep 提升 +10pp/+20pp 的來源是 **R1+R2 (透過 episodes 序號) + R3+R4** 全套。詳細三系統 LLM context 結構驗證見 [A_pipeline_alignment_verification.md](A_pipeline_alignment_verification.md)。

### §1.A 這個崩潰**不是** task 設計問題 (Construct Validity)

直覺第一個質疑會是「FC-MH 22% 是不是 task 設計爛?」 — 我們用 **PureChain** setup 直接擋住:把同樣 100 題的 context 換成「只有本題 chain_new facts,無任何 distractor」,**accuracy 達 97%** (§2.A 詳述)。

→ **任務本身可解**;同 100 題,context 乾淨時 LLM 多跳推理近完美。崩潰來自 **KU (knowledge update) 與 MH (multi-hop) 的 intersection**,不是任一方獨立難。

### §1.B 這個崩潰**也不是** KU、MH 各自難度的線性疊加 (Emergent Intersection Difficulty)

第二個質疑會是「KU 跟 MH 各自有失敗率,串起來自然更難」(multiplicative explanation)。我們用獨立性預測量化反駁:

**獨立性預測 (multiplicative baseline,保守版)**:
- $P_{KU}$ on FC-MH pool = **78.3%** (P1.5 驗證, 見 §2.A.X) — 跟 FC-SH 77% 差 1pp 內,跨池假設成立
- $P_{MH}$ ≈ OracleClean-All 61% (multi-hop reasoning under noisy retrieval, **無** conflict)
- 若兩者獨立: $P_{KU} \times P_{MH} = 0.783 \times 0.61 = $ **47.8%**
- 觀察: **22%** (FC-MH vanilla)
- → **觀察值比獨立性預測低 25.8pp** = 不是線性疊加的乘積,**是 emergent intersection difficulty**

**進階驗證 — per-hop independence 在「拆解條件下」也 hold**:
- P1.5 量到 2/3/4-hop 的 per-hop EM 分別 80.3% / 77.8% / 75.0%
- 若每跳獨立, all-pass 預測 = (per-hop)^N
  - 2-hop: 0.803² = 0.645 vs 觀察 0.656 ✓
  - 3-hop: 0.778³ = 0.471 vs 觀察 0.500 ✓
  - 4-hop: 0.750⁴ = 0.316 vs 觀察 0.267 ✓ (略低)
- → **拆解後的 hops 之間幾乎獨立**。但**組成完整 multi-hop FC question 後 collapse 到 22%** — 這個 collapse 不能用 hop-wise independence 解釋,**emergent intersection difficulty 真實存在**

→ 25.8pp gap 是 paper 的核心 evidence: **KU 跟 MH 在交集處有獨特的失敗模式**, 構成獨立的研究問題。

→ 自然問題: **為什麼 multi-hop knowledge update 會崩潰? Emergent gap 由什麼造成?**

---

## §1.5 先排除 retrieval miss — HippoRAG-v2 retrieval 本身沒崩

在進入 context-level 拆解前,先確認**「retrieval 是否漏抽 chain new 是主因」**。如果 chain_new 根本不在 top-10 retrieval 裡,那問題在 retrieval 端;如果 chain_new 大多數都在,那問題在下游 (context 處理 / LLM 推理)。

### Setup

- HippoRAG-v2 用 NV-Embed-v2 + PPR retrieval, chunk_size=512
- FC corpus: 455 facts 切成 ~12 個 chunks
- 每題 retrieve top-10 chunks (~378 unique facts, **覆蓋 83% 整個 corpus**)
- Retrieval 是「廣 (wide)」而非「精準 (precision-targeted)」

### chain_new / chain_old 在 top-10 retrieval 的覆蓋率

| | chain_new in top-10 | chain_old in top-10 | 全 chain_new 都在 (per-question) |
|---|:---:|:---:|:---:|
| **FC-SH** (n=100) | 99/100 = **99%** | 74/74 = **100%** | 99% |
| **FC-MH 2-hop** (n=61) | 118/122 = 97% | 95/97 = 98% | 57/61 = 93% |
| **FC-MH 3-hop** (n=24) | 68/72 = 94% | 53/53 = 100% | 20/24 = 83% |
| **FC-MH 4-hop** (n=15) | 57/60 = 95% | 37/38 = 97% | 12/15 = 80% |
| **FC-MH all** (n=100) | 243/254 = **96%** | 185/188 = **98%** | 89% |

### 主要觀察

**(a) chain_new retrieval rate 普遍 ≥94%**:
- FC-SH: 99%
- FC-MH 2/3/4-hop fact-level: 94-97% (4 個 cells 都 ≥94%)
- 即使 4-hop 也有 80% 的題目「全 chain_new 都在 top-10」

**(b) chain_old retrieval rate 同樣 ≥97% 甚至 100%**:
- FC-SH: 100% chain_old 都在 top-10
- FC-MH 各 hop level: 97-100%
- → **chain_old 跟 chain_new 一樣顯眼地出現在 retrieval 裡**

**(c) Retrieval 是「廣」不是「精準」**:
- Top-10 chunks 覆蓋 ~83% 整個 corpus (378/455 facts)
- 等於 LLM 看到「corpus 大半內容」,而非「篩選後的相關內容」
- 這意味 chain_new 跟 chain_old 通常**同時出現在 LLM context**

### 結論 — retrieval miss **不是**主因

- chain_new 不在 retrieval 的情況很少 (FC-MH 11% 的題目少了 ≥1 個 hop)
- chain_old 出現率 ≥97% — 就算 detection 完美,**沒做 context-level 過濾**,LLM 仍幾乎一定看到 chain_old
- → **bottleneck 在「retrieval 之後」**: context 處理 (filter / annotation) + LLM 對 context 的使用

→ 引出 §2 的兩 axis 拆解

---

## §2 拆解 FC-MH 崩潰的兩個主因

為避開 Mem0/Zep 系統實作的混淆變因 (各自 prompt / 黑箱 / OOD scenario),**我們先在 HippoRAG-v2 上做控制實驗**,逐步排除可能的失敗源,定位主要 driver。

### §2.A 第一個主因:retrieval context 中的 query-related OLD

我們設計 6 種「context 內含什麼」的 oracle,跑同樣 FC-MH 100 題:

#### Channel ceiling ladder (orig prompt, rule-clean 96 題)

| Setup | EM | 解讀 |
|---|:---:|---|
| **Vanilla** (corpus 含全 old+new) | **21%** | production baseline |
| **OracleClean-Others** (留本題 chain_old, 移其他 165 olds) | **26%** | 加 +5pp 邊際 |
| **OracleClean-ThisChain** (移本題 1-4 chain_olds, 其他 olds 留) | **55%** | 加 **+34pp** ← 主 gain |
| **OracleClean-All** (全 165 olds 移) | **61%** | 加 +6pp 邊際 |
| **PureChain** (context 只有 chain_new, 無 distractor) | **97%** | LLM reasoning ceiling |

#### 主要 reading

**(a) 移除「本題的 chain_old」貢獻 80%+ 的 gain**:
- Vanilla → OracleClean-ThisChain: +34pp (移 1-4 chain_olds)
- OracleClean-ThisChain → OracleClean-All: 只 +6pp (額外清掉 161 個其他 olds)
- 反向驗證 (OracleClean-Others): 留 chain_old 而清其他 → 26% (只 +5pp from Vanilla)

→ **量化結論**: 移除「query 相關的 chain_old」是衝突機制的核心價值;移除「query 不相關的 olds」邊際效益小。

**(b) chain_old 數量越多 → acc 越低,在兩個獨立 setup 都成立**:

**(b1)** HippoRAG 真實 retrieval 上的相關性 (OracleClean-Others by n_conflict):

| n_conflict (留 chain_olds 數) | n_q | acc |
|:---:|:---:|:---:|
| 1 | 33 | 16/33 = **48%** |
| 2 | 47 | 8/47 = **17%** |
| 3 | 14 | 1/14 = **7%** |
| 4 | 2 | 0/2 = **0%** |

⚠️ **Caveat**: 此 stratification 跟 `num_hops` confound (n_conflict=4 cell 全部都是 4-hop)。同 num_hops 內仍呈下降趨勢 (2-hop n_conflict=1/2: 52%/19%; 3-hop n_conflict=1/2/3: 40%/11%/10%; 4-hop n_conflict=1/2/3/4: 33%/0%/0%/0%),但**單獨此實驗無法分離 chain_old dose 效應與 hop 數效應**。

**(b2)** Forced context 上的嚴格 dose-response (Mode C grad_injection — 同樣 96 題,飽和噪音,只變 chain_olds 注入數量):

| n_inject (注入 chain_olds 數) | n_q | acc |
|:---:|:---:|:---:|
| **0** (純飽和噪音, 0 chain_old) | 96 | 56/96 = **58%** |
| **1** (注入 1 chain_old) | 96 | 9/96 = **9%** ← 同 96 題,差 -49pp |
| 2 | 63 | 2/63 = 3% |
| 3 | 16 | 0/16 = 0% |
| 4 | 2 | 0/2 = 0% |

→ **n_inject=0 跟 n_inject=1 是 same 96 題, 唯一差別是「注入 1 個 chain_old」, EM 從 58% 掉到 9% = -49pp**。這是嚴格控制 dose 的 evidence,無 hop 數 confound。

→ **(b1) + (b2) 合起來**: 真實 retrieval 跟 forced-context 兩個獨立 setup,**chain_old 多 = acc 低** 的 pattern 都成立。(b2) 是嚴格 dose-response,(b1) 是 retrieval 場景下的相關性 (有 confound,但同 num_hops 內仍下降)。

#### §2.A.X Multiplicative baseline 計算 (對應 §1.B 的 high-level 主張)

> 把 §1.B 的 emergent intersection 主張用三個版本量化, 從保守到嚴格依次降序預期值,觀察值都遠低於預期。

##### §2.A.X.0 $P_{KU}$ 跨池假設驗證 (P1.5)

> 預先排除 reviewer 攻擊「$P_{KU}$ = 0.77 是 FC-SH pool 量的, 在 FC-MH pool 上未必同數值」。

**設計**: 對 FC-MH 100 題的每一跳 (254 hops 總計), 用 `hop_question` 拆成 single-hop FC question, 在 **same retrieval setting** (vanilla HippoRAG-v2 over 6k 全 olds+news) + **same prompt** (vanilla orig + FC seq rule wrapper) 下測 EM。

**結果**:
| 量 | 數值 |
|---|---|
| Per-hop EM on FC-MH pool (orig prompt) | **78.3%** (199/254) |
| FC-SH baseline (orig prompt, comparison) | 77% |
| Difference | +1.3pp (基本相同) |

→ **$P_{KU}$ 跨池假設成立**;FC-MH 題目池上的「真實 per-hop $P_{KU}$」≈ FC-SH 77%。

**By num_hops**:
| num_hops | per-hop EM | per-question all-pass |
|---|---|---|
| 2-hop (61q) | 80.3% (98/122) | 65.6% (40/61) |
| 3-hop (24q) | 77.8% (56/72) | 50.0% (12/24) |
| 4-hop (15q) | 75.0% (45/60) | 26.7% (4/15) |

→ 三個 hop level 的 per-hop EM 在 75-80% 區間, 都接近 FC-SH 77%。**沒有 hop-specific 難度偏差**。

##### §2.A.X.1 Multiplicative baseline 三個版本

**版本 1 (保守, paper main 用此版)** — 用 P1.5 驗證的同池 $P_{KU}$ + OracleClean-All:
- $P_{KU}$ = 0.783 (P1.5 measured on FC-MH pool, vanilla orig prompt)
- $P_{MH \mid \text{noisy}}$ = 0.61 (OracleClean-All, FC-MH no-conflict 但有 retrieval noise)
- 獨立性預測: $0.783 \times 0.61 = 0.478$
- 觀察: **0.22** (Vanilla FC-MH)
- **Emergent gap = 25.8pp 低於 multiplicative baseline**

**版本 2 (寬鬆, 用 PureChain ceiling)** — 用 PureChain 97% 當「clean MH ceiling」:
- 0.783 × 0.97 = 0.760
- 觀察: 0.22
- Gap = 54pp

**版本 3 (最嚴格, Mode C same-question, single-variable)** — 同 96 題, 飽和噪音, 唯一變數=是否注入 1 chain_old:
- $P_{MH}$ on 96 題 = 0.58 (n_inject=0)
- $P_{KU}$ = 0.783 (P1.5 same-pool)
- 獨立性預測: $0.58 \times 0.783 = 0.454$
- 觀察: **0.09** (n_inject=1, same 96 questions)
- Gap = **36.4pp 低於 multiplicative baseline,在 same-question 控制下**

**為什麼版本 3 是 reviewer-proof**:
- Same questions → 沒有題目難度差異
- Same retrieval context size → 沒有 retrieval randomness
- Single-variable manipulation (n_inject=0 → 1) → 沒有 hop count confound
- 唯一變動: 是否注入 1 個 chain_old
- → 任何「只是兩 hard task 串起來」的 multiplicative 解釋都被排除

##### §2.A.X.3 P1.4 No-seq-rule ablation — 進一步擋掉「seq rule trivially 告訴 LLM」攻擊

> Reviewer 可能質疑:Mode C 的 dose-response 是否依賴 FC seq rule wrapper (顯式告訴 LLM 「大 seq = 新」)。我們直接拿掉 wrapper 跑 same-question Mode C n=0 / n=1。

**設計**: 同 Mode C 的 context 構造,但 inference query 改用 `q["question"]` (bare question, 無 FC wrapper)。

**結果 (rule-clean 96)**:
| Condition | n_inject=0 | n_inject=1 | Drop |
|---|---|---|---|
| **With seq rule** (Mode C 原版, FC wrapper) | 58% | 9% | **-49pp** |
| **Without seq rule** (P1.4 bare question) | 47.9% | 1.0% | **-46.9pp** |

**關鍵 reading**:
- Seq rule 確實貢獻 ~10pp 的 baseline (n=0 時 58% vs 47.9%) — 它幫 LLM 在 clean context 下解決多跳推理
- 但**注入 1 chain_old 造成的崩潰幅度 (-47pp)** 在有/無 seq rule 都基本一致
- → **emergent intersection difficulty 不是 seq rule artifact**, 是 chain_old 出現在 LLM context 的根本性影響

**對 paper 防守**:
- 即使 reviewer 把 FC wrapper 視為 "trivial KU detection hint",我們的核心 claim (chain_old in retrieval = killer) 在無 wrapper 條件下 evidence 更乾淨 (-46.9pp)
- 這個 ablation 同時 disprove "結果只是因為 LLM 信任 seq rule" 的解釋

##### §2.A.X.2 Per-hop independence 在「拆解條件下」hold,但組合後 collapse

P1.5 的 by-num_hops 數據還提供一個額外檢驗:

| num_hops | per-hop EM | (per-hop)^N 預測 all-pass | 觀察 all-pass |
|---|---|---|---|
| 2 | 0.803 | 0.645 | 0.656 ✓ |
| 3 | 0.778 | 0.471 | 0.500 ✓ |
| 4 | 0.750 | 0.316 | 0.267 ✓ (略低) |

→ **三個 cells 都接近 hop-wise independence 預測**, 表示拆解後的 hops 幾乎獨立。

**但**完整 multi-hop FC question 答對率為 22%, 比上述 all-pass (~50% for 3-hop) 又低很多。這個額外的 collapse:
- 不是 hop-wise dependence 造成 (證明上面 ≈ 獨立)
- 不是個別 hop 變難 (per-hop 仍 75-80%)
- → **必有 multi-hop 整體層級的 emergent failure mode** (§2.A 後續章節進一步拆解 = retrieval 中的 chain_old 干擾)

**Paper 報法**:
- Main text 報版本 1 (25.8pp gap, $P_{KU}$ same-pool 量過)
- 版本 3 (Mode C 36.4pp gap) 作為 confirmatory evidence,在 §2.A.b2 已呈現
- §2.A.X.2 per-hop independence check 升為 emergent claim 的第二層 evidence

**(c) 但 retrieval 乾淨後仍離 ceiling 36pp**:
- OracleClean-All (61%) vs PureChain (97%) = **36pp gap**
- 這個 gap 不是 chain_old 造成 (已全清),必有其他原因

→ 引出 §2.B

### §2.B 第二個主因:LLM 從 retrieved context 中穩定使用知識

假設: 即使 context 已乾淨, **LLM 在多跳推理時不一定穩定地把 retrieved facts 接成 chain**。

驗證方式:加上「結構化 prompt」強迫 LLM 結構化地使用 context,看是否能填補這 36pp gap。我們測試 3 種**不同的**結構化 prompt,各自只對 vanilla prompt 做最小改動:

| Prompt variant | 與 vanilla 的最小改動 |
|---|---|
| **V1 trailer** | system 加 1 句要求輸出 "Intermediate answers: [a, b, c]";one-shot 加 1 行 |
| **V2 cite-source** | system 加 1 句要求每個結論引用對應的 fact 編號;one-shot 加括號引用 |
| **V3 decompose** | system 加 1 句要求先列子問題;one-shot 加 "Sub-questions:" 段 |

#### 結果 — 3 variants 給出一致的 +28~31pp gain

**OracleClean-ThisChain (orig 55%) + 結構化 prompt**:

| Prompt | EM | Δ vs orig |
|---|:---:|:---:|
| (no structured prompt) | 55% | — |
| + V1 trailer | **83%** | **+28pp** |
| + V2 cite-source | **85%** | **+30pp** |
| + V3 decompose | **86%** | **+31pp** |

→ **3 個 independent 的結構化 prompt 都拿到 +28-31pp gain** — 不是 V1 trailer 特有的 quirk,是 stable underlying signal:LLM 在乾淨 context 上**需要結構化指引才能穩定多跳推理**。

#### Cross-cleanness 對照 (verify 上述 claim 不只 OA2 上成立)

V1 trailer 在不同 cleanness setup 上的 gain:

| Setup | orig | + V1 trailer | trailer Δ |
|---|:---:|:---:|:---:|
| Vanilla (太髒) | 21% | 23% | **+2pp** ← 救不了 |
| OracleClean-Others | 26% | 34% | +8pp |
| **OracleClean-ThisChain** | **55%** | **83%** | **+28pp** ← 最強 |
| OracleClean-All | 61% | 81% | +20pp |
| PureChain (太乾淨) | 97% | 98% | **+1pp** ← 飽和 |

→ 結構化 prompt 在「中度乾淨」context 上效益最大;太髒救不了,太乾淨已飽和。**這個 pattern 跨 5 個 cleanness 級別都符合**,不是單一 setup 的偶然。

#### 剩餘 17pp gap (OracleClean-ThisChain + V3 86% → PureChain 98% = 12pp 或 → OracleClean-All + V1 81% → PureChain 98% = 17pp)

這部分是:
- **chain_new 沒被 retrieval 完整 surface** (HippoRAG retrieval coverage 問題,~10pp)
- **LLM parametric override** (Gemini pretrain 內含的真實世界 fact 蓋過 NEW context, ~5-7pp,見 [§4 analysis](#§-4) 中 Mode A 分析)

這 17pp 主要是**外部記憶研究範圍外的 LLM/retrieval 限制**,paper 顯式 disclose 不挑戰。

---

## §3 兩個核心 Research Claim

基於 §2 的控制實驗,我們提出兩個 orthogonal axis 的 claim:

### 🎯 Claim 1 (Retrieval-side)

> **Query 每一跳的舊知識若不過濾,會大幅讓表現下降。**
>
> 量化: vanilla 21% → 移本題 chain_old 後 55% (= +34pp);移其他 olds 只 +5pp 邊際。
>
> Dose-response: 留 1 / 2 / 3 / 4 個 chain_olds → acc 48% / 17% / 7% / 0%。
>
> Driver: chain_old (含「衝突對 OLD」與「OLD 實體相關事實」) 出現在 LLM 看到的 retrieval 中,系統性把推理拉向 OLD chain。

### 🎯 Claim 2 (Inference-side)

> **即使 retrieval context 乾淨,LLM 在多跳鏈上的推理仍不夠穩定。需要結構化 prompt 強迫 step-by-step 用 context。**
>
> 量化: 3 個 independent 結構化 prompt 在乾淨 context 上都拿 +28~31pp gain。
>
> 驗證: 同 prompt 在太髒 context (vanilla) 救不了 (+2pp),在太乾淨 context (PureChain) 飽和 (+1pp)。
>
> Driver: LLM 沒被結構化指引時,容易在多跳中途 regress 到 OLD / give up / 忽略 metadata。

兩 claim **orthogonal** — 解 Claim 1 不會自動解 Claim 2,反之亦然。需要兩 axis 都做才能逼近 ceiling。

---

## §4 用 Mem0/Zep 機制分析支持兩 claim

### §4.1 兩系統的衝突機制流程

#### Mem0 (filter at write)

```
chunk → LLM 抽 fact list (FACT_RETRIEVAL_PROMPT)
       → 對每 new fact,在 vector store 找 top-5 nearest existing
       → LLM 判斷 ADD/UPDATE/DELETE/NONE (UPDATE_MEMORY_PROMPT)
       → UPDATE 直接覆寫舊 entry, DELETE 刪除
```

→ 衝突偵測 = LLM 對 (new, existing top-5) 做 sentence-level judge。

#### Zep (annotation at inference)

```
chunk → cloud server LLM 抽 entity + edge
       → 對新 edge (S, R, O') 比對既有 (S, R, O)
       → cloud LLM 判斷是否 contradiction (graphiti dedupe_edges.py:resolve_edge)
       → 標 invalid_at timestamp 在舊 edge (不刪除)
```

→ 衝突偵測 = cloud LLM 對 (new edge, existing edge candidates) 做 edge-level judge。標記後**新舊 edge 都保留**,只在舊 edge 加 metadata。

→ Query-time: graph search 取 edges/nodes/episodes 三 scope 各 top-10 餵 LLM。

### §4.2 失敗模式統計支持 Claim 1

**核心統計**: 答錯題目中,LLM output 含某個 chain_old 答案的比例 (full MABench-aligned 跑)。

#### 整體 (FC-MH)

| 系統 | 答錯題 (n) | output 含 chain_old (n) | rate |
|---|:---:|:---:|:---:|
| Mem0 | 56 | 16 | **29%** |
| Zep | 72 | 20 | **28%** |

→ 兩系統一致約 **28-29% 失敗來自 chain_old 干擾**。即使 MABench default 已含 inference-time wrapper,chain_old 仍佔超過 1/4 的失敗 — chain_old in retrieval 仍是 production 系統的明顯失敗源。

#### by num_hops

| hop | Mem0 wrong/pulled/rate | Zep wrong/pulled/rate |
|:---:|:---:|:---:|
| 2-hop | 28/11/**39%** | 38/14/**37%** |
| 3-hop | 15/5/33% | 19/4/21% |
| 4-hop | 13/0/0% | 15/2/13% |

→ hop 越多 pulled-by-old 比例反而越低,因為 hop 多時 LLM 更傾向以「沒答案 / 拒答 / 中途偏離 chain」失敗,不是被 chain_old 拉走。但 2-hop 時兩系統都仍有 ~37-39% 的失敗源於被 chain_old 拉走。

#### by detection bucket × pulled-by-old

| bucket | Mem0 wrong/pulled/rate | Zep wrong/pulled/rate |
|---|:---:|:---:|
| all_detected | 15/4/**27%** | 12/3/**25%** |
| partial | 26/6/23% | 29/8/28% |
| no_detection | 15/6/40% | 31/9/29% |

→ pull rate 在三 bucket 接近 (23-40%) — wrapper 的救援不分 bucket。
→ 但**仍有 25-27% 的 all_detected 答錯題被 chain_old 拉走** — 即使 retrieval 端已正確偵測 (Mem0: filter 對, Zep: 標 invalid_at),LLM 端仍可能被 chain_old 拉走 → **直接支持 Claim 1 在 production scope 仍成立**。

### §4.3 偵測效能 + 完美偵測仍失敗 — 支持 Claim 2

#### §4.3.A 兩系統的偵測效能本身就是 bottleneck

先看**衝突偵測涵蓋率**(per-hop level: 該 has_pair hop 是否被正確偵測,跟 wrapper/inference 無關 — 系統 ingestion 行為決定):

| | FC-SH (n_has_pair=74) | FC-MH (n_has_pair=188) |
|---|:---:|:---:|
| **Mem0** UPDATE/DELETE in history.db | 46/74 = **62%** | 111/188 = **59%** |
| **Zep** edge with `invalid_at` | 26/74 = **35%** | 71/188 = **38%** |

升至 **per-question all_detected** (該題所有 has_pair hops 都偵測對):

| | FC-SH (n=100) | FC-MH (n=100) |
|---|:---:|:---:|
| Mem0 all_detected | 46/100 = **46%** | 41/100 = **41%** |
| Zep all_detected | 26/100 = **26%** | 20/100 = **20%** |

> 數字源自 [aligned_detection_answer_correspondence.json](../results/aligned_detection_answer_correspondence.json), v2 統一 detection logic。Mem0 detection 來自 `~/.mem0/history.db` 的 UPDATE/DELETE event 比對 GT 衝突對 (UPDATE 要兩端 text_match,DELETE 要 old text_match);Zep detection 來自 retrieved edges 中 `invalid_at != None` 且 fact text_match GT。Zep coverage 為下界(只看 retrieve 過的 edges, 不是全 graph)。算法詳見 [DETECTION_REGEN_CHANGELOG.md](../results/DETECTION_REGEN_CHANGELOG.md)。

→ **生產系統的偵測完整覆蓋率都低於 50% (MH 更差到 20-41%)**。Mem0 比 Zep 高近一倍但仍遠不足。

→ 偵測本身就是 **bottleneck #1**: 多數題目連衝突都沒完全偵測到,談何下游處理。

#### §4.3.B 即使衝突偵測完全正確,LLM 仍可能答錯

聚焦到 all_detected subset (偵測 100% 正確的題目),看 LLM 表現:

| 系統 × split | all_detected n | all_detected EM | "偵測對仍錯" rate |
|---|:---:|:---:|:---:|
| Mem0 SH | 46 | 89% (41/46) | 11% |
| **Mem0 MH** | 41 | **63%** (26/41) | **37%** |
| Zep SH | 26 | 85% (22/26) | 15% |
| **Zep MH** | 20 | **40%** (8/20) | **60%** |

→ **4 個 cells 都 < 100%, MH 兩系統都顯著低於 SH**。即使衝突偵測對:
- Mem0 MH: 37% 仍錯 — filter 後 retrieval 中仍有 OLD-related satellite facts;multi-hop chain 銜接時 LLM 仍易斷
- Zep MH: 60% 錯 — annotation `invalid_at` 在 multi-hop reasoning 中 LLM 部分忽略

→ **支持 Claim 2** (bottleneck #2): 即使衝突機制完美觸發 + MABench default wrapper 已啟用,LLM 推理仍不穩定。需要更強的 inference-time scaffold (V1/V2/V3, §3.2)。

#### §4.3.C 兩個 bottleneck 合計解釋 Mem0/Zep 的低 MH EM (aligned)

| 系統 | bottleneck #1 (偵測漏 → 上限) | bottleneck #2 (偵測對也錯) | overall MH EM |
|---|---|---|---|
| Mem0 | 41 all_det → 限上限 41 | 之中 15 答錯 → 拿 26/100 | + partial/no_det 的 18 → 44% |
| Zep | 20 all_det → 限上限 20 | 之中 12 答錯 → 拿 8/100 | + partial/no_det 的 20 → 28% |

→ 改進 paradigm 必須同時處理兩個 bottleneck (對應兩 claim)。

#### §4.3.D SH 飽和但 MH 仍崩 — bottleneck #2 在 MH 才主導

| 系統 × split | overall EM | all_detected EM | no_detection EM |
|---|:---:|:---:|:---:|
| Mem0 SH | 85% | 89% | 81% |
| Mem0 MH | 44% | 63% | 32% |
| Zep SH | 89% | 85% | 91% |
| Zep MH | 28% | 40% | 31% |

驚人觀察:
- **SH 上 no_detection 的 EM 接近 / 略高於 all_detected** (Mem0 81% vs 89%, Zep 91% vs 85%) — 顯示 wrapper 在 SH 上幾乎完全救援 LLM,系統的衝突 detection 幾乎沒帶來額外升力。
- **MH 上 all_detected vs no_detection 的 gap 重新打開** (Mem0 +31pp, Zep +9pp) — multi-hop 場景下,detection 的價值才真正體現。
- → 這直接支持「**KU + MH 交集才是難題**」(§1.B): SH 即使 detection 全失敗,結構化 prompt 已能救;MH 則需要 detection × prompt 兩端都對,單側都不夠。

#### Case study (illustrative,非 dominant pattern,放這裡只為具體化)

**q6 (Mem0)**: "Twitter CEO 的國籍?" GT=France
- Mem0 W1 偵測對 (Twitter CEO: Jack Dorsey → Bernard Arnault)
- 但 retrieval top-1 是 "Jack Dorsey is a citizen of US" (OLD-entity 相關事實,非衝突對本身)
- LLM 答 US (從 OLD entity 的 satellite fact 串起 OLD chain)

**q2 (Zep)**: "Steve Sax 的運動發源國?" GT=Italy
- Zep 偵測對 (chain_old edge `(Steve Sax, sport, baseball)` 標 invalid_at = 2026-05-02)
- 但 retrieval 同時含 invalid OLD edge 跟 valid NEW edge,**LLM 忽略 metadata**
- LLM 答 baseball/US (跟著 OLD chain)

### §4.4 兩種衝突處理哲學 — Mem0 ingestion-time 物理刪除 vs Zep inference-time 標記

我們從 dump 出的真實 LLM context 觀察 (見 [A_pipeline_alignment_verification.md §A.1](A_pipeline_alignment_verification.md)),三系統送進 LLM 的 retrieval 結構截然不同。理解 Mem0 vs Zep MH 的 EM 差距 (44% vs 28%) **不能只看序號是否可用,要看「ingestion-time vs inference-time 處理 chain_old」這條設計哲學分岔**。

#### §4.4.A 三系統 LLM context 的真實組成

| 系統 | LLM 看到的 retrieval 結構 | chain_old 處理 |
|---|---|---|
| **HippoRAG-v2** | top-10 chunks (`Passage N: ... 76. ... 77. ... 100. ...`),保留原始 chunk 完整內容含序號 | 不處理 (vanilla 無衝突機制) — chain_old 仍在 retrieval 中 |
| **Mem0** | top-100 paraphrased facts (e.g. `The chairperson of Fatah is Moshe Kahlon`),無序號、無時間戳 | **ingestion-time 物理刪除**: `UPDATE` 直接覆寫舊 entry,`DELETE` 直接移除 — chain_old 從 vector store 完全消失 |
| **Zep** | **三個 scope 並列** (見 [methods/zep.py:10-30](../../methods/zep.py)): <br>(a) edges (top-10): `FACT (date_range)` paraphrased fact 含時間戳<br>(b) nodes (top-10): entity name + summary<br>(c) episodes (top-10): 原始 chunk 文字含序號 | **inference-time 標記**: 舊 edge 標 `invalid_at` 但**不刪除** — chain_old 在 3 個 scope 都可能仍出現,LLM 須自行讀 metadata 區分 |

→ **關鍵不對稱**: Mem0 用「ingestion 端物理切除」減輕 inference 負擔,Zep 用「ingestion 端標記」把區分新舊的責任全交給 inference 端 LLM。

#### §4.4.B Mem0 為何沒序號還能 44%

從 [`~/.mem0/history.db`](../../analysis/regen_detection_buckets.py) 跑 detection 統計:
- 188 個 has_pair hops 中 **111 個 chain_old 已被 UPDATE/DELETE** (per-hop 偵測 59%)
- 41/100 道題的整條 chain_old 全部已從 vector store 移除 (all_detected, §4.3.A)
- 對應 EM (§4.3.B): all_detected = **63%** — 這 41 道題目的 retrieval 中根本不含 chain_old,LLM 不需要靠序號區分,自然能拿高 EM
- partial 37 道 / no_detection 22 道 EM 分別 30% / 32% — chain_old 仍在 retrieval 但 Mem0 paraphrased fact 無序號,LLM 失去明確 ordering signal

→ **Mem0 不靠序號的 44% 主要來自 ingestion 端清理**,不是 wrapper 規則。Wrapper 對 Mem0 的 +1pp 只反映 R3 anti-parametric 微弱救援。

#### §4.4.C Zep 為何 retrieval 帶序號 + 時間戳卻只有 28%

Zep 三個 scope 都可能含 chain_old,LLM 必須 **同時做三件事** 才能正確答題:
1. 讀 edges 的 `(valid_at - invalid_at)` 時間戳判斷哪個 fact 已失效
2. 不要被 nodes 的 entity summary 中可能保留的舊資訊誤導 (entity summary 沒明確時間標)
3. 讀 episodes 中的原始 chunk 序號比較大小

實測 Zep MH all_detected EM 只 40% (8/20):即使 Zep 已正確標記 chain_old edge 為 invalid,**LLM 仍經常忽略 metadata 或 cross-reference 失敗**。

→ Zep 的設計哲學把「區分新舊」的負擔全交給 inference 端,這個負擔在 multi-hop 場景被放大,直接導致 Zep MH < Mem0 MH 16pp。

#### §4.4.D 兩設計哲學的 trade-off (對 paper framing 的意涵)

| | Mem0 (filter-at-write) | Zep (annotation-at-inference) |
|---|---|---|
| **優勢** | retrieval 乾淨,LLM 端負擔低,即使無序號也能高 EM | 保留歷史 fact,可審計;支援時態查詢 |
| **代價** | 衝突若沒被偵測就無法挽回 (一次性刪除);無法做時態查詢 | LLM 必須跨 3 個 scope cross-reference,inference 端負擔大 |
| **failure mode** | partial/no_detection 子集 EM 大幅下降 (Mem0 MH partial 30% / no_det 32%) | 即便偵測對 LLM 仍多失敗 (Zep MH all_det 40%) |

→ **Wrapper 規則 (R1+R2 序號) 對 Zep 是必要救援**, 因為 Zep 的 chain_old 不會被刪除, LLM 必須有規則才能用 episodes 中的序號區分。對 Mem0 wrapper R1+R2 用不上,但 Mem0 已靠 ingestion-time 處理彌補。

→ **這個 trade-off 直接支持 §3 兩 claim**:
- Claim 1 (chain_old in retrieval = killer): Zep 是 chain_old 仍在 retrieval 的活例 — 標 invalid 也救不了 60% 的 all_detected MH 題目
- Claim 2 (LLM 需 inference 端 scaffold): Zep 的 invalid_at metadata 沒有對應的 actionable rule 時 LLM 完全忽略,加 wrapper R1+R2 才解鎖

#### §4.4.E 對 V1/V2/V3 portability 的意涵

V1/V2/V3 在 OracleClean (chunks 含序號) 上 +28-31pp gain,外推到 Mem0/Zep 須看 instance 是否依賴序號:

| Instance | 對 Mem0 (無序號) | 對 Zep (3-scope, episodes 含序號) |
|---|---|---|
| **V2 cite-source** ([oa2_v2_cite_source.py:48-49](../oa2_v2_cite_source.py)) — 明確要求 "cite the specific fact number" | **失效** (Mem0 retrieval 無 fact number) | 可用 (但 LLM 須區分 cite 來自 episodes 序號 vs paraphrased fact) |
| **V1 trailer** ([pat_modified_prompt.py:50-52](../pat_modified_prompt.py)) — `Intermediate answers: [a, b, c]` 格式約束 | 可用 (跟序號無關,純粹強制 LLM 列出每跳實體) | 可用 |
| **V3 decompose** ([oa2_v3_decompose.py:38](../oa2_v3_decompose.py)) — 拆 multi-hop 為 sub-questions | 可用 | 可用 |

詳細 portability 矩陣與 design constraint 見 [method_design.md §9](method_design.md)。

### §4.5 Mem0/Zep 結論

兩系統**不論機制**,失敗統計都符合兩 claim (aligned 數字):
- **Claim 1** evidence: ~28-29% wrongs 仍含 chain_old, 即便 MABench default wrapper 已啟用 — chain_old 干擾在 production scope 仍真實 (§4.2)
- **Claim 2** evidence:
  - 完美偵測時 Mem0 MH 仍 37% 錯 / Zep MH 60% 錯 (§4.3.B)
  - Zep MH all_detected EM 偏低 (40% < Mem0 63%) 反映 invalid_at metadata 在缺乏 actionable rule 時被 LLM 忽略;wrapper R1+R2 提供規則才解鎖
- **Trade-off**: Mem0 用 ingestion-time 物理刪除減輕 inference 負擔,Zep 用 inference-time 標記但需 LLM 做 3-scope cross-reference — 兩條路徑都未達 OA2 ceiling,提示**衝突處理 + 結構化 inference scaffold 雙端都需要進一步設計**

---

## §5 Research Gap & Future Contribution Direction

### §5.1 Research Gap — 三個層次的觀察

從 §1 到 §4 的所有實驗,可整理出**現有多輪對話衝突解決記憶方法的三個共通弱點**:

#### Gap 1: 衝突偵測 coverage 不足
- Mem0 在 FC-MH 完美偵測 (per-question all_detected) 僅 41%, Zep 僅 20% (§4.3.A)
- per-hop level 也只有 Mem0 59%, Zep 38%
- → **過半題目連衝突都偵測不到**, 後續 filter / annotation 無從談起

#### Gap 2: FC 通用世界事實放大 LLM 對 OLD 的依賴
- FC 的 old fact 是 LLM pretrain 內已有的真實世界知識 (§3.3)
- 即使外部記憶清乾淨,LLM 仍可能 fall back to parametric (Mode A 8/96 都因此錯,5/8 是 mid-chain regression to OLD)
- 即使加了 MABench 預設 wrapper,production 系統 (Mem0/Zep) 跑下仍有 **28-29%** 失敗含 chain_old (§4.2)
- → **OLD 出現在 retrieval 中的影響在 FC scope 上頑強**,wrapper 削弱但無法消除

#### Gap 3: 完美偵測 ≠ 完美答對
- 衝突偵測 100% 對的子集仍有大量錯 (MABench-aligned, §4.3.B):
  - Mem0 MH all_detected EM: 63% (37% 仍錯)
  - Zep MH all_detected EM: 40% (60% 仍錯)
- 失敗源:
  - Mem0: filter 後 retrieval 仍含 OLD-related 內容 (e.g., q6 satellite leak)
  - Zep: `invalid_at` metadata 在 multi-hop reasoning 中部分被 LLM 忽略
- → **覆蓋率夠也不保證答對**, 還需要 inference-side 更強的結構化引導 (Claim 2 — V1/V2/V3 而不是僅靠 wrapper)

#### Gap 4 (新): Inference-time scaffold 的 leverage 取決於 retrieval format
- Wrapper 規則 "序號大=新" 對 HippoRAG-v2 (chunk 含序號) 直接可用、對 Zep (時間戳) 間接可用、對 Mem0 (LLM-paraphrase 後無序號) 完全無法套用 (§4.4)
- → **未來 scaffold 不能只在 OracleClean (chunks) 上 demonstrate, 必須在多種 retrieval format 下驗證可移植性**

### §5.2 Future Contribution Direction

基於上述 gap, 我們的潛在貢獻方向(待 §6 method 設計 + 文獻 survey 後具體化):

#### 對 Gap 1 (detection coverage) 的回應方向
- 探索**多種偵測機制**, 不限於現有 Mem0 / Zep 風格的 LLM judge
- HippoRAG-v2 既有 KG 結構提供另一條路徑: 用 (subject, relation) edge constraint 做 deterministic detection (待 survey 比對過去文獻)
- 也可探索 hybrid: deterministic 高信心 + LLM judge 補 recall

#### 對 Gap 2 (FC parametric leakage) 的回應方向
- 接受這是 FC scope 上的特殊放大效應 — 並把它當作**強化 evidence 的場景**
- 解 Gap 2 的方法跟解 Gap 1 一致: 把 OLD 從 LLM context 拿掉 (Phase 1 filter)
- 同時要 disclose: 我們的方法在 personal-facts benchmark 上 gain 可能小於 FC

#### 對 Gap 3 (perfect detection ≠ correct) 的回應方向
- 結構化 inference scaffold 是必要的 (§2.B 證明 +28-31pp 一致 gain on clean context)
- 多種 scaffold 可選: trailer / cite-source / decompose-first / **subgraph injection** / **sequential per-hop retrieval**
- 後兩者 (subgraph injection, sequential) 利用 KG 結構, 不依賴 prompt 文字, 較易 generalize 到非 FC scope

### §5.3 後續 Survey 方向 (建立 contribution 邊界)

要做出明確 contribution, 必須先確認過去文獻在以下方向已做到什麼程度:

1. **衝突偵測 (detection)**:
   - Temporal KG completion: timestamp + edge constraint (Trivedi+ 2017, García-Durán+ 2018) 做到何種程度?
   - Memory networks: ingestion order 的衝突處理 (Sukhbaatar+ 2015) 邊界在哪?
   - LLM-based knowledge editing: ROME / MEMIT / MEND 等系列在 conflict detection 上的位置
   - 工業系統: Mem0 / Zep / LangMem / Letta 各自的偵測機制差異

2. **衝突解決 (resolution)**:
   - 直接刪除 vs metadata 標記 vs 版本化 KG, 各自過去文獻的 trade-off 結論
   - 結構化 prompt (CoT / decomposition / iterative retrieval) 在 multi-hop QA 上的累積成果
   - subgraph injection / chain-aware retrieval 過去做法 (e.g., GraphRAG, KG-augmented LLM)

3. **Benchmark scope**:
   - LongMemEval-KU / MemBench / BEAM 含哪些 conflict 類型, 跟 FC 的 explicit triple conflict 差別
   - 過去 benchmark 對「multi-hop knowledge update」的覆蓋程度

→ **Survey 完成才能畫出**:
- 哪些 gap 已被過去文獻解 (那部分我們不貢獻)
- 哪些 gap 還是 open (那部分是我們潛在 contribution)
- 哪些是「過去文獻有做但沒在 multi-hop 場景驗證」(可能適合作我們的 incremental contribution)

---

## §6 Caveats (誠實 disclose)

1. **Mem0 fact extraction prompt 修改**: 預設 prompt 對 FC 全拒收,我們做 L1 minimal mod (移 2 個 anti-knowledge few-shots)。可能有抽取偏差,但 §4.2 / §4.3 用的是 across multiple cells 的 pattern,不是單一數字
2. **Zep cloud 黑箱**: 機制描述靠 graphiti 開源 (Apache 2.0) 的 prompt 邏輯倒推,實際 cloud server 行為可能有差。所有 Zep 結論基於 cloud 給的 output (retrieved edges, nodes, episodes, invalid_at metadata) 而非內部 reasoning
3. **FC scope 限制**: FC 衝突 100% 是 explicit triple conflict (S+R 同, O 不同)。Claim 在隱式衝突 / aggregation 衝突 scope 上是否 generalize 待 §7 survey 確認
4. **4 題 rule-violation** (q44/q67/q86/q98): MQuAKE-CF 跨題 edit collision 導致 FC 序號 rule 與題目 GT 矛盾。所有實驗以 rule-clean 96 題報告為主
5. **Single LLM (Gemini 3.1 FL Preview)**: 跨 model 驗證 (e.g., GPT-4o-mini) 可選做以排除 model-specific 偏差

---

## §7 對 method 設計的 implication (兩 phase, 對應兩 claim)

| Phase | 對應 claim | 機制 | 預期 EM gain (cumulative) |
|---|---|---|:---:|
| **Phase 1: Filter** (高信心 only) | Claim 1 | Write-time 偵測 chain_old → mark superseded edge / 過濾 retrieval | 22% → 55-60% |
| **Phase 2: Reasoning guide** | Claim 2 | Inference-time 結構化 prompt + (chain-aware retrieval) | 55-60% → 80-85% |

剩餘 17pp 屬 retrieval coverage / parametric leakage,**不在 conflict resolution scope**。

### Phase 1 design 約束 (HippoRAG-v2 上)

- HippoRAG-v2 既有 KG (entity nodes + relation edges via OpenIE) **無 supersession 機制**
- 我們可加: **deterministic edge constraint** — 同 (S, R) 不同 O 自動 mark 舊 edge superseded by ingestion timestamp
- 等於用 KG 結構做 Mem0 W1 等價的偵測,**100% precision on explicit triple conflict** (FC scope 內 home court)
- Trade-off: 隱式衝突仍漏,**未來需要 hybrid (deterministic + LLM judge fallback)**

### Phase 2 design 約束

- §2.B 證明 V1/V2/V3 都拿 +28-31pp,代表 **多種 prompt 變體都 work**
- HippoRAG-v2 inference 加結構化 prompt 是最小改動 method
- **不依賴 FC 序號規則 wrapper** (序號規則是 FC 特有 crutch, 不能 generalize 到一般對話記憶)

---

## §8 接下來

1. **Survey 過去文獻** (§5.3) — 確認 detection / resolution 過去做到何種程度, 畫出 contribution 邊界
2. **Phase 1 prototype** — HippoRAG-v2 + deterministic edge constraint (V0 已測 44%), 後續推進 detection recall
3. **Phase 2 整合** — 加結構化 prompt 或 subgraph injection, 看是否進一步推到 80%
4. **跨 benchmark 驗證** — LongMemEval-KU / MemBench / BEAM 上跑同樣 method, 看 generalization

---

## 對應 figures (已生成)

- **Fig 1** (§1): SH→MH drop bar chart (3 systems × 2 splits)
- **Fig 2** (§2.A): Channel ceiling ladder horizontal bar (5 setups, orig prompt)
- **Fig 3** (§2.B): Cross-cleanness × prompt-variant heatmap (5 cleanness × 4 prompts)
- **Fig 4** (§2.A): chain_old dose-response line plot (n_conflict 0/1/2/3/4 → acc)
- **Fig 5** (§4.2): Mem0 + Zep failure mode by num_hops grouped bar
