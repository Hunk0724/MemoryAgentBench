# MemoryAgentBench 論文實作文件索引

本資料夾收錄論文實作所有實驗細節、方法重點。讓未來不論誰來查,都能在分類資料夾下快速找到對應內容。

> **與 `analysis/` 的分工**:`analysis/` 收實驗腳本與短期 session note,`docs/` 收**穩定的、會被論文引用的**文件。新文件預設放這裡。

---

## 📂 分類資料夾

### `baseline_methods/` — Baseline 方法分析
對手方法(mem0/mem0g、HippoRAG-v2、Zep/Graphiti 等)的系統架構、衝突偵測機制、論文 vs 實作對齊度。

- [baseline_methods_paper_vs_impl.md](baseline_methods/baseline_methods_paper_vs_impl.md) — mem0g vs Zep/Graphiti vs HippoRAG-v2 三方法架構比較 + 論文/實作對齊度評估 + 學術論述策略

### `ground_truth/` — Ground Truth 對應機制
MQuAKE → FC-SH/MH 題目 → 對話歷史 → hop-level GT 的完整 alignment pipeline。

- [mquake_alignment_guide.md](ground_truth/mquake_alignment_guide.md) — 對話歷史結構、衝突對來源、per-hop 對應流程、各長度覆蓋狀況

### `experiments/` — 實驗規劃與執行
pilot 計畫、log schema、run 紀錄。

- [chunk_size_convention.md](experiments/chunk_size_convention.md) ⭐ 各 method × task 的 chunk_size 規則(mem0=4096 統一,HippoRAG/FC=512)
- [pilots/mem0_mem0g_pilot_plan.md](experiments/pilots/mem0_mem0g_pilot_plan.md) — 6k mem0/mem0g × 5 Gemini × 2 chunk size pilot 計畫
- [pilots/2026-05-29_LCA_model_selection.md](experiments/pilots/2026-05-29_LCA_model_selection.md) — 5 個 Gemini LCA × FC-MH 6k 對比,選定 `gemini-3.1-flash-lite` (GA) 為 backbone
- [pilots/SESSION_2026-05-24_mem0_mem0g_setup.md](experiments/pilots/SESSION_2026-05-24_mem0_mem0g_setup.md) — Session note + revert 指南
- [log_schema.md](experiments/log_schema.md) — 三層 log(ingest events / retrieve events / final results)結構

### `infrastructure/` — 基礎設施
Neo4j、Vertex AI、Gemini 配置。

- neo4j_setup.md(待寫)
- gemini_vertex_config.md(待寫)

### `paper_draft/` — 論文草稿
論文核心數據與敘事素材。

- [lca_backbone_ctx_sweep.md](paper_draft/lca_backbone_ctx_sweep.md) ⭐ LCA(trivial baseline)× FC-MH × 4 ctx length 主結果 + paper §6.3/§7 narrative anchor
- 既有檔(open_questions.md, paper_narrative.md, paper_narrative_experiments.md, references.md)

---

## 📄 既有頂層文件(尚未分類,日後考慮歸入)

- [method_design_v2.0.2_spec.md](method_design_v2.0.2_spec.md) — 我方法 v2.0.2 spec
- [method_v2.0.2_framework.xml](method_v2.0.2_framework.xml)
- [B_remove_hyperedge_design.md](B_remove_hyperedge_design.md)
- [C_v2_chunk_rebuild_design.md](C_v2_chunk_rebuild_design.md)
- [v1_experiment_plan.md](v1_experiment_plan.md)
- [engineering_todos_v2.0.2.md](engineering_todos_v2.0.2.md)
- [hardware_request_6k.md](hardware_request_6k.md)
- [insight_discussion.md](insight_discussion.md)
- [chat_discussion_context_2026-05-26.md](chat_discussion_context_2026-05-26.md)
- [PROVENANCE.md](PROVENANCE.md)

---

## ✏️ 寫作慣例

1. 所有文件用**繁體中文**
2. 程式碼引用一律用 `[file.py:42-50](relative/path/to/file.py#L42-L50)` 格式
3. 跨文件引用用 `[[name]]` 風格(指向 docs 內其他 markdown)
4. 文件目的、建立日期、最後更新放在開頭 frontmatter
5. 每個分類資料夾的 README/index 可選,但若該資料夾超過 5 個檔案,**必須**寫一個 index

---

## 🔗 相關位置

- 實驗腳本與分析:[analysis/](../analysis/)
- 論文方法核心程式:[methods/](../methods/)
- agent 主流程:[agent.py](../agent.py)
- baseline 方法(vendored):[mem0/](../mem0/), [methods/hipporag/](../methods/hipporag/), [methods/zep.py](../methods/zep.py)
- 外部 reference(Graphiti / mem0 upstream):`/home/yhchiang/graphiti/`, `/home/yhchiang/mem0/`
