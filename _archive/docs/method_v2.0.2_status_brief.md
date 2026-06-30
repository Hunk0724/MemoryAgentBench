# Method v2.0.2 — Implementation Status Brief_v2

> **目的**:給 chat 同步當前 v2.0.2 實作狀況、結果、設計合理性,以便共同討論改進。
> **配套**:`method_design_v2.0.2_spec.md`(完整 spec) / `analysis/results/full100_eval/labels.json`(GT)。

---

## 0. 執行摘要(TL;DR)

### 0.1 方法設計架構

在 vanilla HippoRAG-v2 上加 3 phase(對外維持 chunk-level retrieval,對內用 proposition 做 supersession 處理):

| Phase | 做什麼 | 狀態 |
|---|---|---|
| **Phase 1** Proposition Layer | indexing 時抽 atomic proposition(完整句意 + 時間戳),作 out-of-KG annotation | ✅ |
| **Phase 2** Chain-Restricted Verdict + Filter | query 時找候選推理鏈 → 對 chain prop 做「LLM identify 語意對立 + code 機械方向判時序」→ filter drop chain_old passages | ✅(核心 contribution)|
| **Phase 3** Enriched Context | 把 verdict 結果注入 LLM prompt(Reasoning Hints + Recent Updates)| ⚠️ 實測無 EM 貢獻 → skip |

### 0.2 結果表現(FC-MH 100Q,Gemini 3.1 Flash-Lite + NV-Embed-v2)

| Ablation | EM | Δ |
|---|---|---|
| A. vanilla(我們重跑)| 17/100 | baseline |
| **B. + Phase 2(chain detect + verdict + filter)** | **31/100** | **+14pt** ⭐ |
| C. + Phase 3 full | 31/100 | +0(W3 無貢獻)|
| D. Phase 3 minimal(no filter)| 15/100 | −2(Phase 2 系統性錯,非 W3 害)|

+14pt 來源:filter drop chain_old passages → LLM 看不到 OLD → 答 NEW。

### 0.3 是否能跟 Mem0 / Zep 比較

**可以比較**(同 FC-MH 6k benchmark + 同 Gemini 3.1 Flash-Lite + 同 FC seq-rule wrapper),但有 caveat。

| System | FC-MH EM | 處理時機 |
|---|---|---|
| HippoRAG-v2 vanilla(motivation 基線)| 22% | — |
| Zep | 28% | inference-time annotation |
| **我們 Phase 2** | **31%** | query-time verdict + filter |
| **Mem0 customized** | **44%** | write-time filter |

- ✅ **比 vanilla(22%)+ Zep(28%)好**
- ❌ **還沒贏 Mem0(44%)— 差 13pt**
- ⚠️ **Baseline alignment caveat**:我們重跑的 vanilla = 17%,motivation 紀錄 = 22%(5pt gap,input_len 一致但可能 LLM 版本/temperature 微差)→ 跨系統絕對數字對照前需先 re-verify 對齊
- 詳見 §6.6

### 0.4 接下來的方法改進方向

Cascade 分析定位兩個 attrition(其餘階段 verdict 機制完美):

| 改進 | 攻擊 stage | 預期 |
|---|---|---|
| **P1 chain enumeration**(beam=16, L=4, score weights)| chain_OLD 進 chain 67%→80%+(4-hop 37% 是死區)| +3-5pt |
| **P2 filter redesign**(`drop_all_old + inject_confirmed_new`,取消過寬 rescue)| chain_OLD chunk drop 51%→65%+ | +3-5pt |
| 合計 | | EM 31 → **38-42**(目標接近 Mem0 44%)|

W3 Phase 3:skip(P-main inject 已涵蓋,留 future work)。

---

## 1. 為什麼這樣設計(核心 framing)

**問題**:HippoRAG-v2 在 FactConsolidation(MQuAKE-style counterfactual)上 multi-hop 17% EM。每個 query 的推理鏈中有 ≥1 個 hop 含 NEW/OLD 對立(`X 主席是 A`(turn 0) → `X 主席是 B`(turn 6)),LLM 答題時 retrieved passages 同時含 NEW + OLD,LLM 不知該選哪個,常選 OLD(因 OLD 有時是 real-world plausible 那個)。

**設計約束**(來自社群相容性):
- 對話記憶社群(Mem0 / Zep / LongMemEval)的 benchmark 約定 retrieval unit = **chunk/passage**
- 不能換 retrieval unit(會破壞跨 baseline 比較)
- → 對外仍 return passages,只在**內部處理**用 proposition

**三 phase 解法**:

| Phase | 目的 | 借鑒 | 創新點 |
|---|---|---|---|
| **Phase 1** | 抽 atomic proposition 作為 supersession verdict 的單位 | PropRAG 抽 prompt + hyperedge style entity connectivity | 抽完 prop 後是「out-of-KG annotation layer」,KG 結構不動 |
| **Phase 2** | Query 時找出 chain_old / chain_new pair,對立判定 | Mem0 small-pool insight (K_pool≤10) | (a) chain-restricted scope(不全 KG scan)+(b) **LLM identify + 機械方向**(v2.0.3 pivot,解 counterfactual 上的 LLM world-knowledge bias)|
| **Phase 3** | 把 verdict 結果回饋給 LLM 答題 prompt | — | enriched context 段落(Reasoning Hints + Recent Updates),**prompt template 不動**,只擴 body |

**核心概念**:對外 chunk-level retrieval(社群相容)+ 對內 prop-level 處理(supersession 精細度)+ LLM 兩段分工(語意 grouping 是 LLM 強項、時序方向是 code 強項)。

---

## 2. 目前 pipeline 流程(v2.0.2 + v2.0.3 verdict pivot)

```
Indexing:
  OpenIE → entity+passage nodes + fact edges + synonymy edges       ← vanilla HippoRAG-v2
  + PropRAG-prompt 抽 proposition (W1.1)                              ← 我們加
  + entity-entity hyperedges from prop entity-pairs (W2 Step 1, B 案) ← PropRAG-inspired

Retrieval:
  Vanilla:                          Phase 2 + 3 介入:
  query → fact rerank → PPR    →   Phase 2.a: prop_mass aggregate
       → chunk ranking                          → active region top-50
                                              → enumerate chains (beam=8, L=3, M=5)
                                   Phase 2.b: K_pool≤10 → LLM identify contradicting
                                              → 機械方向 from timestamps
                                   Phase 2.c: filter top-20 passages 含 chain_old (rescue 若含 current)
                                   Phase 3:   render Reasoning Hints + Recent Updates
                                              → inject into qa() prompt body

QA:
  prompt = "Wikipedia Title: <passage>" × K_qa
         + [Phase 3 enriched context, optional]
         + "Question: <q>\nThought:"
  → LLM 答 (Gemini 3.1 Flash-Lite)
```

---

## 2.5 Phase 2.b LLM Verdict — Pool 構造 + Prompt + Mapping Flow

### Pool 構造(2 signals + 1 protected channel)

```
本質只 2 種訊號 (從全 450 props 掃):
  Source 1: Entity overlap (substring entity match,e.g. focus 含 "Fatah" → 找所有提 Fatah 的)
  Source 2: Cosine similarity (focus.embedding × prop.embedding ≥ 0.7)
                                ↓
            Union, top-20 by (entity_overlap_count + cosine)
                                ↓
  γ protected channel: 其他 chain 上 entity-overlap prop 強制進 pool (bypass top-20 trim)
                                ↓
                       trim K_pool=10 by relevance to focus
                                ↓
                       每個 chain prop focus 各跑一次 LLM verdict
```

**γ 量化** (從 552 verdict events):0 events 只靠 γ 找 candidate(γ candidate **100% 也是 dynamic_lookup 能 find 的**)。γ 唯一 unique role = bypass top-20 trim,但這個 protected channel 的真實 added value 需要更精細 instrumentation 才能 verify(目前看可能是 implementation redundancy)。

### LLM Verdict Prompt(`verdict_prompt.py`)

LLM 看到的內容:

```
System: "You are a conflict identifier. Your job is to find pool statements
         that make CONTRADICTING claims with a focus statement..."

User:
  QUERY (for context only, do not use to judge): <query text>

  FOCUS:
  "<focus prop text>"

  POOL:
    [1] "<pool prop 1 text>"
    [2] "<pool prop 2 text>"
    ...
    [10] "<pool prop 10 text>"

  CRITICAL RULES:
    - Treat statements as opaque assertions (don't use real-world knowledge)
    - DO NOT consider timestamps
    - DO NOT decide current/outdated — only identify contradicting pairs

  [contradicting / not-contradicting 範例]

  Output (JSON only):
  { "contradicting_pool_indices": [<int>, ...], "reason": "..." }
```

**關鍵設計選擇**(W1.3 v2.0.3 pivot):
- Pool 用 `[1] [2] ...` 數字標號 → LLM 用 index 回答,parse 穩定 + 省 tokens
- **隱藏 timestamp**(防 LLM 用順序當方向 hint)
- **隱藏 chain context**(防 chain 順序污染)
- **`DO NOT consider timestamps` + `DO NOT decide current/outdated`** 雙重明示 → 解 W1.3 v1 counterfactual world-knowledge bias

### Output → Code Mapping(4 段)

```
[1] LLM returns JSON:
    {"contradicting_pool_indices": [1], "reason": "..."}
        ↓
[2] parse_verdict_response (verdict_prompt.py:102-148):
    strip markdown wrapper → json.loads → map index→pid via pool_number_to_pid
        ↓
    contradicting_pids = ["prop-fea1480e..."]  (e.g., Moshe-chairperson)
        ↓
[3] _decide_verdict_mechanically (verdict.py:278-333):
    focus.ts = (0, 1)  (Mahmoud)
    later = [pid for pid in contradicting_pids if pid.ts > focus.ts]
    if later: focus = superseded by max(later)
    elif contradicting_pids: focus = current (low, defensive)
    else:                    focus = current (high, no contradicting)
        ↓
    Verdict(status="superseded", superseder_id="prop-fea1480e...", confidence="high")
        ↓
[4] Filter (HippoRAG.py:1483):
    chain_old_pids = {pid | verdict.status='superseded', confidence≥medium}
    Top-20 retrieval passages 含 chain_old_pids prop → drop (除非 rescue)
```

### 整合 verdict 結果(目前 vs 完整 bidirectional 設計)

**目前(unidirectional)**:只看 `focus.status='superseded'` → 加入 `chain_old_pids`
```
focus = chain_OLD, contradicting=[chain_NEW] → focus.status='superseded' ✓ 加入
focus = chain_NEW, contradicting=[chain_OLD] → focus.status='current' ✗ 漏掉 chain_OLD
```

**完整 bidirectional 設計**(用戶 reframe):「所有經 LLM 偵測 + code 判 ts 後的 earlier 對立 props 都該加入 chain_old_pids,不分 chain_old 在 focus 還是 pool」。

實證量化 bidirectional 額外捕獲:
- 多識別 49 個 chain_old prop_ids,但**只 4 個對應 GT**(2-hop +1, 3-hop +1, 4-hop +2)
- 多 drop 43 個 chunks(其中 39 可能是 noise → false positive 風險)
- 工程量小(~1 hour),但風險中等。建議加 sanity check(高 LLM confidence 才 trigger inverse)

---

## 3. 實作進度 + 100Q 結果

| 階段 | 完成 | 一句話結論 |
|---|---|---|
| **W1.1** Proposition 抽取 | ✅ | PropRAG prompt port,450 props,yield 0.98 |
| **W1.2** Phase 2.a chain id | ✅ qualitative | beam search 用 cosine proxy 取代真 PPR |
| **W1.3** Phase 2.b verdict | ✅ design pivot | v2.0.3:LLM identify-only + 機械方向,解 counterfactual world-knowledge bias(spec §B.3.2.3)|
| **W1.4** Mini-eval framework | ✅ | 100Q hop-level prop_id GT,3 層指標分離 |
| **W2 Step 1** I3c hyperedge(option B)| ⚠️ partial | 真 PPR + entity-entity hyperedge,但因 atomic prop = 1 triple,hyperedge 跟 fact edge 100% 共 key,只 boost weight 沒新增結構性連結 |
| **W3** Phase 3 enriched context | ⚠️ infra pass | render + inject wire 通,但 EM 沒收益(見下)|

### 4-Ablation 結果(FC-MH 100Q,Gemini 3.1 Flash-Lite + NV-Embed-v2)

| Run | 設定 | EM | Δ vs vanilla |
|---|---|---|---|
| A. vanilla HippoRAG-v2 | no Phase 2 | **17/100** | — |
| B. + Phase 2(chain detect + verdict + filter)| | **31/100** | **+14pt** ⭐ |
| C. + W3 full(Hints + Updates + filter)| | **31/100** | +14pt(= B,W3 沒額外貢獻) |
| D. W3 minimal(no filter + Updates only)| | **15/100** | **−2pt** ❌ |

### Per-hop Cascade(B/C/D 三組 Phase 2 一致)

```
chain_new in active_region:  94%    ← Phase 2.a 起點良好
chain_new in any chain:      62%    ← beam=8/L=3 漏 32pt(主 attrition)
BOTH in SAME chain:          51%    ← 多 hop 配對丟失(spec target 70%)
Pool co-occurrence:          68%    ← spec target 80%
Verdict correct:             65%    ← 被 pool co 上限封頂
chain_old chunk dropped:     56%    ← filter 實際作用率
W3 update pair in enriched:  67%    (4-hop 只 37%)
```

#### Per-hop cascade — 怎麼算的

每個 query 在 `analysis/results/full100_eval/labels.json` 內有 hop-level GT:每 hop 有 `chain_new_matches[0].prop_id` + `chain_old_matches[0].prop_id`(若 conflict_type='has_pair')。對 100Q × 254 hops join `monitoring_logs/<ts>_ablation_<name>/phase2_w13_dump.jsonl`(每 query 一筆 dump)+ `verdict_events.jsonl`(每 LLM call 一筆),逐欄位算:

| Phase | Metric | 怎麼算 |
|---|---|---|
| 2.a | `new_in_active_region` | chain_new prop_id ∈ `dump.active_pids`(top-50 by mass) |
| 2.a | `new_in_any_chain` | chain_new prop_id ∈ ⋃ `dump.chains[i].proposition_ids` |
| 2.a | `BOTH_in_SAME_chain` | 存在 i 使 `new_pid ∈ chain[i] AND old_pid ∈ chain[i]` |
| 2.b | `pool_co_occurrence` | `old_pid ∈ pool_pids[focus=new] OR new_pid ∈ pool_pids[focus=old]`(從 verdict_events.jsonl 找) |
| 2.b | `verdict_correct` | `verdicts[old_pid].status='superseded' AND superseder_id == new_pid` |
| 2.c | `chain_old_chunk_dropped` | chain_old.source_chunk_id ∈ `dump.passages_dropped_chunk_ids` |
| 2.c | `chain_new_chunk_kept` | chain_new.source_chunk_id ∈ `dump.passages_kept_chunk_ids` |
| 2.c | `filter_effective` | both above true |
| 3 | `update_pair_in_enriched` | chain_new.text ⊂ `dump.enriched_context_text` AND chain_old.text ⊂ same |

只算 `phase2_status='RAN'` 且 GT prop_id 兩端都成功 mapping 的 has_pair hops(170/188 = 91%)。

腳本:`analysis/eval_100q_full_analysis.py`(吃 dump dir,輸出 cascade table + per-hop json)。

### Cross-ablation comparison(同題在 A/B/C/D 各對錯)

**4-way correctness pattern**(`analysis/eval_ablation_cross_compare.py` 輸出):

| A | B | C | D | count | 解讀 |
|---|---|---|---|---|---|
| 0 | 0 | 0 | 0 | **61** | 整 pipeline 救不到 |
| 0 | 1 | 1 | 0 | **18** | ★ **Phase 2 + filter 核心貢獻**(B/C 救到,D 不夠) |
| 1 | 1 | 1 | 1 | 11 | 所有 ablation 都對(query 不依賴衝突解析) |
| 1 | 0 | 0 | 0 | 5 | Phase 2 害了 vanilla 對的(B+C+D 都壞) |
| 其他 | | | | ≤ 1 | noise |

**B vs C 重疊(都 31/100)**:
- 30 題 overlap,**Jaccard = 0.94**
- W3 在 C 多救 1 題(no71 Connachta)、又壞 1 題(no11 Methodism)→ **W3 在 production = noise**

**A→B 的 +14pt 結構**:
| | 救對 | 害錯 | net |
|---|---|---|---|
| 2-hop | **15** | 4 | +11 |
| 3-hop | 4 | 1 | +3 |
| 4-hop | 1 | 1 | +0 |
| 按 has_pair=2 占救對 13/20 | | | |

B 害錯的 6 題(vanilla 對的):no28 Prague→None / no35 Fairly OddParents→Godfather / no54 Beaumont→Washington / no81 Ankara→"Not mentioned" / no82 Elizabeth II→Gorbachev / no96 Guangzhou→Paris(部分)。
注意 **no81 / no82 / no54 在 D 也害錯** → 是 **Phase 2 系統性錯**(chain detection 誤判 chain_new),不是 W3 的鍋。

**D 害錯 5 題 vanilla 對的**(net -2):no81 Ankara、no35 Fairly OddParents、no82 Elizabeth II、no96 Guangzhou、no54 Beaumont — 跟 B 害錯的 6 題高度重疊。

**結論**:
- Phase 2 真實效應 = +20 救對 − 6 害錯 = +14 net,主要救 2-hop has_pair=2 的 query
- W3 在現設計下完全是 noise(B↔C Jaccard 0.94)
- W3 minimal(D)看似害人是因為 filter 關掉,沒 W3 自己的問題;真實「W3 vs no-W3 同 filter 設定」差異 ≈ 0

---

## 4. 三個重大觀察(paper-grade finding)

**Finding 1: Phase 2.c filter passages 才是核心 +14pt 來源**(不是 verdict 本身)
- A→B 全靠 filter drop chain_old chunk(rate 56%)
- 簡單但有效機制:LLM 看不到 OLD 答案 → 自然答 NEW

**Finding 2: W3 enriched context 在 filter on 時 = no-op**
- C = B 都 31/100,token overhead 但 EM 沒進步
- 原因:LLM 從 filtered passages 已看不到 chain_old,enriched 的 Recent Updates 沒新資訊
- 原 spec §B.4.4 A3.1(預期 W3 +5pp)**未達成**

**Finding 3: D 看似害人(15 < A 17),但實際是 Phase 2 系統性錯,不是 W3 害的**(校正)

從 4-way pattern (A,B,C,D) cross-ablation 細查:
- D 害的 5 個 case 對應 pattern `(1, 0, 0, 0)` — **A 對,但 B+C+D 都錯**
- 即 **B 跟 D 害的是同 5 case**(Phase 2 chain detection 在這 5 個 query 系統性錯),W3 在 D **沒額外害任何 query**
- 真實「W3 vs no-W3 同 filter setting」isolated effect ≈ **net 0**(B↔C Jaccard 0.94,swap 1 對 / 1 錯)

→ Finding 不是「W3 害人」,而是「Phase 2 chain detection 在這 5 個 case 系統性錯導致 D 漏救」+「W3 本身 always net 0」。

---

## 4.5 Detailed Analyses + Key Findings

> 為支撐 §4 三個 high-level finding,以下 8 個細部分析逐一拆解 component。完整 table + chart 在 [`analysis/results/priority5/`](../analysis/results/priority5/)。

### A1 Filter Rescue Breakdown

對 219 個 top-20 內含 chain_old 的 passages 分類:

| 類別 | 數量 | % | 解讀 |
|---|---|---|---|
| Hard drop(filter 真生效)| 173 | 79% | 沒 rescue,正常 drop |
| Rescue w/ real chain_new(justified)| 22 | 10% | passage 內真有 chain_new,救得對 |
| Rescue w/ unrelated current(questionable)| 24 | 11% | passage 只是含「無關 current prop」就被救,**noise** |

**Finding**:rescue 一半(52% of rescued = 24/46)是 unrelated current 觸發 → **P2 filter rescue 收緊可清 24 個 noise rescue**。

### A2 Pool Sources Contribution

| Source | 用率 | 量化 |
|---|---|---|
| `dynamic_lookup`(entity overlap + cosine)| 552/552 = 100% | 主訊號 |
| `γ` opportunistic | 539/552 = 98% | 配對訊號 |
| Only γ(獨自有效)| **0 events** | γ 從未獨自找到 candidate |

**Finding**:γ candidate **100% 也是 dynamic_lookup 能找到**(γ 範圍 ⊂ dynamic_lookup 範圍)。γ 唯一可能 unique role = bypass top-20 trim,但未 instrument 驗證。**可能完全冗餘**。

### A3 LLM Identify Accuracy(conditional on pool co-occurrence)

| Hop | n | Identified | Accuracy |
|---|---|---|---|
| 2-hop | 73 | 71 | 97% |
| 3-hop | 29 | 28 | 97% |
| 4-hop | 13 | 13 | **100%** |
| **All** | **115** | **112** | **97%** |

**Finding**:**LLM identify 不是瓶頸**!verdict 機制本身近乎完美。改 prompt 收益接近 0。

### A4 Failure Cascade Root-cause(69 wrong queries 標 first-failed stage)

| Stage | Count | % | 解讀 |
|---|---|---|---|
| **F2** not both in chains | **27** | 39% | ★ chain enumeration 漏 — 主因 |
| F6 filter no drop | 18 | 26% | chunk 不在 top-20 retrieval |
| F7 LLM wrong despite clean context | 17 | 25% | context 已乾淨 LLM 仍答錯 |
| F4 LLM missed identify | 1 | 1.4% | 真正 verdict 階段失敗 |
| F5 verdict status wrong | 1 | 1.4% | |
| F7 other | 4 | 5.8% | no_pair query 答錯 |
| F0 no Phase 2 | 1 | 1.4% | DPR fallback |

**Finding**:
- 多 hop wrong **主因 F2 (chain enumeration 漏)** — 3-hop 61% / 4-hop 54% 的 wrong 都在這
- 2-hop wrong 主因是 F7 (LLM 答錯,不是 retrieval 機制)

### A5 Cascade Attrition by Hop(symmetric, both directions)

| Hop | n | Active | Chain Union | Pool co | Verdict | Filter |
|---|---|---|---|---|---|---|
| 2-hop | 87 | 100% | 80% | 84% | 83% | 68% |
| 3-hop | 48 | 90% | 50% | 60% | 58% | 58% |
| 4-hop | 35 | 83% | **29%** | 37% | 34% | 23% |

**Finding**:**Active → Chain 是主要 attrition**(4-hop -54pt!)。

### A5b Asymmetric Filter-Driven Cascade(校正版,符合 filter 真實 logic)

只看 chain_old 進 chain(不要求 chain_new 也進):

| Hop | n | S1 old∈chain | S2 new∈pool | S3 LLM ident | S4 verdict | S5 chunk∈top20 | S6 dropped |
|---|---|---|---|---|---|---|---|
| 2-hop | 87 | 83% | 83% | 81% | 81% | 81% | 64% |
| 3-hop | 48 | 58% | 58% | 58% | 58% | 58% | 47% |
| 4-hop | 35 | **37%** | 37% | 37% | 34% | 34% | **22%** |
| **All** | 170 | 67% | 67% | 66% | 65% | 65% | 51% |

**Finding**:
- **S1 → S2 → S3 → S4 幾乎零 attrition**(verdict 機制完美無瑕)
- 改進空間 100% 在 **S1(chain enumeration)+ S6(filter rescue)**

### A6 Filter+Inject Potential(chain_old chunk 分類)

| 類別 | 含義 | 數量 | % |
|---|---|---|---|
| **A SAFE_DROP** | chunk 不含任何 GT chain_new | 146 | **83%** |
| **B SAME_HOP_NEW** | chunk 內含同 hop 的 chain_new | 20 | 11% |
| **C CROSS_HOP_UNIQUE** | 含他 hop chain_new + 只此 chunk | 9 | 5% |
| **D CROSS_HOP_REDUNDANT** | 含他 hop chain_new + 也有別 chunk | 0 | 0% |

**Finding**:**83% 可放心 drop / 16%(B+C = 29 hops)必須 filter + inject chain_new prop text** 否則誤殺答案。

### A7 Bidirectional Verdict Quantification(user reframe)

| 設計 | chain_old 識別量 | GT recall gain | Extra chunk drop |
|---|---|---|---|
| Unidirectional(現實作)| 253 | — | — |
| Bidirectional | 302(+49)| **+4 GT** | **+43**(~39 noise risk)|

**Finding**:理論完整但**實證收益小**(+4 GT)**+ noise 風險大**(39/43 = 91% noise drop)。建議若做需加 LLM 高 confidence sanity check。

### A8 Per-hop EM by Ablation(已在 §3 列過,此處強調 hop pattern)

| Hop | n | A vanilla | B Phase 2 | Δ |
|---|---|---|---|---|
| 2-hop | 61 | 21% | **37%** | +16pt |
| 3-hop | 24 | 8% | **25%** | +17pt |
| 4-hop | 15 | 13% | **13%** | **+0pt** |

**Finding**:Phase 2 對 ≤3-hop 有效,**4-hop 完全 0pt**(被 S1 chain enumeration 37% recall 卡死)。

---

## 4.6 Deep-Dive 1: Phase 2 +14% 來源完整解剖

### 階段貢獻 cascade(170 has_pair hops,Ablation B)

| Stage | Survive | Loss | Cumulative |
|---|---|---|---|
| Start(理論上限)| 170 (100%) | — | — |
| **S1** chain_old 進 chain | 114 (67%) | **-33pt** ★ chain enumeration 漏 | 67% |
| S2 chain_new 進 pool | 114 (67%) | 0pt(完美)| 67% |
| S3 LLM identify | 112 (66%) | -1pt(完美)| 66% |
| S4 verdict superseded | 111 (65%) | -1pt(完美)| 65% |
| S5 chunk 在 top-20 | 111 (65%) | 0pt | 65% |
| **S6** chunk dropped(rescue 沒救)| 87 (51%) | **-14pt** ★ rescue 過寬 | 51% |

→ **+14pt EM 是這 87 個成功 drop 的 chain_old chunk** 帶來的:LLM 看不到 OLD → 答 NEW。

### 兩個 attrition 點 + 改進方向

| 攻擊點 | 現況 | 策略 | 預期救 hops | 預期 EM |
|---|---|---|---|---|
| **S1 chain enumeration** | 4h 37% / 3h 58% / 2h 83% | beam=16, L=4, sweep score weights | ~22 hops | +5-7pt |
| **S6 filter rescue** | 51% effective | rescue 收緊 + inject chain_new prop text | ~24 hops | +3-5pt |
| **合起來** | | | ~46 hops | EM 31 → **38-42** |

### EM gain by hop pattern(已在 §3 / §4.5 A8 列過,此處強調瓶頸對應)

| Hop | A vanilla | B Phase 2 | Δ | 卡哪 |
|---|---|---|---|---|
| 2-hop (61) | 21% | **37%** | +16pt | S1 83% / S6 64%(有空間)|
| 3-hop (24) | 8% | **25%** | +17pt | S1 58%(主限制)|
| 4-hop (15) | 13% | **13%** | **+0pt** | S1 37%(完全卡死)|

→ Phase 2 在 ≤3-hop 有效,**4-hop 完全 0pt**(被 S1 卡死)。

### 為什麼 verdict 中間段(S2-S5)完美 — 是否值得攻擊?

- S1→S2 0pt:dynamic_lookup 對全 450 props 跑 entity overlap+cosine,「chain_old 進 chain 後 chain_new 進 pool」幾乎必然
- S3 LLM identify 97%:v2.0.3 pivot(拿掉 ts/chain context)+ NLI 本質強項
- S4 機械方向 100%:純比 ts,沒模糊空間

→ verdict 機制**已 saturated**,改 LLM prompt / pool sources / mechanical logic **收益接近 0**。**改進空間 100% 在頭尾(S1 + S6)**。

### Chain_OLD Recall by Stage(per-hop,filter 真正依賴的 path)

Filter drop 的對象是 chain_OLD,所以「chain_OLD 走到每階段的存活率」才是 filter 的真實 recall:

| Stage | 2-hop (87) | 3-hop (48) | 4-hop (35) | All (170) |
|---|---|---|---|---|
| S1 in active region(top-50)| 100% | 90% | 86% | **94%** |
| **S2 in any chain(成為 focus)** | **84%** | **58%** | **37%** | **67%** ★ |
| S3 verdict ran | 84% | 58% | 37% | 67% |
| S4 chain_new 進 pool | 84% | 58% | 37% | 67% |
| S5 LLM identify | 82% | 58% | 37% | 66% |
| S6 marked superseded | 82% | 58% | 34% | 65% |
| S7 chunk 在 top-20 | 82% | 58% | 34% | 65% |
| **S8 chunk dropped(rescue 沒救)** | **64%** | **48%** | **23%** | **51%** ★ |

**兩個 attrition points**(其餘 6 stage 幾乎零損失,verdict 機制完美):
- **S1 → S2 chain enumeration**:全 -46 hops(-27pp)。4-hop 從 active 86% 跳水到 chain 37%(-49pp 內含 S1→S2)。**核心瓶頸**。
- **S7 → S8 filter rescue**:全 -24 hops(-14pp)。2-hop 從 82% 掉到 64%。

→ **chain_OLD 進 chain(S2)是 +14pt 的真正限制因子**,4-hop 只 37% → 4-hop EM 完全 0pt。

### Chain 內 prop 的真實組成(關鍵理解校正)

當前 candidate chain enumeration **supersession-agnostic**,chain 內 prop 實際上含 4 種類型(對 query 而言):

| Prop 類型 | 對 query 推理鏈關係 | 對 filter 機制影響 |
|---|---|---|
| **query-relevant chain_NEW** | 我們要的 NEW(query GT chain_new)| verdict 標 current → **不 drop chunk**(正確)|
| **query-relevant chain_OLD** | 要 filter 掉的 OLD | verdict 標 superseded → **drop chunk**(正確)|
| **query-IRRELEVANT current**(other_NEW) | 其他 entity 的新 fact,跟 query 無關 | verdict 標 current → **觸發 rescue**(保留 chunk)— **noise!** |
| **query-IRRELEVANT superseded**(other_OLD)| 其他 entity 的舊 fact,跟 query 無關 | verdict 標 superseded → **drop chunk**(無害)|

實證量化(B run,98 queries):
- chain[0] 內 **67%** prop 是 query-relevant(chain_new/old of some hop)
- **33%** prop 是 query-IRRELEVANT(other current / other superseded)
- 按 hop:**2-hop 72% / 3-hop 64% / 4-hop 50%** ← 4-hop 一半 noise

### 目前 filter 行為 vs 真實需求

**目前 filter 邏輯**:
```
所有 verdict.status='superseded' (any prop) → 加 chain_old_pids → drop chunk
所有 verdict.status='current' (any prop, query-relevant 或 irrelevant)
  → 在 chain_old chunk 內 → 觸發 rescue → keep chunk
```

→ **rescue 不分「query-relevant chain_new」跟「query-irrelevant other_new」**,只要 chunk 內有任何 current prop 就保留。

A1 量化:**rescue 內 52% (24/46) 是「query-irrelevant current」觸發**(noise rescue) → 對應 P-main `drop_all_old + inject_confirmed_new` 的設計動機。

---

## 4.7 Deep-Dive 2: Phase 3 為什麼沒貢獻 + 為什麼 D 看似退步

### W3 真實 isolated effect = net 0(同 filter setting 對照)

| Run | Filter | W3 | EM | 結論 |
|---|---|---|---|---|
| **B** | ON | OFF | 31 | baseline |
| **C** | ON | ON(full)| 31 | W3 isolated effect = **+0pt** |
| | | | Jaccard(B, C) = **0.94** | 30 題重疊,W3 swap 1 對 / 1 錯 |

→ W3 在 production 是 **noise swap**,不是真實 +EM 機制。

### 為什麼 D = 15 比 vanilla 17 還低 — **不是 W3 害的**

從 4-way pattern (A,B,C,D) cross-ablation 細查:

| Pattern | count | 解讀 |
|---|---|---|
| **(1, 0, 0, 0)** | **5** | A 對,但 B+C+D 都錯 ← **Phase 2 系統性害的 5 case** |
| (1, 0, 0, 1) | 1 | A+D 對,B+C 錯(W3 偶然救回 1)|

→ **D 害錯的 5 個 = B 害錯 6 個的子集**,是 **Phase 2 chain enumeration 在這 5 個系統性錯**(把 chain_new 也誤判進 chain_old_pids 或漏掉)。**W3 minimal 在 D 沒額外害任何 query**。

3 個 case 證據:
```
no81 Ankara:    A=Ankara ✓   B=Not mentioned ✗   D=Bucharest ✗
no35 Fairly:    A=Fairly ✓   B=Godfather ✗       D=Godfather ✗
no82 Eliz II:   A=Eliz II ✓  B=Gorbachev ✗       D=Gorbachev ✗
```

B 跟 D 答錯**同樣**答案 → Phase 2 chain detection 系統性錯,不是 W3 之間差異。

### W3 沒貢獻的三個原因 + 結構性根因

**原因 1:Filter on 時 enriched 完全 redundant**
```
Filter 已 drop 含 chain_OLD 的 passages
        ↓
LLM 看到的 retrieved passages 不含 OLD
        ↓
LLM 已能直接從 passages 答 chain_NEW
        ↓
W3 加 "Recent Updates: NEW (updates earlier: OLD)"
        ↓
        沒新資訊!LLM 從 passage 已知 NEW
```

**原因 2:同 prop 文字在 prompt 出現 3 次,LLM 注意力分散**

同 NEW prop 出現在:
- passage 內 numbered fact
- Reasoning Hints 列舉
- Recent Updates 列舉

→ 對 long-context LLM 是冗餘,沒額外受益。

**原因 3:"updates earlier: X" 措辭歧義**

對 case no27(4-hop Harrisville)實測:
- D predicted "Washington, D.C."(chain_OLD)
- 推測 LLM 可能誤解「updates earlier: X」為「X 才是更新的」

### W3 結構性沒 unique niche(根本問題)

```
W3 需要 verdict 結果(supersession_events)才能 render
   ↓
verdict 需要 chain_old 進 chain (S1) 才會有

如果 chain_old 沒進 chain (4-hop 63% 沒進):
   → 沒 supersession event → W3 沒這個 update 訊息 → W3 也救不到

如果 chain_old 進 chain → verdict 對 → filter 也會作用:
   → filter 已解決問題 → W3 變 redundant
```

→ **W3 不存在「filter 救不到但 W3 能救」的 niche**。**結構性原因,不是措辭微調能解**。

### W3 可改進方向(若仍想保留)

| 改動 | 動機 | 預期 EM | 工程量 |
|---|---|---|---|
| **P3.1** 改措辭 `"updates earlier: X"` → `"CURRENT FACT: X. (SUPERSEDES outdated: 'Y')"` | 消歧義 | +0-2pt | 0.3 天 |
| **P3.2** Prompt 內 dedup(同 prop 不重複 3 次)| 注意力 | +0-1pt | 0.3 天 |
| **P3.3** 條件式 inject(僅 filter rescue 觸發的 query 才注入 W3)| 切 W3 unique niche | +1-3pt | 0.5 天 |
| **P3.4** ★ **Reasoning Hints redesign β**:對 chain[0] 內 superseded → 替換為 superseder + dedup | 用 verdict 結果清洗 chain → 給 LLM cleaned reasoning path | +1-3pt | 0.3 天 |
| **P3.5** P3.4 + per-prop query relevance filter(cosine threshold)| 過濾 chain[0] 內 33% noise prop | +2-3pt | 0.5 天 |
| **P3.6** ★ **完全 skip W3** | P-main 的 `inject_confirmed_new` 已涵蓋 β 想做的事(直接從 verdict.superseder_id inject 純文字,不依賴 chain composition)| 0 | 0.1 天 |

### Reasoning Hints β 的設計侷限 — 為什麼 P-main inject 已涵蓋

```
β 設計:對 chain[0] 替換 superseded → superseder, dedup → cleaned chain
   但 chain[0] 內 33% prop 是 query-irrelevant noise (4-hop 50% noise)
   → β 可能展示 other_old→other_new 的替換,跟 query 推理鏈無關

P-main inject 設計:從 verdict.superseder_id 集合直接 inject chain_new prop text
   不依賴 chain[0] composition(直接從 verdict 結果取)
   → 完全避開 chain[0] noise 問題
```

→ **P-main inject 機制本質上就是「精準版的 β」**。Reasoning Hints redesign 變得 redundant。

→ **推薦 P3.6**:skip W3 整段,paper frame 為 "originally designed but found redundant; verdict-driven filter+inject suffices"。

---

## 5. W2 Step 1 I3c Hyperedge — 詳細實作 + 為何不夠 + 三個修法

> 這是目前實作面**最該優先迭代**的部分(cascade 顯示 Phase 2.a chain 62% / BOTH same chain 51% 是 attrition 主因,而 W2 Step 1 hyperedge 是直接影響這層的 indexing 動作)。

### 怎麼做的(三段)

**(1) entity_node_ids lazy resolve**(`_ensure_v2_phase2_loaded`):
- 對每 prop 的 `entities`(text list,來自 W1.1 PropRAG-prompt 抽取)→ `compute_mdhash_id(text_processing(e), prefix="entity-")`
- `text_processing` 跟 vanilla 一致(lowercase + 移除非英數字符) → 確保 hash 對得上 vanilla KG entity node key
- Sentinel 統計 KG 內找得到的比例(目前 ≥ 90%)

**(2) Hyperedge 加進 KG**(`_add_proposition_hyperedges_to_stats`,index() hook):
- 在 `add_passage_edges` 之後、`add_synonymy_edges` 之前
- 對每 prop 的 entity_node_ids,**兩兩**加 entity-entity edge:`node_to_node_stats[(e1, e2)] += 1.0` 雙向
- 過濾掉 entity 不在 vanilla KG 的(避免 orphan edge)
- 不加 prop node(option B,PropRAG-style hyperedge,KG 結構不動)
- 參考 PropRAG.py:944-995 的 `add_proposition_edges_with_entity_connections`(verbatim 同邏輯)

**(3) 真 PPR aggregation**(`_v2_phase2_pipeline`):
- vanilla retrieve 跑完後,從 `pagerank_scores[entity_vertex_idx]` 蒐成 dict
- `prop_mass[p] = mean(entity_ppr[e_id] for e_id in p.entity_node_ids)`(Q5 lock = mean,max 為 ablation flag)
- 取代 W1 cosine proxy
- defensive fallback to cosine proxy 若 PPR 全 0(沒進 entity PPR)

### 為何結構性沒新增 connectivity(關鍵限制)

**Atomic prop = 1 triple = 2 entities** 是 PropRAG 抽 prompt 的設計。當每 prop 只含 2 entities,加 hyperedge 等同加一條 (e_i, e_j) edge — 但 vanilla 早已有 fact edge `(s, o)`(同一個 triple 的 subject-object)。

實測量化:
- 加 hyperedge 後 igraph 內 `entity-entity` edges 仍是 **996 條**(同 backup graph,沒新增)
- `node_to_node_stats` 內 entry 數也不變(共用 key)
- 唯一差別:entity-entity edge **weight 從 1 升到 2**(累加)
- Weighted PPR 因此略有變化,但結構性連通性 = 0

**對 multi-hop 末端 entity 的影響**:
- query="OMF 作者的配偶國籍?",query-mention entity = "Our Mutual Friend"
- 末端 entity "Belgium" 在 vanilla KG 上要走 3-4 條 fact edge 才到 → PPR 多 hop 衰減 ≈ 0
- 加 hyperedge 後仍是同條路徑(因 hyperedge = fact edge 共 key),只是 weight 翻倍 → 衰減略慢但**沒短路徑**
- 結果:cascade `new_in_active_region` 94% 看起來 OK,但這是因為 prop 內 entities 多數已 query-mention;真正缺的是**末端 prop**(含 Belgium 那種)拿不到 mass

### 三個修法(優先嘗試)

**P1(最高優先,工程量低):chunk-level entities union clique**
- 對同 chunk 內**所有** prop 的 entities 取 union,然後**整 union 加 clique**
- 例:chunk 0 含 prop A "Darwin married Amala" + prop B "Amala citizen Belgium"
  - 目前 (atomic hyperedge): `(Darwin, Amala)` + `(Amala, Belgium)` 兩條 edge(都跟 fact edge 共 key)
  - **chunk-clique**: 多加 `(Darwin, Belgium)` 一條 — **這是新 edge 沒對應 fact**
- 為何高優先:
  - 結構性短路徑:query 從 "Our Mutual Friend"(seed)→ "Darwin"(fact edge)→ **"Belgium" (chunk-clique 直連)**,PPR mass 一步到位
  - 不需要重抽 prop;只改 indexing hook 一個 method(~10 行)
  - 預期 cascade `new_in_any_chain` 62% → 75%+(末端 prop 拿到 mass 進 active region 後 beam search 能找到)
- 工程量:0.5 天
- 預期 EM 收益:**+3-6pt**(31→34-37,主要救 multi-hop)

**P2(中優先,工程量低):`prop_mass` score 函式混合**
- 目前 `prop_mass = mean(entity_ppr)`
- 改 `prop_mass = α × cosine(q_emb, p.emb) + (1-α) × normalized_ppr_mass`
- α = 0.5 起,sweep {0.3, 0.5, 0.7}
- 動機:cosine(W1 proxy)55% pool co-occurrence;真 PPR 也 55%;**兩者答的可能不一樣**,混合可能拿到 union 益處
- 工程量:0.3 天(改 `_v2_phase2_pipeline` 一個 block + sweep config)
- 預期 EM 收益:**+1-3pt**(31→32-34)

**P3(高 yield 但高成本):重抽 multi-entity proposition**
- 改 W1.1 PropRAG-prompt 抽 multi-fact propositions(prop 含 3+ entities)
- 例如 "Charles Darwin married Amala Paul who is a citizen of Belgium"(4 entities)
- 自然會有 (Darwin, Belgium) hyperedge 直連
- 工程量:1-2 天(改 prompt + 重 build proposition_index ~1h + 重 verify mini-eval)
- 預期 EM 收益:不確定(+3-8pt),但有 noise 風險(multi-entity prop 不再 atomic,可能 verdict 噪音上升)
- 建議:**先做 P1**,如果 P1 充足就不需 P3

### 為什麼 W2 Step 1 是首要瓶頸

| Phase 攻擊點 | 預期 EM 收益 | 工程量 |
|---|---|---|
| W2 Step 1 P1 (chunk-clique) | **+3-6pt** | 0.5 天 |
| Filter rescue 收緊 | +2-4pt | 0.3 天 |
| W3 措辭重設計 | +0-3pt | 0.5 天 |
| Phase 2.a beam=16/L=4 sweep | +1-4pt | 0.5 天(配合 P1)|
| Multi-entity prop 重抽 (P3) | +3-8pt(不確定)| 1-2 天 |

P1 + Filter rescue 收緊兩個一起做(都 indexing/filter 階段)可能拿到 +5-10pt total。

---

## 6. 其他 Open items(已 instrument 但未解決)

| 類別 | 項目 | 預期影響 |
|---|---|---|
| **W3 措辭歧義** | "updates earlier: X" 讓 LLM 誤解 X 為新版本 | 改為「The CURRENT fact is X. (SUPERSEDES: 'Y')」+ inject 時機 |
| **Phase 2.c filter rescue 過寬** | passage 含任一 chain_current 就保留 → 44% chain_old 漏網 | 收緊 rescue → filter rate 56%→70%+ |
| **Phase 2.a beam/L sweep** | 目前 beam=8/L=3,4-hop 末段抓不到 | sweep beam={16,32} L={3,4} |
| **DPR fallback (2% queries)** | `len(top_k_facts)==0` 時 vanilla 走;Phase 2 no-op | 邊界 case,影響 ≤ 2pt |

---

## 6.5 PropRAG vs Ours — Component-level Comparison(必須比較的同類方法)

PropRAG(EMNLP 2025)跟我們**借用相同的 building blocks**(proposition + beam search on prop graph + hyperedge),但解的是**不同問題**。詳細對照:

### Component-level view

| Component | PropRAG | Ours v2.0.2 |
|---|---|---|
| Prop 抽取 | 自定 prompt,可能 multi-entity | 用 PropRAG prompt,但 FC dataset 是 1-句-1-fact → atomic(2 entities)|
| KG 結構 | entity + passage nodes + hyperedge(entity-entity from prop pairs)| 同 PropRAG;**option B (PropRAG-style)** |
| Active region 找候選 | 全域 PPR(用 fact embedding 抓 seed)| Active region top-50 by prop_mass(mean entity_ppr)|
| Chain enumeration | Beam search on prop graph;**path-text re-encode** vs query(每步)| Beam search on prop graph;score = avg prop emb cosine + coherence + ppr_coverage(沒 path-text re-encode) |
| Final ranking | 局部 PPR(用 chain entity 重 seed)→ top-K passages | (我們沒這步)→ top-K passages via vanilla PPR |
| ★ Supersession resolution | **❌ 不解這問題** | ★ Phase 2.b:**chain-restricted LLM identify + 機械方向 verdict** |
| ★ Verdict-driven passage filter | ❌ | ★ Phase 2.c:**filter top-20 含 chain_old 的 passage** |
| Final return unit | passage(對話場景相容)| passage(對話場景相容)|

### Cost 對照(誠實版本,**不是我們 cost-efficient**)

| 層面 | PropRAG | Ours v2.0.2 |
|---|---|---|
| LLM API call / query | **0** | ~5–7 calls(verdict 階段) |
| Local embedding re-encoding | ~24/query(beam search 內)| 0(用既有 prop embedding)|
| Local PPR runs | 2(全域 + 局部)| 1 |
| Wall-clock latency | ~1.3s/query(全 local)| ~5–14s/query(主要 LLM API)|
| API $ cost (100Q) | **$0** | $0.05–0.7 |
| 對 no-API-budget 環境 | ✓ 完全可重現 | ✗ 需要 API |

**Key takeaway**:**PropRAG 不是「過貴的方法」**。它把 cost 放在 local GPU,我們放在 LLM API。Reproducibility 角度看 PropRAG **反而更友好**。

### Paper framing 校正

→ 我們**不該 claim "cost-efficient"**(那個 framing 對外 over-sell)。

→ 應該 claim **"problem-specific contribution"**:
- PropRAG 解 multi-hop **retrieval accuracy**(Wikipedia static QA)
- 我們解 multi-hop **with knowledge update / supersession**(動態對話)
- 兩者用類似 building blocks(prop + beam search + hyperedge),但**我們在 retrieval 之上加 supersession resolution 兩個 component(verdict + filter)**
- PropRAG path scoring 我們**可借可不借** — 但借了不會讓我們的核心 contribution 變強(因為核心 contribution 在 verdict + filter,不在 retrieval accuracy)

### PropRAG 作為 baseline 比較的角色

| 角色 | 為什麼有意義 |
|---|---|
| **必須比的 prior method**(W4 priority)| PropRAG 是最相關的 prior work(同用 prop + beam search);conversational memory benchmark 上沒人跑過,我們會是第一個 |
| **可能是 cost-EM Pareto 上的 different point** | PropRAG(local 1.3s,no API)EM 假設 X;我們(API-based,~10s)EM 31。如果 X ≈ 25–30,我們的 +EM 不夠突出;如果 X ≈ 35+,**PropRAG 在 retrieval 已比我們強,我們的 contribution 只在 supersession 部分** |
| **設計靈感來源**(已 cite)| §B.8.1 已 frame 為 inspiration |

### 我們是否該借 PropRAG path-text scoring 進 chain enumeration?

**降級為「視 W4 對照 baseline 結果再決定」**:
- 如果 PropRAG baseline 對 FC-MH 跑出來 < 25%(retrieval 也不夠強),那借 path scoring 也救不到我們,**不該借**
- 如果 PropRAG > 30%(retrieval 強過我們),那我們需要追上 retrieval 部分,**可以借**(但要明確 cite PropRAG)
- 在不知道 PropRAG baseline 結果前,**不該預先押注「移植 path scoring」**

---

## 6.6 跟 Mem0 / Zep 對照 — 能比較嗎 + 目前位置

### 對照表(FC-MH 6k,Gemini 3.1 Flash-Lite,FC seq-rule wrapper)

| System | FC-SH | FC-MH | 衝突處理時機 | 來源 |
|---|---|---|---|---|
| HippoRAG-v2 vanilla(無衝突機制)| 77% | **22%** | — | motivation_narrative |
| Zep(annotation at inference)| 89% | **28%** | inference-time | motivation_narrative |
| **我們 v2.0.2 Phase 2** | (~75)| **31%** | query-time verdict + filter | 本次 ablation B |
| Mem0 customized(filter at write)| 85% | **44%** | write-time filter | motivation_narrative |

### 能比較嗎 — 可以,但有 caveat

**可比的理由**:
- 同 benchmark(FC-MH 6k)、同 LLM(Gemini 3.1 Flash-Lite)、同 FC seq-rule wrapper(`utils/templates.py` 對所有 `rag` agent 套同一個)
- motivation_narrative §1 已驗證三系統 query template / system prompt / max_tokens / temperature 對齊

**Caveat — baseline alignment**:
- 我們重跑的 ablation A vanilla = **17%**,但 motivation 紀錄 vanilla HippoRAG-v2 = **22%**(5pt gap)
- 已驗證:input_len 兩邊一致(~5583 tokens)→ 不是 top-K 差異
- 可能來源:LLM 版本/temperature 微差、或不同時間跑的 sampling variance
- → **跨系統絕對數字對照前,應先 re-run vanilla 對齊到 22%**(或解釋 gap)

### 目前位置 — 誠實評估

```
vanilla 22% < Zep 28% < 我們 Phase 2 31% < Mem0 44%
                              ↑                 ↑
                         比 Zep +3pt        比 Mem0 −13pt
```

- ✅ **比 vanilla(+9pt vs motivation 基線)+ Zep(+3pt)好**
- ❌ **還沒贏 Mem0(差 13pt)**

### 為什麼 Mem0 在 FC-MH 比我們強 — 待釐清

Mem0 是 **write-time filter**(寫入記憶時就 LLM 判斷要不要存/更新),我們是 **query-time verdict**。Mem0 44% 可能優勢來源:
- write-time 處理時,Mem0 對每個新 fact 主動 update/delete 舊版 → 記憶庫內已「乾淨」
- 我們 query-time 才判斷,受限於 chain enumeration recall(67%)+ filter rescue
- 但 Mem0 write-time 不知 query → 對 multi-hop 應該也有侷限,44% 仍遠低於 SH 85%

→ **Paper 對照需要進一步分析 Mem0 為何 44%**(是 retrieval 強?還是 write-time filter 對 multi-hop 也有效?)。這是 W4 baseline 對照工作。

### Paper framing implication

- 目前**不能 claim SOTA**(Mem0 44% > 我們 31%)
- 可 claim:**在 HippoRAG-v2 base 上,query-time chain-restricted verdict + filter 把 multi-hop 衝突 EM 從 22% 拉到 31%**(+9pt vs motivation vanilla)
- P1 + P2 改進目標 38-42 → 若達成則**接近 Mem0**,可 claim competitive
- 真正的 paper contribution 是**機制 novelty**(chain-restricted verdict 的 LLM↔code 分工),不是純 EM 數字贏 Mem0

---

## 7. 對 paper framing 的影響

**Pre-100Q 假設**:
- Phase 2.b chain-restricted verdict + Phase 3 enriched context = 主 contribution

**Post-100Q 實測**:
- **Phase 2.b verdict + Phase 2.c filter passages = 主 contribution**(+14pt)
- **Phase 3 enriched context 在當前設計下 = +0pt**(或 -2pt 若 filter 關)

**Paper 重新 frame**(綜合 §6.5 PropRAG 對照):

- 核心 contribution = **chain-restricted supersession verdict(LLM 語意 + code 時序分工)+ verdict-driven passage filter**
- ❌ **不該 claim "cost-efficient"** — PropRAG 用 local embedding(無 API)反而對 reproducibility 友善
- ✓ 改 claim **"problem-specific solution"**:解 multi-hop **with supersession**(PropRAG 解 multi-hop accuracy 但不解 supersession)
- 對外 framing 維持 "Phase 1 (proposition) + Phase 2 (verdict + filter) + Phase 3 (enriched, future work)" 結構,但 Phase 3 必須重設計或標 future work
- 跟 PropRAG / Mem0 / Zep 對照:
  - **PropRAG**:同類 building blocks(prop + beam),解 different problem(retrieval accuracy);我們可借其 path-text scoring(W4 視 baseline 結果決定)
  - **Mem0 / Zep**:對話記憶社群 baseline,跟我們 retrieve unit 一致(passage),直接 EM 對照
  - 三者組合給 paper 的 baseline matrix 完整

---

## 7.5 Confirmed Next Priorities — Phase 2 Filter Redesign(主)+ Phase 3 Per-hop Retrieval(次)

### P-main: **Phase 2 Filter — `drop_all_old + inject_confirmed_new`**

**問題**:目前 rescue 規則「passage 含任何 chain_current 就保留」過寬。`chain_current` 不一定 query 相關 → 24 個 questionable rescue 保留 noise(A1 量化)。

**新 filter logic**:

```
1. Drop all passages containing chain_old (NO rescue)
   chain_old_pids = {pid | verdict.status='superseded', confidence≥medium}

2. Identify confirmed chain_new from verdict results:
   chain_new_pids = {v.superseder_id | v.status='superseded'}

3. Inject chain_new prop text into retrieval_context:
   for new_pid in chain_new_pids:
       prompt_user += f"  - {propositions[new_pid].text}\n"

4. Result: retrieved_context = clean passages (no chain_old) + chain_new prop text injection
   → 無 "updates earlier" 措辭歧義(純 prop text)
```

**預期收益**:
- 多 drop 24 個 chain_old chunks(原 rescue noise)→ S6 51% → ~65%
- 16% B+C case 透過 inject 保留 chain_new → 不誤殺答案
- 同時 W3 措辭歧義問題消失(inject 是純 text,沒「方向 hint」)
- **EM 預期 31 → 34-37(+3-6pt)**
- 工程量:0.3 天(改 `_v2_phase2_pipeline` filter 段 + `qa()` prompt assembly 加 inject)

### P-next:**Phase 3 處置 — Skip + 留 Per-hop Retrieval 為 W4**

#### 為什麼 skip Phase 3 是正確選擇(從前面理解串起來)

```
Phase 3 原設計:Reasoning Hints + Recent Updates
    ↓
Reasoning Hints 想做的事 = 提供 cleaned reasoning path 給 LLM
    ↓
但 chain[0] 33% 是 query-irrelevant noise(4-hop 50% noise)
    ↓
β cleaning 可能展示 other_old → other_new 的替換,跟 query 無關
    ↓
P-main filter inject 機制本身就直接 inject「verdict.superseder_id 集合」對應 chain_new prop text
    ↓
P-main inject 不依賴 chain[0] composition → 避開 noise → 更精準版「β」
    ↓
W3 變 redundant
```

#### Phase 3 long-term future work(W4 候選,等 P-main 跑完後決定)

| 候選 | 描述 | 何時做 |
|---|---|---|
| **Per-hop Subset Retrieval** | LLM 拆 query 成 sub-questions / 用 chain enumeration 拆 hop → 各別 retrieve top-2 → union | 等 P-main 後若 EM 仍未達 hard gate 40% 才考慮 |
| **W3 措辭 redesign** | 改 `updates earlier` 措辭 | low priority,因 P-main 已涵蓋 |
| **PropRAG path-text scoring 借鑒** | 改 chain enumeration score 為 path-text re-encode cosine | W4 後段,跟 PropRAG baseline 對照同時做 |

### 為什麼這個順序

| | P-main filter redesign | Phase 3 處置 |
|---|---|---|
| 對 +EM 確定性 | 高(A1/A6 量化 24+29 hops 受益)| skip → 0 確定;留 future work |
| 工程量 | 0.3 天 | 0 天(skip),0.5-1 天(若做 per-hop)|
| 風險 | 低(只改 filter logic)| n/a |
| 對齊 motivation narrative | ✓ 沒動 prompt | ✓ 沒動 prompt |
| Paper 簡潔度 | 高(filter 機制成 core)| skip 更乾淨 |

→ **動工 P-main filter redesign;Phase 3 完全 skip,paper frame 為 future work**。

---

## 8. 優先嘗試(預期收益 + 工程量 + cost 影響)

> Cost 角度看:**local 改動**(filter logic、score 函式)是純贏;**LLM call 增加**(verdict 精度)要 trade-off;**embedding re-encoding 增加**(PropRAG path scoring)cost 中等但屬於 "borrowed method"。

| 優先 | 嘗試 | 預期 EM | 工程量 | Cost 影響 |
|---|---|---|---|---|
| **P1** | **Filter rescue 收緊**(chain_current 數 > chain_old 才保留)| **+2-4pt** | 0.3 天 | **無**(純 logic)|
| **P2** | `prop_mass` cosine + PPR 混合(W2 Step 1 P2)| +1-3pt | 0.3 天 | 無 |
| **P3** | Phase 2.a beam=16 / L=4 sweep | +1-4pt | 0.5 天 | local +0.5s/query |
| **P4** | W3 措辭重設計("CURRENT fact / SUPERSEDES Y")+ inject 時機 | +0-3pt | 0.5 天 | 無 |
| **P5** | Chunk-level entities union clique(W2 Step 1 P1)| +0-2pt(FC dataset 同 chunk facts 不一定相關)| 0.5 天 | indexing time +少量 |
| **P6** | Verdict 精度提升(LLM prompt 微調 / self-consistency)| +1-3pt | 0.5 天 | **LLM call ×2 ↑**(self-consistency)|
| **W4-1** | **PropRAG full base 對照**(borrowed method baseline)| 不確定(可能 25-40)| 1-2 天 | 換 method,不增量 |
| **W4-2** | **PropRAG path-text scoring 移植進 enumerate_chains**(條件:W4-1 顯示 PropRAG 強過我們才做)| +2-5pt | 1 天 | embedding +24/query |

**建議組合**(一次跑完):**P1 + P2 + P3** 一起做(都 local 改動,無 cost 增加,共用一輪 100Q 驗證),預期 EM 31 → **35-38**。

**W4-1 PropRAG baseline 必跑**:不論結果,paper 都需要這個對照。如果 PropRAG > 30% 顯示「retrieval mechanism 強過我們」,則我們的 +EM 主要來自 verdict + filter(reinforce 我們的 contribution claim)。

---

## 9. 給 chat 的核心問題

1. **Paper framing 校正**:我們不該 claim "cost-efficient"(PropRAG 用 local embedding 反而對 reproducibility 更友善)。改 claim **"problem-specific contribution for multi-hop with supersession"** 是否合理?
2. **PropRAG baseline 必跑嗎?**(W4-1)— 第一個 conversational memory benchmark 上跑 PropRAG 的工作,結果都有 paper value:
   - 若 PropRAG ≈ 25–30%:我們的 +EM 部分來自 retrieval、部分來自 verdict+filter,要分解
   - 若 PropRAG > 30%:retrieval 已強,我們的 contribution 純粹在 verdict+filter
   - 若 PropRAG < 25%:retrieval 弱(可能因 FC dataset atomic prop 對 PropRAG 也失效),我們的 verdict+filter 對應的 issue 更獨立
3. **W3 enriched context 怎麼處置?**
   - (a) 完全捨去,frame 為 "tried but didn't help"
   - (b) 留 structure 標 future work,等 W4 措辭 tune 再回來
   - (c) 重設計措辭 + 條件式 inject(只在 filter 失效時)
4. **Priority 是否同意?**(P1+P2+P3 local 組合 → W4-1 PropRAG baseline → 視結果決定 W4-2)

---

**Generated 2026-05-17 from spec §B.14 + 4-ablation 100Q run + cascade analysis**
