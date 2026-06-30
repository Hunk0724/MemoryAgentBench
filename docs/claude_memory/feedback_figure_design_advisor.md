---
name: feedback_figure_design_advisor
description: 指導教授畫圖規範:用 matplotlib/seaborn/SciencePlots/plotnine(非 Excel/HTML);黑白可讀為主;長字縮寫+caption 註明;bar 不佳(趨勢用 line、無趨勢用 table)
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 3e0a308a-3986-4a05-bce2-da75bfd6d859
---

指導教授對論文圖表的明確要求(2026-06-28):

**工具**(不要 Excel、不要 HTML-based output):
- **Matplotlib** — 核心,定位於 publication-quality plots,支援多格式輸出。
- **Seaborn** — 基於 matplotlib 的高階統計視覺化,快速畫較漂亮的統計圖。
- **SciencePlots** — matplotlib 的論文風格樣式套件,主打 scientific papers / presentations / theses。
- **plotnine** — Python 版 grammar of graphics,語法近 R 的 ggplot2。

**配色**:**不要過度用色彩 → 以「黑白印出來也清楚」為主體思考**(靠 linestyle / marker / hatch / 灰階區分,不靠顏色)。

**標籤**:文字太長就用**縮寫**,在 **caption 註明 `(xx stands for ...)`**。

**圖型選擇**:**長條圖不是好圖** —— 有趨勢時 bar 看不出趨勢 → 用 **line**;沒趨勢時 → 不如用 **table**。

**Why:** reviewer 常黑白列印;要 publication-quality + 一致風格;清楚 > 花俏。
**How to apply:** 預設 matplotlib(+SciencePlots 樣式)、colorblind/grayscale-safe;**趨勢用 line、純數值/組成比較優先 table、真的分類 part-to-whole 才用 bar(且 grayscale-safe)、不用 pie(pie 只留簡報)**;長 label 縮寫 + caption 定義。延伸自 [[feedback_cheap_eval_during_validation]] 的研究工作規範;落地於 `docs/0615_.../scripts/make_*.py` 與 `figure_captions.md`。
