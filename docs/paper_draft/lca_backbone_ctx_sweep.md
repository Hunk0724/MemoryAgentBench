# LCA(Long-Context Agent)backbone × FC-MH ctx sweep

> 日期:2026-05-29
> 目的:把 LCA(trivial baseline)在 paper main result table 的數字 lock 下來,作為 paper §6.3 主表的 baseline,並支持 angle C(ctx scaling)的 narrative。

---

## 0. Why this matters

LCA(把整段對話歷史塞進 LLM 的 prompt)是 **memory paper 文獻 convention 中的 trivial baseline** — 看「不做 memory abstraction、純靠 LLM long context 能力」能達到多少。所有 memory method 都需要打贏 LCA 才算「memory 有用」。

對應 FC_metrics_spec.md §6.3 主表 LCA row,以及 §10.0 framing:
> Expected pattern: Ours likely LOSE on 6k (small ctx Long-Context 直接讀夠用), MAY WIN at 32k+ (Long-Context 失靈,memory abstraction 顯出價值)。

→ LCA cross-ctx 數字決定「memory method 在哪個 ctx 開始有意義」的 turning point。

---

## 1. Backbone 選擇:`gemini-3.1-flash-lite` (GA)

詳見 [[../experiments/pilots/2026-05-29_LCA_model_selection.md]]。

簡述:
- LCA × FC-MH 6k 5 個 Gemini 對比,**`gemini-3.1-flash-lite` (GA) 跟 `gemini-3.1-flash-lite-preview` aggregate metrics 完全一致**(16.0% EM)
- 其他 SOTA(2.5-flash-lite / 2.5-flash / 3.5-flash)都顯著差(1-4%)
- GA 是 preview 的 production 版本,可作長期 stable backbone(preview 2026-07-09 sunset)

**Backbone 決定**:後續所有 LCA + mem0/mem0g 主結果都用 `gemini-3.1-flash-lite` (GA)。

---

## 2. LCA × FC-MH cross-ctx 主表

| ctx | EM | F1 | rougeL | sEM | avg_input | avg_output | wall (s) | n |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 6k   | **16.0%** | 17.2% | 17.2% | 16.0% |   7,429 | 2.63 | 112 | 100 |
| 32k  | **16.0%** | 17.1% | 17.1% | 16.0% |  39,286 | 2.61 | 282 | 100 |
| 64k  | **12.0%** | 13.4% | 13.8% | 12.0% |  79,142 | 2.11 | 331 | 100 |
| 262k |  **4.0%** |  4.7% |  4.7% |  4.0% | 330,770 | 2.14 | 435 | 100 |

**Backbone**:`gemini-3.1-flash-lite` (GA), Vertex AI, temperature=0.7, max_output=10。100 題 FC-MH × 4 ctx = 400 queries 跑完總計 ~19 分鐘(2026-05-29)。

> avg_input 大於 ctx length 是因為加上 LCA prompt template(系統指令 + question wrap)。

---

## 2.B Mem0 × FC-MH(2026-05-29 加入)

| ctx | EM | F1 | rougeL | sEM | wall (s) | n |
|---|---:|---:|---:|---:|---:|---:|
| 6k | **50.0%** | 50.0% | 50.0% | 50.0% | TBD | 100 |
| 32k | TBD | — | — | — | — | — |
| 64k | TBD | — | — | — | — | — |
| 262k | TBD | — | — | — | — | — |

**Setup**:`gemini-3.1-flash-lite` (GA, **同 LCA backbone**), `agent_chunk_size=512`, mem0 internal `temperature=0.1`, `max_tokens=8192`, embedder = Vertex `text-embedding-004` (768-dim, ADC), L1 modified fact extraction prompt.

⚠️ **三個 setup deltas vs mem0 paper convention**(完整審計見 [[../baseline_methods/mem0_setup_deltas_vs_paper.md]]):
1. **L1 prompt fix**:移除 2 個 rejection few-shots(95/3173 chars = 3.0%)— 否則 Gemini OOB EM=0%
2. **chunk_size 512 instead of 4096**:對齊 HippoRAG-v2 FC convention(MABench paper allow per-method);Gemini × 4096 → meta-summarize 失效
3. **max_tokens 8192 instead of default 2048**:Update Memory call 撞 MAX_TOKENS 預設導致 empty response

文獻先例 + ablation 規劃見 [[../baseline_methods/mem0_setup_deltas_vs_paper.md §1-3]]。

### 2.B.1 6k 結果三方對比

| Method | EM | F1 | rougeL | wall(s) | 相對 LCA |
|---|---:|---:|---:|---:|---:|
| LCA 6k | 16.0% | 17.2% | 17.2% | 112 | (baseline) |
| **Mem0 6k(L1+512+8192)** | **50.0%** | 50.0% | 50.0% | 738 | **+34.0 pp** |
| **Mem0g 6k(同 setup + Neo4j 5)** | **43.0%** | 43.0% | 43.4% | 2048 | **+27.0 pp** |
| Mem0 6k OOB(chunk=4096) | 0.0% | 0.6% | 1.0% | 247 | -16.0 pp(ablation) |

### 2.B.1a 🚨 重要 finding:Mem0g 圖層反而扣 7 pp

**Mem0g 在 FC-MH 6k 上比 Mem0 輸 7 pp**(43% vs 50%)。這個 finding 跟 mem0 v3 上游拋棄圖記憶的決定一致:

> "The graph-augmented mem0g consistently underperforms the vector-only mem0 on FC,
>  empirically validating mem0's v3 design decision to remove the graph memory layer."

**Hop-level diagnostic 顯示圖層在每個維度都更差**:

| Metric | Mem0(向量) | Mem0g(向量+圖) | Δ |
|---|---:|---:|---:|
| **CLEAN_rate**(理想) | **38.8%** | **31.9%** | **−6.9 pp** |
| **LEAK_rate**(主要 fail) | **54.3%** | **58.5%** | **+4.2 pp**(更糟) |
| **MISS_rate**(retrieve 漏) | **10.6%** | **17.0%** | **+6.4 pp**(更糟) |
| RETRIEVED_rate(no_conflict) | 89.4% | 78.8% | −10.6 pp(更糟) |

Mem0g 圖層觸發了 **121 個 hard-delete entities** — 但其中包含**該保留的舊資訊**,導致 MISS rate 從 10.6% 升到 17.0%,RETRIEVED rate 從 89.4% 降到 78.8%。

Error type 的 `entity_confused` 從 22% → 29%(+7 pp),也跟「圖層誤刪 entity」相符。

**Mem0 在 6k FC-MH 上完勝 LCA 34 pp**。這跟「memory abstraction 在 dense conflict 場景下有用」的直覺對齊。

### 2.B.2 M-core hop-level 分析(spec §3)

100 query, 254 hops 總計(188 has_pair / 66 no_conflict):

| State | Count | Rate |
|---|---:|---:|
| **CLEAN**(has_pair, 理想) | 73 | **38.8%** |
| **LEAK**(has_pair, 主要 fail) | 102 | **54.3%** |
| **MISS**(has_pair, retrieve 漏) | 20 | 10.6% |
| **RETRIEVED**(no_conflict, OK) | 59 | 89.4%(/66) |

**主要 fail mode 是 LEAK(54.3%)** — mem0 retrieve 到舊版 fact,沒 hard delete 掉。對應 paper narrative:**這是 memory abstraction 方法的「結構缺陷」(write-time detection imperfect),我們的方法應該針對 LEAK rate 改善**。

### 2.B.3 Error type 分布(top-level)

| Type | Count | 含義 |
|---|---:|---|
| correct | 50% | 答對 |
| entity_confused | 22% | 答錯但 close entity |
| **older_fact** | **20%** | **取到舊版 fact**(LEAK 的直接後果) |
| empty | 7% | LLM 沒答 |
| hallucination | 1% | 完全胡亂答 |

`older_fact` 20% 跟 LEAK rate 54.3% 對應:**並非所有 LEAK 都導致答錯,但 LEAK 是答錯的主因之一**。

> 數字會在 background job 跑完後自動 patch 進這個表。

---

## 3. 結論讀法(數字已出)

### Pattern:LCA 有明顯的「短 ctx 平 → 長 ctx 崩」分段曲線

```
      EM
   16% ●———●         <- 6k, 32k 完全持平 (16% 是這個 model + FC-MH prompt 的 EM ceiling)
              \
   12%         ●     <- 64k 開始降 (~25% relative drop)
                 \
    4%            ●  <- 262k 陡降 (~75% relative drop)
        6k  32k 64k 262k
```

3 個 hypothesis 結論:

| Hypothesis | 結果 | 證據 |
|---|---|---|
| A. monotonic decline | **部分成立** | 6k→32k 平,但 32k+ 確實 monotonically 退化 |
| B. LCA 在 32k 維持 | **成立** | 6k=32k=16.0%(EM 完全相同) |
| C. 262k 陡降 | **強烈成立** | 16% → 4%(-12pp,只剩 1/4) |

### Paper narrative 的核心 finding

> **LCA(`gemini-3.1-flash-lite`)在 FC-MH 上達到 EM ceiling ≈ 16%,並可在 32k token 內維持;但在 64k 開始退化,262k 崩到 4%(只剩 1/4 ceiling)。Turning point 落在 32k-64k 之間。**

這給 memory method 一個明確的 paper narrative anchor:
- **6k / 32k 上要打贏 16%** 才算「memory method 有用」(困難 — LCA ceiling 等同)
- **64k 上打贏 12% 即贏**(容易;LCA 已退化)
- **262k 上打贏 4% 即贏**(很容易;LCA 幾乎崩)

### 為什麼 6k → 32k 完全沒退化?

可能解釋:
1. **FC-MH 6k context (455 facts)已是 model 對這類題的 saturation 點**,加更多 facts 不會幫助也不會嚴重害(只要還在 effective context 內)
2. Gemini 3.1 Flash Lite 在 32k 範圍內 attention 還沒明顯 dilute
3. 「16% EM」可能就是 model 對 FC-MH 衝突解析任務的 capability ceiling — 受限的不是 retrieval(LCA 全 context 可見)而是 reasoning(多跳衝突需要識別 newer fact 並串接)

→ 若 hypothesis 3 成立,意味著 **memory method 即使 retrieve 完美,也很難超過 16% EM** — 除非 memory method 提供更好的 reasoning scaffold(例如 explicit OLD/NEW tagging,對應 metrics spec §3.8.2 Approach 2)。

### 為什麼 64k → 262k 陡降?

- 64k = 4580 facts,262k = 18332 facts
- 衝突對在 18332 個 facts 內被稀釋(noise-to-signal 比變差)
- LCA 沒 retrieval/filter,所有 facts 都進 attention,新舊衝突更容易混淆
- 這是 memory method 的「典型優勢場景」 — 預期 memory method 在 262k 上可以**保持** 10-15% EM

---

## 4. 對 paper § 章節對應

| Paper section | 這份數據怎麼用 |
|---|---|
| §6.3 主表 | LCA row × 4 個 ctx column,作為 trivial baseline 的基準線 |
| §6.4 mechanism | LCA 無 mechanism,不算進此表,但作為 EM ceiling 參考 |
| §7 angle C narrative | 「LCA 在 ctx > X token 時 EM 降到 Y%,memory method 在同樣 ctx 上保持 Z%」直接寫成 figure |
| §3 motivation | 「為什麼要 memory:long-context 在 X token 時崩」用 LCA 6k vs 262k 對比展示 |

---

## 5. 沒在這次 sweep 內的

| Dimension | 為什麼不跑 |
|---|---|
| FC-SH × 4 ctx | 使用者本輪指示「先跑 FC-MH 就好」,SH 之後再說 |
| 其他 4 個 Gemini | LCA 6k 已顯示 3.1-flash-lite 是唯一接近 preview 的;其他 model 跑下去也是同模式 |
| Non-FC tasks(AR / EventQA)| Stage 3 才做(claim-c) |
| 32k/64k/262k FC-SH | 同上 |

---

## ⚠️ Sanity check:沒撞 context window 上限

| ctx | yaml ctx_max | yaml input_lim | 實際 avg input | 與 1M 距離 |
|---|---:|---:|---:|---|
| 6k | 6,000 | 1,000,000 | 7,429 | 還有 99.3% |
| 32k | 32,768 | 1,000,000 | 39,286 | 還有 96.1% |
| 64k | 65,536 | 1,000,000 | 79,142 | 還有 92.1% |
| 262k | 300,000 | 1,000,000 | 330,770 | 還有 67% |

關鍵 verify 點:
- **沒有任何 ctx 撞 `input_length_limit: 1000000`** — 最大的 262k input 才 330k token,離 Gemini 3.1 Flash Lite 名義 1M context window 還很遠
- **input_len 各題 std 4-5 token**(`in_min ≈ in_max ≈ in_avg`),100 題 input 几乎完全相同 — 這是 LCA 預期行為(共享同一個累積 context,只 question 不同)
- **avg input 比 yaml ctx_max 大** — 例如 6k ctx 但實際 7,429 token,差額是 system prompt + question wrap

→ **EM 從 16% 退化到 4% 是 model 在 long context 上的「真實 capability 退化」,不是 truncation / setup 限制造成**。Paper 可以放心 claim「dense conflict 場景下,Gemini 3.1 Flash Lite 即使在它名義能處理的 context 內(330k ≪ 1M),effective context 顯著有限」。

## 6. Reproducibility 紀錄

- **Yaml**:[Long_context_agent_gemini-3.1-flash-lite.yaml](../../configs/agent_conf/Long_Context_Agents/Long_context_agent_gemini-3.1-flash-lite.yaml)(model=`gemini-3.1-flash-lite`)
- **Dataset yaml**:`configs/data_conf/Conflict_Resolution/Factconsolidation_mh_{6k,32k,64k,262k}.yaml`(這次跑前已把 32k/64k/262k 的 `max_test_samples: 1` 改成 `null` — 改動見 [SESSION_2026-05-24_mem0_mem0g_setup.md](../experiments/pilots/SESSION_2026-05-24_mem0_mem0g_setup.md))
- **Vertex AI**:project `fc-mh-494213` location `global`
- **Output JSON**:`outputs/gemini-3.1-flash-lite/Conflict_Resolution/factconsolidation_mh_*_results.json`
- **Run log**:`logs/lca_3.1-flash-lite-ga_mh_*.log`

---

## 7. 待補

- [x] ~~等 32k / 64k / 262k 三個 background job 完成,填入 §2 表格~~ ✅(2026-05-29)
- [x] ~~視結果決定 hypothesis A/B/C 哪個成立~~ ✅(B + C 都成立)
- [ ] 寫對應的 paper §6.3 主表 LCA row + §7 angle C narrative draft
- [ ] FC-SH × 4 ctx 之後補(看 mem0/mem0g 結果再決定)
- [ ] 跑 mem0/mem0g × `gemini-3.1-flash-lite` × FC-MH × 4 ctx,跟 LCA 同表比較
- [ ] 用 [align_mem0_mquake.py](../../analysis/align_mem0_mquake.py) 對 4 個 LCA result 做 hop-level alignment,看 LCA 在 has_pair / no_conflict 上的差異

---

## 8. 相關文件

- 5-model 選 backbone 過程:[[../experiments/pilots/2026-05-29_LCA_model_selection.md]]
- MQuAKE alignment + ctx coverage:[[../ground_truth/mquake_alignment_guide.md]]
- pilot plan:[[../experiments/pilots/mem0_mem0g_pilot_plan.md]]
- Metrics spec(指 Tier hierarchy):[[../sync_with_claude_chat/FC_metrics_spec.md]]
