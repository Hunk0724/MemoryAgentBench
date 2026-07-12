# Reproduction Guide — 如何重跑實驗、核對數字

> **用途**:paper reviewer / 未來 session Claude Code / 換機器 team member 讀完此檔就能**逐格重現** [COVERAGE.md](COVERAGE.md) 上的任一 cell。每個實驗記 exact command → expected number → cost/wall 估算。
> **搭配讀**:[`CLAUDE.md §環境`](../../../../../CLAUDE.md) · [`methods_reproduction.md`](../methods_reproduction.md)(baseline package pin)· [`evaluation_protocol_main.md`](../evaluation_protocol_main.md)(evaluation protocol)。
> **檢驗數字時**:所有 canonical 數字回引 [`../results/objective_data_consolidated.md`](../results/objective_data_consolidated.md);跨版本容忍 ±2-3 pp(temp 0 但 OpenAI server bf16 微小非決定性,見 `CLAUDE.md §Migration proof`)。

---

## §0. Prereqs(先確認環境)

### 0.1 Env

```bash
# One-shot bootstrap(換機器後)
git clone -b exp/v2-llm-judge https://github.com/Hunk0724/MemoryAgentBench.git && cd MemoryAgentBench
conda create -n MABench python=3.10 -y && conda activate MABench
pip install -r requirements-core.txt          # ⚠ 不是 requirements.txt(見 CLAUDE.md §換機重建)
```

### 0.2 `.env`(不進 git;每台機器需自建)

```
OPENAI_API_KEY_A=sk-...
OPENAI_API_KEY_B=sk-...
OPENAI_API_KEY_C=sk-...
OPENAI_API_KEY_D=sk-...
OPENAI_API_KEY_E=sk-...
ZEP_API_KEY_A=...  # Zep cloud (LME 128k 上限,不夠用)
ZEP_API_KEY_B=...
ZEP_API_KEY_C=...
ZEP_API_KEY_D=...
```

### 0.3 Datasets

- **FC-SH / FC-MH**:HuggingFace `ai-hyz/MemoryAgentBench` 自動抓(用 `datasets` package)。無需手動下載。
- **LongMemEval**:手動下載 `xiaowu0162/longmemeval-cleaned` 的 `longmemeval_s_cleaned.json` / `longmemeval_oracle.json` → 放 `data/longmemeval/`。

### 0.4 Migration sanity check(強烈建議跑一次)

```bash
RUN_OAI_KEY_NAME=OPENAI_API_KEY_A bash docs/0615_intro_framework_after_problem_statement/scripts/run_fc_sh.sh 6k ours
```

**驗證通過標準**(6k `ours` = struct+P3+P5+argmax 於 gpt-4o-mini backbone):
- has_pair EM ≈ **68/74(91.9%)**、overall ≈ **93/100** ± 2-3
- Wall ~50 min(Mac Studio M2 Ultra)/ ~54 min(Windows i7)
- 若跑通且數字吻合 → pipeline(code + env + data + keys + qdrant)完整轉移成功

---

## §1. FC-SH 實驗(fastest to reproduce headline claims)

**執行 script**:`docs/0615_intro_framework_after_problem_statement/scripts/run_fc_sh.sh <L> <method>`

**核心 env vars**:
- `RUN_OAI_KEY_NAME=OPENAI_API_KEY_{A|B|C|D|E}` — 選 API key(避免同 key 多程序衝 quota)
- `MODEL_TAG={gpt-4o-mini|gpt-4.1-mini|gpt-4o|gemma3-1b|...}` — 選 backbone(空 = 預設 gpt-4o-mini)
- `MEM0_TRIPLE_MODEL={same as MODEL_TAG}` — mem0 內部 LLM(通常同 backbone,full swap)
- `RUN_ZEP_KEY_NAME=ZEP_API_KEY_{A|B|C|D}` — Zep only,選 Zep key

### 1.1 Method 別 → script method 對照(**極重要,常誤解**)

| Paper 稱呼 | script `<method>` arg | Query-time pipeline | Store output_dir suffix |
|:--|:--|:--|:--|
| **ours (main)** ← 論文主 method | **`ours_no_p5`** ⚠(NOT `ours`)| (S,P) struct + P3 LLM + argmax(**NO P5**)| `_no_p5` |
| ours (+P5) ← appendix ablation | `ours` ⚠(內含 P5)| struct + P3 + **P5** + argmax | 無 suffix |
| ours (struct) ← ablation | `ours_struct` | struct + argmax(no P3, no P5)| `_struct` |
| ours (p3-only) ← ablation | `ours_p3_only_no_struct` | P3 + argmax(no struct, no P5)| `_p3_only_no_struct` |
| (b) mem0+P1 ← extraction-controlled baseline | `b` | ours' P1 extract + mem0 destructive | `_dest` |
| (a) vanilla mem0 | `vanilla` | mem0 native extract + destructive | `_native` |

> ⚠ **最常踩雷**:script `ours` 是**+P5** 版(內含 P5),不是 paper "ours main"。paper "ours main" 用 `ours_no_p5`。此 naming 於 2026-07-07 已 canonicalize,見 [memory `ours-method-naming-canonical`](../../../../../.claude/projects/-Users-yhchiang/memory/project_ours_method_naming_canonical.md)。

### 1.2 執行順序 caveat(reproduction 必知)

**held-fixed baseline**(`b`、`ours_struct`、`ours_no_p5`、`ours_p3_only_no_struct`)會**重用 `ours` 的 extraction cache** → **同一長度必須先跑 `ours` 或 `ours_no_p5`、再跑 held-fixed variants**,否則 extraction 會重抽(失去 held-fixed 一致性)。

推薦順序(以 6k 為例):
```bash
# 1. 先跑 ours_no_p5(paper main;建 extraction cache)
RUN_OAI_KEY_NAME=OPENAI_API_KEY_A bash .../run_fc_sh.sh 6k ours_no_p5
# 2. 依賴 ours_no_p5 extraction cache 的 held-fixed baselines
RUN_OAI_KEY_NAME=OPENAI_API_KEY_A bash .../run_fc_sh.sh 6k b
RUN_OAI_KEY_NAME=OPENAI_API_KEY_A bash .../run_fc_sh.sh 6k ours_struct
RUN_OAI_KEY_NAME=OPENAI_API_KEY_A bash .../run_fc_sh.sh 6k ours_p3_only_no_struct
# 3. 獨立 baselines(不共用 cache)
RUN_OAI_KEY_NAME=OPENAI_API_KEY_A bash .../run_fc_sh.sh 6k vanilla
```

### 1.3 主要 backbone × length × method 執行對照

**A. gpt-4o-mini(mid,主 regime)**

| Length | Command | Expected has_pair EM | Wall | Cost($) |
|:--|:--|:--:|:--:|:--:|
| 6k | `bash run_fc_sh.sh 6k ours_no_p5` | **69/74 (93.2%)** | ~50 min | ~$1.0 |
| 6k | `bash run_fc_sh.sh 6k ours` | 68/74 (91.9%) | ~50 min | ~$1.2 |
| 32k | `bash run_fc_sh.sh 32k ours_no_p5` | **57/65 (87.7%)** | ~1.5 hr | ~$1.5 |
| 64k | `bash run_fc_sh.sh 64k ours_no_p5` | **60/66 (90.9%)** | ~2.5 hr | ~$3 |
| 6k | `bash run_fc_sh.sh 6k b` | 34/74 (46%) | ~30 min | ~$0.3 |
| 6k | `bash run_fc_sh.sh 6k vanilla` | 0/74 (0%) ⚠ | ~30 min | ~$0.5 |

> ⚠ `vanilla` 於 FC-SH 6k has_pair = 0%(native extraction 抽不到 dense fact chunks 的 fact);此為預期,非 bug。**於 FC-SH 用 `b` 為主 baseline**(給 mem0 我方 P1 消除 extraction failure confound)。

**B. gpt-4.1-mini(strong)**

需設 `MODEL_TAG=gpt-4.1-mini MEM0_TRIPLE_MODEL=gpt-4.1-mini`。

| Length | Command | Expected has_pair EM | Notes |
|:--|:--|:--:|:--|
| 6k | `MODEL_TAG=gpt-4.1-mini MEM0_TRIPLE_MODEL=gpt-4.1-mini bash run_fc_sh.sh 6k ours_no_p5` | **66/74 (89%)** | 2026-07-07 重跑(修正之前 script `ours` = +P5 誤標 61/74 為 main 的錯誤)|
| 6k | 同上 + `ours` | 61/74 (82%)= +P5 | 供 §4.5.3 P5 ablation |
| 6k | 同上 + `b` | 56/74 (76%)| |
| 32k | `MODEL_TAG=gpt-4.1-mini ... 32k ours_no_p5` | **51/65 (79%)** | |
| 32k | `MODEL_TAG=gpt-4.1-mini ... 32k b` | **53/65 (82%)** ⚡ | 意外:b **勝** ours main 3pp,gap collapse |
| 64k | `MODEL_TAG=gpt-4.1-mini ... 64k ours_no_p5` | 53/66 (80%) | |
| 64k | `MODEL_TAG=gpt-4.1-mini ... 64k b` | 55/66 (83%) | b 又勝(±3pp gap collapse)|

**C. gpt-4o(strong,額外)**

| Length | Command | Expected | Notes |
|:--|:--|:--:|:--|
| 64k | `MODEL_TAG=gpt-4o MEM0_TRIPLE_MODEL=gpt-4o bash run_fc_sh.sh 64k ours_no_p5` | 61/66 (92%) | 唯一有的 gpt-4o 點 |

**D. gemma3-1B/4B/12B/27B(weak,GX10)**

**執行環境**:GX10 machine(有 Ollama + gemma weights)。跑法與 gpt-4o-mini 相同,只需:

```bash
# Ollama 啟動 gemma model(換機 setup)
ollama pull gemma3:1b     # or 4b, 12b, 27b
# Backbone swap via MODEL_TAG
MODEL_TAG=gemma3-1b MEM0_TRIPLE_MODEL=gemma3-1b \
  RUN_OAI_KEY_NAME=OPENAI_API_KEY_A \
  bash docs/0615_intro_framework_after_problem_statement/scripts/run_fc_sh.sh 6k ours_no_p5
```

**Expected(6k has_pair EM)**:

| Backbone | ours (main) | ours (struct) | ours (p3-only) | (b) mem0+P1 | Zep |
|:--|:--:|:--:|:--:|:--:|:--:|
| gemma3-1B | 25/74 (34%) | 29/74 (39%) | 7/74 (9%) | 0/74 (0%) | 12/74 (16%) |
| gemma3-4B | 54/74 (73%) | 54/74 (73%) | 26/74 (35%) | 0/74 (0%) | 17/74 (23%) |
| gemma3-12B | 73/74 (99%) | 73/74 (99%) | 46/74 (62%) | 44/74 (59%) | 43/74 (58%) |
| gemma3-27B | 70/74 (95%) | 65/74 (88%) | 27/74 (36%) | 36/74 (49%) | 35/74 (47%) |

> **weak-tier caveat**:gemma 為 per-backbone extraction(每 size 用自己的 gemma 抽取,不是統一 gpt 抽);同 backbone 內 method 比較公平,跨 backbone 絕對值混抽取品質。詳見 [`../results/weak_model_6k_analysis.md §0`](../results/weak_model_6k_analysis.md)。

**vanilla 沒 gemma-1B 結果**:1B 不會產 mem0 native extraction schema → 崩、不列。

**gemma 沒 32k/64k**:GX10 wave 目前只完成 6k;長 context 需另 GPU wave。

### 1.4 EM 讀出方法(post-run 手動 verify)

Script 內建 EM print(見 `run_fc_sh.sh` line 148),但若要獨立 verify:

```bash
python3 -c "
import json, glob
fs = glob.glob('outputs/gpt-4o-mini-mem0-chunk512-temp0-openai-unified_no_p5/Conflict_Resolution/*sh_6k*results*.json')
d = json.load(open(fs[0]))
rows = d['data']
em = sum(1 for r in rows if r.get('exact_match'))
# has_pair-only
from collections import Counter
gt = {r['query_id']: r.get('conflict_type') for r in json.load(open('analysis/results/sh_6k_mquake_analysis.json'))}
by_ct = Counter(); by_em = Counter()
for r in rows:
    ct = gt.get(r.get('query_id'), '?')
    by_ct[ct] += 1
    if r.get('exact_match'): by_em[ct] += 1
print(f'overall {em}/{len(rows)}, has_pair {by_em.get(\"has_pair\",0)}/{by_ct.get(\"has_pair\",0)}')
"
```

---

## §2. Zep FC-SH(需 D key + probe waiter fix)

**執行 script**:`docs/0615_intro_framework_after_problem_statement/scripts/run_zep_fc.sh <L>`

### 2.1 Zep key 選擇(關鍵)

Zep free plan 於 A/B/C key 已耗盡(過去測試燒完 episode credit)。**目前唯一可用 = D key**:

```bash
MODEL_TAG=gpt-4o-mini RUN_OAI_KEY_NAME=OPENAI_API_KEY_A RUN_ZEP_KEY_NAME=ZEP_API_KEY_D \
  bash docs/0615_intro_framework_after_problem_statement/scripts/run_zep_fc.sh 6k
```

### 2.2 Probe-based waiter(2026-07-07 patch)

`agent.py:1162-1191` 的 Zep async wait 從固定 360s 改為 **episode-stability probe**:
- 初始等 360s
- 每 300s probe 一次 `graph.search(scope='episodes', limit=200)`
- 兩輪 episode count 相同 → graph 已 ready → 開始 queries
- Max 8 probes(~40 min 額外 wait)

**為何 patch**:先前 32k Zep 用 360s 硬等,graph 未完整處理 → probe with `scope='edges' limit=3` 假通過 → 100% empty response → 4/65 has_pair(broken)。Patch 後 20/65(true baseline)。

### 2.3 Expected(gpt-4o-mini backbone)

| Length | Command | Expected has_pair EM | Wall |
|:--|:--|:--:|:--:|
| 6k | `... run_zep_fc.sh 6k` | 46/74 (62%) | ~10 min |
| 32k | `... run_zep_fc.sh 32k` | 33/65 (51%) ⚠(D key 可能仍 partial)| ~15 min |
| 64k | `... run_zep_fc.sh 64k` | 36/66 (55%) | ~20 min |

**gpt-4.1-mini × Zep**:
- 6k = 46/74(=gpt-4o-mini 值,flat)
- 32k = 20/65(D key + probe waiter 後,顯著低於 4o-mini)
- 64k = 23/66 strict / 50/66 sEM(4.1-mini answer LLM 產 verbose format,strict EM 崩,sEM 追回)

### 2.4 Zep FC-SH 「輸出檔」路徑

- outputs/`${MODEL_TAG}`-zep/Conflict_Resolution/factconsolidation_sh_`${L}`_...results*.json

---

## §2.5 Deterministic-freshness baseline(Reddy & Challaram 2026,直接對手)

並行工作 "Don't Ask the LLM to Track Freshness"(BM25 → LLM extract candidates → Python `max(serial)`)。我們**直接 import 他們的程式碼**跑在我們設定下。結果與判讀:[`../results/deterministic_freshness_baseline.md`](../results/deterministic_freshness_baseline.md)。

- **他們的 code**:vendored 於 [`../../related work/memory-conflict-resolution/`](../../related%20work/memory-conflict-resolution/)(MIT,commit `b6b92b4`)。
- **driver**:`docs/0615_.../scripts/maxserial_theircode.py`(stub 掉他們的 Langfuse `_lf`,import `_pipeline._extract_candidates`(verbatim CANDIDATE_PROMPT)+ `_freshness_pick`)。
- **設定**:bank = 我方 P1 抽取(extraction-controlled)+ ingestion ordinal;metric = 官方 overall-100 SubEM;backbone = `PIPELINE_MODEL`。

### 執行(vector top-100 = 公平版,預設)
```bash
cd $REPO_ROOT
set -a; . .env; set +a; export OPENAI_API_KEY="$OPENAI_API_KEY_A"
export PIPELINE_MODEL=gpt-4o-mini
python docs/0615_intro_framework_after_problem_statement/scripts/maxserial_theircode.py --length 6k
# --retrieval bm25  -> authors' as-designed top-10 (reproduces their released 71%/62.2%)
```
> 也可用 harness 原生 `dotenv`(main.py:31 同法)載 key:`python -c "import dotenv,os,runpy,sys; dotenv.load_dotenv(); os.environ['OPENAI_API_KEY']=os.environ['OPENAI_API_KEY_A']; sys.argv=['x','--length','6k']; runpy.run_path('docs/0615_.../scripts/maxserial_theircode.py', run_name='__main__')"`。首次會 embed bank(快取 `outputs/maxserial_theircode/bank_emb_<L>.npy`)。

### Expected(6k × gpt-4o-mini,官方 SubEM)
| retrieval | overall | has_pair | extraction leak(wrong & n_cand=1)|
|:--|:--:|:--:|:--:|
| **vector top-100(公平)** | **80%** | **54/74 (73%)** | 20/20 |
| bm25 top-10(as-designed)| 71% | 46/74 (62%) | 27/28(= 作者釋出值)|

> **對照**:ours (main) 94% / Zep 82% / **作者 80%** / mem0+P1 52%(全 6k gpt-4o-mini overall SubEM)。失敗機制 = world-prior extraction leak(LLM 抽候選漏掉 counterfactual);ours (S,P) 結構 identity 免疫。詳見 results doc。

---

## §3. LME-KU(LongMemEval Knowledge-Update)

**執行 script**:`docs/0615_intro_framework_after_problem_statement/scripts/run_lme_ku.sh <method> [limit] [judge]`

### 3.1 資料 prereq

- `data/longmemeval/longmemeval_s_cleaned.json`(手動下載)
- 篩選 KU questions:script 內建 `--qtype knowledge-update` 抽出 78 題

### 3.2 4 methods 對照(gpt-4o-mini backbone,gpt-4o-mini judge)

| Method | script command(sharded)| Expected KU accuracy | Cost | Wall |
|:--|:--|:--:|:--:|:--:|
| **ours (main)** | `SHARD=0 NSHARD=2 RUN_OAI_KEY_NAME=OPENAI_API_KEY_A bash run_lme_ku.sh ours_no_p5` + shard 1 with key B | **55/78 = 70.5%** | ~$2 | ~1.5 hr |
| **ours (+P5)** | `bash run_lme_ku.sh ours`(注意:script `ours` = +P5)| **~55/78 = 70.5%**(P5 net-zero)| ~$5 | ~1.5 hr |
| ours (+P5) via **reuse**(推薦,快 15x)| `bash run_lme_ku.sh ours_p5_reuse`(先跑 ours_no_p5)| 55/78 = 70.5%(same as main)| ~$0.5 | ~5 min/shard |
| (a) vanilla mem0 | `bash run_lme_ku.sh vanilla` | **53/78 = 67.9%** | ~$4 | ~1.5 hr |
| (b) mem0+P1 | `bash run_lme_ku.sh b`(需先跑 ours_no_p5)| **47/78 = 60.3%** | ~$3 | ~2 hr |

### 3.3 ⚡ `ours_p5_reuse` — 便宜快速的 +P5 verification(2026-07-07 新增)

**用途**:reuse ours (main) 已 populated 的 store,只重跑 query phase 加 P5,得 P5 decision trace。省 memorize 階段的 LLM cost。

**Prereq**:先跑完 `ours_no_p5`(產出 store + caches):
```bash
SHARD=0 NSHARD=2 RUN_OAI_KEY_NAME=OPENAI_API_KEY_A bash run_lme_ku.sh ours_no_p5
SHARD=1 NSHARD=2 RUN_OAI_KEY_NAME=OPENAI_API_KEY_B bash run_lme_ku.sh ours_no_p5
# (等 78 hyps 齊)
```

**執行 reuse**:
```bash
SHARD=0 NSHARD=2 RUN_OAI_KEY_NAME=OPENAI_API_KEY_A bash run_lme_ku.sh ours_p5_reuse
SHARD=1 NSHARD=2 RUN_OAI_KEY_NAME=OPENAI_API_KEY_B bash run_lme_ku.sh ours_p5_reuse
```

**Internal mechanism**(`run_lme_ku.sh:66-89`):
- 用 `ours_no_p5.yaml`(agent_name 匹配 populated store)
- SUBDS override 為 `longmemeval_s_ku_ours_no_p5_${SHARDSFX}`(共用 store)
- reuse extraction/triple/subject/grouping caches
- FRESH conflict_cache(P5 decisions log)
- `MEM0_P5_SKIP` unset → P5 enabled
- 加 `--query-only` flag(`run_longmemeval_ku.py:52`)→ skip memorize phase

**Output**:
- `docs/.../lme_hyps/lme_ku_ours_p5_reuse_${SHARDSFX}.jsonl`
- `analysis/results/p1_caches/lme/conflict_ours_p5_reuse_${SHARDSFX}.json`(P5 decisions,可讀取分析)

### 3.4 Judge 執行(post-run)

```bash
# 1. Concat shards
cat docs/0615_intro_framework_after_problem_statement/lme_hyps/lme_ku_ours_no_p5_s0n2.jsonl \
    docs/0615_intro_framework_after_problem_statement/lme_hyps/lme_ku_ours_no_p5_s1n2.jsonl \
    > docs/0615_intro_framework_after_problem_statement/lme_hyps/lme_ku_ours_no_p5.jsonl

# 2. Judge(要 conda activated + .env sourced;用 miniforge3 或 miniconda3 對應路徑)
bash -c '
cd /Users/yhchiang/MemoryAgentBench
set -a; . .env; set +a
export OPENAI_API_KEY="$OPENAI_API_KEY_A"
HYP=$PWD/docs/0615_intro_framework_after_problem_statement/lme_hyps/lme_ku_ours_no_p5.jsonl
REF=$PWD/data/longmemeval/longmemeval_s_cleaned.json
cd llm_based_eval
$HOME/miniforge3/envs/MABench/bin/python evaluate_qa_official.py gpt-4o-mini "$HYP" "$REF" | tail -12
'
# Output ends with "Accuracy: 0.7051" + per-qtype breakdown
```

### 3.5 Zep LME-KU:**已 defer**(Zep free plan 128k 上限)

- 所有 4 keys(A/B/C/D)測試皆撞 Zep episode credit / 128K per-graph 上限
- LME context ~115K tokens/題 → 遠超 free plan
- **Future work**:移進 Graphiti self-hosted(`/Users/yhchiang/graphiti`,已 clone,~1-2 day 整合)
- 目前 §4.6 Table 7 Zep 位標 "deferred"

---

## §4. Common pitfalls & gotchas

### 4.1 Naming confusion(**2026-07-07 canonical 前最常誤解**)

- `ours` script method ≠ paper "ours (main)";前者是 +P5,後者是 `ours_no_p5`
- 若讀舊 paper 材料看到 "ours" 沒帶 (main) / (+P5) qualifier:根據 has_pair 6k 數字判別 — 68/74 = +P5、69/74 = main
- 詳見 memory [`ours-method-naming-canonical`](../../../../../.claude/projects/-Users-yhchiang/memory/project_ours_method_naming_canonical.md)

### 4.2 Extraction cache order

- `b` / `ours_struct` / `ours_no_p5` / `ours_p3_only_no_struct` 都 reuse `ours` 的 extraction cache
- 同一長度必須**先跑 `ours` 或 `ours_no_p5`**,再跑 held-fixed variants
- 否則變成 fresh extraction → 失去 held-fixed 一致性

### 4.3 SUBDS race(2026-07-07 fix,已進 master)

- 舊 `run_lme_ku.sh` 於 concurrent methods 上撞 shared `history_${SUBDS}__*.db` glob → 誤刪對方 db → sqlite readonly error
- Patched:`SUBDS="longmemeval_s_ku_${METHOD}${SHARDSFX}"`(method-specific)

### 4.4 Cost logger

- `MEM0_COST_LOG=$LOGROOT/cost_lme_${METHOD}${SHARDSFX}.jsonl` 於 script 內建
- 讀取:field 是 `prompt_tokens` / `completion_tokens`(不是 `in_tok`/`out_tok`)
- gpt-4o-mini pricing:$0.15/M input, $0.60/M output(2026-07 rates)
- gpt-4.1-mini pricing:$0.40/M input, $1.60/M output

### 4.5 Zep 3 種失敗態(Zep debugging 用)

| 症狀 | Root cause | Fix |
|:--|:--|:--|
| 100% empty response(input_len=85=raw question)| `graph.search` 全空,graph 未 ingest 完 | 用 episode-stability probe waiter(`agent.py:1162-1191`)|
| 403 forbidden "over episode credit" | Free plan account 用完 monthly quota | 換 key;等 monthly reset;上 paid plan |
| 429 rate limit "5 req/min" | Free plan rate throttle | 等 33s retry-after,或換 key |

### 4.6 Migration 兩雷(換機時)

- `.env` 殘留舊機 `HF_*` 變數 → 卡 FC-SH HuggingFace 資料載入 → `.env` 只留 API key,清 `HF_*` / `SSL_CERT_FILE` / `*_CA_BUNDLE`
- Windows conda `SSL_CERT_FILE` 指向 Unix 佈局路徑 → httpx/openai TLS 炸 → 複製憑證或修 SSL_CERT_FILE(見 CLAUDE.md § Migration 兩雷)

---

## §5. 對照 canonical 數字(discrepancy 排查用)

若你重跑數字與此檔 expected 差 > 3pp,排查:

1. **backbone / MODEL_TAG 對嗎**?(gpt-4o-mini vs gpt-4.1-mini 差 5-15pp normal)
2. **method 對嗎**?(`ours` = +P5 有 P5、`ours_no_p5` = main 無 P5;數字差 1-3pp)
3. **extraction cache 有 reuse 嗎**?(held-fixed baseline `b` 沒 reuse `ours` cache 會失去對照乾淨度)
4. **判斷數字是 has_pair 還是 overall**?(6k has_pair 分母 74;overall 分母 100)
5. **是本次 run 的 fresh 數字還是 partial hyps**?(script 未跑完 exit=1 有 partial 結果混錯)

canonical 數字 authoritative source:[`../results/objective_data_consolidated.md`](../results/objective_data_consolidated.md) §1 mapping + §2 Table A + §3 Table B。

---

## §6. Change log

- **2026-07-07**:初版,含 §1-5 + gemma3 GX10 section + LME-KU 完整 4 methods + ours_p5_reuse 快速 verify method
- **未來若有 backbone / method 補齊**:更新 §1.3 對應 cell + COVERAGE.md 對應 row
