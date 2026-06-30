---
name: FC-MH multi-hop diagnostic session
description: MemoryAgentBench FC-MH 雙階段研究 (Phase 1 detection × Phase 2 packaging),9 個 oracle + 5 個 hypotheses + prospective design,整合總覽在 fc_mh_research_overview.md
type: reference
originSessionId: 9e90e8ef-a3e4-44a7-9cd8-1304e9218d22
---
對 MemoryAgentBench 的 FC-MH (Conflict_Resolution / FactConsolidation multi-hop) 任務做了完整的 oracle 診斷實驗 (HippoRAG-v2 × Gemini 3.1 Flash-Lite × chunk_size=512 × 6k context × 100 題)。

## 研究框架 (兩階段)

| 階段 | 任務 |
|---|---|
| Phase 1: Write-time detection | 寫入時偵測新舊知識、誰 supersede 誰 |
| Phase 2: Query-time handling | 根據 Phase 1 標記，決定怎麼把新舊知識傳給 LLM |

**核心 thesis**: FC-MH 需要 Phase 1 + Phase 2 都做對才能解；過去 production 系統 (Zep/Mem0/HippoRAG-v2) 沒人同時做好。

## 入口檔案 (依優先序讀)

1. `MemoryAgentBench/analysis/fc_mh_research_overview.md` — **整合總覽 (2026-04-29)**，含 §0 Executive Summary (兩階段架構 + 進度 + caveat + prospective design)，是接手者第一個讀的檔
2. `MemoryAgentBench/analysis/SESSION_2026-04-28_diagnostic_summary.md` — session 完整敘事與 prompt rigor 修正過程 (深挖細節)
3. `MemoryAgentBench/analysis/fc_mh_hypotheses.md` — H1–H5 working hypotheses + 嚴謹度審計
4. `MemoryAgentBench/analysis/next_phase_design_space.md` — (A) detection × (B) packaging 維度與 D1–D5 detection 方向
5. `MemoryAgentBench/analysis/diagnostic_findings.md` — paper-ready 數據
6. `MemoryAgentBench/analysis/diagnostic_methodology.md` — 9 個實驗的方法論

## 核心數字 (FC-MH 100 題, Gemini 3.1 Flash-Lite)

Perfect Phase 1 條件下 Phase 2 不同 channel 的上限:
- A1 baseline: **23%** (Floor)
- OA2 retrieval-filter (orig prompt): **55%** (Layer 1 universal target)
- OA2 + intermediate-trailer prompt: **83%** (Layer 2 QA-only)
- RPT (Section A/B + MUST, FC-overfit): **68%** (reference ceiling, 不可部署)
- Sim-OB chain-only: **98%** (absolute ceiling)

## 主要結論

1. **Filter > soft annotation** 在所有 prompt 條件下成立 (+19 ~ +35 pp on MH)
2. **OA2 retrieval-filter 不改 prompt 即可 +32 pp** → Layer 1 universal recommendation
3. **LLM 純多跳推理不是瓶頸** (Sim-OB 98%)，剩 15 pp 是 retrieval 雜訊不是 conflict
4. **RPT 是 FC-overfit 不可部署**，只能當 in-context FC-aware reference ceiling
5. **Trailer 對 context cleanliness monotonic**: very-noisy +3pp / mid-noisy +12pp / clean +28pp

## 方法論 caveat (重要)

本次研究大量使用 modified prompt (intermediate trailer) + (A)/(B)/(C) 條件來 probing LLM reasoning，但 probing prompt 本身就是 intervention，所以 H1–H5 的「LLM-side recall」是 upper bound 而非真實黑盒 inference 行為。

→ 下一階段改用 **prospective hypothesis-driven design**：實驗前寫死預測值、inference prompt 不動，比較實際 vs 預測 EM。詳見 overview §0.6。

## 下一步優先順序

1. **Phase 1 (★ 最高優先)**: Zep + Mem0 用 Gemini 重跑 + 量化 detection precision/recall — 確認 production 系統 gap (paper main motivation 的 evidence)
2. **Phase 2**: imperfect-detection robustness ablation (對 OA2 加人為 noise 看 degradation 曲線) — paper 從 oracle ceiling 推到 production claim 的關鍵橋樑
3. **Phase 3**: hybrid filter + annotation channel design
4. **Phase 4**: 從 HippoRAG-v2 加 detection layer (D1–D5)，對應 Phase 2 的 robustness 曲線位置
5. **Phase 5**: generalization (32k/64k/262k context, chunk_size=4096, 換 LLM)

## 重跑指南

resume-safe，可直接讀 `MemoryAgentBench/analysis/results/diagnostic/*.json`，不要刪 partial output。Vertex AI 環境變數: `GOOGLE_CLOUD_PROJECT=fc-mh-494213`, `LOCATION=global`。

當使用者繼續這個方向的研究時，先讀 overview §0 再決定下一步。
