```python
NEVER mark facts as duplicates if they have key differences, particularly around numeric values, dates, or key qualifiers.

IMPORTANT constraints:
- duplicate_facts: ONLY idx values from EXISTING FACTS (NEVER include FACT INVALIDATION CANDIDATES)
- contradicted_facts: idx values from EITHER list (EXISTING FACTS or FACT INVALIDATION CANDIDATES)
- The idx values are continuous across both lists (INVALIDATION CANDIDATES start where EXISTING FACTS end)

<EXISTING FACTS>
{context['existing_edges']}
</EXISTING FACTS>

<FACT INVALIDATION CANDIDATES>
{context['edge_invalidation_candidates']}
</FACT INVALIDATION CANDIDATES>

<NEW FACT>
{context['new_edge']}
</NEW FACT>

You will receive TWO lists of facts with CONTINUOUS idx numbering across both lists.
EXISTING FACTS are indexed first, followed by FACT INVALIDATION CANDIDATES.

1. DUPLICATE DETECTION:
   - If the NEW FACT represents identical factual information as any fact in EXISTING FACTS, return those idx values in duplicate_facts.
   - If no duplicates, return an empty list for duplicate_facts.

2. CONTRADICTION DETECTION:
   - Determine which facts the NEW FACT contradicts from either list.
   - A fact from EXISTING FACTS can be both a duplicate AND contradicted (e.g., semantically the same but the new fact updates/supersedes it).
   - Return all contradicted idx values in contradicted_facts.
   - If no contradictions, return an empty list for contradicted_facts.

<EXAMPLE>
EXISTING FACT: idx=0, "Alice joined Acme Corp in 2020"
NEW FACT: "Alice joined Acme Corp in 2020"
Result: duplicate_facts=[0], contradicted_facts=[] (identical factual information)

EXISTING FACT: idx=1, "Alice works at Acme Corp as a software engineer"
NEW FACT: "Alice works at Acme Corp as a senior engineer"
Result: duplicate_facts=[], contradicted_facts=[1] (same relationship but updated title — contradiction, NOT a duplicate)

EXISTING FACT: idx=2, "Bob ran 5 miles on Tuesday"
NEW FACT: "Bob ran 3 miles on Wednesday"
Result: duplicate_facts=[], contradicted_facts=[] (different events on different days — neither duplicate nor contradiction)
</EXAMPLE>
""",
        ),
    ]
```

---

## 執行端（實際操作記憶庫）— 來源：`graphiti`

> 上面是「LLM 判斷」prompt（`resolve_edge`，只吐 `duplicate_facts` / `contradicted_facts` 兩個關係標籤）。
> 以下補「候選檢索 → 操作時間戳執行 → commit」。
> **判斷層特性：LLM 只輸出關係標籤、操作下游決定論化 → 屬第二派。**

### 0. 候選檢索（找相關既有 edge）— `utils/maintenance/edge_operations.py`（`resolve_extracted_edges`）
兩路撈：
- **去重候選**：`EntityEdge.get_between_nodes(driver, src, tgt)` — 只取「同一對 source/target 之間」的既有 edge（縮小搜尋空間）。
- **失效候選**：`search(..., EDGE_HYBRID_SEARCH_RRF)` — embedding+BM25 混合檢索，撈語義相近、不限端點的 edge（找會被新事實否定者）。

### 1. 時間戳執行（你先前缺的部分）— `edge_operations.py:538-573` `resolve_edge_contradictions()`
**LLM 不設時間戳；這一步是純時間邏輯。** 對 LLM 判為 contradicted 的既有 edge，僅在「舊 edge 的 `valid_at` 早於新 edge 的 `valid_at`」時，把它設為失效：

```python
def resolve_edge_contradictions(resolved_edge, invalidation_candidates) -> list[EntityEdge]:
    invalidated_edges = []
    for edge in invalidation_candidates:
        edge_invalid_at_utc        = ensure_utc(edge.invalid_at)
        resolved_edge_valid_at_utc = ensure_utc(resolved_edge.valid_at)
        edge_valid_at_utc          = ensure_utc(edge.valid_at)
        resolved_edge_invalid_at_utc = ensure_utc(resolved_edge.invalid_at)
        if ( ... 時間區間不重疊 ... ):
            continue
        elif (edge_valid_at_utc is not None
              and resolved_edge_valid_at_utc is not None
              and edge_valid_at_utc < resolved_edge_valid_at_utc):   # 新事實較新
            edge.invalid_at = resolved_edge.valid_at                 # 設失效起點
            edge.expired_at = edge.expired_at if edge.expired_at is not None else utc_now()
            invalidated_edges.append(edge)
    return invalidated_edges
```
注意：**edge 本體不刪**，只設 `invalid_at` / `expired_at` 兩欄（bi-temporal 記帳）。

### 2. Commit（write-time）
`resolve_extracted_edges()` 回傳 `(resolved_edges, invalidated_edges, new_edges)`；在 `add_episode` 內 `entity_edges = resolved_edges + invalidated_edges` 一起經 `add_nodes_and_edges_bulk()` **立即寫入資料庫**（Cypher），非延後到 read-time。

### 可逆性判定
| 操作 | 圖中行為 | 可逆性 | commit 時機 |
|---|---|---|---|
| edge 去重 | 複用既有 edge、附新 episode | 可逆 | write-time |
| **edge 失效** | 設 `invalid_at`/`expired_at`，**本體保留** | **✗ 實務不可逆**：無任何程式會清回 `invalid_at`，失效 edge 被檢索過濾（fire-and-forget） | write-time |
| **node 合併**（`resolve_extracted_nodes`/`dedupe_nodes`） | 被併 node 直接消失、不入庫，無 `IS_DUPLICATE_OF` 記錄 | **✗ 完全不可逆**：無 un-merge | write-time |

**結論：Zep 雖將「執行」決定論化、且 edge 失效是非破壞記帳（保留歷史），但 `invalid_at` 一旦設定即永不回頭（fire-and-forget），實務上仍不可逆；node 合併則為破壞性、完全不可逆。determinism 在 LLM 判斷的下游，救不了上游誤判。**

> 補充：node 合併（entity resolution）是另一條知識更新路徑，prompt 在 `prompts/dedupe_nodes.py`，執行在 `utils/maintenance/node_operations.py:627`，此檔尚未涵蓋其 prompt 全文，如需可另補。