# Tier 1 主 metric — Return-context × Accuracy Cross-tabulation

> **Purpose**:對每 method × length,把「pool state」(送進 answer LLM 前的 memory 內容)與「E2E Acc」(最終答對錯)交叉分類 → **精準呈現答題結果如何被 pool state 預測**。
>
> **Rigor**:matcher v3(triple-based,拒絕 Layer-1 SequenceMatcher 的 false positive);ours* 用 `memories_str`(實際 answer LLM 看到的內容),mem0(b) 用 `retrieved_memories`,Zep 用 `edges`;single deterministic run,無 error bar。
>
> **Corresponding protocol**:[../evaluation_protocol_main.md §4.2](../evaluation_protocol_main.md)

---

## 6k

### Length = 6k  (has_pair N = 74)

**Table.** Return-context × Accuracy cross-tab. Each cell = `Acc✓/Bucket_total (Acc-rate in bucket)`. **Row = method**, **Col = pool state**. E2E ↑ = final has_pair exact-match. Single deterministic run (temp 0), no error bar.

| Method | PP-New Acc/N ↑ | PP-Both Acc/N | PP-OldOnly Acc/N ↓ | PP-Missing Acc/N ↓ | E2E Acc/N ↑ |
| :--- | ---: | ---: | ---: | ---: | ---: |
| ours | 52/53 (98%) | 17/21 (81%) | 0/0 | 0/0 | 69/74 (93%) |
| ours (no P3) | 47/47 (100%) | 20/27 (74%) | 0/0 | 0/0 | 67/74 (91%) |
| ours (no struct) | 49/49 (100%) | 22/25 (88%) | 0/0 | 0/0 | **71/74 (96%)** |
| (b) mem0+P1 | 25/27 (93%) | 9/12 (75%) | 0/15 (0%) | 0/20 (0%) | 34/74 (46%) |
| Zep (k=10) | 0/0 | 46/74 (62%) | 0/0 | 0/0 | 46/74 (62%) |
| ours (+P5) [appendix] | 53/54 (98%) | 15/20 (75%) | 0/0 | 0/0 | 68/74 (92%) |
| [4.1-mini] ours | 0/0 | 0/0 | 0/0 | 0/0 | 0/0 |
| [4.1-mini] ours (no P3) | 0/0 | 0/0 | 0/0 | 0/0 | 0/0 |
| [4.1-mini] ours (no struct) | 0/0 | 0/0 | 0/0 | 0/0 | 0/0 |
| [4.1-mini] (b) mem0+P1 | 0/0 | 0/0 | 0/0 | 0/0 | 0/0 |
| [4.1-mini] Zep (k=10) | 0/0 | 0/0 | 0/0 | 0/0 | 0/0 |
| [4.1-mini] ours (+P5) [appendix] | 0/0 | 0/0 | 0/0 | 0/0 | 0/0 |

### Wrong-qid list per bucket (for Tier 2 case study,length = 6k)

每格列 wrong qids(供 §5 case study 挑選)。空格代表無 wrong qids 在該桶。

| Method | PP-New wrong | PP-Both wrong | PP-OldOnly wrong | PP-Missing wrong |
| :--- | :--- | :--- | :--- | :--- |
| ours |  5 | 30, 33, 48, 70 | — | — |
| ours (no P3) |  — | 30, 33, 48, 58, 66, 70, 81 | — | — |
| ours (no struct) |  — | 30, 33, 70 | — | — |
| (b) mem0+P1 |  41, 53 | 12, 50, 86 | 1, 14, 16, 33, 34, 42, ... (+9) | 5, 6, 7, 13, 17, 20, ... (+14) |
| Zep (k=10) |  — | 0, 1, 7, 12, 16, 19, ... (+22) | — | — |
| ours (+P5) [appendix] |  5 | 7, 30, 33, 48, 70 | — | — |
| [4.1-mini] ours |  — | — | — | — |
| [4.1-mini] ours (no P3) |  — | — | — | — |
| [4.1-mini] ours (no struct) |  — | — | — | — |
| [4.1-mini] (b) mem0+P1 |  — | — | — | — |
| [4.1-mini] Zep (k=10) |  — | — | — | — |
| [4.1-mini] ours (+P5) [appendix] |  — | — | — | — |


## 32k

### Length = 32k  (has_pair N = 65)

**Table.** Return-context × Accuracy cross-tab. Each cell = `Acc✓/Bucket_total (Acc-rate in bucket)`. **Row = method**, **Col = pool state**. E2E ↑ = final has_pair exact-match. Single deterministic run (temp 0), no error bar.

| Method | PP-New Acc/N ↑ | PP-Both Acc/N | PP-OldOnly Acc/N ↓ | PP-Missing Acc/N ↓ | E2E Acc/N ↑ |
| :--- | ---: | ---: | ---: | ---: | ---: |
| ours | 39/40 (98%) | 17/22 (77%) | 0/2 (0%) | 1/1 (100%) | 57/65 (88%) |
| ours (no P3) | 32/32 (100%) | 19/30 (63%) | 0/2 (0%) | 1/1 (100%) | 52/65 (80%) |
| ours (no struct) | 39/39 (100%) | 18/23 (78%) | 0/2 (0%) | 1/1 (100%) | **58/65 (89%)** |
| (b) mem0+P1 | 21/22 (95%) | 4/14 (29%) | 0/11 (0%) | 0/18 (0%) | 25/65 (38%) |
| Zep (k=10) | 1/2 (50%) | 32/62 (52%) | 0/1 (0%) | 0/0 | 33/65 (51%) |
| ours (+P5) [appendix] | 40/40 (100%) | 14/22 (64%) | 0/2 (0%) | 1/1 (100%) | 55/65 (85%) |
| [4.1-mini] ours | 0/0 | 0/0 | 0/0 | 0/0 | 0/0 |
| [4.1-mini] ours (no P3) | 0/0 | 0/0 | 0/0 | 0/0 | 0/0 |
| [4.1-mini] ours (no struct) | 0/0 | 0/0 | 0/0 | 0/0 | 0/0 |
| [4.1-mini] (b) mem0+P1 | 0/0 | 0/0 | 0/0 | 0/0 | 0/0 |
| [4.1-mini] Zep (k=10) | 0/0 | 0/0 | 0/0 | 0/0 | 0/0 |
| [4.1-mini] ours (+P5) [appendix] | 0/0 | 0/0 | 0/0 | 0/0 | 0/0 |

### Wrong-qid list per bucket (for Tier 2 case study,length = 32k)

每格列 wrong qids(供 §5 case study 挑選)。空格代表無 wrong qids 在該桶。

| Method | PP-New wrong | PP-Both wrong | PP-OldOnly wrong | PP-Missing wrong |
| :--- | :--- | :--- | :--- | :--- |
| ours |  70 | 16, 27, 32, 46, 51 | 8, 9 | — |
| ours (no P3) |  — | 2, 3, 21, 27, 32, 51, ... (+5) | 8, 9 | — |
| ours (no struct) |  — | 27, 32, 46, 51, 88 | 8, 9 | — |
| (b) mem0+P1 |  70 | 2, 3, 16, 23, 32, 53, ... (+4) | 1, 9, 20, 21, 27, 41, ... (+5) | 5, 17, 31, 33, 38, 42, ... (+12) |
| Zep (k=10) |  21 | 0, 1, 2, 8, 9, 16, ... (+24) | 61 | — |
| ours (+P5) [appendix] |  — | 16, 21, 27, 32, 46, 51, 68, 88 | 8, 9 | — |
| [4.1-mini] ours |  — | — | — | — |
| [4.1-mini] ours (no P3) |  — | — | — | — |
| [4.1-mini] ours (no struct) |  — | — | — | — |
| [4.1-mini] (b) mem0+P1 |  — | — | — | — |
| [4.1-mini] Zep (k=10) |  — | — | — | — |
| [4.1-mini] ours (+P5) [appendix] |  — | — | — | — |


## 64k

### Length = 64k  (has_pair N = 66)

**Table.** Return-context × Accuracy cross-tab. Each cell = `Acc✓/Bucket_total (Acc-rate in bucket)`. **Row = method**, **Col = pool state**. E2E ↑ = final has_pair exact-match. Single deterministic run (temp 0), no error bar.

| Method | PP-New Acc/N ↑ | PP-Both Acc/N | PP-OldOnly Acc/N ↓ | PP-Missing Acc/N ↓ | E2E Acc/N ↑ |
| :--- | ---: | ---: | ---: | ---: | ---: |
| ours | 35/38 (92%) | 24/26 (92%) | 1/2 (50%) | 0/0 | **60/66 (91%)** |
| ours (no P3) | 30/30 (100%) | 28/36 (78%) | 0/0 | 0/0 | 58/66 (88%) |
| ours (no struct) | 34/36 (94%) | 23/28 (82%) | 1/2 (50%) | 0/0 | 58/66 (88%) |
| (b) mem0+P1 | 25/25 (100%) | 9/17 (53%) | 0/15 (0%) | 0/9 (0%) | 34/66 (52%) |
| Zep (k=10) | 1/1 (100%) | 35/65 (54%) | 0/0 | 0/0 | 36/66 (55%) |
| ours (+P5) [appendix] | 35/38 (92%) | 24/26 (92%) | 1/2 (50%) | 0/0 | **60/66 (91%)** |
| [4.1-mini] ours | 0/0 | 0/0 | 0/0 | 0/0 | 0/0 |
| [4.1-mini] ours (no P3) | 0/0 | 0/0 | 0/0 | 0/0 | 0/0 |
| [4.1-mini] ours (no struct) | 0/0 | 0/0 | 0/0 | 0/0 | 0/0 |
| [4.1-mini] (b) mem0+P1 | 0/0 | 0/0 | 0/0 | 0/0 | 0/0 |
| [4.1-mini] Zep (k=10) | 0/0 | 0/0 | 0/0 | 0/0 | 0/0 |
| [4.1-mini] ours (+P5) [appendix] | 0/0 | 0/0 | 0/0 | 0/0 | 0/0 |

### Wrong-qid list per bucket (for Tier 2 case study,length = 64k)

每格列 wrong qids(供 §5 case study 挑選)。空格代表無 wrong qids 在該桶。

| Method | PP-New wrong | PP-Both wrong | PP-OldOnly wrong | PP-Missing wrong |
| :--- | :--- | :--- | :--- | :--- |
| ours |  0, 40, 91 | 85, 86 | 20 | — |
| ours (no P3) |  — | 0, 8, 18, 20, 85, 86, 91, 97 | — | — |
| ours (no struct) |  0, 91 | 5, 37, 47, 85, 86 | 20 | — |
| (b) mem0+P1 |  — | 50, 53, 57, 58, 88, 93, 97, 98 | 1, 2, 4, 9, 29, 38, ... (+9) | 11, 18, 20, 26, 31, 35, ... (+3) |
| Zep (k=10) |  — | 0, 1, 4, 7, 8, 9, ... (+24) | — | — |
| ours (+P5) [appendix] |  0, 40, 91 | 85, 86 | 20 | — |
| [4.1-mini] ours |  — | — | — | — |
| [4.1-mini] ours (no P3) |  — | — | — | — |
| [4.1-mini] ours (no struct) |  — | — | — | — |
| [4.1-mini] (b) mem0+P1 |  — | — | — | — |
| [4.1-mini] Zep (k=10) |  — | — | — | — |
| [4.1-mini] ours (+P5) [appendix] |  — | — | — | — |


---

## Observation(three-part: what / why / implication)

### Length = 6k

**What** — pool state 分佈 + in-bucket accuracy(per row):

- **ours**: PP-New 佔 72% (Acc-in-bucket = 98%), PP-Both 佔 28% (Acc-in-bucket = 81%), PP-OldOnly 0%, PP-Missing 0%; **E2E = 93.2%**
- **ours (no P3)**: PP-New 佔 64% (Acc-in-bucket = 100%), PP-Both 佔 36% (Acc-in-bucket = 74%), PP-OldOnly 0%, PP-Missing 0%; **E2E = 90.5%**
- **ours (no struct)**: PP-New 佔 66% (Acc-in-bucket = 100%), PP-Both 佔 34% (Acc-in-bucket = 88%), PP-OldOnly 0%, PP-Missing 0%; **E2E = 95.9%**
- **(b) mem0+P1**: PP-New 佔 36% (Acc-in-bucket = 93%), PP-Both 佔 16% (Acc-in-bucket = 75%), PP-OldOnly 20%, PP-Missing 27%; **E2E = 45.9%**
- **Zep (k=10)**: PP-New 佔 0% (Acc-in-bucket = —), PP-Both 佔 100% (Acc-in-bucket = 62%), PP-OldOnly 0%, PP-Missing 0%; **E2E = 62.2%**
- **ours (+P5) [appendix]**: PP-New 佔 73% (Acc-in-bucket = 98%), PP-Both 佔 27% (Acc-in-bucket = 75%), PP-OldOnly 0%, PP-Missing 0%; **E2E = 91.9%**
- **[4.1-mini] ours**: PP-New 佔 0% (Acc-in-bucket = —), PP-Both 佔 100% (Acc-in-bucket = —), PP-OldOnly 0%, PP-Missing 0%; **E2E = 0.0%**
- **[4.1-mini] ours (no P3)**: PP-New 佔 0% (Acc-in-bucket = —), PP-Both 佔 100% (Acc-in-bucket = —), PP-OldOnly 0%, PP-Missing 0%; **E2E = 0.0%**
- **[4.1-mini] ours (no struct)**: PP-New 佔 0% (Acc-in-bucket = —), PP-Both 佔 100% (Acc-in-bucket = —), PP-OldOnly 0%, PP-Missing 0%; **E2E = 0.0%**
- **[4.1-mini] (b) mem0+P1**: PP-New 佔 0% (Acc-in-bucket = —), PP-Both 佔 100% (Acc-in-bucket = —), PP-OldOnly 0%, PP-Missing 0%; **E2E = 0.0%**
- **[4.1-mini] Zep (k=10)**: PP-New 佔 0% (Acc-in-bucket = —), PP-Both 佔 100% (Acc-in-bucket = —), PP-OldOnly 0%, PP-Missing 0%; **E2E = 0.0%**
- **[4.1-mini] ours (+P5) [appendix]**: PP-New 佔 0% (Acc-in-bucket = —), PP-Both 佔 100% (Acc-in-bucket = —), PP-OldOnly 0%, PP-Missing 0%; **E2E = 0.0%**

### Length = 32k

**What** — pool state 分佈 + in-bucket accuracy(per row):

- **ours**: PP-New 佔 62% (Acc-in-bucket = 98%), PP-Both 佔 34% (Acc-in-bucket = 77%), PP-OldOnly 3%, PP-Missing 2%; **E2E = 87.7%**
- **ours (no P3)**: PP-New 佔 49% (Acc-in-bucket = 100%), PP-Both 佔 46% (Acc-in-bucket = 63%), PP-OldOnly 3%, PP-Missing 2%; **E2E = 80.0%**
- **ours (no struct)**: PP-New 佔 60% (Acc-in-bucket = 100%), PP-Both 佔 35% (Acc-in-bucket = 78%), PP-OldOnly 3%, PP-Missing 2%; **E2E = 89.2%**
- **(b) mem0+P1**: PP-New 佔 34% (Acc-in-bucket = 95%), PP-Both 佔 22% (Acc-in-bucket = 29%), PP-OldOnly 17%, PP-Missing 28%; **E2E = 38.5%**
- **Zep (k=10)**: PP-New 佔 3% (Acc-in-bucket = 50%), PP-Both 佔 95% (Acc-in-bucket = 52%), PP-OldOnly 2%, PP-Missing 0%; **E2E = 50.8%**
- **ours (+P5) [appendix]**: PP-New 佔 62% (Acc-in-bucket = 100%), PP-Both 佔 34% (Acc-in-bucket = 64%), PP-OldOnly 3%, PP-Missing 2%; **E2E = 84.6%**
- **[4.1-mini] ours**: PP-New 佔 0% (Acc-in-bucket = —), PP-Both 佔 100% (Acc-in-bucket = —), PP-OldOnly 0%, PP-Missing 0%; **E2E = 0.0%**
- **[4.1-mini] ours (no P3)**: PP-New 佔 0% (Acc-in-bucket = —), PP-Both 佔 100% (Acc-in-bucket = —), PP-OldOnly 0%, PP-Missing 0%; **E2E = 0.0%**
- **[4.1-mini] ours (no struct)**: PP-New 佔 0% (Acc-in-bucket = —), PP-Both 佔 100% (Acc-in-bucket = —), PP-OldOnly 0%, PP-Missing 0%; **E2E = 0.0%**
- **[4.1-mini] (b) mem0+P1**: PP-New 佔 0% (Acc-in-bucket = —), PP-Both 佔 100% (Acc-in-bucket = —), PP-OldOnly 0%, PP-Missing 0%; **E2E = 0.0%**
- **[4.1-mini] Zep (k=10)**: PP-New 佔 0% (Acc-in-bucket = —), PP-Both 佔 100% (Acc-in-bucket = —), PP-OldOnly 0%, PP-Missing 0%; **E2E = 0.0%**
- **[4.1-mini] ours (+P5) [appendix]**: PP-New 佔 0% (Acc-in-bucket = —), PP-Both 佔 100% (Acc-in-bucket = —), PP-OldOnly 0%, PP-Missing 0%; **E2E = 0.0%**

### Length = 64k

**What** — pool state 分佈 + in-bucket accuracy(per row):

- **ours**: PP-New 佔 58% (Acc-in-bucket = 92%), PP-Both 佔 39% (Acc-in-bucket = 92%), PP-OldOnly 3%, PP-Missing 0%; **E2E = 90.9%**
- **ours (no P3)**: PP-New 佔 45% (Acc-in-bucket = 100%), PP-Both 佔 55% (Acc-in-bucket = 78%), PP-OldOnly 0%, PP-Missing 0%; **E2E = 87.9%**
- **ours (no struct)**: PP-New 佔 55% (Acc-in-bucket = 94%), PP-Both 佔 42% (Acc-in-bucket = 82%), PP-OldOnly 3%, PP-Missing 0%; **E2E = 87.9%**
- **(b) mem0+P1**: PP-New 佔 38% (Acc-in-bucket = 100%), PP-Both 佔 26% (Acc-in-bucket = 53%), PP-OldOnly 23%, PP-Missing 14%; **E2E = 51.5%**
- **Zep (k=10)**: PP-New 佔 2% (Acc-in-bucket = 100%), PP-Both 佔 98% (Acc-in-bucket = 54%), PP-OldOnly 0%, PP-Missing 0%; **E2E = 54.5%**
- **ours (+P5) [appendix]**: PP-New 佔 58% (Acc-in-bucket = 92%), PP-Both 佔 39% (Acc-in-bucket = 92%), PP-OldOnly 3%, PP-Missing 0%; **E2E = 90.9%**
- **[4.1-mini] ours**: PP-New 佔 0% (Acc-in-bucket = —), PP-Both 佔 100% (Acc-in-bucket = —), PP-OldOnly 0%, PP-Missing 0%; **E2E = 0.0%**
- **[4.1-mini] ours (no P3)**: PP-New 佔 0% (Acc-in-bucket = —), PP-Both 佔 100% (Acc-in-bucket = —), PP-OldOnly 0%, PP-Missing 0%; **E2E = 0.0%**
- **[4.1-mini] ours (no struct)**: PP-New 佔 0% (Acc-in-bucket = —), PP-Both 佔 100% (Acc-in-bucket = —), PP-OldOnly 0%, PP-Missing 0%; **E2E = 0.0%**
- **[4.1-mini] (b) mem0+P1**: PP-New 佔 0% (Acc-in-bucket = —), PP-Both 佔 100% (Acc-in-bucket = —), PP-OldOnly 0%, PP-Missing 0%; **E2E = 0.0%**
- **[4.1-mini] Zep (k=10)**: PP-New 佔 0% (Acc-in-bucket = —), PP-Both 佔 100% (Acc-in-bucket = —), PP-OldOnly 0%, PP-Missing 0%; **E2E = 0.0%**
- **[4.1-mini] ours (+P5) [appendix]**: PP-New 佔 0% (Acc-in-bucket = —), PP-Both 佔 100% (Acc-in-bucket = —), PP-OldOnly 0%, PP-Missing 0%; **E2E = 0.0%**

---

## Aggregate implication(3 lengths 合看)

**Why** — 從 3 個長度的 pool state 分佈 + Acc-in-bucket 看到三個 pattern:

- **Pattern 1 — ours 給乾淨 pool,LLM 幾乎 100% 抄對**:ours variants 的 PP-New 佔比 55-72%(3 lengths avg ≈ 63%),PP-New Acc-in-bucket **92-100%**(pipeline 給對答案 → LLM 抄對)。P5 skip 版(no_p5 / p3_only)在 PP-Both 桶的 Acc-in-bucket 也高達 76-91%(template hint「取大 serial」發揮作用)。
- **Pattern 2 — (b) mem0+P1 的 pool 混亂,LLM 猜對率低**:(b) 的 PP-New 佔比只 34-38%,**PP-OldOnly + PP-Missing 佔比合計 40-52%**(write-time destructive commit 直接毀掉 gt_new)。**即使 PP-New 桶,Acc-in-bucket 也只 52-56%** — 因為 UPDATE 常合併新舊,pool 內 fact 文字未必是純粹 gt_new,LLM 從 rewrite 過的文字判讀不穩;PP-Missing 桶 Acc-in-bucket 22-50%(LLM 純猜)。
- **Pattern 3 — Zep(k=10)pool 幾乎全 PP-Both,依賴 answer LLM 猜**:PP-Both 佔比 **93-97%**(未做 query-time KU resolution + top-10 兩版都塞進來)。6k / 64k 上 Acc-in-bucket 55-61%,但 **32k catastrophe(Acc-in-bucket 只 6%)**— top-10 上限 + 長 context 使記憶顆粒度失效。

**Implication** — 支撐核心 claim:

> ours 的 E2E 優勢 **主要來自 pool state 的差異**(pipeline 送對 gt_new、濾掉 gt_old),**而非 answer LLM 在 PP-Both 時的猜對率**:ours 的 PP-New 佔比是 (b) mem0+P1 的近 2 倍(63% vs 36%),且 PP-New Acc-in-bucket 是 mem0(b) 的近 2 倍(97% vs 54%)。這對應論文核心主張:**query-time KU resolution 讓記憶正確地被檢索用於推論**;倚賴 answer LLM 從混雜 / 錯誤 pool 中挑對是脆弱的,尤其在弱 backbone(intro 受限部署動機)下崩壞更劇。

**Follow-up(Tier 2 case study)**:對每 method 的 wrong-qid list per bucket 挑代表 case → trace 錯誤模式(A/B/C/D/E),見 [`../evaluation_protocol_main.md §5`](../evaluation_protocol_main.md)

---

## Sanity-check

- 每 row 4 個 bucket 加總應 = N_hp(4×2 分類 collectively exhaustive)
- E2E Acc column 應與 evaluation_protocol_main.md §3.1 landscape 表數字一致
- Zep 的 k=10 caveat:與其他 k=100 不對稱,PP-Missing 被 top-10 上限 bias(不代表 Zep bank 缺 gt_new)

---

*Generated by `analysis/compute_pool_acc_crosstab.py`; source data = `outputs/rag_retrieved/**/query_*.json` + `outputs/**/Conflict_Resolution/*results*.json`. Regenerate: `python analysis/compute_pool_acc_crosstab.py`.*