# Engineering TODOs — v2.0.2 Post-W1.3 / Pre-Method-Improvement

**最後更新**: 2026-05-23
**狀態**: 暫停執行,user 切去做論文論述方向的實驗分析
**回來時讀**: 本檔 → `method_v2.0.2_status_brief.md` 對齊現況 → 直接動工 E1+E2+E3 並行批次

---

## 0. Context — 我們暫停在哪個點

- W1.3(Phase 2.b verdict)已收斂,4-ablation 結果在手:A=17 / B=31 / C=31 / D=15(FC-MH 100Q)
- 方法討論已收斂出方向(beam search 近窮舉 / partner-expanded seeding / fact-slot 去重),但**那些是 method 改進,不是當下工程**
- **本檔聚焦工程層的 6 個未解項目**,動工前需 user 拍板
- 約束:**user 要明確說「好」才能跑執行**;reads-only 分析腳本可以做

---

## 1. Engineering TODOs(優先序)

### E1 — vanilla baseline 對齊驗證 ⛔ 阻擋性最高

**內容**
- 確認所有 ablation(A/B/C/D + motivation 報的 vanilla)用同一 `qa_top_k`
- 確認 inference 端的 prompt template + agent_name normalize 完全一致
- 確認我們的設計**只動 retrieval 回傳給 inference 的 context 內容**,沒碰 LLM prompt wrapper

**為何首要**:現況 vanilla A=17,motivation 報的 vanilla 是 22,**5 點 gap 未解**。若這 gap 是 prompt / 組態差異造成,所有 ablation 數字都要重新解讀,後續任何 method 改進的結果都站不住。

**驗證方式**
- 讀 `eval_*` 路徑的 prompt 構造程式
- 對比 motivation 跑 baseline 時的設定 commit / config
- 跑 1–2 次 sanity check 對照

**成本**: 小

**user 強調的不變式**(原話):
> 我們所做的設計應該只有改動到 HippoRAG-v2 記憶方法最終回傳給 inference 的 context 記憶內容,而非 inference 的 LLM prompt template / wrapper

---

### E2 — 移除 Phase 1 hyperedge 🧹 cleanup,資料已定案 — **CODE 已完成 2026-05-24,等 GPU re-run 驗證**

**內容**: ~~把 `_add_proposition_hyperedges_to_stats()` 從 `index pipeline 移除~~ 改採「保留函數本體 + 加新 flag `enable_proposition_hyperedge` (default False) 解耦 call」的設計。詳見 [`B_remove_hyperedge_design.md`](B_remove_hyperedge_design.md)。

**為何可立刻做**:
- W2 Step 1 實測:entity-entity 邊數 **996 → 996**(零增量)
- 根因:FC 的 atomic proposition 剛好 2 個 entity → hyperedge 的 entity-clique 退化成 fact edge → **100% 重複 dict key**
- 不是 bug,是 atomic-prop regime 下的結構必然

**好處**:method narrative 變乾淨(不必再向 chat / reviewer 解釋一個沒效果的層)

**改動範圍(2026-05-24 完成 code)**:
- `methods/hipporag/HippoRAG.py:336-348` — call site 改用新 flag,加 DEPRECATED 註解
- `methods/hipporag/HippoRAG.py:1291` — 函數 docstring 加 DEPRECATED 標記
- `methods/hipporag/utils/config_utils.py` — 加 `enable_proposition_hyperedge` flag (default False)
- ✅ smoke test 通過(BaseConfig 可實例化,兩個 flag 預設 False)

**驗證(pending)**: GPU re-run ablation B 100Q,通過條件 EM ∈ [30%, 32%]。

---

### E3 — 5 個 timestamp 反例人工確認 🔍 20 分鐘事

**內容**: 從 `analysis/verify_timestamp_semantics.py` 加一段把「old > new(list order)」的 5 個 has_pair hop 連 prop text、source chunk 一起印出 → 人工看是 label 雜訊還是 benchmark 真的把 edit 放在前面。

**為何重要**: 決定「verdict 用 timestamp 判方向」的天花板是 **97% 還是可修到 100%**。

**背景**: 175 個 has_pair hop 裡,full timestamp 上 old<new = 170(97%);chunk_idx-only 上有 20 對同 chunk 無法區分。

**成本**: 極小

---

### E4 — 補上缺的 instrumentation(Gap A + Gap B)📊

**Gap A — verdict noise false-positive rate**
- 衡量:noise prop(other-old / other-new,非 GT chain_old)被 LLM verdict 判為 superseded 的比例
- 為什麼要量:case no81 是實證,但只有單案;要量化才知道是 1% 還是 30%

**Gap B — dropped-chunk collateral damage**
- 衡量:filter drop 掉的 chunk 裡,query-relevant 但**不是** chain_old 的 prop 有多少
- 為什麼要量:現在我們知道 D=15 比 A=17 差,但說不準是 chain detection 錯還是 filter 連帶誤殺其他答題相關 prop

**實作**: 在 `phase2_w13_dump.jsonl` 補欄位(`noise_pids_flagged_superseded`, `dropped_chunk_query_relevant_pid_count`),寫 `analyze_gap_AB.py`。

**為何重要**: 沒這兩個指標,filter 失敗的 root cause 說不準是哪個機制。

**成本**: 中

---

### E5 — OracleClean upper bound(Gap C)📈

**內容**: 寫一條 oracle 路徑——直接從 `labels.json` 拿 GT chain_old prop 的 source_chunk_id,**精準**砍掉那些 chunk(沒有 false positive),其他完全照 vanilla → 跑 EM。

**為何重要**: 告訴我們 31% → motivation 期望的 50%+ 的 gap,是 **filter 設計問題**(我們現在的 filter 不夠 oracle)還是 **chain detection 不到位**(連 oracle 都救不回的多 hop)。

**實作**: `methods/hipporag/HippoRAG.py` 加一個 `enable_oracle_filter` flag,從 labels 讀 GT 直接 drop,跑一次 100Q。

**為何在 E4 後**: oracle 跑出來的 attrition 模式要對著 E4 的 Gap A/B 看才有意義。

**成本**: 中

---

### E6 — Mem0/Zep 衝突偵測 recall/precision 對照 🆚

**內容**: 從 Mem0(write-time filter)和 Zep(inference annotation)的 run dump 裡,抽出他們**對 chain_old prop 的偵測決策**(命中 / 漏失 / 誤判),算 detection recall / precision。

**為何重要**: paper 主張裡有「我們偵測得更準」這條;現在只有 EM 對照(我們 31 / Mem0 44 / Zep 28),**EM 不等於偵測準確度**——可能我們偵測準但下游 filter 太凶。要拿 detection metric 才站得住「精準偵測 + 精準介入」這個 paper framing。

**前置**: 需理解 Mem0/Zep 的 dump 格式(在 `agents/Structure_rag_zep_*` 之類路徑)。

**成本**: 中–大

**獨立性**: 不阻擋任何其他項,可外部並行。

---

## 2. 執行批次建議

| 批次 | 項目 | 並行 / 串行 |
|---|---|---|
| **批次 1** | E1 + E2 + E3 | 並行(三者完全獨立) |
| **批次 2** | E4 | 串行(E1 結果落定後) |
| **批次 3** | E5 | 串行(E4 完成後) |
| **外部並行** | E6 | 任何時候都能跑 |

---

## 3. PropRAG 採用範圍(現在能定案的)

| PropRAG 部分 | 決定 | 理由 |
|---|---|---|
| **Hyperedge(entity-clique 邊)** | **移除**(= E2) | 資料定案,零增量 |
| **Proposition 抽取** | **保留** | 已是我們核心 layer |
| **PPR 對 passage 排序** | **保留** | 已對齊 vanilla |
| Beam path-text 重編碼評分 | 延後(方法改進) | 不是當下工程 |
| 雙向 / parallel expansion | 延後 | 同上 |
| Synonymy edges | 暫不動 | FC entity 多是專有名詞,實證沒看到 paraphrase bridge |

**= 現在跟 PropRAG 有關的工程動作只有「移除 hyperedge」一件(E2)**

---

## 4. 相關檔案 / 文件

- 現況綜整: `docs/method_v2.0.2_status_brief.md`(v9)
- 方法 spec: `docs/method_design_v2.0.2_spec.md`
- 架構圖: `docs/method_v2.0.2_framework.xml`
- timestamp 驗證腳本: `analysis/verify_timestamp_semantics.py`
- 4-ablation cascade 分析: `analysis/analyze_filter_cascade_corrected.py`
- 100Q labels: `analysis/results/full100_eval/labels.json`
- monitoring dumps: `monitoring_logs/*_ablation_*/`

---

## 5. 已決定但**不**在工程清單內(歸方法改進)

- Phase 3 restart(enriched context 重新設計)
- Beam search 改造成近窮舉 + length-robust scoring
- Partner-expanded seeding(active region 加 entity-neighbor 擴展)
- Fact-slot 去重 + 放大 M(top-M cut 處理)
- 上述全部等工程清單收斂後再進

---

## 6. 回來時的 checklist

當回到工程階段,先做這幾件:
1. 讀本檔 → 確認 6 項哪些還沒做、哪些可能因論述方向改變要重排
2. 讀 `method_v2.0.2_status_brief.md` 最新版確認狀態沒變
3. 從**批次 1(E1+E2+E3)並行**開始
4. user 拍板再動工(constraint 不變:跑執行前要明確說好)
