# Method v1 Spec — HippoRAG-v2 + Conflict Mechanism (locked, 2026-05-11)

> **本文件目的**: GB10 上實作 v1 方法的單一 source of truth。包含設計決策、HippoRAG.py 切入點、falsifiable assertions、實驗順序。
>
> **基礎**: 觀察自 [`motivation_narrative.md`](motivation_narrative.md),設計討論於 [`../../claude_chat_method_design_experiment.md`](../../claude_chat_method_design_experiment.md) §B.3 + §B.7。
>
> **何時更新**: v1 跑完後,把結果記到 §6 並依 §7 reactive tree 決定 v2 動作。

---

## §0 v1 核心定位

- **Baseline**: vanilla HippoRAG-v2 on FC-MH 6k,EM = **22%**
- **目標**: 設計 + 實作 KG-native 衝突機制,不依賴 FC 特有 corpus 結構(numbered fact list),要能 generalize 到一般 KG-based memory
- ****棄用** V0** ([`phase1_v0_auto_supersession.py`](../phase1_v0_auto_supersession.py)) 因為它依靠 FC 的「一個 numbered fact = 一個 triple」格式紅利做 fact-line excision,**不可 generalize**。其 44% EM 不算 v1 的 baseline,只當 diagnostic 不寫進 paper。

---

## §1 Method v1 — 三個 Phase 對應兩 claim

| Phase | 對應 motivation claim | 機制概念 | HippoRAG 切入步驟 |
|---|---|---|---|
| **Phase 1** Conflict-Aware Fact Annotation | Claim 1 (filter chain_old) | 寫入時掃 OpenIE triples, 同 (S, R) 不同 O → 舊 fact 標 superseded metadata | I3 KG 建構結束後(`augment_graph` 內) |
| **Phase 2** Chain-Aware Passage Filtering | Claim 1 (filter chain_old) | 查詢時 PPR 跑完, 用 phrase mass + supersession metadata 判定 passage 是否含 chain-old, 過濾 | O4 PPR 之後、O5 passage ranking 之前(`graph_search_with_fact_entities` 內) |
| **Phase 3** Universal Reasoning Scaffold | Claim 2 (LLM multi-hop stability) | inference 階段加 universal prompt scaffold(不依賴 conflict / 序號) | O6 QA(`rag_qa` system prompt) |

---

## §2 設計決策 (全部 locked)

### Q1 — Phase 2 filter 粒度

**選擇**: **(a) Hard filter at passage level** — 整 passage 從 ranked list 移除

**理由**:
- v1 走最直接路徑,先確認核心機制 work
- 若觀察到傷 FC-SH recall 或 P1+P2 EM 低於 OracleClean-Others (26%) → 迭代到 demote/lost-in-middle reorder (對應 Claim 2 探討)

### Q2 — high-mass 的定義

**選擇**: **(A) PPR 收斂後 phrase node mass top-X%**(X 起手 20%, 待 calibrate)

**理由**:
- 不能用 `top_k_facts` 的 entity 集合(Option B), 因 chain_new 跟 chain_old 兩條 chain 的 entities 同時都會在 top_k_facts → 規則永遠 trigger 失效
- PPR 後 mass 反映 query-aware 結構距離, 跨 hop 都有效

### Q3 — Phase 3 always-on vs conditional

**選擇**: **always-on**, 但 v1 跑 **4-way ablation** 驗證 Claim 2 行為

**Ablation**:
| Condition | 預期 EM | 驗證什麼 |
|---|---|---|
| vanilla | 22% (baseline) | sanity |
| P1+P2 only(無 scaffold) | 35-45% | Phase 1+2 機制效益 |
| P3 only(scaffold on vanilla) | ~22-25% | scaffold 在髒 context 上救不了(motivation §2.B vanilla→V1 +2pp) |
| P1+P2+P3 全套 | 45-55% | scaffold 在乾淨 context 上才釋放(motivation §2.B OA2→V1 +28pp) |

### Q4 — Phase 1 metadata 儲存層

**選擇**: **新建 `superseded_facts` dict + `chunk_to_fact_keys` map, 持久化為 JSON**

**理由**:
- 不污染 `fact_embedding_store`(embedding store 設計 immutable)
- 不掛 graph edge(relation collapse,同 entity pair 不同 r 共用一條 edge)
- 跟既有 KG / embedding store 解耦,容易 serialize + load

```python
# Phase 1 在 HippoRAG instance 加兩個 dict
self.superseded_facts: Dict[str, Dict] = {}
# fact_key → {
#     'by_fact_key': str,            # 哪個 new fact supersede 它
#     'observed_chunk_idx': int,     # 此 superseded fact 在哪 chunk
#     'superseder_chunk_idx': int,   # new fact 在哪 chunk
#     's': str, 'r': str,
#     'o_old': str, 'o_new': str,
# }

self.chunk_to_fact_keys: Dict[str, List[str]] = {}
# chunk_id → [fact_key1, fact_key2, ...]
```

持久化到 `outputs/rag_retrieved/.../supersession_index.json`。

---

## §3 程式碼端切入點

### Phase 1: Conflict-Aware Fact Annotation

**位置**: [`HippoRAG.augment_graph` L757](../../methods/hipporag/HippoRAG.py#L757) 內, `add_passage_edges` 之後、`add_synonymy_edges` 之前

**實作概念**:
```python
def _phase1_scan_supersession(self, chunk_ids, chunk_triples):
    """掃所有 triples, 找同 (S, R) 不同 O 的 fact 對, 後出現者 win."""
    sr_to_facts = defaultdict(list)
    for chunk_idx, (chunk_key, triples) in enumerate(zip(chunk_ids, chunk_triples)):
        for triple in triples:
            if not (isinstance(triple, (list, tuple)) and len(triple) == 3):
                continue
            s, r, o = [str(x).strip() for x in triple]
            fact_key = compute_mdhash_id(content=str(tuple(triple)), prefix="fact-")
            sr_to_facts[(s.lower(), r.lower())].append((chunk_idx, chunk_key, o, fact_key))
            self.chunk_to_fact_keys.setdefault(chunk_key, []).append(fact_key)

    for (s_low, r_low), occurrences in sr_to_facts.items():
        distinct_o = {(o, fk) for _, _, o, fk in occurrences}
        if len(distinct_o) <= 1:
            continue
        # 後 chunk 的 O 勝, 早 chunk 的 O 標 superseded
        latest_idx = max(idx for idx, _, _, _ in occurrences)
        latest_fact_keys = {fk for idx, _, _, fk in occurrences if idx == latest_idx}
        for idx, chunk_key, o, fk in occurrences:
            if idx < latest_idx and fk not in latest_fact_keys:
                self.superseded_facts[fk] = {
                    'by_fact_key': next(iter(latest_fact_keys)),
                    'observed_chunk_idx': idx,
                    'superseder_chunk_idx': latest_idx,
                    's': s_low, 'r': r_low, 'o_old': o,
                }
```

**Hook 位置**:
```python
# augment_graph(), 插在 add_synonymy_edges 之前
if getattr(self.global_config, 'enable_supersession', False):
    self._phase1_scan_supersession(self._last_chunk_ids, self._last_chunk_triples)
```

注意:`augment_graph` 不接收 `chunk_ids` / `chunk_triples`,需要在 [`index` L262](../../methods/hipporag/HippoRAG.py#L262) 把這兩個變數存到 self 上 (`self._last_chunk_ids = chunk_ids; self._last_chunk_triples = chunk_triples`)。

### Phase 2: Chain-Aware Passage Filtering

**位置**: [`HippoRAG.graph_search_with_fact_entities` L1162](../../methods/hipporag/HippoRAG.py#L1162), `run_ppr` return 之後、return passage scores 之前

**前置: 修 `run_ppr` return signature**

[L1203-1242](../../methods/hipporag/HippoRAG.py#L1203) 目前只 return `(sorted_doc_ids, sorted_doc_scores)`, 改成 also return 整個 `pagerank_scores`(numpy array, length = total nodes):
```python
def run_ppr(self, reset_prob, damping=0.5):
    # ... existing code ...
    pagerank_scores = self.graph.personalized_pagerank(...)
    doc_scores = np.array([pagerank_scores[idx] for idx in self.passage_node_idxs])
    sorted_doc_ids = np.argsort(doc_scores)[::-1]
    sorted_doc_scores = doc_scores[sorted_doc_ids.tolist()]
    return sorted_doc_ids, sorted_doc_scores, np.array(pagerank_scores)  # NEW: full scores
```

**Phase 2 邏輯**:
```python
def _phase2_filter_chain_old(self, sorted_doc_ids, sorted_doc_scores, full_pagerank_scores, top_n=20):
    """Filter passages containing chain-old facts (both endpoints high-mass)."""
    # 1. high-mass phrase set (PPR top-X% over phrase nodes only)
    phrase_scores = full_pagerank_scores[self.entity_node_idxs]
    threshold = np.percentile(phrase_scores, 80)  # X=20% → 80th percentile
    high_mass_idxs = set(
        self.entity_node_idxs[i]
        for i, s in enumerate(phrase_scores) if s >= threshold
    )

    # 2. 過濾 candidate passages
    keep_mask = np.ones(len(sorted_doc_ids), dtype=bool)
    for rank, doc_idx in enumerate(sorted_doc_ids[:top_n]):
        chunk_key = self.passage_node_keys[doc_idx]
        fact_keys = self.chunk_to_fact_keys.get(chunk_key, [])
        for fk in fact_keys:
            if fk not in self.superseded_facts:
                continue
            sf = self.superseded_facts[fk]
            s_node_idx = self.node_name_to_vertex_idx.get(
                compute_mdhash_id(sf['s'], prefix="entity-"))
            o_node_idx = self.node_name_to_vertex_idx.get(
                compute_mdhash_id(sf['o_old'], prefix="entity-"))
            if s_node_idx in high_mass_idxs and o_node_idx in high_mass_idxs:
                keep_mask[rank] = False
                break

    return sorted_doc_ids[keep_mask], sorted_doc_scores[keep_mask]
```

**Hook 位置**: 在 `graph_search_with_fact_entities` 最後 return 之前:
```python
if getattr(self.global_config, 'enable_phase2_filter', False):
    ppr_sorted_doc_ids, ppr_sorted_doc_scores = self._phase2_filter_chain_old(
        ppr_sorted_doc_ids, ppr_sorted_doc_scores, full_pagerank_scores
    )
```

### Phase 3: Universal Reasoning Scaffold

**位置**: [`HippoRAG.rag_qa` L361](../../methods/hipporag/HippoRAG.py#L361) — 在 system prompt template 末尾追加

**Scaffold 文字** (universal, 不提 conflict / supersession / 序號):
```
When the answer requires connecting multiple facts, briefly list the
intermediate entities or facts you use, and ensure that any entity
appearing in multiple steps is referenced consistently.
```

**Hook 位置**: 在 `rag_qa` 構造 system prompt 處加 feature flag:
```python
if getattr(self.global_config, 'enable_phase3_scaffold', False):
    system_prompt = system_prompt + "\n\n" + SCAFFOLD_TEXT
```

---

## §4 Feature Flags (baseline preservation)

全部 v1 改動都通過三個 flag 控制,**default False = vanilla behavior**:

```python
# 在 global_config 加三個 flag (default False)
enable_supersession: bool = False        # Phase 1
enable_phase2_filter: bool = False       # Phase 2 (依賴 enable_supersession=True)
enable_phase3_scaffold: bool = False     # Phase 3
```

**Vanilla 跑法**: 三個 flag 都不開, 行為 100% 等同 upstream(已驗證 baseline integrity, 見 [MIGRATION.md §12](../../MIGRATION.md))。

**對應 yaml config**: 在 `configs/agent_conf/RAG_Agents/.../Structure_rag_*_hippo_rag_v2_nv.yaml` 加可選 flag。

---

## §5 Falsifiable Assertions

### v1 跑完後驗證

| ID | Assertion | 驗證方法 |
|---|---|---|
| **A1.1** Phase 1 不傷 vanilla | Phase 1 only(P1 flag on, P2/P3 off)FC-MH EM = 22% ± 1pp | 跟 vanilla baseline 對比 |
| **A1.2** Detection 涵蓋率 | Phase 1 標出的 superseded fact 對 GT chain_old 的 recall ≥ 41%(同 V0 detection 程度) | 比對 `mh_512_mquake_analysis.json` GT |
| **A2.1** P1+P2 提升 EM | FC-MH EM ∈ [35%, 50%](lower bound 35% 必達, stretch 50%) | 直接跑 |
| **A2.2** Chain identification precision | Phase 2 filter 掉的 passages 中, 含 GT chain_old 的比例 ≥ 85% | 比對 GT |
| **A2.3** FC-SH 退步 < 3pp | 同 method 跑 FC-SH, EM ≥ 74%(vanilla FC-SH 77%) | 直接跑 |
| **A3.1** Scaffold 在乾淨 context 上 +20pp 以上 | OracleClean-ThisChain orig 55% → orig+scaffold ≥ 75%(對應 motivation §2.B V1 trailer +28pp ceiling) | 用 OA2 pipeline 跑 |
| **A3.2** Scaffold 不傷非 KU multi-hop | MuSiQue / 2Wiki 上 vanilla+scaffold 退步 < 2pp | 額外 benchmark |
| **A4.1** P1+P2+P3 全套 | FC-MH EM ∈ [45%, 60%] | 直接跑 |

### Critical sanity checks(每個 phase 跑前必跑)

1. **Vanilla reproducibility**: 跑 vanilla(三 flag 都關)EM = 22% ± 1pp(對齊 MIGRATION.md §7 預期)
2. **Phase 1 only 不變 EM**: A1.1 — 若改變 vanilla EM, Phase 1 有副作用, 必須修
3. **P3 only 跑 vanilla context**: A1.1 對應, P3 not save vanilla 證明 Claim 2 假設

---

## §6 實驗執行順序(GB10 上)

### Step 0 — Sanity baseline (~半天)
1. `git tag vanilla-baseline-2026-05-11 HEAD`(鎖當前 state)
2. 跑 `run_hipporag_gemini.sh` 確認 vanilla FC-MH EM = 22%, FC-SH EM = 77%
3. **若不對齊先除錯, 不動 v1**

### Step 0.5 — `chunks` vs `raw_chunks` delta sanity check (~30-60 min)

**目的**: 量化 commit a4845b4 (改用 raw_chunks for HippoRAG indexing) 對 vanilla EM 的影響。確認這個 baseline 修正不會 invalidate motivation 分析(motivation 全是 raw_chunks 下測的)。

**步驟**:
1. 暫時 revert raw_chunks: 在 [`agent.py` L909](../../agent.py#L909) 把 `docs = self.raw_chunks` 改回 `docs = self.chunks`
2. 清掉 KG cache: `rm -rf outputs/rag_retrieved/NV-Embed-v2/factconsolidation_mh_6k/chunksize_512/context_id_0/graph.graphml`(因 timestamp 不同 hash 會變,但這步保險)
3. 跑 `bash run_hipporag_gemini.sh` for FC-MH
4. 比 EM 跟 raw_chunks vanilla(22%)的 delta
5. **revert 改動**: `git checkout -- agent.py` 恢復 raw_chunks

**判斷邏輯**:
| delta | 結論 | 動作 |
|---|---|---|
| < 2pp | raw_chunks 修正影響可忽略 | 繼續 raw_chunks, paper §6 caveats 加 footnote disclose |
| 2-5pp | 修正有實質影響,但 motivation 主結論 likely 不變 | 跟 advisor 討論是否重跑 motivation,或詳細 disclose |
| > 5pp | 修正影響大,motivation 數字位移 | 必須選: (a) 改用 chunks 重跑全套 motivation, (b) 寫信問 upstream 作者 paper 數字是否也用 raw_chunks |

**為什麼這個 check 重要**: motivation_narrative.md 全部數字(vanilla 22%, OracleClean ladder, Mode C dose-response, detection 統計)都是 raw_chunks 下測的。若 chunks 是 upstream paper 的真實 baseline 設定,且 delta 大,我們的 motivation 跟 upstream 不可直接比。



### Step 1 — Phase 1 only (~1 天)
1. Implement `_phase1_scan_supersession` + 兩個 dict + flag
2. 跑 FC-MH+FC-SH, 驗證 A1.1, A1.2
3. 輸出 `supersession_index.json` 持久化

### Step 2 — Phase 1 + Phase 2 (~1 天)
1. Implement `run_ppr` return signature 改動 + `_phase2_filter_chain_old`
2. 跑 FC-MH+FC-SH, 驗證 A2.1, A2.2, A2.3
3. 若 EM < 35%, revisit Phase 2(可能是 X=20% 太鬆/太緊, 或 hard filter 太激進)

### Step 3 — Phase 3 (~半天)
1. Implement scaffold text + flag
2. 跑 P3 only + P1+P2+P3 全套, 驗證 A3.1, A4.1

### Step 4 — Generalization check (~半天)
1. 跑 MuSiQue / 2Wiki(已有 pipeline 可改 minimal), 驗證 A3.2
2. 若 scaffold 在非 KU 上 > 2pp 退步, Phase 3 改 conditional 設計

### Step 5 — 量化 hop 2+ satellite fact 比例 (~半天)
1. 對 FC-MH 答錯題目,human/LLM annotate Type-1/2/3 比例
2. 決定 v2 是否優先做 OLD-entity propagation(見 chat B.7.2)

---

## §7 v2 Reactive Decision Tree(等 v1 結果出來決定)

### §7.0 v1 → v2 的 framing 升級 — 從 Type 分類到 Discoverability Asymmetry

> ⚠️ **Epistemic status**: 此節是**working hypothesis**, 部分 claim 仍待驗證(見 [chat §B.7.2.bis](../../claude_chat_method_design_experiment.md))。**特別 C5「PPR mass 是 query 推理鏈相關性的好 proxy」未驗, 影響 Phase 2 規則本身**, 建議去 GB10 前先在 mac 上驗 C5。

Phase 2 的 open problem(假設成立的話)不是「規則漏哪幾類 (Type 1/2/3)」, 是更深層的:

> **多跳 query 的訊息分布不對稱**: query 文字只能揭示 hop-1 entity + hop-last relation, **中段 bridge entities / hop 數 / per-hop supersession 狀態** 都只能從記憶庫查。Semantic retrieval 只擊中 hop-1 / hop-last triple, PPR 補上多跳但連帶把 chain_old 一起拉。Phase 2 「兩端都 high mass」規則用「圖距離」當「query 推理鏈相關性」proxy — 對 hop-1 直接衝突有效, 對 hop-2+ satellite 失效, 因為 supersession 沒從 hop-1 propagate 到 hop-2。

詳見 [chat B.7.2 完整論述 + epistemic status 表](../../claude_chat_method_design_experiment.md)。

→ v2 各方向都是這個 asymmetry 的不同解法(填補「query 看不到 / 記憶庫才有」的 gap), 不是 Type 1/2/3 各自修補。**前提是 asymmetry 本身在數據上成立** — v1 跑完跟 Check 1-3 (chat §B.7.2.bis) 一起判斷。

### §7.1 v2 候選方向(依 v1 觀察觸發)

| v1 觀察 | v2 對應動作 | 對應 asymmetry 的補法 |
|---|---|---|
| A1.2 detection recall < 50% | 加 entity/relation alias normalization(利用 synonymy edges) | 改善 Phase 1 偵測本身 |
| A2.2 precision < 80%(誤刪過多) | hard filter → soft demote(rerank 而非刪除) | 不改 framing, 改 Phase 2 強度 |
| A2.1 EM < 35% / 過度傷害 retrieval | X=20% 改 calibrate / 改為「兩端有一端 high mass」放寬 | 不改 framing, 改 Phase 2 規則 |
| A2.3 FC-SH 退步 > 3pp | Phase 2 加 trigger gate(只在偵測到 superseded fact 時 trigger) | 減少 false trigger |
| **Step 5 量化 Type-3 satellite > 30%** | **(α) Chain_old anchor propagation** — Phase 1 標 anchor, Phase 2 用 anchor + PPR mass 過濾 satellite | 用 supersession metadata 補 query 看不到的「O_old 是否相關」 |
| FC-MH 仍 < 60% 且 retrieval 內 chain_old satellite 多 | **(γ) Subgraph injection** — 抽 KG 子圖含 supersession metadata 注入 prompt | 用 KG 結構補 query 看不到的「完整 chain 跟 update 狀態」 |
| FC-MH 仍 < 60% 且推理穩定性差 | **(β) Sequential per-hop retrieval** — query decompose + 逐 hop retrieve | 用 query decomposition 揭露 hop 中段 entities |
| A3.2 非 KU 退步 > 2pp | Phase 3 改 conditional-on-superseded-edge-hit | scaffold 不再 always-on |
| 接近 ceiling 但仍想推進 | **(δ) Decayed PPR** — superseded edge weight ×0.1 | 用 supersession metadata 嵌入 PPR, 不靠 query-time 規則 |

---

## §8 對應 paper 章節對照表

| 本文件章節 | 對應 paper 預計章節 |
|---|---|
| §0 vanilla 22% / V0 棄用 | Ch.3 Method introduction, V0 不出現 |
| §1 三 Phase | Ch.3 Method overview |
| §2 設計決策 Q1-Q4 | Ch.3 Method details + 對應 design rationale |
| §3 程式碼端切入點 | (不入 paper, 純實作參考) |
| §4 Feature flags | Ch.4 Reproducibility note |
| §5 Falsifiable assertions | Ch.4 Experimental design / Ch.5 Results |
| §6 實驗順序 | Ch.4 Experimental procedure |
| §7 v2 reactive tree | Ch.6 Limitations & Future work |

---

## §9 References(本文件依賴的其他文件)

- [`motivation_narrative.md`](motivation_narrative.md) — 所有 claim + evidence 出處(必讀)
- [`../../claude_chat_method_design_experiment.md`](../../claude_chat_method_design_experiment.md) §B.3 + §B.7 — 設計討論完整脈絡
- [`method_design.md`](method_design.md) — 抽象 functional requirements + 多 instance design space
- [`A_pipeline_alignment_verification.md`](A_pipeline_alignment_verification.md) — Mem0/Zep 跟 HippoRAG-v2 pipeline 對齊驗證
- [`../../MIGRATION.md`](../../MIGRATION.md) §12 — Baseline integrity report
