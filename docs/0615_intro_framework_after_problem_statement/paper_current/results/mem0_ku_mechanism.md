# mem0 KU mechanism — write-time coupled update（canonical 機制檔）

> **用途**:與 [`zep_ku_resolution_bitemporal.md`](zep_ku_resolution_bitemporal.md) 對稱的 mem0 版機制參考。說明 mem0 write-time KU 的 **prompt input/output、per-chunk 組裝、四操作 apply 語意、失效路徑**,供 E-B(pool_state 歸因)與 E-D(error-mode case study)直接引。
> **與既有檔分工**:本檔 = **機制/prompt 參考**(code-grounded);[`mem0_event_taxonomy_gt4o.md`](mem0_event_taxonomy_gt4o.md) = **經驗 case 分類**(M1/M2,event-log elimination)。兩者互引不重複。
> **code source**:`mem0/configs/prompts.py`(prompts)、`mem0/memory/main.py`(組裝 + apply)。行號以本 repo patched 本地 `mem0/` 為準。
> **日期**:2026-07-07。

---

## §1 為何 pool_state 對 mem0 有效(與 Zep 對比)

mem0 的 KU 決策**物理改變 stored text**:ADD 建新、UPDATE 原地覆寫、DELETE 實刪。reader 看到的 pool = 存活的記憶文字 → **KU 結果直接反映在 pool 文字**。因此文字 pool_state(PP-New/Both/OldOnly/Missing)是 mem0 的**有效 mediator**(ours 亦然:query-time 解成 new-only 文字)。

**只有 Zep 例外**(search 回傳含 invalid edges、KU 在 bi-temporal 不在文字,見 `matcher_specification.md` §3.4)。→ E-B 分工:**mem0/ours 用文字 pool_state;Zep 用 bi-temporal**;跨方法只在 E2E Acc 對齊。

---

## §2 Write-time pipeline(extract → update,update 為 **per-chunk 一次 call**)

### Stage 1 — 抽取（`FACT_RETRIEVAL_PROMPT`）
chunk → LLM → `{"facts": ["...", ...]}`（personal-info organizer few-shot;`main.py:252-270`）。

### Stage 2 — 更新（`DEFAULT_UPDATE_MEMORY_PROMPT` + `get_update_memory_messages`）
候選組裝（`main.py:328-409`）:
1. 對**每個** new fact,vector search 撈 **top-5**(`limit=5`)相似既有記憶。
2. 全部候選 **union + dedup** 成一個扁平 pool;id **重編號 0..N**(另存 `temp_uuid_mapping` 對照回真實 uuid）。
3. **一次 LLM call**,輸入 = 整個 pool + 這個 chunk 的**所有** new facts,一起判。

> ⚠ **顆粒度重點**:不是「每個 new fact 各一次 call / 各一個 event」;是**整個 chunk 的所有 new facts + 全候選 pool 塞進同一 prompt、一次輸出**。

### 輸入給 LLM 什麼（`get_update_memory_messages`）
`DEFAULT_UPDATE_MEMORY_PROMPT`（四操作定義 + guidelines + few-shot）後接:
```
Below is the current content of my memory ...:
{retrieved_old_memory}      # [{"id":"0","text":...}, ...]  重編號後扁平 pool
The new retrieved facts ...:
{new_retrieved_facts}       # 這個 chunk 抽出的所有 new fact 字串 list
```
**❗ 無任何時間/ordinal 信號**——vanilla prompt 不知道哪個 fact 較新(`prompts.py:344` 註解自陳)。這與 ours `CONFLICT_CLASSIFICATION_PROMPT`(顯式餵 ordinal）是根本差異。

### 輸出什麼
一個 JSON,**key 為 memory entry(不是 new fact)**:
```json
{"memory":[
  {"id":"0","text":"...","event":"NONE"},
  {"id":"1","text":"...","event":"UPDATE","old_memory":"..."},
  {"id":"2","text":"...","event":"DELETE"},
  {"id":"3","text":"<new fact>","event":"ADD"}
]}
```
結構 = 一個 reconciliation:**每條既有記憶(0..N)各給一個 event**,**未被對應到的 new fact 以新 id + `ADD` 出現**。新事實要靠 LLM **主動補 ADD entry**;漏掉 = 靜默消失。

### Apply loop（`main.py:460-508`,確定性執行）
- `ADD` → `_create_memory(text)` 建新記憶
- `UPDATE` → `_update_memory(uuid=map[id], data=text)` **原地覆寫**(同 uuid、text 換成 LLM 給的 → 舊內容 GONE)
- `DELETE` → `_delete_memory(uuid=map[id])` 實刪(不可逆)
- `NONE` → noop

---

## §3 四操作的**實際 prompt 語意**(注意 DELETE-on-contradiction)

逐字要點（`DEFAULT_UPDATE_MEMORY_PROMPT`）:
- **ADD**:memory 沒有的新資訊 → 生新 id。
- **UPDATE**:「already present but **totally different**」→ 覆寫(同 id);或同資訊更詳細 → 留資訊多者。可能 LLM 重寫 text。
- **DELETE**:**「retrieved facts contain information that _contradicts_ the memory → delete it（既有那條）」**。→ **KU 的破壞路徑**:新舊矛盾時,指令是**刪舊**。
- **NONE**:已存在/不相關 → 不動(對 new fact = 沒被 emit ADD = 靜默 drop)。

**DELETE + ADD 是允許的但非原子**:apply loop 各自獨立執行,`{DELETE old}`+`{ADD new}` 兩條會照做。但這是**兩條各自的操作**,要 LLM **記得同時 emit**;漏 ADD → GT-new 消失。→ **可靠 KU 路徑是 UPDATE(單一原地操作),DELETE+ADD 是易碎路徑**。

---

## §4 失效路徑（機制層,對映 pool_state 與 M1/M2）

| pool_state（reader 所見）| mem0 event path | taxonomy |
| :--- | :--- | :--- |
| **PP-New**（正確 KU）| UPDATE(old→new) **或** DELETE(old)+ADD(new) 皆成功 | — |
| **PP-OldOnly** | old 留(NONE)+ new 被 NONE / 漏 ADD（world-prior 拒反事實）| **M1** |
| **PP-Missing** | old DELETE + new 沒 ADD（missing-ADD）/ cross-item cascade DELETE | **M2a / M2b** |
| **PP-OldOnly / Missing** | 人名等近似 → cross-item 靜默合併,new 沒獨立 ADD | **M2c** |
| **PP-Both** | 兩版都 ADD、沒偵測衝突（COEXIST-like）| — |

**根因(intro 掛點)**:mem0 把「判斷該不該 KU」與「執行 ADD 新+DELETE 舊」綁在**同一個 LLM output**,且**無時間信號** → 矛盾時要不要刪、刪哪邊,全由**語意 + world-prior** 決定;output 一旦有 completeness bug(漏 ADD / 多 DELETE / cross-item 混淆),記憶就損壞且 **query 時不可逆**。

**兩個只有 code 才看得到的失效**:
1. **hallucinated-id 靜默 drop**:UPDATE/DELETE 走 `temp_uuid_mapping[id]`,LLM 引用不存在的 id → KeyError → except 吞掉 → 操作消失(`main.py:483,497,507`;instrumentation `main.py:436-439` 專記 `hallucinated_ids`)。
2. **同 chunk 兩版共存**（GT-new + GT-old 同時在 new_fact_list):**與 Zep 不同**,mem0 一次 prompt **同時看到兩版**(Zep 同 chunk sibling 互不可見)。但無時間信號、且 few-shot 只教「new vs existing memory」沒教「兩個互斥的 new fact」→ 最可能**兩個都 ADD(PP-Both)**或 world-prior 挑一。

**M1/M2 分佈**（來自 `mem0_event_taxonomy_gt4o.md`,gpt-4o-mini×64k,24 個 PP-OldOnly/Missing wrong qids)：M1 = 11(46%)、M2 = 13(54%;M2a 3 / M2b 4-5 / M2c 5)。

---

## §5 三派對照（KU locus × 破壞性 × 時間信號）

| 維度 | mem0 | Zep | ours |
| :--- | :--- | :--- | :--- |
| KU 位置 | **write-time commit** | write-time labeling（延後判讀）| **query-time** |
| 判斷單位 | **per-chunk 一次**(所有 new × 全 pool) | per-edge（只跟已存圖比）| per-query |
| 時間信號 | **無**（語意 + world-prior） | 有（valid/invalid_at）| 有（ordinal，確定性 argmax）|
| 對舊版 | **實刪 / 覆寫**（不可逆）| 保留 + 標 invalid（軟）| 全版本保留 |
| pool_state mediator | ✅ 文字 | ❌（改 bi-temporal）| ✅ 文字 |
| 主要失效 | coupled-output bug + world-prior（M1/M2）| 80% additive 不偵測 | —（write 不做跨筆判斷）|

---

## §6 分析用法（E-B / E-D)

- **E-B（結果層,現在就能講）**:mem0 用文字 pool_state × Acc（crosstab canonical）→ 「丟分因 pool 落 PP-OldOnly/Missing」。
- **E-D（機制層,現在就能講）**:引 M1/M2（event-log elimination,`mem0_event_taxonomy_gt4o.md`）→ world-prior vs coupled-update 兩根因。
- **direct 證據（僅按需）**:`MEM0_CAND_LOG_DIR` env 重跑,dump `update_prompt`/`raw_response`/`parsed_actions`/`hallucinated_ids`（`main.py:429-458`）。**只在**：① reviewer 追問 elimination 可靠性;② 某 case study 要秀 raw LLM decision(NONE / 漏 ADD / 幻覺 id)時才跑（~$0.3 / 30min）。**非 E-B 說明 error modes 的前置**。

---

## §7 rigor caveat

- event log **只記成功 side-effect events**;**看不到** NONE decision、raw prompt、被幻覺 id 吞掉的操作 → elimination 能推「被靜默拒絕」,但分不清 NONE / missing-ADD / hallucinated-drop 哪種。要區分需 §6 的 direct 證據。
- 本檔行號依 patched 本地 `mem0/`;upstream mem0ai 版本可能不同(尤其 `_update_u5`/instrumentation 為本 repo patch)。
- 數字一律回引 `objective_data_consolidated.md`（E2E）與 `mem0_event_taxonomy_gt4o.md`（M1/M2 分佈）;本檔不重列易 stale 的 per-qid 數。
