# Paper Narrative — 實驗矩陣與追蹤

**最後更新**: 2026-05-23
**用途**: 集中追蹤論述方向需要的所有實驗,過去做過的標出來、新的列待跑、結果更新時直接 inline 修
**狀態約定**:
- ✅ **Done** — 結果已有,並指到具體檔案
- 🟡 **Partial** — 部分資料已在 artifact 中
- ⬜ **Not started**

**LLM 對齊基準**: 本文所有比較以 **gemini-3.1-flash-lite-preview** 為主(我們的 ablation 與 2026-05-02 Mem0/Zep run 都用此模型)。Zep-internal LLM 不可換,需特別注記。

---

## 0. 兩個 baseline 派系 + 論述主張

| 派系 | 代表 | 主張(我們要打的點) |
|---|---|---|
| **A. Conflict-aware** | Zep / Mem0(custom) | Write-time/inference 標注,但 **detection F1 < 50%**;**Zep 在 3-hop+ 結構性 0%**;Mem0 過度觸發(FP 高);Zep 沒設 invalid_at;偵測本身不可靠 |
| **B. Multi-hop retrieval** | HippoRAG-v2 / PropRAG | 找得到 new(K=10 94%),但**舊版本一起被抓回(K=5 73%)**→ LLM 拿到髒 context;**沒有衝突機制** |

**我們的方法主張**: B 派 + 衝突機制,要證明:
1. **B + 衝突機制 > A 派**(整體 EM + 多跳穩定度)
2. 我們的衝突機制 > A 派(detection metric)
3. 我們的 multi-hop retrieval > A 派(retrieval recall)

---

## 1. A 系列 — 對 Conflict-aware(Zep, Mem0)的失敗點刻畫

| 編號 | 實驗 | 設定 | Metric | Claim | **狀態** | 資料來源 / 結果摘要 |
|---|---|---|---|---|---|---|
| **A1a** | Per-ingestion / event-level detection | 對每個 invalidation event 評估 | Precision / Recall / F1 | Write-time detection 內在品質有限 | ✅ | Mem0 FC-MH: P=53.0/R=35.6/**F1=42.6**;Zep×Gemini FC-MH: P=83.3/R=34.6/**F1=48.9**;Zep×GPT FC-MH: P=88.1/R=31.4/F1=46.3 — 三者 **F1 都 < 50**。`analysis/experiments/2026-05-02_mem0_zep_gemini_full100/README.md §4` |
| **A1b** | Query-driven / per-hop detection | 對 query 推理鏈每 hop 評估 | Per-Hop / All-Hops Resolution + det × answer 交叉表 | Write-time detection **對 query 關鍵衝突服務不佳** | ✅ | Mem0 MH: all-detected 77% → no-det 22%(差 55pp,detection-bottleneck);**Zep MH: all-detected 0%(8/8 全錯)< no-det 9.5%(propagation-bottleneck)**。同檔 §4.5 |
| **A1.5** | Failure case study | A1b 失敗 case 分類 | 模式比例 | 失敗有系統性 root cause | ✅(分類已有,F1–F6 映射待補) | 既有分類:Mem0 buckets(A_direct_old_leak 16 / B_satellite_leak 26 / C_parametric 5 / D_gave_up 6 / E_hallucinated 4);Zep buckets(A1_with_invalid_at 35 / A2_no_invalid_at 55 / E_hallucinated 1 / B 1)。`results/failure_mode_classification.json` + `case_studies.md`(696 行)+ `inference_prompts_comparison.md` |
| **A2a** | Single-hop retrieval — new-version recall | Mem0/Zep retrieval | New-version Recall@K | retrieval 未必抓到對的 | 🟡 | Mem0 已有 `mem0_aligned_chain_presence_audit.json`;Zep retrieval recall 已部分由 `zep_*invalidation_audit*.json` 派生(Zep recall ≈ 30%),需正式重彙整 |
| **A2b** | Multi-hop path recall | 同 A2a, 改 path 完整性 | Path Recall | Single-hop 找不齊所有 hop | 🟡 | 同上資料源派生 |
| **A3** | Multi-hop 改造可行性 | code-level 定性 | 結論 | Zep/Mem0 加 multi-hop 也救不回 | ✅(主要結論已寫) | `inference_prompts_comparison.md`(Mem0=write-time, Zep=inference-annotation)+ `zep_mechanism_deep_dive.md`;**Zep × Gemini 3-hop=0% / 4-hop=0%** 是結構性 evidence |
| **A4** | E2E QA on FC-MH | 完整 pipeline,**各方法用各自 vanilla(orig)prompt — 不變式:設計只動 retrieval 回傳的記憶 context,不動 inference system prompt** | EM | 整體 baseline | ✅(對齊版) | Mem0 customized × Gemini MH = **43.0%**;Zep × Gemini MH = **8.0%**(3-hop 0% / 4-hop 0%);Zep × GPT MH = 28%(舊);HippoRAG-v2 vanilla(我們 A)= **17%**;HippoRAG-v2 plain Gemini **modified prompt** = 23%(已踩到不變式邊界,僅當參考)。**Ceiling(orig prompt,fig3 對齊)**:OracleClean-All = **60%**;PureChain(Sim-OB)= **97%**。V1 structured prompt 數字(83% / 98%)屬於 inference-side 修改,僅作 secondary observation,不入主表。`results/summary.md` + `paper_motivation/figures/slides/fig3_channel_ceiling_ladder.png` |

### 1.1 A1.5 失敗模式預設 → 既有分類映射

User 框架的 F1–F6,對應到實證已分類的 buckets(Mem0/Zep 各自分類):

| User F-模式 | Mem0 buckets | Zep buckets |
|---|---|---|
| **F1 LLM Prior Bias**(parametric 強知識覆蓋) | C_parametric_or_other (5/100) | (見 Zep×GPT SH wrong-direction 25/48,52%;Gemini 改善但 7/64 仍存) |
| **F2 Query-Agnostic Conservative**(沒 query 不肯動) | A_direct_old_leak (16) | A2_no_invalid_at (55/100 = **過半 Zep 失敗模式**) |
| **F3 Embedding Miss**(根本沒撈到) | (silent miss 在 case_studies 有但無 bucket) | (有 audit completeness ~70-90% caveat,可能 underestimate) |
| **F4 Implicit Conflict** | (未顯式分類) | (未顯式分類) |
| **F5 Cascading Error** | D_gave_up (6) | (propagation crash) |
| **F6 Granularity Mismatch** | B_satellite_leak (26 — peripheral fact leak) | B (1) |
| (新:detection 正確但 inference 仍錯) | — | A1_with_invalid_at (35) |
| (新:hallucination) | E_hallucinated (4) | E (1) |

→ 已分類比例:Mem0 失敗 57 例分到 5 桶;Zep 失敗 92 例分到 4 桶。**F1–F6 與既有分類的映射要寫進 paper § / appendix**。

---

## 2. B 系列 — 對 Multi-hop retrieval(HippoRAG-v2, PropRAG)的驗證

| 編號 | 實驗 | 設定 | Metric | Claim | **狀態** | 資料來源 / 結果摘要 |
|---|---|---|---|---|---|---|
| **B1a** | Raw retrieval: New-version Recall@K | vanilla,FC-MH | Recall@K | 多跳系統能找到新版本 | ✅ | **K=5: 74.7% / K=10: 94.1%**(per-hop);`analysis/results/paper_narrative/B1_retrieval_recall.md` |
| **B1b** ⭐ | Raw retrieval: **Old-version Retrieval Rate@K** | 同上 | Rate@K | **舊版本也被抓回** | ✅ | **K=5: 73.4% / K=10: 94.4%**(per-hop, has_pair);**B1a≈B1b → 新舊幾乎一比一被一起撈出來 = 髒 context gap** |
| **B1c** | Multi-hop Path Recall | 推理鏈所有 hop new 都 hit | Path Recall | 多跳 retrieval 完整性 | ✅ | **K=5: 55% / K=10: 89%** per-query;按 hop:K=5 2-hop 65.6% / 3-hop 41.7% / 4-hop 26.7% — 4-hop 嚴重崩 |
| **B1d** | B vs A retrieval 直接對比 | 同 benchmark | Recall@K, Path Recall | B1 > A2 | 🟡 | B1 數字已有;需 A2 對齊後直接製表 |
| **B2** | 我們衝突機制後的 detection accuracy | Query-time | LLM identify / mechanical direction | B2 > A1 | ✅ | LLM identify=**97%**, mechanical direction=**97%**(175 hop,5 反例)。比 Mem0 F1 42.6% / Zep F1 48.9% 高 50pp+(注意:這是不同 metric 框架,比較時要對齊定義) |
| **B3a** | E2E QA on FC-MH | 我們 4-ablation | EM | B3a > A4 | ✅ | A=17 / **B=31** / C=31 / D=15(Gemini-3.1-flash-lite)。**B 高於 Zep×Gemini 8% +23pp、低於 Mem0 customized 43% −12pp** ⚠️ |
| **B3b** | EM 按 hop 拆 | 4-ablation × hop | EM by hop | 多跳場景優勢 | ✅ | A: 2h 21.3 / 3h 8.3 / 4h 13.3;**B: 2h 37.7 / 3h 25.0 / 4h 13.3**(4-hop 完全沒改善);D 全面崩。`B3b_em_by_hop.md` |

### 2.1 B1b 為何是核心(callout)

> HippoRAG-v2 / PropRAG **沒有衝突機制** → B1b 預期高 ✅ 已驗證
> **B1a ≈ B1b(K=5 都 73-75%)**= 「找得到 new,也撈到 old → LLM 拿到髒 context」這個 gap 被精確量化
> 我們的衝突機制目標 = **B1b 壓下來、B1a 保持高**

### 2.2 B3a vs A4 跨系統比較(已有完整 evidence)

| 系統 | LLM | FC-MH Overall | 2-hop | 3-hop | 4-hop | Detection F1 |
|---|---|---|---|---|---|---|
| HippoRAG-v2 vanilla(我們 A) | Gemini-flash-lite | **17%** | 21.3% | 8.3% | 13.3% | — |
| HippoRAG-v2 plain(modified prompt) | Gemini-flash-lite | 23% | — | — | — | — |
| **+ 我們 Phase 2(B/C)** | Gemini-flash-lite | **31%** | 37.7% | 25.0% | 13.3% | LLM 97% / Mech 97% |
| Mem0 customized | Gemini-flash-lite | **43%** | 44.3% | 50.0% | 26.7% | F1 42.6% |
| Zep × Gemini | Gemini(inference) | **8%** | 13.1% | **0.0%** | **0.0%** | F1 48.9% |
| Zep × GPT(legacy) | GPT-4o-mini | 28% | — | — | — | F1 46.3% |
| OracleClean-Others(留 chain_old,清其他 olds)| Gemini, **orig** prompt | 25% | — | — | — | — |
| **OracleClean-ThisChain(= OA2,移本題 chain_old)** | Gemini, **orig** prompt | **55%** | — | — | — | 100% |
| **OracleClean-All(全 165 olds 移)** | Gemini, **orig** prompt | **60–61%** | — | — | — | — |
| **PureChain(= Sim-OB,只 chain_new)** | Gemini, **orig** prompt | **97%** | — | — | — | — |
| (secondary)OA2 + V1 structured prompt | Gemini, modified | 83% | — | — | — | — |
| (secondary)Sim-OB + V1 structured prompt | Gemini, modified | 98% | — | — | — | — |

**⚠️ 重要觀察**:
1. 在同樣 Gemini 條件下,**Mem0 customized(43%) > 我們 B(31%) > HippoRAG plain(23%) > 我們 A(17%) > Zep(8%)**。我們目前不是第一,paper framing 要誠實處理。
2. **17 vs 23 的 6pt gap 來自 prompt 修改**:`modified prompt` 是 2026-05-02 在 HippoRAG default prompt 上做的修改(可能去掉 Wikipedia wrapper / one-shot example),這部分對應**工程 E1 的不變式驗證**——我們 A 用的是 raw HippoRAG default prompt。
3. **4-hop 我們 B 完全沒改善(13.3 → 13.3)**;Mem0 還有 26.7%,Zep 是 0%。深跳是大家共同弱項,我們也沒贏。
4. **Ceiling 解讀(orig prompt 主線)**:OracleClean-All = **60%**(完美過濾後仍只 60% → 60% 以上的 36pp 是 LLM 多跳推理能力極限);PureChain = **97%**(零 distractor 的絕對 ceiling)。我們 B=31% vs OracleClean-All 60% = **−29pp**(detection/filter 還有大量改進空間);60 vs 97 = 37pp(reading / multi-hop reasoning 的剩餘空間,屬於 inference 層)。
   - secondary observation:同樣的 oracle setup 套上 V1 structured prompt 後,OA2 從 55→83(+28pp),PureChain 從 97→98(+1pp 飽和)→ prompt 強化只有在「context 已乾淨」時才生效,這對 method 設計是個獨立的可疊加維度,但不進入主 ceiling 表。

---

## 3. 已有結果速查(集中)

### 3.1 我們的核心數字
| 來源 | 數字 | 對應 cell |
|---|---|---|
| 4-ablation EM | A=17 / B=31 / C=31 / D=15 | B3a |
| W1.3 verdict 內在準確率 | LLM identify=97% / mechanical direction=97% | B2 |
| chain_OLD recall by stage | S1 active 94% → S2 chain 67%;4-hop 37% | (內部診斷) |
| timestamp direction 上限 | 170/175 = **97%**(5 反例待 E3) | B2 機制上限 |
| has_pair hops | 175(2-hop=126, 3-hop≤55, 4-hop=24) | A/B denominators |

### 3.2 vanilla HippoRAG-v2 retrieval(B1)
| Metric | K=5 LLM-visible | K=10 full |
|---|---|---|
| **B1a new-recall** | **74.7%** | 94.1% |
| **B1b old-rate** | **73.4%** | 94.4% |
| **B1c path-recall** | **55%** | 89% |

### 3.3 A 派 detection F1(per-hop level, FC-MH, n=188 has_pair denominator)
| System | LLM | Precision | Recall | **F1** |
|---|---|---|---|---|
| Mem0 customized | Gemini | 53.0% | 35.6% | **42.6%** |
| Zep | Gemini-inference | 83.3% | 34.6% | **48.9%** |
| Zep | GPT-4o-mini | 88.1% | 31.4% | 46.3% |
| **OracleClean-ThisChain(OA2,事實層 oracle)** | — | 100% | 100% | **100%** |

### 3.4 detection 對 answer 的因果(A1b cross-tab)
| System | All-detected EM | No-detection EM | Δ |
|---|---|---|---|
| Mem0 MH | 76.9% | 22.0% | **+55pp**(detection 是瓶頸) |
| Zep MH | **0%** (0/8) | 9.5% | **−9.5pp**(propagation 是瓶頸,反例!) |

---

## 4. 既有 artifact 索引

### 我們的 ablation / cascade
| 檔案 | 內容 |
|---|---|
| `analysis/results/full100_eval/labels.json` | 100Q × hop-level GT chain_old/new + source_chunk |
| `analysis/results/full100_eval/ablation_cross_compare.json` | A/B/C/D 比對 |
| `analysis/results/priority5/A5b_*.md/png` | filter-driven cascade |
| `analysis/results/priority5/A6_*.md/png` | chain_old chunk 分類 |
| `monitoring_logs/2026-05-17_*_ablation_{A,B,C,D}/` | per-query EM + retrieval + phase2 dump |
| **`analysis/results/paper_narrative/B1_retrieval_recall.md`** | **B1a/B1b/B1c 完整**(本次新產出) |
| **`analysis/results/paper_narrative/B3b_em_by_hop.md`** | **B3b 完整 + 跨系統比較**(本次新產出) |
| `analysis/verify_timestamp_semantics.py` | timestamp 驗證 |

### Mem0 / Zep 既有分析(2026-04 ~ 05)
| 檔案 | 內容 |
|---|---|
| `analysis/results/oracle_a/conflict_resolution_mechanisms.md` | 概覽 |
| `analysis/results/oracle_a/mem0_deep_analysis.md` | Mem0 深度分析 |
| `analysis/results/oracle_a/mem0_zep_findings.md` | pilot run 失敗根因(Mem0 原版 prompt 拒絕通用知識) |
| `analysis/results/oracle_a/zep_mh_full100_findings.md` | Zep MH × GPT 完整 100Q 分析(28%、67 invalidations、95.2% 對) |
| `analysis/results/oracle_a/zep_mechanism_deep_dive.md` | Zep 機制深度 |
| `analysis/results/oracle_a/zep_mh_invalidation_audit_v2.json` | MH invalidation 原始 audit |
| **`analysis/experiments/2026-05-02_mem0_zep_gemini_full100/README.md`** | **全部 A 系列核心:Mem0/Zep × Gemini E2E + detection F1 + det×ans cross-tab + failure modes + case studies** |
| `…/results/case_studies.md`(696 行) | 12 個具體 case 拆解 5 種 pattern |
| `…/results/inference_prompts_comparison.md` | A3 定性分析來源 |
| `…/results/failure_mode_classification.json` | Mem0/Zep failure buckets |
| `…/results/mem0_*_results.json` `zep_*_results.json` | per-question raw 結果(A2 派生來源) |
| `…/results/*_invalidation_audit.json` | event-level invalidation 原始 |

### docs
| 檔案 | 內容 |
|---|---|
| `docs/method_v2.0.2_status_brief.md`(v9) | 方法現況綜整 |
| `docs/method_design_v2.0.2_spec.md` | 方法 spec |
| `docs/engineering_todos_v2.0.2.md` | 工程 todos(暫停) |

---

## 5. 對 paper 仍有缺口的部分

| 缺口 | 原因 | 補法 | 需要 GPU? |
|---|---|---|---|
| **A1.5 F1–F6 標準化映射** | 既有 buckets 跟 user 的 F1–F6 不一致 | 純表格 + 文字對齊;可加微抽樣 case 強化 | 否 |
| **A2a/A2b 正式重彙整** | 數字散在 invalidation audits 跟 chain_presence_audit | 寫一個 retrieval-recall 彙整腳本 | 否 |
| **B1d B-vs-A 直接 head-to-head** | 依賴 A2 正式表 | A2 出完後製表 | 否 |
| **B2 detection metric 對齊 A1a 定義** | 我們的 97% identify 跟 Mem0/Zep F1 不同框架 | 用相同(P/R/F1, has_pair denominator)定義重算我們的 verdict 統計 | 否(verdict_events.jsonl 已有) |
| **「我們的 Phase 2 對應 OA2/Sim-OB 之間哪個 paradigm」** | 對齊 paper 模式 B (detection+propagation) 雙瓶頸論述 | 寫一段定位 § | 否 |
| **vanilla HippoRAG 17 vs 23 的 6pt gap** | prompt template 差異 | **工程 E1 對齊**(需重跑) | **是(GPU)** |
| **我們方法 vs OA2 oracle 的 detection % gap** | 同 detection metric 框架後直接比 | 由 B2 對齊後直接看 | 否 |
| **Mem0-graph(Mem0g)baseline** | Mem0g 沒跑(README §8 列為 todo) | Neo4j + langchain-neo4j + 設定 + 重跑 | **是(GPU + Neo4j)** |
| **PropRAG E2E 數字** | PropRAG 我們完全沒跑 | 跑 PropRAG on FC-MH | **是(GPU)** |
| **我們方法在 Mem0-style detection metric 上的 F1** | 對齊 §3.3 表格 | 從 verdict_events 用相同公式重算 | 否 |

---

## 6. 需要 GPU(整套 pipeline)才能補的清單

| 項目 | 為何需要 | 預估 |
|---|---|---|
| **工程 E1 — vanilla HippoRAG prompt 對齊重跑** | 修改 prompt(去掉 wrapper / one-shot)後重跑 100Q,確認 22-23% 可重現,17 vs 22 的 5pt gap 解開 | 1 hr |
| **工程 E4 — 補 instrumentation 後重跑 B/C/D** | 補 Gap A/B 欄位後需要重跑 3 個 ablation 才有資料 | 3 hr |
| **工程 E5 — OracleClean upper bound** | 加 oracle filter 路徑,重跑一次 | 1 hr |
| **PropRAG E2E on FC-MH** | PropRAG 從未跑過,B 派完整論述需要 | 2 hr |
| **Mem0-graph(Neo4j-backed)on FC-MH** | A 派 graph 版本對照(Mem0 vector vs Mem0g) | 設置 + 跑 ~4 hr |
| **我們的新方法 ablation**(改 path-finding / partner-seeding) | 任何方法改進都需要 | per-ablation 1-3 hr |

→ **目前無 GPU 可做的事已基本做完**。剩餘論述彙整都是純文書/表格(§5 列的「否」項)。

---

## 7. 建議下一步(無 GPU)

1. **A1.5 F1–F6 映射表寫成 paper-ready 文字** — 從既有 buckets 直接對到 F1–F6,寫進論述 § ;可順帶 sample 幾個 case
2. **A2a/A2b 正式重彙整** — 一個彙整腳本把 retrieval recall 數字從 audit json 撈出
3. **B2 用 Mem0/Zep 同框架定義重算** — 從 `verdict_events.jsonl` 用 P/R/F1, has_pair denominator 重算,得到我們在「同一定義下」的 detection F1
4. **B1d head-to-head 表** — A2 出完後直接製
5. **「我們方法在 paper 模式判定」一頁定位 §** — 結合 OA2/Sim-OB ceiling 講清楚我們補 detection 還是 propagation

要從上面 1–5 哪個開始,user 拍板。

---

## 8. 已知 caveats / paper 必須記得

- **A4 alignment 5pt gap 已釐清來源**:vanilla HippoRAG 我們 A=17,2026-05-02 modified-prompt 23,**差距來自 prompt 修改**,需工程 E1 處理
- **mechanical direction 是 97% 不是 100%**:16-題 mini-eval 的 100% 是小樣本運氣;175 hop 全集 5 反例待 E3 確認
- **Zep×Gemini 8% vs Zep×GPT 28% 是 cross-LLM,不能直接比**;但「Zep 3-hop+ 全 0%」across LLM 都穩定 → 結構性失敗
- **Zep audit 完整度 ~70-90%**:可能 underestimate Zep detection recall
- **Mem0-graph(Mem0g)沒跑**:目前 A 派只 cover Mem0 vector 版
- **FC「時間」是人造 list 順序**,不是真實串流時間 — paper framing 不能宣稱真實時間性
- **detection F1 定義在 Mem0/Zep 用 event-level precision × pair-level recall**;我們的 97% 是 LLM identify 命中率(不同框架)— 比較前必須對齊定義

---

## 9. 相關文件

- 工程 todos: [`engineering_todos_v2.0.2.md`](engineering_todos_v2.0.2.md)
- 方法現況: [`method_v2.0.2_status_brief.md`](method_v2.0.2_status_brief.md)
- 方法 spec: [`method_design_v2.0.2_spec.md`](method_design_v2.0.2_spec.md)
- 完整 A 系列原始實驗: [`../analysis/experiments/2026-05-02_mem0_zep_gemini_full100/README.md`](../analysis/experiments/2026-05-02_mem0_zep_gemini_full100/README.md)
