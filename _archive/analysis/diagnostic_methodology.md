# FC-MH Multi-hop Diagnostic — Methodology

> 對應腳本目錄: `analysis/`
> 結果目錄: `analysis/results/diagnostic/`
> 實驗環境: HippoRAG-v2 × Gemini 3.1 Flash-Lite × chunk_size=512 × 6k context (455 facts)

## 研究問題

`MH Acc 與 chain reasoning 的真正瓶頸`

A1 modified-prompt baseline 顯示 FC-MH = 23.0% (vs FC-SH = 96.0%)。
36+ pp gap 是來自:
- (a) **Conflict mixing**: retrieved context 同時有新舊事實 → LLM 採信舊事實
- (b) **Multi-hop reasoning under noisy context**: chain 在多跳推理過程中累積誤差

本系列七個實驗用 controlled ablations 量化 (a) 與 (b) 的相對貢獻,並驗證 framing。

---

## 實驗總覽

| # | 實驗 | Manipulation | Output | 角色 |
|---|---|---|---|---|
| **0** | Parse 現有 Thought | (無) | 確認 baseline output 已被 split('Answer:') 截掉 | 排除零成本選項 |
| **A1** | Modified-prompt baseline | system prompt 加 `Intermediate answers: [...]` 要求 + one-shot 示範 | a1_modified_baseline_{mh,sh}.json | 重建 fair-compare baseline |
| **A2** | Per-hop diagnosis | 從 A1 抽 per-hop 預測對齊 MQuAKE per-hop GT | a2_per_hop_diagnosis.{json,txt} | 失敗 hop 屬性歸因 |
| **B** | Hop-by-hop ablation | 每 hop 當 standalone FC-SH (full HippoRAG retrieval + inference) | b_hop_ablation_results.json | Single-hop ceiling + chain-context 干擾量化 |
| **Sim-OB** | Chain-only context | context = 僅 chain 的 N current facts | sim_ob_chain_only_results.json | 純 chain reasoning ceiling |
| **Sim-OB-grad** | Noise gradient | chain + k ∈ {10, 50, 100, 200, 455} distractors × {random, ppr-nearby} | sim_ob_grad_results.json | Noise tolerance 曲線 |
| **C** | 移除非 chain old facts | 6k 全集移除其他題目的 old facts | c_no_distractor_conflicts_results.json | Query-irrelevant conflicts 是否有害 |

---

## Modified prompt (用於 A1, B, Sim-OB, Sim-OB-grad, C)

System prompt 在原 HippoRAG `rag_qa_musique` system 後追加:

> After "Thought: ", output a single line in the exact format
> "Intermediate answers: [a, b, c]" where the bracketed list contains your
> predicted entity at each reasoning hop in order (the last item being the
> final answer). If the question is single-hop, the list has exactly one item.

One-shot example 也更新成示範新格式 (Neville Stanton → University of Southampton → 1862)。

**為何要重建 baseline**: prompt 改動會改變 LLM 行為。實際測得 SH 從 77% → 96% 大跳,證實 prompt 確實影響表現。所有後續比較都對齊 modified-prompt baseline 才公平。

---

## A2 演算法

對每題,逐 hop 比對 LLM intermediate prediction vs MQuAKE per-hop GT:

```
classify_hop(pred, gt, old, conflict_type):
  if pred matches gt:                        return "correct"
  elif conflict_type=="has_pair" and pred matches old:  return "older_fact"
  elif pred is missing:                      return "missing"
  else:                                       return "other"
```

對失敗題,找 **first error hop** = 第一個 class != "correct" 的 hop。記錄該 hop 的 conflict_type、class、position。

---

## B 演算法

對每題每 hop:
1. 取 `hop_question` (e.g. "Who is the author of Our Mutual Friend?")
2. 用 FC question wrapper 包裝
3. HippoRAG.retrieve() with cached index → top-10 passages
4. 用 modified-prompt + retrieved 跑 inference
5. 比對 final answer 與 hop_gt_answer

**為何 retrieve 而非沿用 MH 題的 retrieval**: 我們要的是 single-hop ceiling — 即 LLM 在最理想的 retrieval 條件下能否解這個 hop。MH 題的 retrieval 是為了多跳設計的,沿用會把該題其他 hop 的 entity 一起帶進來 → noise。

**Cross-tab with A2**:
- A2 = 同 hop 在 chain context 中的預測
- B = 同 hop 在 standalone retrieval 中的預測
- 兩者相減 = chain context 本身造成的干擾量

---

## Sim-OB 演算法

context = 由 chain 的 N current facts 組成的單一 "Wikipedia Title:" passage,facts 按原 seq-no 排序保留 numbered 格式 (這樣才符合 FC prompt wrapper 的「serial number」框架)。

無 retrieval 步驟 — 直接餵給 LLM,測純 chain reasoning。

---

## Sim-OB-grad 演算法

每題對每個 (source, k) 配置構造 context:
- chain N current facts (一定保留)
- + k distractor facts:
  - **random**: uniform 從非 chain 的 ~451 個 facts 抽
  - **ppr-nearby**: 取該題原 retrieval 中所有 fact (按 PPR rank 順序),排除 chain → 取前 k

facts 全部按 seq-no 升序混入同一 passage。

**Noise level k=455** = 全集 (chain 之外所有 facts 都進來)。此時 random 與 ppr-nearby 應該幾乎一樣,作為 sanity check。

---

## C 演算法

**Global old-fact set 認定**: 用 `mh_512_mquake_analysis.json` + `sh_512_mquake_analysis.json` 中所有 `has_pair` hop 的 `old_seq` 取聯集。這是「至少有一道測試題會用到的 old facts」。

對每題:
- chain old seqs = 該題各 hop 的 old_seq
- non-chain olds to remove = global olds - chain olds
- kept facts = 全 455 - non-chain olds
- 用 kept facts (按 seq-no 升序) 構造 context

如此保留:
- 所有 newest facts
- 該題 chain 上的 conflict 對 (新 + 舊)
- 移除其他題目的 old facts

---

## 預期結論模板

| 觀察 | 推論 |
|---|---|
| A2 first-error 多在 has_conflict | conflict 解析是主要瓶頸 |
| A2 first-error 也有 no_conflict 的比例 | chain 在 noisy context 下也會 drift |
| B per-hop EM ≫ A2 per-hop correct | chain context 干擾量化 (差值 = 干擾貢獻) |
| Sim-OB 接近 100% | 純 chain reasoning 不是瓶頸 |
| Sim-OB-grad 在 PPR-nearby 比 random 早 drop | semantic distractors 比 length 更傷 |
| C >> A1 baseline | non-chain conflicts 也會干擾 |
| C ≈ Oracle A | 干擾來源主要是 query-irrelevant conflicts |
| C < Oracle A | 即使 query-relevant 是主要,non-chain conflicts 也貢獻一部分 |

---

*產出日期: 2026-04-28*
