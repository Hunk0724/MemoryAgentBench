# 研究階段成果 — Conclusion & Next Step(2026-06-28)

## Conclusion

### 核心理念(method design)
主張 **knowledge update (KU) 是 query-time 問題,而非 write-time 的 commitment**。三個 commitment:
1. **忠實寫入(conservative / faithful write)**:單一統一抽取器忠實捕捉使用者主張的所有 fact(個人 + 世界),**write-time 不做任何跨筆 LLM 判斷、保留全版本**。
2. **延遲 KU 至 query-time**:衝突消歧只在 query 時做。
3. **LLM 任務簡單化(decoupled, local, cacheable)**:raw-question retrieval → identity grouping((S,P) 結構 + LLM)→ 3-way conflict-type 分類(query-aware)→ deterministic temporal resolution(僅 FRESHNESS 取最新)。

問題定位:**過去記憶系統在 write-time commit KU,一旦誤判即不可逆地把正解從記憶庫刪除**;我們延遲 → 記憶庫永遠保有正解,只需 query-time 用簡單判斷解析。

### Dataset 實驗是否驗證

**FC-SH(general fact;MemoryAgentBench, ICLR 2026)— 機制與結果已充分驗證:**
- **結果**:ours has_pair **86–92%** 跨 6k–262k(robust),勝過所有 baseline(full-context gpt-4o-mini、Zep、mem0+ours storage、mem0)。〔F_robust_haspair〕
- **機制(why we win / why they fail)**:
  - **write-time 不可逆性**:破壞性 baseline 的記憶庫(L0)缺約一半新版,且 **L0 == L1 → 損失在 write-time、非檢索**。〔F_bank_recall〕
  - **兩道關卡**:recall ceiling 決定表現上限;ours 撐高 ceiling(保守寫入)並逼近它(resolution),破壞性 baseline 被低 ceiling 封死。〔F_em_vs_ceiling〕
  - **query-time resolution 有效**:both → new_only。〔F_ours_L1L2_bar〕
  - **貢獻拆解**:忠實抽取 +46pp、query-time resolution +41–46pp。〔F_ablation〕

**LongMemEval(personal fact;ICLR 2025)— ours 泛化已驗證,但對照不完整:**
- ours KU **83.3%**(gpt-4o-mini judge)→ **KU 主張非 FC-overfit、泛化至個人事實**。
- 額外發現 **Mode B**(題目要歷史/舊值或新舊雙值,已用 oracle 驗證為設計如此)→ **反向強化 keep-all**(舊版只有保守寫入保住、可救;破壞性 baseline 連資料都沒了)。
- **誠實缺口**:baseline(mem0 / mem0+ours storage / Zep)的 LongMemEval full run 尚未完成(smoke 已過、full 暫停)→ **「第二個 dataset 也贏 baseline」尚未證實**。

### 一句話
**FC-SH 已把「為何贏 / 為何過去輸」的機制與主結果都立穩;LongMemEval 已證 ours 泛化,但 cross-dataset 的 baseline 對照尚缺。**

---

## Next Step(優先序 = 對論文貢獻 × 扣合 narrative arc)

### P0 — 核心貢獻必補(否則 claim 不完整)
1. **LongMemEval full baselines**(mem0 / mem0+ours storage / Zep):泛化 claim 的另一半 = 「也贏 baseline」。目前只有 ours 83%;baseline smoke 已過、可直接 resume。
2. **all-in-one-call ablation**:把 grouping + type + resolve 塞進**一次 LLM call** vs 我們的**分解 pipeline**。**證「任務簡單化(decompose)」本身有貢獻** → 反駁「直接拿 RAG conflict-resolution 一次解就好」+ 扣 weak-model 主張。

### P1 — 強化說服力(cheap、直接扣 narrative)
3. **qid29 case study**(write-time 不可逆毀損的質化鐵證:mem0 把新版 Guangzhou 刪掉、留舊版 Paris)→ F_bank_recall 的質化 companion。
4. **weak-model dose-response**(強/中/弱 model × ours / baseline):「簡單局部任務利於弱模型」是核心 claim,目前全 gpt-4o-mini、未直接證。
5. **paper-final judge 重跑(gpt-4o)**:驗證期用 gpt-4o-mini,進論文需官方 gpt-4o judge。

### P2 / Future work — 誠實限制(不阻擋投稿,但須在 limitation 寫明)
6. **query-aware resolver(Mode B)**:歷史/雙值題目目前 over-collapse;keep-all 已保住資料,缺 query-aware 解析(已記錄、暫不實作)。
7. **retrieval at scale**:always-write 使記憶庫膨脹、理論上更難檢索;目前 top-100 未成瓶頸,但需 acknowledge / 壓力測試。
8. **Zep multi-granularity(E5)/ Zep-on-LongMemEval**:Zep 原生戰場,強化 cross-system 對照(已延後)。
9. **單一 deterministic run**(temp 0、無 seed variance):若 venue 要求 robustness,需多 seed。

### 取捨建議
先 **P0**(LongMemEval baselines + all-in-one ablation)補「貢獻完整性」;**P1** cheap 可並行;**P2** 寫進 limitation / future work 誠實揭露即可。
