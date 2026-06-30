# 實驗結果(主檔)

> **只記「目前定版設定」下實際跑的結果 + 每個 run 的錯誤模式總結。**
> 設定 = **P1 統一抽取 + 保守寫入 +(S,P)結構 + LLM 分群 + conflict-type 分類 + temporal resolution + raw-question 檢索 + batch embedding**。
> 舊的 L2-based / pre-raw-question 數字已移除(保留於 `previous_record/`)。
> roadmap / method registry / benchmark registry → **`experiment_plan.md`**;pipeline 與 prompt → `method_pipeline_and_prompts.md`;公平性/工程 → `methodology_materials.md` §10;定位 → `ku_taxonomy_and_scope_zh.md`。

---

## 0. 一句話結論

**KU 是 query-time 問題,不是 write-time commitment。** 寫入只做保守、無破壞性的「保留全版本」;誰是權威由查詢時**確定性 temporal argmax** 決定,LLM 全程不挑 recency。首個定版設定結果(FC-SH 32k):overall EM **89%**、衝突題 has_pair **86%**(前一版 L2+wrapped 為 84% / 78%)。

---

## 1. 實際結果(定版設定)

### 1.1 FC-SH 全矩陣 — 詳細題數(gpt-4o-mini)

> 每長度共 **100 題** = has_pair(衝突題)+ no_conflict。數值為 **答對/題數**。
> 方法:**ours**(P1+保守+query-time)/ **(a)vanilla**(native 抽取+破壞性)/ **(b)mem0+P1**(P1 抽取 held-fixed + 破壞性更新)/ **LCA**(全塞、無記憶模組)。
> has_pair 題數:6k=74、32k=65、64k=66、262k=77。

**has_pair(KU 核心子集)— 答對/題數:**
| 長度 | (a)vanilla | (b)mem0+P1 | **ours** | LCA |
|---|---|---|---|---|
| 6k | 0/74 | 34/74 | **68/74** | 65/74 |
| 32k | 2/65 | 29/65 | **56/65** | 46/65 |
| 64k | 2/66 | 27/66 | **60/66** | 36/66 |
| 262k | 1/77 | ⚠ | **68/77** | 24/77 |

**no_conflict — 答對/題數:**
| 長度 | (a)vanilla | (b)mem0+P1 | **ours** | LCA |
|---|---|---|---|---|
| 6k | 16/26 | 17/26 | **24/26** | 23/26 |
| 32k | 20/35 | 32/35 | **33/35** | 28/35 |
| 64k | 24/34 | 31/34 | **34/34** | 29/34 |
| 262k | 16/23 | ⚠ | **23/23** | 18/23 |

**overall — 答對/100:**
| 長度 | (a)vanilla | (b)mem0+P1 | **ours** | LCA |
|---|---|---|---|---|
| 6k | 16 | 51 | **92** | 88 |
| 32k | 22 | 61 | **89** | 74 |
| 64k | 26 | 58 | **94** | 65 |
| 262k | 17 | ⚠ | **91** | 42 |

**讀法(has_pair%):**
- **ours flat、robust**:92/86/91/88%,跨 6k→262k(40× context、18324 facts)不掉。
- **LCA 隨長度崩**:88→71→55→31%(視窗塞不下、找不到最大 serial);**ours−LCA gap +4→+15→+36→+57** = killer narrative。
- **additive ablation**:(a) 0/3% → **(b) 46/45%** → (c) ours 92/86%:抽取補好讓 has_pair 從 0 升到 ~46(把事實存進 store),但 **mem0 破壞性更新仍丟掉約一半衝突**;保守保留全版本 + query-time 解析把剩下那半救回。
- vanilla(a)全程 ~0-3% has_pair(native 抽取在 FC 幾乎存不到事實)。
- ours 對照前一版(L2+wrapped):overall 64k 65→94、has_pair 62→91(raw-q 解掉 64k 的 wrapped-q 檢索瓶頸)。

**跨系統 baseline — Zep(proactive·decoupled;同 runner `run_zep_query_only.py`:bare-raw-q、native k=10、多顆粒 edges+nodes+episodes+context_block、SubEM):**
| | 6k | 32k | 64k | 262k |
|---|---|---|---|---|
| has_pair | 50/74=**68** | 36/65=**55** | 44/66=**67** | ⚠ prohibitive |
| overall | 76 | 69 | 78 | ⚠ |
- **機制**:Zep 的 fact-level KU(`invalid_at` edge)鮮少作動;它在 64k 贏破壞性 mem0(b)(67 vs 41)主要靠**保留 raw episodes**(64k graph **130 episodes 全收齊**、edge-recall 僅 13/15)→ 舊值常仍在 → answer-LLM 從 episodes 撈到最新。**這正是「多顆粒度」會稀釋 KU 機制歸因之處**(E5 待分析)。has_pair 非單調 68→55→67(64k 多 episodes 回升,真實一致測量)。
- **write-time**:262k cloud-proc prohibitive(送完 1hr 後 GT edge-recall 仍 1/15);詳 §1.4。
- ours 全程仍明顯領先(64k 91 vs Zep 67)。

### 1.2 錯誤模式總結 — ours FC-SH 6k/32k/64k

> 來源:從 run 存的 per-query 檢索/解析 JSON 直接歸因 + 核對 HF 原文 serial。**三長度一致、無致命問題。** 腳本:`scripts/diag_fc_errormodes.py`。

| 長度 | has_pair EM | D1 檢索可救率 | (S,P) same_sp | benchmark 標註錯(排除) | 真 method 錯 | winnable has_pair |
|---|---|---|---|---|---|---|
| 6k | 92% | **100%** | 66% | 0 | 6(全 old_not_dropped) | 92% |
| 32k | 86% | 98% | 66% | 2(q8/q9) | 7(5 分群 + 2 answer) | 89% |
| 64k | 91% | 95% | 68% | 1(q20) | 5(1 分群 + 4 answer) | 92% |

**答錯題的歸因(檢索造成 vs method 造成):**
| 長度 | 總錯 | benchmark 標註錯(排除) | **檢索造成**(GT_new∉top100) | **method 造成**(GT_new 有檢索到卻錯) |
|---|---|---|---|---|
| 6k | 6 | 0 | **0** | 6 = 6 old_not_dropped |
| 32k | 9 | 2 | **0** | 7 = 5 old_not_dropped + 2 answer-LLM |
| 64k | 6 | 1 | **0** | 5 = 1 old_not_dropped + 4 answer-LLM |

> **三長度「檢索造成答錯」都 = 0**:每題答錯時 GT_new 都已在 top-100,錯在下游。method 錯只有兩種:**`old_not_dropped`**(GT 兩版都檢索到,但 (S,P) 未 canonicalize → 沒分到同群 → 沒丟舊 → context 留新舊兩版混淆答題;6k/32k 主因)、**`answer-LLM`**(context 已乾淨仍答錯,backbone 能力,長 context 下變多)。

**跨長度模式(穩定):**
- **① retrieval(D1)很強、且不造成任何答錯**:可救率 100→98→95%(嚴格 substring 比對;at-scale 微降但**無一題因檢索而錯**)。raw-q 下 retrieval **不是瓶頸**。
- **② (S,P) 配對穩定 ~66-68% same_sp**,即 **~1/3 的 GT 配對因 predicate/subject 未 canonicalize 而 (S,P) key 不同**(`is associated with` vs `...the sport of`、主詞抽取不一致、缺 triple),只能靠 LLM grouping。
- **③ 主要 method 錯 = (S,P) 分群失敗 → old_not_dropped**(6k 6/6、32k 5/7);**64k 改以 answer-LLM 為主**(4/5,長 context 下 context 乾淨仍答錯)。
- **④ benchmark 標註錯**:0/2/1 題(gold=較小 serial、違反 FC 規則 → 不可贏),孤立、排除。
- **temporal key 正確**:HF 原文核對 FC 池**按 serial 排序**、chunk-ordinal 正確對應 recency,無 inversion。
- **排除 benchmark 錯後 winnable has_pair = 92/89/92%。**

**Backlog(方法階段性定版,不在本輪改):**
- **(S,P) canonicalization = 唯一主要 lever**(predicate 去尾綴/正規化、subject canonicalize,或強化 LLM grouping 接同義述詞)。
- **lazy-triple**(見 `method_pipeline_and_prompts.md` §4.3):D1 顯示 retrieval 95-100% 可救 → write-time (S,P) 結構**非為 retrieval 必要** → triple 可移到 query-time 只對 top-100 抽 → 砍掉寫入端 ~68% latency。**待 262k 檢索確認**後定。

### 1.3 262k / LongMemEval KU — 待補(各做相同錯誤模式總結)
LongMemEval KU 待跑。完成後在此各加一節。

### 1.4 Latency material(Table-12 式:M.C. = Memory Construction / Q.E. = Query Execution)

> 對標 MemoryAgentBench(Hu et al.)Table 12。M.C.=`memory_construction_time`、Q.E.=`query_time_len`,benchmark **每個 result json 自動記、方法無關**。腳本 `scripts/latency_summary.py`。
> **Provenance**:**✓ 實測**(完整跑完已記錄)/ **🔄 跑中**(會實測)/ **\* 估算**(從 per-chunk 速率外推,如 Table 12 的 *)/ **⚠ 未記錄**(待重跑)。

**Memory Construction(M.C.)總時間(gpt-4o-mini):**
| 方法 | 6k | 32k | 64k | 262k |
|---|---|---|---|---|
| **ours** | 476s ✓ | 2102s ✓ | 4208s ✓ | **17041s ≈ 4.7hr ✓** |
| (a)vanilla(native) | 22s ✓ | 124s ✓ | 242s ✓ | **1058s ≈ 17.6min ✓ ⚠抽≈0條才這麼快** |
| **(b)mem0+P1(破壞性)** | 569s ✓ | **4843s ✓** | **8610s ≈ 2.39hr ✓**(=ours 2.05×) | **≈13hr \***(殺於 53/531@92s/chunk;per-chunk 隨 store 增長 → **下界**) |
| LCA(全塞) | 0 ✓ | 0 ✓ | 0 ✓ | 0 ✓(無 M.C.) |
| Zep | send 55s ✓ + cloud-proc 慢 | send + cloud-proc | **cloud-proc ~70-90min \***(48min 後 GT 6/15) | **cloud-proc 數小時 \***(47min 後 0/15) |

**Query Execution(Q.E.)每題秒數:** ours ~27–36s/q(query-time grouping+conflict-type)✓;vanilla/mem0(b) ~1.3–2.4s/q ✓;LCA 1–4.7s/q ✓。

**latency 發現(對我們有利):**
1. **mem0 的 coupled 破壞性更新 = 昂貴 M.C.,且隨 store 膨脹**:32k **4843s=ours 2.3×**、64k **8610s=ours 2.05×**(均實測);262k **估 ≈13hr**(實際更久)。→ write-time 請 LLM 判斷舊事實的成本隨 store 增長。
2. **vanilla「做得完」262k 是抽取失敗的症狀**:M.C. 僅 17.6min **因為 native 幾乎沒抽到 fact**(store 近空 → 無破壞性更新成本)→ 報告 vanilla「快」時**必須標注此 caveat**。
3. **ours 用較高 Q.E.(~30s/q)+ 線性 M.C.** 換正確性 → 量化 intro 的「硬體儲存 + query-time latency 換正確記憶」。triple 抽取是 M.C. 主成本(lazy-triple 可砍)。
4. **Zep M.C. 特例 + 實測很慢**:main.py 只記 graph.add send(64k ~55s);真實成本是 **Zep cloud server 端 async 處理**——**64k 送完 48min 後 GT 僅 6/15、262k 47min 後 0/15** → 64k ~70-90min、**262k 數小時**。
5. **★ headline:兩個 proactive baseline(mem0 coupled、Zep decoupled)在 262k 的 write-time 都 prohibitive**(mem0(b) 估 ~13hr、Zep 數小時),而 **ours 262k M.C. 4.7hr 實測跑完** → **「保守寫入」不只更安全(不可逆性),寫入成本也比 proactive 破壞性/圖建構更可行**。

> **待重跑/補測(⚠)**:mem0(b) 262k(實測值,因 ~13hr 暫以估算代)、Zep 各長度的 cloud-processing M.C.(poll 量測中)。

---

## 2. Baseline 對照框架(三層,證明不是 trivial / 不是只在 niche 贏)

| 層 | 用意 | 我們的具體對象 |
|---|---|---|
| **Same family**(同取徑代表作) | 證明比**同類 KU 記憶法**強 | **mem0**(proactive·coupled,= 我們 (a) 真 vanilla)、**Zep**(proactive·decoupled,最接近我們)、**LightMem**(coupled) |
| **Different family**(不同取徑代表作) | 證明不是只在 niche 領先 | **Long-context LLM**(全塞,無記憶模組)、**RAG**(BM25 / dense top-k,passive)、**passive memory**(MemGPT/letta、A-Mem:存但不解 KU) |
| **Trivial baseline** | 證明問題非 trivial | **parametric/constant**(忽略記憶、用 LLM 世界知識答 ≈ 真 vanilla-native:FC has_pair 0%,反事實猜不到)、**random-among-retrieved**(同 (S,P) 隨機挑值)、**majority/most-frequent value** |

- **公平規則**:跨系統(same/different family)各用**自己原生抽取 + 原生 inference 模板**,raw-question 檢索 ungated 一致(zep 本就如此)。內部 ablation(a/b/c)固定 P1 抽取。詳 experiment_plan.md。

---

## 3. 關鍵設計決議(濃縮)

### 3.1 query-time 解析:3-way conflict-type classifier(取代 per-predicate arity guard)
走過的彎路:per-predicate「multi-valued arity guard」修好 LongMemEval 誤丟、卻**回測 FC 崩**(arity 是 context-dependent、非述詞絕對屬性)。**現行解**:per-group、query-aware 的 3-way 分類(Cattan et al. 2025)`{NO_CONFLICT, FRESHNESS, COMPLEMENTARY}`,看該組 values±query;`phase2_resolve` **只在 FRESHNESS 丟舊**,其餘全留(precision-safe)。FC-SH 32k 上 95.5% 判 freshness(健康)。

### 3.2 檢索:raw-question(FC「retrieval 瓶頸」是 wrapped-query artifact,已修)
benchmark 拿「qa 模板包裝後整段 query」(~800 字指令樣板)做 embedding → 樣板主導、稀釋真問題 → GT 掉出 top-100。修法:`agent.py: _retrieval_query()` 剝模板、只 embed raw question(inference 仍餵完整 wrapped)。FC-SH has_pair 可救率 wrapped 87% → raw **98%**。ungated(vanilla 同套用)、zep 本就如此 → pipeline 對齊、論文揭露。

### 3.3 工程:batch embedding(只快、結果不變)
寫入端逐 fact 一次 API → 改 `embed_batch`(一次 ≤2048)。非 bit-identical(OpenAI bf16,逐筆重跑本就有 1.22e-4 抖動),但 batch vs 逐筆同級、cosine 0.9999995 → 排序零影響。

### 3.4 Temporal key = ordinal(ingestion 序)
LongMemEval(sessions 依時間序餵入)→ ingestion 序 = recency。**FC 經核對亦正確**:知識池按 serial 排序、serial 隨文件位置遞增 → chunk-ordinal 正確對應 recency(無 inversion;63/65 has_pair gold = 較大 serial)。q8/q9 是 benchmark gold 違反自己規則的標註錯誤(§1.2-B),非我方問題。

---

## 4. Narrative arc ↔ figures(扣合 intro;**figures 待用定版 data 重繪**)

intro(`intro_zh_revised_v2.md`)論證三步 ↔ metric / figure:

| intro 主張 | metric | figure(`figures/`) |
|---|---|---|
| ① 破壞性寫入 + 弱模型 → 不可逆損失 | vanilla store 縮水;has_pair 新版在 L1 已 old_only/neither(不可救) | F1_store_shrinkage、F2_has_pair_retrieval |
| ② 保守寫入 → 保留全版本 → recoverable | ours has_pair L1 = both/new_only;vanilla 卡 old_only/neither | **F_L1L2_haspair_compare(核心圖)** |
| ③ query-time deterministic 解析 | both→new_only clean_rate;final-state→EM | F3_resolution_clean_rate、F4_state_to_em |
| 總體 payoff | overall EM,baseline vs ours,跨長度 | **F6_overall_em** |

**⚠️ 現行 figures 過時,待重繪(`make_figures.py`)**:(1) 用舊 L2 抽取 + wrapped-q;(2) 圖內 "vanilla" 定義要統一為 a/b/c;(3) 用定版 P1+raw-q 的 L1/L2/L3 重算。**預期**:raw-q 後 ours 可救率各長度回 ~100%,vanilla 仍卡 old_only/neither → 「可逆 vs 不可逆」對比更乾淨。

---

## 附:重現

```bash
# ours 全量 FC-SH 32k(定版設定;fresh p1_ caches / 隔離 unified store / phase0+phase2 / raw-q / batch-emb)
bash docs/0615_intro_framework_after_problem_statement/scripts/run_full_p1_sh_32k.sh
# 完整 roadmap / 各 run 設定 → experiment_plan.md
```

---

## 2. LongMemEval KU(官方資料 + 官方 judge)— 廣度泛化

> **動機**:LongMemEval 的 `knowledge-update` 才是記憶方法真正的 KU 對象文本(每題 haystack 40 sessions ~115k,**舊值 session + 更新 session 都在**,系統須答最新)。MemoryAgentBench 的 longmemeval 打包未保留此結構 → 改用**官方 `origin_longmemeval/` 程式碼 + `longmemeval_s_cleaned.json`**(KU=78 題)。
> **Bridge**(`run_longmemeval_ku.py`):官方 haystack → 我們的 mem0 pipeline → hyp jsonl → 官方 `evaluate_qa.py`(KU 專屬 judge 模板)。session-level ingestion(每 session 一 memorize,帶真實日期;haystack 已 time-sorted → ordinal=recency);per-question user_id 隔離;4-key sharding(B/C/D/E)~2.4hr。
> **Judge**:驗證期 **gpt-4o-mini**(成本);**paper-final 用官方 gpt-4o** 重跑。

### 2.1 主結果(judge=gpt-4o-mini)
| 方法 | KU EM(全 78) | 非-abs(72) | abs(6) | 備註 |
|---|---|---|---|---|
| **ours**(保守+query-time) | **65/78 = 83.3%** | 61/72=85% | 4/6 | ✓ 實測 |
| mem0(b)(破壞性) | ⏳ | | | full 跑中/待 |
| vanilla(native) | ⏳ | | | 待 |
| Zep(多顆粒·temporal) | ⏳ | | | bridge 整合中(真實 created_at) |

- **smoke(2 題)已驗證方法分化**:ours 2/2、b 2/2(n 太小)、vanilla **0/2**(答 stale 舊值 27:12 / Three)。
- **ours 13 個錯 → 兩種失敗模式(看 per-query 解析 context 歸因)**:
  - **Mode B(問題要「歷史/舊值」,被 freshness 解析丟掉)≈7/13 — 已用 oracle evidence 驗證非標註錯,真為設計如此**,再分兩子類:
    - **B1 純舊值**(答案=被取代的舊版):「**previous** 5K best」GT 27:45、「Apex 更新**前**的舊目標」GT 100、「**頭三個月**幾顆球」GT 15、「**earlier** 釣魚行(7/22 前)」GT 7、「**old** sneakers 放哪」。
    - **B2 複合題(答案字面需要「舊 AND 新」兩版,殺手級)**:31748ae「剛上任帶幾個?**現在**幾個?」GT「started **4**, now **5**」;685340e「以前多常打網球?**現在**?」GT「previously **every week**, now **every other week**」。
    - 舊值**仍在 store(保守寫入沒刪),query 端無條件 collapse 成最新** → 必錯。**→ keep-all 最強論證:歷史值/複合題只有保守寫入保住了可救的舊版;破壞性 baseline(mem0(b)/vanilla)舊版已刪、再強的 resolver 也救不回。** 修法是 query-aware resolver(偵測 previous/first/both 意圖就不 collapse)——**列為未來 case study,暫不實作**。
  - **Mode A(新舊同時在 context,LLM 挑了舊的)≈3-4/11**:如 ba21379「目前做哪台車」context 同時有 F-150(新)+ Mustang(舊),沒歸成 FRESHNESS 群(被當不同 model 專案)→ 該丟沒丟。→ 指向 grouping/conflict-type 分類可再強化。
  - **judge 嚴格 ≈1-2**:GT「1300」vs ours「close to 1300」。
  - 2 abs:未成功 abstain。
- **跨 benchmark 一致**:ours 在 FC-SH(has_pair 86-92%)與 LongMemEval-KU(83%)都強 → KU 主張非 FC-overfit。

### 2.2 待補
- mem0(b) / vanilla full 78(同 4-key sharding;b 重用 ours 各 shard held-fixed 抽取 cache)。
- Zep-on-LongMemEval(`zep_lme_ingest.py`+`zep_lme_query.py`:per-question graph、真實 `created_at` 驅動 temporal KU、多顆粒 compose;多 ZEP 帳號 sharding)。
- paper-final:gpt-4o judge 重跑全矩陣。
