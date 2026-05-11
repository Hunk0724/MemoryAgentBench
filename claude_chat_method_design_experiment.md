# §B 方法骨架快查

## B.1 HippoRAG-v2 原方法流程 (我們的 base)

> **為什麼這節重要**: 我們所有改動都是在 HippoRAG-v2 既有 pipeline 的特定 step 上加東西,不是另起爐灶。寫 Ch.3 method 時要清楚對讀者解釋「HippoRAG-v2 原本怎麼做」+「我們在哪個 step 改」。

### Offline Indexing (建索引時做一次)
| Step | 動作 |
|---|---|
| I1 | LLM 對每個 passage 跑 OpenIE, 抽 `(s, r, o)` triples |
| I2 | 對所有 triple 中的 phrase, 用 embedding 找相似度高的 pair, 加 **synonym edge** (跨 passage entity 同義對齊) |
| I3 | Phrase nodes + passage nodes + relation edges + synonym edges + context edges 一起組成 KG |

### Online Retrieval & QA (每次 query 跑一次)
| Step | 動作 | 在這 step 動刀的 implication |
|---|---|---|
| O1 | Query → embedding, 跟 phrase nodes 與 passage nodes 算 similarity, 各取 top-k 為 seed | (我們 v1 不動) |
| O2 | **Recognition memory**: LLM 對 query 周邊抽出的 candidate triples 做 filter, 過濾不相關 triple | (v2 可選 hook: 在這步加 superseded triple 的 filter) |
| O3 | Phrase node 與 passage node 根據前兩步分配 PPR reset probability | (v1 不動) |
| O4 | KG 上跑 **Personalized PageRank** propagate mass, 每個 node 收斂到 PPR score | (v2 可選 hook: edge weight × supersedence freshness factor — 即 Idea A "decayed PPR") |
| O5 | 從 PPR 分布中取 **passage node** PPR score 排序, top-N passages 拿出來 | **(v1 主戰場): 此 step 後加 chain-aware filter** |
| O6 | Top-N passages 原始 chunk 文字 concat 進 LLM context, 跑 QA | **(v1 主戰場): system prompt 加 scaffold** |

### 關鍵限制 (paper Ch.3 要點出來)
- **Granularity mismatch**: LLM 看到的是 **passage 文字**, 不是 KG 結構。KG 上的 metadata (如 supersedence) 無法直接 propagate 到 LLM context, 只能透過影響 passage ranking
- **Passage 異質性**: 一個 passage chunk (512 token) 可能同時含 5-10 個 fact, 其中部分 superseded、部分 active。FC corpus 上問題不嚴重 (chunk 內 fact 關聯弱), 但延伸到自然對話時是 v2 主要要處理的問題

### 程式碼端對應(從 HippoRAG.py 補完, 2026-05-11)

> 上面的 I1-I3 / O1-O6 是抽象敘述。這節記錄真實 code 對應(以及 chat 原版的小錯誤修正), 之後 design decision 都依這份為準。

#### KG 真實組成 — 2 種節點 + 3 種邊(沒有 chat 原 B.1 提的 "context edges")

| 元件 | 程式碼 | FC 上長什麼樣 |
|---|---|---|
| **Phrase node** (= entity node) | [`entity_embedding_store`](methods/hipporag/HippoRAG.py#L143), igraph vertex with key `"entity-<hash>"` | 每個 OpenIE 抽出的 entity 一個節點: `"Twitter"`, `"Jack Dorsey"`, `"Bernard Arnault"`, ... |
| **Passage node** (= chunk node) | [`chunk_embedding_store`](methods/hipporag/HippoRAG.py#L143), igraph vertex with key `"chunk-<hash>"` | 12 個 chunks 各一節點(6k corpus) |
| **Fact edges** (phrase ↔ phrase) | [`add_fact_edges` L494](methods/hipporag/HippoRAG.py#L494), 對每 triple `(s,r,o)` 加 `(s_node, o_node)` 雙向 | `Twitter ↔ Jack Dorsey`, `Twitter ↔ Bernard Arnault`(兩者並列, 沒有新舊區分) |
| **Passage edges** (passage → phrase) | [`add_passage_edges` L543](methods/hipporag/HippoRAG.py#L543), 對每 chunk 加 `(chunk_node, entity_node)` | passage_1 → `Twitter`, passage_1 → `Jack Dorsey`, ... weight = 1.0 |
| **Synonymy edges** (phrase ↔ phrase, KNN) | [`add_synonymy_edges` L587](methods/hipporag/HippoRAG.py#L587), entity embedding KNN + sim threshold | FC canonical entity 字串高度一致 → synonymy 影響相對小 |

> ⚠️ **chat 原 B.1 表格 I2 "Synonym edge" 在程式碼中是在 `add_fact_edges` + `add_passage_edges` 之後跑** (在 [`augment_graph` L757](methods/hipporag/HippoRAG.py#L757) 之前), 不是並列在 I2。對 design 不影響, 但要知道實際順序是 I1(OpenIE) → I3(fact/passage edges) → I2(synonymy) → finalize。

#### Fact 不是節點 — 存在 `fact_embedding_store`

- **`fact_key`** = [`compute_mdhash_id(content=str(triple), prefix="fact-")`](methods/hipporag/HippoRAG.py#L527)
  - 對 triple tuple stringify (e.g. `"('Twitter', 'CEO', 'Jack Dorsey')"`) 後算 md5
  - 同 (s, o) 但不同 r → **不同 fact_key**, **fact_key 自然保留 relation 資訊**
- `fact_embedding_store` 存 fact tuple 字串 + embedding(供 [`get_fact_scores` L964](methods/hipporag/HippoRAG.py#L964) 的 query→fact similarity)
- 但 fact **不進 igraph**: [L913 assert](methods/hipporag/HippoRAG.py#L913) 規定 `entity_nodes + passage_nodes == graph.vcount()` — fact 只活在 embedding store, 影響 retrieval 第一階段, 不參與 PPR

→ **設計 implication**: Phase 1 supersession metadata **必須掛在 fact_key 層**(因 graph edge 沒 relation 區分能力, 同 (s, o) 不同 r 共用一條 edge)。chat 原 B.3 Phase 1 寫的「在舊 edge 加 metadata」要修正為「在舊 fact_key 加 metadata」, 詳見 §B.3 更新。

#### Retrieval pipeline 對應(用 FC 衝突 query 走一遍)

Query 例: **"What is the nationality of the CEO of Twitter?"** (FC-MH 2-hop, GT=France, chain_new: Twitter→Bernard Arnault→France; chain_old: Twitter→Jack Dorsey→US)

| O 階段(chat 原命名) | 程式碼 | 在 FC 衝突 query 上的行為 |
|---|---|---|
| **O1** Query → fact scores | [`get_fact_scores` L964](methods/hipporag/HippoRAG.py#L964): query embed × all fact embeds (dot product, normalized) | 高分含 `(Twitter, CEO, Bernard)` 跟 `(Twitter, CEO, Jack)` — query 跟兩者文字 similarity 都高 |
| **O2** Recognition memory (LLM rerank) | [`rerank_facts` L1170](methods/hipporag/HippoRAG.py#L1170): top `link_top_k` facts → LLM judge keep/drop | LLM 看 (s,r,o) 完整 tuple(relation 在此可見)。實證: LLM 通常保留兩個 `(Twitter, CEO, *)` 版本因為都跟 query 相關 |
| **O3** Seed reset probability | [`graph_search_with_fact_entities` L1102-1129](methods/hipporag/HippoRAG.py#L1102): 對每 kept fact, subject + object 設 `phrase_weights[idx] = fact_score / ent_node_to_num_chunk[entity]` | **chain_old entity (Jack) 跟 chain_new entity (Bernard) 同時成為 PPR seed** ← 核心問題 |
| **O3'** Passage seed | 同函式 L1144-1148: DPR 給每 passage `passage_weight × passage_node_weight(=0.05)` | 提供 passage-level fallback signal |
| **O4** PPR propagate | [`run_ppr` L1203](methods/hipporag/HippoRAG.py#L1203): igraph `personalized_pagerank(reset=node_weights, damping=0.5)` 跑收斂 | mass 沿 fact/passage/synonym edges 流動。chain_old hop 2 satellite passage(含 `Jack Dorsey citizenship US`)也獲高 mass |
| **O5** Top-N passages | 同函式 L1162-1167: 取 PPR 後 passage node 排序前 N(預設 10) | top-10 含 chain_new + chain_old chunks 並列, 覆蓋 ~83% corpus(motivation §1.5) |
| **O6** QA reading | [`rag_qa` L361](methods/hipporag/HippoRAG.py#L361): top-N passage 原文 concat 進 prompt | LLM 同時看到兩條 chain → 困惑, vanilla EM 22% |

#### Vanilla 在 FC-MH 各 step 的表現量化

| 量 | 數值 | 來源 |
|---|---|---|
| Fact retrieval (O1) chain_new 命中率 | ≥94%(top-k facts 內) | motivation §1.5 |
| Fact retrieval (O1) chain_old 命中率 | ≥97% | 同上 |
| Recognition rerank (O2) 衝突過濾能力 | 弱 — LLM 缺 disambiguation signal 多保留 | 推測, 待量化 |
| Top-10 passages 對 corpus 覆蓋率 | ~83% (378/455 facts) | motivation §1.5 |
| Per-question 全 chain_new 進 retrieval | 89% | 同上 |
| Per-question 全 chain_old 進 retrieval | ~98% | 同上 |
| Vanilla EM(FC-MH) | **22%** | motivation §1 |

→ **崩盤不在 retrieval recall**, 在 (a) 圖結構不區分新舊 + (b) LLM 拿到混合 chain 後不穩定多跳推理。

## B.2 我們三階段在哪些 step 動刀

```
                                              我們的改動
─ Offline Indexing ─────────────
I1. OpenIE                                    
I2. Synonym edge (entity-level)               
I3. Build KG                          ← Phase 1 加: 對 (s,r,≠o) 標 superseded metadata

─ Online Retrieval & QA ────────
O1. Query encoding + seed top-k
O2. Recognition memory (LLM filter triples)
O3. Seed reset probability
O4. PPR propagate                              ← v2 候選: edge weight decay by freshness
O5. Passage ranking & selection       ← Phase 2 加: chain-aware filter (PPR mass-based)
O6. QA reading                        ← Phase 3 加: universal reasoning scaffold
```

## B.3 v1 spec lock (本週要實作)

### Phase 1 — Conflict-Aware KG Annotation (write-time, on I3)

**機制**:
1. OpenIE 抽 triple 後, 對每個 incoming `(s, r, o_new)`, 比對 KG 已有的 `(s, r, o_old)` 且 `o_old ≠ o_new`
2. 在舊 **fact** 加 metadata: `{superseded_by_fact_key: ..., observed_chunk_idx: t}` (見 ⚠️ 修正)
3. **新舊 fact 都保留**, 不刪、不改 PPR transition

**⚠️ 程式碼端修正 (Updated 2026-05-11)**:
- chat 原寫「在舊 **edge** 加 metadata」, 但 v2 graph fact edge 只連 (s_entity, o_entity), **relation collapse 掉** → 用 edge 標 metadata 會 ambiguous (同 entity pair 不同 relation 共用一條 edge, e.g. `(Twitter, CEO, Jack)` 跟 `(Jack, founded, Twitter)` 共用同一條 `Twitter ↔ Jack` edge)
- **正確做法**: 在 **fact_key 層**標 supersession。`fact_key = compute_mdhash_id(content=str(triple), prefix="fact-")` 對整個 (s,r,o) 雜湊, 自然區分 relation, 且跟 igraph 解耦不干擾 PPR
- **具體實作**:
  - 新建 `self.superseded_facts: Dict[fact_key, {by_fact_key, observed_chunk_idx, s, r, o_old, o_new}]`
  - 在 [`add_fact_edges` L494](methods/hipporag/HippoRAG.py#L494) 跑完後(或進 [`augment_graph` L757](methods/hipporag/HippoRAG.py#L757) 內)掃 `chunk_triples`, group by (s.lower(), r.lower()) 找同 (S, R) 不同 O 的 fact 對, 標 superseded
  - 同時持久化 `self.chunk_to_fact_keys: Dict[chunk_id, List[fact_key]]`, 給 Phase 2 反查 passage→constituent triples
- 此設計**保留所有 vanilla 行為**(graph 結構、PPR、retrieval 都不變), Phase 1 only 預期 EM ≈ vanilla 22% ± 1pp

**Falsifiable assertions** (v1 跑完要驗證):
- A1.1: Per-question all-detected coverage > Mem0 41% (FC-MH)
- A1.2: FC-MH EM 與 vanilla HippoRAG-v2 一致 (因為 KG 結構未變動, 只加 metadata)

### Phase 2 — Chain-Aware Retrieval Filtering (query-time, after O4 before O5)

**機制**:
```
PPR 收斂後:
  1. high_mass_entities = top-X% phrase nodes by PPR score  (X=20)
  2. for each candidate passage p in PPR-ranked top-N:
       sup_edges = [edge in p.source_triples if edge.superseded_by exists]
       if not sup_edges: keep p
       else for edge in sup_edges:
           if both endpoints (edge.s, edge.o) in high_mass_entities:
               // chain-old: filter p
               remove p from ranked list; break
           else:
               // other-old: keep p
```

**v1 起手參數**:
- X = 20 (PPR top-20% mass 為 high mass)
- 兩端都 high mass 才 filter (保守, 減少 false positive)
- Hard filter (對齊 OracleClean-ThisChain ceiling)
- 任一條 chain-old 對應到 passage → filter 整個 passage

**⚠️ 程式碼端實作位置 (Updated 2026-05-11)**:
- 切入點: [`graph_search_with_fact_entities` L1162](methods/hipporag/HippoRAG.py#L1162), 在 `run_ppr` return 之後、return passage scores 之前
- **必須先修 [`run_ppr` L1203](methods/hipporag/HippoRAG.py#L1203) 的 return signature**, 額外回傳 **phrase node 上的最終 PPR mass**(目前 L1239-1241 只 return passage 的 sorted ids + scores), 才能取 high-mass phrase set
- Passage 反查 source triples 用 Phase 1 持久化的 `chunk_to_fact_keys`, 對每個 fact_key 查 `superseded_facts` 判斷是否 superseded
- High-mass selector X=20% 是 hyperparameter 起手值, 待 calibrate

**⚠️ 開放問題 — Hop 2+ satellite fact 偵測 (新發現, 2026-05-11)**:
- chat 原規則「兩端都 high mass 才 filter」只 catch **同 (S, R, ≠O) 直接衝突** = Type-1 hop 1 直接衝突(例: 兩條 `(Twitter, CEO, ?)` triples)
- **漏掉 Type-2 / Type-3** (見 B.7.2):
  - **Type-2** hop 2+ 直接衝突, S 不同(例: `(Jack, citizen, US)` vs `(Bernard, nationality, France)`) — 不是同 (S, R) 衝突, 規則漏
  - **Type-3** satellite leakage, 此 fact 本身對(`Jack` 真是美國人), 但 query 已不問 `Jack` — 不是 superseded fact, 規則漏
- 候選解(v2): **OLD-entity propagation** — 把 hop 1 superseded triple 的 `O_old`(Jack) 標為「chain_old anchor entity」, query 時把任何 `(O_old_anchor, *, *)` fact 進入 high-mass-gate 判定
- **v1 不解 Type-2/3**, 但 v1 跑完後**必須量化 FC-MH 答錯題目中 Type-2/3 佔比**, 決定 v2 優先度

**Falsifiable assertions**:
- A2.1: FC-MH EM > 50% (lower bound) / > 70% (stretch)
- A2.2: Chain identification precision > 85%
- A2.3: FC-SH 退步 < 3pp vs vanilla HippoRAG-v2

### Phase 3 — Universal Reasoning Scaffold (inference-time, in O6)

**v1 措辭草案** (system prompt 末尾追加):
> "When the answer requires connecting multiple facts, briefly list the intermediate entities or facts you use, and ensure that any entity appearing in multiple steps is referenced consistently."

**設計準則**:
- 不提 conflict / supersedence / 序號 (避免為 FC overfit)
- 對非 multi-hop query 自動跳過 (前綴 "When the answer requires connecting multiple facts")
- 對非 KU 多跳 QA (MuSiQue / 2Wiki) 應為微正向或無害

**Trigger**: v1 always-on, 不做 conditional gate

**Falsifiable assertions**:
- A3.1: 在 OracleClean-ThisChain 上重現 +28pp gain (sanity check)
- A3.2: 非 KU multi-hop task (MuSiQue) 退步 < 2pp

## B.4 從觀察到方法的決策過程 (給 advisor / reviewer 解釋為什麼這樣設計)

| 觀察 (motivation §) | 方法決策 | 設計 trade-off |
|---|---|---|
| PureChain 97% (§1.A) | 任務本身可解, 崩潰來自 KU+MH 交集 | 確認方向是「處理交集」而非「改 task」 |
| 25.8pp emergent gap (§2.A.X) | KU 與 MH 不是線性疊加, 有 emergent failure | 需要結構化方法, 純 prompt 救不了 |
| +34pp (移本題 chain_old) vs +5pp (移其他 olds) (§2.A) | Phase 2 必須 **query-aware**, 不能 query-agnostic delete | Rule out Mem0 風格的 write-time hard delete |
| n_inject 0→1 掉 49pp (§2.A.b2) | 一個 chain_old 就足以崩盤 → filter recall 要高 | Phase 2 寧可激進 filter (hard) 也不要漏 |
| Mode C 無 seq rule 也 -47pp (§2.A.X.3) | 崩盤不是 seq rule artifact, 是 chain_old 本身 | 我們的方法不依賴 seq rule, 可 generalize |
| V1/V2/V3 都 +28-31pp (§2.B) | scaffold signal robust, 不是某個 prompt 巧合 | Phase 3 可以用最 universal-safe 那版 |
| Mem0 detection 41%, all-detected MH 仍 63% (§4.3) | 即使偵測全對, retrieval 端不過濾還是錯 | 證實 Claim 1 (retrieval-side filtering 必要) |
| Zep MH all-detected 40% (§4.3.B) | annotation 保留兩版但 LLM 忽略 metadata | 證實 Claim 2 / 啟發 scaffold 設計 |

## B.5 未來迭代方向 (v2 reactive decision tree)

v1 跑完後, 根據觀察決定 v2 動作:

| v1 觀察 | v2 對應動作 |
|---|---|
| Phase 1 detection coverage < 50% | 加 entity/relation canonicalization (利用 HippoRAG-v2 既有 synonym edge) |
| Phase 2 precision < 80% (誤刪過多) | hard filter → soft demote (rerank 而非刪除) |
| Phase 2 recall < 70% | 放寬「兩端 high mass」→「一端 high mass」; 或加 LLM-judge fallback |
| FC-SH / non-KU 退步 > 3pp | Phase 2 加 trigger gate / Phase 3 改 conditional |
| FC-MH 仍 < 60% | 加 dual-track reading (KG active-chain summary 注入 context) |
| Phase 3 對非 KU multi-hop 傷害 > 2pp | scaffold 改 conditional-on-superseded-edge-hit |

## B.6 簡報中曾考慮但 v1 暫不做的方向

> 這些是 pptx 簡報中的延伸 idea, v1 不做, 但記下來避免遺忘

| Idea | 狀態 | 預期觸發 v2 的條件 |
|---|---|---|
| **Subgraph injection** (把 KG 上 active chain 摘要注入 prompt) | 暫不做 | 若 v1 Phase 2 後 leakage 仍嚴重, granularity mismatch 沒解掉 → 升 v2 |
| **Sequential per-hop retrieval** (拆 query 為 sub-Q, 各 hop 各 retrieve) | 暫不做 | 若 v1 在純 multi-hop 仍不穩定, prompt-only scaffold 不夠 → 升 v2 |
| **Decayed PPR** (edge weight × freshness factor in O4) | 暫不做 | 若 v1 Phase 2 在 O5 filter 效果不佳, 才回到 O4 動 PPR |
| **Episode memory** (記住過去更新模式, 提升 detection) | 不做 (碩論 scope 外) | LongMemEval 多 session 章節 (碩論後續) |

## B.7 程式碼研讀新增的設計觀察 & 開放問題 (2026-05-11)

讀 HippoRAG.py 後浮現三個觀察, 對 v1 spec 都不衝突, 但對 paper framing 跟 v2 方向關鍵。

### B.7.1 Relation 在 vanilla HippoRAG-v2 中的有效範圍

| 階段 | relation 是否參與 | 程式碼證據 |
|---|:---:|---|
| O1 Fact retrieval | ✅ | [`get_fact_scores` L964](methods/hipporag/HippoRAG.py#L964) 用 `fact_embeddings`(來自 `str(triple)` 完整 tuple), relation 文字參與 query↔fact similarity |
| O2 Recognition rerank | ✅ | [`rerank_facts` L1170](methods/hipporag/HippoRAG.py#L1170) 給 LLM 看 (s,r,o) 完整 tuple |
| O3 Seed weight | ❌ | [`graph_search_with_fact_entities` L1108-1113](methods/hipporag/HippoRAG.py#L1108-L1113): 只取 `f[0]`(subject) + `f[2]`(object), `f[1]`(relation) 丟掉 |
| O4 PPR propagate | ❌ | fact edge 只連 entity↔entity, 無 relation attribute |
| O5 Passage ranking | ❌ | 純 PPR mass 排序 |
| O6 QA reading | ✅ | 原文 chunk 還含 relation 文字, LLM 看得到 |

→ **Relation 在 graph propagation 階段 (O3-O5) 完全 collapse**。對 Phase 1 (S, R, ≠O) 衝突偵測 → 必須在 **fact_key 層**做(保留 relation), 不能在 graph edge 層(relation 已丟失)。

→ **Paper framing 含意**: 若強調「KG-native 衝突機制」, 可附帶指出 vanilla v2 的設計缺陷 — relation 在 graph layer 沒地位。是否擴充到「保留 relation 的 KG」(relation as edge attribute / typed edge) 屬 v2/未來方向, 碩論可 mention 不深做。

### B.7.2 Multi-hop query 上 hop 1 vs hop 2+ 衝突的非對稱性

#### 核心觀察 — Discoverability Asymmetry (補, 2026-05-11)

> ⚠️ **Epistemic status**: 此節含**直觀推理 + 既有 evidence + 待驗證假設**。請看 §B.7.2.bis 的 claim status 表分清楚, 不要把直觀當定論。
>
> Type-1/2/3 (下面表格) 是**症狀**, 此節是**機制**。理解此機制才知道 v2 該往哪走。

多跳 query 的訊息來源不對稱:

| 訊息 | Query 文字可揭示 | 必須查記憶庫才知道 |
|---|:---:|:---:|
| Hop 1 entity (subject) | ✓ | |
| Hop 1 relation | ✓ | |
| Hop 1 object (= hop 2 subject) | | ✓(從 KG 查) |
| Hop 中間 bridge entities | | ✓ |
| Hop 數量(2/3/4?) | | ✓ |
| Per-hop supersession 狀態 | | ✓(從 Phase 1 metadata) |
| Hop-last relation(若 query 含「what is X of Y」) | ✓(部分) | |

→ Semantic retrieval (query embedding × fact embedding) 本質上**只能高分擊中 hop-1 + hop-last 相關 triple**, 因為 query 文字裡其他東西都未知。HippoRAG 用 **PPR graph traversal 補這個 gap** — 但同時也把 chain_old 拉進來(chain_old 跟 chain_new 共享 hop-1 entity 當圖鄰居)。

#### 對 Phase 2 「兩端都 high PPR mass 才 filter」規則的意涵

我們的規則本質上是**用「圖距離」當「query 推理鏈相關性」的 proxy**:
- ✅ Type-1 hop 1 直接衝突: Twitter + Jack 都是 PPR seed/鄰居 → 命中, 規則對
- ❌ Type-3 satellite: `(Jack, citizenship, US)` 的兩端 (Jack, US) 都 high mass(透過 Twitter 連到), 但**這條 triple 本身不是 superseded**, 規則漏。問題不在 mass, 在 supersession 沒從 hop-1 propagate 到 hop-2

→ **Phase 2 規則做不到的事**: 區分「跟 query 推理鏈相關的 chain_old」vs「跟 query 無關的其他 olds」, 因為 query 文字本身看不到推理鏈中段。

**Retrieval 層**(原段落保留): hop 2+ entity 不在 query 文字, 但 HippoRAG-v2 靠 **PPR 多跳擴散** 拉到 — chain_new 跨 hop level retrieval rate 94-97% (motivation §1.5) 證實這條路徑 work。同時也把 chain_old hop 2 satellite 拉進 retrieval。

**衝突偵測層 (新發現)**: hop 1 跟 hop 2+ 的衝突**結構不對稱**, 拆解三種 type:

| 類型 | 例子 | 我們 (S, R, ≠O) 規則能否抓 |
|---|---|:---:|
| **Type-1** 直接衝突 (多在 hop 1) | `(Twitter, CEO, Jack)` vs `(Twitter, CEO, Bernard)` — 同 (S, R) | ✅ |
| **Type-2** hop 2+ 直接衝突 | `(Jack, citizen, US)` vs `(Bernard, nationality, France)` — S 不同, 不是同 (S, R) | ❌ |
| **Type-3** satellite leakage | `(Jack, citizen, US)` 本身對(Jack 真是美國人), 但 query 已不問 Jack | ❌ — 此 fact 不是 superseded |

→ **(S, R, ≠O) 規則是「hop 1 友善, hop 2+ 盲」的偵測機制**。這可解釋為什麼之前 V0 在 FC-MH 上 by hops 2/3/4 分別 52/33/18% — hop 越多, Type-2/3 比例越高, 偵測 recall 越掉。

→ **v1 不解 Type-2/3**, 但 v1 跑完後**量化 FC-MH 答錯題目中 Type-2/3 的佔比**, 決定 v2 優先度。

→ **v2 候選方向(對應 discoverability asymmetry 的不同解法)**:

| 方向 | 機制 | 用記憶庫的哪個訊息 | 預期 generalization |
|---|---|---|:---:|
| **(α) Chain_old anchor propagation** (最小增量) | Phase 1 標 `(S, R, O_old)` 同時把 O_old 加入 `chain_old_anchor_entities`;Phase 2 對任何 passage triple, 若 subject 是 anchor 且 anchor 在 query-time PPR mass high → 視為 satellite filter | supersession metadata + PPR mass | 中(不依賴 FC 特性) |
| **(β) Sequential per-hop retrieval** | Query 拆 sub-questions, 每 hop 各 retrieve, grounding 後再走下 hop;每 hop 各自用 supersession 過濾 | query decomposition + 逐 hop 記憶查詢 | 高(KG-agnostic) |
| **(γ) Subgraph injection** | 對 query hop-1 entity 抽 KG 子圖(含 supersession metadata), 把「active chain summary」注入 prompt | KG 結構 + supersession | 高(KG-native) |
| **(δ) Decayed PPR** | superseded fact edges weight × 0.1, PPR 源頭抑制 chain_old propagation | supersession metadata 嵌入 PPR | 高(純結構) |

→ **(α) v1 → v2 最小增量**;**(γ) 跟 paper Claim 2 連結最直接**(它本質上是 Phase 2+3 雙重身份);**(β) 跟「Phase 3 不依賴 prompt 文字」未來規劃對齊**;**(δ) 已在 B.6 標 v2 deferred**。

→ **Paper framing 含意**: 把 discoverability asymmetry 發展成「**多跳衝突需要 chain-aware 偵測, 非單 triple 偵測**」獨立 claim, 可放進 Gap 4(motivation §5.1 已有類似的但偏 retrieval format)。這個 framing 比 Type 1/2/3 分類更深, 因為它解釋了「**為什麼**單 triple 偵測不夠」 — 不是因為偵測規則的工程缺陷, 是 query-time information 結構性不對稱。

#### B.7.2.bis Claim epistemic status & 驗證計畫 (2026-05-11)

| Claim | 狀態 | 既有 evidence | 待驗證項 |
|---|---|---|---|
| **C1** Query 只揭示 hop-1 entity + hop-last relation, 中段 entity 看不到 | 部分有 evidence | motivation §1.5: hop-2+ chain_new fact 仍 94-97% 進 top-k(靠 PPR 而非 query similarity) | 量化 hop-1 vs hop-2+ fact 在 `query_fact_scores` 上的 rank/score 分布差距 |
| **C2** PPR 把 chain_old hop-2 satellite 拉進 retrieval | **已驗** | motivation §1.5: chain_old 命中 ≥97%, top-10 覆蓋 83% corpus | ✓ |
| **C3** Chain_old satellite 是答錯主要 driver | 未量化 | motivation §4.2: 28-29% 答錯 含 chain_old(但沒拆直接衝突 vs satellite) | method_v1_spec.md §6 Step 5 |
| **C4** Phase 2「兩端 high mass」對 Type-3 失效 | 邏輯推論 未實測 | 規則只 trigger superseded fact, satellite 本身不是 superseded | v1 跑完直接看 P1+P2 答錯題的 Type 比例 |
| **C5** PPR mass 是「query 推理鏈相關性」的好 proxy | **未驗證** (Phase 2 規則的隱含假設) | (無) | **可現在驗**: chain_new entity vs unrelated old entity 的 PPR mass 分布是否區分得開 |
| **C6** PureChain→OA2 36pp gap 純是 retrieval coverage + parametric leak | 部分推論 | motivation §2.B 結尾 | v1 跑完後可重新拆解 |

→ **C5 影響 v1 設計本身** — 若 PPR mass 對 chain_new / unrelated old 區分不開, 「兩端 high mass」proxy 失效, Phase 2 規則需 v1 階段就改, 不能等 v2。**建議去 GB10 前先在 mac 上驗 C5**。

→ C1 / C3 是 paper framing 強度問題, 影響 v2 方向決策, 不影響 v1 是否能跑。

### B.7.3 PPR temporal blindness 跟 supersession 的整合策略

**核心觀察**: [`run_ppr` L1203](methods/hipporag/HippoRAG.py#L1203) 純結構演算法, 只接 `reset_prob + damping + edge weight`, **沒有時間軸概念**。Supersession metadata 是 orthogonal subsystem。

**三條整合路徑**:

| 路徑 | 機制 | 優點 | 缺點 |
|---|---|---|---|
| **(A) Post-PPR filter** ← v1 採用 | PPR 跑完, 在 O5 後用 supersession × high-mass 規則 filter/demote | 不破壞 PPR 性質, supersession 跟 PPR 解耦, v1 最低風險 | hop 2+ satellite (Type-3) 不被自動處理 |
| **(B) Pre-PPR seed gating** | chain_old entity 的 `reset_prob = 0` | 從源頭切斷 chain_old propagation | 若 chain_old entity 是 hop 1→hop 2 唯一橋樑(query 含 X, X 連 chain_old, chain_old 連答案), 會斷 hop 2 連通 → 損失 chain_new retrieval |
| **(C) In-PPR edge weight decay** | superseded fact 對應的 fact edge weight × 0.1 之類, mass 沿這條邊衰減 | 跟 PPR 自然整合, 不切斷只是降流 | 需修 igraph edge attribute, 工程量大; 已在 B.6 標 v2 deferred |

→ v1 走 (A) 但要在 paper / v2 規劃明寫: **PPR 跟 supersession 在 v1 是兩個獨立 subsystem, Phase 2 在 PPR 後做最終裁決**。

→ 若 v1 (A) 效果不夠好, v2 優先試 (C) decayed PPR(B 風險最高暫不考慮)。

### B.7.4 對 v1 spec 的補丁總結

整合 B.7.1-3 對 §B.3 的影響:

| Phase | 變更前 (chat 原版) | 變更後 (程式碼端對齊) |
|---|---|---|
| Phase 1 機制 | 在舊 **edge** 加 metadata | 在舊 **fact_key** 加 metadata (B.7.1 relation collapse) |
| Phase 1 儲存 | `node_to_node_stats` 邊屬性 | `self.superseded_facts` dict + `self.chunk_to_fact_keys` map |
| Phase 2 偵測範圍 | catches Type-1 only | 同上(v1 不擴充), 但**v1 跑完量化 Type-2/3 比例**指引 v2 |
| Phase 2 vs PPR 關係 | (未明) | Post-PPR filter (B.7.3 路徑 A) — orthogonal subsystem |
| Phase 3 | always-on universal scaffold | 同(不變) |
