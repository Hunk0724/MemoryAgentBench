# 研究工作脈絡紀錄

> 輸出時間：2026-04-16  
> 用途：保留本次對話的完整研究背景，供下次 session 快速接續

---

## 研究目標

分析 HippoRAG-v2 在知識衝突任務（FC-SH、FC-MH）上的失敗根因，並透過 Oracle 實驗驗證「retrieved context 新舊混雜是主因」的假說，最終設計 Conflict Filter 改進方法。

---

## 研究步驟進度

| Step | 狀態 | 結論 |
|---|---|---|
| **Step 1A** 衝突跳數 vs Acc | ✅ 完成 | SH 69%、MH 11%；衝突跳數嚴格單調遞減；圖表與 methodology md 已產出 |
| **Step 1B** Prompt 序號規則 | ✅ 確認 | HippoRAG-v2 inference 已有「序號越大越新越正確」規則，但仍大量失敗 |
| **Step 1C** 失敗類型細分 | ⏭ 跳過 | |
| **Step 1.5** 新舊事實定位 & retrieval 確認 | ✅ 完成 | SH/MH 透過 MQuAKE ground truth 精確定位；誤差 <1%；Old 取回率近 100% |
| **Step 3** Oracle 實驗 | 🔜 設計中 | 架構已清楚，待實作 |

---

## 實驗設置

| 項目 | 值 |
|---|---|
| RAG 系統 | HippoRAG-v2（NV-Embed-v2 + KG + PPR） |
| LLM | GPT-4o-mini |
| Chunk size | 512 tokens |
| Top-k | 10 |
| Context | 6k（455 個有序事實句） |
| 題數 | FC-SH 100 題、FC-MH 100 題 |

---

## 核心數據

### FC-SH（單跳）

| 子集 | 題數 | Acc |
|---|:---:|:---:|
| has_pair（有衝突對） | 74 | 59.5% |
| no_conflict_pair | 26 | 96.2% |
| **整體** | 100 | **69.0%** |

- GT 取回率 98.6%、Old 取回率 **100%**
- 失敗 30 題中 93% 是 `older_fact`（LLM 採信舊事實）
- Oracle A 理論上限：(69+27)/100 = **96%**

### FC-MH（多跳）

| 衝突跳數 | 題數 | 正確 | Acc |
|:---:|:---:|:---:|:---:|
| 1 跳 | 33 | 10 | 30.3% |
| 2 跳 | 48 | 1 | 2.1% |
| 3 跳 | 17 | 0 | 0.0% |
| 4 跳 | 2 | 0 | 0.0% |
| **整體** | 100 | 11 | **11.0%** |

- 失敗 89 題中 78% 是 `older_fact`
- GT 取回率 94-100%、Old 取回率 97-100%

---

## 分析腳本與產出檔案

| 檔案 | 說明 |
|---|---|
| `analysis/analyze_sh_512_mquake.py` | SH 分析主腳本 |
| `analysis/analyze_mh_512_mquake.py` | MH 分析主腳本 |
| `analysis/generate_step1a_charts.py` | 圖表生成（4 張圖） |
| `analysis/step1a_methodology.md` | Step 1A 完整方法論 |
| `analysis/step1a_sh_summary.md` | FC-SH 結果摘要 + Oracle 預期 |
| `analysis/results/sh_512_mquake_analysis.json` | SH 100 題分析結果 |
| `analysis/results/mh_512_mquake_analysis.json` | MH 100 題分析結果 |
| `analysis/results/fig_conflict_hops_vs_acc.png` | 圖1：衝突跳數 vs Acc |
| `analysis/results/fig_hop_composition.png` | 圖4：各組 2/3/4-hop 組成 |
| `analysis/results/fig_retrieval_vs_acc.png` | 圖2：Retrieval 品質 vs Acc |
| `analysis/results/fig_error_distribution.png` | 圖3：失敗原因分布 |

---

## 重要發現

### 1. no_conflict_pair 的根本原因（不是 context size 問題）

FC-SH 26 題 `no_conflict_pair` 分類：

| 類型 | SH | MH hops | 說明 |
|---|:---:|:---:|:---|
| Entity cascade | 13 | 30 | upstream rewrite 換 entity，新 entity 沒有舊版本 |
| 此跳未被改寫（old ans = new ans） | 13 | 36 | 這跳原本就不是衝突跳 |

→ 換更大的 context（32k/64k/262k）不會改變這個結構性事實。

### 2. 1-conflict-hop MH vs SH has_pair 的差距

- SH has_pair Acc = 59.5%
- MH 1-conflict-hop Acc = 30.3%（2-hop 28%、3-hop 40%、4-hop 33%）
- 差距來自多跳鏈式推理本身的難度，不只是衝突

### 3. Oracle 有效樣本

| 任務 | 有效樣本 |
|---|:---:|
| SH Oracle | 74 題（has_pair） |
| MH Oracle（全衝突） | 48 題（2/2: 36題、3/3: 10題、4/4: 2題） |

---

## Step 3 Oracle 實驗設計

### 三個變體

| 變體 | 做法 | 目的 |
|---|---|---|
| **Oracle A（必做）** | 移除含舊事實的 passage，只留新事實 | 驗證「乾淨 context → Acc 大幅上升」 |
| **Oracle C（必做）** | 移除新事實，只留舊事實 | 對照組：LLM 在單一版本下推理穩定 |
| **Oracle B（可選）** | MH 逐跳刪除 | 觀察哪一跳貢獻最大 |

### 實作方式（獨立腳本，方向 A）

```
1. 讀 analysis JSON → 取得每題 old_rank（哪個 passage 含舊事實）
2. 讀 retrieved JSON（outputs/rag_retrieved/.../query_{id}_context_0.json）
3. 過濾掉 old_rank 的 passage
4. 重組 retrieval_context = "Passage 1:\n...\nPassage 2:\n..."
5. 直接呼叫 OpenAI API（system_prompt + filtered_context + question）
6. 評估 exact_match
```

### Prompt 格式（已確認，utils/templates.py）

```
system: "Pretend you are a knowledge management system. Each fact...serial number...
         newer fact has larger serial number..."
user:   [retrieval_context] + "\n" + [question template]
```

### 待確認

- OpenAI API key 位置（環境變數 or 設定檔）

---

## 資料路徑

| 資料 | 路徑 |
|---|---|
| SH results | `outputs/gpt-4o-mini-hippo_rag_v2_nv/Conflict_Resolution/factconsolidation_sh_6k_..._k10_chunk512_results.json` |
| MH results | `outputs/gpt-4o-mini-hippo_rag_v2_nv/Conflict_Resolution/factconsolidation_mh_6k_..._k10_chunk512_results.json` |
| SH retrieved | `outputs/rag_retrieved/Structure_rag_hippo_rag_v2_nv/k_10/factconsolidation_sh_6k/chunksize_512/query_{id}_context_0.json` |
| MH retrieved | `outputs/rag_retrieved/Structure_rag_hippo_rag_v2_nv/k_10/factconsolidation_mh_6k/chunksize_512/query_{id}_context_0.json` |
| MQuAKE | `/home/yhchiang/MQuAKE/datasets/MQuAKE-CF.json` |
| 6k context | `/home/yhchiang/MemoryAgentBench_old/scripts/contexts/factconsolidation_sh_6k_context_0.txt` |
