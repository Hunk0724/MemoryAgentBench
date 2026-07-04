# Rigor Audit — aggregated ↔ per-qid consistency (all method × length)

> **When to re-run**:每次 baseline / method 有新 run 之後,commit 前必跑一次。
> **Command**: `python analysis/rigor_audit.py`
> **Source of truth**:per-qid `response`(內部 consistent with pool);aggregated 只是 batch summary,可能 stale。
> **EM 定義**:MAB 官方 `default_post_process` = max(EM(raw), EM(parse_output(raw))) 用 `drqa_exact_match_score`。
> **Matcher**:pool state 判定用 [`matcher_specification.md`](matcher_specification.md) v4;此 audit 只查 EM/response consistency,不查 matcher。

## 1. 摘要 status 表

| Method | Length | N | AGG EM | Per-qid EM | Mismatch (out ≠ resp) | Empty AGG output | Empty per-qid resp | Status |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| ours (full P3+P5) | 6k | 74 | 68/74 | 68/74 | 0 | 0 | 0 | ✅ OK |
| ours (full P3+P5) | 32k | 65 | 55/65 | 55/65 | 0 | 0 | 0 | ✅ OK |
| ours (full P3+P5) | 64k | 66 | 60/66 | 60/66 | 0 | 0 | 0 | ✅ OK |
| ours (no_p5) | 6k | 74 | 69/74 | 69/74 | 0 | 0 | 0 | ✅ OK |
| ours (no_p5) | 32k | 65 | 57/65 | 57/65 | 0 | 0 | 0 | ✅ OK |
| ours (no_p5) | 64k | 66 | 60/66 | 60/66 | 0 | 0 | 0 | ✅ OK |
| ours (struct) | 6k | 74 | 67/74 | 67/74 | 0 | 0 | 0 | ✅ OK |
| ours (struct) | 32k | 65 | 52/65 | 52/65 | 0 | 0 | 0 | ✅ OK |
| ours (struct) | 64k | 66 | 58/66 | 58/66 | 0 | 0 | 0 | ✅ OK |
| ours (p3_only) | 6k | 74 | 71/74 | 71/74 | 0 | 0 | 0 | ✅ OK |
| ours (p3_only) | 32k | 65 | 58/65 | 58/65 | 0 | 0 | 0 | ✅ OK |
| ours (p3_only) | 64k | 66 | 58/66 | 58/66 | 0 | 0 | 0 | ✅ OK |
| (b) mem0+P1 | 6k | 74 | 34/74 | 34/74 | 0 | 3 | 3 | ✅ OK |
| (b) mem0+P1 | 32k | 65 | 25/65 | 25/65 | 0 | 5 | 5 | ✅ OK |
| (b) mem0+P1 | 64k | 66 | 34/66 | 34/66 | 0 | 2 | 2 | ✅ OK |
| Zep (k=10) | 6k | 74 | 46/74 | 46/74 | 0 | 0 | 0 | ✅ OK |
| Zep (k=10) | 32k | 65 | 33/65 | 33/65 | 0 | 0 | 0 | ✅ OK |
| Zep (k=10) | 64k | 66 | 36/66 | 36/66 | 0 | 0 | 0 | ✅ OK |

## 2. 詳細:mismatch 樣本

## 3. Canonical file registry(以 per-qid 為 source of truth)

| Method × Length | Aggregated file | Per-qid dir |
| :--- | :--- | :--- |
| ours (full P3+P5) × 6k | `outputs/gpt-4o-mini-mem0-chunk512-temp0-openai-unified/Conflict_Resolution/factconsolidation_sh_6k_unknown_in6000_size256_shots0_max_samplesunknown_k100_chunk512_results.json` | `outputs/rag_retrieved/Structure_rag_gpt-4o-mini-mem0_512_openai_unified/k_100/factconsolidation_sh_6k/chunksize_512` |
| ours (full P3+P5) × 32k | `outputs/gpt-4o-mini-mem0-chunk512-temp0-openai-unified/Conflict_Resolution/factconsolidation_sh_32k_unknown_in32768_size256_shots0_max_samplesunknown_k100_chunk512_results.json` | `outputs/rag_retrieved/Structure_rag_gpt-4o-mini-mem0_512_openai_unified/k_100/factconsolidation_sh_32k/chunksize_512` |
| ours (full P3+P5) × 64k | `outputs/gpt-4o-mini-mem0-chunk512-temp0-openai-unified/Conflict_Resolution/factconsolidation_sh_64k_unknown_in65536_size256_shots0_max_samples1_k100_chunk512_results.json` | `outputs/rag_retrieved/Structure_rag_gpt-4o-mini-mem0_512_openai_unified/k_100/factconsolidation_sh_64k/chunksize_512` |
| ours (no_p5) × 6k | `outputs/gpt-4o-mini-mem0-chunk512-temp0-openai-unified_no_p5/Conflict_Resolution/factconsolidation_sh_6k_unknown_in6000_size256_shots0_max_samplesunknown_k100_chunk512_results.json` | `outputs/rag_retrieved/Structure_rag_gpt-4o-mini-mem0_512_openai_unified_no_p5/k_100/factconsolidation_sh_6k/chunksize_512` |
| ours (no_p5) × 32k | `outputs/gpt-4o-mini-mem0-chunk512-temp0-openai-unified_no_p5/Conflict_Resolution/factconsolidation_sh_32k_unknown_in32768_size256_shots0_max_samplesunknown_k100_chunk512_results.json` | `outputs/rag_retrieved/Structure_rag_gpt-4o-mini-mem0_512_openai_unified_no_p5/k_100/factconsolidation_sh_32k/chunksize_512` |
| ours (no_p5) × 64k | `outputs/gpt-4o-mini-mem0-chunk512-temp0-openai-unified_no_p5/Conflict_Resolution/factconsolidation_sh_64k_unknown_in65536_size256_shots0_max_samples1_k100_chunk512_results.json` | `outputs/rag_retrieved/Structure_rag_gpt-4o-mini-mem0_512_openai_unified_no_p5/k_100/factconsolidation_sh_64k/chunksize_512` |
| ours (struct) × 6k | `outputs/gpt-4o-mini-mem0-chunk512-temp0-openai-unified_struct/Conflict_Resolution/factconsolidation_sh_6k_unknown_in6000_size256_shots0_max_samplesunknown_k100_chunk512_results.json` | `outputs/rag_retrieved/Structure_rag_gpt-4o-mini-mem0_512_openai_unified_struct/k_100/factconsolidation_sh_6k/chunksize_512` |
| ours (struct) × 32k | `outputs/gpt-4o-mini-mem0-chunk512-temp0-openai-unified_struct/Conflict_Resolution/factconsolidation_sh_32k_unknown_in32768_size256_shots0_max_samplesunknown_k100_chunk512_results.json` | `outputs/rag_retrieved/Structure_rag_gpt-4o-mini-mem0_512_openai_unified_struct/k_100/factconsolidation_sh_32k/chunksize_512` |
| ours (struct) × 64k | `outputs/gpt-4o-mini-mem0-chunk512-temp0-openai-unified_struct/Conflict_Resolution/factconsolidation_sh_64k_unknown_in65536_size256_shots0_max_samples1_k100_chunk512_results.json` | `outputs/rag_retrieved/Structure_rag_gpt-4o-mini-mem0_512_openai_unified_struct/k_100/factconsolidation_sh_64k/chunksize_512` |
| ours (p3_only) × 6k | `outputs/gpt-4o-mini-mem0-chunk512-temp0-openai-unified_p3_only_no_struct/Conflict_Resolution/factconsolidation_sh_6k_unknown_in6000_size256_shots0_max_samplesunknown_k100_chunk512_results.json` | `outputs/rag_retrieved/Structure_rag_gpt-4o-mini-mem0_512_openai_unified_p3_only_no_struct/k_100/factconsolidation_sh_6k/chunksize_512` |
| ours (p3_only) × 32k | `outputs/gpt-4o-mini-mem0-chunk512-temp0-openai-unified_p3_only_no_struct/Conflict_Resolution/factconsolidation_sh_32k_unknown_in32768_size256_shots0_max_samplesunknown_k100_chunk512_results.json` | `outputs/rag_retrieved/Structure_rag_gpt-4o-mini-mem0_512_openai_unified_p3_only_no_struct/k_100/factconsolidation_sh_32k/chunksize_512` |
| ours (p3_only) × 64k | `outputs/gpt-4o-mini-mem0-chunk512-temp0-openai-unified_p3_only_no_struct/Conflict_Resolution/factconsolidation_sh_64k_unknown_in65536_size256_shots0_max_samples1_k100_chunk512_results.json` | `outputs/rag_retrieved/Structure_rag_gpt-4o-mini-mem0_512_openai_unified_p3_only_no_struct/k_100/factconsolidation_sh_64k/chunksize_512` |
| (b) mem0+P1 × 6k | `outputs/gpt-4o-mini-mem0-chunk512-temp0-openai-unified_dest/Conflict_Resolution/factconsolidation_sh_6k_unknown_in6000_size256_shots0_max_samplesunknown_k100_chunk512_results.json` | `outputs/rag_retrieved/Structure_rag_gpt-4o-mini-mem0_512_openai_unified_dest/k_100/factconsolidation_sh_6k/chunksize_512` |
| (b) mem0+P1 × 32k | `outputs/gpt-4o-mini-mem0-chunk512-temp0-openai-unified_dest/Conflict_Resolution/factconsolidation_sh_32k_unknown_in32768_size256_shots0_max_samplesunknown_k100_chunk512_results.json` | `outputs/rag_retrieved/Structure_rag_gpt-4o-mini-mem0_512_openai_unified_dest/k_100/factconsolidation_sh_32k/chunksize_512` |
| (b) mem0+P1 × 64k | `outputs/gpt-4o-mini-mem0-chunk512-temp0-openai-unified_dest/Conflict_Resolution/factconsolidation_sh_64k_unknown_in65536_size256_shots0_max_samples1_k100_chunk512_results.json` | `outputs/rag_retrieved/Structure_rag_gpt-4o-mini-mem0_512_openai_unified_dest/k_100/factconsolidation_sh_64k/chunksize_512` |
| Zep (k=10) × 6k | `outputs/gpt-4o-mini-zep/Conflict_Resolution/factconsolidation_sh_6k_unknown_in6000_size256_shots0_max_samplesunknown_k10_chunk512_results.json` | `outputs/rag_retrieved/Structure_rag_zep/k_10/factconsolidation_sh_6k/chunksize_512` |
| Zep (k=10) × 32k | `outputs/gpt-4o-mini-zep/Conflict_Resolution/factconsolidation_sh_32k_unknown_in32768_size256_shots0_max_samplesunknown_k10_chunk512_results.json` | `outputs/rag_retrieved/Structure_rag_zep/k_10/factconsolidation_sh_32k/chunksize_512` |
| Zep (k=10) × 64k | `outputs/gpt-4o-mini-zep/Conflict_Resolution/factconsolidation_sh_64k_unknown_in65536_size256_shots0_max_samples1_k10_chunk512_results.json` | `outputs/rag_retrieved/Structure_rag_zep/k_10/factconsolidation_sh_64k/chunksize_512` |

## 4. Interpretation & action recommended per status

- **✅ OK** — aggregated ↔ per-qid consistent;可安全引用 aggregated 的 `exact_match` 欄
- **⚠️ stale-aggregated** — mismatch 存在但 aggregated `output` 非空;通常代表**部分 re-run 覆蓋 per-qid 但沒重生 aggregated**。**應該從 per-qid 重生 aggregated**;此處 crosstab 已 fallback 用 per-qid,結果不受影響
- **🚨 broken-aggregated** — aggregated `output` 大量為 `Answer:` 空 stub;需要:(a) 用 per-qid 重生 aggregated,或 (b) 明確標記此 aggregated 檔為 corrupted 並移到 `_deprecated/`
- **❌ no-aggregated / no-perqid** — canonical 路徑找不到檔;需檢查 method × length 是否真的跑過 / 檔案路徑是否對
