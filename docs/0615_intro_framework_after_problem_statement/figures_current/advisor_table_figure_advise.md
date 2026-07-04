請大家畫圖不要用excel或用html-based的output，請用：
Matplotlib 是最核心的工具，官方也明確定位它可用來產生 publication-quality plots，並支援輸出多種格式。
Seaborn 則是基於 Matplotlib 的高階統計視覺化工具，適合快速畫出比較漂亮的統計圖。
SciencePlots 是 Matplotlib 的論文風格樣式套件，主打 scientific papers、presentations、theses 的圖表格式。
plotnine 則是 Python 版 grammar of graphics，語法接近 R 的 ggplot2。

1. 另外請圖不要過度用色彩，而是用黑白印出來都可以清楚呈現為主體思考。
2. 有一些文字太長要用縮寫，在caption再寫上(xx stands for ...)就好。
3. 其實長條圖不是很好的圖，如果有趨勢，會看不出來；如果不是有趨勢，不如考慮用table