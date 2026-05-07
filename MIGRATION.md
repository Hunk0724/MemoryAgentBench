# Migration Guide — Restoring this repo on a new machine

> 從 GX10-2 遷移到任何相容硬體的完整步驟。
> Last updated: 2026-05-07
> Maintainer: Hunk0724

## 1. 這個 repo 是什麼

這是 [MemoryAgentBench](https://github.com/ai-hyz/MemoryAgentBench) (ICLR 2026) 的**私有研究 fork**,聚焦在 FactConsolidation (FC-SH / FC-MH) 衝突解決任務上,跑三個系統的對比實驗:

- **HippoRAG-v2 + NV-Embed-v2**(KG-based RAG)
- **Mem0**(LLM-paraphrase fact extraction with filter-at-write)
- **Zep**(temporal graph with annotation-at-inference)

論文研究主軸見 [`analysis/paper_motivation/motivation_narrative.md`](analysis/paper_motivation/motivation_narrative.md)。

## 2. 硬體需求

完整討論見 [`docs/hardware_request_6k.md`](docs/hardware_request_6k.md)。一句話:

| 階段 | GPU memory | 系統 RAM | 備註 |
|---|---|---|---|
| 6k FC method design 階段(主要工作) | **20 GB**(建議)/ 16 GB(緊) | 64 GB | NV-Embed-v2 fp16 14.6 GB 是地板 |
| 32k FC indexing(一次性) | 同上 | 67 GB peak | 已實測 |
| 128k LongMemEval | TBD | >120 GB | 需 streaming patch |

任何 NVIDIA GPU ≥ 16 GB(RTX 4080 / RTX A4500 / 3090 / 4090 / A5000)+ CUDA 12.x 都可用。

## 3. Quick start(理想路徑,假設新機器是 Linux + CUDA 12.x + miniconda)

```bash
# 1. Clone (SSH)
git clone git@github.com:Hunk0724/MemoryAgentBench-private.git
cd MemoryAgentBench-private
git checkout exp/chunk-size

# 2. 建兩個 conda env
conda env create -f setup/MABench_env.yml         # 主 env (Mem0, Zep, evaluation)
conda env create -f setup/hipporag_env.yml        # HippoRAG-v2 (transformers + NV-Embed-v2)

# 3. 設 API keys (新建 .env, 內容見 §5)
nano .env

# 4. 設 HF cache 位置(避免下載到 root-owned dir)
export HF_HOME=$(pwd)/.cache/huggingface

# 5. Smoke test (見 §7)
bash run_hipporag_gemini.sh    # 第一次會下載 NV-Embed-v2 (15 GB)
```

## 4. Conda envs

| env | 用途 | 對應檔案 |
|---|---|---|
| `MABench` | 主環境(Mem0, Zep, evaluation, run scripts) | [`setup/MABench_env.yml`](setup/MABench_env.yml) |
| `hipporag_env` | HippoRAG-v2 跑 NV-Embed-v2(transformers 版本相容) | [`setup/hipporag_env.yml`](setup/hipporag_env.yml) |

```bash
conda env create -f setup/MABench_env.yml
conda env create -f setup/hipporag_env.yml
```

如果 yml 重建失敗(常因 CUDA wheel 版本不匹配),fallback:
```bash
# Manual MABench
conda create -n MABench python=3.10 -y
conda activate MABench
pip install -r requirements.txt

# Manual hipporag_env (需 transformers 跟原 repo 相容版,參考 hipporag_env.yml 的 pinned versions)
conda create -n hipporag_env python=3.10 -y
conda activate hipporag_env
# Install per setup/hipporag_env.yml (注意 transformers 版本不能太新,否則 NV-Embed-v2 會缺 all_tied_weights_keys)
```

## 5. API keys / `.env`

`.env` 已 gitignore,需新建。必填:

```bash
# .env 範本
OPENAI_API_KEY=sk-...                     # gpt-4o-mini (若要跑 gpt 系列實驗)
GOOGLE_API_KEY=AIza...                    # Gemini direct API (gemini-3.1-flash-lite-preview)
GOOGLE_CLOUD_PROJECT=fc-mh-494213         # 如果走 Vertex (見 run_*_gemini.sh)
GOOGLE_GENAI_USE_VERTEXAI=True            # 若用 Vertex,否則設 False / 不設
GOOGLE_CLOUD_LOCATION=global              # Vertex 用
ZEP_API_KEY=z_...                         # Zep cloud API key (跑 Zep 實驗才需要)
```

**Gemini API**: 推薦走 Vertex(已在多支 `run_*_gemini.sh` 內預設),需:
1. `gcloud auth application-default login` 完成 ADC
2. `gcloud config set project fc-mh-494213`(或你自己的 project)

## 6. NV-Embed-v2 模型(15 GB,自動下載)

```bash
export HF_HOME=$(pwd)/.cache/huggingface
# transformers 第一次 from_pretrained("nvidia/NV-Embed-v2") 會自動下載到 .cache/huggingface/hub/models--nvidia--NV-Embed-v2/
```

**注意**: 預設 `~/.cache/huggingface` 可能因為先前曾以 root 跑而擁有 root 權限導致 PermissionError,務必設 `HF_HOME` 到專案內路徑或乾淨的 user 路徑。

## 7. Smoke test — 確認新環境跟既有 baseline 一致

跑這條最小命令,跟現有 baseline 比對:

```bash
# 6k FC-MH HippoRAG-v2 (應產出 EM ≈ 22% MH)
bash run_hipporag_gemini.sh
# 結果在: outputs/gemini-3.1-flash-lite-preview-hippo_rag_v2_nv/Conflict_Resolution/factconsolidation_mh_6k_*_results.json
```

驗證項目(對應 `motivation_narrative.md` §3 表格):

| 系統 × split | 預期 EM | reference baseline 路徑 |
|---|---|---|
| HippoRAG-v2 vanilla 6k MH | 22% | (在 reference 中已有) |
| HippoRAG-v2 vanilla 6k SH | 77% | 同上 |
| Mem0 aligned 6k MH | 44% | `analysis/experiments/2026-05-02_mem0_zep_gemini_full100/` |
| Mem0 aligned 6k SH | 85% | 同上 |
| Zep aligned 6k MH | 28% | 同上 |
| Zep aligned 6k SH | 89% | 同上 |

詳細等價性比對腳本(若需要):

```bash
# 比對 OpenIE 結果(應 bit-identical,Gemini API + temp=0)
diff outputs/rag_retrieved/NV-Embed-v2/factconsolidation_mh_6k/chunksize_512/context_id_0/openie_results_ner_gemini-3.1-flash-lite-preview.json \
     <reference baseline 路徑>

# 比對 fact embeddings (L2 距離 < 1e-3 可接受 fp16 跨 GPU 微小漂移)
python -c "
import pandas as pd, numpy as np
new = pd.read_parquet('outputs/rag_retrieved/NV-Embed-v2/factconsolidation_mh_6k/chunksize_512/context_id_0/gemini-3.1-flash-lite-preview_nvidia_NV-Embed-v2/fact_embeddings/vdb_fact.parquet')
ref = pd.read_parquet('<reference path>')
diffs = [(np.linalg.norm(np.array(new.iloc[i]['embedding']) - np.array(ref.iloc[i]['embedding']))) for i in range(min(len(new), len(ref)))]
print(f'mean L2: {np.mean(diffs):.6f}, max L2: {max(diffs):.6f}')
"
```

## 8. 目錄結構

| 路徑 | 內容 |
|---|---|
| `analysis/` | 所有 research script + paper narrative + experiment 記錄 |
| `analysis/paper_motivation/` | motivation_narrative.md, method_design.md, generate_slides_figures.py |
| `analysis/experiments/2026-*/` | 階段性 experiment 記錄(timestamped) |
| `analysis/results/` | derived metrics: detection bucket、profile JSON、aligned correspondence |
| `methods/hipporag/` | HippoRAG-v2 實作 (modified for Gemini support) |
| `mem0/`, `letta/`, `cognee/` | 其他 memory system 整合 |
| `configs/` | yaml 配置: agent / data / method |
| `outputs/<model>-*/Conflict_Resolution/*.json` | 每次實驗的 EM 結果 (Tier 1 備份) |
| `outputs/rag_retrieved/` | HippoRAG indexing cache: graph.graphml + fact/chunk embeddings + OpenIE 結果 (Tier 2) |
| `docs/hardware_request_6k.md` | 硬體需求說明 |
| `run_*.sh`, `run_zep_*.py` | 實驗 driver scripts |
| `setup/*.yml` | conda env exports |

## 9. 哪些東西**不**在 repo 裡(刻意排除)

| 排除項 | 理由 | 如何重建 |
|---|---|---|
| `.cache/`, `cache/` (15 GB) | NV-Embed-v2 model weights | transformers 第一次 from_pretrained 自動下載 |
| `__pycache__/`, `*.pyc` | Python bytecode | 自動再生 |
| `*.db`(Mem0 history) | 大且每次 ingestion 重建 | 跑 `run_zep_mem0_phase1.sh` 之類重建 |
| `.env` | API keys 不能進 repo | 見 §5 範本 |

## 10. Common gotchas

1. **NV-Embed-v2 缺 `all_tied_weights_keys`**: 表示 transformers 版本太新。`hipporag_env` pin 了相容版本,新機器照 yml 建即可。如果出問題,降到 transformers ≤ 4.40.0
2. **HF cache PermissionError**: 上面講過,設 `HF_HOME` 到 user-owned 目錄
3. **GPU OOM at indexing**: 如果不是 GB10 unified memory,而是 16 GB GPU,把 `methods/hipporag/utils/config_utils.py` 的 `embedding_batch_size` 從 16 降到 4 或 2(實測 bs=4 chunks max_len=512 peak 16.76 GB)
4. **Gemini Vertex 認證**: `gcloud auth application-default login` 之後才能跑 `run_*_gemini.sh`
5. **resume 機制**: 大部分 run_*.py 跑到一半中斷可以重跑同樣命令自動續跑(Mem0/Zep ingestion + RAG QA 都支援)— 不要刪 partial output 檔
6. **方法層 Mem0 / Zep 對齊**:這是論文研究核心,任何 bare 跟 aligned baseline 不對齊都是大忌(見 [`analysis/paper_motivation/A_pipeline_alignment_verification.md`](analysis/paper_motivation/A_pipeline_alignment_verification.md))

## 11. Quick reference — 最常見的命令

```bash
# 跑 HippoRAG-v2 6k FC-SH/MH (Gemini)
bash run_hipporag_gemini.sh

# 跑 Mem0 6k aligned (有 anti-knowledge few-shots 修正)
python analysis/run_mem0_gemini_aligned.py

# 跑 Zep 6k aligned
python run_zep_mh_full100.py

# 重生 detection bucket (v2 unified algorithm)
python analysis/regen_detection_buckets.py

# 重生 NV-Embed VRAM profile
python analysis/profile_nvembed_vram.py

# 看實驗結果完整 breakdown
python analysis/aligned_full_breakdown.py
```

---

## 後續維護

如果之後又改了關鍵環境設定 / 硬體,記得回頭更新本檔(尤其 §5 API keys 跟 §7 預期 EM 數字)。
