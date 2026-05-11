# Migration Guide — Restoring this repo on a new machine

> 從 GX10-2 遷移到任何相容硬體的完整步驟。
> Last updated: 2026-05-11
> Maintainer: Hunk0724
>
> **2026-05-11 update**: 加 §11 v1 method 實作計畫(下次 GB10 開機要做的事)+ §12 baseline integrity 報告(vs upstream MemoryAgentBench diff 結論)

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

## §11 v1 Method 實作計畫 (2026-05-11 加, 下次 GB10 開機後執行)

### 11.1 上下文 (給 GB10 的 Claude Code 看)

我們在 mac 端跟 Claude(chat + code 兩條 session)做了完整的方法設計, 階段如下:

1. ✅ Motivation 完整定稿 — [`analysis/paper_motivation/motivation_narrative.md`](analysis/paper_motivation/motivation_narrative.md)(2 claim, 量化 evidence, FC-MH 失敗根因拆解到 KU+MH 交集的 emergent gap 25.8pp)
2. ✅ 方法設計討論定稿 — [`claude_chat_method_design_experiment.md`](claude_chat_method_design_experiment.md):
   - §B.1-B.4: 與 chat 的高層討論(3 phase 架構, decision rationale)
   - §B.7: 程式碼端讀 HippoRAG.py 後的補充(KG 真實組成, fact_key, relation collapse, hop 2+ satellite 非對稱, PPR temporal blindness)
3. ✅ v1 spec 鎖死 — [`analysis/paper_motivation/method_v1_spec.md`](analysis/paper_motivation/method_v1_spec.md):
   - §2 設計決策 Q1-Q4 全部 locked
   - §3 HippoRAG.py 切入點 + pseudo-code
   - §5 Falsifiable assertions(每 phase 必跑的驗證)
   - §6 實驗執行順序

### 11.2 V0 已棄用

之前的 V0 prototype([`analysis/phase1_v0_auto_supersession.py`](analysis/phase1_v0_auto_supersession.py))**已棄用**:
- 它的 fact-line excision 依靠 FC corpus 的 numbered fact list 結構紅利, 不可 generalize
- 44% EM 不算 v1 baseline, 僅當 diagnostic 不寫進 paper
- 棄用理由詳見 method_v1_spec.md §0

### 11.3 GB10 上應該做的事(優先序)

按 method_v1_spec.md §6 執行:

```bash
# Step 0 — Sanity baseline (~半天)
git tag vanilla-baseline-2026-05-11 HEAD  # 鎖定當前 vanilla state 方便對照
bash run_hipporag_gemini.sh                # 驗證 FC-MH=22%, FC-SH=77%

# Step 0.5 — chunks vs raw_chunks delta sanity check (~30-60 min)
# 詳見 method_v1_spec.md §6 Step 0.5
# 暫時 revert agent.py L909 docs=self.chunks, 跑 vanilla, 量 delta vs 22%

# Step 1 — Phase 1 only (~1 天)
# 實作 _phase1_scan_supersession + superseded_facts/chunk_to_fact_keys dicts
# 加 enable_supersession flag (default False)
# 驗證 A1.1 (EM=22% ± 1pp), A1.2 (detection recall ≥ 41%)

# Step 2 — Phase 1 + Phase 2 (~1 天)
# 修 run_ppr return signature 多回 full_pagerank_scores
# 實作 _phase2_filter_chain_old
# 加 enable_phase2_filter flag
# 驗證 A2.1 (EM ∈ [35%, 50%]), A2.2 (precision ≥ 85%), A2.3 (FC-SH 退步 < 3pp)

# Step 3 — Phase 3 (~半天)
# 在 rag_qa system prompt 加 universal scaffold + enable_phase3_scaffold flag
# 跑 4-way ablation: vanilla / P1+P2 / P3 only / P1+P2+P3 全套
# 驗證 A3.1, A4.1

# Step 4 — Generalization check (~半天)
# 跑 MuSiQue / 2Wiki 驗證 A3.2 (scaffold 不傷非 KU multi-hop)

# Step 5 — 量化 hop 2+ satellite (~半天)
# 對 FC-MH 答錯題目人工/LLM annotate Type-1/2/3 比例, 決定 v2 方向
```

### 11.3.1 v1 整體硬體資源預估 (FC-MH 6k Gemini Vertex)

| 階段 | GPU peak | GPU 占用時間 | CPU | RAM | 100 queries 耗時 | API call |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| vanilla (已 cache) | <1 GB | <1 sec/query | 4-8 core | <8 GB | ~5-10 min | rerank+QA each 100 |
| vanilla (fresh reindex) | **14.6 GB** | 30-60 sec | 同上 | 16-32 GB | ~15 min | + OpenIE 12 calls |
| Phase 1 only | 14.6 GB | 30-60 sec(reindex) | 同上 | 同上 | ~15 min | 同 vanilla |
| Phase 1+2 (不 reindex) | <1 GB | <1 sec/query | 同上 | <8 GB | ~10 min | 同 vanilla |
| Phase 1+2+3 | <1 GB | <1 sec/query | 同上 | <8 GB | ~10 min | 同 vanilla |

**Step 0-5 整體時間(在 GB10 上)**:
| Step | 計算時間 | 含 impl/debug |
|---|---|---|
| 0 baseline + 0.5 chunks delta | 30-60 min | 半天 |
| 1 Phase 1 | 30 min | 1 天 |
| 2 Phase 2 + calibration | 1-2 hr | 1 天 |
| 3 全套 ablation | 40 min | 半天 |
| 4 MuSiQue/2Wiki | 1-2 hr | 半天 |
| 5 annotate satellite | 1-2 hr(LLM judge) | 半天 |
| **小計** | **~4-6 hr 純計算** | **~3-4 天 wall-clock** |

**API cost 估算**: 全 v1 矩陣總計 ~5-10M input + ~2-3M output tokens, Gemini 3.1 Flash-Lite Preview 約 **$5-15 美元**

**Bottleneck**: 不在 GPU/CPU, 在 (a) Gemini API rate limit (Vertex 通常很寬), (b) debug 時間, (c) 等實驗結果的決策時間。GB10 GPU 用不到一半時間,可放心同時做別的事。

### 11.3.2 監測指令

```bash
# GPU 即時占用
watch -n 1 nvidia-smi

# 看 disk(KG cache 約 200 MB-2 GB / config)
du -sh outputs/rag_retrieved/

# 看 OpenIE cache 命中
ls -la outputs/rag_retrieved/NV-Embed-v2/factconsolidation_mh_6k/chunksize_512/context_id_0/openie_results_*.json
```

### 11.4 重要設計約束

- **Feature flag preservation**: 所有 v1 改動必須包在 `enable_supersession` / `enable_phase2_filter` / `enable_phase3_scaffold` 三個 flag 後, default 全 False。這樣 vanilla baseline 永遠可跑(不需要切 branch)
- **Phase 1 metadata 在 fact_key 層**, 不在 graph edge 層(因 relation collapse, 詳見 chat §B.7.1)
- **Phase 2 high-mass 用 PPR 收斂後 phrase node mass top-20%**(不能用 `top_k_facts` 的 entities, 會永遠 trigger)
- **Phase 2 hard filter 對齊 OracleClean-ThisChain ceiling 設計**, 若觀察到問題再迭代到 demote
- **量化 Type-2/3 satellite leakage 是 v2 起點**, 對應 chat §B.7.2

### 11.5 結果存哪

- Phase 1 supersession index: `outputs/rag_retrieved/.../supersession_index.json`(新增, 跟既有 graph cache 並列)
- Phase 1/2/3 EM 結果: `outputs/gemini-3.1-flash-lite-preview-hippo_rag_v2_nv/Conflict_Resolution/factconsolidation_mh_6k_*_results.json`(沿用既有命名)
- Ablation logs: `analysis/results/phase_v1/{vanilla,p1_only,p3_only,p1p2,p1p2p3}_mh_results.json`(新建 directory)
- 觀察記錄: `analysis/experiments/2026-05-{actual_date}_v1_phase_results/`(timestamp directory)

---

## §12 Baseline Integrity Report (vs upstream MemoryAgentBench, 2026-05-11)

**目的**: 確認 private fork 對 vanilla baseline 行為的影響, 避免實驗依賴 untrusted patched baseline。

### 12.1 對 upstream commit 569241d 的 diff 分類

| 檔案 | 改動性質 | 影響 vanilla? |
|---|---|---|
| `methods/hipporag/HippoRAG.py` | `VLLMOfflineOpenIE` 改 lazy import(2 行) | ❌ vanilla 走 online OpenIE 不 trigger |
| `methods/hipporag/embedding_model/__init__.py` | `GritLM` 改 lazy import(2 行) | ❌ vanilla 用 NV-Embed-v2 不 trigger |
| `methods/hipporag/llm/__init__.py` | 加 Gemini fork point(4 行) | ❌ OpenAI baseline 路徑不變 |
| `methods/hipporag/llm/gemini_llm.py` | 新增 128 行 Gemini support | ❌ 新增模組, 不修既有 |
| `methods/hipporag/prompts/prompt_template_manager.py` | import path fallback 修正 | ❌ 純機制修復 |
| `agent.py` Gemini section | Vertex AI + retry + `thinking_budget=0` | ❌ 只影響 Gemini 路徑 |
| `agent.py` mem0/Zep | logging 加性 + idempotent + 360s Zep wait + retry | ⚠️ Zep wait 是 cloud API 必要 |
| `agent.py` L909 `docs = self.raw_chunks` | HippoRAG indexing input 換 raw content | ⚠️ **唯一 baseline 行為灰色地帶, 見 §12.2** |
| `configs/data/Factconsolidation_*_6k.yaml` | `max_test_samples: 1 → null` | ⚠️ 修 upstream debug 殘留(必要) |
| `configs/data/Factconsolidation_*_512.yaml` | 全新增 | ❌ 純加性 |
| `configs/data/Factconsolidation_*_baseline_b.yaml` | 全新增 | ❌ 純加性 |
| `configs/agent_conf/.../gemini*.yaml` | 全新增 | ❌ 純加性 |

### 12.2 唯一灰色地帶 — `raw_chunks` for HippoRAG indexing

**Commit**: `a4845b4` "Fix: use raw_chunks for HippoRAG indexing to stabilize hash_ids"

**改動**:
- Before: `docs = self.chunks`(含 memorize template wrapper + `{time_stamp}`)
- After: `docs = self.raw_chunks`(純對話內容, 不含 wrapper)

**wrapper 在 FC 上的真實內容** ([utils/templates.py:78](utils/templates.py#L78)):
```
'Dialogue between User and Assistant {time_stamp} \n
<User> The following context is the facts I have learned: 
{context}
<Assistant> I have learned the facts and I will answer the question you ask.'
```
`{time_stamp}` = `time.strftime("%Y-%m-%d %H:%M:%S")` = run 當下 wall-clock time。

**評估**: **reproducibility correction, 不是任意修改**
- Upstream 行為下 `{time_stamp}` 讓每次 run 的 chunk hash 都不同, KG cache 無法復用(每次重 index ~30 min)
- 餵給 OpenIE 的文字含時間戳雜訊, 抽 triples 結果可能不穩定(wrapper-derived triples 如 `(User, said, ...)` 進 KG)
- 此修改是 baseline cleanup, 不影響 HippoRAG-v2 演算法本身, 只影響 input cleanliness

→ **vanilla HippoRAG-v2 演算法本身** 100% 等同 upstream
→ **vanilla HippoRAG-v2 在 FC 上的 reproducibility** 受惠於此修正

**GB10 上必跑 Step 0.5 量化 delta**: 在動 v1 之前, 暫時 revert raw_chunks 跑一次 vanilla, 比 EM。詳見 [method_v1_spec.md §6 Step 0.5](analysis/paper_motivation/method_v1_spec.md)。

→ 若 delta < 2pp: 保留 raw_chunks, paper §6 disclose
→ 若 delta ≥ 2pp: 重新考慮 motivation 數字是否需要重跑

### 12.3 結論

- ✅ vanilla HippoRAG-v2 baseline 在 OpenAI / Gemini 路徑上行為等同 upstream(差異僅在 lazy import / Vertex fork / reproducibility fixes)
- ✅ Mem0 baseline 需配 `analysis/run_mem0_gemini_aligned.py` 的 L1 prompt 修正(motivation §1 註 2)
- ✅ Zep baseline 行為等同 upstream(僅加 retry/wait, 不改 query/ingestion 邏輯)
- ✅ 不需要切換到 upstream MemoryAgentBench(/Users/yhchiang/MemoryAgentBench/ 可當 reference 但不需 import)

### 12.4 v1 實作期間的 baseline 保護機制

加 v1 method 改動時, 必須遵守:

1. **Git tag 鎖 baseline**: `git tag vanilla-baseline-2026-05-11 HEAD` 在動 HippoRAG.py 之前打 tag, 之後可隨時 checkout 回對照
2. **Feature flag default False**: 所有 v1 改動包在三個 flag 後(method_v1_spec.md §4), 預設行為 = vanilla
3. **不改 vanilla 函式 signature** : 若需修改 `run_ppr` return(method_v1_spec.md §3 Phase 2 要求), 維持 backward-compatible — 新欄位放在 tuple 最後 + optional return
4. **跑 v1 之前先驗 vanilla**: 每次重啟實驗環境, 先跑一次 `run_hipporag_gemini.sh` confirm EM=22%, 再開 v1 flag

---

## 後續維護

如果之後又改了關鍵環境設定 / 硬體,記得回頭更新本檔(尤其 §5 API keys 跟 §7 預期 EM 數字)。
