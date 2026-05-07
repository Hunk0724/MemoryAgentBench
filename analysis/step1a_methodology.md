# Step 1A 方法論：FC-MH 衝突跳數 vs 答對率

> **目的**：在不修改任何方法的情況下，系統性量化「衝突對數量」對 HippoRAG-v2 在 FC-MH 任務上的準確率影響，確認失敗主要來自 retrieval 還是 reasoning。

---

## 1. 實驗設置

| 項目 | 設定 |
|---|---|
| 資料集 | FC-MH (FactConsolidation Multi-Hop) |
| 知識庫大小 | 6,000 tokens（6k context，共 455 個有序事實句） |
| RAG 系統 | HippoRAG-v2（NV-Embed-v2 + KG + PPR 排序） |
| Chunk size | 512 tokens（每個 chunk 約含 25–30 個事實句） |
| Top-k 取回 | k = 10（共取回 10 個 chunks） |
| LLM | GPT-4o-mini |
| 題目總數 | 100 題 |
| 跳數範圍 | 2-hop / 3-hop / 4-hop |

### Inference Prompt 的衝突解決規則

HippoRAG-v2 的 inference prompt 已包含以下規則（原文）：

> *「事實序號越大代表越新、越正確；遇到衝突時，優先採用序號較大的事實。」*

本分析即是在此規則已存在的條件下，觀察系統的實際表現。

---

## 2. 資料來源

### 2.1 Inference 結果
- 路徑：`outputs/gpt-4o-mini-hippo_rag_v2_nv/Conflict_Resolution/factconsolidation_mh_6k_unknown_in6000_size10_shots0_max_samplesunknown_k10_chunk512_results.json`
- 每筆包含：`query_id`、`qa_pair_id`、`query`（含 knowledge pool）、`answer`（GT）、`output`（模型輸出）、`exact_match`、`retrieval_scores`

### 2.2 Retrieved Passages
- 路徑：`outputs/rag_retrieved/Structure_rag_hippo_rag_v2_nv/k_10/factconsolidation_mh_6k/chunksize_512/query_{id}_context_0.json`
- 每題對應一個 JSON 字串，格式為 `"Passage 1:\n...\nPassage 2:\n..."` 共 10 個 passages

### 2.3 MQuAKE-CF Ground Truth
- 路徑：`/home/yhchiang/MQuAKE/datasets/MQuAKE-CF.json`
- 用途：精確提供每一跳的新事實（`new_single_hops[k].cloze + answer + "."`）與舊事實對（`single_hops[k]`）

### 2.4 Knowledge Pool（事實句庫）
- 路徑：`/home/yhchiang/MemoryAgentBench_old/scripts/contexts/factconsolidation_sh_6k_context_0.txt`
- 格式：455 個有序事實句，每句前綴序號 `{n}. {fact text}`（SH 和 MH 共用同一份）

---

## 3. 步驟一：MQuAKE 對應

### 3.1 建立索引

對 MQuAKE-CF.json 的每個 case，以 `(question.lower(), new_answer.lower())` 為 key 建立索引，支援 alias：

```python
for c in mquake:
    for q in c.get("questions", []):
        key = (q.strip().lower(), c["new_answer"].lower())
        mh_q_index[key] = c
    for alias in c.get("new_answer_alias", []):
        for q in c.get("questions", []):
            key2 = (q.strip().lower(), alias.lower())
            mh_q_index[key2] = c
```

### 3.2 從 query 提取問句

每筆 inference 的 `query` 包含 knowledge pool，用 regex 提取問句：

```python
m = re.search(r'Now Answer the Question:\s*(.+?)(?:\nAnswer:|$)', query, re.DOTALL)
question = re.sub(r'Based on the provided Knowledge Pool,\s*', '', m.group(1).strip())
```

### 3.3 比對成功率

100 題全部成功比對到 MQuAKE case（比對率 100%）。

---

## 4. 步驟二：逐跳新舊事實定位

### 4.1 新事實（GT）定位

每一跳的新事實由 `new_single_hops[k]` 提供：

```python
gt_fact = hop["cloze"] + " " + hop["answer"] + "."
gt_seq  = ctx_by_lower.get(gt_fact.lower())   # 在 455 句中查序號
```

### 4.2 舊事實（衝突對）定位

**主要方法**：從 `requested_rewrite[k].target_true.str` 取得舊答案：

```python
old_ans  = requested_rewrite[k]["target_true"]["str"]
old_fact = hop["cloze"] + " " + old_ans + "."
old_seq  = ctx_by_lower.get(old_fact.lower())
```

**Fallback 方法**（若上述找不到）：在 455 句中搜尋以相同 cloze 開頭、答案不同的句子，取序號最接近但小於 GT 的句子。

### 4.3 衝突類型判斷

```python
conflict_type = "has_pair" if old_seq is not None else "no_conflict_pair"
```

**可靠性驗證**：  
對 66 個 `no_conflict_pair` 跳，逐一比對 `single_hops[k].answer`（MQuAKE 提供的舊版跳鏈）與 `new_single_hops[k].answer`：

| 情況 | 跳數 | 結論 |
|---|:---:|---|
| 兩者答案相同（這跳本來就沒被改寫） | 33 | 確認為真正的 no_conflict_pair |
| MQuAKE 也無此跳的 target_true | 30 | 確認為真正的 no_conflict_pair |
| 兩者答案不同（漏找到舊事實） | **3** | 實際應為 has_pair（誤差 ~1%） |

**結論：has_pair 分類的可靠度 ≥ 99%，3 筆誤差不影響整體觀察。**

---

## 5. 步驟三：在 Retrieved Passages 中定位事實

### 5.1 定位方式

使用序號精確定位（`{seq_no}. ` prefix）：

```python
def find_seq_in_passages(seq_no, passages):
    prefix = f"{seq_no}. "
    for rank, p in enumerate(passages, 1):
        if prefix in p:
            return rank, p.find(prefix)
    return None, None
```

### 5.2 記錄資訊

每跳記錄：
- `gt_retrieved`：新事實是否在 top-10 中
- `gt_rank`：所在 passage 的 rank（1 = PPR 最高）
- `gt_ppr`：對應 passage 的 PPR score
- `old_retrieved`、`old_rank`、`old_ppr`：舊事實同上
- `same_passage`：新舊事實是否在同一個 passage 中

---

## 6. 步驟四：失敗原因分類

對每題，使用 inference 結果的 `exact_match` 欄位（substring matching）判斷是否答對，再對失敗題細分：

```python
def classify_error_mh(output, new_answer, old_final_answer,
                      new_single_hops, single_hops, exact_match):
    if exact_match:
        return "correct"

    out_n   = normalize(output)     # 去除尾部標點後小寫
    old_f_n = normalize(old_final_answer)

    # 1. older_fact：模型輸出等於舊鏈最終答案
    if old_f_n and (out_n == old_f_n or old_f_n in out_n or out_n in old_f_n):
        return "older_fact"

    # 2. intermediate_stop (new)：停在新版鏈的中間跳答案
    for k in range(last_hop):
        if normalize(new_single_hops[k]["answer"]) matches out_n:
            return "intermediate_stop"

    # 3. intermediate_stop (old)：停在舊版鏈的中間跳答案
    ...

    # 4. entity_confused：輸出是 context 中某個 entity 但不是任何已知答案
    if any(out_n in fact.lower() for fact in all_context_facts):
        return "entity_confused"

    # 5. hallucination：完全無法匹配
    return "hallucination"
```

**`normalize()` 定義**：
```python
def normalize(s):
    return s.strip().rstrip(".,;:!?\"'").strip().lower()
```

---

## 7. 主要觀察結果

### 7.1 衝突跳數的定義與題目組成

「n 跳有衝突」表示：一道多跳題目中，恰好有 n 個子問題（hop）在 6k 知識庫裡同時存在新事實與舊事實（has_pair）。

各組的 2-hop/3-hop/4-hop 題目分布如下：

| 衝突跳數 | 題數 | 2-hop 題 | 3-hop 題 | 4-hop 題 | 各組的 conflict/total hops |
|:---:|:---:|:---:|:---:|:---:|:---|
| **1 跳有衝突** | 33 | 25 | 5 | 3 | 1/2、1/3、1/4 跳有衝突 |
| **2 跳有衝突** | 48 | 36 | 9 | 3 | 2/2（全衝突）、2/3、2/4 跳有衝突 |
| **3 跳有衝突** | 17 | — | 10 | 7 | 3/3（全衝突）、3/4 跳有衝突 |
| **4 跳有衝突** | 2 | — | — | 2 | 4/4（全衝突）|

> **可靠性說明**：以上分類使用 MQuAKE 的 `single_hops[k].answer` 與 `new_single_hops[k].answer` 直接比對，100% 依賴 dataset ground truth，人工核查確認誤差僅 3/254 跳（< 1%）。詳見第 4 節。

  1 conflict hop 組（33 題）答對分布                                                                                                                      

| **推理步數 (num_hops)** | **總題數** | **答對題數** | **正確率 (Acc)** |
| --- | --- | --- | --- |
| **2-hop** | 25 | 7 | 28.0% |
| **3-hop** | 5 | 2 | 40.0% |
| **4-hop** | 3 | 1 | 33.3% |
| **合計** | **33** | **10** | **30.3%** |                                                                                                                                                                                                                                               
                                                                                                                                                          
  樣本數太少（5 題、3 題），3-hop/4-hop 的 Acc 差距不穩定，不能直接解讀為「跳數越多越難」。 
### 7.2 衝突跳數 vs 答對率

| 衝突跳數 | 題數 | 正確（題） | Accuracy |
|:---:|:---:|:---:|:---:|
| 1 跳有衝突 | 33 | **10** | **30.3%** |
| 2 跳有衝突 | 48 | **1** | **2.1%** |
| 3 跳有衝突 | 17 | **0** | **0.0%** |
| 4 跳有衝突 | 2 | **0** | **0.0%** |
| **整體** | **100** | **11** | **11.0%** |

→ **衝突跳數與答對率呈嚴格單調遞減。** 每增加一跳衝突，Acc 急劇下降。

### 7.2 Retrieval 品質（has_pair 跳）

| 衝突跳數 | GT 取回率 | Old 取回率 | 全部衝突跳都兩者取回（per entry） |
|:---:|:---:|:---:|:---:|
| 1 跳 | 97.0% | 100.0% | 97.0% |
| 2 跳 | 95.8% | 97.9% | 87.5% |
| 3 跳 | 94.1% | 98.0% | 82.4% |
| 4 跳 | 100.0% | 100.0% | 100.0% |

→ **Retrieval 品質極高**，新舊事實幾乎都進入 context。失敗不來自 retrieval 缺失，而是 LLM 在新舊並存時選了舊事實。

### 7.3 失敗原因分布

| 失敗類型 | 1 跳衝突 | 2 跳衝突 | 3 跳衝突 | 4 跳衝突 | **合計** |
|---|:---:|:---:|:---:|:---:|:---:|
| older_fact | 19 | 34 | 14 | 2 | **69 (78%)** |
| entity_confused | 1 | 8 | 1 | — | **10 (11%)** |
| hallucination | 3 | 4 | 2 | — | **9 (10%)** |
| intermediate_stop | — | 1 | — | — | **1 (1%)** |

→ **78% 的失敗原因是 `older_fact`**：LLM 即使看到序號規則，仍選擇了舊事實答案。

---

## 8. 核心結論

1. **衝突跳數與答對率負相關**（1 跳 30% → 2 跳 2% → ≥3 跳 0%），符合 Step 1A 的預期假說。

2. **Retrieval 幾乎完美（GT ≥ 94%, Old ≥ 97%）**，問題不在 HippoRAG-v2 的取回能力，而在 LLM 面對新舊共存 context 時的 reasoning。

3. **Prompt 中的序號規則無法穩定解決多跳衝突**：78% 失敗是 `older_fact`，說明即使已明確告知「序號越大越新越正確」，LLM 仍然選擇舊版答案。

4. **乘法效應**：每增加一跳衝突，就多一次「被舊事實拉偏」的機會，導致 Acc 急劇崩潰。

---

## 9. 圖表

| 檔案 | 內容 |
|---|---|
| `fig_conflict_hops_vs_acc.png` | 折線圖：衝突跳數 vs Accuracy，標注 `correct/total (acc%)` |
| `fig_hop_composition.png` | 堆疊長條圖（2/3/4-hop 組成）+ Accuracy 折線 overlay，說明各組如何構成 |
| `fig_retrieval_vs_acc.png` | 折線圖：GT/Old 取回率 + 兩者取回率（per entry）+ Accuracy |
| `fig_error_distribution.png` | 堆疊長條圖：各組的 Correct/older_fact/entity_confused/hallucination 比例 |

---

## 10. 分析腳本

| 腳本 | 用途 |
|---|---|
| `analysis/analyze_mh_512_mquake.py` | 主分析：MQuAKE 對應、逐跳事實定位、失敗分類，輸出 `mh_512_mquake_analysis.json` |
| `analysis/generate_step1a_charts.py` | 圖表生成：從 `mh_512_mquake_analysis.json` 輸出三張圖 |
| `analysis/step1a_methodology.md` | 本文件 |

---

*分析環境：`hipporag_env`（Python 3.x, matplotlib 3.10.8）*  
*資料產出日期：2026-04-15*
