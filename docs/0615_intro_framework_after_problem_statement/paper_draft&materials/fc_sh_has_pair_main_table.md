# FC-SH has_pair 主結果(Mac Studio 重現)

> **數據來源**:Mac Studio M2 Ultra 從零 clone 重跑(2026-06-30 / 07-01),`gpt-4o-mini` temp 0、embedding `text-embedding-3-small`、chunk 512、top-100。詳細對齊度見 [reproduction_log_mac_studio.md](../../handoff/reproduction_log_mac_studio.md)。
> **子集**:`has_pair`(FC-SH 中真正有 knowledge-update 衝突的題,對應 method claim 主戰場)。
> **搭配讀**:[experiment_results.md §1.1](experiment_results.md) 是 paper baseline(另一台 Linux 跑的);本檔用 **Mac Studio 這台的數字**;每格 Δ 於 ±2-3(single deterministic run + OpenAI server-side bf16 抖動)。

---

## Table 1(headline,以 % 呈現)— `has_pair` Exact Match Accuracy

| Method | 6k | 32k | 64k |
| :--- | :---: | :---: | :---: |
| **ours** (P1 + conservative write + phase2 resolve full P3+P5) | **93.2** | **87.7** | **90.9** |
| **ours-no-P5** (phase2 with P3 grouping but forced argmax; no conflict-type classifier) | 90.5 | 84.6 | 90.9 |
| ours-struct (structural-only:(S,P) group + argmax; no LLM at query time) | 93.2 | 78.5 | 86.4 |
| LCA (gpt-4o-mini full-context, no memory) | 87.8 | 70.8 | 57.6 |
| Zep (proactive, decoupled) | 62.2 | 50.8 | 54.5 |
| (b) mem0+P1 (P1 held-fixed + mem0 destructive update) | 44.6 | 38.5 | 51.5 |
| (a) vanilla mem0 (native extraction + destructive) | 0.0 | 3.1 | 3.0 |

---

## Table 2(detailed,分數 + Acc)— 供論文附錄或審稿追蹤

| Method | 6k | 32k | 64k |
| :--- | :---: | :---: | :---: |
| ours | 69/74 (93.2%) | 57/65 (87.7%) | 60/66 (90.9%) |
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

## Table 3(ablation trend)— P3 vs P5 貢獻拆解

`ours_no_p5` 已跑,拆解如下:

| L | struct | no_p5 | ours | **P3 純貢獻**(no_p5 − struct)| **P5 net**(ours − no_p5)|
| :---: | :---: | :---: | :---: | :---: | :---: |
| **6k** | 69/74 | 67/74 | 69/74 | **-2 pp** ⚠ | +2 pp |
| **32k** | 51/65 | **55/65** | 57/65 | **+4 pp** ★ | +2 pp |
| **64k** | 57/66 | 60/66 | 60/66 | **+3 pp** ★ | 0 pp |

判讀:

1. **P3 LLM identity grouping 是主要 workhorse**(32k +4、64k +3);唯 6k 上 -2(有可能是小樣本 answer-LLM noise 或 P3 對太少 candidate 分群偏 aggressive)
2. **P5 conflict-type classifier 是溫和 upside**(+2/+2/0);跟原本從 `both bucket` 分析預測的「P5 偏害」相反 — 說明 P5 判 NO_CONFLICT keep-all 有時保留了 answer LLM 需要的 canonical form
3. **`ours_no_p5` 全長度都在 struct 之上**(除 6k -2 邊緣)— 說明 P3 有真實貢獻,不是被 P5 帶偏
4. **weak-model regime 假設**(未實測):P5 對弱模型判斷可能更亂 → `ours_no_p5` 可能在弱模型上更 robust;GX10 上跑 3 mode(struct / no_p5 / ours)× 4 size 可驗

## 32k 逐題對位(65 has_pair)— 3 mode 交集

| bucket | n | qids |
| :--- | :---: | :--- |
| all 3 correct(共同 backbone)| 47 | — |
| no_p5 對, ours 錯(**P5 downside**)| 1 | [21] |
| ours 對, no_p5 錯(**P5 upside**)| 2 | [84, 88] |
| struct 對, no_p5 + ours 錯 | 2 | [16, 46](P3 反害)|
| all 3 wrong | 6 | [8, 9(benchmark 標註錯), 27, 32, 51, 68] |
| misc | 7 | — |

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
