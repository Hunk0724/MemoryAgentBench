# v1 Step-by-Step Commands — tmux 操作指引(暫時檔)

> **本檔目的**: 提供你在 tmux 內逐步 copy-paste 的指令。每個 step 包含:目的 / pre-flight / tmux 指令 / 預期觀察 / 完了做什麼。
>
> **配讀**: [`v1_experiment_plan.md`](v1_experiment_plan.md) 看完整背景跟資源預估
>
> **狀態**: ⚠️ 暫時檔, v1 跑完整理結果後可刪。Auto-archive 到 `analysis/experiments/2026-05-{date}_v1_phase_results/`

---

## §0 共用設定 (每個新 tmux session 進來都要)

```bash
cd /home/yhchiang/MemoryAgentBench
export HF_HOME=/home/yhchiang/MemoryAgentBench/.cache/huggingface
export GOOGLE_GENAI_USE_VERTEXAI=True
export GOOGLE_CLOUD_PROJECT=fc-mh-494213
export GOOGLE_CLOUD_LOCATION=global

# Verify Gemini auth
gcloud config get-value project 2>&1 | head -1
# 應該回 fc-mh-494213
```

如果 gcloud auth 沒設好,先跑 `gcloud auth application-default login`。

---

## §1 Pre-flight — git tag + backup baseline cache (跑一次,後續所有實驗共用)

### 1.1 tag 當前 vanilla state(隨時可 checkout 回對照)

```bash
git tag vanilla-baseline-2026-05-11 HEAD
git tag -l vanilla-baseline-2026-05-11  # 確認 tag 存在
```

### 1.2 備份既有 HippoRAG cache + result 檔案

```bash
BACKUP=/home/yhchiang/MemoryAgentBench/.baseline_backup_2026-05-11
mkdir -p "$BACKUP"

# HippoRAG indexing cache (graph.graphml + fact_embeddings + OpenIE results)
mv outputs/rag_retrieved/NV-Embed-v2/factconsolidation_mh_6k "$BACKUP/NV-Embed-v2_mh_6k"
mv outputs/rag_retrieved/NV-Embed-v2/factconsolidation_sh_6k "$BACKUP/NV-Embed-v2_sh_6k"

# Structure_rag retrieval cache (per-query retrieval logs)
mv outputs/rag_retrieved/Structure_rag_hippo_rag_v2_nv/k_10/factconsolidation_mh_6k "$BACKUP/Structure_mh_6k"
mv outputs/rag_retrieved/Structure_rag_hippo_rag_v2_nv/k_10/factconsolidation_sh_6k "$BACKUP/Structure_sh_6k"

# EM result JSONs (move out to force re-run all 100 queries)
mkdir -p "$BACKUP/results"
mv outputs/gemini-3.1-flash-lite-preview-hippo_rag_v2_nv/Conflict_Resolution/factconsolidation_mh_6k_*_results.json "$BACKUP/results/"
mv outputs/gemini-3.1-flash-lite-preview-hippo_rag_v2_nv/Conflict_Resolution/factconsolidation_sh_6k_*_results.json "$BACKUP/results/"

# Verify
ls -la "$BACKUP/"
ls "$BACKUP/results/" | wc -l    # 應該有 2-4 個 result files
```

### 1.3 確認 cache 確實移走

```bash
ls outputs/rag_retrieved/NV-Embed-v2/ 2>&1 | grep "factconsolidation_.h_6k"
# 不應該有任何 6k 出現,如果還在表示沒搬走
```

---

## §2 Step A4-default — bs=16 benchmark default cold rebuild

### 目的
量 unmodified HippoRAG-v2 + NV-Embed-v2 + default bs=16 + 12 個 6k chunks 的真實 indexing peak。

### 預期觀察
- GPU peak: **25-32 GB**(超出 20 GB 目標, 但 GB10 unified 119 GB 撐得起)
- Wall time: 15-25 min
- Phases: `indexing/openie` → `indexing/embed_kg` → `indexing/synonymy` → `query` (200 queries: 100 SH + 100 MH)
- API cost: ~$0.5

### 開 tmux + 跑

```bash
tmux new -s a4_default

# 進 tmux 後:
cd /home/yhchiang/MemoryAgentBench
export HF_HOME=/home/yhchiang/MemoryAgentBench/.cache/huggingface
export GOOGLE_GENAI_USE_VERTEXAI=True
export GOOGLE_CLOUD_PROJECT=fc-mh-494213
export HIPPORAG_EMBED_BATCH_SIZE=16   # 顯式 set 即使是 default(讓 manifest 記到)

bash scripts/run_with_monitoring.sh A4_default_bs16 "bash run_hipporag_gemini.sh"
```

**Detach** (留著背景跑): `Ctrl+B` 然後 `D`
**Reattach** 觀察進度: `tmux attach -t a4_default`
**列所有 sessions**: `tmux ls`

### 監看 GPU 在 host 上(另開 terminal,不在 tmux 內)

```bash
watch -n 2 'nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total --format=csv'
```

GB10 的 `memory.used` 可能顯示 N/A(unified memory),改看 per-process:

```bash
watch -n 2 'nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv'
```

### 跑完看結果

```bash
LOG=$(ls -td monitoring_logs/*_A4_default_bs16 | head -1)
echo "Log dir: $LOG"
cat "$LOG/hw_phase_summary.md"
```

### Equivalence check vs backup

```bash
# 比 EM(應該完全相同)
diff <(jq '[.data[] | {qid: .query_id, em: .exact_match}]' \
        outputs/gemini-3.1-flash-lite-preview-hippo_rag_v2_nv/Conflict_Resolution/factconsolidation_mh_6k_*_results.json) \
     <(jq '[.data[] | {qid: .query_id, em: .exact_match}]' \
        .baseline_backup_2026-05-11/results/factconsolidation_mh_6k_*_results.json)
# 應該無輸出(完全相同)

# 比 OpenIE 結果(temp=0 + Gemini API → 應 bit-identical)
diff outputs/rag_retrieved/NV-Embed-v2/factconsolidation_mh_6k/chunksize_512/context_id_0/openie_results_ner_gemini-3.1-flash-lite-preview.json \
     .baseline_backup_2026-05-11/NV-Embed-v2_mh_6k/chunksize_512/context_id_0/openie_results_ner_gemini-3.1-flash-lite-preview.json
# 應該無輸出(API 回應穩定情況下)
```

如果 EM 不一致 → equivalence failed,要 debug 前不要進 §3。
如果 EM 完全一致 → ✅ 進 §3。

---

## §3 Step C — chunks vs raw_chunks delta(順便量 bs=8 GPU peak)

### 目的(雙重)
1. 量化 `agent.py` L909 `raw_chunks` 改動對 vanilla EM 的影響(MIGRATION.md §12.2 灰色地帶)
2. 順便測 `HIPPORAG_EMBED_BATCH_SIZE=8` 的 GPU peak

### 預期觀察
- GPU peak: **20-25 GB**
- Wall time: 30-45 min(含 reindex 一次)
- chunks vs raw_chunks EM delta:
  - < 2pp → 保留 raw_chunks, paper 加 footnote
  - ≥ 2pp → 重新討論 motivation 數字
- API cost: ~$0.5

### 3.1 暫時 revert raw_chunks

```bash
# 確認當前 agent.py L909
grep -n "docs = self.raw_chunks\|docs = self.chunks" agent.py
# 應該看到 docs = self.raw_chunks

# 暫存當前 agent.py (revert 完還要改回來)
cp agent.py /tmp/agent.py.backup_raw_chunks

# revert L909
sed -i 's/docs = self\.raw_chunks/docs = self.chunks/' agent.py
grep "docs = self\." agent.py | grep -v "raw_chunks"
# 應該看到 docs = self.chunks
```

### 3.2 清掉 6k MH 的 KG cache(會因 chunk content 改變而 hash 不同)

```bash
rm -rf outputs/rag_retrieved/NV-Embed-v2/factconsolidation_mh_6k
rm outputs/gemini-3.1-flash-lite-preview-hippo_rag_v2_nv/Conflict_Resolution/factconsolidation_mh_6k_*_results.json 2>/dev/null || true
```

### 3.3 跑 chunks 版本 + bs=8 監測

```bash
tmux new -s c_chunks_bs8

# 進 tmux 後:
cd /home/yhchiang/MemoryAgentBench
export HF_HOME=/home/yhchiang/MemoryAgentBench/.cache/huggingface
export GOOGLE_GENAI_USE_VERTEXAI=True
export GOOGLE_CLOUD_PROJECT=fc-mh-494213
export HIPPORAG_EMBED_BATCH_SIZE=8

# 注意: 這次只跑 MH(SH 不需要,因為只是測 chunks vs raw_chunks delta on MH)
bash scripts/run_with_monitoring.sh C_chunks_delta_bs8 \
    "conda run -n hipporag_env --no-capture-output python main.py \
        --agent_config configs/agent_conf/RAG_Agents/gemini-3.1-flash-lite-preview/Structure_rag_gemini-3.1-flash-lite-hippo_rag_v2_nv.yaml \
        --dataset_config configs/data_conf/Conflict_Resolution/Factconsolidation_mh_6k.yaml \
        --chunk_size_ablation 512"
```

Detach: `Ctrl+B D`

### 3.4 跑完比 EM,看 chunks 版的 vanilla MH

```bash
LOG=$(ls -td monitoring_logs/*_C_chunks_delta_bs8 | head -1)
cat "$LOG/hw_phase_summary.md"

# 算這次 EM
NEW_RESULT=$(ls outputs/gemini-3.1-flash-lite-preview-hippo_rag_v2_nv/Conflict_Resolution/factconsolidation_mh_6k_*_results.json | head -1)
jq '[.data[] | .exact_match] | add as $em | length as $n | "EM: \($em)/\($n) = \(($em*100/$n) | floor)%"' "$NEW_RESULT"
# 對照 raw_chunks vanilla 22%
```

### 3.5 ⚠️ 必做: revert chunks 改動

```bash
# 把 agent.py 還原為 raw_chunks 版本
cp /tmp/agent.py.backup_raw_chunks agent.py
grep "docs = self\.raw_chunks" agent.py
# 應該看到 docs = self.raw_chunks
git diff agent.py
# 應該沒 diff
```

### 3.6 把 chunks 版的 result mv 到 backup,還原 raw_chunks 版

```bash
# 把 chunks 版 result 收進 backup
mkdir -p .baseline_backup_2026-05-11/results_chunks_version
mv outputs/gemini-3.1-flash-lite-preview-hippo_rag_v2_nv/Conflict_Resolution/factconsolidation_mh_6k_*_results.json \
   .baseline_backup_2026-05-11/results_chunks_version/
mv outputs/rag_retrieved/NV-Embed-v2/factconsolidation_mh_6k \
   .baseline_backup_2026-05-11/NV-Embed-v2_mh_6k_chunks_version

# 把 raw_chunks 版的 backup 拿回來(從 1.2 備份的)
cp -r .baseline_backup_2026-05-11/NV-Embed-v2_mh_6k outputs/rag_retrieved/NV-Embed-v2/factconsolidation_mh_6k
cp .baseline_backup_2026-05-11/results/factconsolidation_mh_6k_*_results.json \
   outputs/gemini-3.1-flash-lite-preview-hippo_rag_v2_nv/Conflict_Resolution/
```

---

## §4 Step B — C5 驗證(PPR mass separability)

### 目的
驗證 chat §B.7.2.bis 的 C5 假設:PPR mass 能否區分 chain_new 相關 entity vs unrelated old entity? 影響 Phase 2 規則設計。

### 預期觀察
- GPU: <1 GB(用 cached retrieval, 只算 cosine 跟 ranking)
- Wall time: 30-40 min
- API cost: $0
- 輸出 AUC / 區分度 metric → 判斷 Phase 2 規則是否需 v1 階段就改

### 4.1 寫 C5 驗證 script

```bash
# 這步還沒寫,等 §2 §3 確認 baseline 沒問題後再來
# 預計檔案: analysis/c5_verify_ppr_mass_separability.py
# 邏輯:
#   1. Load FC-MH GT (mh_512_mquake_analysis.json) 取每題 chain_new/chain_old entities
#   2. 對每 query 跑 vanilla HippoRAG (用 cached KG) 拿 PPR mass distribution
#   3. 比 chain_new entity mass vs unrelated old entity (e.g. random sample) mass
#   4. 算 AUC-ROC of「entity is chain_new-related」given mass
#   5. 若 AUC > 0.75 → 區分能力夠, Phase 2 規則可用; 若 < 0.6 → 規則需改
```

### 4.2 跑 C5 (TODO, 等 script 寫好)

```bash
tmux new -s c5_verify

# 等 script 寫好後填指令
```

---

## §5 Step D2 — Phase 1 implementation + first reindex(bs=4)

### 目的
1. 把 Phase 1 (`_phase1_scan_supersession` + `superseded_facts` dict + `chunk_to_fact_keys` map + `enable_supersession` flag) 加進 [`methods/hipporag/HippoRAG.py`](methods/hipporag/HippoRAG.py)
2. 跑一次驗證 A1.1 (EM 不變) + A1.2 (detection recall ≥ 41%)
3. 順便量 `HIPPORAG_EMBED_BATCH_SIZE=4` 的 GPU peak

### 5.1 實作 Phase 1(在 tmux 之外做,純 IDE 編輯)

按 [`method_v1_spec.md §3 Phase 1`](current_focus/method_v1_spec.md) 改:
- `HippoRAG.__init__` 加 `self.superseded_facts = {}` 跟 `self.chunk_to_fact_keys = {}`
- `BaseConfig` 加 `enable_supersession: bool = False` field
- `index()` 把 `chunk_ids` / `chunk_triples` 存到 self 上
- `augment_graph` 加 `if enable_supersession: self._phase1_scan_supersession(...)`
- 新增 `_phase1_scan_supersession` method
- 持久化 `superseded_facts` 跟 `chunk_to_fact_keys` 到 `outputs/rag_retrieved/.../supersession_index.json`

實作完做 syntax check + 不開 flag 跑一次確認 vanilla 不變(回到 §2 的 EM 22%)。

### 5.2 開 flag 跑 Phase 1

```bash
# 清掉 MH 6k cache(因為要重 index 才會跑 Phase 1)
rm -rf outputs/rag_retrieved/NV-Embed-v2/factconsolidation_mh_6k
rm outputs/gemini-3.1-flash-lite-preview-hippo_rag_v2_nv/Conflict_Resolution/factconsolidation_mh_6k_*_results.json 2>/dev/null || true
```

```bash
tmux new -s d2_phase1_bs4

# 進 tmux 後:
cd /home/yhchiang/MemoryAgentBench
export HF_HOME=/home/yhchiang/MemoryAgentBench/.cache/huggingface
export GOOGLE_GENAI_USE_VERTEXAI=True
export GOOGLE_CLOUD_PROJECT=fc-mh-494213
export HIPPORAG_EMBED_BATCH_SIZE=4
# 在 yaml config 加 enable_supersession: true,或暫時改 BaseConfig default
# (具體做法視實作而定)

bash scripts/run_with_monitoring.sh D2_phase1_bs4 \
    "conda run -n hipporag_env --no-capture-output python main.py \
        --agent_config configs/agent_conf/RAG_Agents/gemini-3.1-flash-lite-preview/Structure_rag_gemini-3.1-flash-lite-hippo_rag_v2_nv.yaml \
        --dataset_config configs/data_conf/Conflict_Resolution/Factconsolidation_mh_6k.yaml \
        --chunk_size_ablation 512"
```

### 5.3 驗證 A1.1 + A1.2

```bash
# A1.1: EM 應該還是 22%
NEW_RESULT=$(ls outputs/gemini-3.1-flash-lite-preview-hippo_rag_v2_nv/Conflict_Resolution/factconsolidation_mh_6k_*_results.json | head -1)
jq '[.data[] | .exact_match] | add as $em | length as $n | "EM: \($em)/\($n) = \(($em*100/$n) | floor)%"' "$NEW_RESULT"
# 應該是 22 ±1

# A1.2: detection recall - 寫個小 script 比 supersession_index.json 跟 GT
python analysis/verify_phase1_detection.py \
    --supersession outputs/rag_retrieved/NV-Embed-v2/factconsolidation_mh_6k/.../supersession_index.json \
    --gt analysis/results/mh_512_mquake_analysis.json
# 應該 detection recall ≥ 41%
```

---

## §6 GPU peak 對照表(各 step 跑完累積填)

跑完每個 step 後填這表(從 hw_phase_summary.md 抓 GPU peak 跟 wall time):

| Run | bs | GPU peak (GB) | Indexing time | API cost | EM (MH) |
|---|---|---|---|---|---|
| A4_default_bs16 | 16 | (填) | (填) | (填) | 22% |
| C_chunks_delta_bs8 | 8 | (填) | (填) | (填) | (填) |
| D2_phase1_bs4 | 4 | (填) | (填) | (填) | 22% |
| (可選) bs=1 in later reindex | 1 | (填) | (填) | (填) | 22% |

對應 [`docs/hardware_request_6k.md`](hardware_request_6k.md) 的 profile prediction 對比驗證。

---

## §7 Cleanup / 還原(實驗結束想還原狀態)

```bash
# 還原 baseline 6k cache (raw_chunks 版)
cp -r .baseline_backup_2026-05-11/NV-Embed-v2_mh_6k outputs/rag_retrieved/NV-Embed-v2/factconsolidation_mh_6k 2>/dev/null
cp -r .baseline_backup_2026-05-11/NV-Embed-v2_sh_6k outputs/rag_retrieved/NV-Embed-v2/factconsolidation_sh_6k 2>/dev/null

# 還原 result JSON
cp .baseline_backup_2026-05-11/results/*.json \
   outputs/gemini-3.1-flash-lite-preview-hippo_rag_v2_nv/Conflict_Resolution/ 2>/dev/null

# 退到 vanilla baseline tag
# git checkout vanilla-baseline-2026-05-11  # 只在需要時用

# 確認 batch_size env 沒殘留
unset HIPPORAG_EMBED_BATCH_SIZE
```

---

## §8 tmux 操作快查

| 動作 | 指令 |
|---|---|
| 建新 session | `tmux new -s <name>` |
| Detach (留背景) | `Ctrl+B` 然後 `D` |
| Reattach | `tmux attach -t <name>` |
| 列所有 sessions | `tmux ls` |
| Kill session | `tmux kill-session -t <name>` |
| 重命名 session | `tmux rename-session -t <old> <new>` |
| 在 session 內水平分割視窗 | `Ctrl+B` 然後 `"` |
| 切換視窗 | `Ctrl+B` 然後方向鍵 |

---

## §9 跑出問題時的 debug 路徑

| 症狀 | 可能原因 | 動作 |
|---|---|---|
| `HF_HOME` PermissionError | `~/.cache/huggingface` 被 root 佔 | 確認 `export HF_HOME=/home/yhchiang/MemoryAgentBench/.cache/huggingface` |
| `gcloud auth` 失敗 | ADC 沒設 | `gcloud auth application-default login` |
| `nvidia-smi` 顯示 memory N/A | GB10 unified memory 預期行為 | 改用 `--query-compute-apps=pid,used_memory` |
| sidecar log 空 / sample 0 | psutil 不在 base python | 確認 `SIDECAR_PYTHON` 指向 MABench env(預設已設) |
| Resume 重跑時跳過所有題目 | 之前 result 還在 | mv 走 result JSON 強制重跑 |
| OpenIE 結果跟 backup 不一致 | Gemini API 偶爾抖動 | 如果只是 wording 變但 triple 結構同則 OK; 若 triple 結構變則異常 |

---

## §10 動工前 self-check

執行 §2 (A4-default) 前一一勾選:

- [ ] §0 環境變數設好(HF_HOME / GOOGLE_GENAI_USE_VERTEXAI / GOOGLE_CLOUD_PROJECT)
- [ ] §0 gcloud ADC 設好 (`gcloud config get-value project` 回 `fc-mh-494213`)
- [ ] §1.1 git tag 打了
- [ ] §1.2 baseline backup mv 完
- [ ] §1.3 確認 cache 目錄已搬走(`outputs/rag_retrieved/NV-Embed-v2/` 下沒 6k)
- [ ] `git status` 顯示 modified: config_utils.py / gemini_llm.py / NVEmbedV2.py(註解);untracked: docs/, scripts/, monitoring_logs/(空)
- [ ] tmux 已安裝 (`which tmux`)
- [ ] MABench env 已存在 (`conda env list | grep MABench`)
- [ ] hipporag_env 已存在 (`conda env list | grep hipporag_env`)

全勾才動 §2。
