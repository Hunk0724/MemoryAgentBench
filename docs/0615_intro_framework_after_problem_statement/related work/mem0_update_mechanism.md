```python
DEFAULT_UPDATE_MEMORY_PROMPT = """You are a smart memory manager which controls the memory of a system.
You can perform four operations: (1) add into the memory, (2) update the memory, (3) delete from the memory, and (4) no change.

Based on the above four operations, the memory will change.

Compare newly retrieved facts with the existing memory. For each new fact, decide whether to:
- ADD: Add it to the memory as a new element
- UPDATE: Update an existing memory element
- DELETE: Delete an existing memory element
- NONE: Make no change (if the fact is already present or irrelevant)

There are specific guidelines to select which operation to perform:

1. **Add**: If the retrieved facts contain new information not present in the memory, then you have to add it by generating a new ID in the id field.
- **Example**:
    - Old Memory:
        [
            {
                "id" : "0",
                "text" : "User is a software engineer"
            }
        ]
    - Retrieved facts: ["Name is John"]
    - New Memory:
        {
            "memory" : [
                {
                    "id" : "0",
                    "text" : "User is a software engineer",
                    "event" : "NONE"
                },
                {
                    "id" : "1",
                    "text" : "Name is John",
                    "event" : "ADD"
                }
            ]

        }

2. **Update**: If the retrieved facts contain information that is already present in the memory but the information is totally different, then you have to update it. 
If the retrieved fact contains information that conveys the same thing as the elements present in the memory, then you have to keep the fact which has the most information. 
Example (a) -- if the memory contains "User likes to play cricket" and the retrieved fact is "Loves to play cricket with friends", then update the memory with the retrieved facts.
Example (b) -- if the memory contains "Likes cheese pizza" and the retrieved fact is "Loves cheese pizza", then you do not need to update it because they convey the same information.
If the direction is to update the memory, then you have to update it.
Please keep in mind while updating you have to keep the same ID.
Please note to return the IDs in the output from the input IDs only and do not generate any new ID.
- **Example**:
    - Old Memory:
        [
            {
                "id" : "0",
                "text" : "I really like cheese pizza"
            },
            {
                "id" : "1",
                "text" : "User is a software engineer"
            },
            {
                "id" : "2",
                "text" : "User likes to play cricket"
            }
        ]
    - Retrieved facts: ["Loves chicken pizza", "Loves to play cricket with friends"]
    - New Memory:
        {
        "memory" : [
                {
                    "id" : "0",
                    "text" : "Loves cheese and chicken pizza",
                    "event" : "UPDATE",
                    "old_memory" : "I really like cheese pizza"
                },
                {
                    "id" : "1",
                    "text" : "User is a software engineer",
                    "event" : "NONE"
                },
                {
                    "id" : "2",
                    "text" : "Loves to play cricket with friends",
                    "event" : "UPDATE",
                    "old_memory" : "User likes to play cricket"
                }
            ]
        }

3. **Delete**: If the retrieved facts contain information that contradicts the information present in the memory, then you have to delete it. Or if the direction is to delete the memory, then you have to delete it.
Please note to return the IDs in the output from the input IDs only and do not generate any new ID.
- **Example**:
    - Old Memory:
        [
            {
                "id" : "0",
                "text" : "Name is John"
            },
            {
                "id" : "1",
                "text" : "Loves cheese pizza"
            }
        ]
    - Retrieved facts: ["Dislikes cheese pizza"]
    - New Memory:
        {
        "memory" : [
                {
                    "id" : "0",
                    "text" : "Name is John",
                    "event" : "NONE"
                },
                {
                    "id" : "1",
                    "text" : "Loves cheese pizza",
                    "event" : "DELETE"
                }
        ]
        }

4. **No Change**: If the retrieved facts contain information that is already present in the memory, then you do not need to make any changes.
- **Example**:
    - Old Memory:
        [
            {
                "id" : "0",
                "text" : "Name is John"
            },
            {
                "id" : "1",
                "text" : "Loves cheese pizza"
            }
        ]
    - Retrieved facts: ["Name is John"]
    - New Memory:
        {
        "memory" : [
                {
                    "id" : "0",
                    "text" : "Name is John",
                    "event" : "NONE"
                },
                {
                    "id" : "1",
                    "text" : "Loves cheese pizza",
                    "event" : "NONE"
                }
            ]
        }
"""
def get_update_memory_messages(retrieved_old_memory_dict, response_content, custom_update_memory_prompt=None):
    if custom_update_memory_prompt is None:
        global DEFAULT_UPDATE_MEMORY_PROMPT
        custom_update_memory_prompt = DEFAULT_UPDATE_MEMORY_PROMPT

    return f"""{custom_update_memory_prompt}

    Below is the current content of my memory which I have collected till now. You have to update it in the following format only:

    ```
    {retrieved_old_memory_dict}
    ```

    The new retrieved facts are mentioned in the triple backticks. You have to analyze the new retrieved facts and determine whether these facts should be added, updated, or deleted in the memory.

    ```
    {response_content}
    ```

    You must return your response in the following JSON structure only:

    {{
        "memory" : [
            {{
                "id" : "<ID of the memory>",                # Use existing ID for updates/deletes, or new ID for additions
                "text" : "<Content of the memory>",         # Content of the memory
                "event" : "<Operation to be performed>",    # Must be "ADD", "UPDATE", "DELETE", or "NONE"
                "old_memory" : "<Old memory content>"       # Required only if the event is "UPDATE"
            }},
            ...
        ]
    }}

    Follow the instruction mentioned below:
    - Do not return anything from the custom few shot prompts provided above.
    - If the current memory is empty, then you have to add the new retrieved facts to the memory.
    - You should return the updated memory in only JSON format as shown below. The memory key should be the same if no changes are made.
    - If there is an addition, generate a new key and add the new memory corresponding to it.
    - If there is a deletion, the memory key-value pair should be removed from the memory.
    - If there is an update, the ID key should remain the same and only the value needs to be updated.

    Do not return anything except the JSON format.
    """
```

---

## 執行端（實際操作記憶庫）— 來源：`MemoryAgentBench_original/mem0`

> 上面是「LLM 判斷」一半（prompt + 組裝）。以下補「實際操作記憶庫」一半。
> **判斷層特性：LLM 直接吐出操作（ADD/UPDATE/DELETE/NONE），無關係標籤、無 decoupling → 屬第一派。**

### 0. 候選檢索（找相關舊記憶）— `memory/main.py:222-236`
對每條新 fact 用 embedding 搜 **top-5** 既有記憶，去重後組成候選池餵給 LLM。

```python
for new_mem in new_retrieved_facts:
    messages_embeddings = self.embedding_model.embed(new_mem, "add")
    existing_memories = self.vector_store.search(
        query=new_mem, vectors=messages_embeddings, limit=5, filters=filters,
    )
    for mem in existing_memories:
        retrieved_old_memory.append({"id": mem.id, "text": mem.payload["data"]})
```

### 1. LLM 輸出後的操作分派 — `memory/main.py:267-311`
LLM 回傳的每個 `event` 直接觸發對應的破壞性操作，**write-time 立即執行**。

```python
for resp in new_memories_with_actions.get("memory", []):
    if resp.get("event") == "ADD":
        memory_id = self._create_memory(data=resp.get("text"), ...)
    elif resp.get("event") == "UPDATE":
        self._update_memory(memory_id=temp_uuid_mapping[resp["id"]], data=resp.get("text"), ...)
    elif resp.get("event") == "DELETE":
        self._delete_memory(memory_id=temp_uuid_mapping[resp.get("id")])
    elif resp.get("event") == "NONE":
        logging.info("NOOP for Memory.")
```

### 2. UPDATE → 原地覆寫（破壞性）— `memory/main.py:692-733`
舊文本/embedding 被**直接覆蓋**；history 表只留「前一版 → 新版」一筆，再次 UPDATE 即二次覆寫、中間值不可回溯。

```python
def _update_memory(self, memory_id, data, existing_embeddings, metadata=None):
    existing_memory = self.vector_store.get(vector_id=memory_id)
    prev_value = existing_memory.payload.get("data")
    new_metadata["data"] = data                         # 覆寫文本
    ...
    embeddings = self.embedding_model.embed(data, "update")
    self.vector_store.update(                            # 原地覆寫 vector + payload
        vector_id=memory_id, vector=embeddings, payload=new_metadata,
    )
    self.db.add_history(memory_id, prev_value, data, "UPDATE", ...)  # 只留 1 筆前值
```
底層（chroma）`vector_stores/chroma.py:172`：
```python
self.collection.update(ids=vector_id, embeddings=vector, metadatas=payload)  # in-place
```

### 3. DELETE → 硬刪（不可逆）— `memory/main.py:735-742`
vector 從庫中**完全移除**（非 soft-delete flag）；history 表記 `is_deleted=1` 僅供審計、不可檢索。

```python
def _delete_memory(self, memory_id):
    existing_memory = self.vector_store.get(vector_id=memory_id)
    prev_value = existing_memory.payload["data"]
    self.vector_store.delete(vector_id=memory_id)                 # 硬刪
    self.db.add_history(memory_id, prev_value, None, "DELETE", is_deleted=1)
```
底層（chroma）`vector_stores/chroma.py:156`：
```python
self.collection.delete(ids=vector_id)                            # 硬刪
```

### 可逆性判定
| 操作 | 向量庫行為 | 可逆性 | commit 時機 |
|---|---|---|---|
| ADD | insert | 可逆（有 history） | write-time |
| **UPDATE** | 原地覆寫 embedding+payload | **✗ 破壞性**（舊 embedding 丟失） | write-time |
| **DELETE** | 硬刪 vector（history 留審計列） | **✗ 不可逆**（向量庫永久移除） | write-time |

**結論：mem0 的 UPDATE/DELETE 為破壞性、不可逆的 write-time commit；LLM 直接定操作，無中介關係層。**