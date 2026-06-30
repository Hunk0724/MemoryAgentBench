# Mem0 / Mem0g × Gemini 5-model × 2-chunk pilot 執行計畫

> 建立日期:2026-05-24
> 目的:整合所有 pieces(yaml、agent.py、alignment、Neo4j、log schema)成一份可執行的 pilot SOP。

---

## 0. Pilot 目標

跑 **6k 對話歷史**(因為 6k MQuAKE GT 已對應好)的 FC-SH / FC-MH × mem0 / mem0g × 5 個 Gemini model × 2 個 chunk_size = **40 個實驗**。

實驗目的:
1. **方法層**:比較 mem0(向量版)vs mem0g(圖版)在衝突偵測的差異
2. **LLM 層**:用 mem0 內部 Gemini class default(`gemini-1.5-flash-latest`)當 baseline-of-baselines,看升級到 SOTA Gemini 後的 gain
3. **Chunk size 層**:`chunk_size=512`(跟過去 HippoRAG-v2 + PropRAG 實驗對齊)vs `chunk_size=4096`(mem0 paper / benchmark default)
4. **方法論透明**:embedding 固定 `text-embedding-004`(與 mem0 Gemini class default 對齊),變數隔離乾淨

---

## 1. 已準備好的 pieces

| 項目 | 位置 | 狀態 |
|---|---|---|
| MQuAKE-CF.json | `/home/yhchiang/MQuAKE/datasets/MQuAKE-CF.json` | ✅ cloned |
| FC 6k context | [analysis/contexts/factconsolidation_6k_context.txt](../../../analysis/contexts/factconsolidation_6k_context.txt) | ✅ 455 facts |
| 32k/64k/262k context | [analysis/contexts/](../../../analysis/contexts/) | ✅ 全部 4 個長度 cache 完成 |
| MQuAKE alignment 腳本 | [analysis/align_mem0_mquake.py](../../../analysis/align_mem0_mquake.py) | ✅ 驗證過 |
| agent.py 改動 | [agent.py](../../../agent.py) `_initialize_mem0_agent` / `_answer_with_client` | ✅ syntax check |
| 20 個 yaml | `configs/agent_conf/RAG_Agents/Gemini/Structure_rag_mem0{,g}_<MODEL>_chunk{512,4096}.yaml` | ✅ 全部生成 |
| Neo4j setup 指南 | [docs/infrastructure/neo4j_setup.md](../../infrastructure/neo4j_setup.md) | ✅ |
| log schema | [docs/experiments/log_schema.md](../log_schema.md) | ✅ |

---

## 2. 執行前準備

### 2.1 Neo4j 啟動(mem0g 必須)

```bash
docker run -d --name neo4j-mem0g \
  -p 7474:7474 -p 7687:7687 \
  -v $HOME/neo4j-data:/data \
  -e NEO4J_AUTH=neo4j/mem0gpassword \
  -e NEO4J_PLUGINS='["apoc"]' \
  neo4j:5-community

# 等 30 秒後驗證
sleep 30 && curl -s http://localhost:7474 > /dev/null && echo "Neo4j ready"
```

詳見 [[../../infrastructure/neo4j_setup.md]]。

### 2.2 Vertex AI 認證

```bash
export GOOGLE_GENAI_USE_VERTEXAI=true
export GOOGLE_CLOUD_PROJECT=<your-gcp-project>
export GOOGLE_CLOUD_LOCATION=us-central1
# 確認 ADC
gcloud auth application-default login   # 若尚未登入
```

### 2.3 5 個 Gemini model dry-run(必做!)

跑 pilot 前先 dry-run 每個 model 1 個 API call,確認字串有效:

```bash
for m in gemini-1.5-flash-latest gemini-2.5-flash-lite gemini-2.5-flash gemini-3.1-flash-lite gemini-3.5-flash; do
  echo "=== $m ==="
  /home/yhchiang/miniconda3/envs/MABench/bin/python -c "
from google import genai
import os
client = genai.Client(vertexai=True, project=os.environ['GOOGLE_CLOUD_PROJECT'], location='us-central1')
try:
    r = client.models.generate_content(model='$m', contents='Say hi briefly.')
    print('  OK:', (r.text or '')[:60])
except Exception as e:
    print('  FAIL:', type(e).__name__, str(e)[:120])
"
done
```

**Fallback 規則**:
- 若 `gemini-1.5-flash-latest` 4xx:改用 `gemini-1.5-flash-002`,**改 [generate_mem0_yaml_variants.py](../../../bash_files/generate_mem0_yaml_variants.py) 的 MODELS,重新生成**
- 若 `gemini-3.5-flash` 4xx:從 5-model 降為 4-model 矩陣,文件記錄此事

### 2.4 確認 mem0 內 OPENAI_API_KEY 不會被觸發

由於 yaml 已注入完整 `mem0_config`(包含 `llm` / `embedder` 都是 vertexai),mem0 不會去抓 OPENAI_API_KEY。但若 yaml 沒注入(舊版),`Memory()` 會 fallback OpenAI 然後崩。**確認** yaml 內有 `mem0_config:` 區塊。

---

## 3. 主執行流程

### 3.1 單一實驗命令(範例)

```bash
/home/yhchiang/miniconda3/envs/MABench/bin/python main.py \
  --agent_config  configs/agent_conf/RAG_Agents/Gemini/Structure_rag_mem0_gemini-2.5-flash-lite_chunk512.yaml \
  --dataset_config configs/data_conf/Conflict_Resolution/Factconsolidation_mh_6k.yaml
```

執行後產出三層 log(詳見 [[../log_schema.md]]):
- Layer A: `outputs/rag_retrieved/Structure_rag_mem0_gemini-2.5-flash-lite_chunk512/k_100/factconsolidation_mh_6k/chunksize_512/ingestion_context_0.jsonl`
- Layer B: 同目錄 `query_*_context_*.json`
- Layer C: `outputs/gemini-2.5-flash-lite-mem0-chunk512/Conflict_Resolution/factconsolidation_mh_6k_*_results.json`

### 3.2 批次跑 40 個實驗

**先跑 chunk=512(對齊 HippoRAG-v2/PropRAG)**:

```bash
for method in mem0 mem0g; do
  for model in gemini-1.5-flash-latest gemini-2.5-flash-lite gemini-2.5-flash gemini-3.1-flash-lite gemini-3.5-flash; do
    for sub in sh mh; do
      echo "===== $method × $model × FC-$sub × chunk=512 ====="
      /home/yhchiang/miniconda3/envs/MABench/bin/python main.py \
        --agent_config  configs/agent_conf/RAG_Agents/Gemini/Structure_rag_${method}_${model}_chunk512.yaml \
        --dataset_config configs/data_conf/Conflict_Resolution/Factconsolidation_${sub}_6k.yaml \
        2>&1 | tee logs/pilot_${method}_${model}_${sub}_6k_chunk512.log
    done
  done
done
```

**跑完 chunk=512 全部 20 個後,再跑 chunk=4096(benchmark default)**:

```bash
# 同上,把 chunk512 全部換成 chunk4096
```

### 3.3 跑前 sanity:1 個 dry-run smoke test

正式跑 20 個前,**強烈建議**先跑 1 個 smoke:

```bash
/home/yhchiang/miniconda3/envs/MABench/bin/python main.py \
  --agent_config  configs/agent_conf/RAG_Agents/Gemini/Structure_rag_mem0_gemini-2.5-flash-lite_chunk512.yaml \
  --dataset_config configs/data_conf/Conflict_Resolution/Factconsolidation_sh_6k.yaml \
  2>&1 | tail -50
```

verify:
- ✅ mem0 不報錯
- ✅ outputs 出來且 JSON 結構正確
- ✅ `metrics.exact_match` 不是全 0(=> answer 客戶端 OK)
- ✅ `ingestion_context_*.jsonl` 有 ADD/UPDATE/NOOP events

確認後再批次跑剩餘的。

---

## 4. 跑完後:alignment + 分析

### 4.1 對每個實驗跑 alignment

```bash
RUN="gemini-2.5-flash-lite-mem0-chunk512"
AGENT="Structure_rag_mem0_gemini-2.5-flash-lite_chunk512"
for sub in sh mh; do
  /home/yhchiang/miniconda3/envs/MABench/bin/python analysis/align_mem0_mquake.py \
    --results outputs/${RUN}/Conflict_Resolution/factconsolidation_${sub}_6k_*_results.json \
    --context analysis/contexts/factconsolidation_6k_context.txt \
    --mode ${sub} \
    --retrieval-dir outputs/rag_retrieved/${AGENT}/k_100/factconsolidation_${sub}_6k/chunksize_512 \
    --out analysis/results/${RUN}_${sub}_6k_mquake.json
done
```

### 4.2 跨實驗統計表

(待補:寫一個 aggregate script 把 40 個實驗的 alignment results 彙整成一張表,欄位:method × model × chunk × subset → accuracy / has_pair_rate / hop-level fail-mode 分佈)

---

## 5. 預期時間 / cost

| 配置 | per-experiment | × 4 subset(2 hop × 2 method) | × 5 model |
|---|---|---|---|
| mem0 × 6k × chunk=512 | 5-10 min | 20-40 min | 100-200 min |
| mem0g × 6k × chunk=512 | 15-25 min | 60-100 min | 300-500 min |
| 小計 chunk=512 | | | **6.6-12 hr** |
| chunk=4096 同上 | | | **6.6-12 hr** |
| **40 個實驗 total** | | | **13-24 hr** |

Vertex Gemini Flash 系列總 token 估 ~8M,**單位數美金級別**(具體看 Google 當前 pricing)。

可分兩晚跑:
- Night 1:chunk=512 全部 20 個
- Night 2:chunk=4096 全部 20 個

---

## 6. 失敗回滾

| 失敗情境 | 處理 |
|---|---|
| Neo4j 容器壞掉 | 重啟 `docker restart neo4j-mem0g`;mem0g 用 user_id 隔離,資料不會混 |
| Vertex quota 撞牆 | agent.py 已有 10 次 retry([line 394-425](../../../agent.py#L394-L425)),逾時則此實驗失敗,不影響其他 |
| 某個 model API 4xx | 該 5-model 矩陣降為 4-model,文件記錄 |
| 某題 LLM 卡住 | 跳過該題(`exact_match=null`),其他正常 |
| 中途停電 | mem0 內部 ingest 沒 checkpoint,要從頭重跑該實驗 |

---

## 7. 相關文件

- 方法論:[[../../baseline_methods/baseline_methods_paper_vs_impl.md]]
- MQuAKE alignment 機制:[[../../ground_truth/mquake_alignment_guide.md]]
- log 結構:[[../log_schema.md]]
- Neo4j 安裝:[[../../infrastructure/neo4j_setup.md]]
- yaml generator:[bash_files/generate_mem0_yaml_variants.py](../../../bash_files/generate_mem0_yaml_variants.py)

---

## 8. 下一階段(此 pilot 之後)

跑完 6k 全部 40 個實驗 + alignment + 統計後,**根據結果**決定下一階段:

| 結果情境 | 下一步 |
|---|---|
| Mem0g 明顯勝過 mem0 | 主推「圖層帶來衝突偵測能力」敘事 |
| Mem0g 沒勝過 mem0 | 主推「為什麼商業用 mem0 拋棄圖層」敘事 |
| 5 model 結果差異不大 | 跳過 32k+ 的 LLM 矩陣,只跑 best model 的 32k/64k/262k |
| Chunk_size 影響顯著 | 加做 chunk size ablation |

每種敘事的對應論述模板在 [[../../baseline_methods/baseline_methods_paper_vs_impl.md]] §6.3。
