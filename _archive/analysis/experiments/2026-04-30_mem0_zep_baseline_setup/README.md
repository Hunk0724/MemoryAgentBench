# Phase 0 Baseline Setup — Mem0 + Zep on Gemini 3.1 Flash-Lite

> **日期**：2026-04-30
> **目的**：為 Phase 0 三天衝刺的 Step 1（Mem0/Zep audit）+ Step 3（Gemini 對齊 setup）+ detection F1 分析做準備工作。
> **狀態**：Setup 階段完成；Mem0 ingestion smoke pass；Zep detection F1 已從既有 GPT 資料計算；**全 100 題 Gemini fair compare 跑與 Mem0-graph 待後續 session**。
> **接續**：[Phase0 3day sprint spec.md](../../../Phase0%203day%20sprint%20spec.md) Step 1 + Step 3。

---

## 1. 三個確認問題

### Q1：Mem0 在 MemoryAgentBench 預設是 graph 還是 vector mode？

**Vector mode（無 graph）**。證據：
- `configs/agent_conf/RAG_Agents/gpt-4o-mini/Structure_rag_gpt-4o-mini-mem0.yaml` 無 `graph_store` 欄位
- `agent.py:232` 是 `self.memory = Memory()`（用預設 MemoryConfig）
- `mem0/memory/main.py:56-62`：`enable_graph = False` unless `self.config.graph_store.config` is truthy；預設 `GraphStoreConfig()` 的 `config = None`

→ 既有 Mem0 OOB FC-SH 15% / FC-MH 1% 是 vector mode 結果。**Mem0-graph 是獨立 baseline，需要 Neo4j + langchain-neo4j 才能跑**。

### Q2：Zep 流程哪裡可換 Gemini，哪裡是 Zep 內部 API？

| 步驟 | LLM 來源 | 可換 Gemini? |
|---|---|:---:|
| `client.user.add()` / `thread.create()` / `graph.create()` | Zep API (no LLM) | 不適用 |
| **`client.graph.add(type="text", data=content)`** | **Zep 內部 LLM**：episode 切分 / entity & edge extraction / 時間解析 / supersession (`invalid_at` 設定) | ❌ Zep cloud 內部 |
| `client.thread.add_messages()` | Zep 內部 | ❌ |
| `client.graph.search(scope='edges/nodes/episodes')` | Zep 內部（embedding + reranker）| ❌ |
| `client.thread.get_user_context()` | **Zep 內部 LLM**：context block summary | ❌ |
| `compose_search_context(...)` | Pure Python 拼接 | 不適用 |
| **`llm_response(self.oai_client, ...)`** | `methods/zep.py:OpenAIAgent`（目前 azure / openai / deepseek 三 source）| ✅ **加 gemini source 即可** |

→ Zep 換 Gemini **只能改最後一步（final QA reading）**。Detection / supersession / context summary 永遠是 Zep 內部 LLM。Paper 必須明示這個 caveat：「Zep 與 HippoRAG / Mem0 的 LLM 一致性有不可避免的 asymmetry」。

實作改動：在 `methods/zep.py:OpenAIAgent.__init__` 加 `elif source == "gemini": ... use google.genai.Client(vertexai=True, ...)` 分支，模仿 HippoRAG `methods/hipporag/llm/gemini_llm.py:CacheGemini`。

### Q3：Mem0 L1 smoke test 是否真的用了 ADD/UPDATE/DELETE pipeline？

**有，全 pipeline 運作**。從 `~/.mem0/history.db` 計數：

| Event | 數量 | 含義 |
|---|:---:|---|
| ADD | 445 | 新 fact 加入 vector store |
| UPDATE | 150 | LLM 判定新 fact supersede 既有 fact（**這就是 Mem0 內建 supersession detection**）|
| DELETE | 5 | LLM 判定刪除某 fact |

→ smoke test 不只「extraction 沒被拒」，整個 extraction → embedding similarity → Update Memory（LLM call #2）→ ADD/UPDATE/DELETE 都跑了。150 UPDATE events 表示 Mem0 在偵測 conflict — 但**是否偵測正確的方向**（FC 期望的舊→新 supersession）需後續用 FC GT 對照算 detection F1。

抽出的 sample facts 包含 counterfactual：
- "quarterback is associated with the sport of Muay Thai"
- "Headquarters of University of California, Berkeley is located in Botevgrad"
- "Frank Zappa died in the city of Berlin"

→ counterfactual 都被保留，meaning Mem0 把 6k FC 的新版本當「current state」存起來。

---

## 2. 本 session 完成的工作

### 2.1 Mem0 customized + Vertex Gemini 跑通

**問題**：Mem0 OOB 在 FC 上 ingestion 抽 0 facts（`FACT_RETRIEVAL_PROMPT` 拒收通用知識），FC-SH 1% / FC-MH 1%。

**解法（minimum viable mod）**：
- **L1 mod**：移除 `mem0/configs/prompts.py` 第 28-32 行兩個拒絕範例（`Input: Hi.` / `Input: There are branches in trees.`），其餘 prompt 不動
- 透過 `MemoryConfig(custom_fact_extraction_prompt=...)` 注入，**不改 vendored mem0 source code**
- LLM backbone：`gemini-3.1-flash-lite-preview` via Vertex AI ADC（仿 HippoRAG `CacheGemini`）
- Embedding：`sentence-transformers/all-MiniLM-L6-v2`（local，無 API key）
- 關鍵 config：`max_output_tokens=8192`（Update Memory 步驟枚舉 prior memories 越來越長，2048 會被截斷）

**Smoke 結果**：
- 12/12 chunks 全部抽出 facts
- 總 448 facts (vs OOB 0)
- 接近 dataset 455 facts 全部 → Mem0 customized 能正確 ingest 整個 6k

### 2.2 Zep detection F1（從既有 audit 算）

[scripts/zep_detection_f1.py](scripts/zep_detection_f1.py) 從既有 `analysis/results/oracle_a/zep_{sh,mh}_invalidation_audit_v2.json`（GPT-4o-mini run）計算：

| | Precision | Recall | F1 | TP | FP | FN |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| **Zep FC-SH** | 42.6% | 27.0% | **33.1%** | 20 | 27 | 54 (out of 74 has_pair) |
| **Zep FC-MH** (hop-level) | 89.4% | 31.4% | **46.5%** | 59 | 7 | 129 (out of 188 has_pair hops) |

**核心觀察**：
- **SH 25 個 wrong-direction supersession**：Zep 在 counterfactual 上把 invalid 方向標反了（invalidate NEW 而非 OLD），world-knowledge bias 擊敗 supersession 訊號 — 這是 paper main motivation 的具體證據
- **MH precision 89% 但 recall 31%**：MH 的 invalidation 比較準（少誤標方向）但**大半 has_pair 根本沒被偵測**（188 個 has_pair hops 只 detect 59）
- **Zep detection F1 < 50%**，遠低於 OA2 oracle 的 perfect detection — **這就是 paper 主張「過去沒人做好 multi-hop knowledge update」的具體量化**

---

## 3. 檔案地圖

```
2026-04-30_mem0_zep_baseline_setup/
├── README.md                    ← 本檔
├── scripts/
│   ├── mem0_vertex_gemini_llm.py      ← Mem0 自訂 LLM provider，Vertex Gemini ADC
│   ├── mem0_l1_smoke_test.py          ← L1 minimal-mod smoke ingestion-only
│   └── zep_detection_f1.py            ← Zep detection F1 純分析（無 LLM 呼叫）
└── results/
    ├── mem0_l1_smoke_results.json     ← Mem0 smoke 12 chunks × facts
    ├── zep_detection_metrics.json     ← Zep P/R/F1
    └── zep_{sh,mh}_invalidation_audit_input.json  ← 計算 F1 的 input data 副本
```

**外部依賴**（未複製進來，原檔保留）：
- `analysis/results/{sh,mh}_512_mquake_analysis.json` — Zep F1 計算依賴（has_pair 母數）
- `analysis/contexts/factconsolidation_6k_context.txt` — Mem0 smoke 的輸入 6k context
- `outputs/rag_retrieved/Structure_rag_mem0/.../ingestion_context_0.jsonl` — OOB baseline 0 facts 的證據
- `~/.mem0/history.db` — Mem0 SQLite history (執行階段 sideeffect，非 input)

**重跑指南**：
```bash
cd /home/yhchiang/MemoryAgentBench
# 純分析 (Zep F1)
python analysis/experiments/2026-04-30_mem0_zep_baseline_setup/scripts/zep_detection_f1.py

# Mem0 smoke (需 Vertex AI ADC + .env 含 GOOGLE_GENAI_USE_VERTEXAI 等)
rm -rf .cache/mem0_smoke_qdrant
conda run -n MABench --no-capture-output python \
  analysis/experiments/2026-04-30_mem0_zep_baseline_setup/scripts/mem0_l1_smoke_test.py
```

---

## 4. 待後續 session 的工作

1. **Mem0 customized × Gemini × FC-SH/MH 全 100 題**：把 L1 mod + Vertex Gemini wrapper 接到 `agent.py:_initialize_mem0_agent` + 新 yaml，跑全 200 題
2. **Zep × Gemini inference-side**：擴 `methods/zep.py:OpenAIAgent` 加 gemini source + 新 yaml，跑全 200 題（ingestion 無需重跑，已在 `outputs/gpt-4o-mini-zep/`）
3. **Mem0-graph baseline**：需要 Neo4j docker setup + `langchain-neo4j` 安裝，spec Step 1 audit 的 fallback
4. **Mem0 detection F1 計算**：跑完 200 題後從 ~/.mem0/history.db 抽 UPDATE events，比對 FC GT old/new pairs 算 P/R/F1（類似 zep_detection_f1.py 但 input 不同）
5. **對比表填好** + **模式 A/B/C/D 判定**（spec Step 5）

---

## 5. 設計決策摘要（給 paper baseline reproducibility）

| 決策 | 理由 |
|---|---|
| Mem0 用 L1 minimal-mod（移 2 few-shots）而非完全自訂 prompt | 保留 Mem0 原本的 "Personal Information Organizer" role / 7 categories / footer，最小改動 → 可被合理稱為 "Mem0 customized baseline"（paper 必須明示移除 2 行的 reproducibility 說明）|
| max_tokens=8192 而非 default 2048 | Update Memory step 在累積 memory 後輸出大型 JSON，2048 會被截斷觸發 `MAX_TOKENS` finish_reason → 變相讓 Mem0 失效 |
| Vertex AI ADC 而非 google-generativeai API key | 跟 HippoRAG-v2 / 9 個 oracle 同一條 Gemini 路徑，避免 SDK 不一致 |
| Embedding 用 HuggingFace MiniLM 而非 OpenAI text-emb-3-small | 沒 OPENAI_API_KEY 可用；MiniLM 是中立 baseline；paper 的 fair compare 對象是「Mem0 conflict detection 邏輯」而非 embedding 模型 |
| 不啟用 Mem0-graph mode | 既有 OOB baseline 是 non-graph，先匹配既有 baseline；graph mode 是獨立 baseline 後續做 |

---

*產出日期：2026-04-30*
*下一步等使用者拍板：(1) 全 200 題 Mem0 customized 跑 + Zep Gemini inference 跑；(2) Mem0-graph baseline 做不做*
