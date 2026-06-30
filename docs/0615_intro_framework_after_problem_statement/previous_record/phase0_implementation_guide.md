# Phase 0 Method Specification & Implementation Guide

> **Two-Stage Knowledge Update Framework — Minimal Structural Version on Mem0**
> Conservative ADD + (S, P)-Indexed Memory with Temporal Resolution

---

## 0. 設計哲學與 Phase 0 範圍

### 0.1 核心哲學一句話

> Write-time 是純粹的 indexing service，不做任何跨 item 的 LLM judgment；所有需要 query context 的判斷推遲到 query-time；Phase 0 的 query-time 只做結構查詢與時序解析，不做 LLM conflict judgment。

### 0.2 基底實作選擇

本 Phase 0 建構在 **Mem0 codebase** 之上。理由：

- 團隊已有 Mem0 baseline 實作經驗，避免重寫 extraction / vector store / retrieval interface
- 對 paper baseline 對照有結構優勢：保留 full Mem0 (含 update logic) 跑同 benchmark，與 Phase 0 (改造版) 做直接 apples-to-apples 對比

### 0.3 Phase 0 涵蓋與不涵蓋

| 元件 | Phase 0 處理 | 備註 |
|---|---|---|
| Conversation → memory extraction | ✓ Reuse from Mem0 | 直接重用 Mem0 prompt |
| Triple extraction (S, P, O) | ✓ NEW, schema-free | 參考 TruthfulRAG (AAAI 2026) |
| Predicate canonicalization | ✗ Deferred | 由 §9 失敗指標觸發升級 |
| Entity resolution | △ Lightweight string normalize | 由 Mem0 user/agent context 取 |
| (S, P) inverted index | ✓ NEW | 並行 Mem0 vector store |
| Query analyzer | ✓ NEW (lightweight) | 抽 (S, P) 或返回 null |
| Hybrid retrieval | ✓ NEW | Union semantic + structural |
| Grouping by (S, P) | ✓ NEW, 純結構 | |
| Temporal resolution | ✓ NEW, argmax timestamp | |
| Answer generation | ✓ Reuse from Mem0 | |
| **Mem0 ADD/UPDATE/DELETE/NOOP** | ✗ **DISABLED** | 改為 pure ADD |
| Active / Archive 物理分層 | ✗ Single tier in Phase 0 | |
| Multi-hop traversal | ✗ Future work | |
| Valid time extraction | ✗ Future work | |
| Write-time relation classification | ✗ Phase 1 | |
| Query-time LLM conflict judgment | ✗ Phase 2 | |

### 0.4 Phase 0 研究問題

> 在純結構性 write-time 處理（schema-free triple + (S, P) indexing）配合純結構性 query-time 解析（hybrid retrieval + timestamp argmax）下，FC KU 任務的表現能比 vanilla semantic top-K 提升多少？失敗的部分集中在哪幾類？這些 failure modes 各自指向下一階段什麼設計需求？

---

## 1. Mem0 改造矩陣

### 1.1 Disable (in new branch)

| Mem0 element | 為什麼 disable |
|---|---|
| ADD / UPDATE / DELETE / NOOP 的 update decision LLM call | 違反 conservative commit；這是 cross-item judgment |
| Vector store 中對 existing memory 的覆蓋邏輯 | 純 ADD，不覆蓋 |
| 預設的 deduplication 機制 | Phase 0 不做 duplicate detection（留 Phase 1） |

### 1.2 Keep (intact)

| Mem0 element | 為什麼 keep |
|---|---|
| Conversation segmentation 規則 | Phase 0 不重新發明 |
| Atomic memory extraction prompt | Phase 0 不重新發明 |
| Embedding model 與 vector store 介面 | 直接重用 |
| 基本 retrieval prompt 結構 | 改造而非重寫 |
| Generation prompt | Phase 0 不做 conflict-aware generation |

### 1.3 Extend (NEW components)

| 新 component | 加在哪 | 目的 |
|---|---|---|
| Triple extractor | Memory extraction 之後 | 從每條 memory 抽 (S, P, O) |
| Lightweight identity normalizer | Triple extractor 之後 | 純字串 normalize |
| (S, P) inverted index | 並行 vector store | 結構查詢服務 |
| Query analyzer | Retrieval 之前 | 抽 query 的 (S, P) 或返回 null |
| Hybrid retriever | 取代 Mem0 預設 retrieval | Union semantic + structural |
| Group + temporal resolver | Retrieval 之後 | 按 (S, P) 分組 + argmax timestamp |

### 1.4 paper baseline 對照組

保留一個未改造的 Mem0 branch 跑「full Mem0」baseline，與 Phase 0 branch 做對比。**這是 paper 中跟 Mem0 的核心對照**：使用同個 codebase 確保比較公平，差異只在「destructive update vs conservative ADD + structural query」。

---

## 2. System Architecture

對應前面討論的視覺化：

- **Write-time pipeline** (LLM extract → LLM triple → string normalize → commit)
- **Storage layer** (vector index | metadata | (S, P) inverted index)
- **Query-time pipeline** (LLM analyze → hybrid retrieve → group + resolve → LLM generate)

整條 pipeline 中 LLM call 只在 4 個位置：write-time 的 extract 與 triple、query-time 的 analyze 與 generate。**所有 LLM call 都是 self-contained per-item 或 per-query，沒有 cross-item judgment**——這是跟 Mem0/LightMem/Zep 的根本區別。

---

## 3. Storage Schema

### 3.1 Memory Item 資料結構

```python
from dataclasses import dataclass
from typing import Optional, List
from datetime import datetime

@dataclass
class MemoryItem:
    memory_id: str                     # UUID
    text: str                          # 原始萃取文本
    embedding: List[float]             # dense vector (from Mem0's embedder)

    source_session_id: str
    source_utterance_range: tuple
    ingestion_timestamp: datetime      # Phase 0 唯一的時間信號

    triple: Optional['Triple']         # None if extraction failed

@dataclass
class Triple:
    subject_text: str                  # raw subject from LLM (e.g., "User")
    subject_id: str                    # lightweight normalize (§4.3)
    predicate_text: str                # raw predicate string from LLM (schema-free)
    object_text: str                   # raw object string from LLM
    extraction_confidence: float       # LLM-reported confidence ∈ [0, 1]
```

**關鍵設計**:
- 沒有 `predicate_canonical` 欄位——Phase 0 直接用 raw normalized string
- 沒有 closed vocabulary
- `subject_id` 只做最輕量的 string normalize + user/agent role binding

### 3.2 Indices

```python
storage = {
    "memories": Dict[memory_id, MemoryItem],         # primary store
    "vector_index": FaissIndex,                       # Mem0 existing
    "sp_inverted_index": Dict[
        (subject_id, predicate_normalized),           # raw normalized string
        List[memory_id]
    ],
}
```

**(S, P) inverted index 是 Phase 0 跟 Mem0 的根本差異**——這個並行 index 讓 fact identity 結構化，使 query-time 「retrieve 所有同事實版本」變成 O(1) key lookup（如果 query 能抽出 (S, P) 的話）。

### 3.3 Storage technology 選擇

| Layer | Phase 0 起步 | 升級路徑 |
|---|---|---|
| Vector index | Reuse Mem0 設定 | 不動 |
| Metadata store | SQLite / Mem0 existing | 不動 |
| (S, P) inverted index | Python dict (in-memory) + JSON persistence | 量大後遷 Redis |

---

## 4. Write-time Pipeline

### 4.1 Step 1: Memory Extraction (Reuse Mem0)

直接重用 Mem0 的 extraction prompt 與 pipeline，輸出 atomic memory texts。

**不需要修改**——這是 Phase 0 從 Mem0 直接繼承的部分。

### 4.2 Step 2: Triple Extraction (NEW, schema-free)

**設計依據**: 採用 schema-free per-item LLM triple extraction。將 fact 表徵為 (s, p, o) 的依據來自 Knowledge Editing 文獻（ROME, MEMIT, MQuAKE 皆以 (s, r, o) 表示一筆 edit）與 Temporal KG 文獻（TempReason, CRONQUESTIONS 以 (s, p, o, t) 表徵時序事實）。TruthfulRAG (Liu et al., AAAI 2026) 提供 LLM-based 關係抽取**且未做 predicate canonicalization** 的近例，支持我們 Phase 0 的延後策略（§9.1）。

> **文獻定位校正**：(1) TruthfulRAG 實作上是 GraphRAG 式 typed-entity + relationship 抽取（closed `DEFAULT_ENTITY_TYPES`、delimited tuple、gleaning loop），**並非乾淨的 schema-free (s, p, o)**；本文僅引其「LLM-based 抽取、未做 predicate/relation canonicalization」這一點，不宣稱形式同構。(2) Zep 的 edge 是 **bi-temporal**（valid time + transaction time），Phase 0 **刻意只用單一 ingestion timestamp**（bi-temporal 是 §9.4 的 F4 future work），故 Zep 僅列為 related work 對照（memory agent 場景把 fact 表成 temporal edge 的先例），**不作為本節 (s, p, o) 表徵的採用依據**。

**Prompt 模板**:

```
Given a single fact, extract its (subject, predicate, object) triple.

The predicate should be a short verb-phrase describing the relation 
between subject and object. Use natural English wording; do NOT 
force the predicate into a fixed vocabulary or controlled form.

If the fact cannot be cleanly expressed as a triple (e.g., subjective 
state, complex narrative, multiple independent facts), return null.

Fact: {memory_text}
Context: user_id={user_id}, session={session_id}

Output JSON:
{
  "subject": "<subject as named entity or 'user'/'assistant'>",
  "predicate": "<verb phrase, e.g., 'lives in', 'works at', 'likes'>",
  "object": "<object as named entity or attribute value>",
  "confidence": <0.0 to 1.0>
}
or null
```

**關鍵 design notes**:

- 不限制 predicate vocabulary——LLM 自由抽
- 不要求 predicate 用 snake_case 或固定 morphology——保留自然語言
- 對 user/agent 角色明確標 `"user"` / `"assistant"`，命名實體則用 named entity
- 抽不出乾淨 triple 時誠實返回 null（item 仍然進 storage，只是無法走 structural path）

**抽 triple 失敗的處理**:

- `triple = None`，memory item 仍然有 embedding 進 vector index
- Query-time 對這類 item 只能走 semantic path，無法 group
- 這類 item 比例是 Phase 0 的 F1 metric

### 4.3 Step 3: Lightweight Identity Tagging (NEW, 純結構)

純字串 normalize，**不依賴 LLM**:

```python
import re

def normalize_subject(subject_text: str, session_context: dict) -> str:
    s = subject_text.lower().strip()
    if s in {"user", "i", "me", "my", "myself"}:
        return f"user::{session_context['user_id']}"
    if s in {"assistant", "you", "claude", "agent"}:
        return f"assistant"
    return re.sub(r'\s+', '_', s)

def normalize_predicate(predicate_text: str) -> str:
    return predicate_text.lower().strip()
```

**Phase 0 故意不做 predicate canonicalization**——`"lives in"` 跟 `"resides at"` 會被當成不同 key。這是預期的設計取捨，是否升級到 dynamic clustering 由 §9 的 F2 指標決定。

### 4.4 Step 4: Storage Commit (Extend Mem0)

```python
def commit_memory(item: MemoryItem, storage: Storage):
    # Mem0 existing
    storage.memories[item.memory_id] = item
    storage.vector_index.add(item.embedding, item.memory_id)
    
    # NEW: (S, P) inverted index
    if item.triple is not None:
        key = (
            item.triple.subject_id,
            normalize_predicate(item.triple.predicate_text)
        )
        storage.sp_inverted_index.setdefault(key, []).append(item.memory_id)
        # Keep sorted by ingestion_timestamp DESC for fast latest-lookup
        storage.sp_inverted_index[key].sort(
            key=lambda mid: storage.memories[mid].ingestion_timestamp,
            reverse=True
        )
```

**Phase 0 不做 duplicate check / update / delete**——所有 new item 統一 ADD，舊 item 一律保留。

---

## 5. Query-time Pipeline

### 5.1 Step 1: Query Analysis (NEW, null-safe)

**設計目標**: 抽出 query 的 (S, P) 結構，**或在開放型 query 時誠實返回空 list**。

```python
@dataclass
class QueryPlan:
    semantic_query: str
    structural_keys: List[tuple]   # may be empty
    raw_query: str
```

**Prompt 模板**:

```
You are a query analyzer. Decide if the query asks about specific 
facts that can be looked up by (subject, predicate).

If yes, extract one or more (subject, predicate) keys.

If the query is open-ended (e.g., "how does the user feel lately", 
"what did we discuss about X"), or cannot be cleanly expressed as 
asking about specific facts, return an empty list. 
Do NOT force a triple if the query is ambiguous.

Query: {query}
Context: user_id={user_id}

Output JSON:
{
  "structural_keys": [
    {"subject": "...", "predicate": "..."},
    ...
  ],
  "semantic_query": "<query rewritten for embedding retrieval, or original>"
}
```

**Sanity check 步驟**: development set 上抽 20 個 query 跑一次，確認 LLM 真的會在開放型 query 上吐 empty list。若發現它強塞 (S, P)，在 prompt 加 1-2 個 negative examples。

### 5.2 Step 2: Hybrid Retrieval (NEW)

```python
def hybrid_retrieve(plan: QueryPlan, storage: Storage, k: int = 20) -> Set[str]:
    candidate_ids = set()
    
    # Path A: Semantic (Mem0's existing retrieval)
    query_embedding = embed(plan.semantic_query)
    semantic_hits = storage.vector_index.search(query_embedding, top_k=k)
    candidate_ids.update(semantic_hits)
    
    # Path B: Structural (NEW)
    for s_raw, p_raw in plan.structural_keys:
        s_id = normalize_subject(s_raw, context)
        p_norm = normalize_predicate(p_raw)
        structural_hits = storage.sp_inverted_index.get((s_id, p_norm), [])
        candidate_ids.update(structural_hits)
    
    return candidate_ids
```

**設計重點**:

- 兩 path 是 union，不是 reranking——precision 由下游 grouping 處理
- `structural_keys` 為空時 Path B 自動退化（無需顯式 fallback 邏輯）
- 即使有 structural_keys，Path A 仍然跑，覆蓋 triple extraction 失敗的 items

### 5.3 Step 3: Group + Temporal Resolve (NEW, 純結構)

**確認設計**: 不論哪個 path retrieved 的 items，全部進這一步。按每個 item 自己的 (S, P) 屬性分組，每組內 argmax timestamp。

```python
def group_and_resolve(
    candidate_ids: Set[str],
    storage: Storage
) -> Tuple[List[MemoryItem], List[MemoryItem]]:
    """
    回傳:
      - resolved: 每 (S, P) group 內 timestamp argmax 後的 winners
      - ungrouped: triple 失敗無法分組的 items，直接保留
    """
    groups: Dict[tuple, List[MemoryItem]] = {}
    ungrouped: List[MemoryItem] = []
    
    for mid in candidate_ids:
        item = storage.memories[mid]
        if item.triple is not None:
            key = (
                item.triple.subject_id,
                normalize_predicate(item.triple.predicate_text)
            )
            groups.setdefault(key, []).append(item)
        else:
            ungrouped.append(item)
    
    # Per-group: argmax ingestion_timestamp
    resolved = [
        max(items, key=lambda x: x.ingestion_timestamp)
        for items in groups.values()
    ]
    
    return resolved, ungrouped
```

**幾個設計 implication**:

- Group key 用 raw normalized string——`"lives in"` 跟 `"resides at"` 會落在不同 group。**Phase 0 已知 trade-off**，由 §9 F2 指標決定升級
- 對 ungrouped items (no triple) Phase 0 不做版本選擇，全部留下進 context
- 一個 group 只回傳 1 個 winner（最新 timestamp），舊版本不進 context

### 5.4 Step 4: Final Context Assembly & Generation (Reuse Mem0)

```python
def assemble_context(
    resolved: List[MemoryItem],
    ungrouped: List[MemoryItem]
) -> str:
    blocks = []
    for item in resolved + ungrouped:
        blocks.append(
            f"[{item.ingestion_timestamp.isoformat()}] {item.text}"
        )
    return "\n\n".join(blocks)

# Then use Mem0's existing generation prompt
```

**Phase 0 generation 完全標準**——沒有 conflict-aware prompting (留 Phase 2)。

---

## 6. Implementation Milestones

按依賴順序，估計 1-2 週可走到 M9 拿到第一份結果：

| Milestone | 內容 | 依賴 |
|---|---|---|
| M0 | Fork Mem0 repo，**標記**所有 update logic 位置（先不 disable） | - |
| M1 | 在 storage 模組加 `MemoryItem.triple` 欄位（None default） | M0 |
| M2 | 實作 schema-free triple extractor (§4.2)；prompt 參考 TruthfulRAG | M0 |
| M3 | 實作 `(S, P) inverted index` 並整合到 commit pipeline (§4.4) | M1, M2 |
| M4 | 實作 null-safe query analyzer (§5.1) | M2 |
| M5 | 實作 hybrid retriever (§5.2) | M3, M4 |
| M6 | 實作 group + temporal resolver (§5.3) | M5 |
| M7 | **新 branch** 上 disable Mem0 update logic | M0 |
| M8 | Pipeline integration test on small dev set；跑 query analyzer sanity check | M5, M6, M7 |
| M9 | 跑 baseline (full Mem0) + Phase 0 (改造版) 在 LongMemEval / MemoryAgentBench KU subset | M8 |
| M10 | 跑 ablation A0–A3 (§7.4) | M9 |
| M11 | Failure mode 分類 (§8) | M9 |
| M12 | 計算 §9 升級觸發指標 | M11 |

---

## 7. Evaluation Setup

### 7.1 Benchmarks

| Benchmark | Subset | 用途 |
|---|---|---|
| LongMemEval | knowledge_update | 主要 KU 評估 |
| MemoryAgentBench | FC KU | Phase 0 核心目標 |
| ConflictBank | temporal_conflict | 純 conflict isolated test |

### 7.2 Baselines

| Baseline | 用途 |
|---|---|
| Vanilla RAG (semantic top-K only) | 證明結構查詢價值 |
| **Full Mem0 (含 update logic)** | 主要 coupled-update baseline，同 codebase apples-to-apples |
| LightMem | 另一個 coupled-update baseline |
| Zep | 主要 decoupled-update baseline |
| DRAGged Taxonomy-Aware Prompting on vanilla | 證明純 query-time LLM judgment 不夠 |
| **Phase 0 (本方法)** | 主結果 |

### 7.3 Metrics

**主要 metrics**:
- KU Accuracy
- Latest-Version Recall
- Stale-Version Pollution

**輔助 metrics**:
- Triple extraction success rate
- (S, P) index hit rate
- Average group size per (S, P)

**Cost metrics**:
- Write-time LLM tokens per memory
- Query-time LLM tokens per query

### 7.4 Ablation Matrix

| 配置 | (S, P) index | Structural path | Temporal argmax |
|---|---|---|---|
| A0 (vanilla) | ✗ | ✗ | ✗ |
| A1 (index only, semantic-only retrieval) | ✓ | ✗ | ✓ (在 semantic top-K 內 group) |
| A2 (no group, semantic + structural retrieval) | ✓ | ✓ | ✗ |
| A3 (Phase 0 full) | ✓ | ✓ | ✓ |

- A1 vs A3 → structural retrieval 貢獻
- A2 vs A3 → temporal grouping 貢獻
- A0 vs A3 → 整體 Phase 0 貢獻

---

## 8. Failure Mode Analysis

對 Phase 0 失敗案例**預先承諾分類**為以下四類：

| Type | 觀察特徵 | 指向的升級 |
|---|---|---|
| F1: Triple extraction failed | `item.triple is None` | Phase 2 fallback design |
| F2: (S, P) inconsistent | 同事實的不同 memory 抽到不同 (S, P) | §9.1 D3 predicate clustering |
| F3: COEXIST mistaken for SUPERSEDE | 多版本實際應並存，被誤取最新 | §9.2 Phase 1 relation classification |
| F4: Ingestion ≠ valid time | 對話中提及歷史事實，ingestion timestamp 不反映 valid time | §9.4 Future work |

從失敗 case 隨機抽 50-100 筆手工標 F1-F4 得 distribution 表。**這張表是 paper Section 4 的核心 evidence**——直接論證 Phase 0 不足與下階段必要性。

---

## 9. Future Upgrade Trigger Conditions

Phase 0 跑完後，依 failure mode 數據觸發具體升級。每個觸發條件對應一個獨立 plug-in，不動 Phase 0 核心 pipeline。

### 9.1 D3 觸發：Predicate Canonicalization

**觸發指標**: F2 比例（同事實被抽到不同 (S, P) 的失敗）

| F2 區間 | 升級內容 |
|---|---|
| < 15% | 不升級。Phase 0 的 raw string normalize 已足夠 |
| 15–25% | 加入 lightweight string normalize（同義詞 dict、stemming） |
| > 25% | 升級到 **open vocabulary + embedding-based online clustering** |

**Embedding-based online clustering 機制**:

```python
class PredicateClusterManager:
    def __init__(self, embedder, threshold=0.85):
        self.clusters = []                 # List[List[predicate_text]]
        self.cluster_centroids = []        # List[embedding]
        self.embedder = embedder
        self.threshold = threshold
    
    def assign_cluster(self, predicate_text: str) -> int:
        emb = self.embedder.embed(predicate_text)
        if not self.clusters:
            self._open_new_cluster(predicate_text, emb)
            return 0
        sims = [cosine(emb, c) for c in self.cluster_centroids]
        max_idx = argmax(sims)
        if sims[max_idx] >= self.threshold:
            self.clusters[max_idx].append(predicate_text)
            self._update_centroid(max_idx)
            return max_idx
        else:
            self._open_new_cluster(predicate_text, emb)
            return len(self.clusters) - 1
```

(S, P) inverted index 的 key 從 `(subject_id, predicate_normalized)` 改為 `(subject_id, cluster_id)`。threshold 在 dev set 上 once-and-for-all 調好。

### 9.2 Phase 1 觸發：Write-time Relation Classification

**觸發指標**: F3 比例（COEXIST 誤判為 SUPERSEDE）

| F3 區間 | 升級內容 |
|---|---|
| < 10% | 不升級 |
| ≥ 10% | 加入 LLM-based duplicate detection；F3 持續高則加完整 6-type relation classification（前述 conservative 版表格） |

### 9.3 Phase 2 觸發：Query-time LLM Conflict Judgment

**觸發指標**: F1 比例 + open-ended query 表現

| 觸發條件 | 升級內容 |
|---|---|
| F1 > 20% OR open-ended query accuracy 低於 baseline | 加入 DRAGged 風格 Taxonomy-Aware Prompting 作為 fallback path |

### 9.4 Future Work 觸發

| 觸發指標 | 升級內容 |
|---|---|
| F4 > 15% | Valid time extraction (Bi-temporal model) |
| Multi-hop query 出現失敗 case | Multi-hop chain traversal |

---

## 10. Phase 0 → Phase 1 / 2 / D3 Plug-in Interfaces

Phase 0 實作時預留以下 hook，讓未來升級不需 refactor 核心：

```python
class WriteTimePipeline:
    def __init__(
        self,
        extractor,                     # Mem0 reuse
        triple_extractor,              # Phase 0 NEW
        duplicate_detector=None,       # Phase 1 plug-in
        relation_classifier=None,      # Phase 1 plug-in
    ):
        ...

class QueryTimePipeline:
    def __init__(
        self,
        query_analyzer,                # Phase 0 NEW
        retriever,                     # Phase 0 NEW
        resolver,                      # Phase 0 NEW
        generator,                     # Mem0 reuse
        llm_conflict_judge=None,       # Phase 2 plug-in
        predicate_clusterer=None,      # D3 plug-in
    ):
        ...
```

升級時只需提供對應 plug-in 並 instantiate，Phase 0 核心 pipeline 完全不動。

---

## 11. paper Method Section Narrative Outline

```
3. Method
  3.1 Framework Overview
       三層架構圖 + 100 字解釋 write-time vs query-time 分工
  3.2 Building on Mem0
       §1 disable / keep / extend 矩陣
  3.3 Write-time Structural Indexing
       3.3.1 Schema-free Triple Extraction (cite TruthfulRAG)
       3.3.2 (S, P) Inverted Index
       3.3.3 Discussion: Why No Cross-item Judgment at Write-time
  3.4 Query-time Structural Resolution
       3.4.1 Null-safe Query Analysis
       3.4.2 Hybrid Retrieval (Union semantic + structural)
       3.4.3 Identity-based Grouping + Temporal Resolution
  3.5 Implementation Details
       Mem0 base, embedding model, hyperparameters
```

**3.3.3 是 paper 哲學的核心放置點**——明確說 conservative commit 不只是「不刪」，而是「不在 write-time 做 cross-item LLM judgment」。這是跟 Zep 最大的區別。

---

*Phase 0 spec ends here. Phase 1 / Phase 2 / D3 upgrades to be designed after Phase 0 results inform the failure mode distribution.*
