# 研究核心主張 + 接下來優先 TODO(ours vs mem0g)

> **Date**: 2026-06-01
> **Status**: 接下來研究的 **核心主張 + 定位 + 優先 TODO**(本 session 收斂)
> **Baseline 收斂**:對手只比 **mem0g**(放棄 mem0 對照)。vanilla HippoRAG-v2 只當 **ablation 起點 / 變因隔離**,不當主張對手。
> **相關文件**:[chat_discussion_context_2026-05-26.md](../chat_discussion_context_2026-05-26.md)(angle C / 內部診斷)、[mem0g_reproducibility.md](../baseline_methods/mem0g_reproducibility.md)(§8 two-store divergence、§7 pipeline)、[research_narrative.md](research_narrative.md)

---

## 0. 一句話論文骨架(mem0g-only)

> **mem0g 把衝突偵測綁在 write-time,候選池(graph G4 = entity × ≤100 triple)隨 context 長度爆掉 → 越長越不準;且其記憶結構僅支援 1-hop 鄰域檢索 → 越多跳越撈不回鏈中段。Ours 把偵測移到 query-time(候選池與長度解耦)、以 PPR + 顯式 proposition chain 做檢索期多跳,因此在長 context 與深多跳上更穩。**
> **6k 單點落後要誠實標(mem0g 41% > ours 31%),賣點在 scaling 斜率與 by-hop 趨勢,不是單點 EM。**

---

## 1. 三方結構對照(主張的共同根據)

| 維度 | **mem0g** | **Vanilla HippoRAG-v2**(ablation 起點) | **Ours**(HippoRAG-v2 + Phase 2 + PropRAG borrow) |
|---|---|---|---|
| 記憶結構 | Qdrant 向量 **+** Neo4j 三元組,**兩庫平行獨立**(除 `delete_all` 外無同步) | 單一 entity–passage KG + 全部 embedding | 同 vanilla,額外給 proposition 加 timestamp `(chunk_idx, pos)` |
| 檢索單位 | vector: memory 文字;graph: 三元組 | passage(chunk) | proposition(三元組) |
| 衝突偵測時機 | **write-time**(ingest 時 vector L2 + graph G4) | **無**(old/new 平等存在、平等擴散) | **query-time**(P2.b chain-restricted verdict) |
| 衝突候選池 | vector L2: 每 fact top-5;graph G4: **entity 數 × ≤100 triple**(隨圖長膨脹) | — | active region 50 → chain → K_pool 10(**per-query bounded**) |
| 多跳檢索機制 | vector: 零跳 top-100;graph: query entity → cosine≥0.7 節點 → **只 1-hop 鄰居** → BM25 top-5 | **PPR 隨機遊走**(多跳擴散,但無顯式鏈) | PPR 擴散 **+ 顯式 beam chain(L 跳)** |
| outdated 處理 | ingest 時刪舊邊(常漏)→ 查詢時 old/new 並存 | **不處理**,outdated 與 current 平等進 top-k | 查詢時過濾 chain_old |
| 時序 / recency | **記了 `r.created` 卻不用**;prompt 聲稱 recency 但實際靠 LLM 猜 | 無 | timestamp **機械判方向**(deterministic) |

**變因隔離(為何留 vanilla HippoRAG 當 ablation)**:

| 對照 | 隔離出的變因 | 看哪個主張 |
|---|---|---|
| mem0g ↔ vanilla HippoRAG | 「有無多跳檢索結構」 | 主張二 |
| vanilla HippoRAG ↔ ours | 「有無 query-time 衝突偵測」(vanilla 17 → +Phase2 31,+14pp) | 主張一 |
| mem0g ↔ ours | 兩者疊加 | 主張一 + 二 綜合 |

---

## 2. 主張一:mem0g 的 write-time 衝突偵測「候選池過大 → 表現下降」

**精確主張**:mem0g 在 ingest 當下要對「**已累積的整個圖/向量庫**」判斷衝突。context 越長:
- **graph G4 候選池 = entity 數 × ≤100 triple**([graph_memory.py:247](../../mem0/memory/graph_memory.py#L247)),圖越大池越大 → LLM 在超長 prompt 裡判矛盾 → **precision 崩**;
- **vector L2 只跟 top-5 既有比**,庫一大,真正的舊 twin 排不進 top-5 → **recall 崩**;
- 兩庫各判各的([mem0g_reproducibility.md §8 two-store divergence](../baseline_methods/mem0g_reproducibility.md)),狀態還會互相岔開。

→ **候選池與總 context 綁死,長度增長直接放大偵測負擔 → 越長越不準**。這是 **scaling 主張**,不是單點主張。

**已有證據**:
| 指標 | 6k | 32k | 趨勢 |
|---|---|---|---|
| vector L2 precision | 0.97 | **0.51** | 崩 ↓↓ |
| graph P(R\|D=1)(mem0g-pa) | — | 35% | graph 在 32k 反而 hurt |
| FC-MH 6k ingestion event | 255 ADD / **0 DELETE** | — | 衝突幾乎沒被偵測,old+new 雙存 |

**誠實 caveat(已填數字)**:6k 時 **mem0g-as-is EM = 41%**([mem0g_reproducibility.md §4.1](../baseline_methods/mem0g_reproducibility.md)) **> ours = 31%**。所以主張一**不能靠 6k 單點**,要靠「6k→32k→64k 的偵測精度與 EM **下滑斜率**」——mem0g 下滑、ours 平,才是賣點。

### 關鍵分析(數字 / 趨勢 / case study)
1. **趨勢圖(最重要)**:mem0g vs ours 的 **detection precision & recall vs context 長度(6k→32k→64k→262k)**。預期:mem0g 隨長度單調下滑,ours 平。= chat context 的 **angle C** 主力證據。
2. **候選池大小 vs 長度**:instrument mem0g G4 每次看到的候選 triple 數(開 `mem0.memory.graph_memory` debug log)→ 畫「池大小 vs context 長度」→ 證明池真的爆。
3. **EM 交叉點**:找出 ours 反超 mem0g 的長度(可能 32k)。6k 輸、32k+ 贏 = 乾淨 scaling story。
4. **Case study**:挑一題 FC,展示 mem0g 在 32k 時 vector 回 old+new 並存、graph relations 也帶矛盾(§8.2 unhappy V/G),LLM 被誤導;ours 同題 query-time 濾掉 chain_old 答對。

---

## 3. 主張二:mem0g 的記憶結構「無法多跳檢索 → 越多跳越差」

**精確主張**:mem0g 的 graph 檢索是「**從 query entity 出發的 1-hop 鄰域查找**」,沒有沿關係鏈往深處走的機制。
- query → 抽 entity → cosine≥0.7 找節點 → `MATCH (n)-[r]->(m)` **只展開直接鄰居** → BM25 top-5([graph_memory.py:84-95](../../mem0/memory/graph_memory.py#L84));vector 路徑更是零跳 top-100。
- A→B→C→D 的 4-hop query 只提到 A 時,mem0g 撈得到 B,**撈不到 C、D**。

→ **答案需要 k-hop 鏈中段的記憶時,中段撈不回 → hop 越多 recall / EM 越低**。

**重要:「1-hop」是建構期限制,不是一行 Cypher 的事**(reviewer 必問「改成 `-[*1..k]->` 不就好了」)。就算加多跳遍歷,mem0g 建構期五個限制讓它撈不出有用的鏈:
1. **Entity resolution 弱**(name + cosine 0.9 dedup,per-chunk LLM 命名不一致)→ 鏈在 chunk 間物理斷開。
2. **關係只在同 chunk 內建**(EXTRACT_RELATIONS_PROMPT 明文)→ 無跨 chunk 橋接邊,連通性是 (1) 的人質。
3. **邊上無可用時序**(有 `r.created` 但檢索/G4 不用)→ 多跳遍歷無差別走 old/new 邊。
4. **BM25 over 扁平 triple**,無 path-as-unit scoring → 遍歷=候選爆炸但無原則排序。
5. **無 PPR / 全域傳播**,只激活 query entity 的 ego-network → query 沒提到的中段 entity 永不浮現。

> ⚠️ (1)(2)(5) 是**真結構限制**(可強主張);(3)(4) 嚴格說是「mem0g 沒做」而非「不可能做」,framing 要寫成「設計選擇缺口」而非「結構不可能」。

**對比的關鍵 framing(避免自打嘴巴)**:我們自己 by-hop 也下滑(2h 37.7% → 3h 25% → **4h 13.3%**,chat context §9.3),但**病因不同**:
- mem0g 下滑 = **結構性無多跳檢索機制**(不可修);
- ours 下滑 = **beam L=3 參數限制**(4-prop 鏈枚舉不出,**可修**:調 L→4/5)。
→ 賣點:**ours L 修好後多跳維持;mem0g 因結構限制無法修**。

### 關鍵分析(數字 / 趨勢 / case study)
1. **by-hop EM 同圖**:mem0g vs ours 的 EM vs hop 數(2/3/4)。預期:mem0g 在 3-4 hop 崩到接近零跳,ours 調 L 後維持。**主張二核心圖**。
2. **檢索期 hop reachability**:每個 GT 多跳鏈,量「鏈上各 hop 是否被檢索回」——mem0g 預期只回第 1 hop,ours 回整鏈。直接證明結構性 1-hop 限制。
3. **先修 ours L=3→4/5**(否則主張二被自己數字反駁)。
4. **Case study**:一題 4-hop,mem0g top-5 triple 只含第 1 跳答錯;ours beam chain 串到第 4 跳答對。

---

## 4. Our method 的突破設計(扣兩主張,合理且可辯護)

| 缺口 | mem0g 病根 | ours 設計 | 為何站得住 |
|---|---|---|---|
| **主張一:池過大** | write-time 對全庫判,池 = entity×100 隨長度爆 | **query-time + bounded pool**:只對 active region(50)→ chain → K_pool(10)判 | 候選池與**總 context 解耦**——本質結構優勢,非調參 |
| 池內 precision | 長 prompt 判矛盾,雜訊多 | **chain-restricted verdict**:LLM 只在「一條候選鏈內」找矛盾,context 極短 | prompt 短 = 判得準 |
| 時序方向 | 記了 `r.created` 卻不用,靠 LLM 猜 recency | timestamp `(chunk_idx, pos)` **機械判方向** | deterministic,見 §5 prior-art 警示 |
| 主張二:無多跳 | 1-hop ego-network | **PPR + 顯式 beam chain(L 跳)** | 檢索期沿鏈走,結構上取回鏈中段 |

**必須補強的兩個自身弱點(誠實面對)**:
1. **beam L=3** 是死穴 → adaptive depth(LLM 預測 hop 數設 L / beam 自適應停止)。
2. **filter ceiling ~31**(rescue leak)→ 主張一「池小所以準」要轉成 EM,目前 detection 贏但 EM 沒兌現,需攻 filter / inference / context 構造層。

---

## 5. 研究定位(本 session 收斂)+ ⚠️ Prior-art 警示

### 5.1 工程:走「graft 候選池」而非「自寫 beam」
- **PropRAG = HippoRAG(改)+ proposition + LLM-free beam over proposition paths**(README 自承 adapted from HippoRAG;retrieve 仍用 PPR + `focus_top_k=50` + beam)。
- 我們需要 PropRAG 的**正是「把相關 proposition 串成 bounded reasoning chain」= 衝突候選池**。
- **決策:忠實 vendor PropRAG 的 `BeamSearchPathFinder` 當 Phase 2.a**,passage ranking 留 HippoRAG-v2。**不要**再維護自寫的半成品 beam(現在 L=3、connectivity 退化、`proprag_strict` 把 LOST_CONNECTIVITY 11→25)。
- 敘述:「base = HippoRAG-v2;query-time chain 枚舉改用 PropRAG 的 beam」。

### 5.2 貢獻:衝突偵測「拆成 LLM 語義分組 + deterministic timestamp 仲裁」
- **設計**:
  - **Baseline(對照)** = mem0g 的 `DELETE_RELATIONS_SYSTEM_PROMPT` 原 prompt 搬到我們的候選池 → **LLM 直接判哪條該刪 / 哪個是舊(LLM 自己猜 recency)**。
  - **Ours** = LLM **只做衝突分組**(指出哪些 prop 互為矛盾版本)→ **timestamp code 判方向**。
  - 兩者只差 verdict 那一塊、其餘全同 → **controlled ablation 乾淨隔離「移除 LLM recency bias」的淨效果**。
- **這個 decomposition 已在 [verdict.py / verdict_prompt.py](../../methods/hipporag/phase2b/) 實作(separate semantic + mechanical direction)**;TODO 是把它**升格成 headline insight + 補 baseline ablation 證明它值多少**,不是發明新東西。

### 5.3 ⚠️ Prior-art 警示(本 session 新發現,務必處理)
- **「用 timestamp 而非 LLM 猜 recency」本身不原創**:**Zep / Graphiti 已用 bi-temporal `valid_at` / `invalid_at` 做 write-time 衝突仲裁**([methods/zep.py:34-35](../../methods/zep.py#L35)、[baseline_methods_paper_vs_impl.md §時間感知](../baseline_methods/baseline_methods_paper_vs_impl.md))。mem0 的 UPDATE/DELETE prompt 也聲稱 "prioritize recency"。
- → **貢獻不能 framing 成「我們用 timestamp」**,否則被 Zep 打臉。**真正的差異化 = query-time + chain-scoped 的放置**:Zep 在 write-time 做(且 FC EM 只 8%),我們在 query-time + 單一候選鏈內做。所有新意都收斂回「時機 + scope」,timestamp 仲裁只是手段。
- **務必在 related work 明確 cite Zep bi-temporal 並做差異化。**

### 5.4 ⚠️ 未解設計問題:"twins" → N-way 衝突組
- 目前 verdict 以「矛盾 pair / twin」為單位,但**一個事實可能被更新多次(N ≥ 2 版本)**,分組不是只有兩種版本。
- → LLM 分組要輸出**衝突等價類(N-way group)**,timestamp 仲裁 = **group 內 argmax(timestamp)** 取最新、其餘全標 outdated。
- 這是 §5.2 decomposition 要先補的設計細節。

---

## 6. 可能挑戰 = 潛在貢獻(empirical 撞到就記下)

| 挑戰 | 為何會撞 | 撞到後的潛在貢獻 | 優先 |
|---|---|---|---|
| **候選池召回是上限** | verdict 再準,beam 沒把 chain_old/new 撈進池就白搭(現 candidate recall 67%) | 「query-time 偵測瓶頸從『判斷』轉移到『候選池召回』」本身是 finding;先上 PropRAG 整套 beam | 高 |
| **filter leak(ceiling ~31)** | 偵測對了但 rescue drop 方式會 leak | 新的 context 構造法(chat context §5 approach 1/2) | 高 |
| **scaling 交叉點** | 池小的好處要長 context 才顯現 | 主張一的 scaling 主圖 | 高 |
| **timestamp 假設破裂** | 非 FC 任務 / 同 chunk 內多 fact 時序不明 | 弱時序訊號下的 recency 仲裁設計 | 低(暫不優先) |

---

## 7. 分析地圖 / 優先 TODO(ours vs mem0g)

| # | 要產出 | 證主張 | 現況 | 優先 |
|---|---|---|---|---|
| 0 | **mem0g 在我們框架下的 detection P/R/F1**(目前無 mem0g-specific 數字;勿沿用 mem0 的 42) | 一 | **待測** | P0 |
| 1 | mem0g vs ours **detection P/R vs context 長度**(6k→32k→64k→262k)曲線 | 一 | mem0g 6k/32k 部分有;ours sweep 待跑 | P0 |
| 2 | mem0g **G4 候選池大小 vs 長度**(debug log instrument) | 一 | 待 instrument | P1 |
| 3 | **EM 交叉點**:ours 何時反超 mem0g | 一 | 待跑 ours 32k+ | P0 |
| 4 | mem0g vs ours **by-hop EM(2/3/4)同圖** | 二 | ours 有;mem0g 待按 hop 拆 | P0 |
| 5 | **鏈上各 hop reachability**(mem0g 只回 1-hop? ours 回整鏈?) | 二 | 待量 | P1 |
| 6 | Case study × 2(長 ctx 衝突題、4-hop 題) | 一+二 | 待挑題 | P1 |
| 7 | **vendor PropRAG `BeamSearchPathFinder`**(取代自寫 beam,順帶修 L=3) | 二(自保) | 待做 | P0 |
| 8 | **decomposed-verdict ablation**(mem0g-prompt-as-is vs LLM-group+timestamp) | 貢獻 | 設計待寫,§5.2/5.4 | P0 |

---

## 8. 一頁誠實清單(reviewer 會戳的點)
1. 6k ours(31)< mem0g-as-is(41)→ 主張靠 scaling 斜率,不靠單點。
2. mem0g detection F1 **還沒在我們框架測**(別用 mem0 的數字代替)。
3. 「用 timestamp」非原創(Zep bi-temporal)→ 新意在 query-time + chain-scoped。
4. ours 自己 4-hop 也崩(L=3)→ 先修才能談主張二。
5. detection 贏但 EM 沒兌現(filter ceiling)→ 「準但沒用」要解決。
6. 主張二的 (3)(4) 是「沒做」非「不可能」→ framing 要保守。
