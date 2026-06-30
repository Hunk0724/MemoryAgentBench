---
name: project_ku_taxonomy_battlefield
description: "KU 分兩類(A 明確更正/B newer-wins),我們戰場=Bucket B 隱式 recency;FC 主、LongMemEval+BEAM 泛化、MemBench 出界"
metadata: 
  node_type: memory
  type: project
  originSessionId: 3e0a308a-3986-4a05-bce2-da75bfd6d859
---

2026-06-23 收斂定錨。經四篇 paper + 各自 eval code 驗證,確立「我們探討的 KU 是哪種問題」。

**KU 分類(依「誰決定權威值」):**
- **Bucket B — 隱式 recency / newer-wins**:權威值=最新權威主張。**FC**(論文叫 Selective Forgetting,「newer = larger serial number, find the newest」,SubEM)、**LongMemEval**(問 "most recent",judge)、**BEAM**(original→update,刻意隱式、移除線索,judge)。
- **Bucket A — 明確使用者更正**:truth=明確更正 turn(「I just realized I need to correct myself…」),**recency 會答錯**(後續同屬性是雜訊)。只有 **MemBench**(多選題)。

**我們的戰場 = Bucket B。** 兩個 commitment 正是 B 的標準解:保守寫入(全版本保留)+ query-time temporal-argmax。
- **主結果 = FC**:recency 外顯成 serial number,直接對應我們 per-chunk `ordinal`,EM 最嚴、最受控。
- **泛化 = LongMemEval / BEAM**:自然 recency(timestamp/順序),judge 計分,真實對話。
- **MemBench(A)出界**:temporal-argmax 對它錯 → 明文 future work(correction-aware resolver),並當「為何要 keep-all + 可插拔 query-time 解析」的對比賣點。

**架構最深的理由(務必寫):keep-all 是必要不是方便** —— 同一 store 還要答 temporal-reasoning(問過去某時值,需舊版本);LongMemEval/BEAM 同時有 KU(133)與 temporal(133)。破壞性 write-time 覆蓋會毀歷史→temporal 無解。故必須保留全版本 + query-time 依問題決定取哪版。

**rigor 修正(收回先前過頭話):** SUT 只看到 raw NL turns(+role/time),`(rel,attr,value)`、`user_messages.json` 全是 oracle-only,不能拿來抽取;extraction 跨情境難做正是領域避開 KU 的原因 → 我們把 extraction 當[[project_phase0_structural_result]]之外的**正交前提**,不解它,同 benchmark 內固定前端、跨系統各用原生抽取。chunk 維持 512。

詳見 docs/0615_intro_framework_after_problem_statement/writing_draft/ku_taxonomy_and_scope.md。延續[[project_u5_conflict_resolution_axis]]與[[project_research_core_claims]]。
