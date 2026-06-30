# mem0 on FC — 當前正確設定、I/O 路徑、結果（single source of truth）

> **用途**:這份是**乾淨、當前正確**的單一真相來源。`00_research_axis_and_setup.md` 是逐步 log（內容多、含過程修正），分析請以**本檔**為準。
> **建立**:2026-06-04　**狀態**:FC-SH/MH × 6k/32k 四組已用下列設定跑完。
> **⚠️ 注意 stale 資料**:`analysis/results/{mh,sh}_512_mquake_analysis.json` 的 `error_type` / `model_output` 是**舊 HippoRAG run** 的欄位,**不可用於本 mem0 run 的歸因**;只可用其 `gt_seq/old_seq/gt_fact_text/old_fact_text/conflict_type`。模型答案一律取本 run 的 `results.output` / retrieval `response`。

---

## 1. 與 MABench mem0 預設的差異（只列改動）

| 項目 | MABench/mem0 預設 | 我們的設定 | 理由 |
|---|---|---|---|
| **Backbone LLM** | gpt-4o-mini | **gemini-3.1-flash-lite**(Vertex ADC,內部+答題同一顆) | Plan A 對齊 |
| **Embedder** | OpenAI text-embedding-3-small | **Vertex text-embedding-004**(768d) | 配合 Vertex/ADC |
| **temperature** | top-level 0.7 / mem0 內部 0.1 | **全 0**(deterministic 單 trial) | 失敗歸因要可重現 |
| **chunk_size** | 4096 | **512** | extraction recall + 逐 chunk 可分析 |
| **Chunker** | nltk 句子切(`chunk_text_into_sentences`) | **fact-aware(`chunk_facts_by_line`)** | 句子切會把序號與內文切到不同 chunk |
| **Extraction prompt** | `FACT_RETRIEVAL_PROMPT`(個人助理,拒收通用知識) | **L2 knowledge-extraction**(`make_l2_knowledge_prompt`)+ **frozen cache** | 預設對 FC 通用知識大量回空;L2 補全;cache 讓 SH/MH 逐字一致 |
| **記憶模式** | — | **vector**(無 graph/Neo4j) | 單純化 |
| **Inference 遞送** | OpenAI native system role(system/user 分開 message) | Gemini **無 system role → `system+"\n\n"+user` 串成單一字串** | 換 backbone 的必然(待 disclose) |

> **inference prompt 內容與原始逐字對齊**:`system_prompt`("You are a helpful AI...")與 user(FC query 模板)都與 [MemoryAgentBench_original/agent.py:582-592](../../../MemoryAgentBench_original/agent.py) **完全相同**,非我們改動。
> **序號規則屬原始 benchmark**:mem0 的 query 走 rag_agent 模板(agent_name 經 normalize→rag_agent),該 FC 模板**內含「用較大序號解衝突」**——原始 MABench 跑 mem0(GPT)時就有。而「記憶無序號 vs 模板用序號」的矛盾**也是原始內建**(mem0 本來就剝序號)。我們**繼承,非製造**。
> 序號:extraction 剝除序號(對 mem0 公平,recency 靠 ingestion 順序)。

---

## 2. 完整 pipeline

```
INGESTION (per chunk = 一次 memory.add())
  1. Extraction:  L2 prompt 從 chunk 抽 new facts（剝序號，完整）
                  → 經 frozen cache 命中（SH/MH/重跑 抽取逐字一致）
  2. Candidate:   每個 new fact 取 cosine top-5 既有記憶（去重成候選池）
  3. Update:      所有 new fact + 整個候選池 一次給 DEFAULT_UPDATE_MEMORY_PROMPT
                  → 每個 new fact 判 ADD/NONE；對候選池既有記憶判 UPDATE/DELETE/NONE
QUERY (per query)
  4. Retrieval:   query → cosine top-100 既有記憶
  5. Inference:   送進 Gemini 的是「system + '\n\n' + user」串成的單一字串
                  (Gemini 無 native system role; agent.py:_answer_with_client)
                  system = "You are a helpful AI. Answer based on query and memories.\n"+memories(無序號)
                  user   = FC 模板(含「用較大序號解衝突」規則，但記憶無序號) + "Current Time:..."
                  text = resp.text or ''   ← Gemini 無有效 text(block)時回空字串
```

**實際單一字串樣貌**(traced,agent.py:954-959 + 507-530):
```
You are a helpful AI. Answer the question based on query and memories.
- <memory 1（無序號）>
- ... (top-100)

Pretend you are a knowledge management system. Each fact ... provided with a serial
number ... newer fact has larger serial number ... solve conflicts by finding the
newest fact with larger serial number ... answer **only** from the knowledge pool ...
Now Answer the Question: ... <question>
Answer:

Current Time: ...
```

---

## 3. I/O 路徑（四組 {SH,MH}×{6k,32k}）

**Agent configs**（重用 yaml,SH/MH 由 dataset config 決定）:
- 6k: `configs/agent_conf/RAG_Agents/Gemini/Structure_rag_mem0_gemini-3.1-flash-lite_chunk512_temp0_factaware_l2.yaml`
- 32k: `..._factaware_l2_32k.yaml`
- Dataset: `configs/data_conf/Conflict_Resolution/Factconsolidation_{sh,mh}_{6k,32k}.yaml`

**核心程式**:
- L2 prompt + L1: [methods/mem0_fc_prompt_fix.py](../../methods/mem0_fc_prompt_fix.py)（agent.py:445/456 套用）
- Instrumentation + cache: [mem0/memory/main.py](../../mem0/memory/main.py)（extraction 段 cache + 三層 log,env 控）
- fact-aware chunker: [utils/eval_other_utils.py `chunk_facts_by_line`](../../utils/eval_other_utils.py#L229)（conversation_creator 對 factconsolidation 路由）

**Frozen extraction cache**（每 context 一份,SH/MH 共用）:
- `analysis/results/extraction_cache_6k.json`（455 facts）/ `extraction_cache_32k.json`（2310 facts）

**執行**（env 開 cache + 三層 log）:
```bash
export MEM0_EXTRACTION_CACHE=analysis/results/extraction_cache_<L>.json
export MEM0_CAND_LOG_DIR=docs/0603_current_research_main_evidence/logs/<task>_<L>_l2
python main.py --agent_config <l2 yaml> --dataset_config <dataset yaml>
```
（launcher: `scripts/run_l2_remaining.sh`；6k 驗證 run 另跑）

**中途輸出（write-time 三層 log）**:`docs/0603_current_research_main_evidence/logs/{mh,sh}_{6k,32k}_l2/`
- `extraction.jsonl`（Component 1:抽取 facts）
- `candidate_pool.jsonl`（Component 2:每 new fact top-5 + score）
- `update_decision.jsonl`（Component 3:update prompt + raw + parsed + hallucinated_ids）

**最終輸出**:
- Layer A（applied events）: `outputs/rag_retrieved/<agent_name>/k_100/factconsolidation_<task>_<L>/chunksize_512/ingestion_context_0.jsonl`
- Retrieval（per query）: 同目錄 `query_<qid>_context_0.json`（retrieved_memories / system_prompt / response）
- Results（EM 等）: `outputs/gemini-3.1-flash-lite-mem0-chunk512-temp0-factaware-l2{,-32k}/Conflict_Resolution/factconsolidation_<task>_<L>_*results.json`

**GT**:
- per-query hop: `analysis/results/{mh,sh}_512_mquake_analysis.json`（6k；32k 用 `mh_32k_mquake_analysis.json`，僅取 seq/text/conflict_type）
- 全 in-store 衝突對: `analysis/results/mh_{6k,32k}_FULLPAIRS_gt.json`（6k=161 對 / 32k=837 對）

**分析腳本**（`docs/0603_current_research_main_evidence/scripts/`）:
- `build_extraction_cache.py`（建 cache）、`map_context_to_mquake.py`（context 衝突/單一組成）、`build_full_pairs_gt.py`
- `awt_writetime_audit.py`（衝突對 resolved/H1/H2/same-chunk）、`full_writetime_accounting.py`、`audit_deviation.py`（role×fate）
- `query_pipeline_analysis.py`、`sh_query_conditional.py`（依 ingestion 結果分組）、`detail_cases.py`

---

## 4. 結果

### 4.1 EM matrix（L2 + frozen cache,extraction 100%）
| | 6k | 32k | 64k |
|---|---|---|---|
| MH | 64% | 39% | （未跑）|
| **SH** | **92%** | **90%** | **94%**⚠️ |
- SH 對 ctx 穩健;MH −25pp 是**多跳 retrieval** confound(非衝突解決)。
- ⚠️ **64k SH 94% 不可直接與 6k/32k 比**:64k 用 **minimal thinking + `generation_max_length=256`**(無截斷空輸出),6k/32k 用 High thinking + max_len=10(有空輸出壓低 EM)。64k **真實規則正確率 96%**(+qid18/20 benchmark 答案鍵瑕疵、mem0 其實答對);真 mem0 失敗只 4 題。詳 [04](04_fc_sh_64k_failure_deepdive.md)。

### 4.2 Write-time（6k,fact-fate canonical,455 筆）
- 組成: 161 衝突對(322)+ 133 non-pair。16 same-chunk + 145 cross-chunk。
- 最終命運: **STORED 296 / SUPERSEDED 144 / DROPPED 13 / DELETED 2**(ideal 310/145/0/0)。
- same-chunk ≠ both-ADD:mem0 同 chunk 內去重,16 對 = 6 both-ADD + 6 留世界丟反事實 + 4 留反事實。
- 偏差 15 筆(DROPPED 13 + DELETED 2);詳 role×fate 表見 00 log。

### 4.3 FC-SH 6k 全 100 題完整分類（`classify_sh_all.py`,用真實 results.output）
| 類別 | n | 說明 |
|---|---|---|
| ✅ clean-resolved | **64** | has_pair,衝突解決,只剩新版(old: 61 SUPERSEDED + 3 DROPPED 全消失),答新 |
| ✅ single-fact | **25** | no_pair,本來就單一事實,與衝突無關 |
| ✅ STALE-correct | **3** | 新舊都在卻答對(脆弱,見下) |
| ❌ write-time DROPPED | **4** | 反事實在 ingestion 被丟→只剩舊→答舊(qid7=cross/34/42/52=same) |
| ❌ 空輸出(gemini block) | **3** | qid66/89/97,§5 |
| ❌ 幻覺 | **1** | qid1 'Vito Corleone' |

- **92 成功 = 64 clean-resolved + 25 single-fact + 3 STALE-correct**。前 89 = 「只剩新版 or 單一事實」(衝突真正解決 or 無衝突);3 STALE 是例外。
- **STALE-correct(qid12/31/57)= 脆弱成功**:新舊兩版都在 DB、都被檢索(retrieved[0]舊/[1]新),模型卻選了**明顯反現實的反事實**(Elvis 娶 Charles the Bold 等)。**機制假設(n=3)**:prompt 指令「answer only from knowledge pool **rather than the real facts in real world**」在無序號可用時把模型推向「非現實」的反事實。→ **這 3 題 write-time 其實沒解決(both present),靠 prompt 反現實指令湊巧答對**,非穩健成功。
- **真正穩健的衝突解決成功 = 64**(write-time 把舊版消除);3 STALE + 4 DROPPED = 7 是 write-time 沒處理好(74 has_pair 中 7 個);另 3 has_pair 是 generation artifact(write-time 其實正確)。

### 4.4 ★ 6k → 32k scaling 對照（write-time 是乾淨對照,query-independent）
> ⚠️ FC-SH/MH **queries 隨長度不同**(6k qid0 答案 pesäpallo,32k=basketball)。write-time 分析用 `*_FULLPAIRS_gt`(從 MQuAKE-CF 枚舉全部 in-store 對,與 query 無關)故可直接比;query 分析須各自用 run 的 queries 建 GT(`build_sh_gt_for_run.py`)。

**Write-time 衝突解決(全 in-store 對)**:
| | 6k(161 對,detect 145)| 32k(837 對,detect 824)| 64k(1691 對,detect 1678)|
|---|---|---|---|
| thinking 設定 | High | High | **minimal**⚠️ |
| resolved | 98.6% | **93.1%** | **95.6%**⚠️ |
| **H1-miss(舊版擠出 top-5)** | 0.7%(1)| 3.5%(29)| **3.2%(53)** |
| **H2-refuse(拒絕覆蓋)** | 0.7%(1)| 3.4%(28)| **1.3%(21)**⚠️ |
| same-chunk | 16(占 10%)| 13(占 1.6%)| 13(占 0.8%)|

- **🔑 使用者假設證實(跨設定穩健)**:**H1-miss 絕對數 1→29→53 單調上升**(純 embedding 檢索,不受 thinking 影響)→「池過大」crowd-out 隨 scale 惡化,**這是最乾淨的 scale 證據**。
- **⚠️ confound — resolved/H2-refuse 暫不可比**:64k resolved 95.6% **>** 32k 93.1%(非單調回升)。成因是 **minimal thinking 削弱 H2-refuse**(3.4%→1.3%;High thinking 更會推理世界事實而拒寫反事實)→ 推高 resolved。**非「池更大反而更好」**。→ **必做:6k/32k 用 minimal 重跑**,才能宣稱 resolved 單調惡化。詳 [04](04_fc_sh_64k_failure_deepdive.md) §E。
- **🔑 失敗主因 SHIFT**:6k 主因 = same-chunk(A1);**32k/64k 主因 = H1-miss**(non-same-chunk);same-chunk 占比隨 scale 降(10%→1.6%→0.8%,版本更分散)。

**FC-SH query 失敗(各自 run GT)**:
| | 6k(EM 92%)| 32k(EM 90%)| 64k(EM 94%)|
|---|---|---|---|
| 真衝突解決失敗 | 4(write-time 丟反事實:A1/A3)| 3 A4 over-fire(qid87/95/98)| **1 A4**(qid32,MLK died-in-city 被 citizen-of 覆蓋)|
| 真單一事實毀損(無衝突)| — | — | **3**:qid77(A4)/qid87(近重複碰撞)/qid76(大池漏 ADD omission)|
| benchmark 答案鍵瑕疵(非 mem0)| — | 2(qid8/9)| **2(qid18/20)**,mem0 輸出大序號 rule-correct,剔除 |
| 模型生成 artifact | 3 空輸出 + 1 cross-fact | 3 空輸出 + 2 cross-fact | **0**(max_len=256 已消除空輸出)|
- 32k benchmark-defect 是 qid8/9;**64k 是 qid18/20**(query 隨長度不同;`sh_full_classify.py` 預設 `--benchmark-defect 8,9` 對 64k 須改 18,20)。
- **🔑 64k 新發現**:真失敗 4 題中 **3 題是無衝突的單一事實**(qid76/77/87)→ 結構失敗**不限衝突解決**,只要候選池混入同實體異關係 / 近重複反事實就毀正確記憶。qid76 揭露 **omission 新子模式**(n_cand=156,update LLM 直接漏輸出 new fact)。詳 [04](04_fc_sh_64k_failure_deepdive.md)。
- SH-query 端失敗數小(64k 4/100),**write-time 端(1678 對)才是乾淨 scaling 證據**;主張力量在機制純度(每個 query 失敗都能 component 定位),非 query EM 量級。

### 4.3a★ same-chunk 衝突失敗的精確機制（為何反事實沒了）
LLM 對「同 chunk 兩個衝突新 fact」**行為不一致**(3 種,實查 update_decision):
| 例 | LLM 決策 | 反事實命運 |
|---|---|---|
| Hines Ward(qid42) | **UPDATE** cornerback 覆蓋 wide receiver(想正確解!),但 id='36' 是空池(n_candidates=0)的 **hallucinated id** | apply loop 丟棄 → DROPPED |
| Christianity(qid34) | 只 ADD Jerusalem,**完全不輸出 Taipei**(去重) | NONE/省略 → DROPPED |
| Robert Parish(qid12) | 兩版都 ADD | STALE |
- **根因 = mem0 架構**:update 只能 UPDATE「已寫入 store 的候選」(候選池=先前 chunk);同 chunk 新 fact 無合法 id,LLM 想 UPDATE 它只能瞎掰 id → 被丟。**update prompt 沒設計「新 vs 新」衝突**。LLM 的解衝突**意圖常是對的**(Hines Ward 想 UPDATE),敗在架構不是判斷。

### 4.3b FC-SH 6k 衝突解決失敗（8 個,真實 L2 輸出）
> 4 個 CORRECT-ingestion 失敗的精確成因(實查):
> - **qid66/89/97 空輸出**:gemini block(`resp.text or ''`,completion_tokens>0),待 finish_reason。
> - **qid1 'Vito Corleone' = cross-fact 混淆**(非參數覆蓋、非隨機):retrieved[0]=正解`Watsuki famous for The Fairly OddParents`,retrieved[10]=`Vito Corleone was created by Watsuki`;模型抓了另一條共用主詞 Watsuki 的 fact 的 object。用了記憶但讀錯 fact。
| 失敗 | n | 機制 | 階段 |
|---|---|---|---|
| **write-time DROPPED** | **4** | 反事實在 ingestion 被丟(同-chunk 去重 ×3 + cross-chunk NONE ×1)→ 只剩舊世界事實 → 答舊(qid7/34/42/52) | ingestion |
| 模型生成 artifact | 4 | **空輸出 ×3**(qid66/89/97,gemini 生成層,非 prompt 設計、非 H2)+ **幻覺 ×1**(qid1 'Vito Corleone') | inference |
- CORRECT-ingestion 93 = 67 has_pair(衝突成功解決)+ 26 no_pair(單一事實)。檢索 93/93 取回、0 洩漏。
- STALE 3(新舊都在):全答對,模型選了後列的新版。
- **衝突解決可歸因失敗 = 4(全是 write-time 丟反事實)**;另 4 為模型生成問題,與衝突解決無關。

---

## 5. 已知問題 / 待確認
- **序號不匹配(原始 benchmark 內建)**:FC user 模板含「用較大序號解衝突」,但 mem0 記憶無序號 → 規則對 mem0 inert;STALE 衝突時模型無序號可用只能猜。**此矛盾原始 MABench 就有(非我們製造)**,但屬 mem0 在此 benchmark 的設計缺陷,值得在論文點出。
- **system-role 遞送 deviation**:原始 OpenAI 用 native system role,我們 Gemini 串接 system+user。內容對齊,遞送方式因 backbone 不同 → disclose;若要更嚴格可測「分開 vs 串接」對 EM 的影響。
- **空輸出 = `generation_max_length=10` 截斷 artifact(2026-06-05 32k controlled re-trial 更正)**:精準重放 stored prompt — **同設定 max_tokens=10 下 qid7/33/51 確定性空(3/3,finish=MAX_TOKENS,thought_tok=0)**;放大 max_tokens=2048 → **三題全答出完全正確答案**(STOP)。→ 根因是 **benchmark 答題上限 10 token 對 gemini-3.1-flash-lite 太小**(較長答案回空),**非 thinking 隨機**(thought_tok=0、確定性)。所有方法共用此 config → 跨方法比較公平、絕對 EM 被壓低;**真實 EM 天花板 32k SH=93%**。空輸出非真失敗。腳本 retrial_empty_outputs.py;[03](03_fc_sh_32k_failure_deepdive.md) §D.2。(註:先前「thinking 非確定」解釋已被此 controlled 實驗修正;見 [[project_gemini3_thinking_determinism]]。)
- **EM 雜訊**:上述空輸出/幻覺使 nominal EM 低估衝突解決能力。
