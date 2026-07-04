# Style Rules — Tables / Figures / Observation / Discussion

> **來源**:濃縮 4 份 advisor 建議(見文末 §附錄)為單一參考。
> **用途**:Mac + GX10 兩台在做**分析、畫圖、寫表、寫 observation** 之前**必先讀一次**;paper_current 內所有新產出都要符合這裡。
> **底部** §10 是**當前實驗結果 landscape**(全局 sync 用),分析前先看數字。

---

## §1 Tools(禁忌先講)

- **✅ 用**:Matplotlib(核心)/ Seaborn(統計圖高階)/ SciencePlots(論文樣式)/ plotnine(ggplot 語法)
- **❌ 禁**:Excel、HTML-based output

---

## §2 B&W-safe 設計(印出來要看得清)

1. **不過度用色彩** — 黑白印出來仍要清楚
   - 主 method 用一個 accent color(green #009E73)
   - 其他方法用 greyscale(black / #555 / #888 / #BBB)
2. **hatch / linestyle / marker** 才是主要區分手段
   - bar:`""` / `"///"` / `"xxx"` / `"..."` / `"++"`
   - line:`"-"` / `"--"` / `":"` / `"-."`
   - marker:`o` / `s` / `^` / `D` / `v` / `*`
3. **長字用縮寫**,caption 補「XX stands for ...」

---

## §3 Chart type 選擇

| 資料特性 | 用什麼 | 為什麼 |
| :--- | :--- | :--- |
| **有趨勢(連續)** | **line** | 趨勢用長條看不出來 |
| **無趨勢(離散對比)** | **table** > bar | bar 差,直接列數字更清 |
| 離散類別但**必須比較幅度** | bar(hatch 區分)| 例如 backbone tier × method |
| **絕對禁忌** | **無** pie(paper) | pie 留給簡報,不進論文 |

---

## §4 Figure 必備元素

- ✅ **軸標 + 單位**:寫「Latency (ms)」,不寫「Latency」
- ✅ **Legend 區分系列**,顏色 colorblind-safe
- ✅ **多 run 標 error bar / shaded region**(mean ± std,3+ runs)
  - 目前 single deterministic run(gpt-4o-mini temp 0),**無 std 可畫,但 caption 要明講** "single deterministic run, no error bar"
- ✅ **Font ≥ 8pt**(print 後仍可讀)
- ✅ **圖面精簡**:只保留 axis label + legend + data label
- ✅ **判讀寫進 caption**(不寫圖上)

---

## §5 Caption 三段論(what / observation / implication)

**80-150 字,3-5 句**。範例(從現行 figure_captions.md):

> **Figure.** [WHAT] FC-SH `has_pair`,五種方法在四種 conversation-history length(6k-262k)的 exact-match accuracy(single deterministic run,無 error bar)。
> [OBSERVATION] ours 在所有長度皆最高、且幾乎不隨長度衰退(92→86→91→88%);而直接以 full context 餵 LLM 的 gpt-4o-mini 隨長度單調崩壞(88→31%),Zep 與 mem0+ours storage 居中且同樣下滑。
> [IMPLICATION] 這顯示 ours 的 KU 正確率對 history length 具 robustness,而依賴 full-context 或 write-time 更新的方法都隨規模惡化 → 我們的設計在長對話記憶情境更具 scalability。

**⚠️ 常見錯**:caption 只寫 what → reviewer 得回主文找答案 → 論文閱讀體驗差。

---

## §6 Table 設計(必備)

- ✅ **Row = method、column = dataset / metric**(不要反過來)
- ✅ **Bold 最佳、underline 次佳**
- ✅ 每個 metric 標 **↑ / ↓** 方向
- ✅ 多 run 標 mean ± std
- ❌ 不超頁寬,超寬拆 table 或轉 sideways

**範例好格式**(從 idea_for_figure-and-table-design.md):

| Method | CIFAR-10 Acc ↑ | ImageNet-1K Acc ↑ | Params (M) ↓ |
| :--- | ---: | ---: | ---: |
| ResNet-50 [He'16] | 93.6 ± 0.2 | 76.1 ± 0.3 | 25.5 |
| ViT-B/16 [Doso'21] | 95.1 ± 0.1 | 77.9 ± 0.2 | 86.4 |
| **Ours** | **95.8 ± 0.2** | **78.6 ± 0.2** | **31.2** |

---

## §7 Observation 寫法(三段式)

**Experiments 章節不能只列數字,要寫 observation** — 從 table/figure 抽出 pattern 並給 explanation。

- **What**:哪一欄、哪幾個 row、什麼 pattern
- **Why**:hypothesis(引 methodology / prior work)
- **Implication**:對後續實驗 / application 暗示什麼

**❌ 壞寫(純描述)**:
> "Table 3 shows our method achieves 92.3% on A and 88.7% on B. Baseline achieves 87.1% on A. Ours outperforms baseline on both datasets."

零 insight;reviewer 自己會看 table。

**✅ 好寫(pattern + hypothesis + implication)**:
> Table 3 顯示三個 pattern:
> (O1) Dataset A 的 gain(+5.2%)顯著大於 B(+3.3%)。假設源於 A 的 class 不平衡更嚴重(§4.1 long-tail ratio 28:1 vs B 的 9:1),而 §3.5 的 re-weighting 主要解 long-tail 問題;§4.5 進一步控制 imbalance 驗證此假設。
> (O2) 在 input length > 512 時,gap 開始拉大 → 支持 sliding-window attention 在長序列才顯出價值;短序列 application 預期 gain 較小。
> (O3) 方差 std 比 baseline 大 30% → 可能源於 policy network 對 seed 敏感;實作時用 ensemble 或 SWA。

每個 observation 都有 hypothesis + follow-up / caveat。

---

## §8 Discussion 應回答的 4 個問題

比 observation **抽象一階**:
1. What conditions work / not work
2. Failure case 長什麼樣、為什麼
3. Practitioner 的建議
4. Follow-up research 的建議

**⚠️ 誠實談 limitation**:reviewer 自己找出 limitation 才危險;明寫反而被視為誠實。

---

## §9 檔名 & 位置 convention

**Figure**:
- 主圖名:`F_<topic>_<detail>.{png,pdf}`(前綴 F_)
- 存位置:
  - 生產(scripts 產生):`docs/0615_.../figures_current/`
  - **進 paper body**:curated copy 到 `paper_current/figures/`(不指向 figures_current,防路徑漂移)
- 產生腳本:`docs/0615_.../scripts/make_<topic>.py`

**Table**(Markdown):
- 存位置:`paper_current/results/<topic>.md`
- 命名:主表 `fc_sh_*_main_table.md`;分析表 `<analysis>.md`

**Caption 集中**:`docs/0615_.../figures_current/figure_captions.md`(集中管理,產生新圖時更新該檔)

---

## §10 現行實驗結果 landscape(sync 用 — 分析前必看)

### 10.1 Mac Studio(gpt-4o-mini)

**已完成**:
- ✅ 6k / 32k / 64k × 4 ours variants(`full` / `no_p5` / `struct` / `p3_only`) = **12 cells**(post-9ced3c2)
- ✅ `(b) mem0+P1` × 3 lengths、`LCA`(gpt-4o-mini full-context)× 3 lengths、`Zep` × 3 lengths(**k=10 caveat**)

**進行中 / 待補**:
- ⏳ `(a) vanilla mem0`:目前只有 6k n=2 smoke,需 full 3 lengths
- ☐ Strong-model tier(**gpt-4.1-mini** 主 / gpt-4.1 次)全 cells

### 10.2 GX10(gemma3 backbones,via Ollama)

**已完成**:
- ✅ 6k × gemma3 {1B, 4B, 12B, 27B} × `ours_struct` + `ours_p3_only_no_struct`
- ✅ F_struct_backbone_6k(has_pair Res vs EM,四 backbone)
- ✅ F_struct_vs_p3_overall_6k(P3 ablation gradient)
- ✅ Resolution-per-query 分析(`analysis/results/resolution_per_query_6k_{1b,4b,12b,27b}.json`)

**進行中 / 待補**:
- ⏳ 32k / 64k weak-model
- ☐ 32k / 64k 全 4 methods(`ours_no_p5` 需 num_ctx 已修 8192)

### 10.3 E2E has_pair EM 主表(post-9ced3c2,Mac Studio gpt-4o-mini)

**Row = method / Col = length**(依 §6 convention);**bold 每列最佳**;**指標方向 ↑**:

| Method | 6k has_pair ↑ | 32k has_pair ↑ | 64k has_pair ↑ |
| :--- | ---: | ---: | ---: |
| ours (full P3+P5) | 68/74 (91.9%) | 55/65 (84.6%) | **60/66 (90.9%)** |
| ours (no_p5) | 69/74 (93.2%) | 57/65 (87.7%) | **60/66 (90.9%)** |
| ours (struct) | 67/74 (90.5%) | 52/65 (80.0%) | 58/66 (87.9%) |
| **ours (p3_only)** | **71/74 (95.9%)** | **58/65 (89.2%)** | 58/66 (87.9%) |
| (b) mem0+P1 | 34/74 (45.9%) | 29/65 (44.6%) | 27/66 (40.9%) |
| Zep (k=10 ⚠️) | 46/74 (62.2%) | 4/65 (6.2%) | 36/66 (54.5%) |
| LCA (long-ctx, gpt-4o-mini) | 65/74 (87.8%) | 46/65 (70.8%) | 36/66 (54.5%) |

**Zep 的 k=10 caveat**:與其他方法 k=100 不對稱,32k 全崩(4/65)是 k 上限直接後果(不是設計缺陷);Zep 建議未來加 chunk=4096 / k=100 補測。

**當前 open question**(尚未驗證):
- 上面的 E2E gap,**多少來自 pool state 差異**(pipeline 是否給對 gt_new)、**多少來自 answer LLM 猜對率**(pool 混雜時 LLM 挑對能力)?
- 這正是 **Tier 1 return_context × Acc cross-tab** 要回答的 → 見 `evaluation_protocol_main.md` §4.2

### 10.4 現有 figures 一覽(paper_current/figures/)

已進 paper_current 的 3 張:
- `F_ours_ablation_haspair.{png,pdf}` — Mac 3 methods × 3 lengths bar chart(主圖)
- `F_struct_backbone_6k.{png,pdf}` — GX10 weak-model Resolution vs EM
- `F_struct_vs_p3_overall_6k.{png,pdf}` — GX10 struct vs +P3 ablation gradient

**新畫圖必須遵循 §5 caption 三段論**;captions 存放 `docs/0615_.../figures_current/figure_captions.md`。

---

## §附錄 濃縮來源(4 份 advisor 建議)

- [`../figures_current/advisor_table_figure_advise.md`](../figures_current/advisor_table_figure_advise.md) — 3 條工具/色彩/類型建議
- [`../figures_current/figure_captions.md`](../figures_current/figure_captions.md) — 現行 8 張圖的 caption 樣本
- [`../figures_current/idea_for_figure-and-table-design.md`](../figures_current/idea_for_figure-and-table-design.md) — Caption 三段論 + Table 規則(必備元素、好/壞範例)
- [`../figures_current/idea_for_observation_and_discussion_writing.md`](../figures_current/idea_for_observation_and_discussion_writing.md) — Observation 三段式 + Discussion 4 問題(誠實 limitation)

**任何改動 → 同步更新本檔;本檔為 paper_current 內產出的品質準則,分析前必先讀。**
