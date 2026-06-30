# Agentic Memory 生態盤點(定位用參考)

> 用途:研究**定位**參考(見 [RESEARCH_CONTEXT.md](RESEARCH_CONTEXT.md) 第 3 節)。下表多數是**平台/工程型 repo,與我們的 KU 方法論正交**,不是直接競爭對手;收進來是為了能對審稿人說清楚「擁擠的 memory 生態裡,我們站在哪、不跟誰比」。
>
> ⚠️ 內容由 AI 協助整理(來源 StockWiki `ai-research` topic,截至 2026-06-29),stars/版本**請至 GitHub 原始來源親自驗證**,可能過時。

## 與我們研究的關係(先讀這段)

- **A 長期記憶平台**(cognee/mempalace/supermemory/honcho/openhuman):**最接近但仍正交**——它們是「系統/平台」,我們是「KU 的方法論」。可比的點:它們**如何處理事實更新與時序矛盾**(例:supermemory 宣稱「處理時序矛盾與過期」、mempalace 報 LongMemEval recall)。**這幾個是要去翻其 update 機制、判斷是否 destructive 的對象**;真正能對標 benchmark 的少。
- **B 工作記憶 / context・KV-cache**(headroom/LMCache/oMLX):**正交**(壓 token、重用 KV cache),不解 KU。
- **C 檢索記憶 / 向量・RAG**(turbovec/LEANN/cocoindex/PageIndex):**正交**(檢索底層),我們假設 retrieval 之上的 resolution。
- **D 程式碼記憶 / codebase 知識圖**(Understand-Anything/codegraph/graphify/codebase-memory-mcp):**完全正交**(coding agent 場景)。
- **E 研究/評測基準**(EvoArena/EvoMem):**這類才是該追的方法論/benchmark 線**——動態環境、patch-based 記憶、temporal update,與我們同題,值得引用與比較。

**定位結論**:我們不和「平台」比工程,而是在 **KU/temporal-fact-update 的方法論**這條窄線上,主打 non-destructive + query-time + weak-model-decomposed。related work 重點放 A 的 update 機制 + E 的方法論/benchmark。

---

## 📊 總覽

| 套件 | 層次 | ⭐ 累計 | 週增 | 授權 |
|------|------|--------:|------|------|
| [cognee](https://github.com/topoteretes/cognee) | 長期記憶 | 24.9k | 🔥 +5,519 | MIT |
| [mempalace](https://github.com/MemPalace/mempalace) | 長期記憶 | 55.5k | +1,984 | MIT |
| [supermemory](https://github.com/supermemoryai/supermemory) | 長期記憶 | 25.8k | +2,944 | — |
| [honcho](https://github.com/plastic-labs/honcho) | 長期記憶 | 4.4k | +708 | AGPL-3.0 |
| [openhuman](https://github.com/tinyhumansai/openhuman) | 長期記憶 | 9.0k | +9,000* | GPL-3.0 |
| [headroom](https://github.com/chopratejas/headroom) | 工作記憶 (context) | 41.8k | 🔥 +12,793 | Apache-2.0 |
| [LMCache](https://github.com/LMCache/LMCache) | 工作記憶 (KV cache) | 9.1k | 週榜#15 | MIT |
| [oMLX](https://github.com/jundot/omlx) | 工作記憶 (KV cache) | 14.0k | +1,513 | — |
| [turbovec](https://github.com/RyanCodrai/turbovec) | 檢索記憶 (向量) | 11.4k | 🔥 +6,863 | MIT |
| [LEANN](https://github.com/yichuan-w/LEANN) | 檢索記憶 (向量) | 11.6k | +632 | — |
| [cocoindex](https://github.com/cocoindex-io/cocoindex) | 檢索記憶 (索引) | 9.2k | +1,548 | — |
| [PageIndex](https://github.com/VectifyAI/PageIndex) | 檢索記憶 (RAG) | 30.1k | +3,991 | — |
| [codebase-memory-mcp](https://github.com/DeusData/codebase-memory-mcp) | 程式碼記憶 | 9.3k | 🔥 +4,212 (全站#1) | Apache-2.0 |
| [Understand-Anything](https://github.com/Lum1104/Understand-Anything) | 程式碼記憶 | 47.1k | 🔥 +25,612 (全站#2) | — |
| [codegraph](https://github.com/colbymchenry/codegraph) | 程式碼記憶 | 35.3k | 🔥 +15,909 | — |
| [graphify](https://github.com/safishamsi/graphify) | 程式碼記憶 | 67.1k | 🔥 +5,478 | — |

<sub>* openhuman:發布 3 天內從 0 → 9,000 stars。週增為入榜當週峰值,僅供相對參考。</sub>

---

## 🧠 A. 長期記憶 — 跨 session 持久化

> 核心:讓 agent 在多次 session 之間記住事實/偏好/上下文。**最接近我們、但仍是平台層**;要查的是它們的「事實更新/時序矛盾」處理是否 destructive。

- **cognee** `topoteretes/cognee` ⭐24.9k:知識圖譜引擎做跨 session 持久長期記憶;v1.2.0-dev1;MIT;相容 Claude Code/LangChain。
- **mempalace** `MemPalace/mempalace` ⭐55.5k:本地記憶系統(宮殿結構);**LongMemEval 96.6% raw recall**(宣稱免費開源最高);後端 ChromaDB/Qdrant/pgvector/SQLite;MIT。
- **supermemory** `supermemoryai/supermemory` ⭐25.8k:自動萃取事實、**處理時序矛盾與過期**、維護 user profile;Hybrid Search;~50ms。← **與我們 KU 最可能對話的點**。
- **honcho** `plastic-labs/honcho` ⭐4.4k:stateful agent 記憶基礎設施;背景推理 + 上下文查詢;AGPL-3.0。
- **openhuman** `tinyhumansai/openhuman` ⭐9.0k:Memory Tree(本地壓縮文件/郵件/聊天為 Markdown 知識圖);GPL-3.0。

## ⚙️ B. 工作記憶 — Context / KV-cache(正交)

- **headroom** `chopratejas/headroom` ⭐41.8k:context 壓縮層,60–95% token 節省;可逆壓縮(CCR);Apache-2.0。
- **LMCache** `LMCache/LMCache` ⭐9.1k:KV cache 跨 serving engine 持久重用;PyTorch Foundation;MIT。
- **oMLX** `jundot/omlx` ⭐14.0k:Apple Silicon 本地推理 + 分層 KV cache(RAM/SSD)。

## 🔍 C. 檢索記憶 — 向量 / RAG(正交,我們假設其之上)

- **turbovec** `RyanCodrai/turbovec` ⭐11.4k:Rust 向量索引(TurboQuant,免訓練);8× 壓縮;MIT。
- **LEANN** `yichuan-w/LEANN` ⭐11.6k:選擇性重計算取代永久嵌入(省 97%);100% 本地。
- **cocoindex** `cocoindex-io/cocoindex` ⭐9.2k:增量資料引擎(只處理 delta),毫秒級新鮮度。
- **PageIndex** `VectifyAI/PageIndex` ⭐30.1k:**無向量庫**的 reasoning-based RAG(LLM 遍歷分層樹);FinanceBench 98.7%。

## 🗂️ D. 程式碼記憶 — Codebase 知識圖(完全正交)

- **Understand-Anything** `Lum1104/Understand-Anything` ⭐47.1k:Tree-sitter + LLM 轉互動知識圖。
- **codegraph** `colbymchenry/codegraph` ⭐35.3k:預建 codebase 語意圖;token -25%、tool calls -62%。
- **graphify** `safishamsi/graphify` ⭐67.1k:AST + LLM 轉可查知識圖;每次查詢省 71.5× tokens。
- **codebase-memory-mcp** `DeusData/codebase-memory-mcp` ⭐9.3k:C 寫的 MCP server,158 語言,token -99%;Apache-2.0。

## 🔬 E. 記憶研究 / 評測基準(← 該追的方法論/benchmark 線)

- **EvoArena / EvoMem** `Aiden0526/EvoArena`(arxiv:2606.13681):動態環境 LLM agent 記憶演化基準;環境變化建模為漸進更新序列;**EvoMem = patch-based 記憶範式(以結構化更新歷史取代靜態快照)**;現有 agent 平均 39.6%,EvoMem 在 GAIA/LoCoMo +6.1%/+4.8%。**與我們 non-destructive + 更新歷史的想法同向,值得對讀。**

---

## 備註

- 商業對照(非 repo,僅比較中提及):**Mem0**($19–249/月)、**Zep**($25+/月)——即我們的 baseline 來源(會在 write-time 做 destructive update / invalidation)。
- 收錄門檻 = GitHub 週增 ≥ +500 stars 的高信號專案,**非全量掃描**;完整生態另查 awesome-list。
