---
name: project_research_core_claims
description: "ours vs mem0g 的兩個核心主張 + 研究定位 + 優先 TODO,接下來研究的主軸"
metadata: 
  node_type: memory
  type: project
  originSessionId: e0f4a0fa-ba97-4e33-bdc8-bb87cd9d4113
---

接下來研究主軸:**ours(HippoRAG-v2 + Phase 2 + PropRAG borrow)vs mem0g**(已放棄 mem0 對照)。完整文件在 `MemoryAgentBench/docs/paper_draft/research_core_claims_TODO_2026-06-01.md`。

**兩個核心主張**:
- 主張一:mem0g write-time 衝突偵測,候選池(graph G4 = entity×≤100 triple)隨 context 長度爆 → 越長越不準(scaling 主張;6k 單點 ours 31 < mem0g-as-is 41,要靠下滑斜率)。
- 主張二:mem0g 記憶結構只能 1-hop 鄰域檢索 → 越多跳越差(1-hop 是建構期限制,非一行 Cypher;真結構限制 = entity resolution 弱/同-chunk-only 關係/無 PPR)。

**研究定位**:
- 工程:忠實 vendor PropRAG 的 `BeamSearchPathFinder` 當衝突候選池,別再自寫半成品 beam(L=3 死穴)。
- 貢獻:衝突偵測拆成「LLM 只做語義分組 + deterministic timestamp 仲裁」;用 mem0g `DELETE_RELATIONS_SYSTEM_PROMPT` as-is 當 baseline 做 controlled ablation。

**⚠️ 嚴謹警示**(務必處理,呼應 [[feedback_research_rigor_pipeline_alignment]]):
- 「用 timestamp 而非 LLM 猜 recency」**非原創**——Zep/Graphiti 已用 bi-temporal valid_at/invalid_at 做 write-time 仲裁。新意只能 framing 在 query-time + chain-scoped。
- "twins" 要改成 N-way 衝突組(一事實可被更新多次),timestamp 仲裁 = group 內 argmax。
- mem0g detection F1 還沒在我們框架測,別沿用 mem0 的 42。

對手 mem0g 的完整方法流程(ingestion/query/inference,逐行驗證)整理在 `MemoryAgentBench/docs/paper_draft/mem0g_architecture_reference.md`。相關背景見 [[reference_fc_mh_diagnostic]]。
