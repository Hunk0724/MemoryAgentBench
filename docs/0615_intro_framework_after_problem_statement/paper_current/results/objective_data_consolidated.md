# Objective Data — Consolidated（step 1:客觀數字展示,先呈現、不解釋）

> **用途**:把目前跑過的實驗數字 reconcile 成**單一 source of truth**,供 paper body §4 Experiments 直接引用。
> **原則**:本檔**只放客觀數字 + 出處 + 對不上清單**;observation / implication(step 2 解釋層)不寫在這裡。
> **排版**:依 [`../style_rules_tables_figures_writing.md §6`](../style_rules_tables_figures_writing.md)(row=method、col=length/backbone、bold 每欄最佳、標 ↑、單次 deterministic run 無 error bar)。
>
> **決定紀錄(2026-07-06)**:① 主表「ours (main)」暫**同時列 no_p5 與 full 兩列**,待 ablation 定案再收斂為一列。② 本輪**只 reconcile 現有數字、不補跑**;gpt-4.1-mini × 6k/32k、weak × 32k/64k 為 optional 加固,誠實列 caveat。

---

## §0 Canonical source of truth 政策

| 數據面向 | Canonical 檔 | 產生方式 | 狀態 |
|:--|:--|:--|:--|
| Mid-tier(gpt-4o-mini)E2E + pool-state | [`pool_acc_crosstab.md`](pool_acc_crosstab.md) | `compute_pool_acc_crosstab.py`(per-qid `response` + `parse_output` + `drqa_exact_match_score` v4 重算)| ✅ **唯一權威** |
| Strong-tier(gpt-4.1-mini,64k)| [`pool_acc_crosstab.md`](pool_acc_crosstab.md) `[4.1-mini]` 列 + [`../style_rules_tables_figures_writing.md §10.3b`](../style_rules_tables_figures_writing.md) | 同上 | ✅ 一致 |
| Weak-tier(gemma3 1B/4B/12B/27B,6k)E2E | [`weak_model_6k_analysis.md §1`](weak_model_6k_analysis.md) | GX10 `results.json` 全 N=100 驗證 | ✅ 權威 |
| ~~Mid-tier 主表(舊)~~ | ~~[`fc_sh_has_pair_main_table.md`](fc_sh_has_pair_main_table.md)~~ | 07-01 早期 recompute | ⚠️ **SUPERSEDED**(數字與 crosstab v4 有 ±2 殘差 + 標籤錯位,見 §5;僅保留 LCA / vanilla mem0 兩列供引用)|

**單一規則**:任何進 body 的 mid/strong 數字**一律引 crosstab v4**;weak 引 weak_model_6k_analysis §1;LCA / vanilla mem0(crosstab 不含)引舊主表。**其餘檔案的數字若與此衝突,以本檔為準。**

---

## §1 方法命名對照字典(跨檔命名混亂,先鎖死)

同一個變體在不同檔有不同名字,這是數字對不上的主因之一。**canonical 名 = 左欄**:

| Canonical 名 | 定義(query-time 路徑)| crosstab.md 標籤 | fc_sh 舊表標籤 | experiment.md 標籤 |
|:--|:--|:--|:--|:--|
| **ours (main)** | (S,P) struct 分群 → P3 LLM 補救 → argmax(**無 P5**)| `ours` | `ours-no-P5` | `ours (main)` |
| **ours (full)** | main **+ P5** conflict-type 分類(appendix)| `ours (+P5)` | `ours`(full P3+P5)| `ours (+P5)` |
| **ours (struct)** | (S,P) struct → argmax（**無 P3、無 P5**）| `ours (no P3)` | `ours-struct` | `ours (no P3)` |
| **ours (p3-only)** | P3 LLM over top-K → argmax（**無 (S,P) routing**）| `ours (no struct)` | `ours-p3-only` | `ours (no struct)` |
| (b) mem0+P1 | P1 held-fixed + mem0 write-time destructive | `(b) mem0+P1` | `(b) mem0+P1` | `(b) mem0+P1` |
| (a) vanilla mem0 | mem0 native extraction + destructive | — | `(a) vanilla` | `(a) vanilla mem0` |
| Zep | decoupled write-time labeling(k=10)| `Zep (k=10)` | `Zep` | `Zep` |
| LCA | gpt-4o-mini full-context,無記憶 | — | `LCA` | `LCA` |

> ⚠️ **最容易錯的一組**:`ours (struct)` 在 crosstab 叫 `ours (no P3)`;`ours (p3-only)` 在 crosstab 叫 `ours (no struct)`。命名相反,對照時務必查此表。

---

## §2 Table A — Mid-tier 主表（gpt-4o-mini × 3 lengths,has_pair EM）

**Row = method,Col = length**。分母:6k=74 / 32k=65 / 64k=66。**Bold = 每欄最佳**。↑ 愈高愈好。單次 deterministic run(temp 0),無 error bar。**來源:crosstab v4**(LCA / vanilla 來源:fc_sh 舊表,crosstab 未含)。

| Method | 6k ↑ | 32k ↑ | 64k ↑ |
|:--|--:|--:|--:|
| **ours (main)** = struct+P3+argmax | 69/74 (93.2) | 57/65 (87.7) | **60/66 (90.9)** |
| **ours (full)** = main+P5 *(appendix)* | 68/74 (91.9) | 55/65 (84.6) | **60/66 (90.9)** |
| ours (struct) = struct+argmax *(ablation)* | 67/74 (90.5) | 52/65 (80.0) | 58/66 (87.9) |
| ours (p3-only) = P3+argmax *(ablation)* | **71/74 (95.9)** | **58/65 (89.2)** | 58/66 (87.9) |
| LCA (long-ctx, no memory) | 65/74 (87.8) | 46/65 (70.8) | 38/66 (57.6) |
| Zep (k=10) | 46/74 (62.2) | 33/65 (50.8) | 36/66 (54.5) |
| (b) mem0+P1 | 34/74 (45.9) | 25/65 (38.5) | 34/66 (51.5) |
| (a) vanilla mem0 | 0/74 (0.0) | 2/65 (3.1) | 2/66 (3.0) |

> **注**:body 主表建議只留 `ours (main)` + 4 baselines(LCA / Zep / mem0+P1 / vanilla);`ours (full)` 與另兩個 ablation 變體移至 §4 ablation 表。此處全列以便 reconcile 對照。

---

## §3 Table B — Backbone spectrum（6k,**HEADLINE Figure 1 來源**,has_pair EM %,N=74）

> **★ 這是 thesis-first 的頭條圖來源**:同一長度(6k)橫跨完整 6-tier backbone(1B → gpt-4.1-mini),呈現「ours 相對現有派的 gap 隨 backbone 判斷力增強而收斂」的可證偽預測。gpt-4.1-mini × 6k 為**待補欄**(2026-07-06 規劃補跑 ours-main / mem0+P1 / Zep)。

**Row = method,Col = backbone tier**（由弱到強)。**Bold = 每欄最佳**。來源:weak(1B–27B)= weak_model_6k_analysis §1;mid(4o-mini)= crosstab v4 6k 欄;**strong(4.1-mini)= 待補**。

| Method | 1B | 4B | 12B | 27B | 4o-mini | **4.1-mini** |
|:--|--:|--:|--:|--:|--:|--:|
| **ours (main)** = struct+P3 | 25 (34) | **54 (73)** | **73 (99)** | **70 (95)** | 69 (93) | ⛔ *no_p5 待跑* |
| ours (struct) = struct only | **29 (39)** | **54 (73)** | **73 (99)** | 65 (88) | 67 (91) | ☐ *(future)* |
| ours (p3-only) = no (S,P) | 7 (9) | 26 (35) | 46 (62) | 27 (36) | **71 (96)** | ☐ *(future)* |
| (b) mem0+P1 | 0 (0) | 0 (0) | 44 (59) | 36 (49) | 34 (46) | **56 (76)** |
| (a) vanilla mem0 | — | 0 (0) | 32 (43) | 28 (38) | 0 (0) | — |
| Zep (k=10) | 12 (16) | 17 (23) | 43 (58) | 35 (47) | 46 (62) | **46 (62)** |

> **4.1-mini 6k 補跑現況(2026-07-07 驗證)**:mem0+P1 **56/74 (76%)**、Zep **46/74 (62%)** 已確認(aggregated EM,per-qid 重算待 crosstab 核對)。**ours-main(no_p5)尚未跑 6k**——目前只有 ours-FULL(+P5)= **61/74 (82%)**〔plain `unified` 目錄〕。頭條圖「ours」線全 backbone 用 no_p5,**故需補跑 `ours no_p5 @ 4.1-mini 6k`**(P1 抽取 cache 已由 full run 建好,補跑只走 query 端,便宜)。**gap 收斂已可見**:ours−mem0 於 6k 從 4o 的 +35pp → 4.1 的 +6pp(暫用 full 61)。

> 格式 `count (%)`,分母固定 74。`—` = 未跑;`☐ 待補` = 本輪規劃補跑。
> **預期方向(依 64k 已觀察外推,見 Table C)**:4.1-mini 欄 ours-main 與 (b) mem0+P1 的 **gap 應收斂**(64k 上該 gap 從 4o 的 +39pp 崩至 −3pp)→ 完成「gap 隨 backbone 增強而收斂」的 6k 完整曲線。**這是預期,不是已知;補跑後以實測為準。**
> **caveat(誠實揭露)**:weak-tier(1B–27B)為 **per-backbone gemma extraction**、mid/strong(4o/4.1-mini)為各自模型跑整條 pipeline;跨 backbone 的**絕對值**混了抽取品質 + 解析品質,但**同一 backbone 內 ours vs baseline 的 gap 是抽取 held-fixed 下的乾淨量**(見 §3 附註「為何 gap 是乾淨的」)。詳見 weak_model_6k_analysis §0。

**§3 附註 — 為何「gap」是這張圖裡乾淨的量(方法論守則)**:跨 backbone 的絕對 EM 不可直接比(抽取品質不同);但在**每個 backbone 內部**,ours 與 (b) mem0+P1 **共用同一份該 backbone 的 P1 抽取**(held-fixed),故 `gap = ours − mem0` 在該 backbone 內把抽取因素消掉,只反映「query-time 解析 vs write-time commit」的差異。**因此頭條敘事應鎖定 gap 的 across-backbone 趨勢,而非絕對線的斜率。**

---

## §4 Table C — Strong-tier 檢驗（64k,gpt-4o-mini vs gpt-4.1-mini,has_pair EM %,N=66）

**Row = method,Col = backbone**。來源:crosstab v4 `[4.1-mini]` 列。Zep 另報 sEM(verbose format 診斷,見 style_rules §10.3b F4)。

| Method | 4o-mini EM | 4.1-mini EM | 4.1-mini sEM |
|:--|--:|--:|--:|
| **ours (main)** | **60/66 (90.9)** | 53/66 (80.3) | 54/66 (81.8) |
| ours (full) *(appendix)* | **60/66 (90.9)** | 51/66 (77.3) | 51/66 (77.3) |
| ours (struct) *(ablation)* | 58/66 (87.9) | 52/66 (78.8) | 52/66 (78.8) |
| ours (p3-only) *(ablation)* | 58/66 (87.9) | 27/66 (40.9) | 28/66 (42.4) |
| (b) mem0+P1 | 34/66 (51.5) | **55/66 (83.3)** | **55/66 (83.3)** |
| Zep (k=10) | 36/66 (54.5) | 23/66 (34.8) | 50/66 (75.8) |

> **caveat**:strong-tier 僅 64k 單點(gpt-4.1-mini × 6k/32k = future work);D-flag benchmark bug @ 64k = 2/66 qid(qid 18/20,`gt_seq < old_seq` argmax 邏輯不可能對),影響 ours (main) −1pp,誠實列 caption。

---

## §4B Table D — Zep bi-temporal KU-resolution decomposition（gpt-4o-mini,has_pair）

> **為何獨立一表**:Zep 的文字 pool-state ~98% PP-Both、零鑑別(見 `matcher_specification.md` §3.4)。Zep 的 KU 行為只能讀 bi-temporal 欄位。本表把 canonical Zep E2E(§2/§4 的 62.2/50.8/54.5)**分解**為 4 桶(handoff-verified)。
> **canonical 產生**:`python analysis/classify_zep_ku_resolution.py`。**機制與判讀**:[`zep_ku_resolution_bitemporal.md`](zep_ku_resolution_bitemporal.md)。**圖**:`figures/F_zep_ku_resolution_6k_32k_64k.png`。**narrative 掛點**:[`../narrative_experiment_evidence/E-B_zep_ku_selfassessment.md`](../narrative_experiment_evidence/E-B_zep_ku_selfassessment.md)。

| length | Resolved-Correct | Resolved-Backward | **Additive-NoKU** | Other-Ambiguous | overall acc（= §2/§4 canonical）|
|:--|:--|:--|:--|:--|:--|
| 6k | 17 (23%), acc 88% | 22 (30%), acc 36% | **29 (39%)**, acc 69% | 6 (8%) | 46/74 = **62.2** |
| 32k | 6 (9%), acc 100% | 2 (3%) | **50 (77%)**, acc 44% | 4 (6%) | 33/65 = **50.8** |
| 64k | 11 (17%), acc 100% | 0 (0%) | **49 (74%)**, acc 41% | 5 (8%) | 36/66 = **54.5** |

> NotBothExtracted(6k 0 / 32k 3 / 64k 1)未列(≤5%,檢索 miss 非 KU 決定)。**一致性**:4 桶 + NotBothExtracted 正好 partition canonical has_pair 集,各桶 EM 加總 = overall acc。
> **引用信心**:Additive-NoKU(headline,保守下界)> Resolved-Correct(handoff+高 acc)> Resolved-Backward 單一數字(matcher over-match 敏感)。

---

## §5 對不上清單（reconcile ledger,供下次 recompute 核對）

| # | Cell | crosstab v4(canonical)| fc_sh 舊表 | 差 | 判定 |
|:--|:--|:--|:--|:--|:--|
| D1 | ours (main) 6k | 69/74 | 67/74(標 `ours-no-P5`)| +2 | 舊表 superseded;±2 單次噪音 + 07-01 早期 run |
| D2 | ours (main) 32k | 57/65 | 55/65 | +2 | 同上 |
| D3 | ours (struct) 6k | 67/74 | 69/74(標 `ours-struct`)| −2 | 同上 |
| D4 | ours (struct) 32k | 52/65 | 51/65 | +1 | 容許內 |
| D5 | ours (p3-only) 6k | 71/74 | 68/74 | +3 | **>噪音**;以 crosstab v4 為準,下次 recompute 核對 |
| D6 | ours (p3-only) 32k | 58/65 | 57/65 | +1 | 容許內 |
| D7 | ours (full) 6k | 68/74 | 69/74(標 `ours`)| −1 | 容許內 |
| D8 | (b) mem0+P1 6k | 34/74 | 33/74 | +1 | 容許內;crosstab 為準 |

**結論**:除 **D5(p3-only 6k,差 3)**外,全部落在單次 deterministic run 的 ±2-3 容許區間(temp 0 下 OpenAI server bf16 抖動,CLAUDE.md §3.3 已記錄)。**行動**:body 一律引 crosstab v4;下次跑 recompute 時特別核對 D5。

---

## §6 尚缺 / optional 加固（非「能否論述」的擋路項,列 future work）

| 缺口 | 現況 | 對論述的影響 | 補跑成本 |
|:--|:--|:--|:--|
| gpt-4.1-mini × 6k / 32k | 只有 64k | 強端「gap collapse」目前是**單點**;補齊 → 3-length curve,防「64k 特例」攻擊 | ~$0.4 / +1.5hr(**本輪不跑**)|
| weak-tier × 32k / 64k | 只有 6k | on-device 主張目前只在 6k;6k 已足支撐 backbone-gap 核心論點,可誠實列 future work | GX10 wave(暫停)|
| vanilla mem0 × 3 lengths(4o)| 只 6k floor | 次要 baseline;(b) 已足代表 destructive | 低 |
| vanilla mem0 @ gemma-1B | 缺 | 次要 | 低 |

---

*本檔為 step 1(客觀展示)的 canonical 引用來源。step 2(observation / implication)寫在 [`../narrative/experiment.md`](../narrative/experiment.md),但其數字必須回引本檔。*
