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
| ours (full P3+P5) | 52/53 (98%) | 14/19 (74%) | 1/1 (100%) | 1/1 (100%) | 68/74 (92%) |
| ours (no_p5) | 51/52 (98%) | 16/20 (80%) | 1/1 (100%) | 1/1 (100%) | 69/74 (93%) |
| ours (struct) | 47/47 (100%) | 18/25 (72%) | 2/2 (100%) | 0/0 | 67/74 (91%) |
| ours (p3_only) | 48/48 (100%) | 21/24 (88%) | 1/1 (100%) | 1/1 (100%) | **71/74 (96%)** |
| (b) mem0+P1 | 15/27 (56%) | 5/12 (42%) | 4/15 (27%) | 10/20 (50%) | 34/74 (46%) |
| Zep (k=10) | 0/0 | 44/72 (61%) | 2/2 (100%) | 0/0 | 46/74 (62%) |

### Wrong-qid list per bucket (for Tier 2 case study,length = 6k)

每格列 wrong qids(供 §5 case study 挑選)。空格代表無 wrong qids 在該桶。

| Method | PP-New wrong | PP-Both wrong | PP-OldOnly wrong | PP-Missing wrong |
| :--- | :--- | :--- | :--- | :--- |
| ours (full P3+P5) |  5 | 7, 30, 33, 48, 70 | — | — |
| ours (no_p5) |  5 | 30, 33, 48, 70 | — | — |
| ours (struct) |  — | 30, 33, 48, 58, 66, 70, 81 | — | — |
| ours (p3_only) |  — | 30, 33, 70 | — | — |
| (b) mem0+P1 |  19, 23, 35, 39, 55, 56, ... (+6) | 12, 15, 28, 30, 45, 50, 86 | 14, 33, 34, 52, 57, 60, ... (+5) | 5, 7, 17, 26, 38, 40, ... (+4) |
| Zep (k=10) |  — | 0, 1, 7, 12, 16, 19, ... (+22) | — | — |


## 32k

### Length = 32k  (has_pair N = 65)

**Table.** Return-context × Accuracy cross-tab. Each cell = `Acc✓/Bucket_total (Acc-rate in bucket)`. **Row = method**, **Col = pool state**. E2E ↑ = final has_pair exact-match. Single deterministic run (temp 0), no error bar.

| Method | PP-New Acc/N ↑ | PP-Both Acc/N | PP-OldOnly Acc/N ↓ | PP-Missing Acc/N ↓ | E2E Acc/N ↑ |
| :--- | ---: | ---: | ---: | ---: | ---: |
| ours (full P3+P5) | 40/40 (100%) | 14/21 (67%) | 0/3 (0%) | 1/1 (100%) | 55/65 (85%) |
| ours (no_p5) | 39/40 (98%) | 16/21 (76%) | 1/3 (33%) | 1/1 (100%) | 57/65 (88%) |
| ours (struct) | 32/32 (100%) | 19/29 (66%) | 0/3 (0%) | 1/1 (100%) | 52/65 (80%) |
| ours (p3_only) | 39/39 (100%) | 17/22 (77%) | 1/3 (33%) | 1/1 (100%) | **58/65 (89%)** |
| (b) mem0+P1 | 12/22 (55%) | 7/14 (50%) | 4/11 (36%) | 6/18 (33%) | 29/65 (45%) |
| Zep (k=10) | 0/1 (0%) | 4/62 (6%) | 0/1 (0%) | 0/1 (0%) | 4/65 (6%) |

### Wrong-qid list per bucket (for Tier 2 case study,length = 32k)

每格列 wrong qids(供 §5 case study 挑選)。空格代表無 wrong qids 在該桶。

| Method | PP-New wrong | PP-Both wrong | PP-OldOnly wrong | PP-Missing wrong |
| :--- | :--- | :--- | :--- | :--- |
| ours (full P3+P5) |  — | 16, 27, 32, 46, 51, 68, 88 | 8, 9, 21 | — |
| ours (no_p5) |  70 | 16, 27, 32, 46, 51 | 8, 9 | — |
| ours (struct) |  — | 2, 3, 27, 32, 51, 65, ... (+4) | 8, 9, 21 | — |
| ours (p3_only) |  — | 27, 32, 46, 51, 88 | 8, 9 | — |
| (b) mem0+P1 |  15, 26, 52, 66, 70, 74, ... (+4) | 2, 3, 23, 53, 60, 62, 79 | 20, 21, 27, 41, 46, 56, 67 | 5, 17, 42, 47, 49, 54, ... (+6) |
| Zep (k=10) |  46 | 0, 1, 2, 3, 5, 8, ... (+52) | 61 | 21 |


## 64k

### Length = 64k  (has_pair N = 66)

**Table.** Return-context × Accuracy cross-tab. Each cell = `Acc✓/Bucket_total (Acc-rate in bucket)`. **Row = method**, **Col = pool state**. E2E ↑ = final has_pair exact-match. Single deterministic run (temp 0), no error bar.

| Method | PP-New Acc/N ↑ | PP-Both Acc/N | PP-OldOnly Acc/N ↓ | PP-Missing Acc/N ↓ | E2E Acc/N ↑ |
| :--- | ---: | ---: | ---: | ---: | ---: |
| ours (full P3+P5) | 35/38 (92%) | 21/23 (91%) | 4/5 (80%) | 0/0 | **60/66 (91%)** |
| ours (no_p5) | 35/38 (92%) | 21/23 (91%) | 4/5 (80%) | 0/0 | **60/66 (91%)** |
| ours (struct) | 30/30 (100%) | 25/33 (76%) | 3/3 (100%) | 0/0 | 58/66 (88%) |
| ours (p3_only) | 34/36 (94%) | 20/25 (80%) | 4/5 (80%) | 0/0 | 58/66 (88%) |
| (b) mem0+P1 | 13/25 (52%) | 6/15 (40%) | 6/17 (35%) | 2/9 (22%) | 27/66 (41%) |
| Zep (k=10) | 1/1 (100%) | 34/62 (55%) | 1/3 (33%) | 0/0 | 36/66 (55%) |

### Wrong-qid list per bucket (for Tier 2 case study,length = 64k)

每格列 wrong qids(供 §5 case study 挑選)。空格代表無 wrong qids 在該桶。

| Method | PP-New wrong | PP-Both wrong | PP-OldOnly wrong | PP-Missing wrong |
| :--- | :--- | :--- | :--- | :--- |
| ours (full P3+P5) |  0, 40, 91 | 85, 86 | 20 | — |
| ours (no_p5) |  0, 40, 91 | 85, 86 | 20 | — |
| ours (struct) |  — | 0, 8, 18, 20, 85, 86, 91, 97 | — | — |
| ours (p3_only) |  0, 91 | 5, 37, 47, 85, 86 | 20 | — |
| (b) mem0+P1 |  0, 16, 19, 22, 32, 40, ... (+6) | 5, 47, 50, 57, 58, 73, ... (+3) | 1, 9, 24, 29, 60, 61, ... (+5) | 11, 20, 31, 35, 59, 79, 95 |
| Zep (k=10) |  — | 0, 1, 4, 7, 8, 9, ... (+22) | 23, 24 | — |


---

## Observation(three-part: what / why / implication)

### Length = 6k

**What** — pool state 分佈 + in-bucket accuracy(per row):

- **ours (full P3+P5)**: PP-New 佔 72% (Acc-in-bucket = 98%), PP-Both 佔 26% (Acc-in-bucket = 74%), PP-OldOnly 1%, PP-Missing 1%; **E2E = 91.9%**
- **ours (no_p5)**: PP-New 佔 70% (Acc-in-bucket = 98%), PP-Both 佔 27% (Acc-in-bucket = 80%), PP-OldOnly 1%, PP-Missing 1%; **E2E = 93.2%**
- **ours (struct)**: PP-New 佔 64% (Acc-in-bucket = 100%), PP-Both 佔 34% (Acc-in-bucket = 72%), PP-OldOnly 3%, PP-Missing 0%; **E2E = 90.5%**
- **ours (p3_only)**: PP-New 佔 65% (Acc-in-bucket = 100%), PP-Both 佔 32% (Acc-in-bucket = 88%), PP-OldOnly 1%, PP-Missing 1%; **E2E = 95.9%**
- **(b) mem0+P1**: PP-New 佔 36% (Acc-in-bucket = 56%), PP-Both 佔 16% (Acc-in-bucket = 42%), PP-OldOnly 20%, PP-Missing 27%; **E2E = 45.9%**
- **Zep (k=10)**: PP-New 佔 0% (Acc-in-bucket = —), PP-Both 佔 97% (Acc-in-bucket = 61%), PP-OldOnly 3%, PP-Missing 0%; **E2E = 62.2%**

### Length = 32k

**What** — pool state 分佈 + in-bucket accuracy(per row):

- **ours (full P3+P5)**: PP-New 佔 62% (Acc-in-bucket = 100%), PP-Both 佔 32% (Acc-in-bucket = 67%), PP-OldOnly 5%, PP-Missing 2%; **E2E = 84.6%**
- **ours (no_p5)**: PP-New 佔 62% (Acc-in-bucket = 98%), PP-Both 佔 32% (Acc-in-bucket = 76%), PP-OldOnly 5%, PP-Missing 2%; **E2E = 87.7%**
- **ours (struct)**: PP-New 佔 49% (Acc-in-bucket = 100%), PP-Both 佔 45% (Acc-in-bucket = 66%), PP-OldOnly 5%, PP-Missing 2%; **E2E = 80.0%**
- **ours (p3_only)**: PP-New 佔 60% (Acc-in-bucket = 100%), PP-Both 佔 34% (Acc-in-bucket = 77%), PP-OldOnly 5%, PP-Missing 2%; **E2E = 89.2%**
- **(b) mem0+P1**: PP-New 佔 34% (Acc-in-bucket = 55%), PP-Both 佔 22% (Acc-in-bucket = 50%), PP-OldOnly 17%, PP-Missing 28%; **E2E = 44.6%**
- **Zep (k=10)**: PP-New 佔 2% (Acc-in-bucket = 0%), PP-Both 佔 95% (Acc-in-bucket = 6%), PP-OldOnly 2%, PP-Missing 2%; **E2E = 6.2%**

### Length = 64k

**What** — pool state 分佈 + in-bucket accuracy(per row):

- **ours (full P3+P5)**: PP-New 佔 58% (Acc-in-bucket = 92%), PP-Both 佔 35% (Acc-in-bucket = 91%), PP-OldOnly 8%, PP-Missing 0%; **E2E = 90.9%**
- **ours (no_p5)**: PP-New 佔 58% (Acc-in-bucket = 92%), PP-Both 佔 35% (Acc-in-bucket = 91%), PP-OldOnly 8%, PP-Missing 0%; **E2E = 90.9%**
- **ours (struct)**: PP-New 佔 45% (Acc-in-bucket = 100%), PP-Both 佔 50% (Acc-in-bucket = 76%), PP-OldOnly 5%, PP-Missing 0%; **E2E = 87.9%**
- **ours (p3_only)**: PP-New 佔 55% (Acc-in-bucket = 94%), PP-Both 佔 38% (Acc-in-bucket = 80%), PP-OldOnly 8%, PP-Missing 0%; **E2E = 87.9%**
- **(b) mem0+P1**: PP-New 佔 38% (Acc-in-bucket = 52%), PP-Both 佔 23% (Acc-in-bucket = 40%), PP-OldOnly 26%, PP-Missing 14%; **E2E = 40.9%**
- **Zep (k=10)**: PP-New 佔 2% (Acc-in-bucket = 100%), PP-Both 佔 94% (Acc-in-bucket = 55%), PP-OldOnly 5%, PP-Missing 0%; **E2E = 54.5%**

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