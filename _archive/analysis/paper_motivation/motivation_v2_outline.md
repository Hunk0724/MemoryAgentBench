# Motivation v2 — 修正後論述線 (2026-05-04)

> 修正自 motivation_draft.md。**重要**:此版根據對話最後一輪的方法學討論,把每個 claim 顯式標 confidence tier。
>
> **核心 framing**:
> - HIGH confidence claims (drop trend + detection coverage + channel ceiling) 構成 paper 主論述
> - MEDIUM confidence claims (detection × answer + failure mode 拆解) 作為 supporting illustration,顯式標 limitation
> - LOW confidence claims (Mem0 specific bucket attributions) 移至 appendix / qualitative observation
>
> **三個系統性 bias 來源**(見 §0.1)決定了哪些 claim 不能高信心宣稱。

---

## §0 Methodology caveats — bias 來源 (paper 必須誠實標)

### §0.1 我們的實驗對 Mem0/Zep 的三個 bias 來源

#### B1: Mem0 fact extraction prompt 的人為修改

- 預設 `FACT_RETRIEVAL_PROMPT` 是「Personal Information Organizer」,**對 FC 通用事實全拒收** (OOB FC-MH = 1%)
- 為了能跑,我們做了 L1 minimal mod (移 2 個 anti-knowledge few-shots)
- 修改後 LLM 抽 facts 時可能產生**不對稱偏好**:
  - 通用世界事實 (e.g., "Twitter CEO is Jack Dorsey") — LLM 可能覺得「太顯然」少抽
  - 反事實 / counterfactual edits (e.g., "Twitter CEO is Bernard Arnault") — LLM 覺得「surprising」多抽
- → **Mem0 MH 43% 含「LLM 自然漏抽 OLD」的不對稱優勢**,不是純粹衝突機制的功勞
- 對應觀察: W4 missed = 19/188 hops 主要落在 OLD 端

#### B2: Zep cloud 不可觀測

- 我們是 Zep cloud API 客戶端 (`zep_cloud.Zep`),**不是本地跑 graphiti**
- Cloud 內部用什麼 LLM、用什麼 embedding、ranking 怎麼算、實際 supersession decision tree — 都是 server-side 黑箱
- graphiti 開源是 reference (告訴我們「prompt 邏輯大概長這樣」),**不能等同實際 cloud 行為**
- → 對 Zep `invalid_at` 的 attribution 只能說「output 顯示 38% 對 60% 沒有」,**不能 claim 為什麼這樣決定**

#### B3: FC 是 Mem0/Zep 的 OOD scenario

- Mem0 / Zep 設計目標: 個人對話記憶、user preferences、agent state
- FC 是把 MQuAKE 通用事實**強塞**進 conversation memory frame,本來就 out-of-distribution
- → 數字反映「強塞 FC 後表現」**而非「方法本身衝突解決能力」**
- Paper 必須 disclose 這點

### §0.2 Confidence tier 對應到 paper 各段

```
HIGH confidence  ─── §1 (drop trend) + §3 (channel ceiling + Sim-OB ladder)
                      load-bearing main argument, 純 EM 數字 + 控制實驗
                      
MEDIUM confidence ── §2.1 (detection coverage), §2.2 (cross-tab)  
                     supporting evidence,需 caveat
                     
LOW confidence    ── §2.3 (failure mode bucket A/B/C)
                     qualitative observation,移到 appendix
```

---

## §1 [HIGH] 整體表現 — FC-SH → FC-MH drop

> **此段全部數字是純 EM 觀察值,不依賴 Mem0/Zep mechanism 推論,不受 §0.1 bias 影響。**

**Claim**: FC-SH 接近飽和 (77-79%),FC-MH 全面崩潰 (drop 34-71pp),drop 程度因衝突機制設計而異。

| System (Gemini 3.1 FL Preview) | FC-SH | FC-MH | drop | 衝突機制 |
|---|---|---|---|---|
| HippoRAG-v2 (vanilla) | 77% | 22% | -55 | 無 — 純 RAG |
| **Mem0 customized** | 77% | **43%** | **-34** | filter at write (UPDATE/DELETE) |
| **Zep** | 79% | **8%** | **-71** | annotation at inference (invalid_at) |

**核心觀察**:
1. SH 接近飽和: single-hop conflict resolution 對所有方法都不太難
2. MH drop 強烈分化: filter paradigm (Mem0) 維持 43%,annotation paradigm (Zep) 跌到 8%,vanilla 22%
3. Zep < HippoRAG vanilla 是反直覺訊號 → 機制本身在 multi-hop 可能有結構性失靈

→ 引出 §2 (現有方法的偵測與失敗) 跟 §3 (channel ceiling)

**Paper-ready takeaway**: Multi-hop knowledge update 是現有 production memory 系統一致性弱點,且 paradigm 之間差異顯著。

---

## §2 [MEDIUM] Mem0/Zep 的偵測機制與表現觀察

> **此段是 supporting illustration,顯式標明 §0.1 三個 bias 來源讓觀察可能不純。**

### §2.1 [MEDIUM] 偵測機制對照與覆蓋率

#### §2.1.A 兩系統的偵測機制 (mechanism 描述, Zep 部分依賴 graphiti reference)

| 項目 | Mem0 (vector mode) | Zep (graph + invalid_at) |
|---|---|---|
| 抽取 | LLM 用 `FACT_RETRIEVAL_PROMPT` 從 chunk 抽 fact list (我們改過,**B1 bias**) | Zep cloud server-side 抽 entity + edge (**B2 黑箱**, graphiti reference: `prompts/extract_edges.py`) |
| **衝突偵測核心** | 每個 new fact 做 embedding,搜 top-5 nearest existing → LLM 用 `UPDATE_MEMORY_PROMPT` 判斷 ADD/UPDATE/DELETE/NONE | 新 edge `(S, R, O')` 進來,與既有 `(S, R, O)` 比對 → cloud 內 LLM 判 contradiction (graphiti reference: `prompts/dedupe_edges.py` `resolve_edge`) |
| 粒度 | sentence-level fact entry | edge-level (subject-relation-object) |
| 儲存 | UPDATE 直接覆寫文字 / DELETE 刪除 | 新舊 edge 都保留,只在舊 edge 加 `invalid_at` metadata |

⚠️ **Caveat**: Zep 的具體 supersession decision 行為**只能從 output 的 `invalid_at` 標記倒推**,我們無法看到 Zep cloud 真實內部 LLM trace。

#### §2.1.B [HIGH] 偵測完整覆蓋率

`all_detected` = 該題所有 has_pair hops 都被偵測對。

| | FC-SH coverage | FC-MH coverage |
|---|---|---|
| Mem0 | 33/74 has_pair = **45%** | 26/100 = **26%** |
| Zep | 18/74 = **24%** | 8/100 = **8%** |

→ **生產系統的偵測完整性遠低於 50%,MH 更差到 8-26%**。Mem0 比 Zep 高近一倍但仍不夠。

**Paper-ready takeaway**: 偵測本身就是現有 paradigm 的瓶頸之一,尤其在 multi-hop。

### §2.2 [MEDIUM with caveat] Detection × Answer 對照

> ⚠️ **Major caveat**: 此 cross-tab 數字是真,但解讀受 §0.1 B1 (Mem0 fact extraction bias) + B2 (Zep 黑箱) 影響。具體是**生產系統在 FC-OOD 的 endpoint 觀察**,**不能解讀為「衝突 paradigm 本身的能力」**。

| Bucket | Mem0 SH | Mem0 MH | Zep SH | Zep MH |
|---|---|---|---|---|
| all_detected EM | 91% (30/33) | 77% (20/26) | 89% (16/18) | **0%** (0/8) |
| partial EM | — | 42% (14/33) | — | 6% (1/18) |
| no_detection EM | 56% (23/41) | 22% (9/41) | 68% (38/56) | 9% (7/74) |

**HIGH-confidence 子 claim**:
- **Zep all_det MH = 0%**: 即使偵測完美,LLM 在 multi-hop 仍全錯 → annotation paradigm 在 multi-hop 沒 propagate (8 題 sample 雖小,趨勢明確)
- **Mem0 all_det MH = 77% > Mem0 no_det MH = 22%**: filter paradigm 偵測對顯著有助,**但 77% 並非全靠 mechanism** (見下方 caveat)

**MEDIUM-confidence 子 claim** (有 bias caveat):
- Mem0 no_det MH 22% 答對 — 部分是 W4 extraction miss accidentally helped (chain_old 從未抽進 store), 不能算 mechanism 真功勞
- Zep no_det MH 9% 答對 — 抽樣顯示主要是 fuzzy match artifact (LLM 同提兩版本,GT 字串恰好出現在 pred 裡)

⚠️ **不要**從這 cross-tab 直接 claim「Mem0 機制比 Zep 強」 — 機制比較需要排除 fact extraction asymmetry。

### §2.3 [LOW — APPENDIX] Failure mode bucket classification

> ⚠️ **Low confidence**: bucket 邊界用 fuzzy match 定義,satellite leak vs parametric leak vs retrieval miss 之間區分有 ambiguity。**這段建議放 appendix 作 qualitative case study**,不放 main text。

#### §2.3.A 整體分布 (qualitative anecdote)

| Failure bucket | Mem0 wrong (n=57) | Zep wrong (n=92) |
|---|---|---|
| chain_old direct in retrieval | ~16 (28%) | ~90 (98%) |
| OLD-entity satellite leak | ~26 (46%) | 1 |
| Parametric / world-knowledge | ~5 (9%) | 0 |
| Gave up | ~6 (11%) | ~13 (14%) |
| Hallucinated | ~4 (7%) | ~1 |

**Qualitative observation**: 兩系統的 wrong **約 82% LLM output 含 chain_old 答案**, 但這個比例本身受 fuzzy match leniency 影響。具體 bucket attribution 要小心。

#### §2.3.B 三個 case study (作為 appendix illustration)

- **q13 (Mem0 direct old leak)**: chain_old 兩 facts 都在 top-100,LLM 直接串 OLD chain
- **q6 (Mem0 satellite leak)**: chain_old 已被 W1 移除,但 OLD-entity (Jack Dorsey) 的其他 fact 仍在,top-1 cosine 高
- **q2 (Zep invalid_at marked but ignored)**: chain_old edge 標 invalid_at,LLM 仍答 OLD chain

⚠️ 這些 case 是真,但「這些是 dominant cause」不能 claim — 在 controlled scope 之外。

### §2.4 [HIGH] Two Research Claims — Mem0/Zep 的 research gap thesis

> 排除 §2.2 / §2.3 的不確定後,結合 §2.1 偵測 coverage 數據 + §3 channel ceiling + §3.3 parametric override evidence,我們對「現有多輪對話場景下含衝突機制的記憶方法」(以 Mem0/Zep 為代表) 提出兩個 orthogonal axis 的 research gap claims。
>
> 這兩個 claims 是 paper §4 method design 的直接 motivation,也是 Phase 1 / Phase 2 設計的依據。

---

#### 🎯 Claim 1 [Retrieval-side gap]

**Statement**:
> **在 LLM 看到的 retrieval context 中,query-related old fact (含直接 chain conflict 與 OLD-entity satellite) 越少越好;且最優先要清除的是 query-related old (而非 query-unrelated old)。**

**精確化**: "query-related" 含兩種,paper 必須拆清:

| 類型 | 定義 | 例 (q6 hop0) |
|---|---|---|
| **直接 chain conflict** | 與當前 query 多跳 chain 中某 hop 的 (S, R, O_new) 衝突的 (S, R, O_old) | "Twitter CEO is Jack Dorsey" (chain_old) |
| **OLD-entity satellite** | 涉及 OLD entity 但非衝突對的其他 facts | "Jack Dorsey is a citizen of US" |

**Evidence map (HIGH confidence)**:

| 主張部分 | Evidence | 數字 |
|---|---|---|
| Old in noisy context = toxic | Sim-OB Mode B vs Mode C n=1 | 60% → 9% (-51pp,conflict×noise 交互) |
| 移 query-related old = 主要 gain | OA2 vs HippoRAG vanilla (orig) | 55% vs 22% = +33pp |
| 移 query-unrelated old = 邊際 | NC vs OA2 (orig) | 60% vs 55% = +5pp 邊際 |
| Satellite leak 也須處理 | Mem0 q6 case study | top-1 retrieval 是 OLD-entity satellite (cosine 0.496) |
| Old 單獨 (無噪音) 影響輕 | Mode A rule-clean | 92% (僅 -5pp from chain-only 97%) |

**Mem0/Zep 對應的 gap**:
- **Mem0**: filter 只處理 conflict pair,**沒處理 entity-level satellite** (q6 失敗)
- **Zep**: invalid_at 只標 metadata,**OLD edge + episodes 仍出現在 LLM context** (98% wrongs 都有 chain_old 直接 visible)
- 兩者偵測 coverage 都不夠 (Mem0 26%, Zep 8% on FC-MH 完美偵測率)

---

#### 🎯 Claim 2 [Inference-side gap]

**Statement**:
> **即使有衝突相關預處理 (Mem0 filter / Zep invalid_at) + retrieved context, LLM 在 multi-hop chain 上的推理仍不夠穩定。具體三個不穩定模式:(a) mid-chain regression 到 OLD;(b) give up 棄答;(c) 忽略 metadata signal。**

**精確化**: "推理不穩定" 含三個具體 mode:

| 不穩定模式 | 例 | 失敗源 |
|---|---|---|
| **Mid-chain regression** | q7: hop0 用 NEW (Bengaluru),hop1 切回 OLD (Asia) | LLM 部分應用 rule,parametric prior 在某 hop 蓋過 |
| **Give up** | q5/q15/q50: "Information not provided" | LLM 看到 NEW 但不確定能否用,棄答 |
| **Metadata ignore** | Zep all_det MH = 0%: invalid_at 標但 LLM 不讀 | 弱 prompt-level signal 在多跳 reasoning 失靈 |

**Evidence map (HIGH confidence)**:

| 主張部分 | Evidence | 數字 |
|---|---|---|
| Filter 對也仍失敗 | Mem0 all_det MH | 77% (而非 100%, -23pp 失敗) |
| Annotation 對完全失靈 | Zep all_det MH | **0%** (8 題 sample) |
| 純淨 chain 仍不穩定 | Mode A rule-clean (chain only, 0 noise) | 92% (8 題 parametric override / give up) |
| 結構化 prompt 大幅穩定 | OA2 trailer effect | 55% → 83% = **+28pp** |
| Trailer 在 noisy context 無效 | Vanilla / A1 trailer effect | 22% → 23% = +1pp |
| Trailer 在 saturated context 飽和 | Sim-OB chain-only trailer | 97% → 98% = +1pp |

→ Trailer effect 的 **inverted-U** (在 mid-clean context 最強, +28pp on OA2): **filter 跟 prompt-level reasoning guide 是 complementary axis,不是 substitute**。

**Mem0/Zep 對應的 gap**:
- **Mem0**: 即使 filter 對,LLM 推理仍 23% 失敗 — 沒有 inference-time 穩定機制 (bare question + memories,沒 trailer 沒 CoT)
- **Zep**: 即使 timestamp 對,LLM 完全不讀 metadata 在 multi-hop — annotation 不 propagate (`invalid_at` 太弱)
- 兩者都是 "filter/annotate 後就 single-shot 餵 LLM",**沒有 multi-hop 結構化 prompt 強制 step-by-step 用 context**

---

#### Two claims 合起來作 research gap thesis

```
Research Gap = Claim 1 (retrieval-side) + Claim 2 (inference-side)

  Mem0/Zep 在 FC-MH 失敗 = 兩個 axis 的 gap 同時存在:
  
  Axis 1 (retrieval)   ─── 偵測+過濾不完整;OLD entity satellite 沒處理
                            ↓
                            導致 LLM context 仍有 query-related old
                            
  Axis 2 (inference)   ─── 即使 context 乾淨,LLM 在多跳上仍不穩定
                            mid-chain regression / give up / metadata ignore
                            ↓
                            需要結構化 prompt + per-hop reasoning 強制

  → 我們的方法分對應兩 axis:
    Phase 1 (Claim 1 解法) = filter (高信心) + entity-aware satellite handling
    Phase 2 (Claim 2 解法) = chain-aware retrieval + trailer/CoT prompt
```

---

#### ⚠️ Reviewer attack vector + paper 該 disclose

1. **"Evidence 都從 FC-MH,FC 是 explicit triple conflict 特殊 scope,claim 怎 generalize?"**
   - 需要 survey 文獻: LongMemEval-KU / MemBench / BEAM 是否含類似 conflict
   - 若其他 scope 也成立 → claim robust
   - 若只 FC 成立 → 改 framing 為「explicit-conflict 多跳記憶更新」更窄但仍 valuable

2. **"Mem0/Zep 數字含 §0.1 三個 bias (B1/B2/B3),怎能用作 research gap evidence?"**
   - Claim 1/2 主要用 §3 channel ceiling (HippoRAG 控制實驗) 跟 trailer ablation 撐
   - Mem0/Zep 數字僅作 illustration,不是 load-bearing
   - 需要 paper 顯式 distinguish 兩種 evidence 強度

3. **"Mode A 92% rule-clean 的 8 題失敗,有多少是 LLM model 特定 (Gemini 3.1 FL)?"**
   - 跨 model 驗證可選做 (如 GPT-4o-mini Mode A) 確認 parametric override 是 LLM 通性而非 Gemini bug
   - 如時間有限,paper 標明 "evidence based on Gemini 3.1 FL Preview" 即可

---

## §3 [HIGH] Channel ceiling + 失敗成因解構 — 主論述線之一

> **此段是 paper 最 robust 的部分** — 用 HippoRAG-v2 控制實驗,完全不碰 Mem0/Zep ingestion,沒有 §0.1 三個 bias。

### §3.1 [HIGH] Oracle channel ceiling — 含 NC 的對照

| Setup | FC-MH (orig prompt) | gap from prev | gap source |
|---|---|---|---|
| **Sim-OB chain-only** (chain 強制可見, 0 distractors) | **97%** | — | 上限 (LLM reasoning ceiling) |
| **NC baseline** (全 chain_olds 全域移, HippoRAG retrieval) | **60%** | -37 | retrieval coverage 損失 + 多跳 reasoning + parametric leakage |
| **OA2 fact-level** (本題 chain_olds 移, HippoRAG retrieval) | **55%** | -5 | 其他題 chain_olds 殘留 noise |
| **Mem0 customized** (production filter) | 43% | -12 | filter 不完美 + satellite leak (production reality) |
| **HippoRAG vanilla** (no conflict mech) | 22% | -21 | 衝突完全沒處理 |
| **Zep** | 8% | -14 | annotation 不 propagate (production reality) |

**關鍵 reading** (你提的兩個洞察):
- **NC vs OA2 只差 5pp**: 移除「本題 chain_olds」就拿走主要紅利,移除「其他題 chain_olds」邊際效益小
- **Method scope 空間**:
  - 22 → 55 = 33pp gap = **filter paradigm 主要 motivation 空間**
  - 55 → 60 = 5pp 邊際 (難拿,需要全域知識)
  - 60 → 97 = 37pp **超出衝突解決研究範圍** (retrieval coverage / 多跳 reasoning / parametric leakage 是另一個維度)

### §3.2 [HIGH] Sim-OB ladder — 失敗成因量化拆解

> 控制實驗 (rule-clean 96 題, orig prompt) — 用 HippoRAG-v2 套件,完全不碰生產 memory 系統。

| 條件 | acc | 拆解 |
|---|---|---|
| chain new only,無 distractor (Sim-OB chain-only) | 97% | 上限 |
| + chain old (無噪音, Mode A) | 92% | conflict 單獨 -5pp |
| + 純噪音 saturated (無 chain old, Mode B k=447) | **60%** | noise 單獨 -37pp |
| + 純噪音 + 1 chain old (Mode C n=1) | **9%** | **conflict×noise 交互 -49pp** |
| + 純噪音 + N chain olds (Mode C n=N) | 0-3% | 4-hop 完全沒 tolerance |

**Paper-ready takeaway**:
- Conflict 單獨輕微 (5pp)
- 噪音單獨可忍 (37pp)
- **真正的 killer 是兩者交互** — 注入 1 chain_old 到飽和噪音上,額外掉 49pp
- 這驗證**為什麼「只 filter conflict pair」(Mem0) 還會失敗** — 噪音裡的 satellite + 多 chunk 之間殘留 OLD 都會跟剩餘 chain_old 形成同樣的 toxic interaction

### §3.3 [HIGH framing, MEDIUM scope] FC 為什麼是難的 testbed — parametric override evidence

**MQuAKE-CF 的結構特殊性**:
- Facts 是**通用真實事實** (Twitter CEO、首都、運動發源國...)
- LLM pretrain 已內化這些事實,有強 prior
- 即使外部 memory 給乾淨 NEW context,LLM 有機會 fall back to parametric

**對比 personal-facts benchmark** (LongMemEval): "user 的生日是 X" 這類 fact LLM 完全沒 prior,失敗只可能來自記憶系統。

#### §3.3.A Mode A 8 題 rule-clean 失敗的具體 parametric override evidence

> Mode A = chain new + chain old facts only (rule-clean 96 題, orig prompt with seq rule wrapper)。文字僅 4-8 facts,LLM 應該幾乎全對。實際 92% (88/96),8 題失敗檢視:

| qid | LLM 行為 | 真實世界 prior 干擾點 |
|---|---|---|
| **q5** | hop0 該選 Wilhelm II (seq 369 NEW) 但選 Elena Ceaușescu (seq 58 OLD) | Nicolae 真實配偶是 Elena |
| **q10** | hop0 該選 Adalbert (360 NEW) 但選 Maharishi (154 OLD) | TM 真實創辦人是 Maharishi |
| **q15** | 3-hop chain 中斷,答 "Information not provided" | "basketball 創於 Soviet Union" 太反真實 |
| **q50** | hop1 該選 Alan Jay Lerner (424 NEW) 但選 Cherie Blair (141 OLD) | Tony Blair 真實配偶是 Cherie |
| **q58** | hop1 chain 不出來 | "Walter Chrysler 是 Sasanian Empire 創辦人" 太反真實 |
| **q7** | hop0 用 NEW (Bengaluru),hop1 切回 OLD (Asia) | Bengaluru 真實在 Asia |
| **q56** | hop0 用 NEW (Germany),hop1 切回 OLD (Europe) | Germany 真實在 Europe |
| q62 | thought 提到 Ernst Heinkel (GT) 但 final answer extraction 抓到 "Director" | (eval issue,非 LLM 錯) |

**Pattern**:
- 5/8 直接違反 seq rule,選 OLD 因為 OLD = pretrain 真實答案
- 2/8 部分應用 seq rule,在 chain 中後段切回 OLD (parametric prior 強的 hop)
- 1/8 是 eval 抽取問題

→ **即使 chain 文字極短 + seq rule 顯式提示,LLM 仍在 ~5% 題目上被 parametric override**。這驗證 FC 失敗的 parametric leakage 維度,且這個 floor cost 任何 method 都很難消除。

#### §3.3.B FC 失敗的兩個額外維度

1. **parametric override** (LLM 信自己 prior 多於 context) — §3.3.A 量化證據
2. **cross-question edit collision** (4 題 rule-violation, 見 §5 caveats)

→ FC 是衡量「外部記憶能否真正 override 內部記憶」的好 testbed,**但 60→97 的 37pp gap 中:**
- ~5pp 是 parametric leakage 的 hard ceiling (Sim-OB 97% 已含這部分,Mode A 92% 多扣的 5pp 是 OLD 提供 parametric-friendly alternative)
- ~32pp 是 retrieval coverage / 多跳 reasoning 的 inherent 困難
- **這 37pp 不在「衝突解決」研究範圍內**

→ **Method scope 修正**: 22% → ~55-60% reachable;**~92% 是含 parametric leakage 的 hard ceiling**,paper 應該 disclose 我們不挑戰這個 floor。

---

## §4 Method Design (待後續討論)

### §4.1 預定 4-layer 架構

| Layer | 階段 | 任務 | 對應現有方法 | 改進方向 |
|---|---|---|---|---|
| **L0** | write-time | 衝突偵測 + KG state versioning | Mem0 UPDATE / Zep invalid_at | **跨 chunk 衝突偵測 + 同 chunk 也要處理** |
| **L1** | query-time retrieval | chain-aware 多跳遍歷,避開 satellite | Mem0 cosine top-K / Zep edge search | **graph traversal by hop**,不依賴純 cosine |
| **L2** | query-time filter | 用 L0 的 versioning 跳過 superseded edge | Zep 把 invalid_at 顯示給 LLM (不夠) | **直接不 retrieve invalid edge**,不只標 metadata |
| **L3** | inference | 強 prompt 確保 LLM 用 retrieved context | Mem0/Zep 都 bare question | **trailer-style 強制 step-by-step**,**不用 seq rule** (避免 FC-specific crutch) |

### §4.2 Method scope 約束

- **目標**: 22% (vanilla) → 55-60% (oracle ceiling)
- **不挑戰**: 60→97 的 retrieval coverage / parametric leakage
- **HippoRAG-v2 既有架構**: KG (entity nodes + relation edges via LLM extraction) + PPR retrieval + 純 LLM inference
- **HippoRAG 缺的** (要加上去的): edge versioning, supersession detection, chain-aware retrieval
- **HippoRAG 有的** (對衝突機制有用的): structured edges (S, R, O 有 supersession anchor), passage-entity mapping, episode/chunk metadata 可加 timestamp

### §4.3 評估約束 (你提的)

- 改進版**不用 seq rule prompt** — 跟 Mem0/Zep 一樣 bare question 進 inference
- 序號規則是 FC benchmark 人工 crutch, 不能 generalize
- 真正能 generalize 的方法應該:
  - 從**內容相似度** (entity-relation match) 偵測衝突
  - 用**時間 / ingestion order** 決定誰新誰舊
  - **不依賴 prompt 裡寫明 rule**

---

## §5 Caveats (整合在最開頭 §0,此處 cross-reference)

1. **§0.1 B1**: Mem0 fact extraction prompt 修改造成 OLD/NEW 抽取不對稱 — 影響 §2 的 attribution
2. **§0.1 B2**: Zep cloud 黑箱 — graphiti 是 reference,**不能等同 cloud 行為**
3. **§0.1 B3**: FC 是 Mem0/Zep 的 OOD scenario — 不是 native 評估
4. **4 題 rule-violation** (q44/q67/q86/q98): MQuAKE-CF 跨題 edit collision 導致 FC 序號 rule 與題目 GT 矛盾。所有實驗以 rule-clean 96 為主報告
5. **Same-chunk conflict**: FC chunk_size=512 下 old/new 大概率分屬不同 chunks,沒 stress-tested
6. **Mem0 over-fire**: 230/541 = 42% UPDATE events 不對應 GT pair,可能 inflate detection metric
7. **Zep 黑箱 (B2 重述)**: detection / supersession / context summary 都是 cloud 內部 LLM,只能對齊 inference LLM 為 Gemini

---

## §6 對應 figure 規劃

### High-confidence figures (paper main text)

- **Fig 1** (§1): SH→MH drop bar chart — 3 systems × 2 splits
- **Fig 2** (§3.1): Channel ceiling ladder — Sim-OB → NC → OA2 → Mem0 → Vanilla → Zep horizontal bar
- **Fig 3** (§3.2): Sim-OB ladder line — Mode A/B/C, conflict×noise interaction visualization
- **Fig 4** (§2.1.B): Detection coverage bar — Mem0 vs Zep, SH vs MH

### Medium/Low-confidence figures (appendix)

- **Fig A1** (§2.2): Detection × Answer cross-tab heatmap — with caveat overlay
- **Fig A2** (§2.3): Failure mode case studies — q13, q6, q2 annotated retrieval

---

## §7 對 Claude chat 討論 method 的 bridge

此份 outline 把目前 codebase 跑出來的實驗整理成 paper-ready evidence,並標出每個 claim 的 confidence 與 caveat。Method design 階段使用此 outline 時:

- **必看**: §3 ceiling + ladder (HIGH confidence,scope 量化的依據)
- **可參考但需 caveat**: §2 偵測觀察 (MEDIUM,有 bias 來源)
- **慎用**: §2.3 失敗 bucket 的具體比例 (LOW)
- **必查**: §0.1 三個 bias 來源,跟 §4.3 評估約束 (改進版不用 seq rule)

Method 設計討論的入口問題:
- L0 write-time detection 的具體機制? (LLM judge 像 Mem0/Zep,還是 deterministic edge constraint)
- L1 chain-aware retrieval 怎麼做? (sequential decomposition vs graph walk)
- L0 同 chunk 衝突處理?
- L2 filter 而非 annotate 的 KG 操作?
