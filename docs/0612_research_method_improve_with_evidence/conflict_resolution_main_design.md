# U5 Conflict Resolution — Implementation Spec for Claude Code (已實作部分)

> **給 Claude Code 的閱讀指示**
> 這份文件描述我們要在 `MemoryAgentBench_original/mem0/` 上做的一個 **update component 改動**。
> 不要動 `agent.py`、inference prompt assembly、`conversation_creator.py` 或任何 benchmark 評分邏輯。
> 整份 spec 包含完整 prompt、新增函式、整合點、schema 改動、驗收 checklist。
> **第 12 節是 open questions**,你看完之後如果發現我們對 mem0 內部理解有誤、或實作細節有問題,請優先回報那邊列的點。

---

## 1. 研究脈絡

我們以 **Mem0** (Chhikara et al. 2025) 為 baseline,在 **MemoryAgentBench** 的 **FactConsolidation (FC)** 子任務上做評估。FC 的特性:

- input 是一連串帶序號的事實 (`[1]`、`[57]` ...),較大序號 = 較新事實
- 同一個 `(entity, attribute)` 會有多版本,新版本邏輯上覆蓋舊版本
- 評估時,query 要求模型根據「最新事實」回答,而不是 retrieve 到的任意版本

### 1.1 過去方法的結構性缺點

長期記憶系統的代表性工作中(Mem0, LangMem, MemoryOS, LightMem, Zep, A-Mem),Mem0 是最常被當作 baseline、設計也最有代表性的。它在 ingest 時做兩個 LLM call:

- **L1 抽取** (`FACT_RETRIEVAL_PROMPT`):從 input 抽取原子事實
- **L2 更新** (`DEFAULT_UPDATE_MEMORY_PROMPT`):對「新 fact × 既有 top-5」一次性裁決,輸出 `{ADD, UPDATE, DELETE, NONE}` 列表

這個設計有四個結構性問題:

1. **三件本該分開的事被綁在同一個 LLM call**:衝突偵測(這是不是衝突?)、衝突解析(該選哪個?)、寫入動作(怎麼改 store?)全部由 L2 在一次 tool-call 內完成,並 commit 成 destructive operation。任何環節判斷錯,store 立刻被永久污染。

2. **沒有時序訊號**:L2 的 prompt 從來沒被告知「哪個 fact 較新」。它只看語意相似度跟內容矛盾。在 FC 這種「序號最大為新」的場景下,序號訊號甚至在 L1 抽取階段就已經被剝離,L2 根本接觸不到。

3. **操作空間迫使 LLM 做 commit**:`{ADD, UPDATE, DELETE, NONE}` 四選一,沒有「我不確定」這個選項。當 LLM 沒把握時,它仍然會選一個,而選錯的代價是不可逆的。

4. **L1 抽取 prompt 偏向「個人偏好整理器」**:其原本設計目標是「記住使用者喜好/個資」,對世界知識類的事實傾向過濾掉。FC 的 input 大多是世界知識(`country X 的 capital`、`A 的發明者` 之類),這些 fact 在 L1 階段就有相當比例被當噪音丟棄。

其他系統的同類限制:LightMem 雖然把 destructive op 從 test-time 推遲到 sleep-time,但操作本身仍是不可逆的;Zep 用 bi-temporal KG,但更新延遲很大、storage overhead 嚴重(>600k tokens per conversation);A-Mem 著重 memory 之間的 link evolution,但對 conflict resolution 沒有顯式機制。三者都沒解決「destructive write-time conflict resolution」這個核心問題。

### 1.2 在 FC 上的具體 failure mode

我們對著 FC factconsolidation_sh_6k 跑 Mem0,觀察到下列具體失敗(這也是我們先前的實驗驗證結果):

- **抽取階段丟序號**:`[1] The capital of country X is Aville` 在抽取後變成 `"The capital of country X is Aville"`,序號 `[1]` 完全不見。下游 L2 失去裁決依據。
- **L2 對矛盾選 DELETE 或方向相反的 UPDATE**:當 `Aville`(舊)跟 `Bville`(新)都在 top-5 候選裡時,Mem0 經常 DELETE 新的 `Bville`(因為它跟既有 `Aville` 矛盾),或者 UPDATE 把 `Aville` 改成更籠統的描述,反而把「真正的最新事實」抹掉。
- **錯誤是不可恢復的**:DELETE 後 vector store 上就真的沒了。後續 query 不可能拿到 `Bville`,無論 retrieval top-k 設多大。
- **即使換成更強的 backbone 也沒救**:我們在 gpt-4o-mini 跟 gemini 3 flash-lite 上都觀察到同類失敗。LightMem 自己的 ablation (paper 附錄 K.2) 也驗證了類似結論——靠 prompt engineering tune 出更保守的 overwrite policy,在 FC-MH 上 ACC 維持在 4–5%,prompt 改了等於沒改。
- **Query template 跟實際 context 脫節**:FC 的 query template (`utils/templates.py:81`) 假設「knowledge pool 帶序號、按序號最大者裁決」,但實際送進 inference 的 context (`agent.py:579-582`) 是剝離序號、可能已被 L2 改寫的 facts。模型被叫去執行一個它根本沒有資料可執行的規則。
- **我們先前嘗試「凍結抽取 + 完美抽取 cache」隔離出 update component 後,失敗仍在**:這證明 FC 上的失分不是 extraction 的問題,而是 update component 結構性的問題。

### 1.3 我們的 insight 與設計原則

從上面的觀察推導出三個設計原則:

**(a) LLM 的能力是「判斷衝突類型」,不是「決定 store 操作」。**
「pears → peas」是 typo correction 還是 additional preference,只有 LLM 能語意判斷;但一旦判斷出類型,該做什麼操作是 mechanical 的,不該再讓 LLM 自由發揮。所以我們把 LLM 的角色從「決定 ADD/UPDATE/DELETE」收斂成「分類六類關係 + 給 reason」,操作交給 deterministic mapping。這樣 LLM 的判斷錯誤被限制在 *misclassification*,而非 *misexecution*。

**(b) 操作必須 information-preserving,新資訊永遠進得了 store。**
Mem0 的問題是 LLM 一錯就掉資料。我們的設計讓**任何 fact 都會被 ADD 進去**(除非分類為完全 DUPLICATE),而舊的 conflicting fact 只被標記 `status=superseded` 而非物理刪除。即使 LLM 判斷錯誤,新 fact 仍在 store 裡,失敗模式從「資料毀損」變成「兩個版本並存」——差別是 categorical 的:前者不可逆、後者可救。

**(c) Ordinal 是 universal temporal signal,不依賴 FC 特定的序號。**
我們用 ingestion order 給每筆 fact 一個 monotonically increasing 整數,大者為新。對 FC 而言,因為 chunk 按順序 ingest,ordinal 順序自動對齊原始 serial 順序;對任意對話/long-form scenario 都同樣適用。LLM 在分類時把 ordinal 當作判斷 SUPERSEDE 的 evidence(但必須搭配 mutual exclusivity 才足夠,單獨 ordinal 不能觸發 SUPERSEDE)。

這三個原則合起來定義了 U5 conflict resolution 的形狀:**LLM 只分類,deterministic 只執行,操作只 ADD 跟 supersede**。本次改動的核心 claim 是:在同樣的 extraction 條件下,把 update component 從 Mem0 的 `DEFAULT_UPDATE_MEMORY_PROMPT` 換成 U5,FC 上的 ACC 會有顯著提升,而且 vanilla path 行為完全不變(由 config flag 控制)。

---

## 2. 實驗設計與「vanilla path 必須保留」原則

我們要做的是一個 **opt-in 的新路徑**,由 config flag 切換,vanilla mem0 行為必須保留 **bit-identical**(同樣 input、同樣 seed 下,輸出 byte-by-byte 一致)。

實驗會做三組 run:

| 組別 | extraction | update component | 目的 |
|---|---|---|---|
| **Stage 1** | mem0 原生 `FACT_RETRIEVAL_PROMPT`(live) | mem0 原生 `DEFAULT_UPDATE_MEMORY_PROMPT` | vanilla baseline |
| **Stage 2a** | 我們的 L2 prompt + frozen cache + `ordinal` | mem0 原生 `DEFAULT_UPDATE_MEMORY_PROMPT` | 隔離 update component 的對照組 |
| **Stage 2b** | 同 2a | **U5 classification + deterministic mapping**(本次改動) | 主結果 |

關鍵:Stage 2a 跟 2b 共用同一份 extraction cache,**差別只在 update 邏輯**。所以這次你不需要動 extraction 端,只要確保 ingestion 從 cache 拿到的每個 fact 有 `ordinal` 欄位即可。

---

## 3. 改動範圍總覽

| 檔案 | 改動類型 | 內容 |
|---|---|---|
| `mem0/configs/prompts.py` | 新增 | 新增常數 `CONFLICT_CLASSIFICATION_PROMPT` |
| `mem0/configs/base.py`(或 MemoryConfig 所在處) | 新增 | 新增 `conflict_resolution: Literal["vanilla", "u5_classification"] = "vanilla"` |
| `mem0/memory/main.py` | 新增 + 重構 | 新增 3 個方法;重構 `_add_to_vector_store` 為分支;`_search_vector_store` 加 status filter |
| qdrant payload schema | 擴充 | 新增 6 個 metadata 欄位 |

**不要動**:`agent.py`、`conversation_creator.py`、`utils/templates.py`、`utils/eval_other_utils.py`、`main.py`(top-level)、任何 benchmark 評分邏輯。

mem0 既有的 file:line 錨點(來自我們的 FC walkthrough 文件,如果跟 repo 不一致請以 repo 為準):

- `mem0/memory/main.py:187-211` — extraction LLM call
- `mem0/memory/main.py:220-243` — top-5 candidate retrieval
- `mem0/memory/main.py:245-253` — update LLM call
- `mem0/memory/main.py:265-315` — 執行 ADD/UPDATE/DELETE/NONE
- `mem0/memory/main.py:457-552` — search
- `mem0/configs/prompts.py:14-59` — FACT_RETRIEVAL_PROMPT
- `mem0/configs/prompts.py:61-209` — DEFAULT_UPDATE_MEMORY_PROMPT
- `mem0/configs/prompts.py:291-333` — get_update_memory_messages

---

## 4. 新增 prompt:`CONFLICT_CLASSIFICATION_PROMPT`

放在 `mem0/configs/prompts.py` 檔尾,**內容逐字如下**(請完整貼,包括所有換行與空格):

```python
CONFLICT_CLASSIFICATION_PROMPT = """\
You are a memory conflict classifier for a long-term memory system.

You will be given:
1. ONE new fact extracted from the user's latest input, with an ordinal
   (a monotonically increasing integer; larger = more recent).
2. A list of existing memory entries that are semantically related to the
   new fact (top-k retrieved candidates), each with its own ordinal.

For EACH (new_fact, existing_entry) pair, classify the relationship.
You do NOT output any operation (ADD/UPDATE/DELETE). You only classify.
The system maps classifications to operations downstream.

==========================
CLASSIFICATION CATEGORIES
==========================

NO_RELATION
  The two facts are about unrelated things. The retrieval was a false positive.

DUPLICATE
  The new fact conveys the same information as the existing one with no
  additional detail.

ENRICHMENT
  The new fact extends or refines the existing fact WITHOUT contradicting it.
  Output a "merged_text" field combining them into a single richer fact.

COEXIST
  Both facts can simultaneously be true. Use this when the attribute can hold
  multiple values (preferences, hobbies, friends, places visited, etc.).
  *** DEFAULT TO COEXIST when you are not certain the attribute is single-valued. ***

SUPERSEDE
  The new fact contradicts the existing fact in a way that implies the existing
  one is no longer current. Use SUPERSEDE only if at least ONE of:
    (a) Explicit correction signal in the new fact ("actually", "I meant",
        "no longer", "used to but now", "the new X is Y", etc.).
    (b) The attribute is single-valued by nature (current capital, current
        employer, current location, current age, current spouse, etc.).
    (c) The new fact has a STRICTLY LARGER ordinal AND the two values are
        mutually exclusive on the same attribute.

UNCERTAIN
  You cannot confidently classify. This is a VALID and ENCOURAGED output.
  Prefer UNCERTAIN over guessing SUPERSEDE.

==========================
CRITICAL RULES
==========================

1. Be CONSERVATIVE with SUPERSEDE. Wrong SUPERSEDE causes information loss;
   wrong COEXIST only causes redundancy. Prefer the latter.
2. Ordinal is EVIDENCE for SUPERSEDE case (c), NOT sufficient by itself.
   Mutual exclusivity of the attribute must also hold.
3. Each (new_fact, existing_entry) pair is judged INDEPENDENTLY.
4. Use only IDs provided in the input. Do not invent new IDs.

==========================
OUTPUT FORMAT (JSON only)
==========================

{
  "classifications": [
    {
      "new_id": "<new_fact_id>",
      "existing_id": "<existing_entry_id>",
      "relation": "NO_RELATION" | "DUPLICATE" | "ENRICHMENT" | "COEXIST" | "SUPERSEDE" | "UNCERTAIN",
      "reason": "<one short sentence>",
      "merged_text": "<required only when relation is ENRICHMENT>"
    }
  ]
}
"""
```

---

## 5. 新增 config flag

在 mem0 的 MemoryConfig(目前位於 `mem0/configs/base.py`,如果不在那邊請依實際位置)新增:

```python
from typing import Literal

class MemoryConfig(BaseModel):
    # ... 既有欄位保留 ...
    conflict_resolution: Literal["vanilla", "u5_classification"] = "vanilla"
```

**預設值必須是 `"vanilla"`**,確保不帶 config 跑時行為跟現在一模一樣。

---

## 6. 新增 3 個方法(都放 `mem0/memory/main.py`)

需要的 imports(若還沒有請加):

```python
import json
import uuid
import time
from mem0.configs.prompts import CONFLICT_CLASSIFICATION_PROMPT
```

(`remove_code_blocks` 應該已存在於 main.py 同檔或 utils,請沿用既有的)

### 6.1 `_classify_conflicts`

```python
def _classify_conflicts(
    self,
    new_fact_id: str,
    new_fact_text: str,
    new_fact_ordinal: int,
    existing_candidates: list,
) -> list:
    """
    Call LLM to classify the relationship between one new fact and its
    top-k existing candidates.

    existing_candidates: list of dicts {"id": str, "text": str, "ordinal": int}

    Returns: list of classification dicts as defined in
             CONFLICT_CLASSIFICATION_PROMPT's output schema.
    """
    if not existing_candidates:
        return []

    user_message = {
        "new_fact": {
            "new_id": new_fact_id,
            "text": new_fact_text,
            "ordinal": new_fact_ordinal,
        },
        "existing_entries": [
            {"existing_id": c["id"], "text": c["text"], "ordinal": c["ordinal"]}
            for c in existing_candidates
        ],
    }

    response = self.llm.generate_response(
        messages=[
            {"role": "system", "content": CONFLICT_CLASSIFICATION_PROMPT},
            {"role": "user", "content": json.dumps(user_message, ensure_ascii=False)},
        ],
        response_format={"type": "json_object"},
    )

    try:
        parsed = json.loads(remove_code_blocks(response))
        return parsed.get("classifications", [])
    except json.JSONDecodeError:
        # Failsafe: if LLM returns malformed JSON, treat as if no classification
        # → downstream will just ADD the new fact (information-preserving default).
        return []
```

### 6.2 `_apply_classifications`

```python
def _apply_classifications(
    self,
    new_fact_temp_id: str,
    new_fact_text: str,
    new_fact_embedding: list,
    new_fact_ordinal: int,
    classifications: list,
    user_id: str,
    metadata_base: dict,
) -> dict:
    """
    Apply LLM classifications to vector store deterministically.
    NEVER physically deletes; uses logical supersession via the `status` field.

    Returns: a dict describing what action was taken (for audit logging).
    """
    relations = [c["relation"] for c in classifications]

    # No candidates / no classification → straight ADD
    if not classifications:
        new_id = self._insert_new_fact(
            text=new_fact_text,
            embedding=new_fact_embedding,
            ordinal=new_fact_ordinal,
            user_id=user_id,
            metadata_base=metadata_base,
            supersede_targets=[],
            flagged_uncertain=False,
            merged_from_enrichment=False,
            classifications=[],
        )
        return {
            "action": "ADDED_NO_CANDIDATES",
            "new_id": new_id,
            "superseded_ids": [],
            "classifications": [],
        }

    # Pure-duplicate short-circuit: every classification says DUPLICATE → drop new
    if relations and all(r == "DUPLICATE" for r in relations):
        return {
            "action": "DROPPED_DUPLICATE",
            "new_id": None,
            "superseded_ids": [],
            "classifications": classifications,
        }

    # Collect supersession targets and possibly merged text (from ENRICHMENT)
    supersede_targets = []
    merged_text = None
    for c in classifications:
        r = c["relation"]
        if r in ("NO_RELATION", "DUPLICATE", "COEXIST", "UNCERTAIN"):
            continue
        elif r == "ENRICHMENT":
            supersede_targets.append(c["existing_id"])
            merged_text = c.get("merged_text") or new_fact_text
        elif r == "SUPERSEDE":
            supersede_targets.append(c["existing_id"])

    flagged_uncertain = any(c["relation"] == "UNCERTAIN" for c in classifications)
    final_text = merged_text if merged_text else new_fact_text
    final_embedding = (
        self.embedding_model.embed(final_text, memory_action="add")
        if merged_text
        else new_fact_embedding
    )

    # ALWAYS insert the new fact (unless it was pure duplicate, handled above)
    new_id = self._insert_new_fact(
        text=final_text,
        embedding=final_embedding,
        ordinal=new_fact_ordinal,
        user_id=user_id,
        metadata_base=metadata_base,
        supersede_targets=supersede_targets,
        flagged_uncertain=flagged_uncertain,
        merged_from_enrichment=(merged_text is not None),
        classifications=classifications,
    )

    # Logically supersede each target. DO NOT call _delete_memory.
    for old_id in supersede_targets:
        self.vector_store.update(
            vector_id=old_id,
            payload={
                "status": "superseded",
                "superseded_by": new_id,
                "superseded_at_ordinal": new_fact_ordinal,
            },
        )

    return {
        "action": "ADDED",
        "new_id": new_id,
        "superseded_ids": supersede_targets,
        "classifications": classifications,
    }
```

### 6.3 `_insert_new_fact`

```python
def _insert_new_fact(
    self,
    text: str,
    embedding: list,
    ordinal: int,
    user_id: str,
    metadata_base: dict,
    supersede_targets: list,
    flagged_uncertain: bool = False,
    merged_from_enrichment: bool = False,
    classifications=None,
) -> str:
    """Helper: insert a new active memory entry with U5 metadata."""
    new_uuid = str(uuid.uuid4())
    payload = {
        **metadata_base,
        "data": text,
        "user_id": user_id,
        "ordinal": ordinal,
        "status": "active",
        "supersedes": supersede_targets,
        "superseded_by": None,
        "superseded_at_ordinal": None,
        "flagged_uncertain": flagged_uncertain,
        "merged_from_enrichment": merged_from_enrichment,
        "classifications_log": classifications or [],
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    self.vector_store.insert(
        vectors=[embedding],
        ids=[new_uuid],
        payloads=[payload],
    )
    return new_uuid
```

---

## 7. `_add_to_vector_store` 的分支重構

把現有的 `_add_to_vector_store` 拆成兩個 sibling 函式,由 config flag 切換。

```python
def _add_to_vector_store(self, messages, metadata, filters, infer):
    # ===== Extraction stage =====
    # 沿用既有 extraction 邏輯(包含 frozen cache 路徑)。
    # 唯一要求:抽取出的 fact list 中每筆要有 "text" 跟 "ordinal" 兩個欄位。
    # ordinal 的取得方式:從 frozen cache 直接讀;若 cache 沒帶,則 fallback
    # 為當前 user_id namespace 的 monotonically increasing counter。
    new_retrieved_facts = self._extract_facts_with_ordinal(messages, filters)
    # ↑ 注意:_extract_facts_with_ordinal 是 wrapper,內部要不要叫 cache 還是 live LLM
    #   都行,但回傳必須是 [{"text": str, "ordinal": int}, ...]

    # ===== Branch on config =====
    if self.config.conflict_resolution == "u5_classification":
        return self._add_to_vector_store_u5(
            new_retrieved_facts, metadata, filters
        )
    else:
        # vanilla path: 保留 mem0 原本的 DEFAULT_UPDATE_MEMORY_PROMPT 流程,
        # 完全不動,bit-identical to current behavior.
        return self._add_to_vector_store_vanilla(
            new_retrieved_facts, metadata, filters
        )


def _add_to_vector_store_u5(self, new_retrieved_facts, metadata, filters):
    """U5 path: per-fact classification + deterministic mapping + soft supersession."""
    user_id = filters.get("user_id", "default")
    results = []

    for fact in new_retrieved_facts:
        fact_text = fact["text"]
        fact_ordinal = fact["ordinal"]
        fact_temp_id = str(uuid.uuid4())  # temporary id only for prompt referencing

        # Embed once; reuse for retrieval and (if no ENRICHMENT) insertion
        fact_embedding = self.embedding_model.embed(fact_text, memory_action="add")

        # Retrieve top-5 ACTIVE candidates (match mem0's top-5 to control this variable)
        raw_candidates = self.vector_store.search(
            query=fact_text,
            vectors=fact_embedding,
            limit=5,
            filters={**filters, "status": "active"},
        )
        existing_candidates = [
            {
                "id": c.id,
                "text": c.payload["data"],
                "ordinal": c.payload.get("ordinal", -1),
            }
            for c in raw_candidates
        ]

        # LLM classification
        classifications = self._classify_conflicts(
            new_fact_id=fact_temp_id,
            new_fact_text=fact_text,
            new_fact_ordinal=fact_ordinal,
            existing_candidates=existing_candidates,
        )

        # Deterministic mapping → store ops
        result = self._apply_classifications(
            new_fact_temp_id=fact_temp_id,
            new_fact_text=fact_text,
            new_fact_embedding=fact_embedding,
            new_fact_ordinal=fact_ordinal,
            classifications=classifications,
            user_id=user_id,
            metadata_base=metadata or {},
        )

        # Audit log
        self._append_u5_audit(
            user_id=user_id,
            new_fact_text=fact_text,
            new_fact_ordinal=fact_ordinal,
            candidates=existing_candidates,
            result=result,
        )

        results.append(result)

    return results


def _add_to_vector_store_vanilla(self, new_retrieved_facts, metadata, filters):
    """
    Vanilla mem0 update path. Must be bit-identical to the current
    implementation of _add_to_vector_store (lines 220-315).
    Just move the existing code here without behavioral change.
    The only adjustment: ignore `ordinal` field on facts (vanilla mem0 doesn't
    use it). All existing payloads remain unchanged.
    """
    # ... move existing top-5 retrieval + DEFAULT_UPDATE_MEMORY_PROMPT call +
    #     ADD/UPDATE/DELETE/NONE execution here verbatim ...
```

---

## 8. `_search_vector_store` 加 status filter

修改 `mem0/memory/main.py:457-552` 範圍內的 search 邏輯:

```python
def _search_vector_store(self, query, filters, limit):
    embeddings = self.embedding_model.embed(query, memory_action="search")

    if self.config.conflict_resolution == "u5_classification":
        # U5 path: only retrieve active (non-superseded) entries
        filters_with_status = {**filters, "status": "active"}
        # over-fetch 2x in case backend filter is post-filter
        effective_limit = limit * 2
        memories = self.vector_store.search(
            query=query,
            vectors=embeddings,
            limit=effective_limit,
            filters=filters_with_status,
        )
        return memories[:limit]
    else:
        # vanilla: unchanged behavior
        return self.vector_store.search(
            query=query, vectors=embeddings, limit=limit, filters=filters
        )
```

注意:`status` filter 只在 U5 路徑啟用,vanilla 路徑完全不加 filter,保持 bit-identical。

---

## 9. Vector store payload schema 擴充

qdrant payload 既有欄位(請以實際 code 為準):

```
data: str
user_id: str
hash: str
created_at: str
updated_at: str | null
```

U5 路徑新增:

```
ordinal: int                             # 該記憶被寫入時的 monotonically increasing 整數
status: "active" | "superseded"          # 預設 "active"
supersedes: list[str]                    # 此記憶覆蓋了哪些舊記憶的 id(forward link)
superseded_by: str | null                # 此記憶被哪個新記憶覆蓋了(backward link)
superseded_at_ordinal: int | null        # 被覆蓋時的新 fact ordinal,方便事後分析
flagged_uncertain: bool                  # LLM 在分類時有 UNCERTAIN
merged_from_enrichment: bool             # 此記憶是 ENRICHMENT 的 merged 版本
classifications_log: list[dict]          # 這次 insertion 的完整 classifications 紀錄
```

vanilla 路徑寫入的 payload 維持原樣,**不要**幫它補 `status` 之類的欄位——這會打破 bit-identical 的要求。如果之後 query 時遇到沒有 `status` 欄位的舊資料,filter 邏輯應該 default 視為 active(用 `.get("status", "active")` 處理)。

---

## 10. Audit log 規格

每次 `_add_to_vector_store_u5` 處理一個新 fact 後,append 一筆 JSONL 紀錄到:

```
{cwd}/logs/u5_audit_{user_id}.jsonl
```

(如果 directory 不存在,自動 mkdir。檔名禁止 path traversal,user_id 先做 sanitize。)

每筆紀錄格式:

```json
{
  "timestamp": "2026-06-12 17:00:00",
  "new_fact": {
    "text": "...",
    "ordinal": 42
  },
  "candidates": [
    {"id": "...", "text": "...", "ordinal": 7},
    {"id": "...", "text": "...", "ordinal": 12}
  ],
  "classifications": [
    {
      "new_id": "...",
      "existing_id": "...",
      "relation": "SUPERSEDE",
      "reason": "...",
      "merged_text": null
    }
  ],
  "result": {
    "action": "ADDED",
    "new_id": "...",
    "superseded_ids": ["..."]
  }
}
```

對應 helper:

```python
def _append_u5_audit(self, user_id, new_fact_text, new_fact_ordinal, candidates, result):
    import os, re
    safe_user_id = re.sub(r"[^A-Za-z0-9_\-]", "_", str(user_id))
    log_dir = os.path.join(os.getcwd(), "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, f"u5_audit_{safe_user_id}.jsonl")

    record = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "new_fact": {"text": new_fact_text, "ordinal": new_fact_ordinal},
        "candidates": candidates,
        "classifications": result.get("classifications", []),
        "result": {
            "action": result.get("action"),
            "new_id": result.get("new_id"),
            "superseded_ids": result.get("superseded_ids", []),
        },
    }
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
```

---

## 11. 驗收 checklist

以下每一項都應該能跑通,請逐項驗證後回報:

- [ ] `conflict_resolution` 在 MemoryConfig 中預設值為 `"vanilla"`
- [ ] 跑 mem0 不帶任何 config 改動時,行為與 main branch 的 mem0 **bit-identical**(同樣 input、同樣 OpenAI seed → 同樣 ACC、同樣 store 狀態)
- [ ] 設 `conflict_resolution="u5_classification"` 後:
  - [ ] `DEFAULT_UPDATE_MEMORY_PROMPT` 跟 `get_update_memory_messages` **完全不會被呼叫**(可用 monkey-patch + assertion 驗證)
  - [ ] vector store 上 **完全沒有 UPDATE 或 DELETE 操作**(只有 INSERT 跟 update_metadata)
  - [ ] 所有新 insert 的 entry 都有 `status="active"`
  - [ ] 被 supersede 的 entry 的 `status` 變成 `"superseded"`,且 `superseded_by` 指向正確的新 id
- [ ] search 在 U5 路徑下只回傳 `status="active"` 的 entry
- [ ] `logs/u5_audit_{user_id}.jsonl` 有正確寫入,每行是合法 JSON
- [ ] 在 FC factconsolidation_sh_6k 上跑通 end-to-end,得到一個 ACC 數字(不論高低,先確認 pipeline 不會 crash)

---

## 12. 給 Claude Code 的 open questions(請優先回報)

下列每一項是我們對 mem0 內部的 **假設**。如果你看完實際 code 發現有任何一個錯,請優先回報那個點,不要先動手實作:

1. **Vector store update API**:我們假設 qdrant 透過 `self.vector_store.update(vector_id=..., payload=...)` 可以只更新 payload(不重新 embed)。請確認這個 API 是否存在、簽名是否正確。如果 mem0 的 qdrant wrapper 是另一個 method 名(如 `update_payload`、`set_payload`),請告訴我們正確名稱。

2. **qdrant filter 行為**:我們假設 qdrant `search` 的 `filters` 是 **pre-filter**(在計算 similarity 前先過濾),所以才 over-fetch 2x 保險。請確認實際行為。如果是 pre-filter 那 over-fetch 可以拿掉。

3. **`metadata_base` 的真實內容**:mem0 現行的 `_add_to_vector_store` 中,payload 是怎麼組起來的?有沒有我們漏掉的必要欄位(如 `hash`)?請列出 vanilla payload 的完整 schema,我們會把它跟 U5 payload 對齊。

4. **`embedding_model.embed` 的簽名**:我們寫了 `self.embedding_model.embed(text, memory_action="add")`,這個是猜的。請確認實際呼叫方式。

5. **`llm.generate_response` 對 `response_format={"type": "json_object"}` 的支援**:mem0 既有 update path 已經用了這個 (`mem0/memory/main.py:245-253`),所以應該可用。請確認我們 U5 用同樣方式 OK。

6. **Extraction cache 的當前格式**:你那邊應該已經在處理 cache 加 `ordinal` 的事。請告訴我 cache 載入後,每個 fact 的實際 schema 長怎樣(欄位名),我們的 `_extract_facts_with_ordinal` wrapper 才能對齊。如果 cache 還沒有 `ordinal`,可以先 fallback 為 per-user_id monotonic counter(每次 INSERT 時 +1),但這要記得寫進 spec。

7. **Vanilla path 的 `_add_to_vector_store` 重構**:我把它叫 `_add_to_vector_store_vanilla`,但程式碼是「把現有的 220-315 行整段搬過來」。請確認搬移過程中沒有遺漏任何 side effect(如 logging、telemetry 等)。

8. **`conflict_resolution` 這個 config 怎麼從 yaml 傳進來**:agent.py 那邊 mem0 是怎麼讀 config 的?我們要不要在 `Structure_rag_gpt-4o-mini-mem0.yaml` 旁邊新增一個 `Structure_rag_gpt-4o-mini-mem0-u5.yaml`,只多一行 `conflict_resolution: u5_classification`?還是有更乾淨的方式?

9. **search 在 vanilla path 的 default behavior**:我們在 U5 path 加了 status filter。但 vanilla path 沒加。問題是:如果先用 U5 跑了一輪、留下了 `status=superseded` 的 entry,**之後切回 vanilla 路徑跑時**,vanilla 不會看 `status`,所以可能撈到我們 supersede 掉的舊資料。是否需要在 vanilla path 也加一個 default-active filter?或者規定 U5 跟 vanilla 必須用不同的 vector store collection?

10. **Failsafe 行為**:在 `_classify_conflicts` 裡,LLM 回傳 malformed JSON 時我們 fallback 為「沒有 classification → 純 ADD」。這個 fallback 行為要不要記到 audit log 裡?是否要 raise warning?

請對上面這些先回報你的判斷,我們對齊之後再開始實作。**特別是 (1) (3) (6) 三點如果跟我們的假設不一致,動手前一定要先溝通,否則整個 U5 path 會跑不起來。**

---

## 13. 不在這次 scope 內的事

下列項目雖然在我們的方法藍圖裡有,但 **這次不要做**,留給後續 PR:

- 改 extraction prompt 本身(L1 / FACT_RETRIEVAL_PROMPT 替換)
- intra-chunk 內部的 new × new 衝突 reduce
- offline / sleep-time consolidation pass
- 從 audit log 反向重建 store 的 recovery 工具
- 加 top-k 的 ablation(目前固定 top-5,跟 mem0 對齊)

這次 PR 只做 U5 update component 替換 + soft supersession + audit log。

---

# 14. As-built（Phase 1，destructive）— 與上方 spec 的差異

> 2026-06-12 落地版。為了**最快驗證核心設計（解耦 + ordinal）能否改善 FC**，Phase 1 刻意**先不做 soft supersession**，改用不可逆操作、重用 vanilla 既有執行原語。實作在 **`MemoryAgentBench/`（工作 repo，09 的 pipeline/cache 所在）**，不是 `_original`，以便與 09 直接 apples-to-apples。

| 項目 | 上方 spec（soft 版）| **Phase 1 as-built（destructive）** |
|---|---|---|
| 觸發 | config flag `conflict_resolution` | **env 變數 `MEM0_UPDATE_MODE=u5_classification`**（與既有 `MEM0_EXTRACTION_CACHE`/`MEM0_CAND_LOG_DIR` 同風格，零 yaml/agent.py 改動）|
| SUPERSEDE 操作 | soft：標 `status=superseded`（可逆）| **物理 `_delete_memory` 舊 + `_create_memory` 新**（重用 vanilla 原語，不可逆）|
| payload schema | 加 6 欄（status/superseded_by…）| **只加 1 欄 `ordinal: int`** |
| search filter | status=active | **不動**（無 status）|
| qdrant `set_payload` | 需要 | **不需要**（不做 soft → 不碰 `vector_store.update`，避開全量 upsert 問題）|
| ordinal | 同 | **chunk ingestion order**（同 chunk 同 ordinal；per-user_id 計數器，每次 `_add_to_vector_store` +1）|
| 候選池 / 單一 call / batch 結構 | 同 vanilla | **完全同 vanilla**（候選 = chunk 內所有 new fact + 各自池化 top-5；單一 LLM call）|

**程式落點（工作 repo `mem0/memory/main.py`）**：
- `__init__`：`self._u5_mode`（env）+ `self._u5_ordinal={}`（計數器）。
- 候選迴圈內 gated 記 `ord_by_uuid`（不動 vanilla 的 `retrieved_old_memory` 結構 → vanilla prompt 逐字不變）。
- **分支點 `main.py:328`**：`if self._u5_mode: return self._update_u5(...)`，在 `get_update_memory_messages`（vanilla）**被呼叫之前**就 return → vanilla path bit-identical。
- `_update_u5`：用 `get_conflict_classification_messages`（全新 prompt + 自有輸出 schema）→ 單一 LLM call → 解析 classifications → deterministic map → `_create_memory`(ADD，metadata 帶 ordinal)/`_delete_memory`(DELETE)。
- prompt：`mem0/configs/prompts.py` 的 `CONFLICT_CLASSIFICATION_PROMPT`（batched 版）+ `get_conflict_classification_messages`。

**deterministic mapping（不可逆）**：SUPERSEDE→DELETE舊+ADD新；ENRICHMENT→DELETE舊+ADD merged；COEXIST/NO_RELATION/UNCERTAIN→只ADD新；DUPLICATE→no-op。

**計時（smoke test）**：單次 classification call 隔離 ~2.26s（1.39–3.76s）。先前「update 慢」是多 chunk 序列 + rate limit，非單次呼叫。

---

# 15. 分析方法論（逐級漏斗，分母全標 m/n）

> 目的：把「conflict-pair 答錯」逐級篩到**單一成因 = update component 把 external memory store 操作錯（write-time）**，與正交成因（檢索 R / 答題 Z / same-chunk 抽取）分離。每一級分母明確、跨方法（LCA / mem0-vanilla / mem0-ours）並排。
> 分析器：`scripts/fc_funnel_full.py <L>`。資料源：`results.json`(EM) + `rag_retrieved/.../query_*.json`(top-100) + `ingestion_context_0.jsonl`(replay) + `sh_<L>_RUN_gt.json`(GT old/new fact text + conflict_type)。

| Stage | 做什麼 | 分母 | 證明 | 怎麼算 |
|---|---|---|---|---|
| 0 | overall EM | /100 | 總體差距 | results.json `exact_match` |
| 1 | EM by 題型 CP/SF | /CP、/SF | gap 集中在 conflict-pair | GT `conflict_type` 切 |
| 2 | 檢索狀態 × Acc | 各 bucket n | **答錯 ⟺ new 沒進 top-100** | top-100 含 new/old fact text → new_only/both/old_only/neither；SF: fact_in/out |
| 跨方法 | CP 檢索狀態分布 | /CP | **ours 的 wins/losses** | 同上，兩方法並排 |
| 3 | CP 答錯題：new **在不在 final store** | CP-wrong | 分「write-time 寫壞」vs「下游 R/Z」 | replay ingestion 事件 → final store；new 在庫但沒檢到=R，檢到卻錯=Z，不在庫=write-time |
| 4 | write-time 再細分 | CP-wrong | old_only / neither{D0,D1,D2} | replay：ever-added vs in-final |
| T | final-store 狀態轉移 vanilla→ours | /CP | **per-pair 贏在哪、輸在哪** | 兩方法 final store 並排比對 |

**文字比對註記**：new/old fact 與儲存文字用正規化 + containment 比對（frozen cache + 逐字 ADD，09 已驗 99%）；U5 ENRICHMENT 的 merged_text 可能對不上 → 少量 both 可能實為 new_only（保守低估）。

---

# 16. Phase-1 證據（FC-SH 6k，gpt-4o-mini）+ claim 對齊

### 16.1 Stage 0/1 — EM
| 方法 | overall | conflict-pair | single-fact |
|---|---|---|---|
| vanilla(matched rerun) | 37/100 | 23/74 | 14/26 |
| **ours(U5)** | **80/100** | **56/74** | **24/26** |
- vanilla rerun 與 09 的 37% 逐字吻合 → 確認 matched baseline、改動未污染 vanilla。

### 16.2 Stage 2 — 檢索狀態 × Acc（證明：答錯 ⟺ new 沒檢索到）
| bucket | vanilla Acc | ours Acc |
|---|---|---|
| new_only | 21/21 | 41/42 |
| both | 2/3 | 15/29 |
| old_only | 0/21 | —(0) |
| neither | 0/29 | 0/3 |
| SF fact_in | 13/13 | 23/23 |
| SF fact_out | 1/13 | 1/3 |
→ new 進 top-100 → ~100%；old_only/neither → 0%。

**跨方法 CP 檢索狀態分布（/74）**：
| 方法 | new_only | both | old_only | neither |
|---|---|---|---|---|
| vanilla | 21 | 3 | 21 | 29 |
| ours | 42 | 29 | **0** | 3 |

### 16.3 ★ Stage 3/4 — 失敗模式翻轉（核心結果）
| 成因 | vanilla(錯51) | ours(錯18) |
|---|---|---|
| old_only（write-time）| 21 | 1 |
| neither D0 omission | 12 | 0 |
| neither D1 舊刪+新沒進 | 15 | 0 |
| neither D2 新被摧毀 | 2 | 2 |
| R/Z 下游 | 1 (Z) | **15 (Z)** |
| **write-time 寫壞 store** | **50/51 = 98%** | **3/18 = 17%** |

> **vanilla 98% 的衝突失敗在 write-time update component**（留舊/毀新），非檢索非答題 → **結構性 claim 成立**。
> **U5 把 write-time corruption 50→3，失敗模式翻轉成 83% 是 inference 層 Z**（新版已在庫且檢索到，答題在新舊並存下挑錯）→ **瓶頸從「寫入層不可逆毀損」搬到「查詢層版本消歧」**。

### 16.4 final-store 轉移矩陣（vanilla→ours，n=74）
```
van\ours   new_only  both  old_only  neither
new_only       13     8        0       0
old_only        9    10        1       1    (19/21 修好)
neither        19     9        0       1    (28/29 修好)
both            1     2        0       0
```
- 修好 47 對（new 進庫）；**`new_only→old_only/neither` = 0**（store 層從不弄丟新版）→ 實證原則 (b) information-preserving。
- 唯一代價 `new_only→both` = 8（新仍在、舊也留 → 答題負擔），即 4 題 EM 退步來源。

### 16.5 U5 分類/操作分布（6k，12 chunks）
relations：COEXIST 130 / SUPERSEDE 101 / NO_RELATION 15 / DUPLICATE 12 / ENRICHMENT 8。
mapped ops：ADD 334 / SUPERSEDE(DELETE舊+ADD新) 101 / DUPLICATE(drop) 12 / ENRICHMENT 8。
對比 09 記錄的 vanilla 6k：ADD 190 / **NONE 554** / UPDATE 57 / DELETE 43（大量 NONE＝不作為＝留舊）。

### 16.6 Claim 對齊體檢
| 結構 claim(§1.1) | 對策 | 資料支持 |
|---|---|---|
| #1 耦合/不可逆 commit | decouple + always-ADD | ✅ 強：neither 29→1；new 零破壞損失 |
| #3 強制 commit 無「不確定」| 六類分類含 UNCERTAIN/COEXIST | ✅ 中強：保守選 both 而非誤刪 |
| **#2 無時序訊號** | ordinal | ⚠️ **未隔離**：U5 = decouple+ordinal 綁一起 → 需 ordinal on/off ablation 才能宣稱 ordinal 因果 |
| #4 抽取偏個資 | frozen cache 控制 | 刻意不測 |

### 16.6b ★ 主軸鐵證：old_only 中「衝突可見卻沒解」的比例（`scripts/oldonly_visibility.py`）
把 vanilla 的 old_only 再切：新 fact 的 top-5 候選**有沒有撈到舊版**（撈到＝衝突攤在 update 面前）。
| | 6k | 32k |
|---|---|---|
| old_only | 21 | 19 |
| **VISIBLE（舊在候選、卻沒 UPDATE）= 純衝突解析失敗** | **18/21=85%** | **18/19=94%** |
| INVISIBLE（舊沒撈到，正交檢索/same-chunk）| 3 | 1 |
→ old_only 失敗 85–94% 是「update 看得到衝突卻沒解」，非候選沒撈到。old_only 已隱含「沒 UPDATE」（否則 store 會是 new_only）。這批正是 U5 餵同候選+ordinal 後解掉的。

### 16.6c D1/D2 機制驗證（`scripts/neither_mechanism.py`，逐事件 replay）
vanilla neither 子類的「曾入庫版本如何被移除」：
| | 6k | 32k |
|---|---|---|
| D1 via **DELETE**（該 UPDATE 卻 DELETE 舊、新沒進）| 13/15 | 9/10 |
| D1 via UPDATE_overwrite（舊被改寫成無關文字）| 2/15 | 1/10 |
| D2 新被摧毀（以 DELETE 為主）| 2 | 4(3 DELETE+1 overwrite) |
→ 與 16.6b 合併讀：vanilla 兩大衝突失敗＝同一個錯的兩面——正確動作都是 `UPDATE old→new`，LLM 直接出操作時 **old_only=錯選 NONE、D1=錯選 DELETE**。四選一、單次 commit、不可逆 → 任一誤選正解永遠進不了庫。

### 16.7 FC-SH 32k（趨勢；CP=65 SF=35）
- EM：vanilla 51/100（CP 24/65, SF 27/35）→ ours **66/100**（CP 38/65, SF 28/35）。（vanilla 32k=51 ≠ 09 的 62%，scale 漂移 → 比自跑 baseline。）
- Stage2 retrieval×Acc 同樣鐵證：vanilla new_only 22/22、old_only 0/19、neither 0/22。
- Stage3/4 write-time corruption：vanilla **38/41=93%** → ours **12/27=44%**（仍翻轉，但殘留 write-time 比 6k 多）。ours 下游 R5+Z10=15/27。
- 轉移矩陣（n=65）：old_only 15/19 修好、neither 16/19 修好；**但 `new_only→old_only/neither = 5`（6k=0）= Phase-1 物理刪除的累積代價**；neither D2「新被摧毀」6k 2→32k 5。
- **結論**：U5 隨長度仍贏（+15pp）且壓低 write-time corruption，但**不可逆刪除的代價隨長度浮現 → 強化 Phase 2 soft supersession 動機**；另檢索飽和 R 隨 store 變大出現（正交問題）。

### 16.8 FC-SH 64k（2026-06-13 補完；CP=66 SF=34；全自跑 matched）
- EM：**LCA 65**（09: 62）/ **vanilla 52**（09: 45，CP 29/66, SF 23/34）/ **ours 53**（CP 34/66, SF **19/34 倒退**）→ **增益收斂 +1**。
- Stage2 vanilla：new_only 20/21、both 6/6、old_only 0/14、neither 3/25（3 例參數知識/巧合）；ours：new_only 27/28、both 7/12、old_only 0/5、neither 0/21。
- Stage3/4 vanilla（錯37）：old_only 16 / D0 3 / D1 8 / D2 3 / R 6 / Z 1 → **write-time 30/37=81%**。
  ours（錯32）：old_only 5 / D0 3 / D2 6 / **R 12** / Z 6 → write-time 14/32=44%，**下游 18/32=56%（R 主導）**。
- 機制：old_only VISIBLE **16/16=100%**（85→94→100 遞增）；D1 via DELETE **9/9**。
- 轉移矩陣（n=66）：修好 27 對；**`new_only→old_only/neither`=7**（0→5→7 累積）；`new_only→both`=1。
- final-store：vanilla 27/6/16/17 → ours 35/17/5/9；「new 在庫」33/66→52/66。
- **解讀**：write-time 修復跨長度成立（corruption 81→44%），但增益被「檢索飽和 R=12（always-ADD store 變大；SF fact_out 15→18 同因）+ 累積誤刪 7」吃掉 → **Phase 2 = scale 必要**：soft supersession 一石二鳥（可逆 + 檢索過濾 superseded 縮小有效 store）、query-time ordinal 消歧處理殘餘 both。

---

# 17. 下一步（依優先序）

1. ✅ ~~FC-SH 32k / 64k~~（已補完，見 §16.7/16.8）。
2. **Phase 2 成套設計（64k 後升級為 scale 必要）**——設計釐清（2026-06-13，使用者點出）：**soft supersession 單獨存在 ≠ 救誤刪**——若 retrieval 硬過濾 superseded，誤標正解的 EM 結局＝物理刪除。必須成套：
   - (a) `status=superseded` 標記 + **檢索附 supersession 鏈**（勝者連帶其壓掉的版本與 ordinal）→ 消歧 + 誤標保險；
   - (b) active 衝突/低信心時 fallback 撈 superseded；
   - (c) **檢索層打 R 的主招＝supersession 鏈擴展**（舊版被檢回時沿 `superseded_by` 拉進新版；輔以 active dedup / diversity）。⚠️ 修正：「過濾 superseded 縮小有效 store」對 Phase-1 不成立——Phase 1 已物理刪除（64k 刪 1140 後 active 仍 2934、top-100 覆蓋 3.4%），soft+過濾只是維持同樣 active 集合；store 尺寸對照：vanilla 180/1101/2179 vs ours 342/1534/2934（1.9/1.4/1.35×）；
   - (d) **DUPLICATE drop 加 deterministic 守門**（battlefield_recovery B2：誤判 DUPLICATE 丟新版的退步 32k 4、64k 5，比 over-SUPERSEDE 還多，且被 drop 的從未入庫、標記救不了——僅文字/embedding 近同一才允許 drop）；
   - (e) query-time ordinal 消歧處理殘餘 both（Z）。
3. LCA 天花板補上 CP/SF 分題型欄（選配）。

# 18. Future work（本次 deferred，不在當前收斂範圍）

1. **ordinal on/off ablation（6k）— 已降級為「確認點」**：兩條獨立證據顯示 write-time ordinal 近乎惰性 →（i）候選恆嚴格更舊（0 例外）使 SUPERSEDE case (c)「ordinal 較大」恆真、零鑑別力；（ii）**LLM 的 SUPERSEDE reason 引用時序僅 0%/0%/2%（6k/32k/64k），實際靠「同屬性互斥+矛盾」case (b)（引用 77–84%）**。故預測 ablation 的 write-time EM delta ≈ 0；write-time 增益歸因「解耦+分類法+保守預設+NEW/EXISTING 角色框架」。**設計定論：ordinal = write-time STAMP、query-time USE；prompt 的 case (c) 為 vestigial（可移除或保留無害）。** write-time stamp 仍必要（否則 query-time 無時序可用，vanilla 即此缺陷）。
2. **Patch 1 — ordinal prompt 去 FC-specific 措辭**：把 `CONFLICT_CLASSIFICATION_PROMPT` 中 ordinal 的說明改成「**由 storage system 在記錄時賦予的單調遞增整數，反映 WHEN THE FACT ENTERED THE SYSTEM，與輸入文字無關；id 僅為內部 reference handle、無時序/語意意義**」，避免讀者誤以為 ordinal = FC 序號。
   - 新措辭（節錄）：`ordinal: a monotonically increasing integer ASSIGNED BY THE STORAGE SYSTEM when a fact is recorded. Larger ordinal = recorded later. Note: ordinal reflects WHEN THE FACT ENTERED THE SYSTEM, not anything in the input text.`
3. **Patch 2 — 加 non-FC 範例**（OUTPUT FORMAT 之前）：用日常偏好/狀態變更例子讓通用性自證，與 benchmark 無關。
   - 例：`{text:"User now drinks tea", ordinal:47}` vs `{text:"User likes coffee", ordinal:3}` → 同屬性互斥+ordinal 較大+"now" → **SUPERSEDE**；`{text:"User likes pears"}` vs `{text:"User likes peas"}` → "likes" 多值、無修正訊號 → **COEXIST**。
   - 效果：prompt 本身證明 U5 不是 FC-specific。