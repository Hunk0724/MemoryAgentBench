# GX10 weak-model 6k — 初步觀察 + 待討論素材(2026-07-05)

> **狀態:preliminary / 待討論**。confirmed 的 E2E 數字已進主表([../../handoff/experiment_results_shared.md]),嚴謹歸因已進 [`../paper_current/results/pool_acc_crosstab_gemma_6k.md`](../paper_current/results/pool_acc_crosstab_gemma_6k.md)。本檔放「還沒定位到 body 某節」的觀察 + 兩張 Res-vs-EM 圖 + b 機制深挖。

## 1. GX10 6k 已驗證結果(gemma,全 07-04 本 session)

| method | 1B | 4B | 12B | 27B | 一句話 |
| :-- | :-: | :-: | :-: | :-: | :-- |
| **ours_struct**(EM/Res/ov) | 29/43/49 | 54/48/79 | 73/68/99 | 65/69/90 | 方法端 Res 單調升,27B EM 掉=reader override |
| **ours_no_p5**(struct+P3) | 25/43/42 | 54/50/79 | 73/68/99 | **70/71/94** | +P3 能力梯度:1B −4 害、4B/12B 中性、27B +5(Res↑ 且壓 override)|
| **b = mem0 破壞性更新**(EM/ov) | 0/5 | 0/10 | 44/64 | 36/53 | 見 §3;弱模型崩、且非單調 |
| **ours_p3_only**(LLM only) | 2✅ | ⛔ | ⛔ | ⛔ | 舊 4b/12b/27b 是 num_ctx 假象、需重跑;1B 真崩 |

**兩軸分解(struct 權威 per-query)**:抽取軸 `new_absent` 1B 18→4B 10→12B 0→27B 0;reader 軸 `drag/override`(pool 乾淨仍錯)1B 16→4B 1→12B 0→27B 7(**U 形**:弱=無能、中=忠實、強=參數 override)。

## 2. 待討論的兩張圖(依 evaluation_protocol §4.2,暫不進 body)

| 圖(在 `../figures_current/`)| 為何 need_discuss | 怎樣才 body-ready |
| :-- | :-- | :-- |
| `F_p3_backbone_6k`(P3 的 Res-vs-EM)| §4.2 明言 Resolution 單獨不足以歸因(both/neither 也能答對);嚴謹版是 §4.2 cross-tab | 若團隊決定要「主 method(no_p5)的 Res+EM 對照圖」,與 F_struct_backbone 並列;否則以 cross-tab 取代 |
| `F_struct_vs_b_overall_6k`(ours vs mem0,**overall** EM)| 主指標是 **has_pair** EM(非 overall);指定 baseline 主圖是 `F_backbone_gap`(全 method,未畫)| 改繪 has_pair EM 版、或併入 F_backbone_gap |

## 3. ★ b = mem0 破壞性更新:為何是「不正常」的 0/5 · 0/10 · 44/64 · 36/53

**設定**:b 共用 ours 的 P1 extraction(抽取 held-fixed),差別只在**寫入層** = mem0 native `ADD/UPDATE/DELETE`(write-time 由 backbone LLM 判);query 時**無 resolution**(raw top-K)。

### (a) 1B / 4B = 0/74 — write-time update LLM 崩壞(非 num_ctx)
- 輸入很小(每 chunk ~600 tok,store 從沒長大)→ **沒碰 context 上限**;產出是**合法 JSON、內容卻是 prompt 範例**。
- **1B store = 5 × `"Name is John"`**(mem0 update prompt 的 few-shot 範例字串);**4B store = 完全空(0 筆)**。
- → 弱模型無法遵循 mem0 的 update 指令,**照抄範例 / 擺爛**。加大 num_ctx 救不了。

### (b) 12B / 27B 能跑,但仍遠輸,且 **27B < 12B 非單調** — 兩個原因
掃 dest store 的 has_pair 版本狀態:

| b store | 總點數 | new_only | old_only | both | neither |
| :-- | :-: | :-: | :-: | :-: | :-: |
| 12B | 313 | 9 | 2 | **63** | 0 |
| 27B | 261 | 10 | **5** | 58 | 1 |

- **關鍵反直覺**:mem0「破壞性」更新其實**大多沒刪**——12B/27B 對多數 has_pair **兩版都留(both 63/58)**,因為 mem0 update LLM **沒把反事實新舊值認成矛盾**(當成不同 fact 各自 ADD)。
- **原因 1(write-time)**:27B update **更激進地刪**(261<313 點、`old_only` 5>2)→ **更常把新版刪掉留舊版**。強模型對 mem0 的「找矛盾刪舊」指令執行得更果斷,反而在反事實上刪錯邊。
- **原因 2(read-time)**:b **無 query-time resolution** → 「both」直接進 pool → **27B reader 以參數先驗 override 挑舊版**(與 struct 的 27B override 同源)。
- 兩者疊加 → 27B(36)< 12B(44)。

### (c) 對照 ours — 這正是我們贏的地方
- ours 的 store 也常是「both」(保守寫入不刪),但 **query-time 確定性把 both→new_only**(temporal argmax);b 沒這步,把「挑哪版」丟給 reader → 受 override 傷。
- 6k overall:ours_struct **49/79/99/90** vs b **5/10/64/53**(每 backbone +44/+69/+35/+37)。**write-time commit KU 在弱模型災難性且不可逆;defer 到 query-time 全 backbone 穩健。**

## 4. 待辦(GX10)
- **p3_only 4B/12B/27B 用 num_ctx=8192 重跑**(舊檔 07-01/02 是 pre-fix num_ctx 假象);預期弱模型真崩、12B/27B 正常(對照 Mac gpt-4o-mini p3_only 71/74)。
- **weak-model 32k / 64k**(`F_backbone_gap` 需要)。
- cross-tab 若要出圖:stacked bar(pool-state × Acc)候選,先討論是否進 body。
