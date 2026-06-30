---
name: project_phase0_structural_result
description: "0615 framework 定版:P1 抽取+保守寫入+(S,P)結構+LLM分群+conflict-type+temporal resolution+raw-q檢索;FC-SH 32k EM 89%/has_pair 86%;方法階段性定版,轉做 baseline+廣度"
metadata: 
  node_type: memory
  type: project
  originSessionId: 3e0a308a-3986-4a05-bce2-da75bfd6d859
---

2026-06-20 起主軸(docs/0615_intro_framework_after_problem_statement;**目錄 writing_draft 已改名 `paper_draft&materials`**)。核心:KU 是 query-time 問題,寫入只保守保留全版本、**write-time 完全無 cross-item LLM 判斷**,誰是權威由 query-time **確定性 temporal argmax** 決定(對比 [[project_u5_conflict_resolution_axis]] 仍 write-time 分類)。

**定版 pipeline(2026-06-26)**:
- 寫入:**P1 統一抽取**(`use_unified_extractor`,source-based,取代舊 FC-tuned L2;FC-SH 32k 前5chunk vs 完美GT micro-recall 97.4%、數量比1.00)→ (s,p,o) triple + subject fallback(`methods/phase0_triple_extractor.py`)→ 保守 ADD +(S,P)倒排索引 + **batch embedding**(`mem0/memory/main.py` `_add_phase0_structural`,env `MEM0_ADD_MODE=phase0_structural`)。
- 查詢:**raw-question 檢索**(`agent.py:_retrieval_query()`,剝 qa 模板,ungated)→ top-100 → conditional routing → 結構分群 +(dynamic_pool)LLM identity 分群 → **3-way conflict-type classifier**(`CONFLICT_TYPE_PROMPT`,Cattan 2025,query-aware,**取代舊 per-predicate arity guard**)→ 僅 FRESHNESS 丟舊(NO_CONFLICT/COMPLEMENTARY keep)。env `MEM0_QUERY_MODE=phase2`,注入 agent.py(關掉 byte-identical)。

**定版結果 FC-SH 32k(ours,real benchmark)**:overall **89%** / has_pair **86%** / no_conflict 94%(前一版 L2+wrapped = 84/78/94;+5/+8pp,has_pair 提升來自 raw-q 救回 GT)。

**錯誤模式(32k,9題錯,無致命)**:A. (S,P)分群失敗 5題(predicate/subject 無 canonicalize,同義述詞 `is associated with` vs `...the sport of`)= **唯一主 lever**;B. **benchmark 標註錯誤 2題(q8/q9,排除)**;C. answer-LLM 2題。排除 benchmark 錯後 **has_pair=56/63=89%**。**retrieval 非瓶頸(可救率98%)、conflict-type健康(95.5% freshness)、temporal key 正確**。

**已推翻的舊認知**:(1) 「retrieval/Path B 規模瓶頸」**其實是 wrapped-query artifact**——benchmark 拿 qa 模板包裝後整段 query 做 embedding;改 raw-question 後 FC-SH 64k recall@100 79%→100%,**Path B/結構檢索不需要了**。(2) per-predicate arity guard 因 arity context-dependent 而棄,改 conflict-type classifier。(3) **「FC serial≠ordinal / 池子打亂」是錯的**:核對 HF 原文,FC 池**按 serial 排序**(serial 隨位置遞增)、chunk-ordinal 正確對應 recency。

**q8/q9 = benchmark 標註錯誤(非我方)**:FC 規則「larger serial = 答案」,但 q8/q9 的 gold 是**較小 serial**(London 707<Washington 1929;Rome 1291<Watertown 2016),gold 跟著真實世界走 → 違反自己規則 → 不可能答對。65 題 has_pair 中僅這 2 題如此。**我們的 ordinal 解析其實是對的**,不需 parse serial、不需特例。

**決策(2026-06-26)**:方法**階段性定版**,不再雕(canonicalization / serial 列 backlog,後續 run 若致命再回頭),**轉做廣度**:更多 benchmark/長度 + baseline。

**Baseline 三層**:Same family(mem0/Zep/LightMem)、Different family(long-context/RAG/MemGPT-letta/A-Mem)、Trivial(parametric-constant/random-among-retrieved/majority)。兩 regime:內部 ablation a/b/c 固定 P1 抽取;跨系統各原生抽取。

**核心 docs**:`experiment_plan.md`(roadmap+method/benchmark registry+Phase1-5)、`experiment_results.md`(只留定版結果+錯誤模式,舊 L2 數字移到 previous_record/)、`method_pipeline_and_prompts.md`(所有 prompt)、`methodology_materials.md` §10(公平性/工程)。figures(F1-F6/F_L1L2)**待用定版 data 重繪**。

**環境坑**:qdrant 必須 `on_disk:True`(否則跨 process 重開清空);conda env **MABench**;embedder OpenAI text-embedding-3-small(1536d)。fresh `p1_` caches self-populating(extraction/triple 命中重播、未命中回寫)。

**待跑(experiment_plan Phase1)**:ours 64k/262k/LongMemEval KU(各做錯誤模式總結)、vanilla mem0(原生+raw-q)、FC-SH 6k 三 arm 重跑、L1/L2/L3 以 P1+raw-q 重算 + 重繪 figures、官方 LongMemEval judge。
