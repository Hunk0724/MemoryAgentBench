# Methods Reproduction — Baselines Pin & Config

> **用途**:paper appendix reproducibility 章節的 code snapshot。任何 baseline 對比實驗**必先確認符合本 pin 表**;若換版須寫進 §Change-log。
> **Pin 依據**:當前 `exp/v2-llm-judge` branch(commit ~`0fa2edc` 之後);正式論文數據以此 branch pin 版本重跑一次(**含更新 Zep API key**,見 §5)。

---

## §1 Environment(共通)

| 項目 | 版本 / 值 | 位置 |
| :--- | :--- | :--- |
| Python | 3.10 | `setup/MABench_env.yml` |
| conda env | `MABench` | `conda create -n MABench python=3.10 -y` |
| OpenAI client | 官方 `openai` package | `requirements-core.txt` |
| **Answer LLM(全 baseline 共用)** | `gpt-4o-mini`, temperature 0 | `configs/agent_conf/RAG_Agents/gpt-4o-mini/*.yaml` |
| Embedder(mem0 / ours vector store) | `text-embedding-3-small`(1536-d) | 各 baseline YAML `embedder` 區塊 |
| **Backbone sweep(未來)** | gpt-4.1-mini / gpt-4.1(strong)、gpt-4o-mini(mid)、gemma3 1B/4B/12B/27B(weak, via Ollama) | 見 `evaluation_protocol_main.md §3` |

---

## §2 mem0 baselines((a) vanilla / (b) mem0+P1)

### 2.1 版本 pin

| 項目 | 值 |
| :--- | :--- |
| PyPI package | `mem0ai==1.0.5`(`requirements-core.txt:24`, `setup/MABench_env.yml:185`) |
| **⚠ Runtime shadow** | Repo 內有 patched `./mem0/`,import 時**覆蓋 pip 版本**(從 repo 根執行時)。paper appendix 需明講「mem0 1.0.5 + local patches(見 repo `mem0/`)」 |
| Runner 檔案 | `agent.py::_initialize_mem0_agent` (L224), `_handle_mem0_agent` (L988) |
| Prompt P1 | `methods/mem0_fc_prompt_fix.py::make_unified_extractor_prompt` (L196-238) |
| Vector store | qdrant on-disk,collection 名以 `sub_dataset + agent_name fingerprint` suffix 隔離 |

### 2.2 兩個 variant 的唯一差別

| Variant | Config file | Flag | 語意 |
| :--- | :--- | :--- | :--- |
| **(a) vanilla mem0** | `Structure_rag_gpt-4o-mini-mem0_512_openai_native.yaml` | *(none)* | mem0 官方 `FACT_RETRIEVAL_PROMPT`(自帶抽取 prompt) |
| **(b) mem0+P1** | `Structure_rag_gpt-4o-mini-mem0_512_openai_unified_dest.yaml` | `use_unified_extractor: true` | 改用 P1(memory organizer);保留 mem0 destructive UPDATE |

**兩者都用 destructive UPDATE**;差別只在**抽取 prompt**。 (b) 的 pool state 4 桶不均是 UPDATE 的直接後果。

### 2.3 Retrieve 設定

- `retrieve_num: 100`(top-k)
- 呼叫:`self.memory.search(query=retrieval_query, user_id=user_id, limit=100)` (agent.py:1023)
- **User isolation**:`user_id = f'context_{context_id}_{self.sub_dataset}'`(agent.py:990),per context 不 per qid

### 2.4 mem0 內部 LLM(判 ADD/UPDATE/DELETE)

`mem0_config.llm.provider=openai, model=gpt-4o-mini, temperature=0, max_tokens=16384`(YAML)—— 與 answer LLM 同型,但**client 分開實例**。

---

## §3 Zep baseline(現行:k=10, chunk=512)

### 3.1 版本 pin

| 項目 | 值 |
| :--- | :--- |
| PyPI package | `zep-cloud==3.20.0`(`requirements-core.txt:12`) |
| Service | **Zep Cloud SaaS**(非 graphiti local);client = `Zep(api_key=os.getenv("ZEP_API_KEY"))` |
| Runner | `methods/zep.py` + `agent.py::_initialize_zep_agent` (L618), `_handle_zep_agent` (L1118) |
| Config | `configs/agent_conf/RAG_Agents/gpt-4o-mini/Structure_rag_gpt-4o-mini-zep.yaml` |
| **k(retrieve_num)** | **10**(不對稱於 mem0/ours 的 k=100 → landscape 標「Zep(k=10) caveat」;Zep 官方推薦 k=10) |
| **chunk_size** | **512**(對稱於 mem0/ours,fairness 已 fix;所有 Zep 檔案均為 chunk_512) |

### 3.2 Retrieve 呼叫

三個 parallel `client.graph.search(graph_id, query[:399], scope, limit=10)`:
- `scope='edges'` → `retrieved.edges` = triple-like facts(**PP 分桶時用的 pool = 這個**)
- `scope='nodes'` → entity summaries
- `scope='episodes'` → raw episodes 片段

**Query 400 char cap**(silent truncation,agent.py:1180)。

### 3.3 Prompt template(給 answer LLM)

見 `methods/zep.py::TEMPLATE`(L10):3 段 concat = FACTS(edges) + ENTITIES(nodes) + EPISODES。**這是「多顆粒 memory」的來源** → §5 的 Zep(only-return-fact)diagnostic 要削掉後兩段。

### 3.4 Isolation

per context 三元組(agent.py:1125):
```
user_id   = f'user_{context_id}_{self.sub_dataset}'
graph_id  = f'graph_{context_id}_{self.sub_dataset}'
thread_id = f'thread_{context_id}_{self.sub_dataset}'
```

**⚠ Zep cloud 有狀態**:同一 API key 重複跑會累積至該 project 的 knowledge graph。**兩層保險**:
1. Runtime 端 → per context 三元組隔離,idempotent 建立(swallow `already exists`)
2. Paper 端 → 正式數據前用**新 key** rebuild(見 §5 Change-log)

### 3.5 First-query wait

新 context 第一 query 前 `sleep(360)` 等 Zep async graph 處理(L1166-1169)—— 不是 bug,是 SaaS 的 eventual consistency。

---

## §4 ours(paper 主方法)

### 4.1 版本 pin

| 項目 | 值 |
| :--- | :--- |
| Code branch | `exp/v2-llm-judge` |
| Phase 0(write-time triple)| `methods/phase0_triple_extractor.py`(P1 unified extractor + normalize_subject/predicate) |
| Phase 2(query-time)| `methods/phase2_query.py`(P3 grouping + P5 conflict type + deterministic temporal) |
| Prompt hash 見 | `paper_current/method_v1.md Appendix A`(全 prompt 已 vendored) |
| Vector store | 同 mem0(qdrant + text-embedding-3-small) |
| **Retrieve k** | 100 |

### 4.2 Variant 對照

| Variant | 語意 | 用途 |
| :--- | :--- | :--- |
| **ours (no_p5)** | P3 grouping + 確定性 temporal(關 P5)| **paper main method** |
| ours (full P3+P5) | 上 + P5 conflict type | ablation:P5 是否有用 |
| ours (struct only) | 只 `(S,P)` 結構 grouping + 確定性 temporal(關 P3)| ablation:LLM grouping 必要性 |
| ours (p3_only) | 只 P3 grouping(不用 (S,P) 結構 pre-filter)| ablation:結構 pre-filter 必要性 |

---

## §5 Change-log(pending / 已發現需 replace 的 baseline)

### 5.1 Zep untracked size256 檔案 commit(建議 commit,不改實驗結果)

- **狀態**:6k / 32k / 64k 三個 chunk_512 size256 result JSON 為 untracked
  - `outputs/gpt-4o-mini-zep/Conflict_Resolution/factconsolidation_sh_{6k,32k,64k}_unknown_...size256_...k10_chunk512_results.json`
- **與 tracked 差異**:tracked 是舊 `FULL100_chunk512`;untracked size256 是**新 run(same chunk_512,新 API key run 或補跑)**。以 6k 為例,untracked has_pair EM=46/74,tracked FULL100 has_pair EM=44/74。**pool_acc_crosstab 現行數字 = untracked size256 檔案** — 因此建議 commit untracked 定案。
- **無 chunk 更換問題**:所有檔案已是 chunk_512,不必再跑 chunk_4096 對照。

### 5.2 Zep(only-return-fact)——(diagnostic ablation,pending)

**目的**:隔離 Zep 敗因是「無 query-time KU」還是「多顆粒 memory 干擾 answer LLM」。

**設計**:
- **不重跑 Zep**(避免 SaaS API cost + 360s wait);用**現有 Zep result JSON 的 `edges` field** re-render prompt
- 削掉 TEMPLATE 的 ENTITIES + EPISODES + context_block,只留 FACTS
- 重新 call gpt-4o-mini(same answer LLM,same temp=0)
- 對比:Acc-in-bucket(edges-only) vs Acc-in-bucket(full multi-granularity)
- **Attribution 結論**:若 edges-only Acc 明顯拉高 → 敗因是 nodes/episodes 干擾;若沒拉高 → 敗因是無 query-time KU(edges 本身就無新舊解析)

**Cost**:6k 74 + 32k 65 + 64k 66 = 205 LLM calls × gpt-4o-mini(~$0.001/call)≈ **< $0.30**

**Script(pending)**:`analysis/rerun_zep_edges_only.py`(下一步實作)

### 5.3 (a) vanilla mem0 全 3 length(pending)

現況只有 6k n=2 smoke。**需補**:6k/32k/64k full run(size=256,unknown max_samples)。

### 5.4 正式論文數據前(paper-final reproducibility protocol)

1. 用**新 Zep API key**(避免現行 key 累積狀態污染)重跑 Zep(所有 variant)
2. mem0 用 pinned `mem0ai==1.0.5` + repo `./mem0/` 現行 patch 版重跑
3. 記錄每次 run 的:commit hash / API key alias / date / n_samples
4. **不再改 pin**;所有 change 進 §5 前必先 update method_v1.md 對應 §

---

## §6 檔案位置速查

- Baseline runners:`methods/{mem0_fc_prompt_fix,zep}.py` + `agent.py` handlers
- YAML config:`configs/agent_conf/RAG_Agents/gpt-4o-mini/`
- Run scripts:`docs/0615_.../scripts/run_fc_sh.sh`, `run_zep_full100.py`
- Results:`outputs/{agent_name}/Conflict_Resolution/*.json`
- Retrieved pool(per-qid):`outputs/rag_retrieved/{agent_name}/k_{k}/{sub_dataset}/chunksize_{chunk}/query_{qid}_context_{cid}.json`
- 分析入口:`analysis/compute_pool_acc_crosstab.py`

---

## §7 Canonical File Registry(2026-07-04 cleanup 之後)

> **用途**:paper_current 引用的所有 baseline 結果的**唯一 source of truth**。任何新 analysis 都應該引用此表列出的路徑。
> **驗證**:`python analysis/rigor_audit.py` → 應該全 18 cells 顯示 ✅ OK。
> **修正 workflow**:若 rigor_audit 顯示 stale/broken → `python analysis/rebuild_aggregated_from_perqid.py`(source of truth 一律以 per-qid `response` 為準,per MAB `default_post_process` 重生 aggregated)。

### 7.1 每個 method × length 的 canonical 路徑

**所有 aggregated 檔案** 位置模板:
```
outputs/{agent_name}/Conflict_Resolution/factconsolidation_sh_{L}_..._results.json
```

**所有 per-qid 檔案** 位置模板:
```
outputs/rag_retrieved/{Structure_rag_name}/k_{k}/factconsolidation_sh_{L}/chunksize_512/query_{qid}_context_0.json
```

| Method | Agent name / Structure_rag name | k | Aggregated file pattern | Length |
| :--- | :--- | :--- | :--- | :---: |
| ours (full P3+P5) | `gpt-4o-mini-mem0-chunk512-temp0-openai-unified` / `Structure_rag_gpt-4o-mini-mem0_512_openai_unified` | 100 | `factconsolidation_sh_{L}_..._size256..._k100_chunk512_results.json` | 6k/32k/64k |
| ours (no_p5) | `..._unified_no_p5` / `Structure_rag_..._unified_no_p5` | 100 | 同上 | 6k/32k/64k |
| ours (struct) | `..._unified_struct` / `Structure_rag_..._unified_struct` | 100 | 同上 | 6k/32k/64k |
| ours (p3_only) | `..._unified_p3_only_no_struct` / `Structure_rag_..._unified_p3_only_no_struct` | 100 | 同上 | 6k/32k/64k |
| (b) mem0+P1 | `..._unified_dest` / `Structure_rag_..._unified_dest` | 100 | 同上 | 6k/32k/64k |
| (a) vanilla mem0 | `..._openai-native` / `Structure_rag_..._openai_native` | 100 | 同上 | 6k(only)|
| Zep (k=10) | `gpt-4o-mini-zep` / `Structure_rag_zep` | **10** | `factconsolidation_sh_{L}_..._k10_chunk512_results.json` | 6k/32k/64k |
| Zep(edges-only)(diagnostic)| `gpt-4o-mini-zep-edges-only`(**no per-qid dir**;post-hoc rerun script) | 10 | `factconsolidation_sh_{L}_..._edges_only_..._chunk512_results.json` | 6k/32k/64k |
| LCA(long-ctx gpt-4o-mini)| `gpt-4o-mini` + `gpt-4o-mini-temp0` | — | 標準 MAB output(non-mem0)| 6k/32k/64k |

**Note**:64k mem0 variants aggregated 用 `size256_shots0_max_samples1` 而非 `max_samplesunknown`;`analysis/rigor_audit.py::pick_agg_file` 自動 fallback。

### 7.2 分析 script 該讀哪個檔

| 用途 | Script | 讀取欄位 | 讀取來源 |
| :--- | :--- | :--- | :--- |
| Pool state × Acc crosstab | `analysis/compute_pool_acc_crosstab.py` | pool 用 per-qid `retrieved_memories` / `memories_str` / `edges`;acc 用 per-qid `response` + MAB official EM | per-qid |
| E2E EM 統計(landscape 表)| 同上;E2E = sum(acc across buckets) | 同上 | per-qid |
| Case study qid trace | `analysis/case_study_64k.py` | 全 fields(question/pool/response/gt)| per-qid + gt |
| Aggregated 重建(修 stale 或 broken)| `analysis/rebuild_aggregated_from_perqid.py` | 從 per-qid `response` + MAB `default_post_process` | per-qid → 生 aggregated |

**絕對不要**:直接讀 aggregated `exact_match` 欄位(可能 stale)—— 必 route via `_em_from_perqid()` in `compute_pool_acc_crosstab.py`(rerouted to per-qid + MAB official EM)。

### 7.3 2026-07-04 cleanup 清單(31 dirs → `outputs/_deprecated/2026-07-04-cleanup/`)

**Legacy mem0 exploration(dead-end)**:
- `gpt-4o-mini-mem0-chunk4096-temp0-l2-openai`(舊 chunk_4096)
- `gpt-4o-mini-mem0-chunk512-temp0-{factaware-l2,l2-openai,l2-openai-phase0,l2-openai-phase2,l2-openai-rerun,l2-openai-u5}`(L2 探索期,superseded by unified_*)
- `gpt-4o-mini-mem0-chunk512-temp0-openai-unified__gemma3-1b`(gemma3-1B 混跑試驗,一次性)
- `gpt-4o-mini-temp0-rerun`
- `hippo_rag_v2_nv_preview_REFERENCE`(HippoRAG 已 discontinued)

**Gemini early experiments(現用 Ollama gemma3 for weak-model)**:
- `gemini-2.5-{flash,flash-lite}`,`gemini-3.1-flash-lite*`(11 variants),`gemini-3.5-flash`

**恢復方法**:`mv outputs/_deprecated/2026-07-04-cleanup/<dir> outputs/<dir>` — 完全可逆。

### 7.4 Aggregated 重建紀錄(2026-07-04)

以下 4 個 aggregated files 從 per-qid `response` 重建(舊檔備份於 `outputs/_deprecated/2026-07-04-cleanup/`):
- `outputs/gpt-4o-mini-mem0-chunk512-temp0-openai-unified_dest/Conflict_Resolution/factconsolidation_sh_{6k,32k,64k}_..._results.json`(mem0+P1 三 length,aggregated stale)
- `outputs/gpt-4o-mini-zep/Conflict_Resolution/factconsolidation_sh_32k_..._results.json`(Zep 32k,aggregated broken — 有 13 個 `Answer:` 空 stub)

重建方式:`analysis/rebuild_aggregated_from_perqid.py`。metric 用 MAB 官方 `utils/eval_other_utils.py::default_post_process`(= max(EM(raw), EM(parsed))+ F1 + rougeL/sum)。
