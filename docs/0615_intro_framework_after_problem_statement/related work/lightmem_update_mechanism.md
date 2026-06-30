```python
UPDATE_PROMPT = """
You are a memory management assistant.
Your task is to decide whether the target memory should be updated, deleted, or ignored
based on the candidate source memories.

Decision rules:
1. Update: If the target memory and candidate memories describe essentially the same fact/event but are not fully consistent (e.g., candidates provide more details, refinements, or clarifications), update the target memory by integrating the additional information.
2. Delete: If the target memory and candidate memories contain a direct conflict, the candidate memories (which are more recent) take precedence. Delete the target memory.
3. Ignore: If the target memory and candidate memories are unrelated, no action is needed. Ignore.

Additional guidance:
- Use only the information provided. Do not invent details.
- Your operation should always be applied to the target memory. Do not modify or correct the content inside the candidate memories.

The output must be a JSON object with the following structure:
{
  "action": "update" | "delete" | "ignore",
  "new_memory": { ... }   // only required when action = "update"
}

Example 1:
Target memory: "The user likes coffee."
Candidate memories:
- "The user prefers cappuccino in the mornings."
- "Sometimes the user drinks espresso when working late."
- "The user avoids decaf."

Output:
{
  "action": "update",
  "new_memory": "The user likes coffee, especially cappuccino in the morning and espresso when working late, and avoids decaf."
}

Example 2:
Target memory: "The user enjoys playing video games."
Candidate memories:
- "The user mostly plays strategy games."
- "They often spend weekends gaming with friends."
- "The user used to enjoy puzzle games but less so now."

Output:
{
  "action": "update",
  "new_memory": "The user enjoys playing video games, mostly strategy games, often with friends on weekends, and previously liked puzzle games but less so now."
}

Example 3:
Target memory: "The user currently lives in New York."
Candidate memories:
- "The user moved to San Francisco in 2023."
- "They mentioned enjoying the Bay Area weather."
- "The user's new workplace is in downtown San Francisco."

Output:
{
  "action": "delete"
}

Example 4:
Target memory: "The user is learning to cook Italian food."
Candidate memories:
- "The user recently started practicing yoga."
- "They bought a new bicycle for commuting."
- "The user enjoys watching sci-fi movies."

Output:
{
  "action": "ignore"
}

Here is a new target memory along with several candidate memories. Please decide the appropriate action (update, delete, or ignore) based on the given rules.

"""
```

---

## 執行端（實際操作記憶庫）— 來源：`LightMem`

> 上面是「LLM 判斷」prompt（`UPDATE_PROMPT`）。以下補組裝、批次時機與實際操作。
> **判斷層特性：LLM 直接吐操作（update/delete/ignore）+ 自己改寫 `new_memory`，無關係標籤 → 與 mem0 同屬第一派。差別只在「target-anchored + offline 批次」。**

### 0. 更新時機：offline 批次（非 online 即時）— `memory/lightmem.py`
寫入時新記憶先入庫、可檢索但**未判衝突**；更新延後到使用者主動呼叫的兩步批次：
- `construct_update_queue_all_entries()` (`lightmem.py:457`)：為每條舊記憶算 top-k 候選、存 `update_queue`（僅計算，不改內容）
- `offline_update_all_entries(score_threshold=0.9)` (`lightmem.py:539`)：逐條掃描，對有候選者呼叫 LLM 判斷
> 預設 `update="offline"`（`configs/base.py`）；`online` 目前為空佔位（`return None`）。

### 1. 組裝（target vs candidates）— `factory/memory_manager/openai.py:379-405`
與 mem0 方向相反：以**單條舊記憶為 target**、相關記憶為 candidates 餵入。
```python
def _call_update_llm(self, system_prompt, target_entry, candidate_sources):
    target_memory = target_entry["payload"]["memory"]
    candidate_memories = [c["payload"]["memory"] for c in candidate_sources]
    # → LLM 回 {"action": "update"|"delete"|"ignore", "new_memory": "..."}
```

### 2. LLM 輸出後的操作分派 + 執行 — `memory/lightmem.py:609-624`
```python
action = updated_entry.get("action")
if action == "delete":
    with write_lock:
        self.embedding_retriever.delete(eid)                 # 硬刪 target
elif action == "update":
    new_payload = dict(payload)
    new_payload["memory"] = updated_entry.get("new_memory")  # 覆寫 memory 欄
    vector = entry.get("vector")
    with write_lock:
        self.embedding_retriever.update(vector_id=eid, vector=vector, payload=new_payload)
```
底層（qdrant）`factory/retriever/embeddingretriever/qdrant.py:193`：
```python
def delete(self, vector_id: int):
    self.client.delete(collection_name=self.collection_name,
                       points_selector=PointIdsList(points=[vector_id]))  # 硬刪
```

### 可逆性判定
| 操作 | 向量庫行為 | 可逆性 | commit 時機 |
|---|---|---|---|
| ignore | 不動 | — | — |
| **update** | 覆寫 `payload["memory"]`（保留 `original_memory`/`compressed_memory`，但被覆寫的當前值丟失） | **✗ 破壞性** | offline 批次 |
| **delete** | qdrant 硬刪 target | **✗ 不可逆** | offline 批次 |

**結論：LightMem 的 update/delete 仍為破壞性、不可逆 commit；offline 批次只延後了那一刀的時機，未讓操作本身可逆。**