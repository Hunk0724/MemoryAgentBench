# MQuAKE → FC-SH/MH Ground Truth 對應完整指南

> 建立日期:2026-05-24
> 目的:讓任何人(包括未來的自己 / 未來的 Claude session)看完這份就懂「FC 題目的衝突對如何從 MQuAKE 對應出來、每個 hop 的 GT 怎麼定位」
> 文件 self-contained,不依賴前後文。

---

## 0. TL;DR

**FC 的「對話歷史」不是 user/assistant 對話,而是「編號事實列表」**。同一個關係的新舊版本以不同編號鑲嵌其中,序號越大越新(版本號)。MQuAKE 的 `requested_rewrite` 提供 `(target_true, target_new)` 配對,讓我們知道哪兩個事實是衝突對。

對應 pipeline 三層:**MQuAKE case → 對話歷史 fact 編號 → retrieval/memory 排序**。

每道 FC-MH 題拆解為 N 個 hop,每個 hop 獨立可判斷有無衝突對(`conflict_type ∈ {has_pair, no_conflict_pair, answer_not_in_ctx}`)。

---

## 1. 概念模型

### 1.1 對話歷史的真實格式

不是 dialogue turn,是這個樣子:

```
Here is a list of facts:
0.   Thomas Kyd was born in the city of London.
1.   The chairperson of Fatah is Mahmoud Abbas.
...
107. The author of Our Mutual Friend is Charles Dickens.      ← 舊版本
...
146. The author of Our Mutual Friend is Charles Darwin.       ← 新版本
...
164. Charles Darwin is married to Emma Darwin.                ← 舊版本
...
335. Charles Darwin is married to Amala Paul.                 ← 新版本
...
294. Amala Paul is a citizen of India.                        ← 舊版本
322. Amala Paul is a citizen of Belgium.                      ← 新版本
```

**核心規則**:
- 每行帶整數編號(`{seq}. ` 前綴)
- 編號 = 版本號(序號越大 = 越新且越正確)
- 衝突對 = **同 cloze、不同 answer、不同編號**的兩個句子
- 6k 對話歷史 = 455 個編號事實([analysis/contexts/factconsolidation_6k_context.txt](../../analysis/contexts/factconsolidation_6k_context.txt))
- 32k = 2310 個事實([analysis/contexts/factconsolidation_32k_context.txt](../../analysis/contexts/factconsolidation_32k_context.txt))
- 64k / 262k 暫無本地 context cache(需從 HuggingFace dataset 載出來,見 §6)

### 1.2 為什麼編號就是版本號

對話歷史按時間順序累積,新事實「覆蓋」舊事實的方式是**追加在後面**,不是修改原條目。所以對 memory system 來說:
- ingest 第 107 條時學到「author = Dickens」
- ingest 第 146 條時看到「author = Darwin」→ **應該觸發 UPDATE/DELETE**
- 沒觸發 = 衝突偵測失敗 = fail case A

---

## 2. MQuAKE 資料結構

### 2.1 來源

`/home/yhchiang/MQuAKE/datasets/MQuAKE-CF.json`(repo 外部,clone 自 MQuAKE 原 repo)

### 2.2 一個 case 的關鍵欄位

```json
{
  "case_id": 22,
  "questions": ["Which sport is goaltender associated with?"],
  "new_single_hops": [
    {
      "cloze": "goaltender is associated with the sport of",
      "answer": "pesäpallo"
    }
  ],
  "single_hops": [
    {
      "cloze": "goaltender is associated with the sport of",
      "answer": "ice hockey"
    }
  ],
  "requested_rewrite": [
    {
      "target_true": {"str": "ice hockey"},
      "target_new": {"str": "pesäpallo"}
    }
  ],
  "new_answer": "pesäpallo",
  "answer": "ice hockey"
}
```

### 2.3 關鍵概念

| 欄位 | 含義 |
|---|---|
| `requested_rewrite[k].target_true.str` | 第 k 個 hop 的**舊答案** |
| `requested_rewrite[k].target_new.str` | 第 k 個 hop 的**新答案** |
| `new_single_hops[k]` | 新鏈第 k 跳的 cloze + 新答案 |
| `single_hops[k]` | 舊鏈第 k 跳的 cloze + 舊答案 |

### 2.4 SH vs MH

| | `new_single_hops` 長度 | 一題的衝突來源 |
|---|---|---|
| **FC-SH**(single-hop) | 1 | `requested_rewrite[0]` 一對新舊答案 |
| **FC-MH**(multi-hop) | 2-4 | `requested_rewrite[0..N-1]` 每跳可能各有衝突對 |

FC-MH 一題的多個 hop 形成**鏈式依賴**:hop k 的答案 = hop k+1 的輸入主語。例如:
- Hop 0: "Our Mutual Friend 的作者?" → "Charles Darwin"(新)/ "Charles Dickens"(舊)
- Hop 1: "Charles Darwin 的配偶?" → "Amala Paul"(新)/ "Emma Darwin"(舊)
- Hop 2: "Amala Paul 的國籍?" → "Belgium"(新)/ "India"(舊)

---

## 3. 三層對應結構

```
MQuAKE-CF.json                  對話歷史(編號 facts)              retrieval / memory
─────────────────                ──────────────────              ───────────────────
case 22                          ────────────                    ─────────
├─ new_single_hops[k]           107. ...Charles Dickens.        passage 1: [...]
│   ├─ cloze                    146. ...Charles Darwin.         passage 2: [...]
│   └─ answer (新答案)           164. ...Emma Darwin.             ...
├─ requested_rewrite[k]          335. ...Amala Paul.             或:
│   └─ target_true (舊答案)                                       mem0 retrieved memories
└─ questions                                                     (free-form fact text)
                ↓ alignment by cloze+answer text match           ↓ rank / hit lookup
                
                  per-hop output JSON
                  ├─ hop_idx, gt_seq, old_seq
                  ├─ conflict_type: has_pair / no_conflict_pair / answer_not_in_ctx
                  ├─ update_gap = gt_seq - old_seq  (新舊事實的序號距離)
                  ├─ gt_retrieved, gt_passage_rank
                  └─ error_type: older_fact / entity_confused / hallucination
```

---

## 4. 已有對應結果 — 直接查詢

### 4.1 6k 對應結果(已 ready)

| 檔案 | 內容 |
|---|---|
| [analysis/results/sh_512_mquake_analysis.json](../../analysis/results/sh_512_mquake_analysis.json) | FC-SH 100 題 × hop=1 對應 |
| [analysis/results/mh_512_mquake_analysis.json](../../analysis/results/mh_512_mquake_analysis.json) | FC-MH 100 題 × hop 1-4 對應 |

**直接查詢 sample**:

```bash
python -c "
import json
data = json.load(open('analysis/results/mh_512_mquake_analysis.json'))
target = 'factconsolidation_mh_6k_no0'
for r in data:
    if r['qa_pair_id'] == target:
        print(f\"題目: {target} | 共 {r['num_hops']} 跳\")
        for h in r['hops']:
            print(f\"  Hop {h['hop_idx']}: {h['conflict_type']}\")
            print(f\"    新 seq#{h['gt_seq']}: {h.get('gt_fact_text','')}\")
            print(f\"    舊 seq#{h.get('old_seq','-')}: {h.get('old_fact_text','-')}\")
            print(f\"    update_gap: {h.get('update_gap','-')}\")
"
```

### 4.2 一個 query 的對應 JSON 結構

```json
{
  "qa_pair_id": "factconsolidation_mh_6k_no0",
  "case_id": 6913,
  "num_hops": 3,
  "hops": [
    {
      "hop_idx": 0,
      "gt_answer": "Charles Darwin",
      "old_answer": "Charles Dickens",
      "gt_seq": 146,
      "old_seq": 107,
      "gt_fact_text": "The author of Our Mutual Friend is Charles Darwin.",
      "old_fact_text": "The author of Our Mutual Friend is Charles Dickens.",
      "conflict_type": "has_pair",
      "update_gap": 39,
      "gt_retrieved": true,
      "gt_passage_rank": 2,
      "old_retrieved": true,
      "old_passage_rank": 1
    },
    ...
  ],
  "conflict_type_all": "has_pair",
  "old_passages_to_remove": [1, 6, 7],
  "error_type": "older_fact"
}
```

### 4.3 主要欄位含義

| 欄位 | 含義 |
|---|---|
| `gt_seq` | 新事實在對話歷史的序號 |
| `old_seq` | 舊事實的序號(衝突對) |
| `update_gap` | `gt_seq - old_seq`(越大代表新舊在歷史中距離越遠) |
| `conflict_type` | `has_pair` / `no_conflict_pair`(該 hop 是否有衝突對) |
| `conflict_type_all` | 全部 hop 都 has_pair / 部分 / 都無 |
| `gt_retrieved` | 新事實是否被取回(視 retrieval 型 baseline 而定) |
| `gt_passage_rank` | 新事實在 top-k 排第幾(若用 passage retrieval) |
| `error_type` | `correct` / `older_fact`(被舊事實誤導)/ `entity_confused` / `hallucination` |

---

## 5. 從零對應 — 動態對應流程(任意長度)

當 4.1 的對應檔不存在(例如 64k/262k 或新方法)時,跟著這個流程做。

### Step 1:建立 MQuAKE 索引

```python
import json

mquake = json.load(open("/home/yhchiang/MQuAKE/datasets/MQuAKE-CF.json"))

# SH 索引:(問句, 新答案) → (case, hop_idx)
sh_hop_index = {}
for c in mquake:
    for i, hop in enumerate(c.get("new_single_hops", [])):
        # 注意:sh 用 hop 內的 question + answer
        key = (hop["question"].strip().lower(), hop["answer"].strip().lower())
        sh_hop_index[key] = (c, i)

# MH 索引:(top-level 問句, top-level 新答案) → case
mh_q_index = {}
for c in mquake:
    top_answer = c.get("new_answer", "").strip().lower()
    for q in c.get("questions", []):
        mh_q_index[(q.strip().lower(), top_answer)] = c
```

### Step 2:建立對話歷史的序號反查表

```python
import re

ctx_text = open("analysis/contexts/factconsolidation_6k_context.txt").read()

# 對話歷史每行格式: "  146. The author of Our Mutual Friend is Charles Darwin."
ctx_lines = [(int(m.group(1)), m.group(2).strip())
             for m in re.finditer(r'^\s*(\d+)\.\s+(.+)', ctx_text, re.MULTILINE)]

ctx_by_lower = {t.lower(): n for n, t in ctx_lines}   # 文本 → 序號
ctx_by_seq   = {n: t for n, t in ctx_lines}          # 序號 → 文本
```

### Step 3:對單題 alignment(MH 例)

```python
def align_mh(question_text, gt_answer):
    case = mh_q_index.get((question_text.strip().lower(), gt_answer.strip().lower()))
    if not case:
        return None
    hops = case.get("new_single_hops", [])
    rewrites = case.get("requested_rewrite", [])
    out = []
    for k, hop in enumerate(hops):
        # 新事實:cloze + answer + "."
        gt_fact = (hop["cloze"] + " " + hop["answer"] + ".").lower()
        gt_seq = ctx_by_lower.get(gt_fact)

        # 舊事實:cloze + target_true + "."
        old_ans = None
        if k < len(rewrites):
            old_ans = rewrites[k].get("target_true", {}).get("str")
        if old_ans:
            old_fact = (hop["cloze"] + " " + old_ans + ".").lower()
            old_seq = ctx_by_lower.get(old_fact)
            conflict = "has_pair" if old_seq else "answer_not_in_ctx"
        else:
            old_seq = None
            conflict = "no_conflict_pair"

        out.append({
            "hop_idx": k,
            "cloze": hop["cloze"],
            "gt_answer": hop["answer"],
            "old_answer": old_ans,
            "gt_seq": gt_seq,
            "old_seq": old_seq,
            "conflict_type": conflict,
            "update_gap": (gt_seq - old_seq) if (gt_seq and old_seq) else None,
            "gt_fact_text": ctx_by_seq.get(gt_seq) if gt_seq else None,
            "old_fact_text": ctx_by_seq.get(old_seq) if old_seq else None,
        })
    return {"case_id": case["case_id"], "num_hops": len(hops), "hops": out}
```

### Step 4(可選):對應到 retrieval / memory 命中

對 mem0/mem0g 這類 memory-based(非 passage retrieval)的方法:

```python
def check_gt_in_memories(gt_seq, gt_fact_text, gt_answer, retrieved_memories):
    """
    retrieved_memories: list of strings(每筆 memory 的純文字)
    回傳 (gt_found, hit_index)
    """
    for idx, mem_text in enumerate(retrieved_memories):
        mt = mem_text.lower()
        # 第一層:完整 fact text 出現
        if gt_fact_text and gt_fact_text.lower() in mt:
            return True, idx
        # 第二層:答案出現 + cloze 主要 entity 出現(fuzzy)
        if gt_answer.lower() in mt:
            # 視 cloze 內主要 entity 判斷
            return True, idx
    return False, -1
```

---

## 6. 各長度對應狀態(2026-05-24 驗證)

| Mode | 6k | 32k | 64k | 262k | 備註 |
|---|:---:|:---:|:---:|:---:|---|
| **context 本地 cache** | ✅ 455 facts | ✅ 2310 facts | ✅ 4580 facts | ✅ 18332 facts | 全部由 [analysis/cache_fc_contexts.py](../../analysis/cache_fc_contexts.py) 抽出 |
| **HippoRAG retrieval-aware 對應** | ✅ SH+MH | ❌ | ❌ | ❌ | [analysis/analyze_{sh,mh}_512_mquake.py](../../analysis/analyze_sh_512_mquake.py) |
| **LCA 純答案層對應** | ✅ SH+MH | ✅ SH+MH | ❌ | ❌ | [analysis/analyze_lca_mquake.py](../../analysis/analyze_lca_mquake.py) |
| **mem0/mem0g 對應** | ⏳ 待跑 | ⏳ | ⏳ | ⏳ | 本文件 §5 的腳本邏輯,腳本見 [analysis/align_mem0_mquake.py](../../analysis/align_mem0_mquake.py) |

### 6.1 驗證結論(實際從 HF arrow 讀出)

- ✅ HF dataset `ai-hyz/MemoryAgentBench` 的 `Conflict_Resolution` split 內,**全部 4 個長度 × SH/MH = 8 個子集都存在**
- ✅ 每個子集 1 個 row,該 row 內 `questions` 是 100 題的 list,所有題目**共享同一個 context**
- ✅ 同一長度的 SH 跟 MH **共用同一個 context**(SH 64k 和 MH 64k 的 context 完全相同)
- ✅ **不同長度** SH/MH 的 context **是獨立生成**的,fact 內容不同(6k 第 0 行 = Thomas Kyd;32k = Steve Jobs;64k = Glenn L. Martin;262k = L. Ron Hubbard)
- 結論:**每個長度都要獨立做 MQuAKE 對應**,但 alignment 邏輯完全一樣 — 只是換 context 檔
- context 已經全部 cache 到 [analysis/contexts/factconsolidation_{6k,32k,64k,262k}_context.txt](../../analysis/contexts/)

### 6.2 8 個子集的 MQuAKE coverage 全量驗證(2026-05-24)

執行 [analysis/check_mquake_coverage.py](../../analysis/check_mquake_coverage.py) 對全部 8 個 FC 子集做純對應驗證(不需要任何模型 output,直接從 HF arrow 抽 100 題 × `(question, answer)` 對應 MQuAKE),結果:

| Subset | matched / total | total hops | has_pair | no_conflict_pair | answer_not_in_ctx |
|---|:---:|:---:|:---:|:---:|:---:|
| `factconsolidation_sh_6k` | **100/100** | 100 | 74 (74.0%) | 26 | 0 |
| `factconsolidation_mh_6k` | **100/100** | 254 | 188 (74.0%) | 66 | 0 |
| `factconsolidation_sh_32k` | **100/100** | 100 | 65 (65.0%) | 35 | 0 |
| `factconsolidation_mh_32k` | **100/100** | 258 | 191 (74.0%) | 67 | 0 |
| `factconsolidation_sh_64k` | **100/100** | 100 | 66 (66.0%) | 34 | 0 |
| `factconsolidation_mh_64k` | **100/100** | 265 | 210 (79.2%) | 55 | 0 |
| `factconsolidation_sh_262k` | **100/100** | 100 | 77 (77.0%) | 23 | 0 |
| `factconsolidation_mh_262k` | **100/100** | 267 | 244 (91.4%) | 23 | 0 |

**核心發現**:

1. **100% match rate** 所有子集所有題都能在 MQuAKE-CF 找到對應 case ✅
2. **0 `answer_not_in_ctx`** — 每個有 `requested_rewrite.target_true` 的 hop,**對應的舊事實都能在對話歷史找到**(沒有「MQuAKE 說有舊答案但 context 內找不到」的情況)
3. **MH 平均 hops 隨長度增加**:6k = 2.54、32k = 2.58、64k = 2.65、262k = 2.67
4. **has_pair 比例隨長度增加**(MH 特別明顯):6k 74% → 262k 91.4% — 越長的對話歷史越容易容納完整衝突對
5. **SH 衝突比例約 65-77%**(較 MH 低 10-15 pp)

**結論**:可以放心對 32k/64k/262k 做 hop-level 衝突分析,GT alignment 沒有死角。

報告 JSON:`analysis/results/mquake_coverage_report.json`(內含每題 per-hop 詳細結果,可直接 query 某題的衝突結構)。

---

## 7. Fail Case 分類框架(基於 alignment)

跑完 mem0/mem0g 後,結合對應結果可分類:

| Fail mode | 判定條件 | 含義 |
|---|---|---|
| **A. Conflict 未偵測** | 同 chunk 內 gt_seq 和 old_seq 都進記憶,且 update_event 沒有 `UPDATE`/`DELETE` | mem0 沒判定為衝突 |
| **B. 偵測到但答錯** | 有 UPDATE/DELETE,但 retrieve 回的 memories 仍含 old + 答錯 | 衝突偵測 ok 但 retrieve / generation 環節失敗 |
| **C. Retrieve 失敗** | gt_seq 對應的 memory 不在 retrieved 中 | 向量/圖檢索沒抓到關鍵事實 |
| **D. Temporal 順序錯** | 新事實被當成舊的刪掉(罕見但要監控) | LLM update decision 反向誤判 |
| **E. Entity resolution 失敗** | 同一現實對象散在多個 memory_id / node UUID | dedupe 失敗,衝突偵測根本沒機會觸發 |

每個 hop 獨立判斷。MH 一題若有 3 hop,可能 hop 0 fail mode A、hop 1 fail mode C、hop 2 correct。

---

## 8. 跨文件引用

- 方法層級對比:[[../baseline_methods/baseline_methods_paper_vs_impl.md]]
- pilot 規劃:[[../experiments/pilots/mem0_mem0g_pilot_plan.md]]
- 原 fc_mh 研究總覽(包含本文件未涵蓋的 detection/packaging 階段):[../../analysis/fc_mh_research_overview.md](../../analysis/fc_mh_research_overview.md)

---

## 9. 相關腳本路徑速查

| 檔案 | 用途 |
|---|---|
| [analysis/analyze_sh_512_mquake.py](../../analysis/analyze_sh_512_mquake.py) | HippoRAG SH 對應參考 |
| [analysis/analyze_mh_512_mquake.py](../../analysis/analyze_mh_512_mquake.py) | HippoRAG MH 對應參考 |
| [analysis/analyze_lca_mquake.py](../../analysis/analyze_lca_mquake.py) | LCA(無 retrieval)對應參考 |
| `analysis/align_mem0_mquake.py` | mem0/mem0g 版對應(待寫,本文件 §5 邏輯) |
