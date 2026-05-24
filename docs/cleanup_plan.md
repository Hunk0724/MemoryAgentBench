# Cleanup Plan — `MemoryAgentBench/` 整理計畫

**最後更新**: 2026-05-24
**原則**:
1. **Move-only,絕不刪除** — 所有移動可逆,只搬位置
2. **保留所有研究成果** — 包括舊腳本、舊筆記,只是搬去 archive 子目錄
3. **不動 vendored libs** — `mem0/`、`cognee/`、`letta/`(等待補)、`methods/` 內部結構不動
4. **不動配置 / agent.py / 演算法** — 純物理移動
5. **git mv 保留歷史** — 所有 tracked file 用 `git mv`,untracked file 用 `mv`

---

## 現況規模

| 區塊 | 規模 | 問題 |
|---|---|---|
| `analysis/` 根層 `.py` | **96 個腳本** | 散亂,不知哪些 active |
| `analysis/` 子目錄 | `results/` 23M、`experiments/` 11M、`paper_motivation/` 1.9M、`contexts/` 168K | 結構 OK |
| `analysis/__pycache__/` | 284K | 應 gitignore + 清掉 |
| `analysis/` 根層 `.md` | INDEX、SESSION、implementation_status、smoke_test_findings、zep_methodology、fc_mh_hypotheses、fc_mh_research_overview | 多份散落筆記 |
| `docs/` | 13 個檔 + 2 子目錄 | 結構 OK,只是要把 v1 舊版歸 archive |
| **根目錄 11 個 `run_*.sh`** | 各種 1-3 KB shell | 應搬 `scripts/runs/` |
| **根目錄 3 個 stray `.md`** | `MIGRATION.md`、`Phase0 3day sprint spec.md`、`claude_chat_method_design_experiment.md` | 應搬 `docs/archive/` |
| **4 個 `.baseline_backup_*/`** | 169M + 220K + 400K + 428K = **170 MB** | 應搬 `archive/baseline_backups/`(已 gitignore) |
| `agents/Structure_rag_zep_*` | Zep 跑 dump | 應搬 `archive/runs/zep_2026-04-21/`(已 gitignore) |
| `outputs/`、`monitoring_logs/`、`logs/` | 200M run 產物 | 確認 gitignore + 留著 |
| `.cache/`、`cache/` | **45 GB** | 已 gitignore, **磁碟管理** issue,不是 repo 問題 |

---

## 目標結構

```
MemoryAgentBench/
├── (upstream files, 不動)
│   ├── agent.py, conversation_creator.py, initialization.py, main.py
│   ├── README.md, requirements.txt, LICENSE
│   ├── methods/, configs/, mem0/, cognee/, letta/, llm_based_eval/, utils/
│   ├── assets/, bash_files/
│
├── scripts/                                 # ← NEW: 所有 .sh 集中
│   ├── runs/                                # 11 個 run_*.sh 搬這
│   └── README.md                            # 解釋每個用途
│
├── docs/                                    # 文件,active
│   ├── PROVENANCE.md                        # 已寫
│   ├── cleanup_plan.md                      # 本檔
│   ├── method_v2.0.2_status_brief.md
│   ├── method_design_v2.0.2_spec.md
│   ├── method_v2.0.2_framework.xml
│   ├── engineering_todos_v2.0.2.md
│   ├── paper_narrative_experiments.md
│   ├── hardware_request_6k.md
│   ├── current_focus/                       # 已存在
│   ├── paper_draft/                         # 已存在
│   └── archive/                             # ← NEW
│       ├── v1_experiment_plan.md
│       ├── v1_step_by_step_commands.md
│       ├── method_design_v2.0.1_spec.md
│       ├── insight_discussion.md
│       ├── MIGRATION.md                     # ← 從根搬來
│       ├── Phase0_3day_sprint_spec.md       # ← 從根搬來(空格改 _)
│       └── claude_chat_method_design_experiment.md  # ← 從根搬來
│
├── analysis/
│   ├── paper_motivation/                    # ← user 最常用,不動
│   ├── results/                             # ← run 出來的結果,不動
│   ├── experiments/                         # ← 日期戳實驗,不動
│   ├── contexts/                            # ← FC context dump,不動
│   ├── current/                             # ← NEW: 最近活躍腳本(本月)
│   │   ├── compute_B1_retrieval_recall.py
│   │   ├── compute_B3b_em_by_hop.py
│   │   ├── compute_A1a_A1b_v2.py
│   │   ├── verify_timestamp_semantics.py
│   │   └── (~10 個正在用)
│   ├── archive/                             # ← NEW: 舊腳本歸檔(不刪)
│   │   ├── README.md                        # 解釋每個的歷史
│   │   ├── smoke_tests/                     # ~10 個 smoke_test_*.py
│   │   ├── oa_oracles/                      # oracle_a_*.py、oa2_*.py、sim_ob_*.py
│   │   ├── mem0_zep_audit/                  # mem0_*.py、zep_*.py
│   │   ├── mquake/                          # analyze_*mquake*.py
│   │   ├── eval/                            # eval_*.py
│   │   └── misc/                            # 其他
│   └── notes/                               # ← NEW: 散落 .md 筆記
│       ├── INDEX.md                         # 從 analysis/INDEX.md 移
│       ├── SESSION_2026-04-28_diagnostic_summary.md
│       ├── fc_mh_hypotheses.md
│       ├── fc_mh_research_overview.md
│       ├── implementation_status.md
│       ├── smoke_test_findings.md
│       ├── zep_methodology.md
│       └── diagnostic_findings.md
│
├── archive/                                 # ← NEW: 大型可逆歸檔
│   ├── baseline_backups/                    # 4 個 .baseline_backup_*/
│   │   ├── README.md                        # 每個 backup 是哪個 milestone
│   │   ├── 2026-05-11_v1_pre/
│   │   ├── 2026-05-17_4ablation_pre/
│   │   ├── g11_pre/
│   │   └── v2_phase2_w13_pre/
│   └── runs/                                # 從 agents/ 等
│       └── zep_2026-04-21/
│
├── outputs/                                 # gitignored, 不動
├── monitoring_logs/                         # gitignored, 不動
└── (.cache/, cache/, logs/, __pycache__/ — 全 gitignored)
```

---

## 具體搬遷清單(move-only)

### M1. 根目錄 → `scripts/runs/`

```bash
mkdir -p scripts/runs
git mv run_full_100_all.sh         scripts/runs/
git mv run_gemini_32k.sh           scripts/runs/
git mv run_gemini_global.sh        scripts/runs/
git mv run_gpt4omini.sh            scripts/runs/
git mv run_gpt4omini_retry.sh      scripts/runs/
git mv run_hipporag_gemini.sh      scripts/runs/
git mv run_oracle_a_gemini.sh      scripts/runs/
git mv run_pat_gemini.sh           scripts/runs/
git mv run_rpt_gemini.sh           scripts/runs/
git mv run_rpt_min_gemini.sh       scripts/runs/
git mv run_zep_mem0_phase1.sh      scripts/runs/
```

(`bash_files/sh/run_hipporag_fc.sh` 留在 `bash_files/` — 那是 upstream 原本的位置)

### M2. 根目錄 stray `.md` → `docs/archive/`

```bash
mkdir -p docs/archive
git mv MIGRATION.md                              docs/archive/
git mv "Phase0 3day sprint spec.md"              docs/archive/Phase0_3day_sprint_spec.md
git mv claude_chat_method_design_experiment.md   docs/archive/
```

### M3. `docs/` 內部分類

```bash
git mv docs/v1_experiment_plan.md       docs/archive/
git mv docs/v1_step_by_step_commands.md docs/archive/
git mv docs/method_design_v2.0.1_spec.md docs/archive/  # v2.0.1 已被 v2.0.2 取代
git mv docs/insight_discussion.md       docs/archive/
```

### M4. `analysis/` 主要重整

#### M4a. 新建 active 區
```bash
mkdir -p analysis/current analysis/archive analysis/notes
```

#### M4b. 最近活躍腳本搬 `analysis/current/`
**判定:本月(2026-05-17 後)寫的 + paper_narrative 直接需要的**
```bash
git mv analysis/compute_A1a_A1b_v2.py             analysis/current/
git mv analysis/compute_A1a_A1b_detection.py      analysis/archive/  # v1,被 v2 取代
git mv analysis/compute_B1_retrieval_recall.py    analysis/current/
git mv analysis/compute_B3b_em_by_hop.py          analysis/current/
git mv analysis/verify_timestamp_semantics.py     analysis/current/
git mv analysis/build_labels_full100.py           analysis/current/
git mv analysis/build_mini_eval_w14.py            analysis/current/
git mv analysis/eval_100q_full_analysis.py        analysis/current/
git mv analysis/eval_ablation_cross_compare.py    analysis/current/
git mv analysis/analyze_filter_cascade_corrected.py analysis/current/
git mv analysis/analyze_filter_inject_potential.py  analysis/current/
git mv analysis/analyze_priority5.py              analysis/current/
git mv analysis/dump_real_qa_prompt.py            analysis/current/
git mv analysis/eval_mini_w14_phase2b.py          analysis/current/
git mv analysis/eval_phase2_filter_quadrants.py   analysis/current/
git mv analysis/run_mini_eval_w14_step1.py        analysis/current/
git mv analysis/run_mini_eval_w3_step2.py         analysis/current/
git mv analysis/run_mini_eval_w3_updates_only.py  analysis/current/
git mv analysis/smoke_test_stage1_dump.py         analysis/current/
```

#### M4c. 其餘 ~75 個 .py 按 topic 歸 archive 子目錄

```bash
mkdir -p analysis/archive/{smoke_tests,oa_oracles,mem0_zep_audit,mquake,eval,sim_ob,misc}
# smoke tests
git mv analysis/smoke_test_*.py                 analysis/archive/smoke_tests/
# OA series
git mv analysis/oracle_a*.py                    analysis/archive/oa_oracles/
git mv analysis/oa2_*.py                        analysis/archive/oa_oracles/
git mv analysis/non_counterfactual*.py          analysis/archive/oa_oracles/
git mv analysis/nc_*.py                         analysis/archive/oa_oracles/
# Sim-OB series
git mv analysis/sim_ob_*.py                     analysis/archive/sim_ob/
# Mem0 / Zep
git mv analysis/mem0_*.py                       analysis/archive/mem0_zep_audit/
git mv analysis/zep_*.py                        analysis/archive/mem0_zep_audit/
git mv analysis/run_mem0_*.py                   analysis/archive/mem0_zep_audit/
git mv analysis/rerun_mem0_zep_aligned*.py      analysis/archive/mem0_zep_audit/
# MQuAKE
git mv analysis/analyze_*mquake*.py             analysis/archive/mquake/
# 剩下的
git mv analysis/*.py                            analysis/archive/misc/    # 最後一行擋住
```

#### M4d. `analysis/` 散落 `.md` → `analysis/notes/`
```bash
git mv analysis/INDEX.md                        analysis/notes/
git mv analysis/SESSION_*.md                    analysis/notes/
git mv analysis/fc_mh_*.md                      analysis/notes/
git mv analysis/implementation_status.md        analysis/notes/
git mv analysis/smoke_test_findings.md          analysis/notes/
git mv analysis/zep_methodology.md              analysis/notes/
git mv analysis/diagnostic_findings.md          analysis/notes/
```

#### M4e. 清 cache
```bash
rm -rf analysis/__pycache__
```

### M5. Backup 目錄 → `archive/baseline_backups/`

```bash
mkdir -p archive/baseline_backups
# 這些已 gitignore,不用 git mv,純 mv
mv .baseline_backup_2026-05-11             archive/baseline_backups/2026-05-11_v1_pre
mv .baseline_backup_4ablation_pre_1779013517 archive/baseline_backups/2026-05-17_4ablation_pre
mv .baseline_backup_g11_pre                archive/baseline_backups/g11_pre
mv .baseline_backup_v2_phase2_w13_pre      archive/baseline_backups/v2_phase2_w13_pre
```

(`archive/` 整個加進 `.gitignore`)

### M6. Zep agent dump → `archive/runs/`

```bash
mkdir -p archive/runs
mv agents/Structure_rag_zep_factconsolidation_mh_6k_chunk512_modelgpt-4o-mini archive/runs/zep_mh_2026-04-21
mv agents/Structure_rag_zep_factconsolidation_sh_6k_chunk512_modelgpt-4o-mini archive/runs/zep_sh_2026-04-21
rmdir agents
```

### M7. 加 README

```
scripts/runs/README.md            — 每個 .sh 用途 + 何時用
analysis/current/README.md        — 列出每個腳本對應到 paper_narrative_experiments.md 的哪格
analysis/archive/README.md        — 解釋為何歸檔 + 歷史
analysis/notes/README.md          — 各 .md 內容索引
docs/archive/README.md            — 各舊版文件的狀態
archive/README.md                 — baseline_backups 是哪個 milestone 的
```

### M8. `.gitignore` 加幾條

```
archive/
outputs/
monitoring_logs/
```

---

## 預期影響

| 指標 | Before | After |
|---|---|---|
| 根目錄檔案數 | 16 個 `run_*.sh` + `.md`(雜) | 5 個基本(agent.py、main.py、README.md、requirements.txt、conversation_creator.py、initialization.py) |
| `analysis/` 根層 .py | 96 個散落 | ~18 個 in `current/`,~75 個 in `archive/*/`(分類) |
| `analysis/` 根層 .md | 7 個 | 0 個(全進 `notes/`) |
| `docs/` 主要層 .md | 12 個(混 active + legacy) | 7-8 個 active + `archive/` 子目錄 |
| 磁碟可逆釋出 | — | `archive/baseline_backups/` 170 MB 可隨時刪 |

---

## 風險 / 副作用

| 風險 | 對策 |
|---|---|
| 有腳本可能 import 其他腳本(被搬會 broken) | 移動後跑 `grep -rn "from analysis\." analysis/current/` 確認 import 仍 OK |
| `.sh` 腳本可能寫死 `cd .../analysis/...` 路徑 | 移動後 grep 'analysis/' 全 .sh 確認 |
| `__pycache__` 殘留會混淆 | `rm -rf analysis/__pycache__` |
| `git mv` 可能跟 LFS 衝突 | 確認 `.gitattributes` — 應該無 LFS |
| 大量 git mv 一次 commit 不易 review | **建議分 5 個 commit**:M1 + M2 + M3 + M4 + M5/M6 |

---

## 執行計畫(我建議分 6 個 commit)

| Commit | 範圍 | size |
|---|---|---|
| `chore(repo): move run_*.sh to scripts/runs/` | M1 + scripts/runs/README.md | 12 files |
| `chore(repo): archive stray root .md` | M2 + docs/archive/README.md | 3 files |
| `chore(docs): archive v1 / v2.0.1 legacy specs` | M3 | 4 files |
| `chore(analysis): split into current/ archive/ notes/` | M4(分 4b/4c/4d/4e)+ READMEs | ~96 files |
| `chore(repo): consolidate baseline_backups + zep dumps under archive/` | M5 + M6 + README | ~5 dirs |
| `chore(gitignore): add archive/ outputs/ monitoring_logs/` | M8 | 1 file |

---

## 我建議的執行順序

1. **你 review 這份計畫,標出有問題的地方**
2. 確認後我**一個 commit 一個 commit** 執行,每個 commit 完先 `git status` 給你看
3. 任何 commit 完 user 都可以 `git revert` 退回
4. 全部完成後跑一次 `pytest`(如有)或 smoke import,確認沒搬壞 import path

**確認可以動工嗎?** 還是要先調整某個 M 項?
