# mem0+P1 write-time failure taxonomy — gpt-4o-mini × 64k(2026-07-05)

> **目的**:對 Ob2(paper §4.4.1 Case A)提供 event-log-grounded 的失敗機制歸類。透過 mem0 `ingestion_context_0.jsonl` 的 ADD/UPDATE/DELETE event log,配合 P1 extraction cache 對照,以 **elimination-based reasoning** 建立 gt_new 為何未進 pool 的因果鏈。
>
> **⚠ 資料 rigor 限制(paper 需明講)**:mem0 event log 只記錄成功的 side-effect events;**不記錄** LLM UPDATE prompt 的 raw output(尤其 NONE decisions)、raw prompt input、retrieval-fetched candidate memories。因此每題個別的「LLM 對 gt_new 這個 fact 具體做了什麼」**無法直接讀出**,只能以 elimination 反推「gt_new 於 P1 cache 有 + 全 event log 無 = 被 mem0 UPDATE 靜默拒絕」。若欲直接 LLM decision evidence,需 patch mem0 加 UPDATE 路徑 logging,列 future work。
>
> **⚠ 待人工 double-check**:本檔分類由 Claude 自動 + review 產出;paper 提交前建議由第二人複查代表 case。
>
> **相依資料**:
> - P1 extraction cache: `analysis/results/p1_caches/extraction_cache_p1_64k.json`(130 chunk hashes,共 ~4000 facts)
> - mem0 event log: `outputs/rag_retrieved/Structure_rag_gpt-4o-mini-mem0_512_openai_unified_dest/k_100/factconsolidation_sh_64k/chunksize_512/ingestion_context_0.jsonl`(130 chunks × ~30 events)
> - Per-qid pool: 同目錄 `query_{qid}_context_0.json`
>
> **產生腳本**:`scratchpad/mem0_event_strict.py`、`scratchpad/mem0_case_deep_trace.py`、`scratchpad/map_chunk_hash_to_ingest.py`(scratchpad 版;若定案 promote 至 `analysis/`)。

---

## §1 兩大失敗機制

依據 Ob2 對 24 個 PP-OldOnly/PP-Missing wrong qids 的 event-log 追蹤,mem0+P1 於 gpt-4o-mini 的 write-time damage 可歸為兩類機制:

### M1. World-prior override(世界先驗覆蓋)

**表現**:gt_old(真實世界標準答案)於 mem0 store 存活;gt_new(counterfactual)於 P1 extraction cache 有,但**於 mem0 event log 中從未出現**(全 event grep 無此 fact,全然靜默)。

**推論的機制**:mem0's LLM UPDATE prompt 於處理 gt_new fact 時,retrieval 找到 gt_old memory 為 similar candidate,LLM 輸出「keep existing memory unchanged」(NONE 或 UPDATE-to-self)- 靜默拒絕 counterfactual。**gpt-4o-mini 的世界先驗越強,越拒絕反事實**。

**對應理論支撐**:對接 intro §第 3 段 [17] ConflictBank(小模型更難採納矛盾新資訊)+ [3] LightMem §5.6 self-quote(LLM 可能誤判導致不可逆資訊損失)。

**分佈**:於 24 qids 中 11(46%)清楚落入此類。

### M2. Coupled-update architectural fragility(架構性脆弱)

**表現**:兩版之一或雙方於 mem0 store 被刪除,原因不是 world-prior 而是「單一 UPDATE prompt output 完整性不足」造成 cross-item cascading damage。包含 3 個 sub-pattern:

- **M2a. Missing ADD**:LLM UPDATE 收到 gt_new + retrieval 找到 gt_old candidate,判「應 DELETE gt_old(認為新版對)」但 output list 中**沒有補上 ADD gt_new 的指示** → 兩版皆失
- **M2b. Cross-item cascade DELETE**:某 gt_new 已於較早 chunk 成功 ADDed,後續 chunk 處理 unrelated 新 fact 時,retrieval 檢索到 gt_new memory 作 similar candidate,LLM 誤判該 DELETE → gt_new 事後被 cascade 刪除
- **M2c. Cross-item name confusion**:P1 extract gt_new "Joseph Mitchell is a citizen of X",mem0 retrieval 找到 "Joseph Smith is a citizen of Y" 為 similar,LLM 判「Joseph Smith memory 不用改」(NONE)但**沒有 ADD Joseph Mitchell** → subject 靜默合併理解為 Joseph Smith,新 fact 全然丟失

**推論的機制**:coupled-update paradigm 把「判斷該 ADD/UPDATE/DELETE/NONE」與「執行操作」綁在**單一 LLM prompt output**。output 是 list-of-decisions,LLM 需要精確為每個 candidate memory 輸出 decision,**且不能漏 ADD 新 fact 這個獨立 entry**。相似 candidates 越多、facts 語意越接近,LLM output 越易 confused。**不可逆**(query time 無法回頭)。

**對應理論支撐**:對接 intro §第 5-6 段 coupled update 派困境(pre-query LLM 判斷是唯一錯誤來源)+ §第 3 段「一旦誤判即不可逆」。

**分佈**:於 24 qids 中 13(54%)清楚落入此類,細分為 M2a(3)、M2b(4-5)、M2c(5)。

---

## §2 M1 canonical case:qid=1 Hard Times

**Question**:*Who is the author of Hard Times?*
- **gt_new**(counterfactual)= `The author of Hard Times is Martin Luther King Jr.`(seq=2335)
- **gt_old**(real world)= `The author of Hard Times is Charles Dickens.`(seq=687)

### Pipeline evidence

**P1 extraction**:兩版都有(P1 cache hash `62d52389fb6f` 內含 MLK Jr. Hard Times fact)。抽取本身正確。

**mem0 event log trace 於 subject `The author of Hard Times`**:

| chunk | event | id | memory content |
|:--:|:--|:--|:--|
| 18 | `ADD` | 34dca530 | `The author of Hard Times is Charles Dickens.` |
| 43 | `UPDATE` | 34dca530 | `The author of Hard Times is Charles Dickens.` |
| 64 | `UPDATE` | 34dca530 | `The author of Hard Times is Charles Dickens.` |

**關鍵 chunk 64 觀察**:
- 該 ingest chunk 共 9 events,分佈:**0 ADD** / 4 UPDATE / 4 DELETE / 1 subject-UPDATE
- **整個 chunk 沒有新增任何 memory** → mem0 於此 chunk 處理的新 facts **全部被 rejection**
- 對照 P1 cache:該 chunk hash 抽出約 36 個 candidate facts,mem0 全數靜默 NONE 或 UPDATE-to-self
- 由 elimination:MLK Jr. 這個 counterfactual 也在其中,被 LLM 判「keep Dickens unchanged」

**MLK Jr. 於全 mem0 event log 出現於**:僅其他 predicate(如 `Martin Luther King Jr. died in the city of Memphis`)、**Hard Times 相關全無**。

**Pool 結果**:PP-OldOnly(只有 `Charles Dickens.`),response `Charles Dickens` ❌。

### M1 判定 evidence 表(pattern 明顯)

| qid | gt_new(counterfactual)| gt_old(real world 保留)|
|:--|:--|:--|
| 1 | MLK Jr. | Charles Dickens(Hard Times author)|
| 9 | Hiroshige | Jim Henson(Kermit creator)|
| 29 | Microsoft | Apple Inc.(PowerBook G4 developer)|
| 60 | cricket | association football(North East Stars sport)|
| 61 | Adam Sandler | Elon Musk(Tesla CEO)|
| 70 | Lamar Alexander | Arvind Kejriwal(Aam Aadmi Party chair)|
| 71 | Madonna | The Beatles(Beatles for Sale performer)|

**每一題被保留的 gt_old 都是真實世界標準答案**,gt_new 皆為 counterfactual。**LLM UPDATE 拒絕更新 = 世界先驗 override**。

---

## §3 M2 canonical case:qid=2 David Farragut

**Question**:*What is the country of citizenship of David Farragut?*
- **gt_new** = `David Farragut is a citizen of Denmark.`(seq=2211)
- **gt_old** = `David Farragut is a citizen of United States of America.`(seq=818)

### Pipeline evidence(M2a — Missing ADD sub-pattern)

**P1 extraction**:兩版都有(cache hash `64b8c3d9d088` 內含 Denmark 版)。

**mem0 chunk mapping**:
- gt_old(USA)於 ingest chunk **21** 進入 store — `ADD (id 49996dcf) "David Farragut is a citizen of United States of America."`
- gt_new(Denmark)於 ingest chunk **61** 遞交給 mem0 — 該 chunk 的 P1 抽 34 個 candidate facts,mem0 emit 20 ADD / 5 UPDATE / 4 DELETE(14 個 silently NONE)

**於 chunk 61 對 subject 的事件**:
- `DELETE (id 49996dcf) memory="David Farragut is a citizen of Denmark."`

**DELETE event memory 欄位為 "Denmark",不是 "USA"** — 這意味著 mem0 UPDATE prompt LLM 的 output 是:
- 新 fact = Denmark
- 對 existing memory 49996dcf(舊 USA)判「應該 DELETE」
- 但 LLM output list 中**沒有相對應的 ADD Denmark 指示**
- 執行結果:USA memory 被 DELETE,Denmark 沒 ADD → **兩版皆失**

**Pool 結果**:PP-OldOnly(matcher 或有他處尋到 USA variant;實際 store 該 subject entry 為空),response `USA` ❌(來自 world prior)。

**判定機制**:M2a — LLM UPDATE prompt output 遺漏 ADD 新 fact 的獨立指示,是 **coupled-update paradigm 的 output-format bug** 於 gpt-4o-mini 上的實例。

---

## §4 M2 canonical case:qid=4 Joseph Mitchell

**Question**:*What is the country of citizenship of Joseph Mitchell?*
- **gt_new** = `Joseph Mitchell is a citizen of United Kingdom.`(seq=2969)
- **gt_old** = `Joseph Mitchell is a citizen of United States of America.`(seq=1594)

### Pipeline evidence(M2c — Cross-item name confusion sub-pattern)

**P1 extraction**:兩版都有(cache hash `5d9745d46627` 含 UK 版、`63179fd9feff` 含 USA 版)。

**mem0 event log grep**:「Joseph Mitchell」 verbatim substring **全 130 chunks × 全 events 共 0 次出現**。

**但同 predicate 的其他 people 有**:
- chunk 55: `ADD "Joseph Smith is a citizen of United States of America."`
- 82 個 chunks 有其他 `X is a citizen of United [States/Kingdom]` 樣板 ADD 事件

**推論**:mem0 UPDATE 於 Joseph Mitchell 兩版本抵達的 chunks(P1 cache hash 對應到「0 ADD」的 ingest chunks):
- Retrieval 找到 `Joseph Smith is a citizen of USA` 等**人名近似**的 candidates
- LLM UPDATE prompt output list 對這些 similar-name candidates 全數判 NONE(不改動)
- 但 output 中**沒有為 "Joseph Mitchell" 這個獨立新 fact 補上 ADD 指示**
- **subject 被 mem0 靜默合併理解為 Joseph Smith 的近似**,新增 fact 完全丟失

**Pool 結果**:PP-OldOnly(matcher 從 retrieval 找到「Paul Morley is a citizen of United Kingdom」等其他 UK 相關 items,分類 mem0 pool 為 PP-OldOnly),response `USA` ❌。

**判定機制**:M2c — 跨筆記憶語意相近(尤其人名 vs 人名)導致 LLM UPDATE prompt output list **靜默合併理解**,新 fact 沒獨立 ADD entry。

---

## §5 M2 canonical case:qid=11 Prince Andrew

**Question**:*Who is Prince Andrew, Duke of York married to?*
- **gt_new** = `Prince Andrew, Duke of York is married to Mahidol Adulyadej.`(seq=3548)
- **gt_old** = `Prince Andrew, Duke of York is married to Sarah, Duchess of York.`(seq=3235)

### Pipeline evidence(M2b — Cross-item cascade DELETE sub-pattern)

**P1 extraction**:兩版都有。

**mem0 event log 對 subject `Prince Andrew, Duke of York`**:

| chunk | event | id | memory content |
|:--:|:--|:--|:--|
| 99 | `ADD` | f5095fed | `Prince Andrew, Duke of York is married to Mahidol Adulyadej.` |
| 106 | `DELETE` | f5095fed | `Prince Andrew, Duke of York is married to Mahidol Adulyadej.` |

**於 chunk 106 的整體 event context**:
- 33 events(15 ADD + 4 UPDATE + **14 DELETE**)- DELETE-heavy chunk
- 其他 DELETE 包括:`Charles the Bold is a citizen of France`、`The author of The Marriage of Figaro is Pierre Beaumarchais`、`East Melbourne Cricket Ground is associated with the sport of cricket` 等 unrelated memories
- 特別是 ADD 中含 `Muay Thai was created in the country of Singapore`(「Muay Thai」與「Mahidol」的 Thai royalty 語義相近)

**推論**:mem0 於 chunk 106 處理某個新 fact,retrieval 檢索到「Prince Andrew married to Mahidol」為 similar candidate(可能因為某 unrelated royalty/marriage fact 的 embedding 相近),LLM UPDATE prompt output 判 DELETE。**gt_new 被 cascade DELETE 移除**。而 gt_old(Sarah)於較早 chunks 從未 ADDed(自身也 fall into M1 的靜默拒絕)- **兩版皆失於單一 UPDATE prompt 決策**。

**Pool 結果**:PP-Missing(兩版都不在),response `Elizabeth II`(**LLM world-prior hallucination**,實為 Prince Andrew 的母親而非配偶)❌。

**判定機制**:M2b — cross-item cascade DELETE。

---

## §6 對 paper 的意涵

**兩個 mechanism 兌現 intro 的兩條核心論述**:

1. **M1 兌現 [17] ConflictBank + [3] LightMem §5.6**:
   > 「LLM 於世界先驗強的情境下,對反事實新資訊採取 rejection 反應;於 write-time 就是靜默 NONE、於 pool state 就是 PP-OldOnly。」
   
   即使不用 weaker backbone,mid-tier gpt-4o-mini 已足以呈現此現象,佐證 intro §受限部署段的 cost-constrained 面向(小型 API 模型足以觸發此 pattern)。

2. **M2 兌現 intro §第 5-6 段 coupled-update paradigm 的架構性缺陷**:
   > 「Coupled Update 把判斷與執行綁在單一 LLM prompt output;output 一旦有 completeness bug(漏 ADD、多 DELETE、cross-item confusion),整條記憶就損壞、且 query 時不可逆。」

**這正是 ours 為何選擇「query-time 解析、寫入不做跨筆判斷」的 architectural 動機**。

---

## §7 rigor 限制與 future work

- **無法直接讀出**:每題個別 gt_new fact 對應的 mem0 LLM 決策(NONE / UPDATE / DELETE / retrieval-fetched candidates / raw reasoning)
- **能間接證明**:by elimination — gt_new 於 P1 cache 有 + mem0 event log 無 = **必然於 UPDATE prompt 被 silently rejected**
- **Future work**:patch `mem0/memory/main.py::_add_to_vector_store` 於 UPDATE prompt 呼叫前後加 diagnostic logging(dump prompt + raw LLM output),重跑 gpt-4o-mini × 64k(成本 ~$0.3, ~30 min)取得直接 LLM decision evidence

## §8 未 audit / 未擴展項目

- ☐ 6k / 32k 相同分析(推斷 pattern 一致,尚未完整跑)
- ☐ gpt-4.1-mini × 64k(強 backbone 上)mem0 的 event log — 對照 M1 pattern 是否於強 backbone 上減弱(F1 backbone extension 觀察)
- ☐ 人工複查 canonical case 於代表題目(paper 提交前)
