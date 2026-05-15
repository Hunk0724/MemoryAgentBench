LLM Agent 記憶系統演進與 HippoRAG-v2 動態更新架構藍圖
======================================

本文件彙整了目前前沿 LLM Agent 記憶系統（Zep, EMG-RAG, AriGraph, Mem0, LightMem）在「記憶衝突偵測與知識更新」上的機制差異，並據此提出將 HippoRAG-v2 升級為具備 Agentic 動態更新能力之系統架構藍圖。

一、 五大 Agent 記憶典範比較矩陣
--------------------

主流 Agent 記憶系統已超越傳統 Rule-based（如單純比對三元組的 S、R、O）的限制，全面轉向依賴 LLM 的「語意與時序推理」來解決衝突。

| **記憶典範** | **代表系統** | **核心哲學** | **衝突偵測與解決機制 (Workflow)** | **適用場景** |
| --- | --- | --- | --- | --- |
|   覆寫更新派      (In-place Update)   |   `Mem0`      `EMG-RAG`   | 記憶庫必須是乾淨且唯一的真實來源 (Single Source of Truth)。 | **Write-time 決斷**：新資訊寫入時，LLM 審查關聯記憶，直接下達 CRUD (Add/Update/Delete) 指令覆寫舊狀態。 | 需要高度擬人化、偏好明確且檢索負擔小的 Agent。 |
|   時間保留派      (Temporal Retention)   | `Zep` | 記憶是有生命週期的狀態機，舊知識是過期而非錯誤。 | **雙時態失效**：LLM 判定語意互斥後，不刪除資料，而是關閉舊知識的「有效時間視窗」，開啟新知識的視窗。 | 需要時間感知能力、能進行歷史回溯與狀態比較的系統。 |
|   延遲鞏固派      (Deferred Consolidation)   | `AriGraph` | 模擬人類長短期記憶機制，容忍短期混亂以求長期一致。 | **情節記憶緩衝**：新資訊先存入短期日誌 (Episodes)，累積後再由 LLM 回顧時序，批次重構全域的「世界模型」圖譜。 | 在複雜虛擬環境中持續探索，需要極高容錯率的 Agent。 |
|   輕量追加派      (Append-Only)   | `LightMem` | 極致的運算效率，將衝突解決推遲至生成階段。 | **Reader-Resolution**：小模型快速擷取重點並純追加寫入。檢索時將新舊矛盾一併提取，交由大模型的 Context Window 當下判斷。 | 資源受限、需要極高吞吐量與處理即時長文本流的對話。 |

* * *

二、 HippoRAG-v2 Agentic 記憶更新架構設計
-------------------------------

HippoRAG-v2 原生具備 **Dense-Sparse Integration（保留文本上下文）** 與 **Synonym Edges（語意連結）** 的圖譜特性，極度適合導入 Agentic 更新機制。為了解決多跳（Multi-hop）推理路徑上的知識更新問題，我們設計了兩階段的演進藍圖。

### 階段一：V1 混合式架構 (MVP 版)

**核心策略：Write-time 輕量標記 + Query-time 動態過濾**，避免在寫入時窮舉全域圖譜導致算力爆炸。

*   **Write-time（寫入階段）：**
    
    1.  **時間戳記寫入**：所有新增的 Passage Nodes 與 Triples 強制綁定時序資料。
        
    2.  **局部 Agent 審查**：利用原生 `Query-to-Triple` 找出 1-hop 內的相似節點，並結合其背後的 Passage 原始文本進行精準的語意衝突判定。
        
    3.  **覆寫邊界 (Supersede Edges)**：若發生衝突，不刪除舊節點，而是建立 `[Superseded_By]` 系統邊界，將舊節點標記為 `Stale`。
        
*   **Query-time（查詢階段）：**
    
    1.  **時間感知機率漫遊 (Time-Aware PPR)**：修改 PPR 轉移矩陣，當機率擴散遇到 `[Superseded_By]` 邊界時，阻斷流向舊知識的權重，強制水流匯聚至最新節點。
        
    2.  **Agentic 邏輯安檢 (Chain-of-Thought Review)**：在最終生成前，引入輕量 Agent 審查 PPR 撈出的 Top-N Passages，剔除推理鏈中互相矛盾或過期的文件，確保最終 Prompt 絕對乾淨。
        

### 階段二：V2 精準演進版 (解決 V1 盲區)

V1 架構雖然能確保回覆的時效性，但面臨兩個潛在痛點：(1) 局部偵測會漏掉深層衝突；(2) 剔除整篇 Passage 會誤殺同文章中其他有用的新知識。V2 將引入以下機制進行優化：

*   **非同步圖譜巡檢 (Asynchronous Consolidation)：**
    
    借鑑 `AriGraph` 的概念，佈署背景垃圾回收 Agent。在系統低負載時，主動掃描圖譜進行深度的多跳邏輯檢查，補齊漏網的衝突標記。
    
*   **導入 PropRAG (命題級別更新)：**
    
    將 HippoRAG-v2 底層的粗粒度段落節點 (Passage Nodes) 替換為 `PropRAG` 提出的**原子化命題 (Propositions)**。當發生衝突時，系統僅精準替換或標記「單一失效命題」，同篇文本提取出的其他正確命題仍可安全參與 PPR 漫遊，徹底解決上下文誤殺問題。
