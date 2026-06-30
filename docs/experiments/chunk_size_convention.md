# MemoryAgentBench Chunk-size 設定 Convention

> 日期:2026-05-29(2026-05-29 補充:在程式碼層級 verify 完成)
> 目的:鎖定各 method × task 該用哪個 chunk_size,避免方法論不一致
> 來源:MABench paper(使用者引述)+ 程式碼層級 verify

---

## ⚠️ 關鍵釐清:兩條獨立的 `chunk_size` 軸

```
┌──────────────────────────────────────────────────────────────────────┐
│  軸 A (dataset config)                                               │
│  configs/data_conf/*.yaml 內的 chunk_size                            │
│  → 給 retrieval-based method(HippoRAG, RAG, RAPTOR)用                │
│  → agent.py:374 `self.chunk_size = dataset_config['chunk_size']`     │
│                                                                      │
│  Paper convention:                                                   │
│    FC/SF/AR (synthetic) → 512                                        │
│    EventQA/InfBench/MCC/Recom (continuous) → 4096                    │
│                                                                      │
│  Codebase 實作位置:                                                  │
│    Factconsolidation_{sh,mh}_512.yaml  ← chunk_size: 512(專門檔)    │
│    Factconsolidation_{sh,mh}_{6k,...}.yaml ← chunk_size: 4096(context長度變體)│
└──────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────┐
│  軸 B (agent config)                                                 │
│  configs/agent_conf/*.yaml 內的 agent_chunk_size                     │
│  → 給 memory construction method(mem0/mem0g/zep/cognee/letta)用     │
│  → agent.py:255 `self.chunk_size = agent_config['agent_chunk_size']` │
│                                                                      │
│  Paper convention:                                                   │
│    mem0/zep/cognee/letta → uniformly 4096 across all datasets        │
│                                                                      │
│  Codebase 實作位置:                                                  │
│    所有標準 mem0/zep/cognee/letta yaml 都寫 agent_chunk_size: 4096   │
└──────────────────────────────────────────────────────────────────────┘
```

**兩軸互不影響**:mem0 不讀 dataset chunk_size、HippoRAG 不讀 agent_chunk_size。

---

## 0. TL;DR

| Method 類別 | FC (SF) | AR | ∞Bench / EventQA | MCC / Recom |
|---|---|---|---|---|
| **Mem0, Mem0g, Zep, Cognee, MIRIX** | **4096** | **4096** | **4096** | **4096** |
| HippoRAG-v2, PropRAG, Simple RAG, etc. | 512 | 512 | 4096 | 4096 |
| LCA(long-context)| N/A(無 chunk) | N/A | N/A | N/A |

**核心規則**:
- **Synthetic context task**(AR, FC/SF):**chunk=512**(retrieval-based methods)
- **Continuous text task**(∞Bench, EventQA, MCC, Recom):**chunk=4096**
- **Mem0/Zep/Cognee/MIRIX**(memory construction methods):**統一 4096**,不分 task(因為 cost / API call overhead 高,小 chunk 會放大成本)

---

## 1. Paper 原文(MABench 設定章節)

> We use smaller chunk size (**512**) for synthetic context used in **AR and SF**.
> For some tasks based on continuous text, such as **∞Bench and EventQA**, we used a larger chunk size (**4096**).
> For tasks such as **MCC and Recom**, considering the characteristics of these tasks and the computational cost, we also chose a larger chunk size (**4096**).
> For the memory construction methods that are more time-consuming and requiring more API cost, **Mem0, Zep, Cognee and MIRIX, we uniformly used a chunk size of 4096 across all datasets**.

---

## 2. 程式碼 verify(2026-05-29)

### 2.1 Agent yaml 內 `agent_chunk_size` 都是 4096(對應 paper convention ✅)

```
configs/agent_conf/RAG_Agents/gpt-4o-mini/Structure_rag_gpt-4o-mini-mem0.yaml    : 4096
configs/agent_conf/RAG_Agents/gpt-4o-mini/Structure_rag_gpt-4o-mini-cognee.yaml  : 4096
configs/agent_conf/RAG_Agents/gpt-4o-mini/Structure_rag_gpt-4o-mini-zep.yaml     : 4096
configs/agent_conf/RAG_Agents/gpt-4o-mini/Agentic_memory_gpt-4o-mini-letta*.yaml : 4096
```

### 2.2 Dataset yaml 內 `chunk_size` 分佈

⚠️ **修正(2026-05-29 verify against MemoryAgentBench_original/)**:
- Original repo 所有 dataset yaml `chunk_size` 都是 **4096**(沒有任何 _512.yaml 變體)
- 我們 fork 後加的 `Factconsolidation_{sh,mh}_512.yaml` 不是 original convention 的一部分
- **Paper 引述「FC 用 512」的真實達成方式 = bash 命令列 override `--chunk_size_ablation 512`**(不是 yaml default)

### 2.3 真正的 chunk=512 來自 bash override(關鍵發現)

[MemoryAgentBench_original/bash_files/sh/run_memagent_rag_agents_chunksize.sh](../../../MemoryAgentBench_original/bash_files/sh/run_memagent_rag_agents_chunksize.sh) 配 [rag_agents_chunksize.txt](../../../MemoryAgentBench_original/bash_files/configs/rag_agents_chunksize.txt):

```
###hippo_rag_v2_nv
Structure_rag_gpt-4o-mini-hippo_rag_v2_nv.yaml  ...EventQA...    512   ← 所有 task
Structure_rag_gpt-4o-mini-hippo_rag_v2_nv.yaml  ...InfBench...   512   ← 包括 continuous text
Structure_rag_gpt-4o-mini-hippo_rag_v2_nv.yaml  ...FC...         512

###mem0
Structure_rag_gpt-4o-mini-mem0.yaml             ...EventQA...        ← 沒第三欄,不 override
Structure_rag_gpt-4o-mini-mem0.yaml             ...FC...
```

對應 [initialization.py:197-209](../../../MemoryAgentBench_original/initialization.py#L197-L209) 的 `_apply_chunk_size_ablation`:
- Memory agent(mem0/letta/cognee/zep)→ 把 `agent_chunk_size` 也設成同值
- 其他(HippoRAG / RAG / RAPTOR)→ 只改 `dataset_config['chunk_size']`

**所以實際 paper 跑時:HippoRAG-v2 / RAG-based 用 bash override 強制 chunk=512(不論 task),mem0 走 yaml default 4096**。

### 2.4 歷史 outputs 反推(GPT-4o-mini × mem0)

### 2.5 歷史 outputs 反推(GPT-4o-mini × mem0)

| Output filename | 真實 `agent_chunk_size` | 真實 `dataset chunk_size` | EM | n |
|---|---:|---:|---:|---:|
| factconsolidation_sh_6k chunk512 | **512** | 512 | 15.0% | 100 |
| factconsolidation_mh_6k chunk512 | **512** | 512 | 1.0% | 100 |
| factconsolidation_sh_6k chunk4096 | 4096 | 4096 | 0.0% | **2**(中斷) |

→ **歷史上 mem0 完整跑過的是 `agent_chunk_size=512`**(非標準!違反 paper convention),
   `agent_chunk_size=4096` 的 mem0 從未完整跑過 FC-MH。

---

## 3. 對本研究的影響

### 3.1 mem0 / mem0g pilot 的正解

**主跑 `agent_chunk_size=4096`**(對應 mem0 paper convention)。chunk=512 變體**只能當 ablation**。

更新後的 pilot 矩陣優先級:

| Priority | Method | `agent_chunk_size` | 目的 |
|---|---|---|---|
| **P0** | mem0 | **4096** | mem0 paper convention,主結果 |
| **P0** | mem0g | **4096** | mem0 paper convention,主結果 |
| P2 | mem0 | 512 | ablation(歷史用過,可對比) |
| P2 | mem0g | 512 | ablation |

### 3.2 HippoRAG-v2 / PropRAG / Ours 的設定

| Method | `dataset chunk_size` | 怎麼設 |
|---|---|---|
| HippoRAG-v2 跑 FC | **512** | 用 `Factconsolidation_{sh,mh}_512.yaml` |
| HippoRAG-v2 跑 EventQA/InfBench | 4096 | 用 `Eventqa_*.yaml`(預設 4096) |
| Ours | 對齊 HippoRAG | 同上 |

### 2.2 HippoRAG-v2 / PropRAG / Ours 的設定

| Method | FC chunk | 理由 |
|---|---|---|
| HippoRAG-v2 | **512** | paper convention(synthetic context) |
| PropRAG | **512** | 同上 |
| Ours(本方法) | **512** | 對齊 HippoRAG-v2 base,公平比較 |

### 2.3 「方法論公平性」的論述

當 paper §6.3 主表 LCA × Mem0 × Mem0g × HippoRAG-v2 × Ours 並列時:

- 每個 method 都用 **「該 method 在 MABench paper 中規定的 convention」** 跑,不是統一某個 chunk
- Mem0 用 chunk=4096(它自己的 convention),HippoRAG 用 chunk=512(它自己的 convention)
- Ours 對齊 HippoRAG(因為 Ours 改的是 HippoRAG-v2 之上的 module)→ chunk=512

→ Paper baselines 章節要明說「we follow per-method conventions from Yue et al. (MABench)」,避免 reviewer 質疑「為什麼 mem0 跟 HippoRAG 用不同 chunk size」。

---

## 3. 既有 yaml 狀態(本 repo)

`configs/agent_conf/RAG_Agents/Gemini/` 下 20 個 yaml,本來 5 model × 2 method × 2 chunk:

| Status | 用途 |
|---|---|
| `Structure_rag_mem0{,g}_<MODEL>_chunk4096.yaml` × 10 | **主跑** ✅ |
| `Structure_rag_mem0{,g}_<MODEL>_chunk512.yaml` × 10 | ablation(可選跑) |

---

## 4. 對 paper_draft 數字的影響

LCA × FC-MH 4 ctx 已跑完,LCA 無 chunk 概念,**不受影響**。

接下來跑 mem0/mem0g 時,**主跑 chunk=4096**,跟 LCA 結果並列。

---

## 5. 相關文件

- [[../paper_draft/lca_backbone_ctx_sweep.md]] — LCA 結果(無 chunk 維度)
- [[pilots/mem0_mem0g_pilot_plan.md]] — 主 pilot plan(需更新 chunk priority)
- [[../sync_with_claude_chat/FC_metrics_spec.md]] — Metric spec(M1 EM 主表)
