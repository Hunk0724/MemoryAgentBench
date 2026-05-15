# §B 方法骨架快查

## B.1 HippoRAG-v2 原方法流程 (我們的 base)

> **為什麼這節重要**: 我們所有改動都是在 HippoRAG-v2 既有 pipeline 的特定 step 動刀。寫 Ch.3 method 時要清楚對讀者解釋「HippoRAG-v2 原本怎麼做」+「我們在哪個 step 改」。

### Offline Indexing (建索引時一次)
| Step | 動作 |
|---|---|
| I1 | LLM 對每 passage 跑 OpenIE, 抽 `(s, r, o)` triples |
| I2 | NV-Embed-v2 fp16 forward 算 chunk / entity / fact embeddings |
| I3a | `add_fact_edges`: phrase ↔ phrase edges in KG |
| I3b | `add_passage_edges`: passage → entity edges in KG |
| I4 | `add_synonymy_edges`: entity KNN cosine ≥ 0.8 |
| I5 | save `graph.graphml` |

### Online Retrieval & QA (每 query 一次)
| Step | 動作 | 我們動刀位置 |
|---|---|---|
| O1 | `get_fact_scores`: query × fact_embeddings cosine | (v1 不動) |
| O2 | `rerank_facts`: LLM judge top-k fact triples | (v2 可選 hook: 加 superseded triple filter) |
| O3 | Seed reset weights: phrase + 0.05·DPR passage | (v1 不動) |
| O4 | `run_ppr`: PPR propagate, return full pagerank_scores | (v2 可選: edge weight × freshness factor) |
| O5 | Passage ranking & selection (top-N) | **v1 Phase 2 主戰場** |
| O6 | `rag_qa`: passages → LLM context → QA | **v1 Phase 3 主戰場** |

### 關鍵限制 (paper Ch.3 要點出)
- **Granularity mismatch**: LLM 看到的是 passage 原始文字, KG 上的 supersedence metadata 無法直接 propagate 到 LLM context, 只能透過影響 passage ranking
- **Passage 異質性**: 一個 chunk (512 token) 同時含 superseded + active fact。FC 上不嚴重 (chunk 內 fact 關聯弱), 但延伸到自然對話時是 v2 主要 challenge

## B.2 v1 三階段位置

```
─ Offline Indexing ─────────────
I1. OpenIE                                    
I2. Embeddings                                
I3. add_fact_edges + add_passage_edges  ← Phase 1 hook: 標 (s,r,≠o) superseded metadata
I4. add_synonymy_edges
I5. save graph.graphml

─ Online Retrieval & QA ────────
O1. fact scoring
O2. rerank_facts (LLM judge)
O3. seed weights
O4. run_ppr → full pagerank_scores
O5. top-N passages                      ← Phase 2 hook: chain-aware filter via PPR mass
O6. rag_qa (LLM)                        ← Phase 3 hook: universal reasoning scaffold
```

## B.3 v1 as built (v1.1 修正版, 對應 Method v1 spec §3)

### Phase 1 — Conflict-Aware Fact Annotation (write-time, after I3 before I4)

**機制**:
1. 對所有 OpenIE triples, group by `(s.lower(), r.lower())`
2. 對 same `(s, r)` 但不同 `o` 的 bucket, 標較早 chunk 對應 fact 為 superseded
3. Metadata: `{by_fact_key, observed_chunk_idx, superseder_chunk_idx, s, r, o_old, o_new}`
4. 持久化到 `supersession_index.json` (next to graph.graphml)
5. **新舊 fact 都保留**, KG 結構不變, PPR transition 不受影響

**Implementation 細節 (對應 Method v1 spec §3.1)**:
- `HippoRAG.__init__`: 加 `self.superseded_facts` dict + `self.chunk_to_fact_keys` map
- Hook: `index()` L280-283
- Algorithm: `_phase1_scan_supersession` L816
- Feature flag: `enable_supersession` (default False)

**v1 結果** (verified):

| Assertion | Target | Measured | Pass? |
|---|---|---|---|
| A1.1 不傷 vanilla | EM = baseline ±1pp | MH 19/100 + 0pp, SH 75/100 + 0pp (bit-identical) | ✅ |
| A1.2 Detection recall (per-hop) | ≥ 41% (Mem0 baseline) | **68/188 = 36.2%** | ❌ -4.8pp short |
| FP rate (OpenIE noise) | low | **1.4%** (1/72 真實 FP) | ✅ deterministic exact-match 穩健 |

**Detection 比較 (motivation §4.3.A format)**:

| Split | Phase 1 v0 | Mem0 | Zep |
|---|---|---|---|
| FC-MH per-hop | **36.2%** | 59% | 38% |
| FC-MH all-detected (per-Q) | **19** | 41 | 20 |

→ Phase 1 v0 ≈ Zep on detection (deterministic 跟 temporal annotation 等同 detection coverage), 但比 Mem0 (LLM judge) 弱 ~20pp。

**Detection 失敗 root cause 分析** (Method v1 spec §13):
- 30% missed: OpenIE 完全沒抽到 chain_old triple
- 35% missed: same S 不同 R surface form (e.g., "married to" vs "is the spouse of")
- 38% missed: same (S, R) 但 false match (大半也是 surface 變體)
- → **70%+ 是 surface variation**, deterministic (S, R, ≠O) exact match 有結構性 ceiling

### Phase 2 — Chain-Aware Passage Filtering (query-time, after O4 before O5)

**機制 (v1 final, percentile=99)**:
```
PPR 收斂後:
  1. high_mass_entities = phrase nodes with PPR score ≥ percentile(scores, 99)
                          → top 1% phrase nodes (約 3 個 entities)
  2. for each candidate passage p in PPR-ranked top-N:
       sup_edges = [edge in p.source_triples if edge.superseded_by exists]
       if not sup_edges: keep p
       else for edge in sup_edges:
           if both endpoints (edge.s, edge.o) in high_mass_entities:
               // chain-old: filter p
               drop p; break
           else:
               // other-old: keep p
```

**Implementation (對應 Method v1 spec §3.2)**:
- `run_ppr` return signature 改: `(sorted_doc_ids, sorted_doc_scores)` → `(..., pagerank_scores_arr)`
- Hook: `graph_search_with_fact_entities` L1415-1417
- Algorithm: `_phase2_filter_chain_old` L936
- Feature flag: `enable_phase2_filter` (depend on enable_supersession)

**Percentile sweep result (X 值決定過程)**:

| Percentile | MH EM | Δ MH | SH EM | Δ SH | 解讀 |
|---|---|---|---|---|---|
| 80 (top 20%) — 起手 | 12% | -7pp | 35% | **-40pp** | ❌ 過度 filter |
| 90 (top 10%) | 26% | +7pp | 49% | -26pp | ❌ 仍 over-filter SH |
| 95 (top 5%) | 28% | +9pp | 68% | -7pp | 接近, MH 高但 SH 仍退 |
| **99 (top 1%) — final** | **25%** | **+6pp** | **82%** | **+7pp** | ✅ A2.2/A2.3 PASS |

→ **X=99 是 v1 lock 決定** (Method v1 spec §10 verified)。

**v1 結果** (P1+P2-99 with X=99 default):

| Assertion | Target | Measured | Pass? |
|---|---|---|---|
| A2.1 MH ∈ [35%, 50%] | ≥ 35% | 25% (P1+P2 only); 37% (full v1) | ⚠️ Partial — P1+P2 only fail; full v1 marginal |
| A2.2 Filter precision | wins ≥ losses | MH 9/3, SH 11/4 | ✅ |
| A2.3 FC-SH 退步 < 3pp | SH ≥ 72% | SH 82% (+7pp 反而 improve) | ✅ |

### Phase 3 — Universal Reasoning Scaffold (inference-time, in O6)

**機制**: System prompt 末尾 append (passage concat 之後 / `'Question:'` 之前):

> "When the answer requires connecting multiple facts, briefly list the intermediate entities or facts you use, and ensure that any entity appearing in multiple steps is referenced consistently."

**Implementation (對應 Method v1 spec §3.3)**:
- Constant: `_PHASE3_SCAFFOLD_TEXT` L459
- Hook: `qa()` L495-496
- Feature flag: `enable_phase3_scaffold`
- Trigger: **always-on** (v1 不做 conditional gate)

**v1 結果**:

| Assertion | Target | Measured | Pass? |
|---|---|---|---|
| A3.1 Scaffold +20pp on clean context | motivation §2.B V1 +28pp | P3 only on vanilla (dirty): MH +8pp, SH +15pp | ⚠️ 不同數據, 但比預期強 |
| A3.2 非 KU multi-hop 退步 < 2pp | MuSiQue/2Wiki | **TBD** (Step 4 待跑) | TBD |

**比預期強的可能原因** (Method v1 spec §10):
- 我們措辭比 motivation V1/V2/V3 trailer 強
- Gemini 3.1 Flash-Lite 對 universal instruction-style scaffold 反應好
- 在 dirty context (chain_old + chain_new 共存) 中, "list intermediate entities consistently" 引導 LLM 跳出 chain_old

## B.4 觀察→方法決策對應表 (v1.1 加 verification 列)

| 觀察 (motivation §) | 方法決策 | v1 實際結果 | 驗證狀態 |
|---|---|---|---|
| PureChain 97% (§1.A) | 任務本身可解 → 處理 KU+MH 交集 | confirm | ✅ |
| 25.8pp emergent gap (§2.A.X) | 需結構化方法 | confirm | ✅ |
| +34pp (chain_old) vs +5pp (other_old) (§2.A) | Phase 2 must be **query-aware** | confirm — P1+P2-99 SH 不退步 verify query-aware filter | ✅ |
| n_inject 0→1 -49pp (§2.A.b2) | filter recall 要高 | partial — Phase 1 36% recall 是 ceiling | ⚠️ |
| V1/V2/V3 都 +28-31pp (§2.B) | scaffold signal robust | **超預期** — dirty context vanilla 也拿 +8/+15pp | ⚠️ Claim 2 framing 修正 |
| Mem0 detection 41%, all-detected MH 仍 63% (§4.3) | retrieval-side filter 必要 (Claim 1) | confirm | ✅ |
| Zep MH all-detected 40% (§4.3.B) | annotation 不夠, 需 inference 端 scaffold (Claim 2) | confirm | ✅ |

## B.5 v2 Reactive Decision Tree (v1.1 升級成 evidence-driven roadmap)

v1 觀察已經明確哪些 trigger 觸發、優先級如何。以下 v2 候選按 ROI 排：

### v2 必做 (按優先級, 依 v1 數據觸發)

| 觸發條件 (v1 觀察) | v2 動作 | 預期 ROI | A/B 類 |
|---|---|---|---|
| A1.2 detection recall 36% < target 41% | **Phase 1 relation alias normalization** (利用既有 synonymy edges; relation 字串也跑 KNN cosine 合併) | +14-24pp detection recall (root cause analysis 35% relation-alias 群組) | A |
| A2.2 EM ≠ filter accuracy (P/Q/R/S 四象限不明) | **Per-filter-event diagnostic** (Method v1 §13.4): log every filter event + GT cross-reference + 4 quadrant classify | 不直接提升 EM, 但 **paper rigor 必做** | A |
| Phase 2 mass-based proxy 局限 (PPR top-1% 已是極限) | **Query-S anchored gate or fact-level excision** (Method v1 §13.3): NER parse query → S exact match | 預期 SH 不再 over-filter, MH 更精準 | A |
| 30% missed 是 OpenIE 沒抽 | (擱置) — Method v1 §13.2 Observation 1: raw passage 保留全部 fact 文字, retrieval pool 仍有, 不致命 | — | — |

### v2 候選 (看必做完後再決定)

| 候選方向 | 機制 | 來源 | A/B 類 |
|---|---|---|---|
| **PropRAG-inspired explicit path discovery** | 在 PPR top-k subgraph 上跑 beam search 找推理鍊, 替代 PPR mass proxy | PropRAG (EMNLP 2025) | A |
| Fact-embedding pairwise cosine detection | 對 NV-Embed-v2 fact embeddings 跑 KNN, top-similar pair 找 same-S-diff-O | (Method v1 §13.3) | A |
| Subgraph injection | 抽 KG 上 active chain 摘要注入 prompt | (簡報延伸) | A |
| Sequential per-hop retrieval | query decompose + 逐 hop retrieve | (motivation §2.B 候選) | A |
| InfoGain-RAG DIG signal | confidence-diff with/without document 當 filter signal | InfoGain-RAG (EMNLP 2025 Oral) | **B (需 logprob, closed API 不可用)** |
| HopRAG helpfulness = similarity + logical importance | 雙重判據替代 PPR mass | HopRAG (Findings ACL 2025) | A |
| TruthfulRAG entropy filter on KG path | entropy-based 替代 X% threshold | TruthfulRAG (AAAI 2026) | A |
| SubgraphRAG 粒度替代 | path → subgraph 抽取 | SubgraphRAG (ICLR 2025) | A |
| Phase 3 升級 (BELLE / BoT / CoVe) | type-aware routing / retrieved scaffold / multi-round verify | 各對應 paper | A |

→ **A 類 = API-only friendly** (closed LLM API 可用), **B 類 = 需 local model 或 logprob access** (有架構限制)。

### v2 真正 contribution 候選 (paper narrative §6 對應)

從 A.3 narrative arc, v2/v3 才是真正 paper contribution。**candidates**:

1. **Explicit chain discovery (PropRAG-inspired)**: 借鑑 PropRAG Stage 2 beam search 的概念, 把推理鍊 explicitly discover 出來 (而非 PPR mass proxy), 再判斷哪些 fact 是 chain-old
2. **Fact-level excision**: 從 passage 文字裡刪該 superseded fact 對應 sentence/span, 而非整 passage filter
3. **Query-anchored anchor propagation**: NER parse query → 從 hop_1 entity propagate, 對 superseded fact 做 S-match 判斷

→ 這幾個候選哪個成為「真正 contribution」, 取決於 v1 §13.4 per-filter-event diagnostic 結果。**待 G.11 close 後決定**。

## B.6 簡報延伸 idea (v1.1 加 prior art 對應)

> v1 不做的延伸 idea, 標記 prior art 對應供 v2 借鑑

| Idea | 簡報出處 | Prior art 對應 | 預期觸發 v2 條件 |
|---|---|---|---|
| Subgraph injection | pptx | — (我們 cleanroom) | Phase 2 後 leakage 仍嚴重 |
| Sequential per-hop retrieval | pptx + motivation §2.B | IRCoT (Trivedi+ ACL 2023), Self-Ask (Press+ EMNLP 2023) | scaffold-only 不夠 |
| Decayed PPR | pptx | (cleanroom; 接近 temporal PageRank Rozenshtein KDD 2016) | Phase 2 在 O5 後 filter 不佳, 才回 O4 動 |
| Episode memory | pptx | HSE (NeurIPS 2025), PREMem (Findings EMNLP 2025) | LongMemEval 多 session (碩論後續) |
| Explicit path discovery (新) | (推導自 PropRAG) | PropRAG (EMNLP 2025 Main) | PPR mass proxy 達 ceiling |

## B.7 PropRAG 三層價值 (v1.1 新增) ⭐

PropRAG (Wang & Han, EMNLP 2025) 跟我們的關係不是「同步動 step」, 是更深的 **方法論啟發**:

### 層 1 — Engineering 參考 (淺)
codebase fork 自 OSU-NLP-Group/HippoRAG (`ReLink-Inc/PropRAG`), 證明「在 HippoRAG-2 上加 post-PPR refinement」是 viable engineering pattern。

### 層 2 — 方法概念對齊 (中)
- PropRAG Stage 2 beam search 解的是 **explicit path discovery** (找推理鍊)
- 我們 Phase 2 解的是 **chain-aware conflict filtering** (在推理鍊上判 chain-old)

**Common ground**: 兩者都認為「PPR mass + graph structure 不足以直接判定推理鍊, 需要 explicit path-level processing」。
**不同 axis**: PropRAG 解 retrieval recall (找到 evidence), 我們解 retrieval precision (移除 superseded)。

### 層 3 — Paper narrative 核心啟示 (深) ⭐
PropRAG 的 explicit beam search 對應 paper narrative §6 候選 contribution: **如果 PPR top-X% mass 當 chain anchor proxy 不夠精準, 可借鑑 PropRAG 的 explicit beam search 做 path discovery, 把推理鍊真的「discover」出來而非用 mass proxy。** 在這個 explicitly-discovered path 上做 chain-old/other-old judgement, 比 v1 的 mass-based proxy 更精準。

**v2 嘗試方向 (待 implement)**:
- Phase 2 v2 candidate: 在 PPR top-k subgraph 上跑 beam search (LLM-free, 用 fact embedding cosine + graph traversal) 找 reasoning paths → 對每 path 上的 facts 判 superseded
- 工程細節: 你可以 clone PropRAG repo, 跟 Claude Code 討論「如何在 HippoRAG-v2 already-modified codebase 上整合 PropRAG Stage 2 beam search」

## §G.B v1 → v1.1 新增 open questions (v2 設計時要決定)

- 🔴 **G.11** [DECISION needed] §C.4.2 per-filter-event (P/Q/R/S) diagnostic — v2 開始前先做 (paper rigor), 還是與 v2 並行做 (時間效率)? **建議: 先做, 因為 paper §C.4 章節必須有這個 data**。預計 W2-W3 動。
- 🔴 **G.12** [DECISION needed] §B.5 v2 必做動作的優先序: relation alias normalization (Phase 1) vs query-S anchored gate (Phase 2) vs fact-embedding pairwise detection (Phase 1 升級)? **依 G.11 結果決定**。
- 🔴 **G.13** [DECISION needed] §C.5.1 real gap framing 三選一: (P) dominant / (Q) dominant / (R) dominant — **完全 depend on G.11 結果**。



### Claude code 這邊的討論
你的定義
| 象限 | 定義 | 歸因 |
| --- | --- | --- |
| **P** (true filter) | filter 掉的是 chain\_old,EM 正確 | ✅ 兩階段都對 |
| **Q** (false filter) | filter 掉的是 chain\_new,誤殺 | P2 chain-anchor 錯(把不在鍊上的 fact 當 chain-old) |
| **R-P1** (miss, P1 沒偵測) | chain\_old 還在 top-N,但 P1 沒抽到 superseded label | P1 detection recall 不足 → 走 relation alias / fact-pairwise |
| **R-P2** (miss, P1 偵測但 P2 沒抓) | chain\_old 在 top-N,P1 有 label,但 (s, o\_old) 沒進 top-1% | P2 chain-anchor 不夠精準 → 走 PropRAG propagation |
| **S** (silent filter) | filter 對的但 EM 沒變(其他 passage 有答案) | 中性 |

→ **G.11 不只告訴我們「filter 對不對」,還能告訴我們 v2 該動 P1 還是 P2**

而過去的結果
| Condition | MH EM | Δ MH vs vanilla | MH wins/losses | SH EM | Δ SH | SH wins/losses |
| --- | --- | --- | --- | --- | --- | --- |
| **vanilla** | 19% | — | — | 75% | — | — |
| **P1 only** | 19% | +0pp | 0/0 | 75% | +0pp | 0/0 |
| **P3 only** | 27% | **+8pp** | 14/6 | **90%** | **+15pp** | 16/1 |
| **P1+P2-99** | 25% | +6pp | 9/3 | 82% | +7pp | 11/4 |
| **P1+P2+P3(full v1)** | **37%** | **+18pp** | **22/4** | **89%** | **+14pp** | **18/4** |

#### 表面層: rule-based 太嚴 → false positive

"User likes Apple" vs "User likes Banana" 不是衝突,deterministic `(s, r, ≠o)` 會誤判。

#### 但這只是症狀,真正的問題是 **conflict 本身是 semantic 概念,不是 syntactic 概念**

`(s, r, o)` 同 (s, r) 不同 o 是否衝突,取決於 r 的 **functional 性質**:

| Relation 類型 | 範例 | 同 (s, r) 不同 o 是衝突嗎? |
| --- | --- | --- |
| **Functional** (1對1) | `is_president_of` / `was_born_in` / `is_capital_of` | ✅ 是衝突 — 一國只有一個 president |
| **Cumulative** (1對多, 累積) | `likes` / `has_visited` / `knows` | ❌ **不是衝突** — 可同時擁有多個 |
| **Temporal-functional** (1對1 但隨時間變) | `works_at` / `lives_in` / `married_to` | ⚠️ **依時間判斷** — 同時點功能性, 跨時點演化 |
| **Aggregated** (多筆共同建構) | `has_skill` / `has_published` | ❌ 累積, 但個別可被撤回 |

→ MQuAKE 的設計刻意只用第 1 類 (functional) 製造 explicit conflict, 所以 deterministic 在 FC-MH 上能拿 36% recall + 1.4% FP。但**這個 FP 1.4% 是 dataset 偏差,不是 method 真實 robust**。

---

## §H Session 2026-05-15 累積 finding(v2 LLM judge 路線)

### H.1 G.11 完整 diagnostic 數據(MH n=182 hops, P1+P2-99 lock 配置)

| Status | Count | % | EM rate |
|---|---|---|---|
| **A** (chain_old not in top-N) | 0 | 0% | — |
| **B** (P-filtered, filter correctly removed chain_old) | 35 | 19.2% | 42.9% |
| **C** (R-P2 — P1 偵測但 P2 chain-anchor 沒抓) | 38 | 20.9% | 23.7% |
| **D** (R-P1 — P1 detection gap) | **109** | **59.9%** | 11.9% |

**Phase 2 衍生 metric**:
- Filter recall (B / 182) = 19.2%
- Filter success given P1 detected (B / (B+C)) = 47.9%
- Filter damage (Q-誤殺 chain_new / 182) = 4.4%

**SH side**: 63 filter events,有 filter EM 81.5% vs 無 filter 82.6% → 中性,**不傷 SH** ✅

**結論**:**R-P1 (109 / 59.9%) 是 v1 最大瓶頸 — P1 detection 在 surface variation 上有結構性 ceiling**。

### H.2 Variant B(fact-embedding cosine pairwise as P1 replacement)feasibility

| Coverage 統計 | 數量 |
|---|---|
| 188 has_pair hops 中 chain_old 跟 chain_new 都有 fact embedding | **120 (63.8%)** ← Variant B ceiling |
| OpenIE 兩端都沒抽到 | 33 (17.6%) |

**Cosine 分布**:
- Conflict pair (n=120): mean=0.88, range=[0.73, 0.95]
- Random pair (n=2000): mean=0.52, p95=0.64
- **Median gap 0.23, 但 tail overlap 存在**

**Threshold sweep**:
| Threshold | Recall | Random FP 率 |
|---|---|---|
| 0.80 | 97.5% | 0.35% |
| 0.85 | 80.8% | 0.20% |

→ **PARTIAL separation**,純 cosine 過 80%,但需要 same-S gate 才能避免 random pair noise。

### H.3 LLM judge as detection — 兩階段 smoke test

#### H.3.1 Small curated pool (n=7-11 facts per query)
- Pool 構成:GT chain_old + chain_new + 5 random distractors
- Prompt 設計:LLM 只做 conflict grouping(用 Wikidata 4 類 cardinality taxonomy),direction 用 chunk_idx(=seq)deterministic 推
- **結果:5 queries,Direction recall 90%, Precision 100%, Distractor FP 0**
- 確認 LLM 在小 pool 內**完全能 group same-(s, r) ≠o**

#### H.3.2 Production-scale pool (n=30-449 facts per query)
- Pool 構成:從 top-N PPR-ranked passages 抽出所有 facts(FC-MH 6k 只有 12 chunks,top-20 ≈ 全 corpus = 449 facts)
- Cosine 預過濾後 K=30:**recall 跌到 20%**
- 純全 corpus K=ALL:**recall 0%**
- LLM 在大 pool 下出現 **garbage grouping**:
  - 把 share token 但不同 (s, r) 的 fact group 在一起
  - Example: `"charles dickens author of OMF"` ↔ `"charles dickens married to catherine"`(不同 r,LLM 卻 group 進同 group)
  - Example: `"charles dickens married to catherine"` ↔ `"charles darwin married to amala paul"`(不同 s,LLM group 進同 group)

#### H.3.3 Root cause 確認:**OpenIE relation surface variation 是失敗主因**
- 比對:
  - **qid=20** Vito Corleone conflict ✅ LLM 抓到 — 兩端 relation 都是 `created by`(surface 一致)
  - **qid=0** Our Mutual Friend conflict ❌ LLM 漏 — 兩端 relation 是 `author` vs `was authored by`(surface 不同)
  - **qid=0** Charles Darwin spouse 漏 — `spouse` vs `married to`(surface 不同)

→ **LLM judge 跟 deterministic rule 同樣中 surface variation 招**,只是 LLM 在 small pool 有 "閱讀" 能力可以救一部分,在大 pool attention 失準後就一起 fail。

### H.4 Architectural gap:fact storage 沒綁 source sentence

實際 check `vdb_fact.parquet` + `openie_results.json`:

| 儲存物 | 內容 | 是否含 sentence-fact 綁定 |
|---|---|---|
| `vdb_fact.parquet` | `hash_id` + `content="('s','r','o')"` + 4096-d embedding | ❌ — embed 的是 stringified triple |
| `vdb_chunk.parquet` | chunk_key + 整 passage 文字 | ❌ — passage 級別 |
| `openie_results.json` | per chunk: `{passage, extracted_triples}` | ❌ — list 平行,沒指針 |

→ **HippoRAG-v2 抽完 OpenIE 後丟失了 source sentence 連結**,LLM 看到的是 stringified triple 不是 natural sentence。

### H.5 對 v2 設計方向的 implication

**我們目前在 `exp/v2-llm-judge` branch,v2 wiring 已 implement(LLMJudgeDetector + HippoRAG.py hooks + filter/annotate 兩模式),但 production scale smoke 顯示這個架構不可行**。

**三個候選方向**:

| 方向 | Effort | 對 FC | 對自然對話 | Paper narrative |
|---|---|---|---|---|
| **(0) FC-specific sentence 重建** — 用 numbered list 結構 post-hoc 找 source sentence | 1 天 | ✅ 可驗證假設 | ❌ | 弱(FC-hack) |
| **(1) PropRAG 提案 — proposition-level KG 改造** | 1-2 週 | ✅ | ✅ | 強(architectural contribution) |
| **(2) 用 HippoRAG-v2 synonymy edges 加 relation alias normalization** | 3-5 天 | ✅ | ✅(部分) | 中(HippoRAG-v2 擴展) |

**下一步建議**(待 chat 討論):
- 先做 **(0)** 快速驗證「surface variation 是真 root cause」(若 sentence form 給 LLM 後 recall 跳回 80%+,證明假設)
- 然後依 chat framing 走 **(1)** 或 **(2)**:
  - 若 paper 走 architecture-level contribution → (1) PropRAG-flavored proposition
  - 若 paper 走 HippoRAG-v2 extension narrative → (2) relation alias via synonymy edges

### H.5.1 Option (0) 快速驗證結果 — sentence form 部分救,沒完全解

實作 FC numbered-list passage 切分 → fact_key → source_sentence 重建(matched 436/449 = 97.1%),把 LLM judge 的 input 從 stringified triple 換成 natural sentence。

| Pool form | Recall | Chain_new 誤殺 |
|---|---|---|
| Small curated pool (n=7-11) | 90% | 0 |
| Production K=30 **triple form** | 20% | 1 |
| Production K=30 **sentence form** | **30%** | 4 |

**結論**:
- ✅ **假設驗證了一半** — surface variation 確實是 root cause 之一(sentence form +10pp 比 triple form 好)
- ❌ **但不是全部** — 30% 仍遠低於 small-pool 90%
- 🤔 **真實 root cause 是多重的**:
  - (a) OpenIE relation surface 變動 — sentence form 部分救
  - (b) Multi-fact-per-chunk → chunk_idx 當 seq 有 collision → mechanical direction 反查可能錯
  - (c) LLM attention 在 30-450 facts 大 pool 中明顯 degrade
  - (d) Query 相關 vs corpus 全域 conflict 混淆 — LLM 抓到的有些是其他 query 的真衝突

→ **單靠 prompt 或 sentence 表示無法解決 production-scale detection 問題**。需要 architectural 改變(PropRAG proposition / HippoRAG-v2 synonymy edge 擴展 / 保留 v1 rule + LLM verify hybrid)。

### H.6 Open questions for chat

1. **Paper contribution framing**:LLM judge as detection 是 v2 唯一方向,還是 v2 應該保留 deterministic rule + 加 LLM verify 作 fallback?
2. **Storage architecture**:proposition-level KG 是 paper §3 method 的主軸,還是只是 implementation detail?
3. **General domain**:目前所有實驗都在 FC-MH 結構化 corpus 上;v2 要不要在 chat 開始前就嘗試 LongMemEval 上看自然對話表現?(這 dataset 已存在但我們尚未 v2 path 測試)
4. **G.12 修正**:G.11 數據顯示 D (P1 gap) >> C (P2 gap),原本 G.12 v2 候選順序 (relation alias 優先) 確認對。但 LLM judge production failure 暴露 deeper 問題 — relation alias 是否仍是 v2 主軸?還是要 pivot 到 proposition-level?
