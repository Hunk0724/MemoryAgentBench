---
name: project_mem0_failure_decomposition
description: 2026-06-03 起的 mem0 失敗拆解研究線 — 把 FC-MH 失敗歸因到 extraction/candidate/update 三 component
metadata: 
  node_type: memory
  type: project
  originSessionId: f891b415-ba71-4a64-81c6-6e8837d11013
---

2026-06-03 起的研究主軸:把 mem0(vector 模式,非 mem0g)在 FC-MH 的失敗,歸因到 ingestion pipeline 三步——Component 1 extraction / Component 2 candidate retrieval(top-5)/ Component 3 update decision——並扣除結構 noise(same-chunk 衝突、extraction 漏抽)。支撐 [[project_research_core_claims]] Claim 1(write-time 偵測長 ctx 失效)。

lab notebook(邊做邊記,設定/定義/目的都要寫清楚):`MemoryAgentBench/docs/0603_current_research_main_evidence/00_research_axis_and_setup.md`。

關鍵設定:改過的 extraction prompt(只移 2 個 few-shot)、mem0 內部 LLM temp=0(diagnostic deterministic;upstream 預設 0.1)、chunk_size=512(4096 會漏抽)、答題 LLM temp=0.7(預設,在三 component 下游)。

已做(2026-06-03):T0 fact-aware chunker(`utils/eval_other_utils.chunk_facts_by_line` + conversation_creator 對 factconsolidation 路由)、T1/T2/T3 三 component instrumentation(`mem0/memory/main.py`,env `MEM0_CAND_LOG_DIR` gate,未設則 byte-identical;產出 extraction/candidate_pool/update_decision 三 jsonl)、T5 正式跑 FC-MH 6k。

**重要發現**:
- 純 fact-aware chunker 改動 → mem0 MH 6k **EM 52%→62%(+10pp)**。舊 nltk chunker 邊界切壞低估了 mem0;**paper baseline 須用 fact-aware 數字**,且 mem0g/HippoRAG 也要用同 chunker 重跑才公平(T5b)。
- mem0 extraction **剝掉序號** → recency=ingestion 順序,非序號;6k extraction 健康(455/455,0 失敗)→ 38% 失敗在下游 candidate/update。
- hallucinated-id(update LLM 指認超出候選池的 id)6k 下非主因(只空池 chunk0),需 32k 驗證。
- **A-WT write-time 衝突解決稽核(6k)**:165 對 GT 衝突,detectable(cross-chunk)148,**resolved 98.6%**,H1-miss(候選擠不進)/H2-refuse(看到不覆蓋)各僅 1 例。→ **6k write-time 衝突解決非瓶頸**,FC-MH 6k 的 38% query 失敗在 query 側。兩假設機制為真但 6k 罕見,**需 32k/64k 看 H1 是否隨池放大**(核心「池過大」驗證)。寫 A-WT 時抓到並修正一個方向 confound:supersession 看 ingestion 順序(大序號 winner 覆蓋小序號 loser),非 MQuAKE gt/old 標籤;且僅 161/165 對 gt==較大序號。

write-time 焦點(使用者釐清):只看 query 前記憶建構,SH/MH 共用 6k context(md5 一致)故 write-time 一致。

**Extraction blocker + 解法(2026-06-04)**:mem0 FACT_RETRIEVAL_PROMPT 是「Personal Information Organizer」抽個人資訊,對 FC 通用知識會回空;L1(移 2 few-shot)沒根除,6k 剛好沒踩、32k 踩到(MH 7、SH 13 個 chunk 全 0,漏數百筆)。**解法 L2**:reframe 成 knowledge extractor(`make_l2_knowledge_prompt`),驗證 100% 完整。**Extraction cache**(`extraction_cache_{6k,32k}.json`,env `MEM0_EXTRACTION_CACHE`,key=numbered-fact lines hash):每 context 抽一次凍結,SH/MH 共用同一份→逐字一致。序號**剝除**(對 mem0 公平:其 inference prompt 無序號規則、recency 靠 ingestion 順序,與 LCA 不同)。四組 L2 yaml `..._factaware_l2{,_32k}.yaml`,output namespace `-l2`。

**Query pipeline 拆解(6k L2,2026-06-04)**:MH 37 失敗 = **retrieval-miss 23(62%,多跳中間 fact 沒進 top-100,4-hop 47% miss)** + inference-fail 12(其中 **9 個 older_fact = H2 參數覆蓋,發生在最終答題 LLM 非 write-time**)+ stale-leak 2。→ **MH 主瓶頸是多跳 retrieval,H2 次要且在 inference**。腳本 query_pipeline_analysis.py。

**乾淨 L2 四組 EM matrix(2026-06-04)**:MH 6k 64 / MH 32k 39 / SH 6k 92 / SH 32k 90。**SH 對 ctx 長度穩健(92→90,−2pp)= mem0 衝突解決本身 scale 下穩**;MH −25pp 是多跳 retrieval confound。→ 使用者決定**衝突解決主軸專注 SH**(排除多跳)。

**研究主軸聚焦(使用者 2026-06-04)**:只談「衝突解決」→ 專注 **SH(單跳)**,排除 MH 多跳 retrieval confound。

**FC-SH 6k 條件式 query 分析(2026-06-04,已二次更正)**:依 ingestion 結果分組(CORRECT 93=67 has_pair+26 no_pair / DROPPED 4 / STALE 3)。⚠️ **初版誤用 sh_512 的舊 HippoRAG `error_type`/`model_output` 欄位** → 誤判「EM 假象」「H2」。改用本 run `results.output` 後:8 nominal 失敗 = **4 write-time DROPPED**(反事實在 ingestion 被丟,答舊世界事實 qid7=cross/34/42/52=same)+ **4 模型生成 artifact**(3 空輸出 qid66/89/97 + 1 幻覺 qid1;**非 H2、與衝突解決無關**)。**衝突解決可歸因失敗=4(全 write-time 丟反事實)**。無 retrieval 問題(單跳)。STALE 3 全對。**教訓:跑後必查當前 run 的實際輸出,勿用殘留欄位**。

**序號規則(更正,2026-06-04 trace)**:⚠️ 之前誤說「mem0 inference 無序號規則」是**錯的**。trace MemoryAgentBench_original/agent.py:582-592 確認:mem0 inference 的 system_prompt + user(FC query 模板,含「用較大序號解衝突」)與原始**逐字相同**;序號規則是**原始 benchmark 內建**(mem0 agent_name→normalize→rag_agent→套 FC 模板)。但 mem0 記憶**無序號**(extraction 剝除)→ 規則 inert = **原始就內建的矛盾,非我們製造**。另:Gemini 無 native system role,我們把 system+user 串成單一字串(原始 OpenAI 用分開 role)= backbone 換動的 deviation,需 disclose。**教訓:alignment 要 trace 原始 code,勿臆測。**

**乾淨設定文件**:`docs/0603_current_research_main_evidence/01_mem0_fc_setup_and_results.md`(single source of truth);`02_fc_sh_6k_failure_deepdive.md`(非正常案例逐題 trace);00 當 log。腳本 sh_query_conditional / detail_cases / classify_sh_all / audit_deviation。

**FC-SH 6k 結構性問題(deepdive,撇除 thinking artifact + benchmark prompt)**:
- **A1 same-chunk 失敗(主因,影響 9 題)**:衝突新舊同 chunk → mem0 architecture 無法 UPDATE 同 chunk 新 fact(無合法 candidate id)。三種任意行為:(i)UPDATE 但 hallucinated-id 被丟(qid42),(ii)NONE 省略一版(qid34/52 丟反事實 fail;qid28/38/69 剛好丟世界 success),(iii)兩版都 ADD=STALE(qid12/31/57)。保留哪版基本任意。
- **A2 cross-chunk write-time H2-refuse(qid7)**:候選 retrieval 成功(American football rank1 score0.902),但 LLM **no-op update(保留世界)+ 丟反事實**=拒絕寫反事實。能做卻不做(與 A1 想做卻做不到不同)。
- **A3 inference cross-fact 混淆(qid1)**:抓了另一條共用主詞 fact 的 object(Watsuki famous for→答 Vito Corleone)。用記憶但讀錯 fact。
- **A4 cross-fact 污染(2026-06-04,32k 補)**:update LLM 把某 fact 槽位 UPDATE 成另一條共用實體的無關 fact(entity confusion)→ 反事實被摧毀。6k 全域 2 例(未 query 到),32k 造成 4 個 SH BAD-SUP 失敗(qid8/87/95/98;qid9 是 benchmark 反常 gt<old 非失敗)。隨 scale 放大。component=update LLM 判斷品質。
- artifact(非結構):空輸出=thinking 非確定(qid66/89/97,重跑 STOP 非空);STALE 成功靠 benchmark prompt「rather than real facts」。

**結構失敗根因統整(2026-06-05 修正,取代「4 條獨立路徑」)**:收斂到 **2 根因 + 1 架構軸**:
- **R1 候選檢索鍵控錯誤**(embedding 按關係模板/實體重疊排序 ≠ (主詞,關係) 槽位身分):**A1 與 A4 是 R1 兩面** — A1 把真舊版擠**出** top-5(miss→兩版 ADD);A4 把同實體異關係 fact 擠**進** top-5 → update LLM **over-fire** 覆蓋它(無關 fact 被毀)。
- **R2 update LLM 不可逆裁決品質**:A2(拒用反事實覆蓋,參數知識)。
- **架構軸 A3**:same-chunk 新 fact 無合法候選 id(實作層,占比隨 scale 降)。
- ⚠️ **A4 ≠ A1 下游(使用者假設的答案:否)**:全域 16 個 A4 污染中 **13/16 被毀 gt 在污染者 top-5(rank 1–3)** → 候選取到了,失敗在 update 判斷。腳本 `a4_contamination_audit.py` / `trace_badsup_cases.py`。
A1/A2/A4 隨 scale 放大(resolved 98.6→93.1%,A1 1→29,A2 1→28,A4 全域 2→16),A3 占比降。主張「ingestion-time 不可逆 LLM 衝突裁決在 FC counterfactual 下系統性失敗」目前是「隨 scale 結構退化」,需 64k 證實持續惡化;caveat:6k/32k 仍 93%+ resolved,非小尺度即崩。

**64k FC-SH 分析完成(2026-06-05,minimal thinking;deepdive=`04_fc_sh_64k_failure_deepdive.md`)**:
- ⚠️ **設定 confound(關鍵)**:64k ingestion+答題皆 **minimal thinking**(High 在 chunk37 本機 OOM),`generation_max_length=256`(無空輸出);6k/32k 是 High。→ **resolved/H2-refuse 不可與 6k/32k 並列**。
- **write-time(1691 對,detect 1678)**:resolved **95.6%** / H1-miss **53(3.2%)** / H2-refuse **21(1.3%)** / same-chunk 13。
- **⚠️ 非單調回升的誠實判定**:64k resolved 95.6% **>** 32k 93.1%,是 **minimal-thinking artifact**(minimal 削弱 H2-refuse 3.4%→1.3% → 推高 resolved),**非「池更大反而更好」**。唯一跨設定穩健的 scale 證據 = **H1-miss 絕對數 1→29→53 單調上升**(純 embedding,不受 thinking 影響)。**必做:6k/32k 用 minimal 重跑**才能宣稱 resolved 單調惡化。
- **query(EM 94%,真實規則正確率 96%)**:6 nominal 失敗 → **qid18/20 是 benchmark 答案鍵瑕疵**(mem0 輸出大序號 rule-correct;⚠️ 64k 瑕疵題是 18/20,非 32k 的 8/9,`sh_full_classify.py --benchmark-defect` 須改 18,20,用 `benchmark_rule_consistency.py` arrow idx6 重判)。**真 mem0 失敗=4**:qid32(A4,MLK died-in-city 槽存對後被「citizen of Vietnam」over-fire 覆蓋)+ **3 個無衝突單一事實** qid77(A4,Areopagitica 摺進 famous-for 槽被 Shakugan no Shana 覆蓋)/qid87(近重複碰撞,Born This Way Ball 巡演 被 Born This Way 歌覆蓋)/qid76(**omission 新子模式**:n_cand=156 下 update LLM 直接漏輸出該 new fact,既非 ADD 也非 NONE)。
- **🔑 強化主張**:3/4 真失敗是**無衝突單一事實** → R1+R2 結構失敗**不限衝突解決**,任何 fact 只要候選池混入同實體異關係/近重複反事實就被毀。但 query magnitude 弱(4/100)→ 主張力量在 **write-time 聚合 + 機制純度**(每失敗可 component 定位、無隨機),非 query EM。產物:`logs/sh_64k_{conditional,full_classify}.json`、`logs/sh_64k_l2/awt_result.json`、`analysis/results/sh_64k_RUN_gt.json`。

**32k SH 10 個 QA 失敗的正確歸因(2026-06-05,逐案 trace Layer A + MQuAKE-CF 來源)**:**2 dataset 跨-case 碰撞(qid8/9,非 mem0,剔除)** + 3 A4 over-fire(qid87/95/98)+ 3 空輸出 thinking artifact(qid7/33/51)+ 2 cross-fact inference(qid23/64)。→ **真正可歸因 mem0 衝突解決的 query 失敗 = 3(全 A4)**。
- **⚠️ qid8/9 是 benchmark 答案鍵自身瑕疵(benchmark-only 確認,非 mem0、非 MQuAKE)**:直接讀 benchmark 原始 item(`ai-hyz/MemoryAgentBench` Conflict_Resolution idx5,**context md5 與我們的完全一致**):Q8 答案鍵=London,但 context 同時有 `707.London` 和 `1929.Washington D.C.`(同主詞同關係);Q9 答案鍵=Rome,context 有 `1291.Rome`+`2016.Watertown`。benchmark prompt 模板(templates.py rag_agent)明寫「newer=larger serial,find newest with larger serial」→ 按規則 Q8 該答 Washington D.C.(1929,大),答案鍵卻標 London(707,小)→ **答案鍵違反 benchmark 自宣告規則**。**mem0 保留大序號反而 rule-compliant,是答案鍵懲罰了正確衝突解決**。全 100 SH:65 衝突題,**63 答案=最大序號(規則自洽),僅 qid8/9 答案=較小序號**(腳本 `benchmark_rule_consistency.py` benchmark-only / `collision_detect.py` 純 context)。→ 從 mem0 失敗分母剔除。**MQuAKE 對應沒抓錯、gt 定位是唯一文字匹配**。成因:答案鍵建構時誤取真實世界事實(London/Rome)而非同 slot 的反事實編輯版。
- **⚠️ write-time FULLPAIRS(837 對)未受碰撞污染**:每個 pair 是單一 requested_rewrite 的 old/new(within-case),(707,1929) winner=1929 標 resolved 成功。碰撞只在 query 端(query 來自 case B、編輯來自 case A)→ A1/A2/A4 計數乾淨。

**32k FC-SH 完整逐題分類(6k §C 等級,2026-06-05;腳本 sh_full_classify.py)**:100 題互斥分類 = 33 single-correct + 57 clean-resolved + **0 FRAGILE 脆弱成功** + 2 benchmark-defect(qid8/9)+ 3 FAIL-A4(qid87/95/98)+ 2 FAIL-inference cross-fact(qid23/64)+ 3 artifact 截斷(qid7/33/51)。
- **🔑 脆弱成功=0**(對比 6k 的 6 個):無 STALE / 無 same-chunk 蒙對 / 無 leak-but-correct。因 32k same-chunk 占比崩到 1.6%(6k 10%)→ 6k 的「same-chunk 任意性蒙對」現象消失。90 答對全乾淨。
- **🔑 真正可歸因 mem0 的 query 失敗=5**:3 write-time A4(qid87/95/98)+ 2 inference cross-fact(qid23/64,winner 乾淨檢索 rank0,答題 LLM 讀同主詞另一條 fact,放大 budget 仍穩定錯答=真混淆非截斷)。其餘 5=2 benchmark 瑕疵 + 3 generation artifact,非 mem0。
- **🔑 空輸出 re-trial(qid7/33/51,controlled)= max_tokens=10 截斷,非失敗**:同設定確定性空(thought_tok=0),放大 budget→**三題全答出完全正確答案** → **真實 EM 天花板 32k SH=93%**(非 90%)。空輸出根因從「thinking 隨機」更正為「generation_max_length=10 太小」,見 [[project_gemini3_thinking_determinism]]。腳本 retrial_empty_outputs.py。
- write-time 操作面:被 query 到的 winner 幾乎全乾淨 STORED,僅 3 A4 例外 → A1/A2 退化集中在**未被 query 的 pair**,印證兩軸框架。**關鍵:A1(H1-miss 29)與 A2(H2-refuse 28)一個都沒造成這 10 個 QA 失敗** — 它們是 write-time 退化(query-independent 837 對的軸1),這批 100 題 query 沒抽樣到。**兩軸不可混**:write-time 退化=主證據(乾淨、不依賴抽樣);query-time 10 失敗只有 A4 傳導。**32k 脆弱成功=0**(57 has_pair 答對全乾淨 SUPERSEDED;6k 有 6 個,因 6k same-chunk 占 10% 任意性,32k 降 1.6% 故消失)。已原地修正 doc 03(頂部加修正區塊)+ doc 01 §4.4。

**32k scaling 對照(2026-06-04)**:write-time(query-independent,用 *_FULLPAIRS_gt)resolved 98.6→93.1%、**H1-miss 1→29(使用者假設「舊版被擠出 top-5」證實)**、H2-refuse 1→28、same-chunk 16→13(占比降)。失敗主因從 same-chunk(A1)轉為 H1-miss+H2-refuse(non-same-chunk)。6k 結構問題 A1/A2/A3 在 32k 持續且部分放大→非獨立。SH query EM 90%(95 CORRECT-ingest + 5 BAD-SUP write-time;artifact 仍 ~3 空輸出/thinking)。⚠️ **GT 教訓:FC-SH/MH queries 隨 context 長度不同**(6k≠32k),query 分析須用 run 自己的 queries 建 GT(`build_sh_gt_for_run.py`,6k 重建與 sh_512 100/100 一致);write-time 用 FULLPAIRS 不受影響。

**待決策**:thinking 三處(agent.py:520/718、mem0_vertex_gemini_llm.py:92)改 thinking_level=minimal+temp=0(最小化但 G3 無法全關),診斷結論不受影響(架構性),但 EM 數字需考慮多 trial。write-time 也受 thinking 影響(update LLM)→ 改 minimal 後該重跑。

**Write-time fact-fate(6k L2 canonical)**:455 = STORED 296 / SUPERSEDED 144 / DROPPED 13 / DELETED 2(ideal STORED 310/SUPERSEDED 145)。偏差 15 筆(DROPPED 13+DELETED 2,10 same-chunk+5 cross)。**重要修正**:same-chunk ≠「both ADD」,mem0 在同 chunk 內去重,16 對 = 6 both-ADD + 6 留世界事實丟反事實(**=H2 在 write-time,僅 same-chunk,因無 ingestion-order 訊號**)+ 4 留反事實。**計數法**:event(per-chunk 操作)≠ fact-fate(455 下落),不可用 `455−events` 數 fact(會差 1~3);DROPPED=13 為正確未進 store 數。腳本 audit_deviation.py(role×fate 交叉表)。

**Minimal 統一重跑 + LCA baseline + 擴充評估集(2026-06-06)**:
- **全域 minimal thinking**:agent.py:523/719 + mem0_vertex_gemini_llm.py:92 皆 `thinking_level="minimal"`(已無法跑 High,要 High 需還原 code)。dataset yaml `generation_max_length` 6k/32k/64k/262k 全改 **256**(消除截斷空輸出)。
- **mem0 6k/32k minimal 重跑**(獨立 `_min` namespace,保留 High 原物;agent yaml `..._l2_min.yaml` / `..._l2_32k_min.yaml`,新 qdrant collection,log `sh_{6k,32k}_l2_min`,**共用 extraction cache → 只 thinking 變**;launcher `run_sh_6k_32k_min.sh`):**EM 6k 93(High 92)/ 32k 94(High 90)/ 64k 94**,空輸出全 0。→ **mem0 FC-SH 的 query EM 在 minimal 下幾乎平(93→94→94),「隨 scale 退化」不在 query EM,在 write-time 聚合**(待對 minimal 6k/32k 重算 resolved/H1/H2 補乾淨趨勢)。
- **LCA baseline**(`Long_context_agent_gemini-3.1-flash-lite_temp0.yaml`,temp0+minimal+256,launcher `run_lca_sh.sh`;**注意**:LCA 答題 agent.py:709-720 與 mem0 答題 agent.py:520-524 已逐項對齊 model/temp/thinking/budget=公平;舊 `size10` LCA 結果是 stale 截斷):**EM 6k 99 / 32k 96 / 64k 94 / 262k 74**,空輸出全 0。→ **長上下文 baseline 在極長度崩(74),mem0/RAG 64k 仍 94**;補跑 mem0 262k 才能定「檢索 vs 長上下文」分歧點。
- **擴充評估集(SH,已建+驗證)**:每個 in-store 衝突對 1:1 對應 MQuAKE-CF `requested_rewrite`,自帶 `question`(官方 has_pair 問題=此欄,64k 66/66 逐字相同)+ target_new/true。答案用 **largest-serial**(benchmark 自宣告規則,無瑕疵,自動修正 HF 答案鍵 bug;builder 交叉比對官方子集**重現** 32k London/Rome、64k Tom Clancy/Europe 4 個 defect=端到端驗證)。題數 **6k 161 / 32k 837 / 64k 1691 / 262k 7236**(vs 官方各 100)。腳本 `build_sh_expanded_gt.py`,輸出 `analysis/results/expanded/sh_<L>_EXPANDED_gt.json`,規格 doc `05_expanded_eval_set.md`。⚠️ alias 只取「答案字串實際相符」的 hop(避免把世界事實別名灌到反事實答案→否則 stale 會被判對、EM 灌水)。**動機**:100 題在強 backbone 下洗掉差異,大 N 才有鑑別度比較「衝突機制放在記憶系統不同階段」的設計。**待辦**:QA harness(對既有 qdrant store 免重 ingestion 逐題回答)+ MH 擴充(需多跳鏈完整性檢查)。

**優先評估失敗對 + QA harness(2026-06-08,使用者定向)**:
- **定向**:不要跑官方 100 題(強 backbone 都答對、洗掉差異),要跑**擴充衝突對**,**最優先 = vanilla mem0 write-time 沒解決好的對**(未來方法要優先改進處;resolved 當對照「維持答對」)。
- **fate 標記(用既有 ingestion log,不重跑)**:`tag_expanded_with_fate.py` join `awt_result.json` rows → `sh_<L>_EXPANDED_tagged.json` + `.priority.json`。失敗對(H1-miss+H2-refuse+same-chunk):6k 18 / 32k 45 / 64k 87。awt 對 minimal 6k/32k 用 `sh_{6k,32k}_l2_min` log 重算(64k 用 sh_64k_l2)。
- **QA harness `run_expanded_qa.py`**:忠實複用 benchmark ingestion/FC query 模板/答題/計分;**忠實度驗證官方 20 題 100% 一致**。summary 按 write_time_fate 分組 EM。
- ⚠️ **重大坑**:原 run 的 qdrant 在 `/tmp` + **`on_disk=False`**(mem0 `Qdrant.__init__` 在 on_disk=False 時 `shutil.rmtree(path)` **每次 init 清空 store**)→ store 沒持久。harness 補 `on_disk=True` + 持久路徑 `analysis/results/expanded/stores/`,一次 re-ingest(extraction 用 cache 凍結、只重跑 update-LLM、檢索與原 run 等價)後可 `--skip-ingest` 重用。**之前 run 存了結果/write-time log(update_decision 1423 actions)/檢索/extraction cache,唯獨向量 store 本體沒持久** → 建議把 on_disk=True+持久路徑寫進 agent yaml。
- **6k 結果(161 題,寫時失敗傳導到 QA 已證實)**:resolved 143 → EM 96.5/leak 0.7%;same-chunk 16 → **EM 56.2/leak 43.8%**;H2-refuse 1 → **EM 0/leak 100%**;H1-miss 1 → EM 100。→ resolved vs 失敗對大幅落差 = 官方題洗掉的弱點現形。6k 失敗對太少(H1/H2 各1),訊號要看 32k/64k。**待跑:32k/64k 持久 store + tagged QA**。產物 `analysis/results/expanded/`、`logs/expanded_qa_*`、spec `05_expanded_eval_set.md`。

**確立的擴充戰場 + store 重建法(2026-06-08,關鍵里程碑)**:
- **store 重建法(免重 ingest,已嚴謹驗證)**:原 qdrant 在 /tmp + `on_disk=False`(mem0 init `rmtree` 清空)沒留;但 **vector_results(mem0 add/update/delete 回傳,含 uuid+event+text)存在 `ingestion_context_0.jsonl`**(跨 run append,須切乾淨 slice:6k `-12`、32k `0:64`、64k `36:166`)。replay → 還原最終記憶集 → 用 mem0 同款 embedder(VertexADCEmbedding,text-embedding-004,RETRIEVAL_DOCUMENT/QUERY,cosine top-100)重做檢索 → **免重跑 update-LLM**。腳本 `reconstruct_store_qa.py`。**驗證 6k vs live mem0:最終記憶數精確(297)、EM 完全相同、18題17題逐字一致(唯一差異「Answer:」前綴)→ 可信**。
- **A4 是真失敗模式但藏在 awt resolved bucket**:awt fate(H1/H2/resolved/same-chunk)是逐 update 事件分類,A4(over-fire 毀 winner)不在其中。64k 全集:**71 個 awt-resolved 對最終 store 不乾淨(47 neither=新舊全毀,抽查 4/4 真實)**。→ **戰場改用「最終 store 狀態」定義**(腳本 `final_store_state.py` / `build_battlefield_gt.py`),自動含 R1 crowd-out(H1)+R2 refuse(H2)+R2 over-fire(A4)。
- **確立戰場 = cross-chunk(排除 same-chunk)+ final-store ∈ {old_only,both,neither}**:6k 6 / 32k 41 / **64k 99**(比 awt-bucket priority 大很多,解決「戰場太小」)。+ new_only 50 對照。
- **mem0 baseline(reconstruction QA)**:control new_only EM **100%**(三長度);both EM 90–95%(靠 benchmark prompt「rather than real world」nudge 挑新,脆弱非確定);**old_only EM 0%、neither EM 0–12%(mem0 write-time 把正確答案摧毀)**。戰場真未解決 EM:6k 33% / 32k 56% / 64k 43%。**old_only+neither(摧毀型)= 最乾淨 gap**:6k 4/32k 19/64k 56 對,EM ~0。
- **backbone 修正**:gemini 對 counterfactual 的參數知識是反向(拉向真實/舊=錯);both 還能答對靠 prompt nudge + 強指令遵循,非知識。→ 換 gpt-4o-mini(指令遵循弱)會讓 both EM 降、gap 變大 → **gemini 是保守戰場**(對主張有利)。計畫:dev-on-gemini(quota 多)→ final-on-gpt-4o-mini(每 token 成本)。
- **our method**(query-time 衝突裁決:非破壞 ingestion 保留所有版本+chunk_id/時間戳,query-time 挑最新)= 待設計,目標把 old_only/neither/both → ~100% 且 control 不退步。**排除 same-chunk**(同 chunk 共時間戳無法區分,屬 extraction 層另一問題)。
- **262k**:mem0 尚未 ingest(無 vector_results);launcher `run_262k_ingest.sh`(先建 extraction cache 再 ingest,on_disk 持久,寫 vector_results)備好,睡前跑(~500 chunks update 很慢)。spec 全在 `05_expanded_eval_set.md` §D2–D4。

**★ gpt-4o-mini 跨 backbone 決定性結果(2026-06-08)— write-time verdict 是失敗主因**:
- OpenAI key 已設(.env,sk-proj,164 字元,連線 OK)。benchmark 預設就是 OpenAI(`OPENAI_API_KEY`),現成 config `RAG_Agents/gpt-4o-mini/Structure_rag_gpt-4o-mini-mem0.yaml`。答題 LLM 由 `model` 欄位路由(agent.py:492 `'gemini' in model` → gemini,else → OpenAI)。
- **三層隔離**(extraction 凍結同 gemini L2 cache、embedder text-embedding-004 同、檢索同,只換 update+answer LLM):**as-is(預設 prompt 抽 0 fact)16% → clean gpt-4o-mini 48% → clean gemini 93%**。新建 config `Structure_rag_gpt-4o-mini-mem0_l2_clean.yaml`(llm provider openai gpt-4o-mini + embedder vertexai;provider 覆寫是條件式 `if llm.provider==vertexai`,openai 不被覆寫)。
- **write-time 毀損率(cross-chunk 145,final-store≠new_only):gpt-4o-mini 86/145 (59%) vs gemini 6/145 (4%)**;gpt-4o-mini 52 個 neither(新舊全毀)、store 縮到 181(gemini 297)。→ **同 fact 同檢索只換裁決 LLM 就 93→48%,失敗確定在 write-time verdict 非 extraction/answer**。
- **慢的主因(使用者揪出)**:Vertex embed **2786ms/call** vs OpenAI **758ms**;mem0 逐 fact embed + O(n²) update 輸出 → gpt-4o-mini 6k ingest ~30-40min。**32k+ 要換 OpenAI embedder**(text-embedding-3-small)。
- **論文框架收斂**(全在 `05_expanded_eval_set.md` §D5):打 write-time query-agnostic 不可逆 verdict 毀損 query 所需版本(old_only/neither/both = H1/H2/A4;排除 same-chunk)。誠實點:gpt-4o-mini 毀損=推理錯+格式錯(hallucinated-id drop,皆源於不可逆重生記憶清單設計);真天花板=LCA per backbone(非 mem0);our method store 變大需承認。核心 insight:write-time verdict 是難題(弱 model 崩)、query-time resolution 是易題(弱 model 也行)→ 換難為易 → 便宜 model 接近天花板。Prototype:非破壞 ingestion(全 ADD+ingestion-order metadata)+ query-time LLM 語意裁決(時序當訊號)。Title 草案:*Resolve When Asked: Query-Time Conflict Resolution for Non-Destructive LLM Memory*。
- **待辦**:(1) gpt-4o-mini LCA per-backbone 天花板;(2) 拆 86 毀損=推理 vs 格式;(3) OpenAI-embedder 版跑 32k+;(4) prototype 在戰場驗證。

**★★ our method 最小 prototype 強力正面結果(2026-06-09)**:
- prototype = 非破壞 ingestion(extraction cache 全 455 fact 留 + ingestion-order index)+ query-time resolution(retrieve top-100 → 答題 LLM 用最大 order 挑最新)。零 write-time update LLM。腳本 `prototype_qa.py`。
- **FC-SH 6k 官方 100(gpt-4o-mini 答題):mem0 48% → our method 96%(+48pp)**,超過 mem0 gemini(93%)、逼近 LCA gemini 天花板(99%),ingestion 不用 update LLM(更便宜)。
- **6k 戰場逐組救回**:mem0 old_only/neither(EM 0)→ prototype **100**;both(83)→ **100**;new_only 對照 100→96 不退步。
- **核心 insight 證實**:write-time verdict 是難題(同 gpt-4o-mini 崩 48%)、query-time resolution 是易題(96%)。「換難為易 → 便宜 model 接近天花板」成立。
- caveat:6k 單 trial、per-category N 小(各 2),需 32k/64k 戰場做統計力 + 多 trial;positioning(vs plain RAG=保留時序不破壞;vs LCA=retrieval 低成本可 scale);次要設計(解耦 LLM 偵測&解決)未做。
- 待辦:prototype 上 32k/64k 戰場、cost 量化、gpt-4o-mini LCA 天花板、次要設計、messier-conflict generality。產物 `logs/prototype_6k_{official,battlefield}_gpt4o.json`。

vendored mem0 非 git 追蹤,patch 記於 doc。相關:[[feedback_memagent_resume]] resume-safe。
