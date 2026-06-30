# Zep 衝突機制獨立分析方法論

> **目的**:在不修改 Zep 任何設定的條件下,系統性量化 Zep 的「temporal-knowledge-graph supersession」機制在 FC-SH / FC-MH 任務上的實際運作情況——重點不是「Zep vs HippoRAG」,而是「Zep 自己的衝突解決機制究竟做到了什麼、在哪裡失敗」。

---

## 1. Zep 衝突機制概覽

### 1.1 Write-time(ingestion 階段)

每個 FC-{SH,MH} 6k context 對應一張 Zep graph(per-context 隔離,見 [agent.py:662-664](../agent.py#L662-L664)):

```python
user_id   = f"user_{context_id}_{sub_dataset}"
graph_id  = f"graph_{context_id}_{sub_dataset}"
thread_id = f"thread_{context_id}_{sub_dataset}"
```

對於 6k context(455 句事實),MAB 將其包成 **「使用者-助理多輪對話」**(見 [utils/templates.py:81](../utils/templates.py#L81)):

```text
Dialogue between User and Assistant {time_stamp}
<User> The following context is the facts I have learned: {context}  <Assistant> Got it.
```

每個 chunk(chunk_size=512 → 12 chunks)一輪對話,以 `client.thread.add_messages` 與 `client.graph.add` 雙寫進 Zep。

Zep 內部 LLM 對這些對話做:
1. **Entity / edge 抽取**:把 "X is associated with Y" 這種句子轉成 graph edge(主體 X、客體 Y、關係 R)
2. **Temporal annotation**:每條 edge 帶 `valid_at`(此事實出現的時間點)、`invalid_at`(被後續事實覆蓋的時間點,初始為 `null`)
3. **Supersession**:當後續對話加入相同 (X, R, ?) 的新事實 Y' 時,前一條 edge 的 `invalid_at` 被填上,新 edge 的 `valid_at` 為當前時間,`invalid_at=null`

### 1.2 Retrieval-time(query 階段)

對每個 query,呼叫 `client.graph.search(graph_id, query, scope=...)` **三次**,分別取得三個獨立的 top-10:
- `edges`(top-10):事實邊(含 `fact`、`valid_at`、`invalid_at`)
- `nodes`(top-10):實體節點(`name` + `summary`,summary 通常嵌入該實體的代表事實)
- `episodes`(top-10):原始對話片段(含序號的 chunk 文字)

LLM 在推理時會同時收到三段內容(見 [methods/zep.py:10-30](../methods/zep.py#L10-L30) 的 TEMPLATE):

```text
# These are the most relevant facts and their valid date ranges.
# format: FACT (Date range: from - to)
{facts}                           ← edges,date range 透露 invalid_at
# These are the most relevant entities
# ENTITY_NAME: entity summary
{entities}                        ← nodes
# These are the most relevant episodes.
{episodes}                        ← raw chunk content
```

Zep 預設行為:**不過濾 `invalid_at != null` 的 edge**(讓 LLM 自己根據時間戳判斷哪些事實還有效),但 `invalid_at` 仍以 date range 形式附在 fact text 後傳遞給下游 LLM,作為 supersession 訊號。

> **重要**:supersession 訊號(`invalid_at`)**只存在於 edges scope**。nodes/episodes 提供的是「事實是否還能被 LLM 看到」的覆蓋率,不帶時間訊號。

### 1.3 LLM 在 inference 時看到的完整 prompt 架構

Zep 在 FC 任務上發送給 LLM 的訊息有 system + user 兩段(見 [methods/zep.py:114-129](../methods/zep.py#L114-L129)):

```text
─── SYSTEM ──────────────────────────────────────────
You are a helpful expert assistant answering questions from users based
on the provided context.

─── USER ────────────────────────────────────────────
Your task is to briefly answer the question. You are given the following
context from the previous conversation. If you don't know how to answer
the question, abstain from answering.

  [retrieved_context — by compose_search_context]
  FACTS and ENTITIES represent relevant context to the current conversation.

  # These are the most relevant facts and their valid date ranges.
  # format: FACT (Date range: from - to)
    - goaltender is associated with the sport of ice hockey.
        (2026-04-20T17:56:41Z - present)                       ← invalid_at
    - point guard is associated with the sport of basketball.
        (date unknown - present)
    ... (10 edges total — supersession 訊號的唯一載體)

  # These are the most relevant entities
  # ENTITY_NAME: entity summary
    - goaltender: Goaltender is associated with the sport of ice hockey.
    - ice hockey: Goaltender is associated with the sport of ice hockey.
    ... (10 nodes — entity summaries,可能含 "conflicts with" 描述)

  # These are the most relevant episodes.
  # format: EPISODE
    - Content: Dialogue between User and Assistant 2026-04-20 17:56:39
      \n<User> The following context is the facts I have learned:
      Frank Zappa died in the city of Los Angeles. 38. Dave Filoni is
      employed by Lucasfilm. 39. Henri Grégoire is a citizen of France.
      ... 75. <Assistant> I have learned the facts and I will answer ...
    ... (10 episodes — 完整 chunk,含序號 0-454 的事實列表)

  [question — by FC rag_agent template,見 utils/templates.py:81]
  Pretend you are a knowledge management system. Each fact in the knowledge
  pool is provided with a serial number at the beginning, and the newer
  fact has larger serial number.
  You need to solve the conflicts of facts in the knowledge pool by finding
  the newest fact with larger serial number. You need to answer a question
  based on this rule. You should give a very concise answer ... only from
  the knowledge pool you have memorized rather than the real facts in
  real world.

  For example:
   [Knowledge Pool]
   Question: ... what is the name of the current president of Russia?
  Answer: Donald Trump

   Now Answer the Question: Based on the provided Knowledge Pool,
  Which sport is goaltender associated with?
  Answer:
─────────────────────────────────────────────────────
```

> **關鍵觀察:LLM 收到兩套不一致的衝突訊號**
>
> | 訊號層 | 載體 | 形式 | 適用衝突 |
> |---|---|---|---|
> | **Zep date-range** | edges 的 `(valid_at - invalid_at)` | 隱式時間戳(秒級) | 只在 edges,觸發率 SH 8% / MH 47% |
> | **FC serial-number** | episodes 內的 `{seq}. {fact}` 文字 | 顯式序號 0–454 | 全部 episodes 都有 |
> | **Node summary** | nodes 的 summary 字段 | 自由 NL,可能含 "conflicts with" | 不是每個 entity 都有衝突描述 |
>
> FC 的任務指令**只告訴 LLM 用 serial number 規則**(「newer fact has larger serial number」),完全沒提到 date range。Zep 的 date range 訊號**沒有對應的 prompt 指令告訴 LLM 怎麼解讀**——`(invalid_at != null)` 的 edge 是要忽略還是只當作參考,LLM 必須自己判斷。
>
> 這解釋了為何即使「supersession 完美觸發」題目 LLM 還是只 71% MH EM——LLM 收到 invalid_at 訊號但**沒有顯式指令說 MUST NOT use OUTDATED**;同時 episodes 又給了 serial number 訊號要它「找最大序號」。兩個訊號可能對齊也可能不對齊(Zep 標 invalid 的 edge 序號未必是較小的),LLM 不知道哪個權威。
>
> **這直接對應我們 RPT 的設計動機**:把訊號統一成顯式的 `[CURRENT FACT]` / `[OUTDATED FACT]` inline marker,並加 `MUST NOT use OUTDATED` 強指令——把 Zep 的隱式 date-range + FC 的隱式 serial-number 兩套不一致訊號**收攏成一套無歧義的指令式信號**。

---

## 2. 實驗設置(對齊 step1a HippoRAG-v2)

| 項目 | 設定 |
|---|---|
| 資料集 | FC-SH / FC-MH(各 100 題) |
| 知識庫大小 | 6k context(455 ordered facts,SH/MH 共用同一份) |
| 記憶方法 | Zep(預設 cloud client、預設 LLM extractor) |
| Chunk size | 512 tokens(對齊 HippoRAG-v2,12 chunks/context) |
| Top-k 取回 | k=10(分別對 edges / nodes / episodes 各取 10) |
| 推理模型 | gpt-4o-mini(MAB 預設) |
| 待用 wait | ingestion 完成後 sleep 360s 等待 Zep 異步索引 |

---

## 3. 資料來源

### 3.1 Zep retrieval dump
- 路徑:`outputs/rag_retrieved/Structure_rag_zep/k_10/factconsolidation_{sh,mh}_6k/chunksize_512/FULL_100queries.json`
- Schema(每題一筆):
  ```json
  {
    "query_id": int,
    "gt": str,            // ground-truth answer
    "pred": str,          // model output
    "exact_match": bool,
    "edges":    [{"fact": str, "valid_at": iso8601, "invalid_at": iso8601 | null}, ...],  // top-10
    "nodes":    [{"name": str, "summary": str}, ...],
    "episodes": [{"content": str}, ...]
  }
  ```

### 3.2 Per-question ground truth(MQuAKE-CF mapping)
- SH:`analysis/results/hipporag_gemini/sh_512_gemini_mquake_analysis.json`
- MH:`analysis/results/hipporag_gemini/mh_512_gemini_mquake_analysis.json`
- 每題提供 `gt_fact_text`、`old_fact_text`、`old_answer`、`conflict_type`(MH 為 hop-level)
- Mapping 可靠度 ≥ 99%(詳見 [step1a_methodology.md §4](step1a_methodology.md))

---

## 4. Fact-to-retrieval 匹配程序(三 scope 都看)

### 4.1 邏輯

FC 的 6k 池中,每對衝突事實本質上是相同 (X, R) 但不同 Y 的三元組:
- 舊事實 `(X, R, oldY)`
- 新事實 `(X, R, newY)`

不論 Zep 用何種 LLM extractor 把對話抽成 triple,只要它把這兩句話分別保留在 edges/nodes/episodes 任一 scope,我們就能透過比對 fact 文字來判斷是否取回。

### 4.2 三層比對

```python
def norm(s):
    s = unicodedata.normalize("NFKC", s).lower().strip()
    s = re.sub(r"\s+", " ", s)
    return s.rstrip(" .,;:!?\"'")
```

| Scope | 匹配規則 | 理由 |
|---|---|---|
| **edges** | `norm(edge.fact) == norm(gt_fact_text or old_fact_text)` | Zep extractor 通常直接把對話事實句抄成 edge.fact(逐字一致),exact match 已足夠 |
| **nodes** | `norm(gt/old_fact_text) in norm(node.summary)`(substring) | node.summary 是該實體的綜合敘述,可能包含事實句作為其中一部分 |
| **episodes** | `norm(gt/old_fact_text) in norm(episode.content)`(substring) | episode.content 是含序號的原始 chunk,事實句以 `{seq}. {fact_text}` 形式逐字保留 |

**抽樣驗證**:SH q0、MH q0 等多筆人工核對 edge fact 與 input fact 完全一致(僅大小寫差異);episode content 為原始 chunk 逐字。誤匹配率估計 < 2%。

### 4.3 「retrieved」的定義

對每個事實(GT 或 Old):
- `in_edges` / `in_nodes` / `in_episodes`:三 scope 各自獨立的 top-10 是否含此事實
- **`in_any` = `in_edges OR in_nodes OR in_episodes`**:LLM 實際看得到的覆蓋率(因 LLM prompt 同時包含三段)

> **取捨**:後續 supersession 機制分析(`old_marked_invalid` 等)只在 `edges` scope 內定義,因為只有 edge 帶 `invalid_at`。但「retrieval 是否取到」的指標應同時報告 `edges` 和 `any`。

### 4.4 重要的歷史 caveat:dump 截斷 bug 已修正

最初的 helper script `run_zep_{full100,mh_full100}.py` 在保存 retrieval dump 時把每個 episode content 截斷到 500 字元,導致 episode-recall 在事後分析嚴重低估(SH 12-18%、實際應 100%;MH 17-18%、實際 94%)。**LLM 推理時看到的是完整內容**(原 MAB code path 不截斷,見 [agent.py compose_search_context](../agent.py)),所以 EM 70% / 25% 是正確的。bug 已修並重跑 retrieval-only(見 [run_zep_refetch_retrieval.py](../run_zep_refetch_retrieval.py))保存到 `RETRIEVAL_FULL_100queries.json`,本分析使用此檔。

> **與 OLD inference dump 一致性驗證**:重抓的 edges fact text 與 OLD inference dump 100% 一致(SH/MH 各 100 query × 10 edges = 1000 facts,0 個 invalid_at flag 不一致),確認 Zep graph state 在這幾天內未漂移、所有 supersession 結論未受影響。

---

## 5. 衝突機制指標定義

對每題(SH)或每 hop(MH):

### 5.1 Retrieval recall(top-10 edges)
- `gt_in_edges`:GT 事實是否被 Zep 取回(top-10 內)
- `old_in_edges`:Old 事實是否被取回
- `both_in_edges`:兩者皆取回

### 5.2 Supersession outcome(僅 has_pair 且 both_in_edges 才有意義)
| 指標 | 定義 | 「正確」意義 |
|---|---|---|
| `old_marked_invalid` | Old edge 的 `invalid_at != null` | ✅ Zep 正確識別舊事實已過期 |
| `gt_marked_invalid` | GT edge 的 `invalid_at != null` | ❌ Zep 把新事實也標成過期(錯誤) |
| `perfect_supersession` | `old_marked_invalid && !gt_marked_invalid` | ✅ 完美:舊死、新活 |

### 5.3 No_conflict_pair 的「不該誤殺」指標
| 指標 | 定義 | 「正確」意義 |
|---|---|---|
| `gt_in_edges` | GT 取回 | ✅ |
| `gt_marked_invalid` | GT 被標 invalid | ❌(此題池中無對應舊事實,不該被覆蓋) |
| `n_other_edges_invalid` | top-10 中其他(非 GT/Old)edge 標 invalid 的數量 | 中性指標:反映 Zep 在整張 graph 上做了多少 supersession 行為 |

---

## 6. 失敗模式分類(question-level)— 與 retrieval 的解耦

依 Zep 模型最終輸出 `pred` 與 GT/Old 答案做 normalized substring match:

```python
if exact_match: return "correct"
if old_answer and (pred == old_answer or old_answer in pred or pred in old_answer):
    return "older_fact"
return "hallucination_or_other"
```

### 6.1 為何不能直接做「有取到 vs 答對與否」的乾淨對應

HippoRAG-v2 的 step1a 分析能精確對應「retrieval × correct」,因為 retrieval 只有一個來源(top-10 chunks),且 LLM 輸入即等於 retrieval 結果。

Zep 的情況不同:**LLM 同時看到三個 top-10**(edges + nodes + episodes,共 30 個項目),而:
- 三個 scope 各自獨立做語義搜尋,可能對同一查詢回傳完全不重疊的結果
- 一條事實可能只出現在 edge 裡(被 supersession 機制管),也可能只出現在 nodes summary 裡(只是被嵌入了該 entity 的描述),也可能只出現在 episodes 裡(原始 chunk 還在,但沒被抽成 edge)
- 失敗時無法乾淨回答「LLM 是因為沒看到 GT 才答錯」還是「看到了 GT 也選了 Old」——除非分別檢視三 scope 並排除其他可能

故本分析的失敗模式分類(older_fact / hallucination_or_other)**只反映「Zep 整體輸出的失敗類型」**,不直接對應「retrieval 缺失 vs 推理錯誤」二分。

### 6.2 部分對應的可行做法

我們仍可以做出部分推論:

- **若 GT 三 scope 都沒取到(`gt_in_any = False`)**:幾乎可以排除「LLM 看到 GT 卻沒選」的可能,失敗主要歸 retrieval。
- **若 Old 在 edges 中且被標 invalid(`old_marked_invalid = True`)**:LLM 收到 supersession 訊號;此時若答錯,可歸 LLM-side reasoning 失敗。
- **完美 supersession (`old_marked_invalid AND NOT gt_marked_invalid AND gt_in_edges`)**:訊號最強,失敗最能歸咎 LLM。

這些細部歸因會在 sh/mh_summary 各自的核心分析段落呈現。

---

## 7. 核心觀察(條列式 summary,完整數據見 sh_summary / mh_summary)

1. **Retrieval 不是 Zep 的瓶頸**:三 scope 取出後 union 到 LLM 看到的:has_pair GT 與 Old 兩者皆中,SH 100%、MH 94.7%(hop-level)。**幾乎所有題目 LLM 都看到了 GT 跟 Old 兩者**。
2. **Edges 取回(supersession 訊號的唯一載體)較弱**:has_pair 兩者皆在 edges 中,SH 51.4% / MH 48.4%。其餘大量 has_pair 題目雖然 LLM 看到了 fact text(在 episodes 層),但拿不到 invalid_at 訊號。
3. **Supersession 在 SH 嚴重失準**:edges-both-retrieved 38 題裡,只有 7 題(18.4%)正確標記 Old 為 invalid;反而有 14 題(36.8%)誤把 GT 標成 invalid。
4. **Supersession 在 MH 較對稱**:91 個 edges-both-retrieved hops 裡,52.7% 正確標 Old invalid,只有 3.3% 誤標 GT invalid。
5. **完美 supersession 信號 ≠ 完美回答**:MH 14 題「所有 has_pair hops 都完美 supersession」,EM 仍只有 10/14 = 71.4%。
6. **No-conflict-pair 不是乾淨基線**:SH 26 題裡 19 題 top-10 裡有至少一條 invalid edge(來自 graph 中其他不相關的 supersession),共 47 條 OTHER edges 被誤標(平均每題 1.8 條)——但 LLM 對 SH 無衝突問題仍 100% 正確,顯示這些雜訊不影響此情境。
7. **重要 reframe**:Zep 在 FC 上對 HippoRAG-v2 的優勢,不是因為 retrieval 更好(其實 union 後與 HippoRAG-v2 都接近滿),而是因為 supersession 機制偶然觸發時(MH 47/91、SH 6/38)能給 LLM 一個明確的「用新棄舊」訊號。當沒觸發時,LLM 看到的 context 本質與 HippoRAG-v2 相當(都是含序號的 chunk-level 事實),依賴 prompt 規則。
8. **SH 上 Zep 機制淨效應接近 0**:perfect 6 題 +31pp(vs HippoRAG)× 6/74 + misfired 14 題 −63pp × 14/74 ≈ −7pp,實測 has_pair EM 兩者都是 59.5%(誤差由其他子集消化)。
9. **MH 上 Zep 機制 +14pp 的 driver 是 ALL_PERFECT 子集**:14 題 EM 71% vs HippoRAG ~26% baseline = +45pp × 14/100 ≈ +6.3pp,加上 PARTIAL_PERFECT 略有貢獻;NO_SIGNAL_BOTH_VISIBLE 47 題 EM 9%(等同 HippoRAG 11%)。
10. **SH-vs-MH 機制效用差異**:同樣是「無訊號但兩者都看得到」狀態,SH EM 68.5%、MH EM 8.5%——多跳鏈在 conflict 下的崩潰是 MH 難解的本質,單跳一次選對就能答對,多跳要連續每步都選對才能答對(乘法效應)。
11. **RPT 嚴格 dominate Zep on MH**:0 題是 Zep 唯一答對、RPT 多救 43 題;RPT 走的是同一條「LLM-side explicit signaling」路線,只是把 Zep 沒做完整的訊號做到 100% 覆蓋(每個衝突對的 [CURRENT]/[OUTDATED] 標記)。

---

## 8. 分析腳本

| 腳本 | 用途 |
|---|---|
| [analyze_zep_mechanism.py](analyze_zep_mechanism.py) | 主分析:edge-to-fact 匹配、supersession 統計、failure-mode 分類 |
| 輸出 | `analysis/results/zep/{sh,mh}_zep_mechanism.json` + `zep_mechanism_summary.txt` |

---

*分析環境:Python 3.x*
*資料產出日期:2026-04-27*
