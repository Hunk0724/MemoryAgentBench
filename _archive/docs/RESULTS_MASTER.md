# 📊 Master Results Dashboard

> **單一可信賴來源** — 所有 FC pilot 最終結果。
> **Updated**: 2026-05-30
> **規則**:任何新結果跑出來 → 立刻更新此檔。歷史過程 → [docs/experiments/pilots/2026-05-30_pre_plan_a_iteration_history.md](experiments/pilots/2026-05-30_pre_plan_a_iteration_history.md)。

---

## 🔒 Plan A 鎖定設定(paper-canonical)

| 項目 | 值 |
|---|---|
| Backbone LLM | `gemini-3.1-flash-lite`(Vertex ADC GA) |
| Embedder | `text-embedding-004`(Vertex ADC) |
| Chunk size | 512(mem0/mem0g 統一;LCA dataset-default 4096 但無 ingestion 不影響) |
| Top-level temperature | **0** |
| Mem0 internal LLM temperature | **0** |
| Mem0 max_tokens | 16384 |
| L1 prompt fix | applied(mem0/mem0g,移除 2 個 rejection few-shots)|
| 9 monkey-patches | applied(mem0/mem0g)— 見 [agent.py:280-301](../agent.py#L280) |
| HF cache | `/home/yhchiang/MemoryAgentBench/.cache/huggingface` |
| Trials per cell | 1(deterministic,no variance)|

→ Paper appendix disclose:「Using temp=0 for deterministic EM evaluation; benchmark default 0.7 produces 23pp variance on FC-MH 6k across trials, motivating deterministic eval.」

---

## 🟢 Verified results — Plan A

從 result file 的 `agent_config` 讀回 ground truth。

| Method | Task | Ctx | EM | Latency | Result file |
|---|---|---:|---:|---:|---|
| LCA | SH | 6k | **96.0%** | ~3 min | `outputs/gemini-3.1-flash-lite-temp0/.../sh_6k...json` |
| LCA | MH | 6k | **16.0%** | 237s | 同上,mh_6k |
| LCA | SH | 32k | **91.0%** | 196s | 同上,sh_32k |
| LCA | MH | 32k | **19.0%** | 188s | 同上,mh_32k |
| Mem0 | SH | 6k | **92.0%** | 736s | `outputs/gemini-3.1-flash-lite-mem0-chunk512-temp0/.../sh_6k...json` |
| Mem0 | MH | 6k | **52.0%** | 652s | 同上,mh_6k |
| Mem0 | SH | 32k | **90.0%** | 3193s | 同上,sh_32k |
| Mem0 | MH | 32k | **39.0%** | 3174s | 同上,mh_32k |
| Mem0g-prompt-aware | SH | 6k | **79.0%** | 1657s | `outputs/gemini-3.1-flash-lite-mem0g-promptaware-chunk512-temp0/.../sh_6k...json` |
| Mem0g-prompt-aware | MH | 6k | **🎯 66.0%** | 1871s | 同上,mh_6k |
| Mem0g-prompt-aware | SH | 32k | **89.0%** | 7841s | 同上,sh_32k |
| Mem0g-prompt-aware | MH | 32k | **40.0%** | 7714s | 同上,mh_32k |
| LCA | SH | 64k | **90.0%** | 189s | `outputs/gemini-3.1-flash-lite-temp0/.../sh_64k...max_samples1_results.json` |
| LCA | MH | 64k | **12.0%** | 242s | 同上,mh_64k |
| Mem0 | SH | 64k | **88.0%** | ~104 min | `outputs/.../sh_64k...max_samples1_k100_chunk512_results.json` |

**15 個 verified cells** all under Plan A 鎖定條件(Mem0 MH 64k 跑中)。

### 跨 ctx 主表

| Method × Task | 6k | 32k | 64k |
|---|---:|---:|---:|
| LCA × SH | 96% | 91% | 90% |
| LCA × MH | 16% | 19% | 12% |
| Mem0 × SH | 92% | 90% | 88% |
| Mem0 × MH | 52% | 39% | 跑中 |
| Mem0g-pa × SH | 79% | 89% | — |
| **Mem0g-pa × MH** | **66%** ⭐ | **40%** | — |

(64k 只跑 LCA + Mem0;Mem0g-pa 64k/262k 因 ingestion 太慢不跑)

---

## 🟡 Pending — 64k(LCA + Mem0 only)

| Method | Task | Ctx | Status |
|---|---|---:|---|
| LCA | SH | 64k | 🟢 跑中(b1n9fdu52) |
| LCA | MH | 64k | ⏳ |
| Mem0 | SH | 64k | ⏳ |
| Mem0 | MH | 64k | ⏳ |

**Mem0g-pa 64k/262k 不跑**(每 cell ~4-17 hr,佔用 method dev 時間;用 6k+32k mechanism story 即可)。
**262k LCA-only**(若需要,~10 min × 2)。

---

## 🔥 Paper 三大 finding

### F1. SH 收斂 + Mem0g-pa SH 補回 13pp
- 6k SH:Mem0g-pa **-13pp** vs Mem0(79 vs 92)— graph 是 SH 噪音
- 32k SH:Mem0g-pa **-1pp** vs Mem0(89 vs 90)— 長 context 三方 ceiling,graph 噪音稀釋

### F2. MH 6k 黃金 cell — graph **+14pp** 打贏 vector ⭐
- Mem0g-pa MH 6k = **66%** vs Mem0 = 52%
- mechanism:detection recall +14pp(0.76→0.90)+ retrieval cleanliness P(R\|D=1) +10pp(71→81)

### F3. MH 32k graph 優勢消失 — 兩者同 ~40%
- Mem0g-pa MH 32k = 40% ≈ Mem0 = 39%
- mechanism cancellation:graph 傷害 R(P(R\|D=1) -4pp)但改善 LLM inference(P(A\|R=1) +6pp)
- 共同 fail mode = D✓R✗A✗ 45-47%(write-time detect 對但 retrieval 漏)
- mem0 L2 precision 32k 崩盤(0.97 → 0.51),UPDATE-content 1.00 → 0.63

---

## 📈 Mechanism analysis(Plan A 6k+32k,8 cells)

完整 analysis 檔案:`analysis/results/plan_a/{mem0,mem0g_pa}_{sh,mh}_{6k,32k}_{align,detect,3way}.json`

### Detection-action(operation-level precision/recall)

| Method × Task × ctx | EM | Precision | Recall | F1 | UPDATE-content | TP | FN |
|---|---:|---:|---:|---:|---:|---:|---:|
| Mem0 SH 6k | 92% | 0.66 | 0.94 | 0.77 | 0.84 | 93 | 6 |
| Mem0g-pa SH 6k | 79% | 0.63 | 0.83 | 0.72 | 0.84 | 74 | 15 |
| **Mem0 MH 6k** | 52% | 0.97 | 0.76 | 0.85 | **1.00** | 112 | 35 |
| **Mem0g-pa MH 6k** ⭐ | **66%** | **0.98** | **0.90** | **0.94** | **1.00** | **142** | **16** |
| Mem0 SH 32k | 90% | 0.42 | 0.99 | 0.59 | 0.49 | 313 | 3 |
| Mem0g-pa SH 32k | 89% | 0.42 | 0.99 | 0.59 | 0.50 | 316 | 4 |
| Mem0 MH 32k | 39% | 0.51 | 0.96 | 0.67 | 0.64 | 393 | 18 |
| Mem0g-pa MH 32k | 40% | 0.52 | 0.93 | 0.67 | 0.63 | 380 | 30 |

### 3-way contingency(MH focus)

| Cell | Mem0 6k | Mem0g-pa 6k | Mem0 32k | Mem0g-pa 32k |
|---|---:|---:|---:|---:|
| clean win D✓R✓A✓ | 51% | **65%** | 24% | 22% |
| inference fail D✓R✓A✗ | 13% | 13% | 15% | 12% |
| retrieval fail D✓R✗A✗ | 25% | 17% | **45%** | **47%** |
| full fail D✗R✗A✗ | 10% | 4% | 0% | 1% |

### 條件機率(D → R → A causal chain)

| | Mem0 MH 6k | Mem0g-pa MH 6k | Mem0 MH 32k | Mem0g-pa MH 32k |
|---|---:|---:|---:|---:|
| P(R \| D=1) | 71% | **81%(+10)** | 39% | 35%(-4)|
| P(A \| R=1) | 80% | 83% | 60% | **66%(+6)** |
| P(A \| R=0) | 3% | 4.5% | 25% | 26% |

→ 6k:graph 改善 R(+10pp)→ EM +14pp
→ 32k:graph 傷害 R(-4pp)+ 改善 inference(+6pp)→ 相消,EM 持平

### Paper §6.4 mechanism evidence DRAFT(可直接貼進 paper)

> At matched conditions (Plan A: temp=0 deterministic, GA backbone
> gemini-3.1-flash-lite, chunk=512, text-embedding-004), Mem0g-prompt-aware
> exhibits a **context-dependent advantage** over Mem0:
>
> **On FC-MH 6k**, Mem0g-pa beats Mem0 by **+14 EM points** (66% vs 52%). The
> 3-way breakdown attributes this to (a) +14pp detection recall (0.76 → 0.90)
> and (b) +10pp retrieval cleanliness P(R|D=1) (71% → 81%). The graph layer
> reduces cross-pair contamination at query time. **The graph is a
> retrieval-side improvement**: P(A|R=1) is comparable (80% vs 83%).
>
> **On FC-MH 32k**, the advantage vanishes (40% vs 39%). The 3-way breakdown
> reveals a **mechanism cancellation**: the graph hurts retrieval cleanliness
> (P(R|D=1) drops 4pp, 39% → 35%) but helps LLM inference when context is clean
> (P(A|R=1) up 6pp, 60% → 66%). The dominant failure mode at 32k is shared by
> both methods: 45-47% of queries land in D✓R✗A✗ — write-time detection fires
> but retrieval still leaks. At 32k, Mem0 L2's precision collapses (0.97 → 0.51)
> and UPDATE-content correctness drops (1.00 → 0.63), indicating that write-time
> detection over-triggers and produces wrong replacements at scale.
>
> **This motivates query-time conflict detection** (our method's contribution):
> by moving conflict identification from per-chunk write-time to per-query
> query-time, we can exploit the actual retrieval candidates to filter
> cross-pair contamination — directly attacking the 45-47% D✓R✗A✗ failure
> mode that bottlenecks both Mem0 and Mem0g-pa at 32k.

→ 也見 [mem0g_reproducibility.md §8](baseline_methods/mem0g_reproducibility.md) — 「two-store divergence」結構性 limitation 作為機制補強。

---

## 📜 Historical reference(不同設定,paper disclose 用)

HippoRAG-v2 vanilla(`preview` backbone + NV-Embed-v2 + temp=0.7,GPU):

| Method | Task | EM | Caveat |
|---|---|---:|---|
| HippoRAG-v2 vanilla SH 6k | preview | **75%** | preview ≠ GA;temp=0.7 |
| HippoRAG-v2 vanilla MH 6k | preview | **29%** | 同上 |
| HippoRAG-v2 vanilla MH 32k | preview | 6%(n=10)| 樣本太少 |
| HippoRAG-v2 + Phase 2 MH 6k | preview | 31% | from [method_v2.0.2_status_brief.md](method_v2.0.2_status_brief.md) |

路徑:`outputs/hippo_rag_v2_nv_preview_REFERENCE/`

**為什麼不重跑 GA + temp=0**:當前 conda env torch 是 CPU-only,NV-Embed-v2 需 GPU。安裝 GPU torch 風險動到依賴。本研究 focus mem0 系列,HippoRAG-v2 用 historical reference + paper appendix disclose 即可。

---

## 📂 Path map

```
outputs/
├── gemini-3.1-flash-lite-temp0/                              ← LCA Plan A
├── gemini-3.1-flash-lite-mem0-chunk512-temp0/                ← Mem0 Plan A
├── gemini-3.1-flash-lite-mem0g-promptaware-chunk512-temp0/   ← Mem0g-pa Plan A
├── hippo_rag_v2_nv_preview_REFERENCE/                        ← HippoRAG-v2 historical
└── _deprecated/                                              ← 移除的舊 runs

outputs/rag_retrieved/<agent_name>/k_<K>/<sub>/chunksize_<C>/
├── ingestion_context_0.jsonl                                 ← mem0 ADD/UPDATE/DELETE events
├── query_<qid>_context_0.json                                ← per-query: system_prompt / retrieved / response
└── mem0g_label_audit.jsonl                                   ← mem0g backtick wrap log

analysis/results/plan_a/<method>_<task>_<ctx>_{align,detect,3way}.json   ← Plan A 機制分析
```

---

## 🔍 哪裡查什麼(quick lookup)

| 想知道 | 看哪 |
|---|---|
| 「現在 X 方法 × Y 任務 × Z ctx EM 是多少」 | 此檔頂部 verified table |
| 「mem0 / mem0g pipeline 細節 / two-store divergence」 | [baseline_methods/mem0g_reproducibility.md](baseline_methods/mem0g_reproducibility.md) |
| 「mem0 設定為什麼這樣鎖」 | [baseline_methods/mem0_setup_deltas_vs_paper.md](baseline_methods/mem0_setup_deltas_vs_paper.md) |
| 「為什麼 mem0g-as-is 結果作廢」(F1 finding 證據鏈)| [baseline_methods/CRITICAL_FINDINGS_2026-05-29_evening.md](baseline_methods/CRITICAL_FINDINGS_2026-05-29_evening.md) |
| 「FC metric spec(M1 / M-detection / M-core)」 | [sync_with_claude_chat/FC_metrics_spec.md](sync_with_claude_chat/FC_metrics_spec.md) |
| 「method v2.0.2 設計(HippoRAG-v2 + PropRAG + conflict)」 | [method_design_v2.0.2_spec.md](method_design_v2.0.2_spec.md) + [method_v2.0.2_status_brief.md](method_v2.0.2_status_brief.md)(brief 更新)|
| 「Plan A 之前的迭代歷史 / Pre-Plan-A cells / temp 決策過程」 | [experiments/pilots/2026-05-30_pre_plan_a_iteration_history.md](experiments/pilots/2026-05-30_pre_plan_a_iteration_history.md) |

---

## 🛠 維護規則

1. **任何新 cell 跑完** → 立刻更新此檔的 verified table + path 那行
2. **新發現 finding** → 寫 dedicated md(`baseline_methods/` 或 `experiments/pilots/`)+ 此檔 quick lookup 加一行
3. **舊結果作廢** → mv 到 `outputs/_deprecated/`,從 verified table 移出
4. **中間過程 / 失敗 log / iteration** → 不寫進此檔;寫 `experiments/pilots/YYYY-MM-DD_*.md`
5. **此檔長度上限**:~200 行。超過就 refactor、把過時內容搬到 history doc。

---

**End of RESULTS_MASTER.md(2026-05-30)**
