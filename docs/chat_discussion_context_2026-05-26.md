# Context for Chat Discussion — Multi-hop Conflict Detection on HippoRAG-v2

**Date**: 2026-05-26
**Purpose**: 把目前研究全局 + 今日改動 + 待解 design 問題 + 完整設定一次給 chat,讓 chat 能(a)對任意環節給改進想法,(b)幫忙找 path scoring / multi-hop reasoning 的相關文獻參考。

---

## §0. TL;DR

- **Research goal**: 給 HippoRAG-v2 加 conflict-aware extension,用 FactConsolidation (FC) MH-6k 100Q 當 benchmark
- **Current best**: FC-MH EM = 31%(vanilla A=17, +Phase 2 = 31)
- **Filter ceiling 撞牆 ~31**(嘗試多種 filter variants 都沒突破)
- **Pivot 到 detection 改進**(認為 candidate chain 對 chain_old/chain_new 的 recall 不夠)
- **欲求 chat 協助**:(a) path scoring 公式有無 cited 先例 / 更好方法,(b) detection / filter / context-return 的 alternative ideas,(c) bidir verdict 設計是否 principled

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

### 7.4 T1 實驗(等 GPU run)

**三變體 ablation**:

| Variant | 公式 | 設計理由 |
|---|---|---|
| **adhoc**(reference) | `Σ cos + 0.3·coh + 0.2·ppr − 0.1·len` | 現行,prior B=31 |
| **pure_relevance**(strawman) | `Σ cos` only | 結構項是無效 ad-hoc 還是真有用?|
| **proprag_strict**(principled) | `cosine(encode(" ".join(prop.text)), q)` | PropRAG (Liu et al. EMNLP 2025) 的 `concatenate` mode,whole-chain re-encode |

**所有其他設定不動**(M=5, L=3, beam=8, n_seed=20, bidir=OFF, rescue=ON, hyperedge=OFF)→ 單一變因。

**之後再跑**:bidir=ON × {pure_relevance, proprag_strict} → 2 個 follow-up runs。

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
| **T1-pure-relevance**(pending GPU) | OFF | rescue | OFF | **pure_relevance** | ? |
| **T1-proprag-strict**(pending GPU) | OFF | rescue | OFF | **proprag_strict** | ? |
| (oracle ceilings, orig prompt) | | | | | OracleClean-All 60 / PureChain 97 |

### 9.2 Cross-method 比較(FC-MH, Gemini-3.1-flash-lite)

| Method | EM | Detection F1 (audit, full data) |
|---|:-:|:-:|
| HippoRAG-v2 vanilla(ours)| 17 | n/a |
| HippoRAG-v2 vanilla(2026-05-02 modified prompt) | 23 | n/a |
| HippoRAG-v2 + our Phase 2 | 31 | LLM identify 97%, mechanical 97% |
| Mem0 customized(Gemini)| **43** | P=53.0, R=35.6, **F1=42.6** |
| Zep × Gemini | 8 | P=83.3, R=34.6, **F1=48.9** |
| Zep × GPT-4o-mini(legacy)| 28 | 46.3 |
| Mem0-graph(Mem0g) | **NOT RUN** | — |
| PropRAG | NOT RUN | — |
| OA2 fact-level oracle | 83(modified)/ 55(orig)| 100% |

### 9.3 Detection recall by stage(內部診斷)

| Stage | chain_old 比例 |
|---|---|
| has_pair hops total | 175 |
| chain_old in active region | 94% |
| chain_old in candidate chain | **67%**(beam 漏 27pp) |
| chain_old + chain_new both reachable for verdict | TBD |
| chain_old correctly flagged by verdict | ~97%(W1.3 mini-eval) |
| chain_old chunk in top-20 retrieval(pre-filter) | ~? |
| chain_old chunk truly dropped by filter | 49%(rescue 卡掉 18pp) |

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

**討論時請對應到具體 §,我們可以針對任何 section 深挖**。最迫切的問題在 §8。
