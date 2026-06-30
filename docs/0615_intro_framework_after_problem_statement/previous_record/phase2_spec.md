# Phase 2 Implementation Guide: Query-time Identity Grouping and Temporal Resolution

> **Status**: Final design spec for Phase 2 query-time component implementation
> **Last updated**: 2026-06-20
> **Predecessor**: `phase0_implementation_guide.md` (write-time + storage schema)
> **Codebase**: Forked from Mem0 (sharing Phase 0 modifications)

---

## §1 Overview

### §1.1 Phase 2 在整體 pipeline 中的位置

Phase 2 實作的是**兩階段知識更新框架 (Two-Stage Knowledge Update Framework)** 中查詢階段 (Stage 2, query-time) 的完整流程。Phase 0 已建立了寫入階段 (Stage 1, write-time) 的所有元件——每筆新進事實的 (subject, predicate, object) 三元組萃取、確定性結構性提交、單一層 (single tier) 記憶儲存。Phase 2 在此基礎上實作查詢階段的條件式結構性路由 (conditional structural routing)、結構性分群 (structural grouping)、LLM 動態分群 (LLM dynamic grouping)、以及時序解析 (temporal resolution)。

整體 pipeline 在 Phase 2 完成後的端到端流程：

```
[Write-time, Phase 0]
  raw conversation segment
    → Mem0 memory extraction
    → per-item triple extraction (LLM, schema-free)
    → string-normalize (S, P, O)
    → commit to unified storage (with triple metadata)

[Query-time, Phase 2]
  user query
    → Mem0 hybrid retrieval (top-100 candidates)
    → conditional structural routing (split candidates into two paths)
    → Path A: structural grouping by (S, P) + timestamp argmax
    → Path B: LLM dynamic grouping + per-group timestamp argmax
    → final context assembly (retrieval-ranking preserved, resolved items removed)
    → inference LLM (Mem0 default context format)
    → answer
```

### §1.2 與 Phase 0 的銜接 interface

Phase 2 沿用 Phase 0 定義的核心資料結構，主要是 `MemoryItem` dataclass：

```python
# From phase0_implementation_guide.md §3.2
@dataclass
class MemoryItem:
    memory_id: str
    content: str
    ingestion_timestamp: datetime
    user_id: str
    triple: Optional[Triple]   # None if triple extraction failed (F1)
    embedding: List[float]
    metadata: Dict[str, Any]

@dataclass
class Triple:
    subject: str           # normalized
    predicate: str         # normalized
    object: str            # normalized
    confidence: float      # from extraction LLM
    raw_subject: str       # pre-normalize
    raw_predicate: str
    raw_object: str
```

Phase 2 不修改寫入階段的任何元件；僅在查詢階段於 Mem0 的 `Memory.search()` 之後插入新的處理 pipeline。Mem0 原本的 search 方法回傳 `List[MemoryItem]`，Phase 2 接手這個 list 進行後續處理。

### §1.3 Phase 2 範圍與明確不做的事

**Phase 2 範圍**：

- 條件式結構性路由邏輯 (conditional structural routing)
- 結構性分群與時序解析 (structural grouping with timestamp argmax)
- LLM 動態分群元件 (LLM dynamic grouping)，包含 prompt design、JSON 解析、failure handling
- Timestamp tie escalation 處理
- Final context 組裝邏輯
- 三層 evaluation pipeline (Retrieval / Resolution / End-to-end)
- Failure mode 量測機制 (F1-F8)

**Phase 2 明確不做的事**：

- 不修改 Mem0 的檢索 (retrieval) 機制——沿用其 hybrid retrieval (semantic + lexical) 與 default top-K=100
- 不引入 recall augmentation (HyDE、Query2Doc 等)，未來若 Level 1 evaluation 顯示 retrieval 是瓶頸再考慮
- 不引入物理分層儲存 (active/archive store)——維持 Phase 0 的 single tier 設計
- 不修改 inference LLM 的 context 格式——沿用 Mem0 default
- 不處理 query-irrelevant 記憶的 resolve 表現量測，假設此部分與 KU Acc 正相關
- 不對 LLM 動態分群池超過 30 筆的情境做 batch 處理優化，等 pilot test 確認分布後再決定

---

## §2 Query-time Pipeline

整個查詢階段拆解為六個依序執行的階段。每階段的輸入、輸出、副作用 (side effects) 都明確界定，方便獨立測試與替換。

### §2.1 Stage 1: Retrieval (沿用 Mem0)

**輸入**：`query: str`, `user_id: str`

**輸出**：`candidates: List[MemoryItem]` (top-100)

**實作**：直接呼叫 Mem0 既有的 `Memory.search(query, user_id, limit=100)`。Mem0 內部用 semantic embedding + lexical match 做 hybrid retrieval，回傳依 relevance score 排序的 memory items。

**關鍵約定**：

- Mem0 的 retrieval ranking 在後續階段必須完整保留，作為 final context 的排序依據。
- Memory items 中已包含 Phase 0 寫入時掛上的 `triple` 欄位（可能為 `None`）跟 `ingestion_timestamp`。

### §2.2 Stage 2: Conditional Structural Routing

**輸入**：`candidates: List[MemoryItem]` (來自 Stage 1)

**輸出**：
- `structural_pool: Dict[Tuple[str, str], List[MemoryItem]]`——key 為 (S, P)，value 為共享該 (S, P) 的多筆 memories（每組至少 2 筆）
- `dynamic_pool: List[MemoryItem]`——所有需要走 LLM 動態分群路徑的 memories

**路由規則**：

對 `candidates` 中的每筆 memory，依以下規則分流：

1. **無 triple 的 memory**（`item.triple is None`）→ 加入 `dynamic_pool`
2. **有 triple 的 memory** → 先收集到一個 `(S, P) → memory_ids` 的 in-memory mapping：
   - 若該 (S, P) 在 mapping 中對應的 memories 數量 ≥ 2 → 整組進入 `structural_pool`
   - 若該 (S, P) 在 mapping 中只對應 1 筆 memory（i.e., 在當前候選池中沒有結構性對手）→ 該 memory 加入 `dynamic_pool`

**設計理由**：這是「**條件式結構性路由 (conditional structural routing)**」——routing 決策不只看 memory 本身是否有 triple，而是看當前候選池中是否存在能用結構性比對的對手 memory。對應的失敗模式 F5 (cross-mechanism missed grouping) 因此被結構性吸收：當有 triple 的 memory 在當前查詢中沒有結構性對手，自然 fall through 到 LLM 動態分群，跟可能是同事實的 untriple memories 在同一池中被一起判斷。

### §2.3 Stage 3: Structural Grouping + Temporal Resolution

**輸入**：`structural_pool: Dict[Tuple[str, str], List[MemoryItem]]`

**輸出**：
- `structural_winners: List[MemoryItem]`——每個 (S, P) group 經時序解析後的唯一最新版本
- `escalated_groups: List[List[MemoryItem]]`——遇到 timestamp tie 無法解析、需要 escalate 到 LLM 動態分群的 groups

**解析規則**：

對 `structural_pool` 中每個 `(S, P) → memories` group：

1. 找出 `memories` 中 `ingestion_timestamp` 最大的 entries
2. 若最大 timestamp 對應唯一一筆 memory → 該 memory 進入 `structural_winners`
3. 若最大 timestamp 對應多筆 memories（timestamp tie）→ 整組 entries 進入 `escalated_groups`

**設計理由**：Timestamp tie 在 batch ingestion、同對話內衝突資訊、或 ingestion timestamp precision 不足（例如以「秒」為單位但同秒寫入多筆）的情境下會發生。當 argmax 退化為無唯一解時，結構性機制無法 disambiguate，必須 escalate 到 LLM 判斷。

### §2.4 Stage 4: LLM Dynamic Grouping

**輸入**：
- `dynamic_pool: List[MemoryItem]` (來自 Stage 2)
- `escalated_groups: List[List[MemoryItem]]` (來自 Stage 3)
- `query: str`

合併輸入：`llm_grouping_input = dynamic_pool + flatten(escalated_groups)`

**輸出**：
- `dynamic_winners: List[MemoryItem]`——LLM 分群後每群經時序解析的最新版本
- `singletons: List[MemoryItem]`——LLM 判定為獨立、與任何其他 entry 無同事實關係的 memories

**處理流程**：

1. 將 `llm_grouping_input` 跟 `query` 餵入 LLM grouping prompt (詳細 prompt 見 §3.3)
2. LLM 回傳 JSON 結構，包含 `groups` 與 `singletons`
3. 對每個 `groups[i]`，提取對應的 `MemoryItem` 物件，做 timestamp argmax：
   - 若唯一 winner → 加入 `dynamic_winners`
   - 若再次 timestamp tie → 該群所有 entries 全部加入 `dynamic_winners`（不再二度 escalate，避免無限遞迴）
4. 對 `singletons`，直接全部加入 `dynamic_winners`
5. JSON 解析失敗 → fallback：`llm_grouping_input` 中所有 entries 視為各自 singleton，全部加入 `dynamic_winners`

**設計理由**：

- 將 `dynamic_pool` 跟 `escalated_groups` 合併輸入 LLM 而非分開處理，是因為 escalated entries (timestamp tie 的 (S, P) groups) 在 LLM 視角下跟 dynamic_pool entries 是同質的——都是「需要 LLM 判斷是否同事實」的記憶。LLM 可能會把 escalated group 重新分群（例如發現裡面其實有不同事實混在一起）。
- Singletons 直接全保留：LLM 判定為獨立 entries 沒有被合群的依據，全保留進入 final context。這對應於「conservative fallback」原則。
- JSON 解析失敗 fallback 為全 singleton：保留所有 entries，不誤判合群、也不誤判排除。

### §2.5 Stage 5: Final Context Assembly

**輸入**：
- `structural_winners: List[MemoryItem]` (來自 Stage 3)
- `dynamic_winners: List[MemoryItem]` (來自 Stage 4)
- `candidates: List[MemoryItem]` (原始 retrieval ranking，來自 Stage 1)

**輸出**：`final_context: List[MemoryItem]`

**組裝邏輯**：

```pseudo
all_winners_ids = {m.memory_id for m in structural_winners + dynamic_winners}
final_context = [m for m in candidates if m.memory_id in all_winners_ids]
```

**設計理由**：沿用 Stage 1 的 retrieval ranking 順序，只移除被 resolve 掉的（即既不在 `structural_winners` 也不在 `dynamic_winners` 中的）entries，不重新排序。如此 final context 對 inference LLM 的呈現順序跟 Mem0 baseline 在 ordering 上完全一致，將對比實驗的 confounding 變數降到最低。

### §2.6 Stage 6: Inference LLM Generation

**輸入**：
- `final_context: List[MemoryItem]`
- `query: str`

**輸出**：`answer: str`

**實作**：直接呼叫 Mem0 既有的 inference 流程 (其 default prompt format)，傳入 `final_context` 跟 `query`。

**設計理由**：Phase 2 不修改 inference LLM 的 prompt 格式，保持跟 Mem0 baseline 的公平對比。後續若 Level 2 evaluation 顯示 resolve 表現好但 Level 3 KU Acc 不夠，再探討 inference context 格式優化。

---

## §3 Component Specifications

### §3.1 Conditional Structural Router

#### Algorithm

```python
from typing import Dict, List, Tuple
from collections import defaultdict

def conditional_structural_routing(
    candidates: List[MemoryItem]
) -> Tuple[Dict[Tuple[str, str], List[MemoryItem]], List[MemoryItem]]:
    """
    Route retrieved candidates into structural and dynamic pools.
    
    Args:
        candidates: Top-K retrieved memories (sorted by relevance).
    
    Returns:
        structural_pool: Dict mapping (S, P) -> list of memories sharing 
                        that (S, P) when at least 2 memories share it.
        dynamic_pool: List of memories routed to LLM dynamic grouping.
                     Includes (a) memories without triple and 
                     (b) triple-tagged memories whose (S, P) has no 
                     competitor in candidates.
    """
    # Step 1: Collect (S, P) -> memory_ids mapping
    sp_to_memories: Dict[Tuple[str, str], List[MemoryItem]] = defaultdict(list)
    no_triple_memories: List[MemoryItem] = []
    
    for m in candidates:
        if m.triple is None:
            no_triple_memories.append(m)
        else:
            sp_key = (m.triple.subject, m.triple.predicate)
            sp_to_memories[sp_key].append(m)
    
    # Step 2: Apply conditional routing rule
    structural_pool: Dict[Tuple[str, str], List[MemoryItem]] = {}
    singleton_triple_memories: List[MemoryItem] = []
    
    for sp_key, mems in sp_to_memories.items():
        if len(mems) >= 2:
            structural_pool[sp_key] = mems
        else:
            # Triple-tagged but no structural competitor in candidates
            singleton_triple_memories.extend(mems)
    
    dynamic_pool = no_triple_memories + singleton_triple_memories
    
    return structural_pool, dynamic_pool
```

#### Interface

- **Input contract**: `candidates` 必須是 `List[MemoryItem]`，每筆 item 的 `triple` 欄位若存在則已經是 normalized 過的 (在 Phase 0 寫入時完成)
- **Output contract**: `structural_pool` 中每個 group 必有 ≥ 2 個 memories；`dynamic_pool` 可能為空（當所有 candidates 都有 triple 且都有結構性對手時）

#### 失敗模式關聯

- **F1 (triple 萃取失敗)** 在 routing 中體現為 `no_triple_memories`，被路由到 `dynamic_pool`
- **F2 (同事實但 (S, P) 不一致)** 在 routing 中體現為兩個或多個 singleton (S, P)——它們都會 fall through 到 `dynamic_pool`，由 LLM 動態分群試圖救回
- **F3 (不同事實但 (S, P) 相同)** 在 routing 中體現為錯誤的 `structural_pool` group——後續 Stage 3 會錯誤地以時序選 winner，污染 final context

### §3.2 Structural Grouping with Temporal Resolution

#### Algorithm

```python
from datetime import datetime
from typing import List, Tuple, Dict

def structural_grouping_and_resolve(
    structural_pool: Dict[Tuple[str, str], List[MemoryItem]]
) -> Tuple[List[MemoryItem], List[List[MemoryItem]]]:
    """
    Apply timestamp argmax to each (S, P) group.
    Escalate timestamp ties to LLM dynamic grouping.
    
    Returns:
        structural_winners: Unique winners per (S, P) group.
        escalated_groups: Groups where timestamp argmax is non-unique.
    """
    structural_winners: List[MemoryItem] = []
    escalated_groups: List[List[MemoryItem]] = []
    
    for sp_key, mems in structural_pool.items():
        max_ts = max(m.ingestion_timestamp for m in mems)
        winners_at_max = [m for m in mems if m.ingestion_timestamp == max_ts]
        
        if len(winners_at_max) == 1:
            structural_winners.append(winners_at_max[0])
        else:
            # Timestamp tie — escalate the entire group (not just tied members)
            escalated_groups.append(mems)
    
    return structural_winners, escalated_groups
```

#### 設計決定：escalate 整群還是只 escalate tied members

當某 (S, P) group 內 timestamp tie 時，**escalate 整群還是只 escalate tied members 進 LLM**？

選擇：**escalate 整群**。

理由：

1. LLM 看到完整 group 才能做正確的 fact identity 判斷。如果只 escalate tied members，LLM 失去了「**這幾筆都共享同 (S, P)，可能是同事實演化**」這個重要 prior。
2. 整群進 LLM 也讓 LLM 有機會 split：例如同 (S, P) 群中 LLM 可能發現 entries 1, 2 是同事實的不同版本，entry 3 雖然 (S, P) 相同但實際描述不同事實（F3 失敗的事後 LLM 救援）。

### §3.3 LLM Dynamic Grouping

這是 Phase 2 的核心 LLM-based component。Prompt 結構 adapt 自 Astute RAG (Wang et al., 2024, arXiv:2410.07176) 的 "Iterative Knowledge Consolidation" prompt——其 cluster-and-separate instruction pattern 跟我們的 fact identity grouping 任務在 structure 上完全對應。但 grouping criterion 我們做了 task-specific 修改：Astute RAG 是依「information consistency」分群，我們依「fact identity」分群——同事實的不同 value 對 Astute RAG 是「conflicting → separate」，對我們是「same fact identity → same group」。

#### Prompt Template

```
You are analyzing a list of memory entries retrieved in response to a user query. 
Your task is to GROUP memories that describe the SAME UNDERLYING FACT (possibly 
with different versions or rephrasings).

# Grouping Criterion
Two memories belong to the SAME group if and only if they refer to the same 
underlying fact—same subject and same attribute or relation—even when the 
specific value (object) differs. Differing values across the same (subject, 
attribute) pair indicate different VERSIONS of the same fact, not different facts.

Memories with different (subject, attribute) pairs belong to DIFFERENT groups.
Memories with no version-relation to any other entry in the list should be 
marked as singletons.

# Query
{query}

# Memory Entries
{for each memory in input:}
[{memory_id}]: {content} (recorded at: {ingestion_timestamp})

# Output Format
Return a JSON object with this exact structure:
{
  "groups": [
    {
      "fact_summary": "<one-sentence description of the underlying fact, e.g., 'User's current city of residence'>",
      "memory_ids": ["<id1>", "<id2>", ...],
      "reasoning": "<brief 1-sentence justification>"
    },
    ...
  ],
  "singletons": ["<id_a>", "<id_b>", ...]
}

# Few-shot Examples

## Example 1: Versioned fact
Query: Where does the user live now?
Memory entries:
[m_001]: User said they live in Taipei. (recorded at: 2024-01-15)
[m_002]: User mentioned moving to Tainan last month. (recorded at: 2024-03-20)
[m_003]: User's favorite food is beef noodle soup. (recorded at: 2024-02-10)

Expected output:
{
  "groups": [
    {
      "fact_summary": "User's city of residence",
      "memory_ids": ["m_001", "m_002"],
      "reasoning": "Both describe the user's city of residence at different times."
    }
  ],
  "singletons": ["m_003"]
}

## Example 2: Same (subject, attribute) but different facts
Query: What does the user do for a living?
Memory entries:
[m_011]: User said they work as a software engineer. (recorded at: 2024-02-01)
[m_012]: User's spouse works as a software engineer. (recorded at: 2024-02-15)
[m_013]: User mentioned switching to product manager role recently. (recorded at: 2024-05-10)

Expected output:
{
  "groups": [
    {
      "fact_summary": "User's own occupation",
      "memory_ids": ["m_011", "m_013"],
      "reasoning": "Both describe the user's own occupation across time."
    }
  ],
  "singletons": ["m_012"]
}
Reasoning note: m_011 and m_012 share surface attribute "software engineer" but 
m_012 refers to a different subject (the spouse), so it is a different fact.

## Example 3: Unrelated entries
Query: Tell me about the user's preferences.
Memory entries:
[m_021]: User likes hiking on weekends. (recorded at: 2024-01-05)
[m_022]: User prefers oolong tea over green tea. (recorded at: 2024-02-12)
[m_023]: User reads science fiction novels. (recorded at: 2024-03-08)

Expected output:
{
  "groups": [],
  "singletons": ["m_021", "m_022", "m_023"]
}

# Conservative Bias
When unsure whether two memories refer to the same fact, prefer placing them 
in separate groups (or as singletons) over erroneous grouping. False merges 
are worse than false splits because they hide valid versions; false splits 
only leave the choice to downstream temporal resolution.

# Now analyze the following:
Query: {query}
Memory entries:
{input_memories_formatted}
```

#### Design Choice Attribution

| Component | Source |
|---|---|
| Cluster-and-separate instruction structure (groups vs singletons output) | **Adapted from Astute RAG** (Wang et al., 2024, arXiv:2410.07176) — its "Iterative Knowledge Consolidation" prompt uses the same cluster-and-separate pattern |
| Grouping criterion = fact identity (same subject + same attribute) | **Our own design** — Astute RAG groups by "information consistency", we replaced it with fact-identity criterion to handle temporal versions correctly |
| Output fields: `fact_summary`, `reasoning` | **Our own design** — for evaluation auditability and ablation diagnostics |
| `singletons` separate from `groups` | **Our own design** — matches our "failure-mode = keep memory as-is" fallback policy |
| Few-shot examples (3 examples covering versioned/disambiguation/unrelated cases) | **Our own design** |
| Conservative bias instruction | **Our own design** — explicit instruction motivated by F4/F5 trade-off analysis |

#### JSON Parsing and Failure Handling

```python
import json
import logging
from typing import Optional

def parse_llm_grouping_output(
    raw_output: str,
    input_memories: List[MemoryItem]
) -> Tuple[List[List[MemoryItem]], List[MemoryItem]]:
    """
    Parse LLM output JSON into groups and singletons.
    On parse failure, fallback to all-singleton handling.
    
    Returns:
        groups: List of memory groups (each group is List[MemoryItem]).
        singletons: List of unrelated memories.
    """
    memory_by_id = {m.memory_id: m for m in input_memories}
    
    try:
        parsed = json.loads(raw_output)
        groups = []
        for g in parsed.get("groups", []):
            group_mems = [memory_by_id[mid] for mid in g["memory_ids"] 
                         if mid in memory_by_id]
            if len(group_mems) >= 2:  # Sanity check: group must have ≥2 entries
                groups.append(group_mems)
            else:
                # Single-entry "group" treated as singleton
                if group_mems:
                    parsed.setdefault("singletons", []).append(group_mems[0].memory_id)
        
        singleton_ids = parsed.get("singletons", [])
        singletons = [memory_by_id[sid] for sid in singleton_ids if sid in memory_by_id]
        
        # Sanity check: every input memory should appear exactly once
        accounted_ids = {m.memory_id for g in groups for m in g} | {s.memory_id for s in singletons}
        missing_ids = set(memory_by_id.keys()) - accounted_ids
        if missing_ids:
            logging.warning(f"LLM output missed memories: {missing_ids}. Adding as singletons.")
            singletons.extend([memory_by_id[mid] for mid in missing_ids])
        
        return groups, singletons
    
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        logging.warning(f"LLM grouping JSON parse failed: {e}. Fallback to all-singleton.")
        return [], list(input_memories)
```

### §3.4 Timestamp Tie Handler

#### Algorithm

```python
def resolve_group_by_timestamp(group: List[MemoryItem]) -> List[MemoryItem]:
    """
    Apply timestamp argmax to a group.
    Returns either single winner (unique max) or all tied entries.
    """
    if not group:
        return []
    
    max_ts = max(m.ingestion_timestamp for m in group)
    winners = [m for m in group if m.ingestion_timestamp == max_ts]
    
    return winners  # length 1 if unique max, else all tied
```

#### 套用範圍

- Stage 3 (structural grouping)：對每個 (S, P) group 套用，若 length > 1 escalate 到 LLM
- Stage 4 (LLM dynamic grouping)：對每個 LLM-derived group 套用，若 length > 1 全保留（不再 escalate）

### §3.5 Final Context Formatter

#### Algorithm

```python
def assemble_final_context(
    candidates: List[MemoryItem],          # Original retrieval ranking
    structural_winners: List[MemoryItem],
    dynamic_winners: List[MemoryItem]
) -> List[MemoryItem]:
    """
    Filter candidates by retained winners, preserving retrieval ranking.
    """
    retained_ids = {m.memory_id for m in structural_winners + dynamic_winners}
    final_context = [m for m in candidates if m.memory_id in retained_ids]
    return final_context
```

#### 與 Mem0 default context format 的銜接

`final_context` 直接傳入 Mem0 既有的 inference pipeline。Mem0 內部會將 `List[MemoryItem]` 轉為其 default prompt format（通常是 "Based on the following memories about the user: ..." 形式的 numbered list）。Phase 2 不修改此 format。

---

## §4 Failure Mode Taxonomy

Phase 2 涵蓋的失敗模式分為兩類：(a) 沿用自 Phase 0 的 F1-F4，但在 Phase 2 中有對應的 query-time 救援機制；(b) Phase 2 新增的 F5-F8。

### F1: Triple Extraction Failure (per-item)

- **發生時機**: Phase 0 write-time
- **表現**: `MemoryItem.triple is None`
- **Phase 2 處理**: 路由到 `dynamic_pool`，由 LLM 動態分群嘗試識別其事實身份
- **量測**: 監控 `dynamic_pool` 中無 triple 的 entries 比例

### F2: Same Fact, Different (S, P) Strings (semantic equivalence missed by normalize)

- **發生時機**: Phase 0 write-time (triple extraction LLM 對同事實萃取出不同 predicate string，例如 "lives_in" vs "resides_at"；或 subject 寫法不一致，例如 "User" vs "the user")
- **表現**: 同事實的不同版本被分配到不同 (S, P) keys
- **Phase 2 處理**: 兩個 (S, P) singleton 都 fall through 到 `dynamic_pool`，LLM 動態分群有機會把它們合群
- **量測**: 對 ground truth conflict pair，檢查它們的 (S, P) 是否一致；計算 F2 rate
- **觸發升級條件**: F2 rate > 25% 時，考慮加入 online predicate clustering normalize 機制 (Phase 3+)

### F3: Different Facts, Same (S, P) String (collision)

- **發生時機**: Phase 0 write-time (例如 "user's job" 跟 "user's spouse's job" 都萃取為 `(User, job, X)`)
- **表現**: 不同事實的 entries 被錯誤分配到同 (S, P) key，Stage 3 會錯誤地以 timestamp argmax 選 winner
- **Phase 2 處理**: 無 query-time 救援；錯誤地呈現「最新版本」（實際上是不同事實的較新 entry）
- **量測**: 對 ground truth 中 (S, P) 相同但實際不同事實的情境，計算 F3 rate
- **觸發升級條件**: F3 rate > 5% 時，考慮 triple extraction 加上 object-aware disambiguation

### F4: Structural Pool — Wrong Winner Selection

- **發生時機**: Stage 3 timestamp argmax
- **表現**: 同 (S, P) group 中所有 timestamps 都正確，但 argmax 結果對應的不是 ground truth new fact (例如 timestamp 較新的反而是 ingestion 雜訊或測試資料)
- **Phase 2 處理**: 無自動救援；此失誤反映 ingestion timestamp 跟「事實真實時間」的潛在 mismatch
- **量測**: 對 conflict instances，檢查 Stage 3 winner 是否對應 ground truth `gt_new`

### F5: LLM Dynamic Grouping — False Merge

- **發生時機**: Stage 4 LLM 判斷
- **表現**: 不同事實的 entries 被 LLM 錯誤合群，後續 timestamp argmax 選錯 winner
- **Phase 2 處理**: 無自動救援；conservative bias instruction 設計上偏向 false split 而非 false merge，減少此 mode 的發生
- **量測**: `group_purity` metric——同群內 entries 是否真的同事實
- **觸發升級條件**: `group_purity` < 0.8 時，考慮 prompt refinement 或加入 NLI-based pairwise validation

### F6: LLM Dynamic Grouping — False Split

- **發生時機**: Stage 4 LLM 判斷
- **表現**: 同事實的不同版本被 LLM 判定為不同 facts，分成不同 groups 或 singletons，舊版本未被 resolve 排除
- **Phase 2 處理**: 無自動救援；但相對良性——final context 中包含多個版本，inference LLM 仍可能識別出哪個是 latest
- **量測**: `group_completeness` metric——同事實 entries 是否真的在同群

### F7: LLM Output JSON Parse Failure

- **發生時機**: Stage 4 LLM 輸出格式錯誤
- **表現**: 無法解析 JSON、或缺欄位、或 memory_id 對應不到
- **Phase 2 處理**: Fallback——所有輸入 entries 視為 singletons 全部保留
- **量測**: `parse_failure_rate`
- **觸發升級條件**: `parse_failure_rate` > 5% 時，加強 prompt 中的 output format 約束，或使用 structured output API (例如 OpenAI's json_mode)

### F8: LLM Pool Size Exceeds Stable Region

- **發生時機**: Stage 4 之前
- **表現**: `len(llm_grouping_input) > 30` 時 LLM 分群品質下降
- **Phase 2 處理**: Phase 2 起步**不做特別處理**，先 empirically 觀察分布
- **量測**: `llm_pool_size` distribution
- **觸發升級條件**: 若 > 30 的 case 佔比超過 30%，考慮加入 batch processing 或 embedding pre-cluster


---

## §5 Evaluation Metrics

Phase 2 的 evaluation 設計基於 MemoryAgentBench (Hu, Wang, McAuley, ICLR 2026) 的 FactConsolidation 子集——其本身建構自 MQUAKE (Zhong et al., EMNLP 2023) 的 counterfactual edit pairs。MQUAKE 的每個 instance 結構為 `⟨E, Q, a, a*, C, C*⟩`，其中 `C` 為 original (s, r, o) triples、`C*` 為 post-edit (s, r, o*) triples——這意味著 ground truth 在 fact-level 上是完全結構化的，**conversation history 中哪幾筆是 old fact、哪幾筆是 new fact、query 對應哪個 fact，全部都明確標出**。

這個 dataset-level grounding 讓我們的三層 evaluation 設計 deliverable：每一層 isolate 不同的失敗源。

### §5.1 Ground Truth Annotation Structure

對 FactConsolidation 中每筆 evaluation instance，從 MQUAKE-derived metadata 提取：

```python
@dataclass
class EvalInstance:
    instance_id: str
    conversation_history: List[ConversationTurn]
    query: str
    gold_answer: str                              # corresponds to a* (post-edit answer)
    
    # MQUAKE-derived fact annotations
    relevant_fact: Tuple[str, str]                # (subject, relation) of the query-relevant fact
    gt_new_memory_id: str                         # memory ID of the new fact in conversation
    gt_old_memory_id: Optional[str]               # memory ID of the old fact (None if no-conflict instance)
    is_conflict_instance: bool                    # True if conversation contains both old and new versions
```

**重要約定**：`gt_new_memory_id` 跟 `gt_old_memory_id` 是當 conversation history 被 Mem0 / our system 寫入 memory bank 後對應的 memory IDs。這需要在 evaluation 前先跑一次 write-time pipeline，並記錄 conversation turn → memory_id 的映射。

### §5.2 Level 1: Retrieval Evaluation

**測量對象**：Stage 1 (Retrieval) 的輸出 `candidates: List[MemoryItem]`

**Metrics**：

```python
def evaluate_retrieval(
    candidates: List[MemoryItem],
    instance: EvalInstance
) -> Dict[str, float]:
    """
    Measure whether retrieval contains query-relevant ground truth memories.
    """
    retrieved_ids = {m.memory_id for m in candidates}
    
    metrics = {}
    
    # Always measured
    metrics["retrieval_new_recall"] = float(instance.gt_new_memory_id in retrieved_ids)
    
    # Only for conflict instances
    if instance.is_conflict_instance:
        metrics["retrieval_pair_recall"] = float(
            instance.gt_new_memory_id in retrieved_ids 
            and instance.gt_old_memory_id in retrieved_ids
        )
    
    # Only for singleton instances (no conflict in conversation)
    if not instance.is_conflict_instance:
        metrics["retrieval_singleton_recall"] = float(
            instance.gt_new_memory_id in retrieved_ids
        )
    
    return metrics
```

**解讀**：

- `retrieval_new_recall`：query 對應的最新事實是否被檢索回。任何下游正確性都建立在此 metric 上。
- `retrieval_pair_recall`：對 conflict instance，新舊版本是否都被檢索回。決定後續 resolve 階段是否有「東西可以 resolve」——若只檢索到 new 而沒檢索到 old，resolve 沒衝突可解；若只檢索到 old 而沒檢索到 new，KU 必然失敗。
- `retrieval_singleton_recall`：對 no-conflict instance，唯一相關事實是否被檢索回。

### §5.3 Level 2: Resolution Evaluation

**測量對象**：Stage 5 (Final Context Assembly) 的輸出 `final_context: List[MemoryItem]`

**Metrics**：

```python
def evaluate_resolution(
    final_context: List[MemoryItem],
    instance: EvalInstance
) -> Dict[str, float]:
    """
    Measure whether resolve correctly preserved new and removed old.
    """
    final_ids = {m.memory_id for m in final_context}
    
    metrics = {}
    
    if instance.is_conflict_instance:
        # New version kept (essential for correct KU)
        metrics["resolution_new_kept"] = float(
            instance.gt_new_memory_id in final_ids
        )
        # Old version removed (essential for clean resolve)
        metrics["resolution_old_removed"] = float(
            instance.gt_old_memory_id not in final_ids
        )
        # Both conditions satisfied (the core KU success criterion)
        metrics["resolution_clean_rate"] = float(
            metrics["resolution_new_kept"] == 1.0 
            and metrics["resolution_old_removed"] == 1.0
        )
    
    if not instance.is_conflict_instance:
        # Should not mistakenly remove the only relevant fact
        metrics["resolution_singleton_kept"] = float(
            instance.gt_new_memory_id in final_ids
        )
    
    return metrics
```

**解讀**：

- `resolution_new_kept`：resolve 後新版本是否還在 final context。若為 0 但 Level 1 的 `retrieval_new_recall` 為 1，表示 resolve 階段錯誤地移除了正確版本 (對應 F5 LLM false merge + 錯誤 timestamp argmax)。
- `resolution_old_removed`：resolve 後舊版本是否已被排除。若為 0 表示 resolve 沒有 successfully resolve 衝突（對應 F6 LLM false split 或結構性分群未涵蓋此事實）。
- `resolution_clean_rate`：同時滿足前兩者。這是 resolve 機制的**核心成功率指標**，相對於 LongMemEval / MemoryAgentBench 官方 KU Acc 而言，這是 model-independent 的：不受 inference LLM 品質影響，純粹反映 resolve 機制的表現。
- `resolution_singleton_kept`：對 no-conflict instance，resolve 不應誤殺 query-relevant 的唯一相關記憶。

### §5.4 Level 3: End-to-end Evaluation

**測量對象**：Stage 6 (Inference LLM Generation) 的輸出 `answer: str`

**Metrics**：

```python
def evaluate_end_to_end(
    answer: str,
    instance: EvalInstance,
    match_type: str = "exact"
) -> Dict[str, float]:
    """
    Measure final answer correctness against MQUAKE post-edit gold answer.
    """
    if match_type == "exact":
        is_correct = (answer.strip().lower() == instance.gold_answer.strip().lower())
    elif match_type == "contains":
        is_correct = (instance.gold_answer.strip().lower() in answer.strip().lower())
    else:
        raise ValueError(f"Unknown match_type: {match_type}")
    
    return {"ku_accuracy": float(is_correct)}
```

**解讀**：

- `ku_accuracy`：MemoryAgentBench FactConsolidation 的 official metric。這是 reportable 數字，可直接跟其他 baseline (Mem0、LightMem、Zep) 對比。

### §5.5 Diagnostic Isolation Chain

三層 metrics 形成 **失敗源 isolation chain**。對每筆 evaluation instance 觀察：

| Level 1 | Level 2 | Level 3 | 推論 | 建議行動 |
|---|---|---|---|---|
| 低 | 低 | 低 | Retrieval 是瓶頸 | 加入 recall augmentation (HyDE / Query2Doc) |
| 高 | 低 | 低 | Resolve 是瓶頸 | 調查 F2-F6 各自比例；針對占比最高的失敗模式改進 |
| 高 | 高 | 低 | Inference LLM 是瓶頸 | 跟我們的方法無關，是 LLM 本身的問題；或考慮加大 context size / 調整 prompt |
| 高 | 高 | 高 | 設計達成預期 | 確認在多個 instance subsets 上穩定 |
| 高 | 高 | 中 | 部分 inference 限制 + 部分 query-irrelevant 記憶污染 | 加入 query-irrelevant resolve metric 進一步 diagnose |

### §5.6 Per-failure-mode Breakdown

除了三層 metrics 外，建議同時記錄每個 instance 的 failure mode label 以便事後分析。對 `is_conflict_instance == True` 且 `resolution_clean_rate == 0` 的 instances，分類為：

| Label | 條件 |
|---|---|
| `F2_split_pair` | `gt_new` 跟 `gt_old` 的 (S, P) 不一致（從 triple metadata 直接判斷） |
| `F3_collision` | `gt_new` 跟 `gt_old` 的 (S, P) 一致，且有其他不同事實的 entry 也共享此 (S, P) |
| `F4_structural_wrong_winner` | 結構性分群選了非 `gt_new` 的 winner |
| `F5_llm_false_merge` | LLM grouping 把 `gt_new` 跟其他不同事實合群 |
| `F6_llm_false_split` | LLM grouping 把 `gt_new` 跟 `gt_old` 分到不同 groups/singletons |
| `F7_parse_fail` | LLM JSON 解析失敗 |
| `F8_pool_too_large` | LLM 池 size > 30 (即使 LLM 給出結果，可能品質下降) |

這個 breakdown 直接驅動 §4 中的 upgrade trigger 條件。

### §5.7 Aggregate Reporting Format

對整個 evaluation set，建議的 reporting 格式：

```
Phase 2 Evaluation Results
==========================
Total instances:                       N
  Conflict instances:                  N_conflict
  Singleton instances:                 N_singleton

Level 1: Retrieval Evaluation
  retrieval_new_recall:                X.XX
  retrieval_pair_recall:               X.XX (over N_conflict)
  retrieval_singleton_recall:          X.XX (over N_singleton)

Level 2: Resolution Evaluation  
  resolution_new_kept:                 X.XX (over N_conflict)
  resolution_old_removed:              X.XX (over N_conflict)
  resolution_clean_rate:               X.XX (over N_conflict)
  resolution_singleton_kept:           X.XX (over N_singleton)

Level 3: End-to-end Evaluation
  ku_accuracy:                         X.XX

Failure Mode Breakdown (over failed conflict instances):
  F2_split_pair:                       X% (n=...)
  F3_collision:                        X% (n=...)
  F4_structural_wrong_winner:          X% (n=...)
  F5_llm_false_merge:                  X% (n=...)
  F6_llm_false_split:                  X% (n=...)
  F7_parse_fail:                       X% (n=...)
  F8_pool_too_large:                   X% (n=...)

LLM Pool Size Distribution:
  mean:                                X.X
  median:                              X
  p90:                                 X
  >30 ratio:                           X.XX
```

---

## §6 Implementation Milestones

按依賴關係排序的 milestone 規劃。每個 milestone 應為可獨立 test 的最小可交付單元 (minimum viable deliverable)。

### M0: Phase 0 完成驗證 (prerequisite)

- 確認 Phase 0 的 triple extraction、(S, P) normalize、寫入 pipeline 已 working
- 確認 `MemoryItem.triple` 欄位在寫入後正確填入
- 建立 evaluation harness 的 conversation_turn → memory_id 映射機制

**完成條件**: 對 5 個 FactConsolidation instance 跑寫入流程，每筆 turn 都對應到 memory_id，且 conflict pair 的 (S, P) 在多數情況下一致（即 F2 rate 在可接受範圍）

### M1: Conditional Structural Router 實作 (§3.1)

- 實作 `conditional_structural_routing` 函式
- 撰寫 unit tests 涵蓋：
  - 全部有 triple 且都有對手的情境
  - 全部無 triple 的情境
  - 部分 triple singleton (S, P) 的情境
  - Empty candidates 的 edge case

**完成條件**: Unit tests 全通過

### M2: Structural Grouping + Argmax (§3.2)

- 實作 `structural_grouping_and_resolve` 函式
- Unit tests 涵蓋：
  - 唯一最新版本的 group
  - Timestamp tie 的 group
  - 多個 (S, P) groups 混合的情境

**完成條件**: Unit tests 全通過

### M3: LLM Dynamic Grouping Prompt 實作 (§3.3)

- 將 prompt template 寫入 Python 模組
- 實作 LLM call wrapper（呼叫 OpenAI / 其他 LLM provider）
- 實作 `parse_llm_grouping_output` 函式
- Unit tests 涵蓋：
  - 正常 JSON 解析
  - JSON 格式錯誤的 fallback
  - 部分 memory_id 對應不到的 sanity check

**完成條件**: 用 5 個合成的 grouping case 手動驗證 LLM 輸出符合預期格式且分群結果合理

### M4: Pipeline 整合 (§2.1–§2.6)

- 把 M1-M3 串接成完整 query-time pipeline
- 處理 timestamp tie escalation (Stage 3 → Stage 4)
- 處理 Stage 4 內 timestamp tie 的全保留邏輯
- 實作 final context assembly (Stage 5)
- 串接 Mem0 既有的 inference pipeline (Stage 6)

**完成條件**: 對 3 個 conflict instance、3 個 singleton instance 跑完整 pipeline，產出合理的 final answer

### M5: Evaluation Harness 實作 (§5)

- 實作三層 evaluation metrics
- 實作 failure mode breakdown
- 實作 aggregate reporting format

**完成條件**: 對 10 個 instance 跑完整 evaluation，生成完整 report

### M6: Pilot Test on FactConsolidation Subset

- 對 FactConsolidation-SH 的 50-100 個 instance 跑端到端
- 觀察三層 metrics 跟 failure mode breakdown
- 記錄 LLM 池 size 分布
- 基於 pilot 結果，決定下一步優先改進方向

**完成條件**: 拿到 pilot test report，identify 主要瓶頸層

### M7: Baseline Comparison

- 跑 Mem0 baseline (full update logic enabled) 在相同 instance subset
- 跑 LightMem / Zep baseline (若 implement)
- 對比三家在 Level 3 KU Acc 的差異
- 若 Phase 2 表現顯著優於 baseline → 進入 paper experiment 階段
- 若表現相當或落後 → 回到 failure mode breakdown，identify 改進方向

**完成條件**: 完整的 head-to-head 比較表

---

## §7 Open Questions and Future Upgrade Triggers

以下議題不在 Phase 2 範圍內，但記錄為觀測點，當對應 trigger 觸發時進入 Phase 3+ 議程。

### §7.1 Retrieval Quality

- **觸發條件**: Level 1 `retrieval_new_recall` < 80%
- **可選改進**: HyDE (Gao et al., ACL 2023)、Query2Doc (Wang et al., EMNLP 2023)、BM25 fusion、increasing top-K
- **優先序**: 高（若觸發則為下一階段首要改進目標）

### §7.2 (S, P) Normalization 升級

- **觸發條件**: F2 rate > 25%
- **可選改進**: Online predicate embedding clustering with threshold 0.85 (參考 vector quantization / hierarchical clustering 文獻)
- **優先序**: 中

### §7.3 LLM Pool Size 處理

- **觸發條件**: `llm_pool_size > 30` 的 case 佔比 > 30%
- **可選改進**: 
  - 簡單版：batch processing (30 ≤ pool ≤ 60 分兩 batch + cross-batch merge pass)
  - 進階版：embedding pre-cluster (pool > 60)
- **優先序**: 中（取決於 pilot test 觀測結果）

### §7.4 Active / Archive 物理分層

- **觸發條件**: Retrieval latency 在生產環境變成瓶頸 (e.g., > 500ms)
- **可選改進**: 將 archive store 物理分離到 secondary index，primary read from active，selective fallback to archive
- **優先序**: 低 (research phase 不必要)

### §7.5 Cross-mechanism Post-merge

- **觸發條件**: F2 rate + F5 rate + F6 rate 合計 > 15%
- **可選改進**: 在 Stage 3 跟 Stage 4 之後加入一個 LLM-based cross-pool merge step——對 `structural_winners` 跟 `dynamic_winners` 做一次合併檢查
- **優先序**: 中

### §7.6 Inference LLM Context Format

- **觸發條件**: Level 2 高、Level 3 不夠高 (resolve 機制 OK 但 inference 沒充分利用)
- **可選改進**: 在 context 中標註 `fact_summary`、加入 explicit "this is the latest version" 提示
- **優先序**: 低

### §7.7 Query-irrelevant 記憶的 Resolve 量測

- **觸發條件**: Level 3 KU Acc 系統性低於預期 (例如比 Level 2 `resolution_clean_rate` 低超過 15%)
- **可選改進**: 對 conversation 中所有 fact pair 做 global resolve metric (而非只看 query-relevant pair)，判斷是否有非相關記憶污染影響 inference
- **優先序**: 低（依賴 Level 3 表現決定是否需要）

---

## Appendix A: Component 依賴圖

```
[Phase 0 deliverables]
  MemoryItem dataclass
  Triple dataclass
  (S, P, O) normalize functions
  Mem0 fork with disabled ADD/UPDATE/DELETE/NOOP logic
  Write-time pipeline (memory extract → triple extract → commit)
  Unified storage (single tier)
                |
                v
[Phase 2 new components]
  Stage 1: Retrieval [Mem0 default]
                |
                v
  Stage 2: Conditional Structural Router
                |
                +--> structural_pool
                |        |
                |        v
                |    Stage 3: Structural Grouping + Argmax
                |        |
                |        +--> structural_winners
                |        +--> escalated_groups (timestamp tie)
                |                |
                |                v
                +-----> dynamic_pool + escalated_groups
                                 |
                                 v
                         Stage 4: LLM Dynamic Grouping
                                 |
                                 +--> dynamic_winners
                                 +--> singletons (treated as winners)
                                 +--> JSON parse fail fallback
                                 
  Stage 5: Final Context Assembly
    (structural_winners + dynamic_winners + singletons)
    filtered by candidates ranking
                |
                v
  Stage 6: Inference LLM [Mem0 default]
                |
                v
            answer
                |
                v
[Evaluation Harness]
  Level 1: Retrieval metrics (on candidates)
  Level 2: Resolution metrics (on final_context)  
  Level 3: End-to-end metrics (on answer)
  Failure mode breakdown
```

## Appendix B: Citation References

文獻引用標準 (對 paper 寫作使用)：

| Reference | Use in Phase 2 |
|---|---|
| Wang et al. (2024) "Astute RAG: Overcoming Imperfect Retrieval Augmentation and Knowledge Conflicts" (arXiv:2410.07176) | LLM dynamic grouping prompt 的 cluster-and-separate structure adapted from this |
| Zhong et al. (2023) "MQUAKE: Assessing Knowledge Editing in Language Models via Multi-Hop Questions" (EMNLP 2023) | Ground truth annotation 來源；Phase 2 evaluation metrics 的 fact-level 標註基礎 |
| Hu, Wang, McAuley (2026) "MemoryAgentBench: Evaluating Memory in LLM Agents via Incremental Multi-Turn Interactions" (ICLR 2026) | FactConsolidation 子集是基於 MQUAKE 構建；提供 evaluation 的具體 dataset structure |
| Hsu et al. (2025) "MADAM-RAG: Retrieval-Augmented Generation with Conflicting Evidence" (arXiv:2504.13079) | 對比 paradigm (multi-agent debate)；在 paper related work 中作為 contrast |
| Saxena et al. (2021) "Question Answering over Temporal Knowledge Graphs: CRONQUESTIONS" (ACL 2021) | Temporal KG 文獻 lineage；(s, p, o, t) 4-tuple 跟我們的 (S, P) 識別 + timestamp resolution 對應 |
| Tan et al. (2023) "TempReason: Towards Benchmarking and Improving the Temporal Reasoning Capability of LLMs" (ACL 2023) | Temporal reasoning evaluation 範式參考 |

