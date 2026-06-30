# Session 紀錄:mem0/mem0g pilot 環境設置

> 日期:2026-05-24
> 目的:讓未來能 revert 本次改動,並清楚知道改了什麼

---

## 1. Git 狀態(本 session 開始時)

```
branch: exp/v2-llm-judge
HEAD:   a63a6b3 feat(hipporag): T1 path scoring variants for ablation
```

本 session 不 commit(沒有 user 明確要求 commit)。所有改動以 working tree 形式存在,可隨時 revert。

---

## 2. 改動清單(完全列舉)

### 2.1 修改既有檔(共 1 個,跟本 session 相關)

| 檔案 | 改動 | 影響 |
|---|---|---|
| [agent.py](../../../agent.py) | `_initialize_mem0_agent` 改寫 + 新增 `_create_answer_client` / `_answer_with_client` + `_handle_mem0_agent` 答題改走 helper | 121 行新增 / 15 行修改;支援 Vertex Gemini 雙層(mem0 內部 + 答題) |

> ⚠️ `docs/chat_discussion_context_2026-05-26.md` 也在 modified list,但**不是本 session 改的**(是之前 session 留下的)。

### 2.2 新增檔(本 session 全部新建,皆 untracked)

#### Scripts(3 個)
- [analysis/align_mem0_mquake.py](../../../analysis/align_mem0_mquake.py) — mem0/mem0g 版 MQuAKE alignment,支援 4 長度 × SH/MH
- [analysis/cache_fc_contexts.py](../../../analysis/cache_fc_contexts.py) — 從 HF arrow 抽 FC contexts
- [bash_files/generate_mem0_yaml_variants.py](../../../bash_files/generate_mem0_yaml_variants.py) — 5 model × 2 chunk → 20 個 yaml

#### Data cache(2 個)
- analysis/contexts/factconsolidation_64k_context.txt — 4580 facts
- analysis/contexts/factconsolidation_262k_context.txt — 18332 facts

#### Yaml(20 個 + 1 個資料夾)
- `configs/agent_conf/RAG_Agents/Gemini/Structure_rag_mem0{,g}_<MODEL>_chunk{512,4096}.yaml`
- 5 model:`gemini-1.5-flash-latest`, `gemini-2.5-flash-lite`, `gemini-2.5-flash`, `gemini-3.1-flash-lite`, `gemini-3.5-flash`

#### Docs(7 個 md + 4 個資料夾)
```
docs/INDEX.md
docs/baseline_methods/baseline_methods_paper_vs_impl.md  ← copy 自 analysis/
docs/ground_truth/mquake_alignment_guide.md
docs/experiments/log_schema.md
docs/experiments/pilots/mem0_mem0g_pilot_plan.md
docs/experiments/pilots/SESSION_2026-05-24_mem0_mem0g_setup.md  ← 本檔
docs/infrastructure/neo4j_setup.md
```

#### External(在 repo 外)
- `/home/yhchiang/MQuAKE/` clone 完成(從 https://github.com/princeton-nlp/MQuAKE,shallow depth=1)

#### Backup(本 session 自動生成)
- `.session_backups/agent_py_pre_mem0_changes.patch` — agent.py 改動的 diff,可 reverse-apply

---

## 3. Revert 指南

### Scenario A:整個 session 都退回(最徹底)

```bash
cd /home/yhchiang/MemoryAgentBench

# Step 1: revert agent.py(關鍵 — 這是 in-place 修改)
git checkout -- agent.py
# 或等價:apply reverse patch
# git apply --reverse .session_backups/agent_py_pre_mem0_changes.patch

# Step 2: 刪除本 session 新增的檔/夾(都 untracked,刪除安全)
rm -rf configs/agent_conf/RAG_Agents/Gemini/
rm -rf docs/{baseline_methods,ground_truth,experiments,infrastructure}/
rm docs/INDEX.md
rm analysis/align_mem0_mquake.py
rm analysis/cache_fc_contexts.py
rm analysis/baseline_methods_paper_vs_impl.md     # 副本(原檔在 docs/baseline_methods/)
rm analysis/contexts/factconsolidation_64k_context.txt
rm analysis/contexts/factconsolidation_262k_context.txt
rm bash_files/generate_mem0_yaml_variants.py

# Step 3(可選):移除 MQuAKE clone
rm -rf /home/yhchiang/MQuAKE
```

### Scenario B:只 revert agent.py(保留 docs/yaml/scripts)

```bash
git checkout -- agent.py
```

新增的 docs/yaml/scripts 不影響 benchmark 行為(benchmark 不會自動載入 untracked yaml),所以保留無害。

### Scenario C:保留 agent.py 改動但要 commit

```bash
# 先把 outputs 改動 stash 掉(那些不是本 session 改的)
git stash push outputs/ docs/chat_discussion_context_2026-05-26.md

# Add 本 session 的東西
git add agent.py
git add analysis/align_mem0_mquake.py analysis/cache_fc_contexts.py
git add bash_files/generate_mem0_yaml_variants.py
git add configs/agent_conf/RAG_Agents/Gemini/
git add docs/{INDEX.md,baseline_methods,ground_truth,experiments,infrastructure}/
git add analysis/contexts/factconsolidation_{64k,262k}_context.txt

# Commit
git commit -m "feat(mem0): pilot setup for mem0/mem0g × 5 Gemini × 2 chunk"

# 恢復 outputs(若需要)
git stash pop
```

---

## 4. 「未受影響」的東西(本 session 沒動)

- 所有 `outputs/` 內既有檔(HippoRAG 之前的實驗結果)
- `mem0/` 整個 vendored 子目錄(0 改動)
- `methods/`、`utils/`、`main.py`、`configs/data_conf/` 等核心 benchmark 程式
- `analysis/` 內既有 .py(`analyze_*_mquake.py`、`analyze_zep_*.py` 等)

---

## 5. Sanity check 紀錄

| 檢查 | 結果 |
|---|---|
| `python -c 'import ast; ast.parse(open("agent.py").read())'` | ✅ OK |
| `align_mem0_mquake.py` × FC-MH 6k LCA results | ✅ 100/100 aligned |
| `align_mem0_mquake.py` × FC-MH 32k LCA results | ✅ 100/100 aligned |
| 20 個 yaml 生成 | ✅ |
| docs/INDEX.md 連結 | ✅ |

---

## 6. 下一步(尚未做)

依 [mem0_mem0g_pilot_plan.md §2-3](mem0_mem0g_pilot_plan.md) 進行 — Neo4j 啟動 → 5 model dry-run → smoke test → 批次跑 20 個 chunk=512 → 批次跑 20 個 chunk=4096。

Coverage validation (32k/64k/262k 是否都能對應 MQuAKE 找到衝突對/單一事實)等寫完 coverage script 後驗證(本次 session 進行中)。
