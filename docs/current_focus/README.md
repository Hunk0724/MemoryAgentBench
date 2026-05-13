# Current Focus — 現在實作 v1 method 會反覆翻的 5 份文件

這個目錄全是 symlink, 點進去就是真檔。canonical 位置仍在原處(symlink 不破壞 cross-reference)。

## 必讀(由淺到深)

| 檔案 | 主用途 | 看哪節最先 |
|---|---|---|
| [`motivation_narrative.md`](motivation_narrative.md) | 三系統觀察 + 兩 claim + 衝突機制必要性 evidence | §1 PureChain ladder, §2.A OracleClean, §2.B V1/V2/V3, §4.3 detection × EM |
| [`method_v1_spec.md`](method_v1_spec.md) | v1 三 Phase 設計, falsifiable assertions, 執行順序 | §1 三 Phase 對照, §3 切入點, §5 assertions, §6 Step 0-5 |
| [`claude_chat_method_design_experiment.md`](claude_chat_method_design_experiment.md) | 跟 chat 討論的設計 rationale, KG code-side details | §B.1 程式碼端對應, §B.7.2 discoverability asymmetry, §B.7.2.bis C5 |
| [`MIGRATION.md`](MIGRATION.md) | 環境重建 + §11 GB10 上 v1 執行計畫 + §12 baseline integrity | §11 v1 plan, §12.2 raw_chunks 灰色地帶 |
| [`INDEX.md`](INDEX.md) | analysis/ 目錄總覽 | 開頭 |

## 還要查的(由本目錄之外)

- [`docs/v1_experiment_plan.md`](../v1_experiment_plan.md) — 今天動工的 integrated plan(monitoring + 橋接 + 實驗清單)
- [`docs/hardware_request_6k.md`](../hardware_request_6k.md) — 硬體需求量化說明
