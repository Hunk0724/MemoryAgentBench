# 實驗計畫 / Roadmap

> 初擬 2026-06-26,**策略重整 2026-06-26**:以「**論文要證明什麼**」(§3 核心 evidence)為主軸,
> 再排執行序(§4)。結果填 `experiment_results.md`;設計見 `method_pipeline_and_prompts.md`;
> narrative 見 `intro_zh_revised_v2.md`;KU 範圍見 `ku_taxonomy_and_scope_zh.md`。

---

## 0. 固定共同設定(invariants)

| 項目 | 值 |
|---|---|
| Backbone LLM | **gpt-4o-mini**(temp 0)為主點;**能力軸階段**掃 強/中/弱(§4 步驟3) |
| Embedding | text-embedding-3-small(1536d)、batch(只快、結果不變) |
| Chunk | **512**(所有方法一致,apples-to-apples)|
| ⚠ chunk caveat | benchmark paper 對 **mem0/Zep/cognee/mirix 預設 4096**(經各方法 config 的 `agent_chunk_size`,非 code 強制;`conversation_creator._determine_chunk_size`)。我們**統一用 512** 與 ours 對齊 + 避免 **Zep `data[:9998]` 截斷**(4096 token≈16k char>9998)。**4096 = 全不同設定 → 獨立另一張表(後續實驗)**,且可順便讓 262k 慢 baseline 變可行(但 Zep 截斷需先解) |
| 檢索 | cosine **top-100**、**raw-question**(ungated,所有方法一致) |
| Temporal key | ordinal(ingestion 序) |
| 評分 | FC = SubEM/exact_match;LongMemEval = LLM-as-judge(官方 `evaluate_qa.py`,gpt-4o judge) |
| 機制分析 | L1 檢索態 → L2 解析後態 → L3 state→EM → overall;+ final-context 純度(§3 Evidence-2) |

---

## 1. Method registry(精確 config + flag)

| 方法 | intro 分類 | config / 來源 | 關鍵 env / flag |
|---|---|---|---|
| **Ours** | **query-time resolution(本作)** | `..._mem0_512_openai_unified.yaml`(`use_unified_extractor`) | `MEM0_ADD_MODE=phase0_structural` + `MEM0_QUERY_MODE=phase2` + fresh `p1_` caches |
| **真 vanilla mem0**(a) | proactive·coupled(stock) | `..._mem0_512_openai_native.yaml`(無抽取 flag) | 無 phase env;raw-q |
| **mem0(b)** | coupled,抽取held fixed | `..._unified_dest.yaml`(`use_unified_extractor`) | **破壞性更新(ADD/UPDATE/DELETE),無 phase env** |
| **Zep** | **proactive·decoupled**(主力對照) | `zep.yaml`(內建);`methods/zep.py` | 需 `ZEP_API_KEY` |
| LightMem | proactive·coupled | 未內建 → 需整合(timebox,§4 步驟5) | — |
| Long-context LLM(LCA) | 無記憶(上界對照) | `Long_Context_Agents/Long_context_agent_*` | 整段塞 context |
| RAG(BM25/dense) | retrieval-only(passive) | `Simple_rag_*-bm25` / `Embedding_rag_*-text_embedding_3_small` | — |
| Passive-on-KU | passive(MemGPT 類) | `Agentic_memory_*-letta` | — |
| Trivial | 非 trivial 對照 | 自寫:parametric/constant、random-among-retrieved、majority | — |

> **mem0(b) 是什麼**:mem0 + **我們的 P1 抽取(held fixed)** + mem0 **原生破壞性更新**。把抽取固定成跟 ours 一樣,**唯一差別只剩「破壞性 vs 保守寫入」** → FC 上**最乾淨的「write-time 判斷損失」展示**(native mem0 在 FC 抽取就掛,看不到 update 損失;mem0(b) 補好抽取才看得到)。
> **公平**:內部 ablation(a/b/c)固定 P1 抽取;**跨系統(ours vs Zep/LightMem/RAG…)各用自己原生抽取 + 原生 inference 模板**,raw-q ungated 一致。

---

## 2. Benchmark registry

| Benchmark | data config | 長度 | KU 子集 | 評分 | 角色 |
|---|---|---|---|---|---|
| **FC-SH** | `Conflict_Resolution/Factconsolidation_sh_{6k,32k,64k,262k}.yaml` | 6k–262k | has_pair + no_conflict | SubEM | 長度 robust + 長 context 對照 |
| **LongMemEval** | `Accurate_Retrieval/LongMemEval/Longmemeval_s.yaml` | ~128k | knowledge-update 題型 | LLM-judge | **命題乾淨戰場**(見下) |
| FC-MH / BEAM | `Factconsolidation_mh_*` / 待整合 | — | — | — | 泛化(後) |

> ⚠️ **FC 對 proactive baseline 可能是「抽取失敗」而非「KU 判斷失誤」**:native mem0 在 FC 抽取就掛(16-26%),**Zep 很可能同樣**(為對話設計、FC 是 fact-list 格式)。若如此,「贏 Zep@FC」會被讀成「Zep 不吃 FC 格式」而非證明 write-time 判斷脆弱。
> **→ 命題最乾淨的戰場是 LongMemEval**(mem0/Zep 在那能正常抽個人事實、真的做破壞性 update,誤判才顯現)。**FC 上以 mem0(b) 當乾淨 write-time-損失展示**(抽取 held fixed)。

---

## 3. 核心 evidence(論文必須證明的,依序)

### Evidence-1 — 同 model 下,ours 贏同類 baseline(KU + FC)【gate】
同一 backbone,**ours vs same-family proactive(mem0(b)、Zep)** 在 **LongMemEval KU(主)+ FC(輔)**。沒贏則後面免談。

### Evidence-2 — 「為什麼贏」的機制觀察(本作真正賣點,比 EM 更硬)
不是只報 EM,要量出機制:
- **(i) 檢索 recall**:query 所需記憶有沒有被檢索到(各方法 top-100 是否含當前正確版)。
- **(ii) 處理後 recall 對照**:經各自 pipeline 處理後,**最終留下的記憶**裡當前正確版的 recall(ours 解析後應升;破壞性 baseline 因 write-time 已刪 → 不可救)。
- **(iii) final-context 純度 → 答題**:送進答題 LLM 的最終 context 中——(a) 當前正確版在不在?(b) 舊版/過時版有沒有混入?(c) 無關噪音佔比?
  - ours:新版在、舊版被丟;mem0:新版可能已刪;**Zep:更新過的 + 未更新的多顆粒一起回 → 答題被污染**(關鍵對照)。
- **(iv) robustness 來源論述**:不只「任務簡單」,更是 **① 不可逆性消除(我們的 LLM 誤判 recoverable、下次可重判;baseline write-time 誤判永久損失)+ ② 確定性兜底(same-(S,P) 約 2/3 走純結構解析、零 LLM、且幾乎全對)** → 與 LLM 強弱部分脫鉤。

### Evidence-3 — 弱 LLM 下的 dose-response(intro 命題的決定性證據)
**能力軸**:強(gpt-4o)/ 中(gpt-4o-mini)/ 弱(Qwen2.5-7B/3B 類 frozen)× {ours, mem0(b), Zep},量 **EM 隨能力的衰退斜率**。
- 預測:write-time 流派**陡降**(弱→更多不可逆誤判);**ours 平緩**;金句 = `ours@弱 ≈ baseline@強`。
- 這是**唯一能把「弱 LLM → write-time 崩」釘成因果**的實驗 → **核心,非 spare-time**(只是排在 Evidence-1 gate 之後)。

### Evidence-4(有閒才做) — 完整性
LightMem(coupled 第二代表)、different-family(LCA✓/RAG/MemGPT)、trivial、ablation、FC-MH/BEAM、其他記憶任務(不退步)、(S,P) canonicalization、lazy-triple efficiency。

---

## 4. 執行序(現況 + 接下來)

**已完成(gpt-4o-mini,FC-SH)。數值 = `overall% / has_pair%`(兩個百分比,非題數)。**
每長度共 100 題;has_pair 題數:6k=74、32k=65、64k=66、262k=77,其餘為 no_conflict。

| 方法 \ 長度 | 6k | 32k | 64k | 262k |
|---|---|---|---|---|
| **ours** | 92 / 92 | 89 / 86 | 94 / 91 | 91 / 88 |
| (a) vanilla native | 16 / 0 | 22 / 3 | 26 / 3 | 17 / 1 |
| **(b) mem0+P1 破壞性** | — / **46** | — / **45** | ⏳ | ⏳ |
| LCA(全塞) | 88 / 88 | 74 / 71 | 65 / 55 | 42 / 31 |

> **ours has_pair% 跨長度 flat(92/86/91/88);LCA 崩(88→71→55→31);gap +4→+15→+36→+57**。
> **additive ablation(has_pair%):(a) 0/3 → (b) 46/45 → (c) ours 92/86** = 抽取補好 + 破壞性更新仍丟一半 → 保守+解析救回。mem0(b) 64k/262k 跑中。

**接下來(依序;每步先 smoke + 人工確認再放手):**

1. **(等 ours 262k OK)整理 ours 6k/32k/64k 的 L1→L2→EM 圖鏈** — 用 P1+raw-q 重算 L1/L2/L3 JSON、重繪 `make_figures.py`(F_L1_retrieved → F_L2_resolved → F4_state_to_em → F6_overall)。先把 **ours 端自洽的因果鏈**畫出來(baseline 對照面板等步驟2/3 補)。

2. **Zep + mem0 + ours 在 FC 與 LongMemEval full-haystack KU**(= Evidence-1):
   - 先讀 benchmark 的 Zep 流程(`agent.py:_handle_zep_agent`、`methods/zep.py`)+ **同時 smoke FC 與 LongMemEval**,確認 Zep 抽取進不進得去(FC 可能不吃)。
   - 進得去就跑:FC-SH 6k/32k/64k/262k + LongMemEval KU。mem0 用 (a) native + (b) held-fixed 兩種。

3. **能力軸(強/中/弱 2-3 點)× {ours, mem0(b), Zep}**(= Evidence-3)在 **FC-SH 32k + LongMemEval KU** 兩個代表點。整條 backbone 用同一 model。**這是核心,不放最後。**

4. **final-context 純度對照圖**(= Evidence-2 (iii)):對每方法 dump「送進答題 LLM 的最終 context」,量當前版在不在 / 舊版混入 / 噪音。

5. **其餘(有閒才做,= Evidence-4)**:LightMem 整合(timebox;太貴則 cite + 用 Zep 代表 decoupled 即可)、different-family/trivial、ablation(structural-only vs LLM-grouping-only、mem0+P1)、FC-MH/BEAM、其他記憶任務、(S,P) canonicalization、lazy-triple。

---

## 5. 執行機制

- **單一 FC run = `bash scripts/run_fc_sh.sh <L> <ours|vanilla>`**(per-run `RUN_OAI_KEY_NAME` 多 key 並行、隔離 store/cache/cost-log)。LCA = `run_lca_fc.sh <L>`。
- **成本/latency**:`MEM0_COST_LOG` env-gated,跑完 `summarize_cost.py` 出每階段 token/時間/估\$。stage 已細分(extract_p1/triple_p2/subject_p2b/group_p3/conflict_p5/embed/answer)。
- **M.C./Q.E. latency(Table-12 式,minor material)**:benchmark **自動記** `memory_construction_time`(M.C.)/ `query_time_len`(Q.E.)於每個 result json,方法無關 → `scripts/latency_summary.py` 出對照表。對標 MemoryAgentBench(Hu et al.)Table 12。**發現**:mem0(b) 破壞性更新 M.C. 32k 4843s = ours 2.3×、262k 估 ~12hr(coupled 不 scale);ours 以較高 Q.E.(~30s/q query-time 解析)換正確。**Zep M.C. 特例**:main.py 只記 graph.add send(~55s),真實成本是 Zep cloud server 端 async 處理(另測 ~數十分鐘)。`cost_logger` 給 M.C./Q.E. 內的 per-stage 細分(bonus)。
- **多 key 並行**:`.env` 放 `OPENAI_API_KEY_A/B/C`,各 run `RUN_OAI_KEY_NAME=OPENAI_API_KEY_X`。
- **錯誤模式診斷**:`scripts/diag_fc_errormodes.py <L>`(D1 檢索 + D2 (S,P)配對 + D2b 解析 + D3 歸因 + benchmark-error 偵測)。
- 每 run 完:更新 `experiment_results.md` §1 + 重繪 figures。
