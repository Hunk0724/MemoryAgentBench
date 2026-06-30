# Experiment Materials (paper / 口試素材)

> 用途:Experiment 章節寫作 + 投影片。彙整 dataset / protocol / baseline / 目前結果 + observation,
> 並**誠實標註已做 vs 待補**。證據細節見 [phase2_three_level_evidence.md](phase2_three_level_evidence.md);方法見 [methodology_materials.md](methodology_materials.md)。
> 建立 2026-06-22。

---

## 1. Datasets

### 1.1 主資料集:FactConsolidation (FC) @ MemoryAgentBench
- **來源**:MemoryAgentBench(Hu, Wang, McAuley, ICLR 2026)的 `Conflict_Resolution` split,`FactConsolidation` 子集;其本身由 **MQuAKE-CF**(Zhong et al., EMNLP 2023)的反事實 edit pairs 建構。
- **任務形態**:Knowledge Update (KU)。「對話歷史」**不是 dialogue,而是一份編號的宣告句事實列表**;同一關係的舊/新版本以不同序號鑲嵌(序號大者為新、為正確)。每題問某事實的**最新版本**。
- **公開可重現**:HF `ai-hyz/MemoryAgentBench`(Conflict_Resolution split)+ MQuAKE-CF 公開。GT 對齊 + frozen caches + scripts 皆在 repo(見 §6)。

### 1.2 Statistics(本研究使用範圍)
焦點為 **FC-SH(single-hop)× {6k, 32k, 64k}**。每子集 100 題、共享一份 context。

| 長度 | context 事實數 | chunk 數(512) | SH has_pair / no_conflict | 備註 |
|---|---|---|---|---|
| 6k | 455 | 12 | 74 / 26 | |
| 32k | 2310 | 64 | 65 / 35 | |
| 64k | 4580 | 130 | 66 / 34 | |
| 262k | 18332 | 531 | (未跑完) | write-time 中止於 ~32% |

> has_pair = context 內同時含該題事實的新舊版本(可解衝突);no_conflict = 僅單一版本。比例與官方 coverage 一致(`build_sh_analysis.py`,同一套對齊)。

### 1.3 Preprocessing(寫入前處理,全 frozen 可重現)
- **Chunking**:`chunk_facts_by_line`(fact-aware,chunk_size=512)——避免序號與內文被切散。
- **Atomic extraction**:L2 knowledge-extraction prompt(`make_l2_knowledge_prompt`)+ **frozen extraction cache**(`MEM0_EXTRACTION_CACHE`),使 SH/MH/重跑抽取逐字一致(抽取非研究對象,固定為可重現前置)。
- **Triple extraction(ours)**:gpt-4o-mini schema-free per-item,batch + **frozen triple cache**(`MEM0_TRIPLE_CACHE`);triple-null 補 subject_fallback(`MEM0_SUBJECT_CACHE`)。
- **GT 對齊**:MQuAKE-CF → 每題 (gt_seq/old_seq, gt_fact_text/old_fact_text, conflict_type),`build_sh_analysis.py`(重用 `analyze_lca_mquake` + `check_mquake_coverage` 的官方對齊)。

### 1.4 待補(誠實列)
- **FC-MH(multi-hop)**:鏈式多跳衝突,未跑。
- **262k**:write-time 中止於 169/531 chunk(triple cache 已快取 5924/18332,可續)。
- **泛化資料集**:LongMemEval(KU)等對話式、多值、非 triple 場景,未開始(§6 roadmap)。

---

## 2. Experimental Protocol(足以重現)

### 2.1 共同設定(三方法完全相同,只差 memory-side)
| 項目 | 設定 |
|---|---|
| Backbone LLM | **gpt-4o-mini**(intro 所指的小型、低成本、不可微調 regime) |
| Embedder | OpenAI **text-embedding-3-small**(1536d;MABench gpt 線預設) |
| Chunk size | 512(fact-aware) |
| Retrieval | **cosine top-100**(vector-only;vanilla 與 ours 相同,刻意不動) |
| Inference prompt | benchmark FC 模板**逐字相同** |
| Scorer | benchmark `exact_match` / `substring_exact_match`(drqa) |
| Determinism | temperature=0 + 全 frozen caches → **單一確定性 run**(故無 run-to-run variance、不畫 error bar;會在 caption 註明) |

### 2.2 Flag 矩陣(同 codebase,一鍵切換,apples-to-apples)
| 模式 | `MEM0_ADD_MODE` | `MEM0_QUERY_MODE` |
|---|---|---|
| vanilla Mem0 | (unset) | (unset) |
| ablation A1(保守 store,無 query 解析) | `phase0_structural` | (unset) |
| **Ours-Phase0**(結構) | `phase0_structural` | `structural` |
| **Ours-Phase2**(結構+LLM 分群) | `phase0_structural` | `phase2` |

> 注入點 `agent.py:931`,關閉時與 upstream byte-identical。

> ⚠️ **「vanilla Mem0」正名(重要,2026-06-24)**:本文件全篇所稱「vanilla Mem0」**並非未改動的 stock mem0**,而是 **mem0 + 我們的 L2 atomic-extraction 修正(`use_l2_fc_prompt`)+ 原生破壞性更新**。L2 抽取在 vanilla/Phase0/Phase2 **三者固定相同** → 這是公平的 internal ablation,**隔離出「記憶機制」的效果**;但它**隱藏了「stock mem0 連 FC 抽取都做不好」**這件事。請依角色正名:
> - **「vanilla Mem0」→ 應稱「Mem0 (L2-extract + destructive)」** = additive ablation 的 **(b)**(抽取修好、寫入仍破壞性)。
> - **真正的 stock vanilla mem0**(native `FACT_RETRIEVAL`、無抽取修正)是**另一條誠實 out-of-box baseline**(在 FC 漏世界事實、低分),= **(a)**,需單獨列。
> - 全表數字為 **L2-based**;專案已收斂為**單一 unified 抽取器(P1, source-based)**,FC 將以 P1 重跑((a)/(b)/(c) 三 arm),**取代本表數字**。屆時本節整體改寫。

### 2.3 Baselines
- **Mem0 (L2-extract + destructive)**(= 本文舊稱「vanilla」;coupled, destructive update)— 主對照(同 codebase,抽取與 ours 相同)。
- **stock vanilla Mem0**(native 抽取,無修正)— 誠實 out-of-box,**待以 (a) 補上**。
- **Ours-Phase0**(structural-only)— ablation,隔離「結構解析」貢獻。
- **待補**:**Zep**(decoupled;intro 說「把其精神推到極致」,**強烈建議補**否則定位無對照)、LightMem(coupled)。

### 2.4 Metrics
- **KU Accuracy(主指標)**:benchmark EM(含 substring)。
- **三層診斷指標**(model-independent,isolate 失敗源):
  - **L1 Retrieval**:top-100 是否含 query-relevant GT。has_pair → {both/new_only/old_only/neither};no_conflict → single retrieved。
  - **L2 Resolution**:resolution 後 final context 的同分類;核心 `resolution_clean_rate = P(L2=new_only | L1=both)`。
  - **L3 State→EM**:`P(exact_match | final-context state)`。
- 評估皆以 **query-directly-relevant** 的 GT(gt_new/gt_old/gt_single)為準。

---

## 3. 目前結果(FC-SH 6k/32k/64k)

### 3.1 主結果:KU Accuracy(EM %,↑;同一 inference 路徑量測,**bold**=最佳)

| Length | Method | has_pair | no_conflict | overall |
|---|---|---|---|---|
| **6k** | vanilla Mem0 | 27 | 65 | 37 |
| | Ours-Phase0 | 82 | 100 | 87 |
| | **Ours-Phase2** | **88** | **100** | **91** |
| **32k** | vanilla Mem0 | 37 | 83 | 53 |
| | Ours-Phase0 | 68 | 94 | 77 |
| | **Ours-Phase2** | **78** | **94** | **84** |
| **64k** | vanilla Mem0 | 42 | 62 | 49 |
| | Ours-Phase0 | 58 | 71 | 62 |
| | **Ours-Phase2** | **62** | **71** | **65** |

(vanilla 為在其破壞性 store 上重跑 inference 量得;32k overall 53 ≈ documented 51。)

**no_conflict 子集的觀察(重要,佐證「破壞性傷及無辜」)**:
- **ours ≫ vanilla**:6k/32k 的單一事實題,ours 100/94% vs vanilla 65/83% —— vanilla 的破壞性更新**把不該刪的單一事實也刪了**(LightMem §5.6 自承)。
- **phase0 == phase2 的 no_conflict 完全相同**(100/94/71)→ **resolution 對無衝突題零影響(零 false-merge)**,加分全在 has_pair。
- 64k 時 ours/vanilla 的 no_conflict 都下滑(71 vs 62),差距縮小 → **retrieval recall 成為共同瓶頸**(非 resolution)。

**Figure（[F6_em_matrix](figures/F6_em_matrix.png),上表的視覺版)**:
> **Figure 6.** *KU exact-match accuracy by conflict subset (has_pair / no_conflict / overall) across history lengths (6k/32k/64k), for vanilla Mem0 vs Ours-Phase0 (structural) vs Ours-Phase2 (structural + LLM grouping); single deterministic run (temperature 0, frozen caches).* Ours dominates at every length and subset; the gain over vanilla is largest on **has_pair** (6k 27→88), the resolution step (Phase0→Phase2) adds a further **+6–10pp on has_pair while leaving no_conflict unchanged**, and all methods degrade as length grows. *This shows our improvement is concentrated where KU conflicts exist, is achieved without harming non-conflict queries, and that at long context retrieval recall — not resolution — becomes the shared bottleneck.*

> 定位:F6 是 §3.1 主結果表的視覺面向(slides 主結果頁用);table 給精確數字,figure 給「方法排序 + 子集 pattern + 規模衰退」的一眼印象。

### 3.2 三層證據(對應 figures F1–F4,見 evidence doc)
- **L1 Retrieval**:store 點數 ours vs vanilla = 455/2310/4580 vs **156/1101/2179**(vanilla 不可逆刪 ~50–66%)。has_pair `both`:ours 97/82/67% vs vanilla 3–9%;vanilla **59–69% 的衝突對新事實不可逆遺失**(old_only+neither)。
- **L2 Resolution**:clean_rate(L1=both→new_only):phase0 61/57/77% vs **phase2 75/83/91%**;no_conflict **零誤刪**(L2_kept==L1_retrieved)。
- **L3 State→EM**(pooled):new_only **98%**(n=317)、both 57%(n=100)、old_only **1%**(n=93)、neither **3%**(n=105)。

### 3.3 抽取品質(ours write-time)
F1 triple-null 率:6k 1.8% / 32k 2.4% / 64k 1.6%。F2(衝突對 (S,P) 一致,both-extracted)6k ≈ 73% ceiling(殘餘多為 predicate 同義 → 留 D3)。

---

## 4. Observations(帶出後續)

1. **破壞性 write-time = 不可逆損失**:vanilla 刪掉約一半到 2/3 事實,衝突題 59–69% 的新版**從 store 消失**;連 no_conflict 單一事實也誤刪(檢索率僅 50–63%)。→ 佐證 intro「上游判斷是唯一錯誤來源、誤判不可逆」。
2. **保守保留 + query-time 按需解析有效**:ours 保留全部 → both 可檢索 → query-time argmax 取最新;state→EM 證明 **收斂成 new_only ⇒ ~98% 答對**,both ⇒ ~57%(無 disambiguation),old_only/neither ⇒ ~0%。
3. **LLM 分群(Phase2)勝純結構(Phase0)**:clean_rate +14/+26/+14pp,救回 F2-split(同事實不同 (S,P));整體 +3–7pp;且 **零 false-merge 連帶傷害**(v2 prompt + subject guard)。
4. **規模化後瓶頸從 resolution 移到 retrieval**:64k 時 phase2 解析後殘留 both 僅 3%(解析近完美),失分主要是 old_only 17% + neither 18%(=**新版沒被檢索到**;但新版仍在 ours store)。no_conflict 檢索率隨長度 96→94→74%。→ **下一個 challenge 是 retrieval module**。
5. **guard 在 FC 上 0 觸發**:改良 prompt 已壓住跨 subject 誤併 → guard 是未被觸發=**尚未驗證**的安全網(泛化場景才會真正壓力測試)。

---

## 5. Failure Mode Analysis(挑重點,每個對應 figure)

只講四個最重要的失敗模式;每個都能用一張 figure 指出,並由 **F4(state→EM)統一說明「為何這狀態會錯」**。完整 F1–F8 taxonomy 見 [phase2_spec.md](phase2_spec.md) §4。

| # | 失敗模式 | 對應 figure | FC-SH 實測 | 性質 / 處置 |
|---|---|---|---|---|
| **FM1** | **vanilla write-time 不可逆刪除**(刪新版 / 刪兩版 / 連單一事實也刪) | **F1**(store 縮水)+ **F2**(vanilla old_only/neither) | store 僅剩 34–48%;衝突對 **59–69% 新版遺失**;no_conflict 也降到 65/83/62% | **baseline 根本缺陷,不可逆**(F4 證明 old_only/neither → ~0% EM) |
| **FM2** | **(S,P) 不一致 → 結構解析漏網**(同事實被抽到不同 (S,P);predicate 同義 / inversion) | **F3**(Phase0 vs Phase2 clean_rate) | Phase0 殘留 both(6k 28 / 32k 22 / 64k 9);F2 raw ~27% → 殘 ~15.6% | ours **可救**:Phase2 LLM 分群收掉 → clean_rate **+14–26pp**;殘餘 → D3(延後) |
| **FM3** | **retrieval recall:new fact 未進 top-100**(規模化主瓶頸) | **F2**(ours neither 0→3→15%)+ **F6**(隨長度衰退) | 64k has_pair 失分主因(old_only 17% + neither 18%) | **可救**:新版仍在 ours store(非 resolution 問題)→ **Path B 結構檢索(下一步)** |
| **FM4** | **LLM 分群 false-merge**(跨 subject/屬性誤併,丟錯版) | (開發發現,無 figure) | v1 出現(citizen-of-USA 跨人大群)→ no_conflict 100→**85**;v2 改良 prompt + subject guard → **回 100,殘餘 0** | 已修;⚠️ guard 在 FC **0 觸發 = 未驗證**(泛化才壓測) |

> **收束(一張投影片可講完)**:vanilla 的失敗是 **write-time 不可逆**(FM1);ours 的殘餘失敗都**可救**——FM2 已被 Phase2 救掉(剩 → D3)、FM3 是 retrieval(→ Path B)、FM4 已用結構護欄處理。**每個重要失敗都能用 figure 指出,並由 F4 統一解釋為何會錯。**

---

## 6. 接下來的實驗 / Roadmap(誠實規劃)

### 6.1 泛化:LongMemEval(KU)— 拆解 triple vs LLM 分群各自效果
- **動機**:FC 全是 (S,P,O) 單值,結構路徑吃下大部分;LLM 分群與 subject guard **在 FC 未被真正壓力測試**。LongMemEval 的記憶是**對話式、多值、常無乾淨 triple** → 正好測:
  - triple/結構路徑覆蓋率(F1 null、(S,P) 命中)在非 FC 場景掉多少;
  - **LLM 動態分群**(處理無 triple / F2-split)與 **subject guard / 多值 COEXIST** 的真正貢獻;
  - 是否 over-fit 在 FC。
- **ablation**:A0 vanilla / A1 conservative-store-no-resolve / Phase0(結構) / Phase2(+LLM) → 拆 triple vs LLM 分群。

### 6.2 下一個 challenge:Retrieval module(由 §4.4 觀測驅動)
- 規模化後 old_only+neither 由 retrieval 主導。我們**已建但 query 時未用的 (S,P) inverted index**(Path B 結構檢索)正好對症:對衝突題用 query 的 (S,P) 直接 lookup,把新舊版本撈回(即使不在語意 top-100)。
- 即 guide §7.4 的 A3;預期能拉回 has_pair 的 old_only/neither。

### 6.3 其他待補(發表前)
- **Zep / LightMem baseline**(定位對照,Zep 優先)。
- **FC-MH**(多跳)、**262k**(續跑 write-time)。
- (選)**frontier model 對照**:坐實「破壞性誤判隨模型變小而惡化」。

---

## 7. Reproduction

```bash
conda activate MABench
# GT 對齊(6k/32k/64k)
python docs/0615_intro_framework_after_problem_statement/scripts/build_sh_analysis.py {6k,32k,64k}
# end-to-end benchmark(vanilla / phase0 / phase2)
bash docs/0615_intro_framework_after_problem_statement/scripts/run_phase0_sh_6k.sh   # vanilla+phase0
bash docs/0615_intro_framework_after_problem_statement/scripts/run_phase2_sh_{6k,32k,64k}.sh
# 三層分析 + 圖
python docs/0615_intro_framework_after_problem_statement/scripts/analyze_l1_retrieval.py
python docs/0615_intro_framework_after_problem_statement/scripts/analyze_l2_resolution.py
python docs/0615_intro_framework_after_problem_statement/scripts/analyze_l3_state_em.py
python docs/0615_intro_framework_after_problem_statement/scripts/make_figures.py
```
- 環境:conda **MABench**;qdrant 須 `on_disk:true`(否則重開會清空)。
- frozen caches:`analysis/results/{extraction,triple,subject}_cache_{L}.json`、grouping cache。
- stores:`analysis/results/expanded/stores/qdrant_gpt4o_512_openai_{rerun,phase0,phase2}__factconsolidation_sh_{L}`。
- 結果/圖:`analysis/results/phase0/l{1,2,3}_*.json`、`docs/0615_.../figures/`。

---

## 8. Conclusion & Future Work(英文精簡 + 中文講稿)

### Conclusion (concise, reviewer-facing)
- KU fails when stale and current fact versions co-accumulate; prior methods resolve it **destructively at write-time**, where a single LLM judgment is an **irreversible** failure point.
- We **defer KU to query time**: conservative structural write (*all versions kept*) + query-time identity grouping + temporal resolution — **decoupling judgment from execution**.
- On FC-SH (gpt-4o-mini), KU accuracy improves **37/53/49% → 91/84/65%** over vanilla Mem0.
- A 3-level analysis pinpoints the mechanism — keep all → current fact recoverable → conflicts collapsed to new-only → final state determines accuracy — and shows failures **shift from irreversible (write-time) to recoverable (query-time)**.

### Future Work (concise)
- **Retrieval recall at scale** — activate the already-built (S,P) index as a structural retrieval path.
- **Generalize to conversational / multi-valued KU** (LongMemEval) to disentangle structural vs LLM grouping.
- **Relevance filtering before resolution** to cut cost and false merges.
- **Broader baselines** (Zep, LightMem) and settings (multi-hop, 262k).

### 結論(講稿)
- 我們處理**知識更新(KU)**:事實被新版本取代後,舊版與新版**同時堆積**在記憶庫,檢索時一起被撈出、誤導推論。
- 過去 proactive 方法在**寫入當下**就用一次 LLM 判斷做破壞性更新——這判斷是**唯一且不可逆**的失誤點(小型不可微調模型更慘)。
- 我們把解析**推遲到查詢時、按需處理**:寫入只做保守結構化保留(每筆抽 (s,p,o)、建索引、**全版本保留**,無跨筆判斷);查詢時才分群 + 時序選最新版——**判斷與執行解耦**。
- FactConsolidation 上,KU 正確率 **37/53/49% → 91/84/65%**。
- 三層分析:全保留→當前事實**撈得回**;查詢時把衝突對**收斂成只剩新版**;最終 context 狀態幾乎**完全決定**答對。殘餘錯誤從「寫入時不可逆」變「**查詢時可救**」,印證核心理念。

### 未來工作(講稿)
- 規模化後記憶庫變大、檢索仍固定 top-K → 當前事實**難撈回**(現階段最大瓶頸);用已建的 **(S,P) 索引**做結構化檢索補上。
- FC 文字結構**可能剛好契合** (S,P) 設計 → 換**對話式/多值 KU(LongMemEval)**才能分清結構 vs LLM 分群,並壓測 subject guard(FC 上未觸發)。
- 解析前加 **relevance filter**(先濾與 query 無關者),省成本、少誤併。
- baseline 補 **Zep / LightMem**;設定補 **MH / 262k**。
