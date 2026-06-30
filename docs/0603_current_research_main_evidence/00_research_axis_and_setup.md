# mem0 失敗拆解 — 研究主軸、實驗設定與 log 規劃

> **目的**:把「mem0 在 FC-MH 為什麼失敗」拆成可歸因的 component-level 問題,並把每個 component 的**設定、定義、目的**釘死,讓之後每一步實作都有明確 why,而非無目的亂跑。
> **建立日期**:2026-06-03
> **最後更新**:2026-06-03
> **範圍**:mem0 **vector 模式**(非 mem0g,無 Neo4j / graph)。pipeline = [mem0/memory/main.py:187-316](../../mem0/memory/main.py#L187)。
> **上游脈絡**:[[../baseline_methods/CRITICAL_FINDINGS_2026-05-29_evening]]、[[../experiments/log_schema]]、[[../paper_draft/progress_report_2026-06-01]]

---

## 0. 研究主軸(一句話)

> 把 mem0 在 FC-MH 的 end-to-end 失敗,**歸因到 ingestion pipeline 的三個 component 中的哪一步**,扣除掉「結構上本來就偵測不到」的 noise(same-chunk 衝突、extraction 漏抽),專注剩下的真失敗,判斷是 **candidate retrieval(假設 2)** 還是 **update decision(假設 3)** 主導。

這是為了支撐核心主張之一:mem0 的 **write-time 衝突偵測在長 context 失效**(母體池過大)。對齊 [[../paper_draft/research_core_claims_TODO_2026-06-01]] Claim 1。

---

## 1. mem0 ingestion pipeline 精確拆解

一個 chunk = 一次 `memory.add()`。pipeline 三步(對應我們的三個 component):

```
Component 1 — Extraction          [main.py:197-218]
  整個 chunk 文字 → 1 次 LLM call → new_retrieved_facts = [新事實字串, ...]

Component 2 — Candidate retrieval  [main.py:222-236]
  for 每個 new_fact:
      existing = vector_store.search(new_fact, limit=5)   # top-5,只搜「已寫入 store」的記憶
      retrieved_old_memory += existing
  retrieved_old_memory = 去重(所有 new_fact 的 top-5 聯集)   # = 候選池

Component 3 — Update decision      [main.py:245-263]
  1 次 LLM call get_update_memory_messages(候選池, 全部 new_facts):
      → 每個 new_fact 判 ADD / UPDATE / DELETE / NONE
  套用結果寫入 store                [main.py:265-315]
```

| Component | 程式碼 | 失敗假設 | 機制重點 |
|---|---|---|---|
| **1 Extraction** | [main.py:197-218](../../mem0/memory/main.py#L197) | GT 衝突事實沒被抽出/抽錯 → 後面全無機會 | 一次 call 抽整 chunk;chunk 越大越易漏抽 |
| **2 Candidate retrieval** ⭐ | [main.py:222-236](../../mem0/memory/main.py#L222) | 歷史變長→store 變大→舊版本擠不進 top-5→LLM 沒看到→只 ADD | **top-5 hard limit**;只搜已寫入 store(跨 chunk 才搜得到) |
| **3 Update decision** | [main.py:245-263](../../mem0/memory/main.py#L245) | 舊版本進候選了,但 LLM 因參數知識把反事實當「舊/錯」→不 UPDATE | 整池 + 全部新 fact 一次判;update prompt = new-vs-既有池 |

> Update prompt 結構見 [mem0/configs/prompts.py:61-205](../../mem0/configs/prompts.py#L61)(`DEFAULT_UPDATE_MEMORY_PROMPT`,ADD/UPDATE/DELETE/NONE 四動作)。

---

## 2. 實驗設定 — 每項都標 定義 + 目的

| 設定項 | 值 | 定義 / 目的 |
|---|---|---|
| **Extraction prompt** | 我們改過版([methods/mem0_fc_prompt_fix.py](../../methods/mem0_fc_prompt_fix.py)) | **只移除** upstream `FACT_RETRIEVAL_PROMPT` 兩個「拒收宣告式知識」的 few-shot(`There are branches in trees → []`)。**目的**:讓 mem0 在 FC 通用知識上能正常抽 fact(OOB 會抽 0 筆),這是讓 pipeline 能跑的最小必要修改,其餘 prompt 不動以保持與 upstream 對齊。 |
| **mem0 內部 LLM temp** | **0**(diagnostic 階段) | mem0 upstream 預設 = **0.1**([mem0/configs/llms/base.py:17](../../mem0/configs/llms/base.py#L17))。**目的**:Component 1 & 3 是 mem0 內部 LLM 的決策;diagnostic 要 deterministic、單 trial 可重現,才能把「這步失敗」歸因為機制而非 sampling 雜訊。論文 disclose「diagnostic 用 temp=0,benchmark 預設 0.1」。 |
| **答題 LLM temp** | 0.7(benchmark 預設)| top-level agent yaml 的 temperature 只控制**最終答題 LLM**,在三個 component 下游,不影響偵測歸因。保持預設即可。 |
| **chunk_size** | **512**(非預設 4096)| **定義**:對話歷史切成 ~512 token 的 chunk,逐 chunk `add()`。**目的**:(a) extraction recall — 已知 4096 單次要抽太多 fact 會漏抽;(b) per-chunk 可分析性 — 能逐 chunk 對齊 GT 看每步行為。與 mem0 paper 預設不同,論文註明此 deviation 與理由。 |
| **Chunker** | **fact-aware**(`chunk_facts_by_line`)| **定義**:FC 是 numbered fact list,以「行=一筆 fact」為單位打包,序號永不離身。**目的**:取代 prose 用的 `chunk_text_into_sentences`(會在邊界把 `<seq>.` 留前一 chunk)。只路由 factconsolidation,其餘 dataset 不動。見 §8 2026-06-03 chunker 決策。 |
| **記憶模式** | vector(**非 graph/mem0g**)| 不啟用 Neo4j。pipeline 只走 `_add_to_vector_store`,無 G4 graph path,歸因單純。 |
| **Component 1 深究程度** | 先用 512 壓住,不深究 | extraction 失敗與長度/參數記憶無關,是 extraction 本身問題;本研究主攻 Component 2、3。 |

---

## 3. 結構性 noise — 必須先標記排除

### 3.1 Same-chunk 衝突(偵測不到是「正常」的)

Component 2 的候選池來自 `vector_store.search()`,只搜**先前 chunk 已寫入 store** 的記憶;同 chunk 的另一個新 fact 此刻**還沒寫進 store**(要等 [main.py:274](../../mem0/memory/main.py#L274) `_create_memory`),所以兩者搜不到彼此。雖然兩個衝突 fact 都在 `new_retrieved_facts` 一起進 update prompt,但 update prompt 做 **new-vs-既有池** 比對,不做 new-vs-new 仲裁 → 結果通常**兩個都 ADD**,偵測不到。

→ **這是 mem0 結構限制,不是我們要研究的失敗**。處理:用 chunk 邊界 × MQuAKE align 算出「該題 gt_new 與 chain_old 是否落在同一 chunk」,標 `same_chunk_conflict=True`,**從 Component 2/3 分母剔除**。

### 3.2 Extraction 漏抽

Component 1 沒抽出 GT 衝突 fact 的 hop → 標記排除,不算進 Component 2/3。

---

## 3.5 Extraction 稽核 = 後續分析的前提(gate)

extraction log 讓我們先界定 denominator:**只有「正確被抽取」的 GT fact 才有資格往下談 candidate / update**。extraction 稽核必須**先跑、當 gate**,否則會把「extraction 就沒抽到」誤算成 candidate miss 或 update 誤判。

每筆比對分四種狀態(不只 match/no-match):

| 狀態 | 定義 | 後續處理 |
|---|---|---|
| **matched** | 抽取 fact ↔ context fact 一對一 | 進入 Component 2/3 分析 |
| **missing** | context GT fact 無對應抽取 | **Component 1 漏抽 → 從 C2/C3 分母剔除** |
| **hallucinated** | 抽取 fact 無對應 context | 獨立計量(store 污染源:可能變他人候選/被誤 UPDATE) |
| **distorted** | 有對應但語意改壞(丟限定詞/換 object) | 最隱蔽且對衝突偵測最致命,單獨標記 |

**比對方法定義**:序號已被剝(§8 T2 發現)、文字被改寫 → 不可用序號或 exact string,須**內文語意比對**。**沿用 [align_mem0_mquake.py](../../analysis/align_mem0_mquake.py) 既有的「抽取 memory ↔ GT 內文比對」邏輯**,不另立一套(待確認其 matcher 細節:exact-normalize / embedding-threshold / LLM-judge)。

---

## 3.6 ★ Write-time 衝突解決稽核(主分析,query-independent)

> **焦點(使用者 2026-06-03 釐清)**:只看「query 進來之前,記憶建構時」衝突解決失敗在哪。**與 SH/MH 無關**(6k context SH/MH 共用 md5 一致;write-time ingestion 與 query 無關)。

**前提性質**:
- GT 衝突對來自 [mh_512_mquake_analysis.json](../../analysis/results/mh_512_mquake_analysis.json) has_pair hop:`(old_seq, old_fact_text)` → `(gt_seq, gt_fact_text)`,**gt_seq > old_seq 恆成立** → 舊版本必在較早或同 chunk ingest。
- fact-aware chunker → extraction **per-chunk 1:1 in-order**(數量 `[38,39,37,...]` == chunk seq 區間數;spot-check 逐筆對上)→ `seq → 抽取fact文字` 由位置推出;candidate top5 的 `text` = store 文字 = 抽取文字 → **exact 比對,不需 fuzzy**。

**每個 GT 衝突對落唯一 bucket**:

| bucket | 判定(log 來源) | 對應假設 |
|---|---|---|
| **same-chunk**(排除) | chunk(old_seq)==chunk(new_seq) | old 尚未進 store,結構上偵測不到 |
| **H1 candidate-miss** | new_fact 的 top-5(`candidate_pool.jsonl`)**不含** old | 假設 1:舊版本擠不進 top-5 → 只 ADD |
| **H2 update-refuse** | old **在** top-5,但 `update_decision.jsonl` 未對它 UPDATE/DELETE | 假設 2:看到衝突卻因參數知識不願覆蓋 |
| **resolved** | old 在 top-5 且被 UPDATE/DELETE | 正確解決 |

→ 輸出:衝突對總數、四 bucket 占比。**直接回答「write-time 衝突解決失敗主因是 H1 還是 H2」**。延伸 32k/64k 看 H1 占比是否隨 ctx 上升(「池過大」)。

> 腳本暫稱 **A-WT**(write-time conflict-resolution audit)。下方 §4 query-side 三向歸因降為**輔助分析**(連到 EM 用)。

---

## 4. 三向歸因 — 每個 has_pair hop 落唯一 bucket(輔助:連到 EM)

排除 §3 noise 後,對每個「該有衝突對」的 hop:

| Bucket | 條件 | 歸因 |
|---|---|---|
| **C2 fail** | chain_old **沒進**任何 new_fact 的 top-5 候選池 | Candidate retrieval miss(假設 2)|
| **C3 fail** | chain_old **進了**池,但 update verdict ≠ UPDATE/DELETE | Update decision 誤判(假設 3,多為反事實 vs 參數知識)|
| **success** | 進池 + 正確 UPDATE/DELETE | 偵測成功 |
| (excluded) | same_chunk_conflict / extraction miss | 結構 noise,不計分母 |

預期沿 context 長度(6k→32k→64k)看 C2 占比上升 = 直接支撐「母體池過大」。

---

## 5. Log 規劃 — 接續既有 log_schema,補缺口

既有 [[../experiments/log_schema]] 的 **Layer A** 只存 **Component 3 的最終結果**(`vector_results.results` = 已決定的 ADD/UPDATE/DELETE)。**Component 1 原始抽取、Component 2 候選池都沒被 dump** — 這是要補的 instrumentation。

| Component | 要 log 的資料 | 插點 | 現況 |
|---|---|---|---|
| **1 Extraction** | `new_retrieved_facts`(update 前的原始抽取)| [main.py:215](../../mem0/memory/main.py#L215) 後 | ❌ 沒存 |
| **2 Candidate** ⭐ | 每個 new_fact 的 top-5(id+text+**score**+`is_gt_chain_old`)、`store_size_before`、去重後池大小 | [main.py:225-236](../../mem0/memory/main.py#L225) | ❌ **完全沒存 → 假設 2 關鍵缺口** |
| **3 Update** | update LLM **完整 prompt + raw response**(不只 parse 後 event)| [main.py:245-263](../../mem0/memory/main.py#L245) | ⚠️ 只有 parse 後 event |

**Component 2 新增 log schema(每 chunk 一行 jsonl)**:

```json
{"chunk_id": 7, "store_size_before": 312,
 "per_fact_candidates": [
   {"new_fact": "...", "top5": [
       {"rank": 1, "id": "u1", "score": 0.81, "text": "...", "is_gt_chain_old": true},
       {"rank": 2, "id": "u2", "score": 0.74, "text": "...", "is_gt_chain_old": false}
   ]}],
 "pool_size_after_dedup": 23}
```

> `is_gt_chain_old` 在跑時可能還不知道(要 align 後才標),先 dump id+text+score,事後用 [analysis/align_mem0_mquake.py](../../analysis/align_mem0_mquake.py) 補標。

---

## 6. 既有可接續資產

- 對齊:[analysis/align_mem0_mquake.py](../../analysis/align_mem0_mquake.py)(Layer A/B/C × MQuAKE GT → per-hop)
- 三向拆解:[analysis/compute_3way.py](../../analysis/compute_3way.py)、[analysis/compute_detection_action.py](../../analysis/compute_detection_action.py)
- 跨方法 Claim A/B:[analysis/compute_claim_AB.py](../../analysis/compute_claim_AB.py)
- run 設定:`configs/agent_conf/RAG_Agents/Gemini/Structure_rag_mem0_gemini-3.1-flash-lite_chunk512_temp0.yaml`

---

## 7. TODO(按依賴序,邊做邊在 §8 記)

- [x] **T0** fact-aware chunker(`chunk_facts_by_line` + FC 路由)— 已實作+驗證,見 §8
- [x] **T1** 在 [main.py:222-263](../../mem0/memory/main.py#L222) 加 Component 2 候選池 dump(env-gated,baseline-safe)— 見 §8 2026-06-03 T1
- [x] **T2** Component 1 extraction dump(`extraction.jsonl`)— 完成+smoke 驗證,見 §8
- [x] **T3** Component 3 update dump(`update_decision.jsonl`,含 hallucinated_ids)— 完成+smoke 驗證,見 §8
- [ ] **T4** same-chunk 衝突標記腳本(chunk 邊界 × MQuAKE align)
- [x] **T5** 跑 FC-MH 6k(fact-aware + text-embedding-004 + temp=0,vector)— **EM 62%**(舊 chunker 52%,+10pp),三層 log 正常。見 §8
- [ ] **T5b** mem0g / HippoRAG 用 fact-aware chunker 重跑 FC-MH 6k(公平比較,因 chunker +10pp)
- [x] **A-WT** ★ write-time 衝突解決稽核(§3.6,主分析)— 6k:resolved 98.6%,H1/H2 各 0.7%。**6k write-time 非瓶頸**。見 §8
- [ ] **T7/A-WT@32k/64k** ★ 延伸長 ctx 跑 + A-WT,測 H1-miss 是否隨池上升(「池過大」核心驗證)
- [ ] **A-EXT** extraction 稽核(§3.5):比對抽取 fact ↔ GT,出 matched/missing/hallucinated/distorted 四態 → 界定 C2/C3 分母(gate)。沿用 align_mem0_mquake.py 比對邏輯
- [ ] **T6** 三向歸因(§4),扣除 §3 noise + A-EXT missing,出 C2/C3 占比
- [ ] **T7** 延伸 32k/64k 看 C2 占比 trend(支撐「池過大」)

---

## 8. 工作日誌(邊實作邊記:做了什麼 / 為何 / 結果)

> 格式:`### YYYY-MM-DD HH:MM — Tn 標題` + 目的 / 設定 / 結果 / 下一步

### 2026-06-03 — 建立本文件
- **目的**:把研究主軸與三 component 設定釘清楚,之後每步實作都有明確 why。
- **產出**:本文件(pipeline 拆解、設定定義、noise 排除原則、log 規劃、TODO)。
- **下一步**:T1 — 先補 Component 2 候選池 log(最關鍵缺口)。

### 2026-06-03 — T1 Component 2 候選池 instrumentation
- **目的**:驗證假設 2「歷史變長→舊版本擠不進 top-5」需要的唯一資料,upstream 完全沒 dump。
- **設定 / 定義**:在 [mem0/memory/main.py:222-263](../../mem0/memory/main.py#L222) 的候選迴圈加側錄。
  - **gate**:環境變數 `MEM0_CAND_LOG_DIR`。**未設 = no-op,行為與 upstream byte 完全一致**(只多一次 `os.environ.get` 與兩個 `is not None` False 判斷)→ baseline 零污染、可逆。
  - **不改決策邏輯**:純記錄,ADD/UPDATE/DELETE 結果不變。
  - **輸出**:`$MEM0_CAND_LOG_DIR/candidate_pool.jsonl`,每次 `add()`(=每 chunk)一行:
    `{user_id, n_new_facts, pool_size_after_dedup, per_fact_candidates:[{new_fact, top5:[{rank,id,score,text}]}]}`。
  - user_id 已編入 `context_{id}_{sub_dataset}`(見 [agent.py:882](../../agent.py#L882)),post-hoc 可分離各實驗。
- **決策記錄**:用 env-gate side-channel(非改回傳值 / 非 monkey-patch),理由 = baseline byte-identical + 最少侵入。`store_size_before` 暫不記(需額外 vector_store 查詢,成本),先用 `pool_size_after_dedup` 當代理,日後需要再補。
- **Reproducibility 注意**:vendored mem0 非 git 追蹤([[../experiments/log_schema]] §5),此 patch 已記錄於此;`import os` 也一併加入 main.py 頂部。
- **驗證**:`ast.parse` 語法通過。**尚未實跑驗證輸出**(待 T5 一起)。
- **下一步**:T2/T3 同模式補 Component 1/3 log,或先做 T4 same-chunk 標記。

### 2026-06-03 — Smoke 驗證 T1(通過)
- **目的**:正式跑前,先確認 T1 的 log 真的正確產出(不是改完就盲跑)。
- **腳本**:[scripts/smoke_t1_candidate_log.py](scripts/smoke_t1_candidate_log.py)。沿用既有 mem0 建構方式(Vertex Gemini LLM + L1 prompt),ingest FC-SH 6k 前 4 chunk,temp=0。
- **結果**:`RESULT: ALL PASS`。`candidate_pool.jsonl` 4 行(=4 chunk),schema/top5 欄位齊全,候選路徑確實被走到。

  | chunk | n_new_facts | pool_after_dedup | top5 rows |
  |---|---|---|---|
  | 0 | 38 | **0** | 0 |
  | 1 | 38 | 36 | 190 |
  | 2 | 37 | 65 | 185 |
  | 3 | 37 | 78 | 185 |

  → chunk0 pool=0(store 空,全 ADD = §3.1 same-chunk noise 的雛形);之後池隨 chunk 累積(36→65→78),正是「池過大」假設要量測的對象。
- **附帶發現(Component 3 線索)**:update 步驟出現 `Error in new_memories_with_actions: '34'/'36'`([main.py:312](../../mem0/memory/main.py#L312)) — update LLM 回傳超出候選池範圍的 id(UUID hallucination,upstream 已知,已被 catch)。與 T1 無關,但 **T3 要記 raw response 才能量化這類 update 端失敗**。
- **⚠️ Embedder(重要 rigor,已定案)**:假設 2(chain_old 是否進 top-5)是 embedder 的函數,所以**凡是要解讀候選數字的 run,embedder 必須與對齊 setup 一致**。決定:smoke 也直接用正式的 embedder,讓 smoke 零落差 mirror production。
  - 正式 / smoke 一致用:**[Vertex `text-embedding-004` 768 維](../../configs/agent_conf/RAG_Agents/Gemini/Structure_rag_mem0_gemini-3.1-flash-lite_chunk512_temp0.yaml#L21)**,走 [methods/mem0_vertex_adc_embedder.py](../../methods/mem0_vertex_adc_embedder.py),redirect 方式與 [agent.py:322-323](../../agent.py#L322) 相同。
  - 釐清:`text-embedding-004` **不是** mem0 upstream 預設(那是 OpenAI text-embedding-3-small);它是我們 Plan A 對齊選的。對齊要對的是後者。

### 2026-06-03 — Smoke 用正式 embedder 重跑(text-embedding-004,通過)
- **目的**:讓 smoke 與正式 run 用同一顆 embedder,零落差。
- **改動**:[smoke 腳本](scripts/smoke_t1_candidate_log.py) embedder 改 `vertexai/text-embedding-004/768`,加 `EmbedderFactory` redirect。
- **結果**:`RESULT: ALL PASS`。per-chunk pool 0→36→62→78(與 MiniLM 版趨勢一致)。**score 由 MiniLM ~0.35 升到 ~0.64** — 同機制、不同相似度排序,正是「候選結果 embedder-sensitive」的直接證據,確認正式跑非用這顆不可。
- **狀態**:T1 instrumentation 設計 + 驗證(含正式 embedder)全部完成,可進 T2/T3。

### 2026-06-03 — Chunk 邊界檢查(發現序號分離問題)
- **觸發**:跑前先確認 chunk 切割是否把 fact 序號與內文切到不同 chunk。
- **方法**:實跑正式 chunker `chunk_text_into_sentences`([utils/eval_other_utils.py:177](../../utils/eval_other_utils.py#L177))於 FC 6k context、chunk_size=512,檢查每個 chunk 邊界。
- **發現**:**每個 chunk 邊界把「下一筆 fact 的序號」留在前一個 chunk,內文跑到下一個**。例:
  - chunk0 尾 `...36. Hines Ward plays the position of cornerback. 37.`
  - chunk1 頭 `Frank Zappa died in the city of Los Angeles. 38. ...`(fact 37 內文無序號)
  - 12 chunk → 9/12 不從乾淨 fact 邊界開始;**~11 筆邊界 fact 的序號被分離**(~11/455)。
- **成因**:`nltk.sent_tokenize` 把 `37.` 當獨立句黏前句尾。
- **範圍**:這是 production chunker 行為 → 現有所有 mem0/mem0g/HippoRAG 結果共享;**chunk 內部** fact 不受影響,只有邊界那筆。
- **兩層次**:(a) 正式 chunker **內文完整**,只序號分離;(b) **本 smoke 用 naive tiktoken 硬切會連內文切壞** → smoke chunker 必須改用正式的 `chunk_text_into_sentences`。
- **是否有害**:取決 recency 訊號 = ingestion 順序(影響小,align 用內文比對)還是序號文字(則 ~11 筆壞)。**待決策**:見下方 Decision。
- **下一步**:依決策修 smoke chunker(必做)+ 決定 production chunker 是否改 fact-aware(每行一 fact,序號永不離身)。

### 2026-06-04 — 32k 整體 pipeline 分析(ingestion→query→SH failure)
- **⚠️ 過程抓到 GT 對齊 bug**:初版 32k SH query 分析把 6k 的 sh_512 remap 當 32k GT → gt_retrieved 7/91 矛盾。查證:**FC-SH queries 隨 context 長度不同**(6k qid0=pesäpallo / 32k=basketball,完全不同 100 題)。修正:`build_sh_gt_for_run.py` 用 run 自己的 query+answer 對 MQuAKE-CF 建 GT(6k 重建與 sh_512 **100/100 一致** sanity 通過)。**write-time 分析不受影響**(用 FULLPAIRS,query-independent)。
- **Write-time(A-WT 837 對 + audit_deviation)**:resolved 98.6→**93.1%**;**H1-miss 1→29**(使用者假設證實:舊版被語意相近 distractor 擠出 top-5);**H2-refuse 1→28**;same-chunk 16→13(占比 10%→1.6%);fact-fate STORED 1435/SUPERSEDED 810/DROPPED 63/DELETED 2;偏差 65=10 same-chunk + **55 non-same-chunk**(6k 是 10+5)。→ **失敗主因從 same-chunk 轉為 H1/H2**。
- **SH query(正確 GT)**:EM 90%,95 CORRECT-ingestion(90 對 + 5 inference-fail)+ 5 BAD-SUP(反事實被 superseded,write-time)。5 inference-fail=3 空輸出(thinking)+2 cross-fact(qid23/64)。5 BAD-SUP:qid8/9/87/95/98。
- **結論**:6k 結構問題(A1/A2/A3)在 32k **持續且部分放大**(A2 H2-refuse 1→28、A3 cross-fact 持續、A1 轉 H1-miss)→ 非獨立出現。詳見 [01](01_mem0_fc_setup_and_results.md) §4.4。
- 新增 GT/腳本:`sh_{6k,32k}_RUN_gt.json`、`build_sh_gt_for_run.py`、`sh_32k_conditional.json`、`mh_32k_l2/awt_result.json`。

### 2026-06-04 — ★ 乾淨 L2 四組就緒 + EM matrix
四組 {SH,MH}×{6k,32k} 全用 L2+frozen cache 跑完,extraction 100% 完整、SH/MH 逐字一致(已驗證)。

| | 6k | 32k | Δ |
|---|---|---|---|
| **MH** | EM **64%** | EM **39%** | −25pp |
| **SH** | EM **92%** | EM **90%** | **−2pp** |

(L1→L2 修復:MH 32k 29→39、SH 32k 74→90,補漏抽 fact 之效。6k 變化小因 6k 本就近完整。)
- **🔑 SH 衝突解決對 ctx 長度穩健(92→90,−2pp)**:extraction 補完後,mem0 conflict resolution 本身在 scale 下穩。MH −25pp 是多跳 retrieval confound(非衝突解決)→ 印證使用者「衝突解決主軸專注 SH」的決定。
- 資料路徑:logs/{mh,sh}_{6k,32k}_l2/(三層 log);outputs/...factaware-l2{,-32k}/(query 結果);query 分析腳本 query_pipeline_analysis.py。

### 2026-06-04 — 計數法澄清:event view ≠ fact-fate view(不可混用)
> 為什麼前面 NONE/dropped 一下 10、一下 12、一下 13 → **誤用 event 算式去數 fact**。

- **event view**(直接可觀察,答「update prompt 每 chunk 做什麼」):per-chunk ADD/UPDATE/DELETE。6k L2 合計 ADD 299 / UPDATE 144 / DELETE 2。
- **但 event 與 fact 非 1:1**,故**不能用 `455−events` 數「多少 fact 沒進 store」**:
  1. UPDATE/DELETE 作用在**舊 candidate**(早先 chunk 的 fact),非當前 chunk 的 new fact;
  2. 一對衝突的兩 event 在**不同 chunk**(舊版 ADD@chunkK、新版 UPDATE@chunkK+n);
  3. 污染/over-fire 產生「event 在、內容對不到乾淨 fact」。
  → 用 event 相減會差 1~3(10/12 都是錯的)。
- **fact-fate view**(唯一自洽的 455 帳,答「每筆 fact 最後在哪」):逐筆檢查內容是否在最終 store → STORED 296 / SUPERSEDED 144 / DROPPED 13 / DELETED 2 = 455。**DROPPED=13 是正確的「未進 store」數**。
- **規則**:問操作行為看 event;問 455 筆下落看 fact-fate。兩者不可用算式互換。

### 2026-06-04 — ★ L2 canonical write-time 盤點 + 逐筆偏差稽核(6k)
> 取代先前 L1 數字為 canonical(L2 乾淨 cache 抽取)。腳本 [scripts/full_writetime_accounting.py](scripts/full_writetime_accounting.py) + [scripts/audit_deviation.py](scripts/audit_deviation.py)。資料:mh_6k_l2(SH/MH 共用同 ingestion)。

**Context**:455 = 161 衝突對(322)+ 133 non-pair。161 對中 **16 same-chunk** + 145 cross-chunk。

**計數法注意**:Layer A 的 **event 數**(ADD 299 / UPDATE 144 / DELETE 2)會把「先 ADD 後 DELETE」的 fact 重複計,故不可用 `455−events` 當「未存入」數(會少算)。正確用**每筆 fact 唯一最終命運**(mutually exclusive,總和=455):

| 最終命運 | Ideal(same-chunk 兩版都 ADD)| L2 Actual | Δ |
|---|---|---|---|
| STORED(內容留 store)| 310 | **296** | −14 |
| SUPERSEDED(loser 被新版覆蓋)| 145 | **144** | −1 |
| DROPPED/NONE(從未存入)| 0 | **13** | +13 |
| DELETED | 0 | **2** | +2 |
| 合計 | 455 | 455 | |

→ **偏差 = DROPPED 13 + DELETED 2 = 15 筆**(10 same-chunk + 5 cross-chunk)。(註:先前 session 寫的「12 筆=10 NONE+2 DELETE」是用 event 計數法之誤,canonical 為 15。)
- Layer A events:ADD 299 / UPDATE 144 / DELETE 2。UPDATE correctness(144):correct 140 / no-op 1 / over-fire-single 1(seq17)/ wrong-dir 1。
- 衝突對 cross-chunk 145:**resolved 143(98.6%)**、H1-miss 1、H2-refuse 1。

**★ 最終 DB 狀態組成 vs 理想(role × fate,按最終狀態讀)**:每個最終桶由哪些「應有角色」組成 → update component 衝突解決失敗的完整觀察。腳本 [scripts/audit_deviation.py](scripts/audit_deviation.py)。

| 角色 (n) | STORED | SUPERSEDED | DROPPED | DELETED | ideal 終態 |
|---|---|---|---|---|---|
| single (133) | 132 | 1 | 0 | 0 | STORED |
| loser-cross (145) | 1 | 142 | 0 | 2 | SUPERSEDED |
| winner-cross (145) | 141 | 1 | 3 | 0 | STORED |
| loser-same (16) | 12 | 0 | 4 | 0 | STORED |
| winner-same (16) | 10 | 0 | 6 | 0 | STORED |
| **直欄合計** | **296** | **144** | **13** | **2** | (455) |

- **STORED 296**(=最終 DB 記憶數,ideal 310):single 132 + **winner-cross 141(新版經 UPDATE 存入,STORED 最大宗)** + loser-same 12 + winner-same 10 + loser-cross 1(H1-miss 殘留,不該在)。→ **STORED 不只「單一+same-chunk」,主體是 cross-chunk 新版**。
- **SUPERSEDED 144**(ideal 145 全 loser-cross):142 正確 + single 1(over-fire 誤覆蓋 seq17)+ winner-cross 1(wrong-dir 污染)。
- **DROPPED 13**(ideal 0):winner-cross 3(含 seq77 H2-refuse)+ loser-same 4(丟世界留反事實=方向對)+ winner-same 6(丟反事實留世界=**H2**)。
- **DELETED 2**(ideal 0):loser-cross 2(seq37/84,刪舊達成正確結果)。

**🔑 逐筆稽核推翻「same-chunk = both ADD」假設**:同 chunk 內新舊兩版**都在 new_retrieved_facts**,update LLM 一起看到,常**去重成一版(另一版判 NONE)**。16 same-chunk 拆解:
- **6 對 both ADD**(兩版都留)
- **6 對 留世界事實、丟反事實**(world ADD / counterfactual NONE)← **= H2 參數偏好在 write-time**!
- **4 對 留反事實、丟世界事實**(正確方向)

→ **重要修正**:H2(參數覆蓋)**確實出現在 write-time,但只在 same-chunk**(新舊同時到、無 ingestion-order recency 訊號→LLM 回退靠世界知識,6/10 留錯世界事實)。cross-chunk 有順序訊號故 H2 不發生(145 對僅 1 H2-refuse=seq77 Stephen Crane)。

**偏差具體清單(15 筆 = 13 NONE/dropped + 2 DELETE,非全部 same-chunk:10 same-chunk + 5 非)**:
- NONE 反事實(world 被留):seq34/36/43/49/126/142(same-chunk),seq50/77/135(cross-chunk,77=H2-refuse)
- NONE 世界事實(反事實被留):seq156/163/237/289(same-chunk)
- DELETE 世界事實(替代式正確解決:刪舊+存新):seq37 Frank Zappa LA、seq84 Laura Bush(⚠️ seq84 world DELETE + seq135 counterfactual NONE → Laura Bush 兩版皆失,異常)

### 2026-06-04 — ★ FC-SH 6k query pipeline(條件式:依 ingestion 結果分組)
> 使用者框架:每題依「所需記憶在 ingestion 是否被正確處理」分組,再各看 retrieval+inference。腳本 [scripts/sh_query_conditional.py](scripts/sh_query_conditional.py)。SH=單跳,無多跳 confound→純衝突解決。

| Ingestion 結果 | n | EM | gt 取回 | 舊版洩漏 |
|---|---|---|---|---|
| **CORRECT**(新進舊除)| 93 | 89/93 | **93/93** | 0/93 |
| **DROPPED**(新版被丟)| 4 | **0/4** | 0/4 | 4/4 |
| **STALE**(新舊都在)| 3 | 3/3 | 3/3 | 3/3 |

**⚠️ 更正(2026-06-04 二次)**:初版用了 sh_512 的 `error_type`/`model_output`(舊 HippoRAG run 殘留欄位)→ 誤判「EM 假象」「qid66 答 politician=H2」。改用本 run 實際 `results.output` 後 drill(`detail_cases.py`):

**8 個 nominal 失敗(真實 L2 輸出)**:
| 組 | qid | gt(反事實) | 模型實際輸出 | 性質 |
|---|---|---|---|---|
| DROPPED | 7 | Muay Thai | American football(舊) | write-time 丟反事實(seq50 winner-cross×DROPPED) |
| DROPPED | 34/42/52 | Taipei/cornerback/Connachta | 答舊世界事實 | write-time 丟反事實(winner-same×DROPPED ×3) |
| CORRECT-ingest | 66/89/97 | journalist/... | **''(空輸出)** | gemini 生成 artifact(completion_tokens>0 卻 parse 空) |
| CORRECT-ingest | 1 | The Fairly OddParents | 'Vito Corleone' | 幻覺 |

- **更正結論**:**衝突解決可歸因失敗 = 4(全 write-time 丟反事實)**;另 4 為**模型生成問題(3 空輸出+1 幻覺),與衝突解決無關、非 H2**。初版「100% H2」「3 EM 假象」均錯。
- **無 retrieval 問題**(單跳 gt STORED 必取回;CORRECT 組 93/93 取回、0 洩漏)。
- **STALE 3 全答對**:模型選後列新版(retrieved[0]舊/[1]新)。
- **序號不匹配發現**:FC user_message 模板含「用較大序號解衝突」,但 mem0 記憶無序號 → 規則 inert(見 [01_mem0_fc_setup_and_results.md](01_mem0_fc_setup_and_results.md) §5)。
- **空輸出待查**:gemini-3.1-flash-lite 對 3 題回空,疑 safety/recitation,非 prompt 設計(prompt 無「無記憶回空」指示,且該題記憶有答案)。
- 詳見乾淨版 [01_mem0_fc_setup_and_results.md](01_mem0_fc_setup_and_results.md) §4.3。

### 2026-06-04 — Query pipeline 分析(6k SH/MH,L2 cache 乾淨資料)
> 腳本 [scripts/query_pipeline_analysis.py](scripts/query_pipeline_analysis.py)。把每題拆 retrieval(GT hop-facts 是否全取回 / 舊版是否洩漏)× inference(取回後答對否)。EM:MH 6k **63%**、SH 6k **92%**(L1 84%→L2 92%,補 chunk4 洞)。

**MH 6k(37 失敗)拆解**:
| 來源 | n | 占失敗 |
|---|---|---|
| **retrieval-miss**(GT 沒進 top-100)| **23** | **62%** |
| inference-fail(取回乾淨卻答錯)| 12 | 32% |
| stale-leak(舊版洩漏致錯)| 2 | 5% |

- **🔑 主瓶頸 = retrieval-miss(多跳)**:不在 write-time、不在 inference。隨 hop 惡化:**2-hop 25% / 4-hop 47%** miss。多跳中間 hop fact 與 query 語意不近 → top-100 取不到 → 鏈斷。
- **🔑 H2 確認且定位於 inference**:12 個 inference-fail 中 **9 個 error_type=older_fact**(取回只有反事實新版、無舊版洩漏,但 LLM 用**參數知識**答出真實世界舊答案)。= 使用者假設 2,發生在**最終答題 LLM**,非 write-time(mem0 update prompt 結構性繞過)。另 2 entity_confused、1 hallucination。
- **🔑 write-time stale-leak 影響小**:old-leak 17/100(對上 write-time 17 same-chunk),但只 2 個真致錯 → write-time 殘留狀態對 query 衝擊有限,印證 6k write-time 非主因。
- **SH 6k(8 失敗)**:retrieval-miss 4 + inference-fail 4(單跳故 retrieval 幾乎全取回 96/100)。
- **待 32k 對照**:retrieval-miss / H2-inference 是否隨 store 與 hop 放大。

### 2026-06-04 — 解法:L2 knowledge-extraction prompt + frozen extraction cache
- **根因確認**(讀 [mem0/configs/prompts.py:14](../../mem0/configs/prompts.py#L14) FACT_RETRIEVAL_PROMPT):整個 prompt 定位是「**Personal Information Organizer**」抽 user 個人偏好/資訊,還明示「找不到相關就回空」。FC 是通用世界知識→LLM 合理判定「無個人資訊」→ 空。L1 只移 2 few-shot,**核心定位沒改**。
- **L2 修法**(使用者方向:讓對手公平、過程可分析):把定位改成「knowledge extractor,抽出每條陳述事實」([methods/mem0_fc_prompt_fix.py](../../methods/mem0_fc_prompt_fix.py) `make_l2_knowledge_prompt`)。**驗證**:對 L1 回空的 32k chunks 0/10/18/28/49 → L2 **100% 完整抽取**(37/39/37/34/35)。
- **Extraction cache**(使用者要求:SH/MH 共用同一份完整抽取):
  - [scripts/build_extraction_cache.py](scripts/build_extraction_cache.py):每 context 用 L2 抽一次,驗證完整(count==numbered facts),不足逐字 backfill,存 `analysis/results/extraction_cache_{6k,32k}.json`,key=numbered-fact lines 的 sha256(timestamp 無關)。**6k cache:455 facts,0 fallback**。
  - mem0 讀 cache(env `MEM0_EXTRACTION_CACHE`,[main.py extraction 段](../../mem0/memory/main.py#L198)):命中→用 cache,跳過 LLM;未設→原行為(baseline-safe)。
  - → 四組 run(SH/MH×6k/32k)讀同一 frozen cache → **extraction 完全一致且完整**,extraction 退出變因,下游 candidate/update 才能公平比較。
- **設計原則**:extraction 非研究對象,需完整+可重現+SH/MH 一致;disclose「mem0 預設 prompt 為個人助理設計,對通用知識不可靠,故改 L2 並 cache 凍結抽取以隔離下游元件比較」。
- **Cache scope + 序號剝除 rationale(使用者 2026-06-04 確認,重要公平性論點)**:
  - 6k cache→6k SH/MH;32k cache→32k SH/MH(各重新抽取,不混用)。
  - 抽取**完整但剝除序號**,對 mem0 正確且公平:
    (a) mem0 最終 inference prompt([agent.py:903](../../agent.py#L903) 純 "answer based on memories")**無序號規則**,與 LCA/RAG 的 rag_agent template([utils/templates.py:81](../../utils/templates.py#L81) 明寫「larger serial = newer」)不同;
    (b) mem0 recency 靠 **ingestion 順序**(後寫覆蓋先寫),fact 按序號順序 ingest→ 大序號=後 ingest=新,recency 已隱含於順序,不需序號在文字中;
    (c) 故剝序號對 mem0 無害且更貼合其設計。LCA 才需序號(一次看全 context 靠序號規則推理)。
- **狀態**:L2 yaml `..._factaware_l2.yaml`(use_l2_fc_prompt)、agent.py 接 L2、cache read 完成。**驗證中**:MH 6k L2+cache 跑確認 runtime key 命中+455/455;32k cache 建置中。通過後重跑四組。

### 2026-06-04 — ⚠️ BLOCKER:32k extraction 大量空抽取(L1 fix 不足)
- **發現**:掃描四組 extraction recall:
  - MH 6k **455/455**(乾淨)、SH 6k 414/455(chunk4 meta-summary 失敗 1 個)
  - **MH 32k 2055/2310**(7 chunks 全 0)、**SH 32k 1826/2310**(13 chunks 全 0)
- **性質**:0-fact chunk 的 raw_response = `{"facts": []}`(乾淨空抽取,非 API/parse 錯)。內容正常(numbered facts)卻回空 → mem0 `FACT_RETRIEVAL_PROMPT` 拒收宣告式知識的**殘留行為**,L1(移 2 few-shot)未根除。
- **部分系統性**:MH/SH 32k **共同失敗 chunk = 0,10,18,28,49**(內容觸發),其餘隨機(temp=0 仍有變異;chunk0 SH 37 vs MH 38 也是)。
- **影響**:32k 記憶缺數百筆 → write-time/query scaling 分析會被 extraction 洞**confound**,不可直接用。
- **與研究焦點關係**:使用者明確說 extraction **不是焦點**(只用 chunk512 壓住),主攻 candidate/update → 讓 extraction 可靠正是為了不污染下游。
- **待決策**(見 §下方 TODO / 對話):強化 extraction prompt(L2,deviation 但讓下游可分析)＋重跑 32k / retry-on-empty / 接受洞當 finding。

### 2026-06-04 — Run matrix 蒐集中(資料就緒,分析待後)
> 計畫:先把 {SH,MH}×{6k,32k} 四組 query pipeline 跑齊,再逐步分析(1) 32k ingestion (2) 各組 query-after pipeline。

| | 6k | 32k |
|---|---|---|
| **MH** | ✅ EM 62% | ✅ **EM 29%**(三層 log 64 行,Layer A 在) |
| **SH** | 🔄 跑中 | ⏳ 排隊(同一 launcher 串行) |

- MH 32k 完成:EM 62%→29%(query 側 scaling,大跌);末 chunk pool_after_dedup=157(與 6k 137 相近 → **pool SIZE 不是判別量,top5 內容/rank 才是**,待 A-WT)。
- SH runs:[scripts/run_sh_6k_32k.sh](scripts/run_sh_6k_32k.sh),重用 factaware yaml(SH/MH 由 dataset config 決定),sub_dataset+user_id 隔離;也開 write-time log 當 determinism 交叉驗證。
- **資料路徑**:logs/{mh_6k,mh_32k,sh_6k,sh_32k}/(三層 ingestion log);outputs/...factaware{,-32k}/Conflict_Resolution/(query 結果);GT:mh_{6k,32k}_FULLPAIRS_gt.json(全衝突對)。
- **待分析(逐步)**:32k write-time(A-WT 837 對 + full-accounting vs 6k);四組 query-time(retrieval→inference,含 H2)。

### 2026-06-04 — Context 組成(mapped to MQuAKE-CF)+ seq-gap 修正
- **seq-gap 修正(使用者指正)**:candidate 是 embedding cosine top-5,**與新舊在 ingestion 的距離無關**。H1 的對的變數 = 「真正舊版在 cosine 候選裡的 rank,被多少語意相近 distractor 擠下」,隨**衝突密度 × store 大小**變化。candidate_pool.jsonl top5 score/rank 正好量這個。先前我講 seq-gap 是錯重點。
- **權威分布**(腳本 [scripts/map_context_to_mquake.py](scripts/map_context_to_mquake.py),枚舉 9218 case 的 requested_rewrite 新/舊版,比對 context):

  | | 6k (455) | 32k (2310) |
  |---|---|---|
  | 衝突對(新+舊兩版都在) | **161 對 = 322 (70.8%)** | **837 對 = 1674 (72.4%)** |
  | old-only(新版不在) | 74 (16.3%) | 236 (10.2%) |
  | single(無 edit) | 59 (13.0%) | 400 (17.3%) |

- **重點**:32k distractor 不是單一事實,而是 **5.2× 的額外衝突對**(837 vs 161),密度幾乎不變(~72%)。
- **精修先前數字**:之前「133 non-pair」= 74 old-only + 59 真 single;161 對與 full-accounting「161 loser+161 winner」吻合(165 是 queried hop 數,含 4 個 gt<old 異常)。
- **對 32k 分析的啟示**:可分析全部 **837 對**(非只 165 queried)→ 對「H1/污染是否隨 store 放大」有最大統計力。待 32k 跑完用 candidate_pool top5 rank 直接測。

### 2026-06-03 — 洞察:H2(參數知識覆蓋)被 mem0 update prompt 結構性繞過 → 屬 query-time
- **觀察**:6k write-time H2-refuse 僅 1 例,幾乎觀察不到 LLM「因參數知識拒覆蓋反事實」。
- **原因**:`DEFAULT_UPDATE_MEMORY_PROMPT`([mem0/configs/prompts.py:61](../../mem0/configs/prompts.py#L61)) **結構上分離**「Retrieved facts(新)」vs「memory(既有)」,問的是「新 fact 要不要更新既有記憶」=**記憶管理**,不是「哪個為真」=真值仲裁。LLM 沒被放到「反事實 vs 參數知識」對決位置。
- **Reframe**:H2(參數覆蓋)更可能在 **query-time inference**——答題 LLM 拿到 retrieved memories(如 "Stephen Crane is the author")但世界知識說 Nietzsche,那裡才是參數覆蓋戰場。**H2 是 retrieval→inference 現象,非 write-time**。→ 後續 query-side 分析重點。
- **對應使用者下一步**:write-time scaling(H1/污染)走 32k;H2 走 query-time。

### 2026-06-03 — 完整 write-time 盤點(6k,全 455 筆命運分布)
> 使用者要求:不能只看 queried 165 對,要全 context 的完整 denominator(多少 pair/single、漏抽、operation 錯誤)。腳本 [scripts/full_writetime_accounting.py](scripts/full_writetime_accounting.py)。

**Context 組成(455 筆)**:165 權威衝突對(sh⊆mh)= 322 conflict-seq(161 loser + 161 winner)+ **133 single fact**。

**Extraction**:**455/455(100%)**,per-chunk 1:1 in-order,**0 漏抽**。

**Operations(Layer A applied)**:ADD 297 / UPDATE 146 / DELETE 0 / **NONE 或 dropped 12**。

**按角色的命運**:
| 角色 | 數量 | 命運 |
|---|---|---|
| single | 133 | **全 ADD,0 over-fire** ✓ 乾淨 |
| 衝突對(cross-chunk) | 148 | 146 resolved(winner UPDATE 覆蓋 loser)/ 1 H1-miss / 1 H2-refuse |
| 衝突對(same-chunk) | 17 | **兩版都 ADD**(結構盲點,store 同時留新舊) |

**Operation 錯誤清單(write-time)**:
- H1-miss 1(候選擠不進)、H2-refuse 1(拒覆蓋)
- **跨事實污染 2**(entity confusion):seq169 `Lisa Leslie plays goaltender`、seq310 `goaltender...pesäpallo`(**SH 正解**)被無關 fact 覆蓋摧毀 → 新錯誤型,full accounting 才抓到
- no-op UPDATE 2(prev==new,浪費)、NONE/dropped 12

**→ 回答使用者的核心檢驗**:
- 「single 就是 ADD」→ **完全成立**(133/133,0 over-fire)。
- 「衝突對新事實都靠 UPDATE 覆蓋舊」→ **大致成立但非全部**:146/165(88.5%)如此;但 17 對 same-chunk 兩版並存、2 對真偵測失敗(H1/H2)、2 筆跨事實污染摧毀正解。所以 vectorDB 末態**不是**乾淨的「每對只剩新版」。

### 2026-06-03 — A-WT write-time 衝突解決稽核(6k,完成)
- **腳本**:[scripts/awt_writetime_audit.py](scripts/awt_writetime_audit.py)(deterministic,無 LLM)。對齊完美(0 unmapped / 0 unmatched,165 對全對上)。
- **⚠️ 過程抓到並修正一個 confound**:初版假設 `gt_seq > old_seq` 恆成立,用 gt/old 標籤定方向 → 3/4 H1-miss 是「方向反了」的假失敗(diag:**僅 161/165 對 gt==較大序號**,4 對相反)。**修正**:write-time supersession 看 **ingestion 順序**(大序號=後 ingest=winner,應覆蓋小序號=loser),與 MQuAKE gt/old 標籤無關。
- **結果(方向修正後,detectable=148 cross-chunk)**:

  | bucket | n | 占 detectable |
  |---|---|---|
  | **resolved** | 146 | **98.6%** |
  | H1-miss(候選擠不進)| 1 | 0.7% |
  | H2-refuse(看到不覆蓋)| 1 | 0.7% |
  | same-chunk(排除)| 17 | — |

- **🔑 核心發現 — 6k write-time 衝突解決「不是」瓶頸**:98.6% 正確 resolved。H1/H2 各僅 1 例 → **「池過大→候選 miss」在 6k 尚未發生**(池 up to 137 夠小)。
  - 含義:FC-MH 6k 的 38% query 失敗**不在 write-time**,在 query 側(retrieval / 多跳 / answer)。
  - 兩假設**機制為真(各有 1 個教科書範例)但 6k 罕見**,預期在 32k/64k 才放大(尤其 H1)→ **這是下一步關鍵實驗**。
- **兩個 exemplar(proof-of-existence)**:
  - **H1**:Richthofen Germany(seq24,ch0)→Canada(seq386,ch10)。距離最遠、store 最大,舊版本擠出 top5 → 只 ADD。
  - **H2**:The Birth of Tragedy Nietzsche(seq76,真實,top5 rank1 score0.92)→Stephen Crane(seq77,反事實)。看到卻不覆蓋 = 參數知識拒覆蓋。
- **附帶 — benchmark 小瑕疵**:4/165 對 MQuAKE gt 是較小序號,與 FC「大序號=對」規則相反 → 這些對即使 write-time 機制完美,downstream 答案仍會與 gt 不一致。量小(2.4%),記錄備查。
- **下一步**:T7 延伸 32k/64k 跑 + A-WT,看 H1-miss 占比是否隨 ctx 上升(直接測「池過大」)。

### 2026-06-03 — T5 正式跑 FC-MH 6k(完成,真實三層資料 + 重要發現)
- **設定**:新 yaml `Structure_rag_mem0_..._chunk512_temp0_factaware.yaml`(vector / text-embedding-004 / temp=0 全層 / L1 prompt / fact-aware chunker),fresh namespace(舊 5/30 結果保留)。`MEM0_CAND_LOG_DIR` 開三層 log。1 context × 100 query,~11.7 分鐘。
- **EM = 62.0%**。三層 log 各 12 行(=12 chunk ingestion)正常。

| Component | 6k 真實結果 | 解讀 |
|---|---|---|
| 1 Extraction | **455 筆全抽出**(per-chunk 38..34),**0 chunk 失敗** | extraction 健康,**非瓶頸** |
| 2 Candidate | pool_size_after_dedup 隨 chunk:0→36→...→137→120 | 真實大池規模 |
| 3 Update | ADD 297 / UPDATE 148 / NONE 992;**hallucinated-id 僅 chunk0(空池)2 個** | 大池下未惡化 |

- **🔑 發現 A — 純 chunker 改動 EM +10pp**:舊 chunker(5/30)**52%** → fact-aware **62%**。同 config 其餘不變,只換 chunker。
  - 含義:舊 nltk chunker 的邊界切壞**實質壓低了 mem0 的 EM 10pp**(不只清掉 11 個序號的 cosmetic)。**先前 Plan A 的 mem0 MH 6k=52% 是被 chunking artifact 低估的數字**。
  - 對 paper:mem0 是被比較的 baseline,低估 10pp 是公平性問題 → **務必用 fact-aware chunker 的數字**。
  - **連帶**:mem0g / HippoRAG 也必須用 fact-aware chunker 重跑才公平(見 §5 TODO,使用者已接受 baseline 重跑)。
- **🔑 發現 B — hallucinated-id 非 6k 主因**:真實大池(up to 137)下 hallucinated-id 沒增加,只空池 chunk0 有 2 個 → 「池過大→更多 id 幻覺」子假設在 6k **不成立**,需 32k 驗證是否在更大池才浮現。
- **🔑 發現 C — extraction 非瓶頸**:455/455 全抽出、0 失敗 → FC-MH 的 38% 失敗在**下游(candidate miss / update 語意誤判 / retrieval)**,正是 A-EXT→T4→T6 要拆的。
- **下一步**:A-EXT(extraction 稽核確認 missing/distorted=0?)→ T4 same-chunk 標記 → T6 三向歸因,定位 38% 失敗。

### 2026-06-03 — T3 Component 3 update-decision instrumentation(完成,instrumentation trio 齊)
- **目的**:記錄 update 的完整 prompt + raw response,並直接算 hallucinated id(LLM 指認的 UPDATE/DELETE id 不在候選池 `0..N-1` → apply loop 會靜默丟棄的那些)。
- **實作**:[mem0/memory/main.py](../../mem0/memory/main.py#L306) parse 後加 env-gated dump(`update_decision.jsonl`)。schema:`{user_id, n_candidates, n_new_facts, update_prompt, raw_response, parsed_actions[], event_counts, referenced_ids[], hallucinated_ids[], id_to_uuid}`。先在 generate 後存 `_t3_raw` 保住 parse 前原始字串。baseline-safe。
- **驗證(smoke 擴充)**:`ALL PASS`。
- **🔑 早期訊號 — 空池也會幻覺 update**:`chunk0: n_candidates=0, hallucinated_ids=['34','36']`。store 還空、應全 ADD,update LLM 卻捏造對 id 34/36 的 UPDATE/DELETE → 全被丟棄。
  - 含義:hallucinated-update 是**與池大小無關的 baseline 病理**(空池都有),之後可畫 `len(hallucinated_ids)` vs `n_candidates` 看是否隨池變大惡化 → 直接測「池過大」是否額外加重 Component-3 失敗。
- **檔案大小注意**:`update_decision.jsonl` 含完整 prompt+raw,正式跑(多 context × 多 chunk × 多 ctx 長度)會偏大;diagnostic 可接受,需要時可改只存 raw 摘要。
- **狀態**:T0 chunker + T1/T2/T3 三 component instrumentation 全部完成且 smoke 一趟通過。下一步 T4 same-chunk 標記 + A-EXT,再 T5 正式跑。

### 2026-06-03 — T2 Component 1 extraction instrumentation(完成)
- **目的**:記錄每 chunk 原始抽取 `new_retrieved_facts`,才能歸因「GT 衝突事實在 extraction 就沒被抽出/抽錯」。
- **實作**:[mem0/memory/main.py](../../mem0/memory/main.py#L221) extraction 後加 env-gated dump(同 `MEM0_CAND_LOG_DIR`,檔名 `extraction.jsonl`)。schema:`{user_id, n_facts, facts[], custom_extraction_prompt, raw_response(僅失敗時)}`。baseline-safe(env 未設 = no-op)。
- **驗證(smoke 擴充)**:`ALL PASS`。extraction n_facts `[38,39,37,37]` == candidate-log n_new_facts(cross-check 一致);`custom_extraction_prompt=True`(確認 L1 prompt 有套用)。
- **🔑 關鍵發現 — mem0 extraction 剝掉序號**:151 筆抽取 fact,**0 筆保留序號**(`0. Thomas Kyd was born in the city of London.` → `Thomas Kyd was born in London`)。
  - 含義 1:mem0 recency **不是序號**(抽取就丟),而是 **ingestion 順序**(後 chunk=較新)→ 先前邊界序號分離對 mem0 機制影響其實很小。
  - 含義 2:**fact-aware chunker 的真正價值** = 讓每筆 fact 乾淨落在唯一 chunk(連續區間),**這是 T4 同-chunk 衝突標記的前提**(否則無法判定 fact 屬哪 chunk),而非「保留一個 mem0 根本不用的 recency 訊號」。決策仍正確,理由更新。
  - 含義 3:**alignment 必須靠內文比對**(序號已不在 memory 裡)— 與 [align_mem0_mquake.py](../../analysis/align_mem0_mquake.py) 既有做法一致。
- **附帶觀察(留給 T3)**:smoke 印的 events `[36,38,36,34]` < extraction `[38,39,37,37]`,chunk0 store 空卻只 36 events(<38 抽取)→ update 端有 drop(hallucinated id / NONE 合併),T3 raw response 會抓到。

### 2026-06-03 — Chunker 決策 = 改 fact-aware(已實作 + 驗證)
- **決策**:改用 fact-aware chunker(使用者選定)。理由:最乾淨,序號永不離身,消除 ~11 筆邊界 noise。接受代價 = 與現有 production FC 結果分歧,baseline 需重跑才公平。
- **實作**(scoped,其餘 dataset 零影響):
  - 新增 [utils/eval_other_utils.py `chunk_facts_by_line()`](../../utils/eval_other_utils.py#L229) — 以行為單位打包到 chunk_size,不跨 chunk 切 fact。
  - [conversation_creator.py get_chunks()](../../conversation_creator.py#L264) 路由:`'factconsolidation' in sub_dataset` → 新 chunker;其餘 → 原 `chunk_text_into_sentences`。import 一併更新。
- **驗證**:FC 6k chunk512 → 12 chunk,**0/12 problem**,facts 連續 0..37 / 38..76 / ... / 421..454(共 455),無 gap/overlap/stranded number。
- **Smoke 重跑**(改用同 chunker):`RESULT: ALL PASS`,events 36/38/36/34 對應乾淨 fact 區間。T1 instrumentation 在新 chunker 下仍正確。
- **⚠️ 重跑需求**:此改動使 FC 的 chunk 組成改變 → **mem0 / mem0g / HippoRAG 在 FC 上的舊結果不可直接沿用**,本研究要比較的 cell 需用新 chunker 重跑(LCA 無 chunking,不受影響)。記入 §5 TODO T0。

### 2026-06-05 — 64k FC-SH ingestion + query pipeline 分析(minimal thinking,完成)
> 目的:在 minimal 重跑 6k/32k 之前,先把 64k 這個第三長度點的 ingestion + query pipeline 用與 6k/32k 相同方法分析完,最終結果整理進 [04_fc_sh_64k_failure_deepdive.md](04_fc_sh_64k_failure_deepdive.md)。
> ⚠️ 設定差異:64k ingestion update LLM 與答題 LLM **皆 minimal thinking**(High 在 chunk37 本機 OOM),答題 `generation_max_length=256`(無截斷空輸出)。6k/32k 當時 High thinking。

**步驟與產物(逐一可重現):**
1. **建 64k SH GT**:`build_sh_gt_for_run.py --results <sh_64k results> --ctx factconsolidation_64k_context.txt --out sh_64k_RUN_gt.json` → `queries=100 | matched MQuAKE=100 | has_pair=66`。
2. **write-time 聚合**:`awt_result.json`(ingestion 後即時產出,21:01 > 20:57 logs,確認是本次 minimal run)→ detectable 1678 / resolved 1604(95.6%)/ H1-miss 53(3.2%)/ H2-refuse 21(1.3%)/ same-chunk 13;gt==larger-seq 1691/1691。
3. **query 條件分解**:`sh_query_conditional.py ... --out logs/sh_64k_conditional.json` → EM 94%;CORRECT 94(gt_retrieved 94/94);DROPPED 2(qid76/77);BAD-SUP 4(qid18/20/32/87)。
4. **逐題分類**:`sh_full_classify.py` → 但**預設 `--benchmark-defect 8,9` 是 32k 沿用值,對 64k 錯誤**(query 隨長度不同)。
5. **規則自洽重判(關鍵更正)**:`benchmark_rule_consistency.py "<arrow>" 6 sh_64k_RUN_gt.json`(arrow idx6=sh_64k,直讀 benchmark context)→ 66 衝突題,64 規則自洽,**僅 qid18/20 答案鍵違反 largest-serial**(qid18 鍵=Tom Clancy@7 但 slot 有 Torquato Tasso@1219;qid20 鍵=Europe@2374 但有 Asia@2468)。mem0 在這兩題輸出**大序號**=rule-correct → 非失敗,剔除。**64k 真正 benchmark-defect = 18,20,非 8/9**。
6. **6 個 nominal 失敗逐案 trace**(`update_decision.jsonl` 實查):
   - qid32:MLK died-in-city 槽 step2 存對 St Leonards,**step3 `UPDATE id=102` 用 `MLK citizen of Vietnam` 覆蓋**(同主詞異關係 over-fire)→ **A4**。
   - qid77:extraction 把 Areopagitica 作者摺進 `Milton famous-for` 槽,**`UPDATE id=13` 用 `Milton famous for Shakugan no Shana` 覆蓋** → **A4**(單一事實也被毀)。
   - qid87:`UPDATE id=10` 用 `Born This Way`(歌)覆蓋 `Born This Way Ball`(巡演)→ **近重複碰撞**。
   - qid76:`James Dashner educated at BYU` **有抽到**(cache 確認),但事件#124(n_cand=156)`parsed_actions` **完全沒這條的動作**、`hallucinated_ids=[]` → update LLM **靜默漏 ADD**(大池壓垮的新子模式 omission)。

**🔑 兩個必記結論:**
- **真 mem0 失敗 = 4(qid32/76/77/87),全部結構性**;3/4 是**無衝突的單一事實** → 結構失敗範圍比「只在衝突題」更廣。mem0 規則正確率 96/100。
- **⚠️ confound**:64k resolved 95.6% > 32k 93.1% 是 **minimal-thinking artifact**(H2-refuse 對 thinking 敏感,3.4%→1.3%),**非 scale 回升**。唯一跨設定穩健的 scale 證據 = **H1-miss 絕對數 1→29→53 單調上升**(純 embedding,不受 thinking 影響)。→ **下一步 6k/32k 用 minimal 重跑**才能宣稱 resolved 單調惡化。
