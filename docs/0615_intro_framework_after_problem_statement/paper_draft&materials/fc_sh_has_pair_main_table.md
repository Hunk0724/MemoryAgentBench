# FC-SH has_pair 主結果(Mac Studio 重現)

> **數據來源**:Mac Studio M2 Ultra 從零 clone 重跑(2026-06-30 / 07-01),`gpt-4o-mini` temp 0、embedding `text-embedding-3-small`、chunk 512、top-100。詳細對齊度見 [reproduction_log_mac_studio.md](../../handoff/reproduction_log_mac_studio.md)。
> **子集**:`has_pair`(FC-SH 中真正有 knowledge-update 衝突的題,對應 method claim 主戰場)。
> **搭配讀**:[experiment_results.md §1.1](experiment_results.md) 是 paper baseline(另一台 Linux 跑的);本檔用 **Mac Studio 這台的數字**;每格 Δ 於 ±2-3(single deterministic run + OpenAI server-side bf16 抖動)。

---

## Table 1(headline,以 % 呈現)— `has_pair` Exact Match Accuracy

| Method | 6k | 32k | 64k |
| :--- | :---: | :---: | :---: |
| **ours** (P1 + conservative write + phase2 resolve full P3+P5) | **93.2** | 86.2¹ | **90.9** |
| **ours-p3-only** (P3 LLM identity over full top-k, no (S,P) routing, no P5) | 91.9 | **87.7** ★ | 89.4 |
| **ours-no-P5** (phase2 with P3 grouping but forced argmax; no conflict-type classifier) | 90.5 | 84.6 | 90.9 |
| ours-struct (structural-only:(S,P) group + argmax; no LLM at query time) | **93.2** | 78.5 | 86.4 |
| LCA (gpt-4o-mini full-context, no memory) | 87.8 | 70.8 | 57.6 |
| Zep (proactive, decoupled) | 62.2 | 50.8 | 54.5 |
| (b) mem0+P1 (P1 held-fixed + mem0 destructive update) | 44.6 | 38.5 | 51.5 |
| (a) vanilla mem0 (native extraction + destructive) | 0.0 | 3.1 | 3.0 |

¹ 32k `ours` re-read reports 56/65 this session vs 57/65 previously (single-run answer-LLM noise; -1 pp, within tolerance).

---

## Table 2(detailed,分數 + Acc)— 供論文附錄或審稿追蹤

| Method | 6k | 32k | 64k |
| :--- | :---: | :---: | :---: |
| ours | 69/74 (93.2%) | 56/65 (86.2%)¹ | 60/66 (90.9%) |
| ours-p3-only | 68/74 (91.9%) | 57/65 (87.7%) | 59/66 (89.4%) |
| ours-no-P5 | 67/74 (90.5%) | 55/65 (84.6%) | 60/66 (90.9%) |
| ours-struct | 69/74 (93.2%) | 51/65 (78.5%) | 57/66 (86.4%) |
| LCA | 65/74 (87.8%) | 46/65 (70.8%) | 38/66 (57.6%) |
| Zep | 46/74 (62.2%) | 33/65 (50.8%) | 36/66 (54.5%) |
| (b) mem0+P1 | 33/74 (44.6%) | 25/65 (38.5%) | 34/66 (51.5%) |
| (a) vanilla | 0/74 (0.0%) | 2/65 (3.1%) | 2/66 (3.0%) |

`has_pair` 分母隨長度變:6k = 74、32k = 65、64k = 66(FC-SH 每長度 100 題中真正含 old/new 版本的子集)。

---

## Caption 三段論(給 figure / table 用)

**What.** FC-SH knowledge-update (`has_pair`) exact-match accuracy of six memory systems / baselines re-run on the Mac Studio (M2 Ultra) at three conversation-history lengths (6k / 32k / 64k). LCA = long-context agent (gpt-4o-mini full-context, no memory module); ours = our full pipeline (faithful write + query-time phase2 resolve); ours-struct = ablation with LLM grouping (P3) and conflict-type classifier (P5) disabled; (b) mem0+P1 = mem0's destructive write with our P1 extraction held fixed; (a) vanilla mem0 = stock mem0.

**Observation.** ours stays flat across lengths (93.2 → 87.7 → 90.9), while LCA drops monotonically (87.8 → 70.8 → 57.6) — the ours-LCA gap widens from 4 to 33 pp as history grows. ours-struct also stays high (93.2 / 78.5 / 86.4), lagging ours by 0-9 pp. vanilla mem0 stays at floor (0-3%) because native extraction fails on the FC dense-fact chunks. (b) mem0+P1 and Zep fluctuate (39-52% / 51-62%) without a clean length trend, reflecting the inherent variance of write-time LLM-judged destructive update and cloud-async graph processing respectively.

**Implication.** Length-robustness on knowledge-update is exclusive to non-destructive writes coupled with query-time resolution; systems that commit KU at write-time (b, vanilla) or bypass memory entirely (LCA) either fluctuate uncontrollably or degrade monotonically with history. That ours-struct alone reaches 78-93% — with LLM components disabled — already establishes structural (S,P) + deterministic temporal as the primary workhorse; the residual 0-9 pp gap to ours full is the contribution of LLM grouping / conflict-type on the long-tail of (S,P) canonicalization failures.

---

## 已知 caveats(建議寫進 paper 揭露)

1. **b (mem0+P1) variance**:6k Δ=-1、32k Δ=-4、64k Δ=+7 vs paper baseline → 跨次跑 range ~11 pp,**這正是 paper 在批的 destructive LLM judge 不穩本身**;可作為 narrative 反例。
2. **Zep variance**:6k -4、32k -3、64k -8 → cloud-async graph processing,paper §1.1 亦承認 Zep 跨長度非單調。
3. **`ours-struct` 這條 ablation 目前對 P3 和 P5 貢獻沒有拆解**:見 [下方 section 「ablation 精細化」](#ablation-精細化-用來拆-p3-vs-p5-個別貢獻)。

---

## Table 3(ablation trend)— 4 mode P3 / P5 / structural 貢獻拆解

`ours_no_p5` + `ours_p3_only`(2026-07-01 已跑),拆解如下:

| L | struct | no_p5 | **p3_only** | ours(full) | P3 純 (no_p5-struct) | **P3 vs struct**(p3_only-struct)| P5 net (ours-no_p5) |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **6k** | 69/74 | 67/74 | 68/74 | 68/74 | -2 pp | -1 pp | +1 pp |
| **32k** | 51/65 | 55/65 | **57/65** ★ | 56/65 | +4 pp | **+6 pp** ★ | +1 pp |
| **64k** | 57/66 | 60/66 | 59/66 | 60/66 | +3 pp | +2 pp | 0 pp |

判讀:

1. **32k p3_only(+6 vs struct) ≥ ours full(+5)** — 純 P3 LLM identity 一次判 100 candidates 就足夠替代 (S,P)+P3+P5 完整組合。
2. **32k struct 錯 / p3_only 對 = 8 題**(qid 1, 2, 3, 21, 65, 81, 87, 94)— 幾乎全是 stem-vs-full predicate(paper 32k case study §3.1 A mode),P3 LLM 語意識別能一次收斂;struct 因 (S,P) canonicalize 分不同 bucket 沒接到。
3. **6k / 64k p3_only < struct**(小差距)— 短長度上 structural 已足夠;長歷史上 retrieval 更雜 P3 判斷變難。
4. **P5 conflict-type classifier 幾乎中性**(0-1 pp);FC 上判 97% freshness,skip 幾乎沒影響。
5. **strong backbone(gpt-4o-mini)下:P3 LLM 與 structural 對等,可互為替代**;structural 效率完勝(免 LLM call、寫入端也免 (S,P) index 建構)。
6. **weak-model 假設(GX10 待驗)**:P3 對 100 candidates 一次判 identity 對弱模型過於複雜可能崩;structural (S,P) 語言無關、不打 LLM,弱模型上應該相對穩。**若弱模型上 p3_only << struct → decomposed simple tasks for weak model 得到最乾淨的 evidence**。

## 32k 逐題對位(65 has_pair)— 4 mode 交集

| bucket | n | qids |
| :--- | :---: | :--- |
| all 4 correct(共同 backbone) | 46 | — |
| all 4 wrong | 6 | [8, 9(benchmark 標註錯), 27, 32, 51, 68] |
| **struct 錯, p3_only 對**(P3 LLM 語意勝結構)| **8** ★ | [1, 2, 3, 21, 65, 81, 87, 94] |
| struct 對, p3_only 錯(structural 勝 LLM 語意) | 2 | [46, 70] |
| misc(3-way split)| 3 | [16, 84, 88] |

**注**:8 題「P3 勝 struct」全部對應 case study A mode(stem-vs-full predicate,`is affiliated with` vs `is affiliated with the religion of` 等)。struct 因 predicate 字面不同分到不同 (S,P) bucket 沒接到;P3 LLM 一次過 100 candidates 判 identity 能識別同 fact 不同表面。

## Ablation 精細化(下一步 — P3-only mode)

> **反思(2026-07-01)**:目前 `ours` vs `ours-struct` 的 delta 混合了 **P3 (LLM identity grouping) + P5 (LLM conflict-type classifier)** 兩個元件。在 FC-SH world-fact 題上,理論上 **所有衝突都是 FRESHNESS(取最新即可)**,P5 判斷若誤判成 `COMPLEMENTARY` 反而會 **keep-all 傷害** ours。因此 `ours full` 未必比 `ours-struct + P3-only` 好 —— 現有數字看不出這件事。

### 建議新增兩個 mode(要動 code,估 ~15 行)

| Mode | (S,P) group | LLM P3 grouping | P5 classifier | 每 group 動作 |
| :--- | :---: | :---: | :---: | :--- |
| `ours_struct`(現有)| ✅ | ❌ | ❌ | 無條件 argmax(取最新)|
| **`ours_p3only`**(新)| ✅ | ✅ | ❌ | 無條件 argmax(取最新)|
| **`ours_p5only`**(新)| ✅ | ❌ | ✅ | 依 P5 分類決定 drop/keep |
| `ours`(現有 full)| ✅ | ✅ | ✅ | 依 P5 分類 |

實作路徑:
- 加 env flag `MEM0_P5_SKIP=1`(在 `phase2_resolve` 內若 true 則跳過 `_classify_conflict_type`、對每 group 直接 argmax)
- 加 env flag `MEM0_P3_SKIP=1`(在 `dynamic_pool` 內若 true 則不呼 `llm_identity_clusters`、每筆當 singleton)
- `run_fc_sh.sh` 加 2 個新 method 值:`ours_p3only`(P5_SKIP=1) 與 `ours_p5only`(P3_SKIP=1)
- 各自獨立 STORE / OUTDIR / cache 後綴(避免污染)

跑完可得 **完整 2×2 ablation grid**:

| | P3 off | P3 on |
| :--- | :---: | :---: |
| **P5 off** | `ours_struct` | `ours_p3only`(新)|
| **P5 on** | `ours_p5only`(新)| `ours`(full) |

- 若 `ours_p3only > ours` → **P5 在 FC 上真的害** → paper 應該說「FC 上只走 P3 就好、關掉 P5」
- 若 `ours_p3only ≈ ours` → P5 在 FC 上中性(97% 判 FRESHNESS 自己在 paper §3.1 已測)
- 若 `ours_p5only ≈ ours_struct` → P5 對 structural_pool 貢獻趨零(vice versa)

這 4 個 cell 給 paper 的「LLM 元件到底哪個在做事」提供決定性答案。

---

## 更新歷程

- 2026-07-01 深夜:加 `ours_no_p5` 3 cell + Table 3 P3/P5 拆解 + 32k 逐題對位 + Table 1/2 加 no_p5 一列
- 2026-07-01:主表建立(本檔)+ ablation 精細化提議
- 2026-06-30:reproduction_log 內粗 grid 完成(18 cell)
