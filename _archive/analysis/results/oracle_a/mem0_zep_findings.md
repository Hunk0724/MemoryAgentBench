# mem0 / Zep 在 FC 任務上的觀察記錄

> 實驗日期：2026-04-20
> 目的：觀察 mem0、Zep 等現有記憶方法在知識衝突任務（FC-SH、FC-MH 6k）上的表現，
> 以協助 HippoRAG-v2 在知識衝突上的改進方向分析。

---

## 觀察 1: mem0 在 FC 上幾乎完全失效（pilot run, 2 題）

### 實驗設置

| 項目 | 值 |
|---|---|
| Config | `Structure_rag_gpt-4o-mini-mem0.yaml`（原生設定，未修改） |
| Dataset | `Factconsolidation_sh_6k`（6k context, 455 facts） |
| Chunk size | 4096（mem0 默認） |
| Retrieve num | 100 |
| Ingestion | 2 chunks（把 6k context 分成兩段餵進去） |
| 題數 | 2 題 pilot |

### 關鍵現象

**Ingestion 返回空結果**：

```
vector_results: {'results': []}
vector_results: {'results': []}
```

兩個 chunk 都成功送進 `memory.add()`，但 mem0 **抽取到 0 個 facts**。

**Retrieval 也是空的**：

```
relevant_memories: {'results': []}
memory_length: 0
```

**LLM 只能靠 parametric knowledge 回答**，答案全部是 real-world 正確答案，而非 MQuAKE 的 counterfactual 新事實：
- query_0: goaltender 問題，mem0 答「Ice Hockey」（world knowledge），但 GT 是「pesäpallo」

---

## 問題根因：mem0 的 fact extraction 只針對使用者個人資訊

查 `mem0/configs/prompts.py` 的 `FACT_RETRIEVAL_PROMPT`，它明確限定抽取範圍：

> **Types of Information to Remember**:
> 1. Store Personal Preferences
> 2. Maintain Important Personal Details (names, relationships)
> 3. Track Plans and Intentions
> 4. Remember Activity and Service Preferences
> 5. Monitor Health and Wellness Preferences
> 6. Store Professional Details
> 7. Miscellaneous Information Management (favorite books, movies, brands)

而且 few-shot examples **直接展示要排除通用知識**：

```
Input: There are branches in trees.
Output: {"facts": []}        ← 通用事實 → 空

Input: Hi, my name is John. I am a software engineer.
Output: {"facts": ["Name is John", "Is a Software engineer"]}   ← 個人資訊 → 抽取
```

所以 mem0 看到 FC 的 455 個通用事實（如「goaltender is associated with pesäpallo」），
**整體判定為「不值得記憶的通用知識」，返回 `{"facts": []}`**。

---

## 初步結論（待驗證）

**假說**：mem0 在 FC 任務上失效的原因是其 fact extraction prompt 專門為 personal assistant
場景設計，無法處理通用知識更新。

**這意味著**：
- mem0 的衝突處理機制（ADD/UPDATE/DELETE）從未被觸發，因為根本沒有 facts 進入 memory
- FC 看到的「失敗」不是 mem0 衝突處理能力不足，而是它壓根沒嘗試記這些資訊
- 對 HippoRAG-v2 的比較會失去意義，因為兩者測試的能力本質不同

---

## 驗證結果（Sanity check, 2026-04-20）

直接呼叫 `mem0.memory.main.Memory` 做 5 個 minimal test，**完全證實假說**：

| Test 輸入 | 預期 | 實際 Facts 抽取 |
|---|---|---|
| `"Hi, my name is John. I have a cat named Luna."` | 個人資訊，應抽取 | ✅ 2 facts: `[ADD] Name is John`, `[ADD] Has a cat named Luna` |
| `"I've had my cat Luna for 5 months."` | 個人資訊更新，應抽取 | ✅ 1 fact: `[ADD] Has a cat named Luna for 5 months` |
| `"Luna has been with me for 9 months now."`（對同 user） | **應觸發 UPDATE** | ✅ 1 fact: **`[UPDATE] Luna has been with the user for 9 months`** |
| `"goaltender is associated with the sport of pesäpallo."` | 通用知識，應忽略 | ✅ **0 facts 抽取** |
| `"1. goaltender is associated with... 2. The author of Our Mutual Friend is..."` | 通用知識，應忽略 | ✅ **0 facts 抽取** |

**Search 也 work**：查 `"How long have I had Luna?"` 回傳 `"Luna has been with the user for 9 months"`
（已是更新後的值，舊的 5 個月被成功 UPDATE 掉）。

### 結論（已驗證）

1. **mem0 的 fact extraction 與 UPDATE 機制在其設計範圍內運作正常**
2. **mem0 確實會忽略通用知識事實**（即使多個事實串在一起也一樣）
3. **FC 任務上 mem0 的失敗原因確認**：是 prompt 設計導致通用知識被拒絕進入 memory，
   衝突偵測邏輯從未被觸發

## 後續步驟

### Step 2: 用 `custom_fact_extraction_prompt` 在 FC 上重跑

確認假說後，嘗試用 custom prompt 覆寫 mem0 的預設 extraction 邏輯，讓它接受通用知識，
然後觀察：
- mem0 能否偵測到 FC 裡的衝突對？
- ADD / UPDATE / DELETE 操作的分布？
- 修改後的 Acc 和錯誤模式

---

## 資料路徑

| 檔案 | 說明 |
|---|---|
| `outputs/gpt-4o-mini-mem0/Conflict_Resolution/factconsolidation_sh_6k_..._k100_chunk4096_results.json` | pilot 2 題結果 |
| `outputs/rag_retrieved/Structure_rag_mem0/k_100/factconsolidation_sh_6k/chunksize_4096/ingestion_context_None.jsonl` | ingestion log（空 results） |
| `outputs/rag_retrieved/Structure_rag_mem0/k_100/factconsolidation_sh_6k/chunksize_4096/query_{0,1}_context_0.json` | retrieved memories（空） |

---

## 後續待做

- [ ] 跑 mem0 on LongMemEval knowledge-update（驗證 Step 1）
- [ ] 確認假說後，用 custom prompt 在 FC 上重跑（Step 2）
- [ ] 跑 Zep on FC-SH 10 題 pilot（觀察是否有類似問題）
- [ ] Zep 若也失效，走類似的 LongMemEval 驗證流程
