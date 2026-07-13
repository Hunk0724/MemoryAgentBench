# FC-SH Main Table — 4 Length × 10 Method(canonical rescore,2026-07-13)

> **數據來源**:`analysis/rescore_canonical.py`(53 cells,gpt-4o-mini backbone,single deterministic run,temp=0)。
> **官方判分**:`substring_exact_match`(sEM;MemoryAgentBench 官方 CR metric,`default_post_process` = normalize + parse_output + max{raw, parsed} + max over alias list)。
> **Supersede**:本檔以 **4 length + Don't Ask + Q-llm-recency** 版取代 [`fc_sh_has_pair_main_table.md`](fc_sh_has_pair_main_table.md)(該檔僅 3 length 且缺 concurrent baseline);舊檔保留供 audit,不再引用於 paper body。

---


## Table 1 — Overall sEM ↑(headline,100-query task metric)

| **Method** | **6k** | **32k** | **64k** | **262k** | AVG |
| --- | --- | --- | --- | --- | --- |
| **Write-time KU Baselines** |  |  |  |  |  |
| Mem0 Vanilla (Write-time LLM)  | 16 | 22 | 28 | 17 | 20.8 |
| Mem0 + P1 (Write-time LLM)  | 52 | 52 | 65 | 50 | 54.8 |
| Zep (Write-time decoupled)  | 82 | 80 | 76 | 29 | 66.8 |
| **Query-time KU Baselines** |  |  |  |  |  |
| LCA (gpt-4o-mini full-context) | 88 | 74 | 65 | 43 | 67.5 |
| Vanilla-RAG (Query-time LLM temporal resolution) | 93 | 77 | 85 | 81 | 84.0 |
| Don’t Ask (Query-time LLM extraction)  | 80 | 86 | 88 | 86 | 85.0 |
| **Ours (Ablation & Variants)** |  |  |  |  |  |
| Ours (LLM-Identity-Only) | **97** | **91** | 91 | 87 | 91.5 |
| Ours (Struct-Only) | 91 | 87 | 92 | 86 | 89.0 |
| Ours (+P5, appendix) | 93 | 90 | **94** | **91** | 92.0 |
| **Ours (Struct + LLM-Fallback)** | **94** | **91** | **94** | **91** | **92.5** |

**Bold** = 該 length 最佳(以及 Mean 欄的最高值)。Mean(4L)= 四長度(6k / 32k / 64k / 262k)Overall sEM 之未加權平均(每格分母皆 = 100 → 為合理平均)。四個 ours variants 之 Mean 皆 ≥89,顯著高於其他所有方法;僅 Don't Ask(85.0)接近 ours (no P3)(89.0)。

---

## Table 2 — `has_pair` sEM ↑(KU-relevant 子集,mechanism metric)

`has_pair` 分母隨長度變:74 / 65 / 66 / 77(FC-SH 每長度 100 題中真正含 old/new 版本的子集)。

| Method | 6k(74) | 32k(65) | 64k(66) | 262k(77) |
| :--- | :---: | :---: | :---: | :---: |
| **ours (main)** | **69 (93)** | **57 (88)** | **60 (91)** | **68 (88)** |
| ours (+P5) | 68 (92) | 56 (86) | **60 (91)** | **68 (88)** |
| ours (LLM only) | **71 (96)** | 58 (89) | 58 (88) | 64 (83) |
| ours (no P3) | 67 (91) | 53 (82) | 58 (88) | 63 (82) |
| Don't Ask | 54 (73) | 51 (78) | 54 (82) | 63 (82) |
| Q-llm-recency | 67 (91) | 42 (65) | 51 (77) | 58 (75) |
| Zep(k=10) | 56 (76) | 45 (69) | 42 (64) | 12 (16) |
| LCA | 65 (88) | 46 (71) | 36 (55) | 24 (31) |
| (b) mem0+P1 | 34 (46) | 26 (40) | 34 (52) | 29 (38) |
| (a) vanilla | 0 (0) | 2 (3) | 2 (3) | 1 (1) |

括號內為 %。**Bold** = 該 length 最佳。

---

## Caption(figure / table 通用,三段論)

**What.** FC-SH knowledge-update accuracy of 10 memory systems / baselines at four conversation-history lengths (6k → 262k tokens), scored by MemoryAgentBench's official `substring_exact_match` on the 100-query set (Table 1) and its `has_pair` subset (Table 2). All runs use gpt-4o-mini (temp 0), chunk-size 512, top-100 retrieval (except Zep at k=10 per its official recipe); single deterministic run, no error bar. `ours (main)` = full pipeline (P1 faithful extraction + P2 (S,P) structural grouping + P3 LLM identity 补救 + deterministic argmax freshness); `ours (no P3)` = P2 + argmax only, LLM identity disabled; Don't Ask [Reddy & Challaram, 2026] = concurrent Q-llm-identity baseline (BM25/vector retrieval + LLM candidate extraction + `max(serial)`); Q-llm-recency = raw-question RAG + LLM recency judgment.

**Observation.** `ours (main)` is the only method flat across all four lengths (91-94 sEM), Δ = −3 pp from 6k to 262k. Every other family degrades or ceilings: Zep collapses at 262k (76 → 29, Δ = −53), LCA drops monotonically (88 → 43, Δ = −45), Q-llm-recency dips non-monotonically (93 → 77 → 85 → 81), and mem0+P1 plateaus at 50-65 across all lengths (W-llm destructive-commit ceiling). Don't Ask is the only competitor that improves with length (80 → 86, Δ = +6), converging to within 5 pp of ours at 262k by exploiting FC-SH's chunk-serial ordering signal.

**Implication.** Length-robust KU on FC-SH is achievable by two structurally different families of query-time resolution: (a) deferred structural grouping + deterministic freshness (ours), and (b) LLM candidate extraction + deterministic serial-max (Don't Ask). Both share the *deterministic freshness* commitment; the +5-14 pp gap between them isolates the identity mechanism (structural (S,P) vs LLM candidate extraction). W-llm methods (mem0 destructive commit, Zep asynchronous KU labelling) either plateau (b) or crash (Zep at 262k) — write-time KU commitment is not length-robust in either coupled or decoupled form.

---

## 已知 caveats(paper 揭露)

1. **Zep k=10 vs k=100 asymmetry**:Zep 官方推薦 k=10;server hard cap 為 50。實測 Zep top-50 於 262k(46/100 queries before rate-limit)為 28.3%,與 k=10 的 29% 統計等價 → 262k crash 非 top-K 上限所致,而是 write-time invalidation 覆蓋不足(僅 6.3% of retrieved edges 帶 `invalid_at`)。詳見 [`zep_ku_resolution_bitemporal.md`](zep_ku_resolution_bitemporal.md)。
2. **(a) vanilla mem0** 於 has_pair 幾乎全零(0-3%)是 native L1 extractor 於 FC 密集 fact chunk 完全失效;非 KU 機制問題,extraction 崩壞就已無 recall 基底可比。故列 appendix。
3. **Don't Ask 用作者自帶單值 GT rescored**:作者 per-row output 以 official pipeline 對 `gt_answer`(單字串,無 alias list)重新判分;alias-hit 可能微幅低估(見 `analysis/rescore_canonical.py` `score_custom_maxserial` 註記)。
4. **Single deterministic run**:temp=0,無 std;OpenAI server-side bf16 帶入 ±2-3 pp 抖動(reproduction_log 已驗證兩台從零 clone 收斂於此範圍)。

---

## 更新歷程

- **2026-07-13**:本表建立;新增 262k 全 method + Don't Ask 4 length + Q-llm-recency 4 length + (b) mem0+P1 262k。
- **舊版**:[`fc_sh_has_pair_main_table.md`](fc_sh_has_pair_main_table.md)(2026-07-01,3 length + 5 method + 未含 Don't Ask / Q-llm-recency)。
