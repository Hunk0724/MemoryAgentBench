# PROVENANCE — `MemoryAgentBench/` 相對 upstream 的所有改動

**最後更新**: 2026-05-24
**參考 upstream**: `/home/yhchiang/MemoryAgentBench_original/`(乾淨 clone)
**Provenance 原則**:
1. **Vanilla path 不變式**:所有方法 flag 預設 `False` 時,執行路徑應等價於 upstream
2. **明確改動才動 baseline**:唯二刻意改的是(a)backbone = `gemini-3.1-flash-lite-preview`、(b)chunk_size = 512
3. **每個改動分類**:✅ 故意 / 🟡 benign(行為應等價) / ⚠️ 待驗(可能影響 baseline)
4. **可逆**:所有 backup 在 `.baseline_backup_*` 目錄中

---

## §1. 配置層

| 檔案 | 變更 | 分類 | 影響 |
|---|---|---|---|
| `configs/data_conf/Conflict_Resolution/Factconsolidation_mh_6k.yaml` | `max_test_samples: 1 → null` | ✅ 故意 | 跑 100 題完整 evaluation,非 1-題 sanity |
| `configs/data_conf/Conflict_Resolution/Factconsolidation_sh_6k.yaml` | 同上 | ✅ 故意 | 同 |
| `configs/agent_conf/RAG_Agents/gemini-3.1-flash-lite-preview/Structure_rag_gemini-3.1-flash-lite-hippo_rag_v2_nv.yaml` | 新檔 | ✅ 故意 | backbone 切 Gemini |
| `configs/agent_conf/Long_Context_Agents/Long_context_agent_gemini-{2.5-flash,2.5-flash-lite,3.1-flash-lite}.yaml` | 新檔 | ✅ 故意 | backbone 切 Gemini |
| `configs/data_conf/Conflict_Resolution/Factconsolidation_{mh,sh}_512.yaml` | 新檔 | ⚠️ 待查 | chunk=512 變體 — 用於哪個實驗待標 |
| `configs/data_conf/Conflict_Resolution/Factconsolidation_{mh,sh}_6k_baseline_b.yaml` | 新檔 | ⚠️ 待查 | "baseline_b" 變體 — 用途待標 |

---

## §2. 演算法層 — Phase 1/2/3 conflict mechanism(我們的核心加法)

### 2.1 HippoRAG.py

| 項目 | 數字 | 分類 |
|---|---|---|
| 行數 | 1242(upstream)→ **2144**(我們),+902 行 | ✅ 故意 |
| 新增 private methods | 10 個:`_add_proposition_hyperedges_to_stats`(DEPRECATED 2026-05-24)、`_build_chunk_to_fact_keys`、`_ensure_v2_detector`、`_ensure_v2_phase2_loaded`、`_load_supersession_index`、`_phase1_scan_supersession`、`_phase2_filter_chain_old`、`_save_supersession_index`、`_v2_llm_judge_apply`、`_v2_phase2_pipeline` | ✅ 故意 |
| **不變式(待驗證)** | 所有 Phase flag 為 False 時,`index()`/`rag_qa()` 路徑等價於 upstream | ⚠️ 需要 V2 驗證腳本實證 |
| **2026-05-24 變更** | hyperedge call site 從 `enable_phase2_chain_detection` 解耦 → 改用新 flag `enable_proposition_hyperedge`(default False)。函數本體保留 + DEPRECATED 註解。資料定案在 FC atomic-prop regime 下加 0 邊。詳見 `docs/B_remove_hyperedge_design.md`。 | ✅ 故意 |

### 2.2 新檔(全部都是 Phase 機制)

| 路徑 | 用途 | 分類 |
|---|---|---|
| `methods/hipporag/phase1/` | Phase 1 supersession scan | ✅ 故意 |
| `methods/hipporag/phase2a/` | Phase 2.a chain enumeration | ✅ 故意 |
| `methods/hipporag/phase2b/` | Phase 2.b verdict prompt + parser | ✅ 故意 |
| `methods/hipporag/phase3/` | Phase 3 enriched context renderer | ✅ 故意 |
| `methods/hipporag/v2_llm_judge.py` | v2 LLM judge | ✅ 故意 |
| `methods/hipporag/llm/gemini_llm.py` | Gemini LLM adapter | ✅ 故意(backbone 必要) |

### 2.3 config_utils.py — 新增的 feature flags

| Flag | Default | 含義 |
|---|---|---|
| `enable_supersession` | False | Phase 1 |
| `enable_phase2_filter` | False | Phase 2 filter |
| `enable_phase2_filter_passages` | False | Phase 2 passage drop |
| `enable_phase3_scaffold` | False | Phase 3 scaffold |
| `enable_phase3_v2_enriched` | False | Phase 3 enriched context |
| `enable_phase3_v2_reasoning_hints` | False | Phase 3 hints |
| `enable_phase3_v2_recent_updates` | False | Phase 3 updates |
| `v2_phase2_ppr_aggregation` | False | PPR-based aggregation |

→ **所有 flag 預設 False = upstream vanilla 行為**(理論上)

---

## §3. 行為改動(可能影響 baseline,需小心)

### 3.1 `agent.py`(1136 → 1244 行, +108 行)

| 變更 | 行 | 分類 | 影響 |
|---|---|---|---|
| Vertex AI Gemini client(`GOOGLE_GENAI_USE_VERTEXAI`) | L133-140 | ✅ 故意 | backbone 切換必要 |
| Azure OpenAI fallback(env-driven) | L254-259 | 🟡 benign | 環境變數沒設時 fallback openai,等價 upstream |
| `OpenAI(max_retries=20)`(原 0) | L108 | 🟡 benign | retry 不影響正確答案,只影響穩定性 |
| Gemini query retry-with-backoff(429/503) | L380-427 | 🟡 benign | 同上 |
| **`self.raw_chunks = []`** + 後續 `raw_chunks.append(message)`、`docs = self.raw_chunks` | L266, L803, L809, L912 | **⚠️ 真行為改動** | **原版傳 wrapped(memorize template)內容給 HippoRAG,hash_id 每次不同;我們改傳 raw 內容,hash_id 穩定**。對 baseline 表現的影響:**理論上應改善 caching / 跨 run 一致性,不應改 final EM**,但需要在 V2 驗證腳本實證 |
| `self.chunk_size = agent_config['agent_chunk_size']` | L227-229 | 🟡 benign | 讀 config 中的 chunk size(原本似乎硬編) |

### 3.2 `conversation_creator.py`

| 變更 | 分類 | 影響 |
|---|---|---|
| `if self.max_test_samples is None: num=len(dataset_items); else: ...` | 🟡 benign | upstream 沒處理 None,我們補上 |

### 3.3 `initialization.py`

| 變更 | 分類 | 影響 |
|---|---|---|
| resume 時保留 `retrieval_context`、`retrieval_scores` | 🟡 benign | 只影響 resume,非 fresh run |
| `agent.send_message(chunk, memorizing=True, context_id=...)` 加 `context_id` 參數 | ⚠️ 待查 | 多 context 場景才會用到,影響待確認 |

### 3.4 `methods/hipporag/embedding_model/NVEmbedV2.py`

| 變更 | 分類 | 影響 |
|---|---|---|
| `torch_dtype` 由環境變數 `HIPPORAG_EMBED_FP16` 控制,**default fp32 = upstream** | 🟡 benign(預設下等價) | 沒設環境變數時 = upstream fp32 |
| inference loop 包 `torch.no_grad()`,修記憶體洩漏(51 GB → <20 GB) | 🟡 benign | **NV-Embed-v2 fp16 forward 是 deterministic**,輸出已驗證 bit-identical |

### 3.5 `methods/hipporag/prompts/prompt_template_manager.py`

| 變更 | 分類 | 影響 |
|---|---|---|
| import path try-fallback 順序對調 | 🟡 benign | 純 import 邏輯改寫,無功能差 |

---

## §4. 待補強的不變式驗證

| 不變式 | 驗證狀態 | 該怎麼驗 |
|---|---|---|
| 所有 Phase flag = False 時,`HippoRAG.index()` 行為等價 upstream | ❌ 未驗 | toy data forward + 比 graph.graphml + chunk dict |
| 所有 Phase flag = False 時,`HippoRAG.rag_qa()` 行為等價 upstream | ❌ 未驗 | 同上,比 top-K retrieval IDs + scores |
| `raw_chunks` 改動不改 final EM | ❌ 未驗 | 1 query 跑兩版(upstream agent.py vs ours) 比 EM |
| `torch.no_grad()` 改動不改 embedding 輸出 | ✅ 已驗(自註解寫 fact_embeddings L2 = 0.0) | — |
| `HIPPORAG_EMBED_FP16` 沒設時 = fp32 = upstream | ✅ 已驗(default 寫死) | — |

→ **下一步:寫 V2 alignment 驗證腳本(`analysis/verify_vanilla_alignment.py`),把上面 3 個 ❌ 變 ✅**。

---

## §5. 雜物 / 非演算法檔案(屬 cleanup 範圍,見 `cleanup_plan.md`)

| 類別 | 範圍 | 處置 |
|---|---|---|
| Backup 目錄 | `.baseline_backup_2026-05-11/`、`_4ablation_pre_*/`、`_g11_pre/`、`_v2_phase2_w13_pre/` | 統一搬 `archive/baseline_backups/` |
| Run 產物 | `outputs/`、`monitoring_logs/`、`logs/`、`.cache/`、`cache/`、`__pycache__/` | gitignore + 過舊歸檔 |
| Run dump | `agents/Structure_rag_zep_*/` | 搬 `archive/runs/` |
| 根目錄雜檔 | `MIGRATION.md`、`Phase0 3day sprint spec.md`、`claude_chat_method_design_experiment.md`、`run_*.sh` | 搬 `docs/archive/` 跟 `scripts/` |
| analysis/ 散落 | `analysis/results/`、`analysis/experiments/`、根層 ~40 個腳本 | 整理見 cleanup_plan |

---

## §6. Replication 指令(對 upstream 跑乾淨 baseline)

```bash
# 切換到 upstream-equivalent vanilla(所有 flag 預設 False)
export HIPPORAG_EMBED_FP16=""        # default fp32
unset HIPPORAG_EMBED_BATCH_SIZE      # default 16
# 不設任何 enable_phase* env var
# Config: configs/data_conf/Conflict_Resolution/Factconsolidation_mh_6k.yaml(max_test_samples=null)
# Agent : configs/agent_conf/RAG_Agents/gemini-3.1-flash-lite-preview/Structure_rag_*hippo_rag_v2_nv.yaml
# 預期:vanilla HippoRAG-v2 on FC-MH 100Q,Gemini-3.1-flash-lite, EM ≈ A=17%
```

---

## §7. 相關 git commits(供 reviewer 追蹤)

```
6d452c5  v2.0.2 W1.1+W1.2 checkpoint: proposition layer + chain enumeration
d8ff38e  v2 LLM-judge wiring + production-scale smoke
916ef0c  v1 G.11 diagnostic checkpoint
6ac92b2  v1 Method: Phase 1+2+3 conflict mechanism (FC-MH 19% → 37%, FC-SH 75% → 89%)
e144fcc  Lock v1 method spec + baseline integrity audit for GB10 handoff
```

(完整 commit 列表:`git log --since=2026-04-01 --oneline`,共 ~20 個 commit)

---

## §8. 相關文件

- `docs/method_v2.0.2_status_brief.md` — 方法現況綜整 v9
- `docs/method_design_v2.0.2_spec.md` — 方法 spec
- `docs/engineering_todos_v2.0.2.md` — 工程 TODO(暫停中)
- `docs/paper_narrative_experiments.md` — 論述實驗矩陣
- `docs/cleanup_plan.md` — 雜物整理計畫(下一份產出)
