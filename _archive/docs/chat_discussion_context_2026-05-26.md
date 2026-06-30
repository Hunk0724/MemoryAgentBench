# Context for Chat Discussion — Multi-hop Conflict Detection on HippoRAG-v2

**Date**: 2026-05-26
**Purpose**: 把目前研究全局 + 今日改動 + 待解 design 問題 + 完整設定一次給 chat,讓 chat 能(a)對任意環節給改進想法,(b)幫忙找 path scoring / multi-hop reasoning 的相關文獻參考。

---

## §0. TL;DR

- **Research goal**: 給 HippoRAG-v2 加 conflict-aware extension,用 FactConsolidation (FC) MH-6k 100Q 當 benchmark
- **Current best**: FC-MH EM = 31%(vanilla A=17, +Phase 2 = 31)
- **Filter ceiling 撞牆 ~31**(嘗試多種 filter variants 都沒突破)
- **Detection 改進實測**(2026-05-27):path scoring 三變體 + verdict bidir 在 detection 端有小幅提升(proprag 4-hop +11.5pp recall)**但 EM 仍卡 29-31** — filter / inference 才是 ceiling
- **★★ Strategic re-examination(§11)**:**今天最重要的反思**。我們的 paper 核心主張(query-time > write-time on multi-hop)**被現有資料部分反駁**(Mem0 = 43 > 我們 = 31),要先建 baseline matrix(競品 × context 長度 × 任務)再決定優化方向 — 詳見 §11
- **欲求 chat 協助**:(a) path scoring 公式有無 cited 先例,(b) **§11 的策略性問題:基底選擇 / 5 個 paper angles / 應否暫停 HippoRAG 內部優化**

---

## §1. 任務 / 資料集

| | |
|---|---|
| Benchmark | FactConsolidation MH(MQuAKE-style counterfactual)|
| 規模 | FC-MH 6k = 100 queries, 12 chunks × 512 tokens, 450 props |
| Query 類型 | 多 hop QA,需要在 knowledge pool 內走推理鏈 |
| 衝突結構 | 每 query 有 0~4 個 has_pair hop(GT 有 chain_old 跟 chain_new 兩版本) |
| has_pair hop 總數 | 175 hops(2-hop: 多數;3-hop: 24 hops;4-hop: 15 hops) |
| Corpus 結構 | "Here is a list of facts:\n0. fact. 1. fact. 2. fact. ..."(編號 list) |
| **Recency cue**(FC 重要性)| **List 編號大 = 較新 = 該作為答案的版本**(LLM 用編號判 recency) |

**Ceiling references**(orig prompt,Gemini-3.1-flash-lite):
- Vanilla(no oracle): 20%
- OracleClean-Others(留 chain_old,清其他 olds): 25%
- OracleClean-ThisChain(移此題 chain_old,留其他): 55%
- OracleClean-All(全 165 olds 移除): **60%** ← filter perfect 的上限
- PureChain(只有 chain_new): **97%** ← LLM 多跳推理絕對上限

---

## §2. Pipeline 架構(Phase 1/2/3)

```
                  ┌─── Phase 1: Indexing (offline) ───┐
       chunks → NV-Embed-v2 → embeddings
       chunks → OpenIE (Gemini) → 450 propositions
                                  with (text, entities, source_chunk_id, 
                                        timestamp=(chunk_idx, in_chunk_pos),
                                        embedding)
       Build KG: entity nodes + passage nodes + synonymy + fact edges

                  ┌─── Phase 2: Per-query detection ───┐
       query → embedding
       PPR → top-200 propositions
       O4.5 identify_active_region: top-K=50 by prop_ppr_mass (mean entity_ppr)
       O4.6 enumerate_candidate_chains: beam search → top-M chains 
                                        (M=5, L=3, beam_width=8, n_seed=20)
       O4.7 chain_restricted_verdict: LLM identifies contradicting pairs
                                      + code mechanical timestamp direction
                                      → chain_old_pids set
       O5 passage filter: drop chunks with chain_old (rescue if chain_new co-located)

                  ┌─── Phase 3: Enriched context (W3, currently OFF) ───┐
       (Reasoning hints + Recent updates injection; tested,marginal)

                  ┌─── Final QA ───┐
       Top-K=5 passages → Wikipedia Title wrapper → LLM (Gemini) → answer
```

---

## §3. 完整 component 設定(每個 top-K / 參數)

| Component | Setting | 來源 |
|---|---|---|
| **LLM backbone** | `gemini-3.1-flash-lite-preview`(via Vertex AI) | agent yaml |
| Inference temperature | 0.7 | agent yaml |
| Embedding model | `nvidia/NV-Embed-v2` (fp16 opt-in via env, default fp32) | NVEmbedV2.py |
| Embedding batch size | 8(opt-in via `HIPPORAG_EMBED_BATCH_SIZE`)| 同 |
| **Chunk size** | **512** tokens(FC corpus → 12 chunks) | data yaml |
| **PPR retrieval_top_k** | **200**(內部 PPR working set,過濾出 top props for chain) | config_utils.py |
| **`retrieve_num`** | **10**(從 PPR 後丟給 agent 的 passages 數量)| agent yaml |
| **`qa_top_k`** | **5**(從 retrieve_num 切到實際給 LLM 看的 passages) | config_utils.py |
| Linking_top_k | 5 | 同 |
| `damping`(PPR) | 0.5 | 同 |
| **Active region `region_topK`** | **50** props(by prop_ppr_mass) | spec §B.3.1.1 |
| **Beam `M`**(max chains output) | **5** | 同 |
| **Beam `L`**(max chain depth = max # props) | **3** ⚠️ (4-hop GT chains 結構性無法 enumerate)| 同 |
| **`beam_width`** | **8**(每 depth 留 top-8) | 同 |
| **`n_seed`** | **20**(initial seed props by mass)| 同 |
| Verdict `K_pool` | 10 | spec §B.3.2 |
| Verdict LLM temperature | 0.0(deterministic) | 同 |
| Inference prompt template | `rag_qa_musique.py`(default HippoRAG-v2;**未改**) | 同 |
| Passage wrapper | `f"Wikipedia Title: {passage}\n\n"`(同 upstream)| HippoRAG.py:580 |
| 1-shot example | Neville Stanton / University of Southampton(MUSIQUE 預設) | rag_qa_musique.py |

**對齊 baseline**:我們 vanilla A = 17%,跟 fig3 vanilla(orig prompt)= 20% 同 prompt 條件,差距 3pp 算 LLM temp=0.7 跨 run 隨機性。

---

## §4. 今日改動(2026-05-26)時序記錄

### 4.1 移除 Phase 1 hyperedge(commit a76f4cd → ab3bd6b)

**動機**: W2 實測加 hyperedge 邊數 996→996(零增量),原因是 FC atomic prop = 2 entity → hyperedge entity-clique 退化成 fact edge → 100% 重複。

**改動**: hyperedge call 從 `enable_phase2_chain_detection` 解耦,改 default OFF。函數本體保留供未來 non-atomic-prop 資料集。

**驗證**: B 重跑 EM=30/100(prior 31, −1pp LLM 噪訊內 ✅)。

---

### 4.2 雙向 verdict aggregation(commit ab3bd6b)

**Bug 觀察**(verdict.py:311-333):

```python
focus_ts = focus.timestamp
later = [pid for pid in contradicting_pids if propositions[pid].ts > focus_ts]

if later:
    # focus 比某些 contradicting 還舊 → focus = superseded ✅
    return Verdict(status="superseded", superseder_id=...)
else:
    # contradicting 都 ≤ focus_ts → focus 標 'current' low conf
    # ❌ BUG:這些 earlier 的 contradicting 是 older twins,
    #    本來該標 chain_old,但完全沒記錄
    return Verdict(status="current", confidence="low")
```

**修正**:`Verdict.older_contradicting_pool_pids` 新欄位,收集 earlier pool pids。`_v2_phase2_pipeline` 雙向聚合 `chain_old_pids`(`enable_phase2_verdict_bidirectional` flag, default OFF for backwards-compat)。

**測試 C-v2 B 組**(bidir ON + rescue ON,其他同 B):
- **EM = 29/100**(prior B 單向 = 31,−2pp)
- D1 診斷:**chain_old_pids 在 B/C 平均一樣**(2.6 個/query,sum 255),代表 bidir 行為對稱有效
- **解讀**:rescue filter 是 ceiling,bidir 抓更多 chain_old 但 rescue 因 chain_new 共置就保留 → leak 更多 → EM 不升反微降
- **推測**:bidir 的效益要等 detection / filter 進一步改進才能兌現

---

### 4.3 B2 chunk_rebuild filter(已測,regression)

**設計**: chunks 含 chain_old 時,從**剩餘(非 old)props 的 text** 重組 chunk 內容。位置在 top-K 不變,只是內容換掉。

**測試 C-v2 C 組**(bidir ON + chunk_rebuild ON, rescue OFF):
- **EM = 15/100** ❌ **regression**(比 vanilla A=17 還低)

**D1+D2 診斷**:
- D1 確認 bidir aggregation 行為對稱(B/C 兩組 chain_old/query 平均都 2.6)
- D2 觀察 rebuilt chunk 內容:**list 編號全消失**,prop text 被 canonicalize(`"The chairperson of Fatah is Mahmoud Abbas"` → `"Mahmoud Abbas is the chairperson of Fatah"`)。

**根因**:**FC 用 list 編號當 recency cue**(編號大 = 較新)。chunk_rebuild 把編號丟掉 + 句型 canonicalize → LLM 同時失去跨 chunk 的 recency 對齊能力。即使 chain_old 被移除,**chain_new(在其他未 rebuild 的 chunks)的「我較新」標誌也失效**。

**Lesson**: format preservation 對 FC 至關重要 — 我們不能假設「chain_old 被移除 = 無衝突 = 不需編號」,因為 chain_new 還在別處需編號顯示自己較新。

---

### 4.4 Reject:B3 inline-remove filter

**設計**:用 regex 解析 chunk 文字 → 找到 chain_old 對應 fact 行 → 刪除 → 保留其餘 verbatim(編號 / 句型全留)。

**驗證**:99.8% prop ↔ fact-span entity-match alignment(實證可行)。

**Rejected**: 這個方法**post-hoc 看穿了 FC corpus 格式**(用「`N. fact-text.`」regex)。學術上不站得住:不能 generalize 到其他 corpus format(Wikipedia paragraphs / dialogue / 自由文本)。

→ Future-work:若要 generalize,可改用 LLM rewriting(approach 1 下面),但風險另議。

---

## §5. 兩個 approach pending(filter 設計暫停)

跑完 chunk_rebuild regression 後,user 提出兩個方向 — **都暫停**,改 pivot 到 detection 改進。

### Approach 1: LLM-based chunk rewriting

- 給 LLM 一個 prompt:`(chunk, old prop to remove) → output chunk with that fact omitted, everything else verbatim`
- Pros: 保 format + corpus-agnostic + 不靠 list 編號 regex
- Cons: 每 chunk 一次 LLM call(每 query ~3 chunks affected → 100 query × 3 = 300 LLM call);hallucination 風險

### Approach 2: Rescue + update list

- 維持現行 rescue filter(chunk 全 old 才 drop;有任何 chain_new 就 keep)
- 額外提供 "update list":verdict-confirmed candidate_new prop texts 當獨立 entries
- Pros: 不靠 format 解析;對 LLM 透明
- Cons: **跟 prior ablation C(W3 full = B + W3 enriched updates)做的事很像,prior C 跑出來也是 31**,沒突破 B 的 ceiling
- 雷:對 detection precision 要求極高,若 update list 含錯誤 superseded pair 會誤導 LLM

### Status

**兩個都暫停**。撞牆原因可能不只是 filter 設計,而是更上游的 detection recall。先攻 detection。

---

## §6. Prompt 不變式(學術原則)

我們允許改「retrieval method 回傳給 inference 用的記憶 context」,但有條件:

| 加進 context 的東西 | 對任意 long-term memory 任務都合理嗎? | 學術上 OK? |
|---|---|---|
| Zep 的時間戳 + invalid_at 標記 + 它在 prompt 內的說明 | ✅ 是 — 任何時序記憶系統都需要它 | ✅ |
| 我們的 update list(verdict-confirmed-new),格式為 `[Updated fact]:` | ✅ 是 — 任何需要區分 current vs outdated 的系統都用 | ✅ |
| HippoRAG 預設 `Wikipedia Title:` wrapper | ✅ 是 — vanilla HippoRAG 對任何資料集都這樣 wrap | ✅ |
| **V1 trailer**: `Intermediate answers: [a, b, c]` 強制 multi-hop 結構化輸出 | ❌ **不是** — 這是 FC-multi-hop 任務專用的 prompt hack | ❌ 不能用 |

**Test**:Would this work on any other long-term memory benchmark? Yes → reasonable. No → prompt-engineered hack for this benchmark.

---

## §7. Detection 改進方向(T1,正在做)

### 7.1 Recall 問題(已實證)

| Stage | chain_old recall | 損失 |
|---|---|---|
| Active region(top-50) | 94% | — |
| Candidate chain(beam output)| **67%** | **−27pp** ❌ |
| Pool(verdict 看到的)| 較高(dynamic_lookup 補)| — |
| Verdict 真標 superseded | ~ | — |
| Filter 真 drop chunk | 49% | 又 −18pp |

**bottleneck**: beam search 把 27pp 的 GT chain_old 從 candidate chain 漏掉。

### 7.2 Beam L=3 結構性問題

| Ablation | 2-hop | 3-hop | **4-hop** |
|---|---|---|---|
| Vanilla A | 21.3% | 8.3% | 13.3% |
| B(Phase 2)| 37.7% | 25.0% | **13.3%**(沒進步)|
| C(W3 full)| 37.7% | 25.0% | **13.3%**(沒進步)|

**4-hop EM = vanilla**,because beam L=3 → 4-prop GT chain 結構不可達。

### 7.3 現行 path scoring 公式(無文獻 cite,ad hoc)

```python
score = relevance + 0.3 × coherence + 0.2 × ppr_coverage − 0.1 × len(chain)

  relevance      = Σ cosine(prop.emb, query.emb)          # 逐 prop 加總
  coherence      = avg # shared entities between adj props # 結構訊號  
  ppr_coverage   = Σ prop_ppr_mass                          # 圖中心度
  length_penalty = −0.1 × len(chain)                        # 長度罰
```

**權重(0.3 / 0.2 / -0.1)從未 tune、從未 ablate、無 paper trace**。各 component 都是 hand-designed intuition,沒有理論依據。
→ Component-wise sensitivity analysis 缺。

### 7.4 T1 實驗(已跑,2026-05-27)

**三變體 ablation**:

| Variant | 公式 | EM |
|---|---|:-:|
| **adhoc**(reference) | `Σ cos + 0.3·coh + 0.2·ppr − 0.1·len` | 31 |
| **pure_relevance**(strawman) | `Σ cos` only | 30 |
| **proprag_strict**(principled) | `cosine(encode(" ".join(prop.text)), q)` | 29 |

EM 全在 LLM 噪訊內(29–31)→ 看不出差異。

**但 detection metric(either-side hop recall @ K=5)很有 differential signal**:

| Hop | n | adhoc | pure_relevance | proprag_strict |
|---|:-:|:-:|:-:|:-:|
| 2-hop | 87 | 83.9% | 83.9% | 80.5%(−3.4) |
| **3-hop** | 48 | 60.4% | 64.6%(+4.2)| **68.8%(+8.4)** |
| **4-hop** | 35 | 37.1% | 34.3%(−2.8)| **48.6%(+11.5)** ⭐ |
| Overall | 170 | 67.6% | 68.2% | **70.6%**(+3.0) |

**Finding 1**: pure_relevance ≈ adhoc(67.6% vs 68.2%)→ **我們手調的結構項(0.3·coh + 0.2·ppr − 0.1·len)幾乎零貢獻**。
**Finding 2**: proprag_strict 在 3-h(+8.4pp)、4-h(+11.5pp)有真實改進,但 EM 沒升 → 被下游 filter ceiling(~31)蓋住。

**Minor observation**(暫不深挖):proprag_strict 的 K=1 chain_new recall 只 2.4%(adhoc/pure ~43%);top-1 chain 偏好 chain_old prop。等 paper writing 時再回頭看。

### 7.5 但 scoring 改進只填了 3pp / 26.4pp 大坑

| Stage | chain_old recall(adhoc → proprag)|
|---|---|
| Active region(top-50)| 94% |
| Candidate chain @ K=5 | 67.6% → **70.6%** |
| 缺口 | 26.4pp → 23.4pp(只填 3pp) |

→ **path scoring 不是主要瓶頸**;**剩下 23pp 的 attrition 在 scoring 上游**:
- ① Active region selection(region_topK=50,by prop_ppr_mass)
- ② Seed selection(n_seed=20,取前 8 當 initial beam)
- ③ Expansion connectivity(entity overlap rule)
- ④ Beam width(8 太窄?)

**T1 結論**:Scoring 確定不是主因。下一步 diagnostic:逐 has_pair hop 分析 GT chain_old 失蹤的具體 stage(①/②/③/④)。

### 7.6 待跑的 follow-ups

- bidir=ON × {pure_relevance, proprag_strict}:測 detection 對稱性是否能 stack 上 scoring 改進
- Upstream component 改動(較大工程):e.g., 加 query-cosine 進 active region selection、加 synonymy / embedding edge 進 expansion connectivity、加大 beam_width / M / n_seed

### 7.7 bidir=ON 結果(2026-05-27 補跑)— **意外結論**

| Run | EM | 2-h@5 | 3-h@5 | 4-h@5 | Overall@5 |
|---|:-:|:-:|:-:|:-:|:-:|
| B-adhoc(bidir=0) | 31 | 83.9% | 60.4% | 37.1% | 67.6% |
| pure_rel(bidir=0) | 30 | 83.9% | 64.6% | 34.3% | 68.2% |
| proprag(bidir=0) | 29 | 80.5% | 68.8% | 48.6% | **70.6%** |
| **pure_rel(bidir=1)** | 29 | 83.9% | 64.6% | 34.3% | **68.2%(同 bidir=0)** |
| **proprag(bidir=1)** | 29 | 80.5% | 68.8% | 48.6% | **70.6%(同 bidir=0)** |

**關鍵**:bidir 對 Phase 2.a candidate chain recall **零影響**(數字一字不差)。

**原因**:bidir 只動 Phase 2.b verdict 的 `chain_old_pids` 聚合(加 `older_contradicting_pool_pids`),**它不影響哪些 chain 進 candidate**。Phase 2.a beam search 完全不知道 bidir 存在。

→ Bidir 的價值只在「給 filter 更多 chain_old_pids」一層,但被 rescue filter ceiling 蓋住,所以 EM 也沒漲。

### 7.8 Beam attrition 階段診斷(關鍵)

**26pp 大坑(active 94% → candidate chain 67%)的真實成分**:

| Stage | chain_old loss(adhoc) | 解讀 |
|---|:-:|---|
| ① LOST_ACTIVE(不在 top-50) | **5.9%(10 hops)** | 改 active region 才能救 |
| ② LOST_CONNECTIVITY(entity overlap 連不到 chain) | **6.5%(11 hops)** | 改 connectivity rule(synonymy / embedding edge)才能救 |
| ③ LOST_BEAM_OR_SCORE(連得到但 beam/score 剪掉)| **20.6%(35 hops)** ← **最大坑** | beam_width / M / scoring |
| ✅ IN_CHAIN | 67.1% | — |

**Cross-variant 站別損失(chain_old)**:

| Stage | adhoc | pure_rel | proprag_strict |
|---|:-:|:-:|:-:|
| LOST_ACTIVE | 10 (5.9%) | 10 (5.9%) | 10 (5.9%) **完全不變** ← scoring 上游無關 |
| LOST_CONNECTIVITY | 11 (6.5%) | 13 (7.6%) | **25 (14.7%) ↑** ← proprag 變更差 ⚠️ |
| LOST_BEAM_OR_SCORE | 35 (20.6%) | 32 (18.8%) | **19 (11.2%) ↓** ← proprag 減 9pp ⭐ |
| IN_CHAIN | 114 (67.1%) | 115 (67.6%) | 116 (68.2%) |

**解讀**:proprag 在 stage ③ 救回 9% 的 LOST_BEAM_OR_SCORE,但把另外 8% chain_old **推到 stage ② LOST_CONNECTIVITY**(chains 內容不一樣 → GT 跟新 chains 沒 entity overlap)→ 淨值只 +1pp。

**4-hop 是三段都漏的 case**:
- 4-h LOST_ACTIVE: 14.3%(5/35)
- 4-h LOST_CONNECTIVITY: 25.7%(9/35) ← rare entity 跟其他 prop 不 overlap
- 4-h LOST_BEAM_OR_SCORE: 22.9%(8/35)
- 4-h IN_CHAIN: 37.1%(13/35)

### 7.9 T1 三個收歸結論

1. **我們的 ad-hoc scoring 結構項是噪聲**(pure_relevance ≈ adhoc;detection 67.6 vs 68.2)
2. **proprag 在 stage ③ 救 9pp,但在 stage ② 多漏 8pp** → 淨改進 +1pp(detection 67.1 → 68.2)
3. **bidir 對 Phase 2.a 完全零影響**(設計上就只動 verdict 聚合;5-way 比對證實)

**真正的瓶頸**:
- ① Active region 漏 6%(scoring 沒救處)
- ② Connectivity rule 漏 6-15%(scoring 反而傷)
- ③ Beam/score 漏 11-21%(scoring 改進的天花板)
- 三段不一個個攻就走不出 67% 區間

### 7.10 待你跟 chat 討論的具體 follow-up

(已加進原 §8 的 questions 列表,但這裡單列):

| Q | 細節 |
|---|---|
| **Q-A**(Stage ②)| Entity-overlap 用「substring + 最少 3 字元」當 connectivity rule 是不是太弱?改成 synonymy edges(KG 已有)/ 加 embedding similarity edge 有沒有先例? |
| **Q-B**(Stage ③)| beam_width=8 / M=5 是否「結構性」太小?對 size 50 的 active region,理想 beam_width / M 有沒有 heuristic? |
| **Q-C**(Stage ①)| Active region 純用 PPR mass 選 top-50 是否太重 graph-centric?加 query-cosine 進聯集是不是先例? |
| **Q-D**(4-hop 整體)| L=3 死卡 4-prop chain → 直接調 L=4 vs LLM 預測 hop count → 哪個更穩? |

---

## §8. **欲求 chat 提供 input 的具體題目**

### 8.1 文獻 reference(我們的 ad hoc scoring 有沒有先例?)

請 chat 幫忙找/評論:

| 主題 | 我們的問題 |
|---|---|
| **Multi-hop path scoring 文獻** | `IRCoT`(Trivedi et al., 2022)、`DSP`(Khattab et al., 2022)、HotpotQA-era baselines、`MuSiQue` baselines。他們有 explicit path/chain scoring 公式嗎?有的話長什麼樣? |
| **KG path traversal scoring** | `PathRanker`、`MINERVA`、`M-Walk`(RL-based)。他們的 reward / scoring 公式有理論基礎嗎?|
| **Embedding-based path scoring** | `concat re-encode` vs `average` vs `max-pool` 之間,有理論偏好嗎?PropRAG 為何選 concat? |
| **Length normalization in beam search** | GNMT 的 `((5+len)^α / (5+1)^α)` 跟我們的 `−0.1·len` 哪個對 multi-hop 更合適?|
| **我們的 ad hoc 結構項**(coherence、ppr_coverage) | 有 cited 先例支持「path 內部 entity 共享數作為 score 訊號」嗎?有「PPR mass 應該加到 path score」的 paper 嗎? |

### 8.2 雙向 verdict 設計

- 我們新增的 bidir aggregation(focus 較新時,把 pool 內 older twins 也收進 chain_old_pids):**有沒有相關文獻**?conflict-aware retrieval / memory update 是否常見這樣的「雙向」設計?
- 還是這只是我們補 bug?(原 code 設計就忽略了 focus-current case 的 pool-older 資訊)

### 8.3 Detection → filter / context 的 alternative

- 我們在 §5 列了 approach 1(LLM rewriting)跟 approach 2(rescue + update list)。chat 看有沒有 missing 的設計?
- 例如:**re-embed chunk 移除某個 prop 後**(透過 prop 對 chunk embedding 的 contribution 反推)?
- 或:**動態 retrieval re-rank**,把含 chain_old 的 chunk 排序往下壓但不 drop?

### 8.4 Beam L=3 → 4-hop 結構性問題

- 我們考慮過(a)直接調 L 到 4 或 5;(b)LLM 預測 query hop count 動態設 L;(c)beam 自適應停止(沒有更高 score 時就停)
- chat 看有沒有更 principled 的 adaptive depth 方法?

### 8.5 整體研究方向 + paper framing

- 我們在 paper_narrative_experiments.md 的研究主張:**B 派(multi-hop retrieval)+ 衝突機制 > A 派(Mem0/Zep)**
- 當前 B=31% vs Mem0=43%(Gemini)vs Zep=8%(Gemini)→ 我們**不是第一**
- chat 看 paper 該怎麼 framing 才合理?強調 detection F1?或 multi-hop sub-accuracy?

---

## §9. 已測結果速查表

### 9.1 EM 主表(FC-MH 100Q, Gemini-3.1-flash-lite, orig prompt)

| Run | bidir | filter | chunk_rebuild | scoring | EM |
|---|:-:|:-:|:-:|---|:-:|
| Vanilla A | OFF | none | n/a | adhoc | **17** |
| Prior B(Phase 2 + rescue) | OFF | rescue | OFF | adhoc | **31** |
| Prior C(W3 full = B + updates) | OFF | rescue | OFF | adhoc | 31(no gain) |
| Prior D(W3 minimal = no filter + updates only) | OFF | none | n/a | adhoc | 15 |
| Re-verify B(hyperedge removed) | OFF | rescue | OFF | adhoc | 30 (≈ prior B) |
| C-v2 B 組(bidir + rescue) | **ON** | rescue | OFF | adhoc | **29**(−2 vs B) |
| C-v2 C 組(bidir + chunk_rebuild) | ON | **OFF** | **ON** | adhoc | **15** ❌ |
| **T1-pure-relevance**(bidir=OFF)| OFF | rescue | OFF | **pure_relevance** | **30** |
| **T1-proprag-strict**(bidir=OFF) | OFF | rescue | OFF | **proprag_strict** | **29** |
| **T1-pure-relevance**(bidir=ON)| ON | rescue | OFF | pure_relevance | 29 |
| **T1-proprag-strict**(bidir=ON) | ON | rescue | OFF | proprag_strict | 29 |
| (oracle ceilings, orig prompt) | | | | | OracleClean-All 60 / PureChain 97 |

→ **所有 T1 變體 EM 都在 29-31**,LLM 噪訊內,**filter ceiling 完全沒被打破**。

### 9.2 Cross-method 比較(FC-MH, Gemini-3.1-flash-lite)

⚠️ **數字 caveat — 看下表前先讀**:
- Detection 數字目前**兩套來源並存**,denominator 與 event 蒐集方式都不同 → **不可直接互比**。
  - **舊 audit(2026-05-02 跑的 invalidation_audit.json)**:denominator = `has_pair_in_dataset = 188`(labels.json 原始所有 has_pair hops,**含 13 個沒 prop-match 上的**);events 只蒐到 mem0=251 / zep=78,**並非系統實際完整輸出**。
  - **A1a/A1b v2(2026-05-17 跑的統一框架,見 `analysis/results/paper_narrative/A1a_A1b_detection_v2.md`)**:denominator = `175`(我們 internal pipeline 一致的 prop-matched has_pair);raw source 直接從 mem0 `history.db` 撈出 **1124 events**(完整),Zep 只剩 **33 / 78 raw events**(原 audit 只 dump 部分樣本到 JSON,full re-audit 要重打 API)。
- 結論:**Mem0/Zep 兩列的 detection F1 是不同框架的數字,且 Zep 的數字是 partial sample 的 publish-only F1,不是可重算的完整 audit**。我們自己的 Phase 2 是用 v2 框架算出來,denominator=175 → 跟舊 audit 的數字 framing 也不同。

| Method | EM | Detection(舊 audit,denom=188)| Detection(v2 框架,denom=175)| 備註 |
|---|:-:|---|---|---|
| HippoRAG-v2 vanilla(ours)| 17 | n/a | n/a | — |
| HippoRAG-v2 vanilla(2026-05-02 modified prompt) | 23 | n/a | n/a | — |
| HippoRAG-v2 + our Phase 2(B,bidir=0)| 31 | LLM identify 97%, mechanical 97% | **A1a F1=78.0** / A1b F1=82.2(253 events,完整)| ✅ raw 完整 |
| Mem0 customized(Gemini)| **43** | P=53.0, R=35.6, F1=42.6 | A1a F1=33.8 / A1b F1=73.0(1124 events,完整)| ⚠ 舊 audit 只 251 events(partial);v2 才完整 |
| Zep × Gemini | 8 | P=83.3, R=34.6, F1=48.9(published)| A1a F1=13.4 / A1b F1=29.0(只 33/78 events,partial)| ⚠ v2 raw events 不完整,F1=48.9 才是 published 真實值 |
| Zep × GPT-4o-mini(legacy)| 28 | 46.3 | n/a | 舊 audit |
| Mem0-graph(Mem0g) | **NOT RUN** | — | — | — |
| PropRAG | NOT RUN | — | — | — |
| OA2 fact-level oracle | 83(modified)/ 55(orig)| 100% | n/a | — |

→ **比較時的正確 framing**:
1. 只比 EM 是 safe 的(43 / 8 / 31 完整、可重算)。
2. 比 detection 要明確指定框架。最公平的是用 v2 框架(denom=175,raw source 統一)— 但 Zep 在 v2 下只有 33 events partial,**Zep 的 detection 嚴格 reportable 數字只剩 published F1=48.9**(舊 audit 算的)。
3. 用 v2 框架的話,我們 Phase 2 F1=78.0 顯著贏 Mem0 F1=33.8,但這需要在 paper 裡明白標 v2 denom 與框架對齊。Zep 受限於資料無法在 v2 框架做完整對比,只能引用 published 值並備註 caveat。

### 9.3 Detection recall by stage(內部診斷)

#### (a) Overall pipeline attrition(adhoc baseline)

| Stage | chain_old 比例 |
|---|---|
| has_pair hops total | **170** (labels.json, prop-matched)|
| chain_old in active region(top-50)| **94%** |
| chain_old in candidate chain(K=5, adhoc)| **67.1%**(beam 漏 26.4pp) |
| chain_old + chain_new both reachable for verdict | TBD(pool dynamic_lookup 補上的另一邊)|
| chain_old correctly flagged by verdict(LLM identify)| ~97%(W1.3 mini-eval) |
| chain_old chunk in top-20 retrieval(pre-filter)| ~? |
| chain_old chunk truly dropped by filter | 49%(rescue 卡掉 18pp)|

#### (b) Either-side hop recall @ K=5, by hop count(三 scoring variant × 雙向)

n_hops per category: 2-h=87, 3-h=48, 4-h=35

| Run | EM | 2-h@5 | 3-h@5 | 4-h@5 | Overall@5 |
|---|:-:|:-:|:-:|:-:|:-:|
| B-adhoc(bidir=0) | 31 | 83.9% | 60.4% | 37.1% | 67.6% |
| pure_relevance(bidir=0) | 30 | 83.9% | 64.6% | 34.3% | 68.2% |
| **proprag_strict**(bidir=0)| 29 | 80.5%(−3.4)| **68.8%(+8.4)** | **48.6%(+11.5)** ⭐ | **70.6%(+3.0)** |
| pure_relevance(bidir=1) | 29 | 83.9% | 64.6% | 34.3% | 68.2% **(同 bidir=0)** |
| proprag_strict(bidir=1) | 29 | 80.5% | 68.8% | 48.6% | 70.6% **(同 bidir=0)** |

→ **bidir 對 Phase 2.a candidate chain 完全零影響**(bidir 只動 Phase 2.b verdict 聚合,beam search 看不到 bidir)。
→ **proprag_strict 在 3-h(+8.4pp)、4-h(+11.5pp)有真實 detection 改進**,但 EM 全在 29-31 → 改進被下游 filter ceiling 蓋住。

#### (c) chain_OLD 在 beam search 失蹤的「攔截站」分布(stage 診斷)

26.4pp 大坑(94% active → 67.1% candidate chain)的攔截站來源:

| Stage | adhoc | pure_relevance | proprag_strict |
|---|:-:|:-:|:-:|
| ✅ IN_CHAIN | **114 (67.1%)** | 115 (67.6%) | 116 (68.2%) |
| ① LOST_ACTIVE(不在 top-50) | 10 (5.9%) | 10 (5.9%) | 10 (5.9%) **完全不變** |
| ② LOST_CONNECTIVITY(entity overlap 連不到 chain) | 11 (6.5%) | 13 (7.6%) | **25 (14.7%) ↑**(proprag 變更差)|
| ③ LOST_BEAM_OR_SCORE(連得到但 beam/score 剪掉)| **35 (20.6%)**(最大坑)| 32 (18.8%) | **19 (11.2%) ↓**(proprag 減 9pp ⭐)|

→ **proprag 在 stage ③ 救回 9pp(scoring 真正攻的點)**,但把另外 8pp 推到 stage ②(chains 內容不一樣 → GT 跟新 chains 沒 entity overlap)→ **淨改進只 +1pp(67.1 → 68.2)**。

→ **4-hop 是三段都漏的 case**:
- 4-h LOST_ACTIVE: 14.3%(5/35)
- 4-h LOST_CONNECTIVITY: 25.7%(9/35)— rare entity 跟其他 prop 不 overlap
- 4-h LOST_BEAM_OR_SCORE: 22.9%(8/35)
- 4-h IN_CHAIN: 37.1%(13/35)只是過半的一半

---

## §10. 相關文件

| 檔案 | 內容 |
|---|---|
| `docs/PROVENANCE.md` | 我們相對 upstream MemoryAgentBench 的所有改動 |
| `docs/method_design_v2.0.2_spec.md` | 方法 spec |
| `docs/method_v2.0.2_status_brief.md`(v9) | 方法現況綜整 |
| `docs/B_remove_hyperedge_design.md` | hyperedge 移除 design |
| `docs/C_v2_chunk_rebuild_design.md` | bidir + chunk_rebuild design(待加 paused note) |
| `docs/paper_narrative_experiments.md` | 論述實驗矩陣(A/B 派對照)|
| `docs/engineering_todos_v2.0.2.md` | 工程 todos |

### Source code 主要檔案

| 檔案 | 內容 |
|---|---|
| `methods/hipporag/HippoRAG.py` | 主類別,index() / retrieve() / qa() |
| `methods/hipporag/phase2a/path_enumeration.py` | beam search(這次 T1 改動處) |
| `methods/hipporag/phase2a/scoring_variants.py`(新)| 三變體 scorer |
| `methods/hipporag/phase2a/active_region.py` | top-K props by mass |
| `methods/hipporag/phase2b/verdict.py` | LLM verdict + bidirectional aggregation |
| `methods/hipporag/phase2b/data_structures.py` | Verdict dataclass + `older_contradicting_pool_pids` |
| `methods/hipporag/utils/config_utils.py` | 所有 flag + env binding |
| `methods/hipporag/phase2b/prompts/verdict_prompt.py` | LLM verdict prompt(separate semantic + mechanical direction)|

---

**討論時請對應到具體 §,我們可以針對任何 section 深挖**。最迫切的問題在 §11(策略反思)+ §8(文獻 / 設計參考)。

---

## §11. Strategic Reflection(2026-05-27)— **本文最重要的一節**

今日跑完 T1 三變體 + bidir × 二變 + diagnostic 後,user 自我反思 + 我幫忙批判性釐清,得出**策略-戰術錯位**的結論。

### §11.1 Paper 核心主張拆解 + 現有資料測試

User 的原始主張:
> **C1**:把衝突偵測**從 write-time 移到 query-time**(at retrieval),回傳的記憶**能幫助 LLM inference 多跳推理更好**;
> **C2**:**同時不傷害其他記憶任務**(FC 之外的 benchmark)

逐項對照現有資料:

| Claim | 證據 | 結果 |
|---|---|---|
| **C1.1** 我們是 query-time | ✅ Phase 2 在 retrieval 時跑 | 對 |
| **C1.2** Mem0 / Mem0g / Zep 是 write-time(LLM 看不到 outdated)| Zep 兩端;Mem0/Mem0g 是 write-time | 大致對 |
| **C1.3** Query-time → 多跳 EM 更好 | Mem0(write-time)= **43%**,我們(query-time)= **31%** | ❌ **資料反駁** |
| **C1.4** Query-time → detection F1 更準 | Mem0=42.6,Zep=48.9,我們=78 | ⚠️ 可能對,但 detection F1 ≠「對 LLM 多跳推理更好」 |
| **C2** 不傷其他任務(FC-SH / 非衝突 QA / 不同 context 長度)| **完全沒測** | ❌ **無資料** |

→ **C1.3 跟 C2 是 paper 主要 selling point,但現在資料根本不支持**。

### §11.2 策略-戰術錯位

| Strategy(claim level) | Tactic(this week) | 對齊嗎? |
|---|---|---|
| Query-time 對 write-time | 改 HippoRAG-v2 的 beam scoring | ❌ Path scoring 改進跟「query-time 為何優於 write-time」是兩件事 |
| 證明多跳更好 | 在 31% ceiling 內找 +1pp +3pp | ❌ Mem0 = 43%,我們再優化也可能還是輸 |
| 不傷其他任務 | 從未跑 FC-SH / 不同長度 / 非衝突 | ❌ 完全沒證據 |

→ **「我們可能在錯的山頭爬坡」**。

### §11.3 基底選擇(HippoRAG-v2 + PropRAG borrow)缺乏 principled justification

| 選擇 | 表面理由 | 實際的弱論證 |
|---|---|---|
| 基底用 HippoRAG-v2 | 有 KG、有 PPR、有 retrieval | Mem0g 也有 graph;Zep 也有 graph。**沒講為何選 HippoRAG** |
| 借 PropRAG path scoring | 多跳更好 | PropRAG 不是 conflict-aware → 跟我們 conflict 主張正交 |
| 加自己的 conflict detection | 是 contribution | OK,但**這個 contribution 為何要跑在 HippoRAG 而非 Mem0g 上?** |

→ Reviewer 必問:**「為何不直接在 Mem0g 上加 query-time 偵測,而要繞道 HippoRAG-v2?」** — **我們現在答不出來**。

### §11.4 可能的 paper angle(5 種,各自的 evidence 缺口)

| Angle | 核心 claim | 現有證據 | 缺什麼 |
|---|---|---|---|
| **A. 多跳 EM 贏** | query-time + multi-hop retrieval 在 FC-MH EM 上贏 write-time | ❌ Mem0=43 > 我們=31 | 要嘛 EM 衝到 ≥ 45,要嘛改 angle |
| **B. Detection 精度贏** | query-time detection F1 顯著高(78 vs 42) | ⚠️ 我們贏,但 detection F1 不是 reader 最在意的 metric | 要證明 detection F1 → downstream value |
| **C. 長 context 韌性** ⭐ | 對話歷史變長(32k/64k/262k),write-time 跟 long-ctx-LLM 都崩,query-time 不崩 | **完全沒測** | 跑長度 sweep |
| **D. 非衝突任務不退步** | FC 之外 benchmark 表現不差於 vanilla | **完全沒測** | 跑 non-FC 任務 |
| **E. Compute / latency** | query-time 省 indexing cost | 沒測 | profiling |

→ **angle C 是研究上最香的**(差異化乾淨,符合 long-term memory 真實場景)。但要靠資料。

### §11.5 Re-prioritization 提議(P0–P5)

| 優先 | 任務 | 為何 |
|---|---|---|
| **P0** | 跑 Mem0 vector / Mem0g / Zep / long-ctx-LLM 在 FC-MH 6k 相同 setup 對齊 | **建立可信對手 baseline**;沒這個無法談論「贏」 |
| **P1** | 上述 × context 長度(6k / 32k / 64k / 262k)| 測 angle C |
| **P2** | 跑 FC-SH(單跳)用相同 setup | 確認 single-hop 不退步 |
| **P3** | 跑非衝突 benchmark(MABench 內任一其他 task)| 測 angle D — paper 必要 |
| **P4** | 看完 P0–P3 結果,**重新決定基底 + 攻擊方向** | 可能換 base(改 Mem0g 上加 query-time),可能改攻 angle C |
| **P5**(目前在做)| HippoRAG-v2 內改 detection / scoring / filter | **暫停**,等 P0-P3 確認方向 |

### §11.6 開放問題 — 給 user(也歡迎 chat input)

| Q | 內容 |
|---|---|
| **Q1** | 跑完 P0-P3 若發現 Mem0g 在所有長度都勝過我們,**會放棄 HippoRAG-v2 base 嗎?**還是堅持「我們設計上 cleaner」? |
| **Q2** | 你期待 angle C(長 context 韌性)出來的結果是什麼?(若沒 prediction = 探索性)|
| **Q3** | Paper 願景:**「全新方法、打 SOTA」vs「query-time 是優於 write-time 的設計原則,提供概念貢獻」**?後者只要設計能證明 + 略勝即可 |
| **Q4** | **能接受「我們不是最強但展示未被探索的設計空間」嗎?** — 學術上合法但要不同 framing |

### §11.7 對 chat 的 specific 詢問

| Q | 內容 |
|---|---|
| **Q-S1** | 我們現有的 31% vs Mem0 43% 的劣勢,有沒有可能是 Mem0 拿 V1 modified prompt 跑出來的虛胖?**Mem0 在 raw prompt 下還是 43% 嗎?**(我們需要重跑驗證) |
| **Q-S2** | 從文獻看,write-time 偵測通常在 long-context(32k+)會 degrade 嗎?有 paper 證據嗎?(這支撐 angle C) |
| **Q-S3** | 把「query-time vs write-time」當設計原則寫 paper(angle C+D 並進)合理嗎?還是 reviewer 一定會要求 EM SOTA? |
| **Q-S4** | 我們的 contribution 應該 reframe 成「query-time 衝突偵測 + 多跳檢索 combined」?還是「在現有 multi-hop retrieval(HippoRAG-v2)上注入 query-time conflict awareness」?哪個 framing 對 reviewer 比較有說服力? |
| **Q-S5** | 若基底改成 Mem0g(在它上面加 query-time 偵測),工程上可行嗎?**chat 對 Mem0g 比較熟,請評估這條路** |

### §11.8 Honest take(2026-05-27)

- 今天的優化(scoring / filter / verdict bidir)在學術上算 **minor contributions**
- 它們對「query-time vs write-time」這個大 claim 都**不是直接證據**
- **真正能讓 paper 站起來的是 P0 + P1 + P3** — 沒有跨方法、跨長度、跨任務的對照,連自己贏在哪都說不清
- **戰術建議**:這週剩下時間**暫停 HippoRAG 內部優化**,啟動 Mem0g / Zep / long-ctx-LLM × 長度 sweep
- 跑完 baselines 後再回頭看:**HippoRAG-v2 內部優化還值不值得做**?或者應該**換 base**?或者**換 angle**?


