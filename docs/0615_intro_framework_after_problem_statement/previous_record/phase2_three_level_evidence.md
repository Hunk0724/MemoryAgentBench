# Three-Level Evaluation Evidence: vanilla mem0 vs ours (FC-SH 6k/32k/64k)

> 建立:2026-06-21　範圍:FactConsolidation **SH**,6k/32k/64k,top-100 retrieval。
> 對應 [phase2_spec.md](phase2_spec.md) §5,佐證 [intro_zh.md](intro_zh.md) 的 narrative arc。
> 評估皆以 **query-directly-relevant** 的 GT(gt_new / gt_old / gt_single)為準。
> 一致對齊標籤:`build_sh_analysis.py`(官方 coverage 對齊,6k/32k/64k 同一套)。

---

## 0. 一句話結論

> **KU 答對 = 把送進 inference 的 context 收斂成「只剩新版(new_only)」。** vanilla 在 write-time 賭一次破壞性更新,賭錯就**不可逆地**卡在 0%-state;ours 保守保留全部 + query-time **按需**收斂,所以 has_pair EM 從 27/37/42% 拉到 88/78/62%。

---

## 1. Setup / 對照組

| | write-time | query-time | store(送進 inference 的來源) |
|---|---|---|---|
| **vanilla mem0** | 破壞性 ADD/UPDATE/DELETE(LLM 判斷+執行) | 無 resolution | 已被破壞性更新的 store,top-100 raw |
| **ours phase0** | conservative ADD + (S,P) triple(無 cross-item 判斷) | 結構分群 + 時序 argmax | 保守 store,top-100 → 結構解析 |
| **ours phase2** | 同 phase0 | 結構 + **LLM 動態分群** + 時序 | 保守 store,top-100 → 完整解析 |

backbone/embedder/檢索/inference prompt/scorer 全部相同,唯一差異 = memory-side。

---

## 2. Level 1 — Retrieval Evaluation（top-100）

每題分類 query-relevant GT 是否被檢索:has_pair → {both / new_only / old_only / neither};no_conflict → single 是否檢索到。

| | store 點數 | has_pair: both / new_only / old_only / neither | no_conflict 檢索到 |
|---|---|---|---|
| 6k vanilla | **156** | 7% / 24% / **26%** / **43%** | 50% |
| 6k ours | **455** | **97%** / 1% / 1% / 0% | **96%** |
| 32k vanilla | **1101** | 3% / 34% / **29%** / **34%** | 63% |
| 32k ours | **2310** | **82%** / 5% / 11% / 3% | 94% |
| 64k vanilla | **2179** | 9% / 32% / **21%** / **38%** | 56% |
| 64k ours | **4580** | **67%** / 2% / 17% / 15% | 74% |

**讀法 / 佐證 intro:**
- **Store 縮水 = 不可逆刪除**:vanilla store 僅 ours 的 34% / 48% / 48% —— write-time 永久刪掉約一半到三分之二事實。
- **has_pair:vanilla 不可逆留下錯版本**。`old_only`(刪新留舊,21–29%)+ `neither`(都刪,34–43%)= **vanilla 59–69% 的衝突對,新事實已不可逆遺失**。ours 67–97% 為 both(可救)。
- **關鍵語義差異**:同樣是 `old_only`/`neither`,vanilla = 新事實**不在 store**(不可逆);ours = 新事實**仍在 store、只是沒進 top-100**(retrieval recall miss,**可救**:加大 k / Path B 結構檢索)。ours neither 隨長度 0→3→15% = 檢索瓶頸,非資訊損失。
- **vanilla 連單一事實也誤刪**:no_conflict 僅檢索到 50/63/56%(LightMem §5.6 自承的失效);ours 96/94/74%。

---

## 3. Level 2 — Resolution Evaluation（query-time 處理後）

核心:**L1=both（兩版都在手）→ L2 是否乾淨收斂成 new_only**(= 移除舊版)。

| len | L1=both 對數 | phase0 clean_rate | **phase2 clean_rate** | phase2 殘留 both |
|---|---|---|---|---|
| 6k | 72 | 61% | **75%** | 25% |
| 32k | 53 | 57% | **83%** | 15% |
| 64k | 44 | 77% | **91%** | 5% |

phase2 解析後 has_pair 終態分布:6k = new_only 74% / both 24% / old 1% / neither 0%;32k = 72/12/12/3;64k = 62/3/17/18。

**讀法 / 佐證:**
- **query-time 按需解 KU 有效**:兩版都在手時,phase2 乾淨移除舊版 75–91%。
- **LLM 分群(phase2)明顯勝純結構(phase0)** +14/+26/+14pp,把 F2-split(同事實不同 (S,P))殘留 both 救回 new_only(6k 28→18、32k 22→8、64k 9→2)。
- **零附帶傷害**:no_conflict `L2_kept == L1_retrieved`(25=25 / 33=33 / 25=25),解析從不誤刪單一事實。
- **規模化殘餘失敗在 retrieval 非 resolution**:64k phase2 終態的 both 僅 3%(解析近完美),失分主要是 old_only 17% + neither 18%(檢索沒撈到新版)→ Path B 施力點。

---

## 4. Level 3 — 最終狀態 → EM（因果鏈）

每題以「送進 inference 的最終 context 狀態」對 exact_match 交叉表(has_pair):

| 最終狀態 | EM 率(跨 mode/長度,高度一致) |
|---|---|
| **new_only** | **~100%**(6k 18/18·45/45·55/55;32k 22/22·46/47;64k 20/21·40/41) |
| **both** | **~40–65%**(LLM 無法可靠選新版,序號已剝離) |
| **old_only** | **~0%**(0/19·0/8·0/14…) |
| **neither** | **~0%** |

has_pair EM(三長度):

| | 6k | 32k | 64k |
|---|---|---|---|
| vanilla | 27% | 37% | 42% |
| phase0 | 82% | 68% | 58% |
| **phase2** | **88%** | **78%** | **62%** |

**讀法:** EM 幾乎完全由最終狀態決定 → KU 答對 = 收斂成 new_only。**both(~50%)→ new_only(~100%)** 就是 query-time resolution 的價值被量化;vanilla 卡在 old_only/neither(0%)**無法下游補救**。vanilla 的 new_only 也 ~100% EM(判對時有效),問題是衝突題只判對 25–32% 且判錯不可逆。

整體 EM(含 no_conflict,benchmark):vanilla 37 / 51 / — → phase0 87 / 77 / 62 → **phase2 91 / 84 / 65**。

---

## 5. 三層合一(寫進 paper 的機制論述）

```
L1  vanilla 破壞性 → 59–69% 衝突對新事實不可逆遺失(old_only/neither)
    ours 保守保留 → 67–97% both(可救)
        │
L2  ours query-time 按需:both → new_only(phase2 75–91%),零誤刪
        │
L3  new_only ~100% EM · both ~50% · old_only/neither ~0%
    ⇒ 收斂成 new_only 即答對;vanilla 卡 0%-state 不可逆
```
→ KU 的可靠性不再取決於單一次 write-time 判斷,而是「保守保留 + query-time 按需收斂」。

---

## 6. 建議圖表清單(slides / paper)

| # | 名稱 | 佐證 | 圖型 | 軸 / 內容 | 用途 |
|---|---|---|---|---|---|
| **F1** | Store shrinkage | L1 不可逆刪除 | grouped bar | x=長度;bar=ours vs vanilla 的 store 事實數(455/2310/4580 vs 156/1101/2179) | slides 動機頁、paper 小圖 |
| **F2** ★ | has_pair retrieval 組成 | L1 不可逆 vs 可救 | **stacked bar**(vanilla vs ours × 長度) | 每條 100%,堆疊 both/new_only/old_only/neither;配色:可救(綠:both,new_only)vs 不可逆/失(紅:old_only,灰:neither) | **主圖**(slides + paper);一眼看出 ours 一片綠、vanilla 破碎紅灰 |
| **F3** | L1→L2 resolution 轉換 | L2 query-time 解 KU | before/after stacked bar 或 Sankey(ours phase2) | 左 L1(both 大)→ 右 L2(new_only 大),per 長度;或 grouping clean_rate phase0 vs phase2 bar | slides(解 KU 的價值)、paper |
| **F4** ★ | 狀態 → EM | L3 因果 | bar(4 條) | x=最終狀態(new_only/both/old_only/neither);y=EM 率;~100/~50/~0/~0 | **因果證明小圖**(slides + paper);決定性 |
| **T1** ★ | 主結果表 | 整體 | table | 行=vanilla/phase0/phase2;列=6k/32k/64k 的 ALL(+has_pair/no_conflict) | **paper 主結果表** |
| F5(選) | no_conflict 檢索率 | L1 連單一事實也被刪 | line/bar | x=長度;ours vs vanilla 的 single 檢索率(96/94/74 vs 50/63/56) | paper 補充 |

**slides 精簡版**:F1(動機)→ F2(L1 不可逆)→ F3(L2 解 KU)→ F4(L3 因果)→ T1(結果)。一條 narrative 五張。
**paper**:全部 + 各層完整 table(§2/§3/§4)。

★ = 最核心,優先做。

---

## 7. 重現

```bash
conda activate MABench
python docs/0615_intro_framework_after_problem_statement/scripts/build_sh_analysis.py {6k,32k,64k}
python docs/0615_intro_framework_after_problem_statement/scripts/analyze_l1_retrieval.py
python docs/0615_intro_framework_after_problem_statement/scripts/analyze_l2_resolution.py
python docs/0615_intro_framework_after_problem_statement/scripts/analyze_l3_state_em.py
```
輸出:`analysis/results/phase0/l{1,2,3}_*.json`。store:`...stores/qdrant_gpt4o_512_openai_{rerun,phase2}__factconsolidation_sh_{L}`。
