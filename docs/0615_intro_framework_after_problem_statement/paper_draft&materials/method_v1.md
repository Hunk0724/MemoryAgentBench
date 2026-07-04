# Method 草稿（v1,2026-07-04,無 P5 核心版）

> 依據:`current_ours_method_pipeline_and_prompts.md`(實作現況)+ intro v5 + vocabulary v2。
> **本文件僅描述 Method 本身**;Experiments / Baselines / Evaluation Protocol 已移至
> [`evaluation_protocol_fc_mquake_v2.md`](evaluation_protocol_fc_mquake_v2.md)。
> 與實作現況的差異用 ⚠️ 標出;待你決定的問題用 ☐ 標出(彙整於 §5)。

---

# 3. Method

## 3.1 問題設定與符號

記憶庫 M 隨對話流累積原子事實；同一事實可能以多個版本存在。依 §0 Scope（LongMemEval / MemoryAgentBench-FC / BEAM / MemBench 的共同定義），KU 的正確行為是：查詢觸及某事實時，以其**時序最新**版本作答。每筆記憶條目為 (text, triple, ordinal)：text 為抽取後的原子事實、triple 為 (subject, predicate, object) 或 null、ordinal 為寫入時序。

本方法圍繞兩個結構性承諾：**忠實寫入 (Faithful Writes)** 與**查詢時 KU 解析 (Query-Time KU Resolution)**。設計原則貫穿全篇：LLM 任務一律**單筆之內、窄範圍、可 cache**；凡可確定性者交精確運算子；**LLM 全程不參與新舊 (recency) 判斷**。

## 3.2 忠實寫入 (Faithful Writes)

**(1) 統一抽取（P1，LLM，per-chunk）。** 自 role-labeled 對話 chunk 抽取 USER 主張的原子事實。三個設計錨點：(a) **source-based**——只收 user 主張、assistant turn 僅作理解上下文，此為 backbone-independence 的來源（不依賴 LLM 自有知識判斷什麼值得存）；(b) **faithfulness**——照抄、不 fact-check，反事實與互相矛盾的值都如實記錄（衝突是預期會發生的，解析是查詢時的事）；(c) selectivity——無事實主張則回空。已驗證：FC-SH 32k 前 5 chunk 對完美抽取 GT 的逐 chunk micro-recall 97.4%、數量比 1.00。

**(2) 三元組抽取（P2 + P2b fallback，LLM，per-fact）。** 每條事實抽 (s, p, o)：subject 取「更新後仍固定的實體」、object 取「會變動的值」，使同一事實的不同版本落在同一 (S, P) 之下。名詞化關係分解為標準 s-r-o 形；複雜敘事/多事實/主觀狀態允許 null（P2b 對 null 再補 subject-only，使查詢期的 subject guard 普遍適用）。不對世界知識驗證、反事實照抽。⚠️ confidence gate 已於 2026-06-20 移除（4o-mini 的 confidence 近常數），confidence 僅記錄供分析。

**(3) 確定性提交（deterministic）。** 整 chunk batch-embed 後**保留所有版本寫入**，每筆 payload 帶 triple + ordinal。**寫入端不存在任何跨筆 LLM 判斷**：無候選檢索、無衝突偵測、無操作決策——這不是省略，而是承諾：持久記憶狀態不是任何一次 LLM 判斷的函數。
⚠️ 實作註記：程式仍另建 (S, P) 倒排索引但查詢期從未讀取（死碼）。**論文 method 不描述此索引**；☐ 建議直接從程式移除或註明 disabled，避免審稿人對照 code 時混淆。

## 3.3 查詢時 KU 解析 (Query-Time KU Resolution)

**(4) 檢索（deterministic）。** 剝除 qa 模板 boilerplate、以 **raw question** 做 embedding 檢索 top-K（預設 100）。理由：模板指令主導向量會稀釋真問題（FC-SH 64k：GT_new recall@100 由 wrapped 79% → raw 100%，rank 中位數 13→2）。公平性：ungated（vanilla mem0 baseline 同樣套用），且 Zep 的 `get_retrieval_query` 本就做同類剝離——屬 pipeline 對齊而非加 buff，論文於 setup 揭露。

**(5) 條件式結構路由（deterministic）。** 候選集內：有 triple 且該 (S, P) 有 ≥2 競爭者 → `structural_pool`（該 (S, P) 群即為一個事實識別分群）；無 triple 或 (S, P) 單例 → `dynamic_pool`。

**(6) 事實識別分群補救（P3，LLM，僅對 dynamic_pool）。** 只判**身分**（哪些候選是同一事實的不同版本），不判 recency、不答題；只輸出有信心的 cluster（≥2 成員），其餘自動保留。設計偏保守：false-merge 會藏掉合法值、false-split 無害，故 cluster 是 RARE、不確定就不分群。硬規則：不同實體＝不同事實、不同屬性＝不同事實、多值屬性＝並存不分群。

**(7) 時序解析（deterministic）。** 對每個分群（structural 群 + P3 cluster）以 **ordinal argmax 取最新、丟舊**（平手 keep-all）；未入任何群的候選一律保留。在本文 scope 的 KU 定義下，同一事實的多版本即互斥、以最新為準——**衝突判斷退化為分群的直接推論，無須額外 LLM 呼叫**；「誰是權威版本」由 argmax 決定，與 LLM 無關。表面變體群（同值不同寫法）經 argmax 仍得同值，無損。
⚠️ 與實作現況的差異：現行 pipeline 在 (6)(7) 之間有 P5 conflict-type 分類（3-way、query-aware、cached）。**本文核心方法不含 P5**；含 P5 的變體降級為 ablation 之一（§4.4），其結果用以實證核心版的選擇。☐ 對應程式開關：`ours(full)` 保留現行路徑、核心版走 group→argmax 直連。

**(8) 推論（P4，LLM）。** 解析後記憶 + 問題 → 答案。使用 MemoryAgentBench 對（方法類型 × 任務）的**標準 qa 模板**，絕不客製 inference prompt（客製會混淆「贏在記憶還是贏在答題 prompt」）；各任務所用模板逐一列於附錄。

## 3.4 設計性質（一段話收束）

寫入端 LLM 只做單筆轉錄（P1/P2），查詢端 LLM 只剩一個窄任務（P3 身分分群補救，且僅在結構失效的少數案例觸發）；分群主要由 (S, P) 精確比對承擔、解析由 argmax 承擔。因此：(i) 持久記憶狀態與任何 LLM 判斷無關——誤判從永久變暫時；(ii) 系統對 backbone 判斷品質的依賴被壓到最低——此為 weak/frozen backbone 部署宣稱的機制基礎；(iii) 解析用畢即棄、不回寫，每次查詢在完好的記憶上重解。

---

# 4. ☐ 待決問題（僅 Method 部分）

> Experiment / Evaluation / Baseline 相關的待決問題已移至 [`evaluation_protocol_main.md`](evaluation_protocol_main.md) §6。此處只留與 method spec 本身相關的兩個。

1. **(S,P) 倒排索引死碼**（現行 pipeline 在寫入時另建 (S,P) 倒排索引但查詢期從未讀取，見 §3.2 註記）：
   - 選項 (a) 從 method 描述完全隱藏 + 在程式碼移除
   - 選項 (b) 保留程式但在 repo README 註明 disabled（避免 reviewer 對照 code 時混淆）
   - **建議** (b)：最小改動、誠實揭露 dead-code

2. **P5 程式開關 flag 名稱**（核心版 group→argmax 直連 vs ablation 加 P5）：
   - **現行實作**：env var `MEM0_P5_SKIP`
     - `unset`（default）→ P5 on = `ours(full)`（現降級 ablation）
     - `=1` → P5 skip = `ours(no_p5)`（paper 主 method）
   - 見 `methods/phase2_query.py:483`
   - **建議**：保留現行、不改；paper method spec 就以「無 P5」為主敘述，ablation 表格再列 `ours(full)`

<!-- items 1-6, 8（實驗/baseline/backbone/embedding 相關）→ evaluation_protocol_main.md §6 -->

