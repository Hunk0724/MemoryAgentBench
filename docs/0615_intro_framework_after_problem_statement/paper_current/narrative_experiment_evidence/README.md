# narrative_experiment_evidence/ — 寫 Experiments 章節的唯一入口

> **為什麼有這個資料夾**:`figures_current/` 有 ~30 張圖、`results/` 有十幾份 md,新舊敘事混在一起 → 寫論述時找不到「現在這條論證鏈**用得到**的那幾張」。這裡把它們**收斂**成一包:論證鏈骨架 + 每個節點的 canonical 圖/表 + 明確的「別用」清單。
> **怎麼用**:照 §A 的論證鏈,一節一節看 §B 的 evidence map,圖在 [`figures/`](figures/),數字一律回引 [`../results/objective_data_consolidated.md`](../results/objective_data_consolidated.md)(canonical)。
> **狀態**:2026-07-07 更新。thesis-first 定案(backbone spectrum 當 Figure 1)。**gpt-4.1-mini 6k/32k 已補跑並驗證**(6k:main 66/mem0 56/Zep 46;32k:main 51/Zep 20)。**E-A 頭條圖待重生**為單一 6k 6-tier(見 §C + §E-2 決策)。

---

## §A 論證鏈骨架(thesis-first)

**中心因果主張(整章都掛在這句上)**:
> 我們的優勢 = 用**確定性規則保證乾淨 pool**;現有派靠 **LLM 判斷**(mem0 靠 write-time judge、Zep/both-present 靠 reader 挑版)才能乾淨,而 LLM 判斷品質**隨 backbone 變弱而崩**。因此「乾淨 pool」在弱 backbone 上最值錢——弱 reader 沒能力從混雜 pool 挑對版本,只能靠 pipeline 先把 pool 清乾淨。

| 節點 | 要證明的 claim | 讀者看完該相信 | 資料狀態 |
|:--|:--|:--|:--:|
| **開章 framing** | 重述 intro 末可證偽預測為經驗主張,宣告本章四問結構 | 每張表都在回答 thesis 逼出的一個問題 | — |
| **E-A ★ 頭條** | ours vs write-time 派的 gap 隨 backbone 判斷力**變弱放大、變強收斂** | 優勢是**範式性質**(conditional on backbone),非刷分 | 🟢 資料齊(6k 6-tier);⚠ 圖待重生 |
| **E-B 機制** | E2E gap **可歸因於 pool state**(乾淨 vs 汙染),非 reader 挑選力 | 是**因果**非相關;乾淨 pool 正是弱 reader 最需要的 | 🟢 完整 |
| **E-C 方法內部** | 確定性 (S,P)+argmax 是 workhorse;LLM 元件(P3)自己也 capability-gated | **遞迴論證**:連我方 LLM 元件都逃不過「弱 backbone LLM 判斷脆弱」 | 🟢 完整 |
| **E-D 責任邊界** | KU 解析只負責一切片;剩餘失分落在正交軸(抽取/reader override/D-flag) | 我們在**誠實劃界**,非宣稱解決一切 | 🟢 完整 |

**節點接榫**:E-A(何時)→ 逼出 E-B(為何:pool state)→ 逼出 E-C(我方哪個 component 做出乾淨 pool)→ 逼出 E-D(剩下沒解掉的是誰的責任)。

---

## §B Evidence map(節點 → 該用的圖 + 該引的表)

### E-A ★ 頭條:backbone-judgment 預測
- **Figure(頭條,已重生 2026-07-07)**: [`figures/F_backbone_spectrum.png`](figures/F_backbone_spectrum.png) — **THE Figure 1**:**單一 6k panel、6-tier**(gemma3-1B→gpt-4.1-mini),3 method(ours / Zep / mem0+unified extract)。ours 全 tier 皆勝;mem0 於 1B/4B=0、於 gpt-4.1-mini 追至 76%,gap 從 +73pp(4B 峰)收至 +13pp(4.1)。標題「gap widens on weak, collapses on strong @ 6k」。
- **誠實揭露 companion(必配)**: experiment.md **§4.3.4 Table 4c** — 6k/32k/64k × (4o vs 4.1) 的 gap 總表,揭露 32k/64k + 強 backbone 下 gap 收斂**甚至反轉**(64k mem0 反超 −3pp)。頭條乾淨、此表誠實,兩者搭配。
- **Table**: `objective_data_consolidated.md` §3 Table B(6-tier @ 6k)+ §4 Table C(強端 64k)。
- **敘事守則**:鎖 **gap 趨勢**,不是絕對線斜率(跨 backbone 絕對值混抽取品質);x 軸是 ordinal tier;誠實揭露非嚴格單調(12B 峰、27B 因 reader override 略降)。

### E-B 機制:gap 從何而來 = pool state
- **Figure(主)**: [`figures/F_pool_diagnostic.png`](figures/F_pool_diagnostic.png) — 3 method × 3 length,(a) pool state share +(b) E2E 100%-stacked 依 pool state 拆解扣分。★核心,一秒讀出「mem0 頂端固定 ~40% 是 OldOnly/Missing、Zep 卡 PP-Both、ours 幾乎全轉正確」。
- **Figure(length-robustness)**: [`figures/F_main_gpt4omini_6k_32k_64k.png`](figures/F_main_gpt4omini_6k_32k_64k.png) — mid-tier 主表的 3-length 視覺(ours flat vs LCA 崩)。
- **Figure(appendix,6-method)**: [`figures/F_pool_diagnostic_ablation.png`](figures/F_pool_diagnostic_ablation.png) — 含 ours 三變體的完整版。
- **Table**: `objective_data_consolidated.md` §2 Table A(mid 主表)+ [`../results/pool_acc_crosstab.md`](../results/pool_acc_crosstab.md)(canonical cross-tab,mid 3-length + 強端 64k)。
- **Rigor backing**: [`../results/matcher_audit_gpt4omini_64k.md`](../results/matcher_audit_gpt4omini_64k.md)(matcher v4 0 confirmed FN)。
- **Zep 支線(pool-state 對 Zep 不適用,改用 bi-temporal)**: [`E-B_zep_ku_selfassessment.md`](E-B_zep_ku_selfassessment.md) — Zep ~98% PP-Both 零鑑別 → 改用自身 KU-resolution 4 桶解釋 E2E(Additive-NoKU 主導 39→77→74%、Resolved-Correct acc 88–100%、6k Backward=world-prior)。
  - **Figure**: [`figures/F_zep_ku_resolution_6k_32k_64k.png`](figures/F_zep_ku_resolution_6k_32k_64k.png)(2-panel:(a) 分桶 share×length、(b) 各桶 EM×length;line 圖、B&W-safe)。
  - **Table(canonical)**: [`../results/objective_data_consolidated.md`](../results/objective_data_consolidated.md) **§4B Table D**(4 桶 × 3 length,EM 加總 = canonical Zep E2E)。
  - **機制/判讀**: [`../results/zep_ku_resolution_bitemporal.md`](../results/zep_ku_resolution_bitemporal.md)。

### E-C 方法內部:誰在做事 = ablation
- **ours 機制檔(canonical,ablation↔code 對映的 source)**: [`../results/ours_ku_mechanism.md`](../results/ours_ku_mechanism.md) — faithful write(全版本保留、write 零跨筆 LLM)→ query-time resolve(struct (S,P)+argmax / P3 identity / P5 conflict-type);§4 確定性 vs LLM 分界、§5 四變體↔開關對映、§6 三派對照、§7 誤差正交軸(接 E-D)。
- **Figure(P3 gate,weak)**: [`figures/F_struct_vs_p3_overall_6k.png`](figures/F_struct_vs_p3_overall_6k.png) — struct 之上加 P3 的淨 Δ 隨 backbone 變號(1B −7 → 12B 0 → 27B +4)。★核心遞迴論證。
- **Figure(mid ablation)**: [`figures/F_ours_ablation_gpt4omini_6k_32k_64k.png`](figures/F_ours_ablation_gpt4omini_6k_32k_64k.png)。
- **Figure(weak ablation)**: [`figures/F_ours_ablation_gemma3_6k.png`](figures/F_ours_ablation_gemma3_6k.png)。
- **Table**: `objective_data_consolidated.md`(ours 變體列)+ [`../results/weak_model_6k_analysis.md`](../results/weak_model_6k_analysis.md) §1/§3(6-tier ablation + 12B/27B cross-tab)。

### E-D 責任邊界:error modes / case studies
- **Baseline 機制檔(canonical,error-mode 歸因的 source)**:
  - [`../results/mem0_ku_mechanism.md`](../results/mem0_ku_mechanism.md) — mem0 write-time coupled update(prompt I/O + per-chunk 組裝 + 四操作 apply + M1/M2 失效路徑 + hallucinated-id drop + 同 chunk 行為)。**pool_state 對 mem0 有效**,故 mem0 error modes **E-B 就能說**(結果層),E-D 引此檔談機制層(M1 world-prior / M2 coupled-update)。
  - [`../results/zep_ku_resolution_bitemporal.md`](../results/zep_ku_resolution_bitemporal.md) — Zep 支線(pool_state 不適用,改 bi-temporal;見 E-B Zep 支線)。
  - **⚠ 何時補 direct 證據**:`mem0_event_taxonomy` 靠 event-log elimination,**看不到** NONE decision / raw prompt / 幻覺 id。若 reviewer 追問可靠性,或某 case 要秀 raw LLM decision → 設 `MEM0_CAND_LOG_DIR` 重跑(dump update_prompt+raw_response+parsed_actions+hallucinated_ids,`mem0/memory/main.py:429-458`,~$0.3/30min)。**非 E-B/E-D 說明 error modes 的前置**,有空或講不清再補。
- **Figure(reader override,pool 乾淨仍答錯)**: [`figures/F_crosstab_1227_6k.png`](figures/F_crosstab_1227_6k.png)(12B/27B pool-state,new_only✗ = override 桶)+ [`figures/F_struct_backbone_6k.png`](figures/F_struct_backbone_6k.png)(Resolution vs EM 分離,27B EM<Res)。
- **Case study md(canonical)**:
  - [`../results/case_studies_64k.md`](../results/case_studies_64k.md)(gpt-4o-mini)
  - [`../results/case_studies_gpt41mini_64k.md`](../results/case_studies_gpt41mini_64k.md)(強端 regression / Zep verbose / D-flag)
  - [`../results/weak_model_case_studies_6k.md`](../results/weak_model_case_studies_6k.md)(**Case F 招牌**:同題四 backbone,失敗點沿 pipeline 後移)
  - [`../results/mem0_event_taxonomy_gt4o.md`](../results/mem0_event_taxonomy_gt4o.md)(Case A:mem0 write-time failure M1/M2 分類)

---

## §C 待補數據(擋 E-A 完整、不擋 E-B/C/D)

| 缺口 | 影響節點 | 補跑後動作 |
|:--|:--|:--|
| ~~gpt-4.1-mini × 6k~~ **✅ 已補**(main 66 / mem0 56 / Zep 46)| E-A | objective_data §3 已填;**剩:重生 F_backbone_spectrum**(§E-2 定 panel 形式後)|
| gpt-4.1-mini × 32k(mem0+P1 一格)| E-A/§4.3.3 | main 51 / Zep 20 已跑,**mem0 32k pending** → 補完 §4.3.3 Table 4b 32k gap |
| weak × 32k/64k(optional)| E-A robustness | 誠實列 future work,不擋投稿 |

> **run checklist**(補跑時看):① 主方法 `MEM0_P5_SKIP=1`(=no_p5=main,別跑成 full);② 先跑 `ours` 再跑 `b`(held-fixed extraction cache);③ 抽取設定與 4.1-mini 64k 保持一致。

---

## §D ⛔ 別用(舊敘事 / superseded — 收斂時的減法)

這些屬 intro v6 **已移除**的舊框架(asymmetry / recoverability / bank-recall / L1-L2 / 262k),**不進現行 thesis-first 論述**:

| 檔 | 屬於的舊敘事 | 處置 |
|:--|:--|:--|
| `F_bank_recall` / `F_em_vs_ceiling` / `F_ours_L1L2*` / `F_L1_state*` | 「recall ceiling / L1-L2 version-state」舊機制線 | 不用(機制已被 pool-state cross-tab 取代)|
| `F_ablation`(additive a→b→c)/ `F_robust_haspair`(262k)/ `F_overall` | 舊主結果框架 | 不用 |
| `F_recoverable` / `F_state_to_em` / `F_struct_vs_b_overall_6k` / `F_p3_backbone_6k` | 舊「可回復性 / 破壞性對比」線 | 不用(併入 E-A gap 敘事)|
| `F_backbone_gap_haspair_6k` | E-A 早期版(weak-only 4 method)| **被 F_backbone_spectrum 取代** |
| `F_main_gpt4omini_6k_64k` | main 舊 2-length 版 | 被 `F_main_gpt4omini_6k_32k_64k`(3-length)取代 |
| `results/fc_sh_has_pair_main_table.md` | 舊主表(07-01)| **SUPERSEDED**(見 objective_data §0);僅留 LCA/vanilla 兩列供引 |
| `results/weak_model_case_study.md` | 舊 weak 頭條(standalone Resolution)| 被 `weak_model_6k_analysis.md` 取代;機制段落仍可 backing |
| `figures_current/figure_captions.md` | 只 caption 了**舊圖** | 現行圖 caption 待重寫(寫 body 時補)|

---

## §E 三個尚待你決定的呈現取捨(寫作時拍板)

1. **main table 降級為 E-B 鋪陳**(Figure 1=spectrum 才是頭條)vs 保留獨立「main results」節?
2. ~~E-A 頭條圖 panel 形式~~ **✅ 已定(2026-07-07)**:**單一 6k 6-tier panel 為頭條**;64k 反轉移至 §4.3.4 Table 4c 誠實揭露(頭條乾淨 + 誠實 companion)。
3. **weak-tier caveat**(per-backbone gemma extraction)在圖上怎麼呈現——標在 caption 就好,還是 panel 分隔?
