# Open Questions v5

> v5 更新（依 memory_systems_conflict_comparison.md 文獻軸對齊）：
> - §A.1 數字更正：FC-MH ≤ 5% 而非 6%（依 MemoryAgentBench Table 3 原始）
> - §B.6 phase 命名問題已解決：採用 Ingestion + Retrieval + component slots（文獻認可）
> - 術語對齊：write-time → pre-hoc, query-time → post-hoc（依 Knowledge Conflicts Survey）
> - Phase 3 → Context Constructor (DC6)（依 Zep §3 formalization）：實作數據、設計合理性、Case Study 規劃

> v2 更新（依 empirical-driven design paper 策略）：
> - §B 每個 design choice 加上「empirical evidence 怎麼產生」欄
> - 新增 §H **Case Study Plan**（四類詳細設計，是 paper 命脈）
> - 新增 §I **Paper 策略風險評估**
>
> 紅燈 🔴 = blocker（不解決會被打死）
> 黃燈 🟡 = 重要（建議解決）
> 綠燈 🟢 = nice-to-have

---

# §A. 待補實作數據

## A.1 🔴 先驗證的關鍵數字（v5 更新：用 MemoryAgentBench Table 3 原始數字）

### v5 重要更正：之前說「FC-MH 6%」其實是 ≤ 5%

| 系統 (Table 3, GPT-4o-mini) | FC-SH | **FC-MH** |
|---|---|---|
| GPT-4o (long-context) | 60.0 | **5.0** |
| GPT-4.1-mini (long-context) | 36.0 | **5.0** |
| BM25 | 48.0 | **3.0** |
| GraphRAG | 14.0 | **2.0** |
| HippoRAG-v2 | 54.0 | **5.0** |
| Mem0 | 18.0 | **2.0** |
| Zep | 7.0 | **3.0** |
| MIRIX | 14.0 | **2.0** |

**所有主流系統 FC-MH ≤ 5%**（不是 ≤ 6%）。Paper 寫作時用 5% 為準。

### 我們的數字待確認

| 數字 | 目前印象 | 需驗證 | 確切 source 在哪？ |
|---|---|---|---|
| 我們在 FC-MH accuracy | 31% | LLM？runs？setting？是否與 Table 3 同 GPT-4o-mini？ | `[TODO 你的 log path]` |
| Vanilla HippoRAG 在 FC-MH（我們補測） | 28% 或 5%？ | 我們補測是否與 Table 3 一致？若不一致是哪個 setting 差異？ | `[TODO]` |
| Zep 在 FC-MH（我們補測） | 28% 或 3%？ | 同上 | `[TODO]` |
| Phase 1+2 oracle ceiling | ~60% | oracle 怎麼定義？vanilla prompt 嗎？ | `[TODO]` |
| Clean context + V1 prompt | 80%+ | 多少筆？哪個 LLM？ | `[TODO]` |

**重要核對**：你說的 31% 是哪個 setting？這直接影響 paper 寫作。如果你的 31% 與 Table 3 同 backbone 比 Zep 3%，是 28pp 提升（極大）；如果不同 backbone，可能是 1pp 內微提升。

### MemoryAgentBench Appendix K.2（prompt-fix 失敗，paper §4.0.1 證據）

| Policy | FC-SH | FC-MH |
|---|---|---|
| Baseline (GPT-4.1-mini) | 36.0 | 5.0 |
| Policy A (Always Prefer Later) | 40.0 | **4.0** |
| Policy B (Conservative Negation) | 28.0 | 4.0 |

Paper 原文：「prompting cannot effectively propagate updates through multi-step reasoning chains」

**用於 §4.0.1** 證明 fair-comparison constraint（不改 inference prompt）是合理的。

### 行動

在跑新實驗前，每個數字標出精確 source（log file path / paper page / table number）。沒準確 source 的數字不出現在 paper。

## A.2 🔴 A 系列實驗（派系 A 對手診斷）

### A1a - Per-ingestion 衝突偵測（intrinsic 品質）
`[TODO]` 對 Zep / Mem0g（必），EMG-RAG / Memory-R1（可選）跑：
```
For each ingestion event:
  Recall = 真衝突中被識別的比例
  Precision = 識別為衝突中真衝突的比例
  F1
```
- 樣本數 `[TODO 預估]`
- 對應 paper §4.1 證據

### A1b - Query-driven 衝突偵測（extrinsic 品質）
`[TODO]` 同上，但只算 query 推理鏈上的衝突：
```
For each FC-MH query：
  Recall / Precision / F1 限定在 ground-truth reasoning chain 上
```
- **A1a vs A1b 的 gap 是 §4.1 的核心數字**

### A1.5 - 失敗 case taxonomy
`[TODO]` 從 A1b 失敗 30-50 case manual annotation：
- 類型 1：純語意衝突（詞彙不重疊）
- 類型 2：跨多 turn 傳遞衝突
- 類型 3：隱含衝突（需 query 才 surface）
- 類型 4：False positive
- 對應 paper §7.1 Case Study Type 1

### A2 - 多跳 path retrieval recall
`[TODO]` 對派系 A 系統測試：
```
Given FC-MH query Q with ground-truth chain [p1, p2, p3]：
  Top-K (K=5/10/20) 是否包含 p1, p2, p3 全部？
```

### A3 - Multi-hop 改造可行性論證
不需大實驗：論證 + mini case study：
- Zep 加 multi-hop 的版本（遞迴 entity neighborhood）為何仍失敗
- 預期 failure mode：bi-temporal invalidation 已破壞性執行，舊資訊遺失

### A4 - End-to-end QA on FC-MH

| Method | Acc | 1-hop | 2-hop | 3-hop |
|---|---|---|---|---|
| Vanilla HippoRAG | `[TODO]` | `[TODO]` | `[TODO]` | `[TODO]` |
| PropRAG | `[TODO]` | `[TODO]` | `[TODO]` | `[TODO]` |
| Zep | `[TODO]` | `[TODO]` | `[TODO]` | `[TODO]` |
| Mem0g | `[TODO]` | `[TODO]` | `[TODO]` | `[TODO]` |
| Our method | `[TODO ~31%?]` | `[TODO]` | `[TODO]` | `[TODO]` |

## A.3 🔴 B 系列實驗（派系 B 對手診斷）

### B1a / B1b / B1c - 三個獨立的 Retrieval Metrics

> ⚠️ 概念警告：這三個 metrics **互相不能互推**，要分開計算且分開呈現。

#### 具體 case 示例

以 2-hop query「Tom 現在的主管所在城市?」為例，記憶中：
- p1: 「Tom 的主管是 Bob」🔴 舊版本
- p2: 「Tom 的主管現在是 Alice」✅ 新版本（hop 1 ground truth）
- p3: 「Alice 工作於 Taipei」✅ 新版本（hop 2 ground truth）
- p4: 「Bob 在 New York」🟡 牽涉舊版本鏈
- p5-p50: 無關內容

Ground truth chain = [p2, p3]

#### B1a - New-version recall@K
- **問題**：top-K 是否包含「該找的最新版本」？
- **計算**：per-hop 平均
- **範例**：top-10 含 p2 與 p3 → recall = 2/2 = 100%
- **越高越好**

#### B1b - Old-version retrieval rate@K
- **問題**：top-K 是否（也）包含「不該找的舊版本」？
- **計算**：per-conflicting-pair
- **範例**：top-10 含 p1 → rate = 1/1 = 100%（這 100% 是「不好」的）
- **越低越好**

#### B1c - Multi-hop path recall@K
- **問題**：top-K 是否**完整**包含整條推理鏈？
- **計算**：per-query（all-or-nothing：整條都在 = 1，少一個 = 0）
- **範例**：top-10 = {p2, p3, ...} → path recall = 1；top-10 = {p2, ...} 沒 p3 → path recall = 0
- **越高越好**

#### 三個 metrics 的獨立性矩陣（為何不能互推）

| top-K 內容 | New-ver recall | Old-ver rate | Path recall | 失敗模式 |
|---|---|---|---|---|
| {p2, p3, ...} 無 p1 | 100% | 0% | 1 | ✅ 理想 |
| {p2, p3, p1, ...} | 100% | 100% | 1 | ⚠️ 找齊但污染（典型派系 B raw） |
| {p2, ...} 無 p3 無 p1 | 50% | 0% | 0 | ⚠️ 多跳沒找齊（典型派系 A） |
| {p2, p1, ...} 無 p3 | 50% | 100% | 0 | 💀 雙重失敗 |
| {p1, ...} 無 p2 無 p3 | 0% | 100% | 0 | 💀 完全失敗 |

#### 預期對手表現（暫定，待實驗確認）

| 方法 | 預期 New-ver | 預期 Old-ver | 預期 Path | 預期失敗模式 |
|---|---|---|---|---|
| HippoRAG / PropRAG raw | 🟢 高 | 🔴 高 | 🟡 中 | 找齊但污染 |
| Zep cloud | 🟡 中 | 🟢 低 | 🔴 低 | 多跳找不齊 |
| Mem0g (vendored) | 🟡 中 | 🟢 極低 | 🔴 低 | 多跳找不齊（且不可逆） |
| T-GRAG（FC-MH 適配）| 🔴 低 | 🟢 低 | 🔴 低 | 機制不觸發 |
| **我們** | 🟢 高 | 🟢 低 | 🟢 高 | 預期最佳 |

#### 具體實驗執行

`[TODO]` 在 vanilla HippoRAG / PropRAG / Zep / Mem0g / T-GRAG / 我們 上跑這三個 metrics：
- K = 5, 10, 20 三組
- 對應 paper §4.3 propagation 證據
- 機制層級診斷的關鍵

### B2 - 加我們衝突機制後的 detection accuracy

`[TODO]` 直接量我們 Post-hoc Conflict slot 的 detection F1：

| Method | Per-ingestion F1 | Query-driven F1 |
|---|---|---|
| Zep (A1a) | `[TODO]` | A1b `[TODO]` |
| Mem0g | `[TODO]` | `[TODO]` |
| **Ours (Post-hoc)** | N/A | `[TODO]` |

### B3 - End-to-end QA on FC-MH
見 A.2 A4 表

## A.4 🔴 C 系列實驗（派系 C 對手在 implicit 場景的失敗）

### C1 - T-GRAG 適配 FC-MH 🔴 必做
`[TODO]`：
1. 從 T-GRAG GitHub 取 implementation
2. 把 ingestion order 視為 timestamp
3. 跑 FC-MH，記錄結果與 failure mode
- **預期失敗點**：Temporal Query Decomposition 不觸發（query 沒 time keyword）
- 失敗也是好故事

### C2 - KEDKG 適配 FC-MH 🟡 嘗試
`[TODO]`：
1. 用 LLM 在 ingestion 時 propose 「這訊息更新了某 fact」當 edit
2. 餵入 KEDKG pipeline
- **預期失敗點**：collapse 回 write-time 派系，與 Mem0/Zep 相近

### C3 - MemoTime 適配 FC-MH 🟢 可選
**建議論證 not applicable** 而非強行跑：
- 對話無 explicit operator → Temporal Grounding 失效
- 建立 TKG 工作量大且不公平

## A.5 🔴 D 系列實驗（Context Presentation 與 Fair Comparison）

### 重要前提
- **Fair 組**：用 MemoryAgentBench 內建 vanilla system prompt，可進 main result
- **Ceiling 組**：用自訂 prompt（如 V1），僅作 ceiling analysis、Appendix 用

### D-Fair 組（Main Result 可用）

| 編號 | 配置 | `[TODO 數據]` | 用途 |
|---|---|---|---|
| D-Fair-1 | Baselines 回傳 context + vanilla prompt | `[TODO]` | 對手 baseline |
| D-Fair-2 | 我們 filter 後 context + vanilla prompt | `[TODO ~31%?]` | **我們的 main result** |
| D-Fair-3 | 我們 + 結構化呈現 + vanilla prompt | `[TODO]` | DC6 變體 1 |
| D-Fair-4 | 我們 + annotation + vanilla prompt | `[TODO]` | DC6 變體 2 |
| D-Fair-5 | 我們 + conflict transparency + vanilla prompt | `[TODO]` | DC6 變體 3 |

### D-Ceiling 組（僅作 Ceiling Analysis）

| 編號 | 配置 | `[TODO 數據]` | 用途 |
|---|---|---|---|
| D-Ceiling-1 | Oracle clean context + vanilla prompt | `[TODO ~60%?]` | 純 retrieval 上限 |
| D-Ceiling-2 | Oracle clean context + V1 prompt | `[TODO ~80%+?]` | 純 inference 上限 |
| D-Ceiling-3 | 我們 context + V1 prompt | `[TODO]` | 「retrieval + inference 都優化」的上限 |

### 重要論述
- **D-Fair-1/2 對比** → 我們方法 vs baselines 的 fair main result
- **D-Fair-2 vs D-Fair-3/4/5** → DC6 ablation（不同 context format）
- **D-Ceiling-1/2 對比** → retrieval 與 inference 對最終 accuracy 的相對貢獻
- **D-Fair-2 vs D-Ceiling-2 的 gap** → 解除 fair constraint 後的潛在上限（discussion 用）
- **D-Ceiling-3** → 在 future direction 中作為「若解除 fair」的依據

### 為何不直接用 V1 prompt 作為 main result？
- 破壞與 baselines 的公平比較
- 若採用，必須給所有 baselines 同樣的 V1 prompt → 工作量爆炸
- V1 prompt 屬於「inference improvement」獨立 line of work，不在我們 paper scope
- 詳見 narrative §5.0 與 §13 紅線 7、8

## A.6 🟡 Ablation 待補

| 變體 | 配置 | 對應 Design Choice | `[TODO 數據]` |
|---|---|---|---|
| Full | All | 完整 | `[TODO]` |
| -query-time | Conflict → write-time | DC1 | `[TODO]` |
| -LLM grouping | Embedding threshold | DC2 | `[TODO]` |
| -code timestamp | LLM direct judgment | DC2+DC3 | `[TODO]` |
| -beam search | Top-K semantic only | DC4 | `[TODO]` |
| -logical filter | Destructive delete | DC5 | `[TODO]` |
| -DC6 Context Constructor | Vanilla concat | DC6 | `[TODO]` |

---

# §B. 設計合理性質疑（每個 choice 加 empirical evidence 欄）

> v2 更新：每個 design 改用「observation → choice → empirical evidence → 引用」四欄。

## §B.1 🔴 為何選 HippoRAG 2 + PropRAG 作為基底？

### 現狀
目前架構是「拼湊出來能跑」，沒有明確論述為何選 HippoRAG 2 + PropRAG。

### 需要回答（empirical-driven 方式）
| 維度 | 內容 |
|---|---|
| Observation | 應該是「多跳推理鏈在 implicit conflict 場景下的 retrieval recall 差距」 |
| Choice | HippoRAG 2 提供 entry point（PPR），PropRAG 提供 expansion（beam search） |
| Empirical evidence | Ablation: PPR-only vs BeamSearch-only vs PPR+BeamSearch 在 FC-MH 上的 path recall |
| 引用依據 | HippoRAG 2 paper 證 PPR 多跳能力；PropRAG paper 證 beam search 對 chain-finding；Dense X Retrieval 證 proposition unit |

### 行動
🔴 跑 ablation：
- 變體 A：純 HippoRAG 2 + Post-hoc Conflict
- 變體 B：純 PropRAG + Post-hoc Conflict
- 變體 C：HippoRAG 2 + PropRAG + Post-hoc Conflict（現在的方法）
- 變體 D（可選）：HopRAG + Post-hoc Conflict

如果 C >> A 且 C >> B → 組合合理性建立 + 寫進 §5.3 DC4

### 若 ablation 顯示組合沒幫助怎麼辦？
- 簡化方法（只用一個），更符合 empirical-driven 風格的 Occam's razor
- 在 paper 寫：「we found PropRAG alone sufficient...」是誠實且有 insight 的結論

---

## §B.2 🔴 為何 LLM 只做分組，timestamp 用程式碼？

### 現狀
這是我們最有原創性的 design choice，但靠直覺說「LLM 會有 prior bias」。

### v2 升級：對應到 §4.2 Observation
| 維度 | 內容 |
|---|---|
| Observation | §4.2 LLM 在 counterfactual contexts 中 prior bias 反向干擾 |
| Choice | LLM 任務限縮為 semantic grouping，時序判定用程式碼 |
| Empirical evidence | Ablation: LLM direct vs LLM-group+code 在 counterfactual subset 的 F1 差距 |
| Case study | §7.2 列 3-5 個 counterfactual case |
| 引用依據 | MQUAKE-CF (Zhong et al., 2023) 已證 LLM 有 counterfactual bias；CLEAR (2510.12460) Probing Latent Knowledge Conflict |

### 行動
🔴 必做的 ablation：
1. 篩出 FC-MH 中的 counterfactual subset（與 LLM prior 不符）
2. 比較 direct vs grouped 的 detection F1
3. Manual annotate 3-5 個 case 寫進 §7.2

### Risk: 如果 FC-MH 沒有明確 counterfactual 設計怎麼辦？
- 檢查 MemoryAgentBench 原始 paper 對 FC-MH 的 dataset 構造方法
- 若無 counterfactual：可人工 inject 一個小 subset 來測（並在 paper 說明）
- 或：把這個 design choice 降級為「robustness consideration」而非主要 contribution

---

## §B.3 🔴 Post-hoc Conflict slot 的 grouping 具體實作

### 現狀
narrative 寫「對候選推理鏈每個 proposition，找語意 Top-K + entity overlap 的相關 propositions，LLM 做衝突分組」，但具體演算法不清。

### 需要決定的細節
| 細節 | 候選方案 | 你的選擇 | empirical 依據 |
|---|---|---|---|
| 語意 Top-K | K=5/10/20 | `[TODO]` | `[TODO sensitivity 跑]` |
| Entity overlap 公式 | Jaccard / Dice / count | `[TODO]` | `[TODO 比較]` |
| LLM grouping prompt | One-shot / Few-shot / CoT | `[TODO]` | `[TODO ablation]` |
| 同 timestamp tie-break | Most recent ingestion / 全保留 / random | `[TODO]` | `[TODO]` |
| Grouping uncertainty | 多保留 / 多刪 / abstain | `[TODO]` | `[TODO]` |

### 引用依據
- Entity overlap：entity linking / coreference resolution
- LLM grouping prompt：CoT / verification prompting
- Tie-break：temporal QA 工作的做法

---

## §B.4 🟡 是否在 beam search 加 timestamp decay？

### 0522 會議 hint
Advisor 提過：「beam search 的 edge weight 是否考慮 timestamp？越舊的 weight 越低？」

### 設計選項
| 方案 | 描述 | 優缺點 |
|---|---|---|
| A. 不改 | 純語意 edge weight | 簡單；對舊版本無 retrieval-time bias |
| B. 線性 decay | edge_weight × exp(-λ × age) | 對近期偏好；λ 超參 |
| C. Step function | 舊版本 weight = 0.5 × 新版本 | 粗暴但可解釋 |
| D. 學習式 | Learn decay function | 太重，over-engineer |

### 重要考量（empirical-driven 風格）
若 beam search 已 prefer 新版本，Post-hoc Conflict slot功能會被弱化。**必須 ablation**：
- 變體 1：純語意 beam + Post-hoc Conflict（現在）
- 變體 2：timestamp decay beam + 無 Phase 2
- 變體 3：timestamp decay beam + Post-hoc Conflict

若變體 2 ≈ 變體 1，說明 Phase 2 才是關鍵；若變體 2 >> 變體 1，需要重新思考 Phase 2 的角色。

### 引用依據
- Temporal IR / time-aware ranking 文獻
- SAT-Graph RAG (2025), Temporal-aware Matryoshka RL (2026/1)

---

## §B.5 🔴 Phase 3 該怎麼設計？（最大空白，且風格未鎖死）

### 重要前提（v2 修正）

**Fair-comparison constraint**：所有 baselines 在 MemoryAgentBench 用同一個 vanilla system prompt。我們**不能改 inference prompt**，否則破壞公平比較。

**Phase 3 的本質改變**：
- ❌ 不是「改進 LLM 推理機制」（如改 prompt 為 V1 形式）
- ✅ 是「改進回傳給 LLM 的 memory context 內容與呈現方式」

### V1 prompt（每跳輸出答案）的處理

V1 prompt 之前我們認為達到 80%+，但這個結果**不能進 main result**：
- ✓ 可作為 **ceiling analysis**（D-Ceiling-2/3）
- ✓ 可在 Appendix 報告，作為 future direction 的依據
- ✗ 不能進 main result table
- ✗ 不能 claim「我們達到 80%+」

### Phase 3 候選方向（在 fair-comparison constraint 下）

#### 方向 1：結構化 context 呈現
- 把 reasoning chain 顯式呈現（按推理順序排列 propositions）
- 例：原本回傳「[p1, p7, p3, p9]」改為「Step 1: p7 → Step 2: p1 → Step 3: p3」
- 引用：multi-hop QA 的 evidence chain 文獻

#### 方向 2：Context Annotation
- 為每個 proposition 加 metadata（entity, source, ingestion order）
- 讓 LLM 看到「這個事實來自第幾 turn / 哪個 speaker」
- 引用：RAG with metadata / temporal annotation 文獻

#### 方向 3：Conflict Transparency
- 把被 filter 的舊版本也呈現給 LLM（標記為「舊版本」）
- 讓 LLM 在看到衝突時 explicit 知道我們的選擇
- 引用：multi-source RAG / source-aware generation

#### 方向 4：Compression / Distillation
- 把 reasoning chain summarize 成更精煉的形式
- 風險：loss of information
- 引用：context compression 文獻

#### 方向 5：採用 given-context multi-hop reasoning 方法的 prompt 結構（重要區分）
- ⚠️ 這個方向需要小心：若採用 IRCoT / Self-RAG 等的 inference 機制，會破壞 fair-comparison
- 變通：把這些方法的 reasoning trace 預先計算後**寫入 context**，而不是改 LLM 的 inference 流程
- 例：用 IRCoT 風格產生 reasoning steps，把 steps 當作 context 一部分送給 vanilla prompt

### Phase 3 是否可能變得複雜？（鬆綁 simple-only 風格的原因）

是的。如果 §H.4 failure case 顯示「context 已經乾淨 + 已結構化，但 LLM 仍推理錯誤」，那 Phase 3 可能需要：
- 更複雜的 context refinement 演算法
- 引入 reasoning verification（在 context 中預先計算 sanity check）
- 甚至引入小模型做 context selection

**這意味著 paper 風格不應該寫死 simple-only**，要保留方法深化的彈性。

### 🔴 必須與 advisor 討論的事項

1. Phase 3 上面 5 個方向哪個最有 publication value？
2. Fair-comparison constraint 是否會被 reviewer 接受？或應該也 report V1 prompt 結果？
3. 如果 D-Fair-2 結果遠低於 D-Ceiling-2，paper 是否要轉變 framing？
4. Phase 3 工作量配置（多少時間在 context refinement 設計）

### 引用依據（候選）

**對 inference 機制的引用（謹慎使用，避免採用其 inference 流程，只借鏡其 context structure）**：
- IRCoT (Trivedi et al., 2023) - interleaved retrieval and reasoning
- Self-RAG (Asai et al., 2024) - self-reflective generation
- ReAct (Yao et al., 2023) - reasoning + acting

**對 context refinement / presentation 的引用**：
- MeLLo / PokeMQA - 多跳問題分解
- Chain-of-Note - context 標註與 reasoning trace
- `[TODO 補：context format 對 LLM 推理影響的 paper]`

### 風險：如果 §4.4 observation 不存在怎麼辦？

若 D-Fair 組實驗顯示「不同 context format 對最終 accuracy 影響微小」（即 §4.4 假設不成立）：
- 選項 A：DC6 降級為「presentation choice」而非 contribution
- 選項 B：Phase 3 重新定位為「diagnostic」——展示 retrieval-side 與 inference-side 的瓶頸劃分
- 選項 C：解除 fair-comparison constraint，將 V1 prompt 改進納入方法，但需要把 baselines 也用同樣優化重新跑（工作量大）

`[TODO 跑 D-Fair-3/4/5 才能確認哪個選項可行]`

---

## §B.6 ✅ Phase 命名問題（v5 解決）

### v5 解決方案

採用文獻認可的 **Ingestion Phase + Retrieval Phase** 雙 phase 架構，配合 component slots：

```
Ingestion Phase:
  - Extraction
  - Update
  - Conflict Mechanism (pre-hoc, optional)

Retrieval Phase:
  - Search (φ)
  - Multi-hop Reasoning
  - Conflict Mechanism (post-hoc, optional)
  - Rerank (ρ)
  - Context Constructor (χ)
```

### 文獻依據（多重）

- **Mem0 §2.1**：「incremental processing paradigm... extraction and update」
- **MemoryAgentBench §3.2**：「incrementally update the memory」
- **Zep §3**：給 retrieval phase 形式化定義 `f(α) = χ(ρ(φ(α))) = β`
- **HippoRAG 2 §3 / PropRAG §5**：「offline indexing + online retrieval」二分

### 跨系統術語對齊

| 我們使用 | Mem0 / MABench | Zep | HippoRAG / PropRAG | Knowledge Conflicts Survey |
|---|---|---|---|---|
| Ingestion Phase | extraction + update | graph construction | offline indexing | pre-hoc 時機 |
| Retrieval Phase | retrieval | memory retrieval (φ→ρ→χ) | online retrieval | post-hoc 時機 |

### 我們的方法在這個 abstraction 下的位置

清楚標出我們在哪個 component slot 與對手不同（見 narrative §5.5 表）：
- Pre-hoc Conflict slot：**我們留空**（vs Zep / Mem0g 填）
- Multi-hop Reasoning slot：**沿用 PropRAG**（不爭創新）
- Post-hoc Conflict slot：**我們的核心貢獻**（vs HippoRAG/PropRAG 留空）
- Context Constructor slot：**DC6 待設計**（vs 對手都是 raw passages）

✅ Phase 命名問題不再需要爭議。

---

## §B.7 🟢 為何用 proposition 而非 triple / chunk / sentence？

### 引用支持
- Chen et al. (2024) Dense X Retrieval：proposition 在 retrieval 優於 chunks / sentences
- PropRAG paper：proposition 比 triple 保留更多 context

### 行動
🟢 在 paper 加 1-2 句說明：「我們沿用 proposition 因為（a）context-rich（b）conflict 容易定位到單一 proposition」

---

## §B.8 🆕 🟡 為何戰場限縮 KG-based memory？

### 為何需要這個論述
Reviewer 一定會問「為什麼不比 Mem0 (non-KG)？」。Paper §1.4 需明確論述。

### 三個論述支柱（見 narrative §1.4）
1. **結構必要性**：多跳推理需要 KG 結構（HippoRAG 2 / PropRAG paper 已證）
2. **衝突 anchor**：fine-grained conflict 需要 structured unit
3. **場域限定合法**：T-GRAG/MemoTime/KEDKG 也都限定子場景

### 行動
🟡 在 paper §1.4 寫明這三個論述 + 在 Limitations 明確說「non-KG 是 future work」

---

# §C. 對手適配可行性（C 系列實驗詳細設計）

## §C.1 🔴 T-GRAG 適配 FC-MH

### T-GRAG 元件在對話場景的命運
| T-GRAG 元件 | 在 FC-MH 命運 |
|---|---|
| Temporal KG Generator | ⚠️ Partial（用 ingestion order 當 timestamp） |
| Temporal Query Decomposition | 💀 失效（query 沒 time keyword） |
| Three-layer Interactive Retriever | ⚠️ Partial（layer-by-time 失效） |
| Source Text Extractor | ✓ 可保留 |
| LLM Generator | ✓ 可保留 |

### 適配步驟
1. 從 T-GRAG GitHub 取 code
2. Ingestion order → timestamp
3. Query 不變
4. 跑 FC-MH

### 預期結果
- T-GRAG 在 FC-MH 應明顯弱於 Time-LongQA
- 寫法：「T-GRAG's Temporal Query Decomposition assumes explicit time keywords; in conversational FC-MH where queries lack such signals, the mechanism does not engage.」

## §C.2 🟡 KEDKG 適配 FC-MH

### KEDKG 元件
| KEDKG 元件 | 在 FC-MH 命運 |
|---|---|
| Explicit edits input | 💀 對話沒 explicit edits |
| → 若 derive edits via LLM | ⚠️ Collapse 回 write-time 派系 |
| CDM module | ⚠️ 依賴 explicit edits |
| Question decomposition | ✓ 可保留（需 fine-tune） |

### 適配步驟
1. 用 LLM 在 ingestion 時 propose edits
2. 餵入 KEDKG pipeline
3. 跑 FC-MH

### 預期結果
- 與 Zep / Mem0 相近（因為 derived edits 同質）
- 寫法：「KEDKG's design assumes explicit edits; deriving edits at ingestion essentially reduces to write-time inference, suffering from the same query-agnostic limitations as Section 4.1.」

## §C.3 🟢 MemoTime 適配 FC-MH

**建議論證 not applicable 而非強行跑**：
- 對話無 explicit operator → Temporal Grounding 失效
- 建立 TKG 工作量大
- 在 paper 寫：「MemoTime assumes structured TKG with explicit temporal operators; both assumptions are violated in conversational memory, making direct adaptation impractical.」

---

# §D. 系統架構整體合理性 audit

## §D.1 各 phase 功能定義是否清晰？

| Phase | 我們的版本 | 問題 |
|---|---|---|
| Phase 1 | Candidate reasoning chain extraction | 「extraction」太模糊；改為「Multi-hop candidate retrieval」 |
| Phase 2 | Conflict detection & resolution | OK |
| Phase 3 | Multi-hop inference with returned memory | 改為「Constrained inference over filtered evidence」 |

## §D.2 各 phase 的 input / output

| Phase | Input | Output | 問題 |
|---|---|---|---|
| Phase 1 | Query | Candidate paths | `[TODO]` list / DAG / tree？ |
| Phase 2 | Candidate paths + Memory KG | Filtered evidence | `[TODO]` path-level 或 proposition-level？ |
| Phase 3 | Filtered evidence + Query | Final answer | `[TODO]` single LLM call 或 multi-step？ |

## §D.3 是否有 phase 邊界 leakage？

| 潛在 leakage | 是否有問題 |
|---|---|
| Search (φ) component 是否用 timestamp？ | 若是 → 影響 Phase 2 ablation cleanliness |
| Phase 2 是否需要重新 query KG？ | 若是 → 邊界模糊 |
| Phase 3 是否 fall back to retrieve more？ | 若是 → 變成 IRCoT |

`[TODO]` 把這三個 leakage 答案明確標出。

## §D.4 整體 latency / cost

`[TODO]` 跑 timing：
- Phase 1: `[TODO]` ms / `[TODO]` LLM calls
- Phase 2: `[TODO]` ms / `[TODO]` LLM calls
- Phase 3: `[TODO]` ms / `[TODO]` LLM calls
- Total: `[TODO]` ms

對比 Zep / HippoRAG 2 等 baseline 的 latency

Reviewer 一定會問 query-time 成本——必須有數據。

---

# §E. 給 Advisor 的問題清單（按重要性）

下次面對面建議 60-90 分鐘解決前 5 個：

1. 🔴 **Phase 3 該選哪個方向？**（§B.5）最大空白
2. 🔴 **HippoRAG 2 + PropRAG 組合是否經得起 ablation？**（§B.1）
3. 🔴 **T-GRAG 適配實驗的 fairness**（§C.1）
4. 🔴 **Phase 命名與框架對齊**（§B.6）
5. 🔴 **戰場限縮 KG 的論述強度**（§B.8）
6. 🟡 **Beam search 是否要加 timestamp decay**（§B.4）
7. 🟡 **C2 / C3 是否值得花時間做**（§C.2/C.3）
8. 🟡 **LLM grouping prompt 設計**（§B.3）
9. 🟡 **Case study 規模與工作量**（§H）
10. 🟢 **論文投稿目標 venue 與時程**

---

# §F. Self-checklist（送 paper 前要全打勾）

## 數據層
- [ ] §A.1 6 個關鍵數字都有精確 source
- [ ] §A.2 A1a / A1b / A1.5 / A2 / A3 / A4 全部跑完
- [ ] §A.3 B1a / B1b / B1c / B2 / B3 全部跑完
- [ ] §A.4 C1 (T-GRAG) 必跑、C2 (KEDKG) 嘗試、C3 論證
- [ ] §A.5 D1 / D2 / D3 / D4 全部跑完
- [ ] §A.6 ablation 7 個變體全跑

## 設計合理性層
- [ ] §B.1 HippoRAG + PropRAG 組合有 ablation 證據
- [ ] §B.2 LLM 分組 + 程式 timestamp 有 ablation + counterfactual case
- [ ] §B.3 Phase 2 具體算法細節都決定
- [ ] §B.4 timestamp decay 已決定加或不加並有依據
- [ ] §B.5 Phase 3 方向已選定並有 2-3 篇前人依據
- [ ] §B.6 Phase 命名跟主流文獻對齊或有說明
- [ ] §B.7 proposition unit 選擇有說明
- [ ] §B.8 KG 戰場限縮的論述強度足夠

## Case Study 層（v2 新增 §H）
- [ ] §H.1 Type 1 失敗 taxonomy annotation 完成
- [ ] §H.2 Type 2 LLM prior bias case 完成
- [ ] §H.3 Type 3 propagation case 完成
- [ ] §H.4 Type 4 我們的 failure case 完成

## 對手適配層
- [ ] §C.1 T-GRAG 適配跑完，結果寫進 paper
- [ ] §C.2 KEDKG 適配跑完或論證 not applicable
- [ ] §C.3 MemoTime 同上

## 架構合理性層
- [ ] §D.1 各 phase 功能定義清晰
- [ ] §D.2 各 phase input / output 明確
- [ ] §D.3 leakage 已處理
- [ ] §D.4 latency / cost 數據完整

## 🆕 Baseline 對齊 / Disclosure 層
- [ ] §J.1 三方法版本鎖定確認
- [ ] §J.2 paper 三層 disclosure 寫入主文 + footnote + supplementary
- [ ] §J.3 至少 7 個口委 Q&A 都能回答
- [ ] §J.5 reproducibility checklist 都打勾
- [ ] §J.6 mem0 v3 移除圖記憶寫入 Discussion 章節

---

# §G. 不可妥協的紅線

無論 advisor 如何建議，以下不可犧牲：

1. **Phase 2 必須是 query-time**——否則整個 thesis 崩盤
2. **LLM 不直接 invalidate / delete**——與派系 A 的關鍵區隔
3. **MemoryAgentBench FC-MH 必須是主 benchmark**——6% → 31% 故事的根基
4. **必須比 T-GRAG**——否則無法 claim implicit subproblem 位置
5. **Ablation 必須包含 §B.2 (LLM 分組 vs 直接判斷)**——是 §4.2 observation 的證據
6. **§3 Empirical Motivation 與 §7 Case Study 必須是 paper 重點章節**——empirical 與 case study 風格的命脈
7. **🆕 Main result 必須用 vanilla MemoryAgentBench system prompt**——所有方法公平比較；V1 prompt 等 inference 優化只進 Appendix / Ceiling Analysis
8. **🆕 Phase 3 只動 context 不動 inference prompt**——破壞此原則 = 破壞 fair comparison = paper 主結果失效

---

# §H. 🆕 Case Study Plan（v2 新增，paper 命脈）

> Case study 是 empirical-driven paper 的命脈。四類 case study 需要 systematic annotation。

## §H.1 Type 1: Write-time 失敗 Taxonomy

### 目的
證明 write-time 不只是「準度不夠」，而是「對某類衝突原理性盲」——這是 §4.1 的核心證據。

### Annotation 方法
1. 從 A1b 失敗 case pool 中 random sample 30-50 個
2. 兩名 annotator 獨立 label 為下列類別之一
3. Inter-annotator agreement 用 Cohen's κ
4. 計算每類比例

### 預期類別
- **類型 A：純語意衝突**——新訊息詞彙與舊訊息不重疊，write-time LLM 找不到比對對象
  - 例：「I love Italian food」← →「I switched to vegan diet last month」（沒有共同關鍵詞）
- **類型 B：跨多 turn 傳遞衝突**——衝突訊息與被衝突訊息之間隔多個 turn
- **類型 C：隱含衝突**——只有 query 才能 surface（如 query 問「Tom 現在做什麼」才知道「Tom 工程師」與「Tom 轉職設計師」衝突）
- **類型 D：False positive**——write-time 誤判為衝突，實為補充（如「Tom 會 Python」+「Tom 也會 Java」）

### Selection Criteria
- 從 A1b 失敗 case pool（write-time 該偵測卻沒偵測）
- 每類至少 5 個 case
- 涵蓋不同 LLM baseline（Zep / Mem0g）

### 輸出（Paper §7.1）
- Pie chart of 類別比例
- 每類 1-2 representative case 詳述
- Inter-annotator agreement 數字

### 工作量
- ~10-15 hours annotation
- 可以 advisor 當第二 annotator

---

## §H.2 Type 2: LLM Prior Bias Case

### 目的
證明 §4.2 design choice 2/3 不是 paranoia，是 measurable phenomenon。

### Annotation 方法
1. 篩出 FC-MH 中與 LLM prior 不符的 case（dataset 設定 counterfactual world fact）
2. 對每個 case，比較「LLM direct judgment」vs「LLM-group + code-compare」的決策
3. 對 LLM direct judgment 失敗的 case，分析是否為 prior bias 導致

### 篩選 counterfactual 的方法
1. 列出 FC-MH 涉及的 entity-relation pair
2. 用 GPT-4 / Wikipedia 確認 dataset 提供的 fact 是否符合 real-world
3. 標出「與 real-world 衝突」的 subset

### 若 FC-MH 沒有明確 counterfactual 怎麼辦？
- 選項 A：用 MQUAKE-CF（有明確 counterfactual）作為補充 dataset
- 選項 B：人工 inject counterfactual 子集（必須在 paper 透明說明）
- 選項 C：降級為 robustness analysis（仍可保留）

### 輸出（Paper §7.2）
- Accuracy 比較表（direct vs grouped）on counterfactual subset
- 3-5 個 case 展示 LLM 如何被 prior 反向拉走
- Qualitative analysis：bias 的型態（fact reversal / entity confusion / ...）

### 工作量
- ~15 hours（含 dataset audit）

---

## §H.3 Type 3: Multi-hop Conflict Propagation

### 目的
證明 §4.3 propagation effect，為 Design Choice 4 提供 case 依據。

### Annotation 方法
1. 從 FC-MH 篩 3-hop query
2. 對每個 query，標記 hop 1 / hop 2 / hop 3 是否各自有衝突
3. 計算 propagation：P(hop k+1 錯 | hop k 錯)
4. 找 hop 1 與 hop 2 都有衝突的 case，做詳細展示

### 輸出（Paper §7.3）
- Propagation matrix（hop k 對 hop k+1 的影響）
- 3 個典型 case 展示「獨立處理」vs「path-aware 處理」的差距
- 數字支持「multi-hop 不是 single-hop 加總」

### 工作量
- ~10 hours

---

## §H.4 Type 4: 我們方法的 Failure Case（誠實節）

### 目的
誠實列出我們仍失敗的 case，提升 paper credibility。

### Annotation 方法
1. 從我們方法 D-Fair-2 的 failure case pool（end-to-end 答錯的 query）
2. Manual annotate 失敗原因
3. 分類為下列預期類別

### 預期類別
- **A. 衝突分組失敗**：LLM 沒識別出兩個 proposition 在說同一件事
  - Future work：更好的 grouping prompt / fine-tune
- **B. 時序資訊不足**：兩個 fact 都很舊或時序模糊
  - Future work：更精細的 timestamp metadata
- **C. 多重衝突**：一個事實有 3+ 版本，分組變難
  - Future work：iterative grouping
- **D. 🆕 Context 已乾淨但 LLM 仍推理錯誤**：retrieval 完美、conflict 解決完美、但下游 LLM 在 vanilla prompt 下還是答錯
  - 這類 case 是 Phase 3 必須處理的，且**直接證明 §4.4 Observation**
  - 若 D 類比例高 → Phase 3 context refinement 有重要 publication value（DC6 重要）
  - 若 D 類比例低 → 我們的 retrieval+filter 已是主要 bottleneck，Phase 3 邊際效益小
  - Future work：context refinement 演算法深化

### 輸出（Paper §7.4）
- Pie chart of failure 類別比例
- 每類 1-2 case
- **特別**：類別 D 的比例決定 Phase 3 工作量與 paper 風格選擇
- 對 future work 的具體 implication

### 重要性
這節是 reviewer credibility 加分項，**且決定 paper 風格**：
- D 類占比高 → Phase 3 是重要 contribution → 方法路線
- D 類占比低 → Phase 3 邊際 → empirical-driven 路線

### 工作量
- ~10 hours

---

## §H.5 整體 Case Study 預算

| Type | 工作量 | 優先級 |
|---|---|---|
| Type 1 (write-time taxonomy) | ~15h | 🔴 必做 |
| Type 2 (LLM prior bias) | ~15h | 🔴 必做（DC2 的證據） |
| Type 3 (propagation) | ~10h | 🟡 強建議 |
| Type 4 (our failure) | ~10h | 🔴 必做（credibility） |
| **Total** | **~50h** | |

**建議排程**：
- Type 1 / Type 4：從現有實驗 log 撈 case，邊跑邊累積
- Type 2 / Type 3：實驗結束後集中 annotate

---

# §I. 🆕 Paper 策略風險評估（empirical-driven 路線）

## §I.1 風險：Paper 風格選擇

某些 reviewer（尤其 ML 場）偏好複雜方法；其他 reviewer 偏好簡單但 insight 深刻的 paper。**我們不該過早鎖定風格**。

**對策**：
- §0.1 寫明風格未鎖死，依方法演進決定
- 等 Phase 3 定型後再選風格：
  - 方法保持簡單 → empirical-driven design paper（投 ACL/EMNLP/NAACL）
  - Phase 3 引入較深設計 → method + empirical analysis 雙重路線（可投 NeurIPS/ICLR）
- 風險於：若 Phase 3 仍很弱，paper 整體缺乏方法新穎性，必須完全靠 empirical insight 撐起
- 引用 Sentence-BERT / ColBERT 等 simple-but-effective 先例作為 fallback

## §I.2 風險：Case study 工作量被低估

預計 ~50 hours，可能高估或低估。

**對策**：
- 邊跑實驗邊累積 case，不集中後做
- Failure case 從必跑的實驗中順便撈
- Advisor 可當第二 annotator

## §I.3 風險：方法定型後可能仍嫌簡單

如果 Phase 3 沒有重要新設計，整個方法可能看起來像 trivial extension。

**對策**：
- §3 Empirical Motivation 必須寫得有 insight 深度
- 每個 design choice 要有「不顯然」的 angle
- 例：「LLM 只分組 + 程式比 timestamp」需要展現「反 Mem0/Zep 的 design philosophy」這個 angle
- **保留 Phase 3 深化的彈性**：如果 D-Fair 實驗顯示 context refinement 有顯著影響，Phase 3 可以引入更複雜設計（如 reasoning verification、context selection 等）
- 風險的 hedge：若方法最終仍簡單，靠 4 類 case study + empirical motivation 撐起 contribution；若方法深化，再決定風格

## §I.4 風險：競爭窗口

T-GRAG / MemoTime / KEDKG 之後可能有人做 implicit version。

**對策**：
- 4-6 個月內投出
- arXiv 早期 preprint 佔位
- 監控 arXiv 每兩週

## §I.5 風險：FC-MH 可能沒有明確 counterfactual subset

若 §H.2 的 counterfactual case 篩選結果太少，Type 2 case study 會 weak。

**對策**：
- A：用 MQUAKE-CF 作為補充 dataset
- B：人工 inject（透明說明）
- C：降級為 robustness analysis
- 提前在 §B.2 確認 dataset 性質

---

# §J. 🆕 Baseline 對齊管理（重要新章節）

> 此節整合 baselines_analysis 調查報告的發現，給出 paper 寫作與口委問答的完整策略。

## §J.1 三方法實作對齊狀況一覽

| 方法 | 我們跑的版本 | 論文-實作對齊度 | 黑/白盒 | 風險等級 |
|---|---|---|---|---|
| Mem0g | MABench bundled v2.x | ⚠️ 論文 §2.2 宣稱 soft invalidate，實作為 hard `DELETE r` | 白盒 | 🟡 中（需 disclosure） |
| Zep | zep_cloud SDK | ✓ 結果可見（`invalid_at`），過程黑盒；Graphiti OSS 對齊論文 | 黑盒 | 🟢 低（已 archive JSON） |
| HippoRAG v2 | MABench bundled | ✓ 自家 official impl | 白盒 | 🟢 低 |
| T-GRAG | 自己 re-implement | ⚠️ 需適配 FC-MH（無 explicit timestamp） | 白盒 | 🟡 中（公平性需論述） |

## §J.2 Paper 內 disclosure 三層策略

### 層級 1：主文（Baselines section，~150 words）
見 narrative §6.5 寫法範例。**核心**：用「we use as representative instances of [our category]」語調，不主動暴露落差。

### 層級 2：Footnote
- mem0g footnote：「The publicly available implementation performs hard deletion. We treat this as a representative instance of destructive write-time methods.」
- Zep footnote：「Evaluated via cloud SDK; backend versions during [date range].」

### 層級 3：Supplementary
- 所有 retrieved JSON archive
- Evaluation timeline
- mem0g commit hash / Zep evaluation date range

## §J.3 口委問答準備清單

### Q1: 「mem0g 你跑的 v2 是 hard delete，論文宣稱 soft invalidate，公平嗎？」

**A1（120 秒回答）**：
> 「我們的核心對比是 write-time vs query-time，不是 destructive vs non-destructive 的次要細節。Hard delete 與 soft invalidate 都是 write-time，都缺乏 query context，所以**都受 A1a vs A1b gap 的影響**。為了完整性，我們也比了 Zep cloud（其可見的 `invalid_at` 顯示 non-destructive），結果與 mem0g **同方向**，證明 write-time 盲點與 destructive/non-destructive 細節無關。
>
> 此外，mem0 upstream v3（2026-04）已完全移除圖記憶（commit a488e190），工業界本身已放棄這個方向，這個 anecdotal evidence 跟我們的論點一致。」

### Q2: 「為什麼 Zep 用 cloud SDK 而非 Graphiti OSS？」

**A2**：
> 「(a) 我們主結果是『方法是否能解 implicit 衝突』，黑盒夠用——測 detection rate / retrieval rate / end-to-end accuracy 都不需要看 internal mechanism。
> (b) 我們已 archive Zep cloud 回傳的所有 JSON 供 reproducibility。
> (c) 如果機制層級分析需要白盒，我們在 supplementary 補 Graphiti v0.29.1 抽樣對比。Graphiti 的核心程式碼（`edge.invalid_at = resolved_edge.valid_at; edge.expired_at = utc_now()`）與論文 §2.2.3 是逐字對應，所以是 valid 的 OSS reference。」

### Q3: 「為什麼派系 A 沒人在 FC-MH 上做實驗？你怎麼確定他們在 FC-MH 上會表現差？」

**A3**：
> 「(a) MemoryAgentBench (Hu et al., 2025) 是新 benchmark（2025）；派系 A 方法多數早於 benchmark；
> (b) MemoryAgentBench 已測多種 SOTA（含 RAG、long-context、commercial memory），所有方法在 CR-MH 都 ≤ 6%；
> (c) 我們的 baseline 不是憑空推測，是把 Zep / Mem0g 實際接上 FC-MH dataset 跑（如 §A.2 表）；
> (d) Detection F1 的 A1a vs A1b gap 進一步證明，這不是『沒人試過』的問題，是『write-time 設計本身的盲點』。」

### Q4: 「你的方法簡單，貢獻在哪？」

**A4**：
> 「我們的 contribution 不在『方法複雜度』，在：
> (a) Problem formulation：將 query-time conflict 切為 explicit / implicit 子問題（§3.2）；
> (b) Diagnostic findings：A1a vs A1b gap、LLM prior bias、multi-hop propagation 三個 empirical observations（§4）；
> (c) Empirically-grounded design：每個 design choice 都對應 observation，非 ad-hoc；
> (d) First method in scenario：第一個在 FC-MH 上突破 6% 上限。
>
> 此外，Phase 3 仍在 active 演進中，方法複雜度可能增加。」

### Q5: 「你怎麼處理 Zep cloud 後端可能更新的問題？」

**A5**：
> 「Paper 明確報告 evaluation date range；所有 Zep 回傳的 JSON 已 archive 在 supplementary material；若 future evaluation 與我們不同，我們的 archive 仍可重現原始實驗。」

### Q6: 「為什麼戰場限縮 KG？非 KG 方法（如 Mem0 non-graph）你沒比？」

**A6**：
> 「(a) Multi-hop reasoning 本質需要 structural relations（HippoRAG / PropRAG paper 已實證）；
> (b) Fine-grained conflict detection 需要 structured units 作 anchor；
> (c) 場域限定是合法的科學選擇（T-GRAG 限 corporate reports、MemoTime 限 TKG、KEDKG 限 editing）；
> (d) Non-KG 延伸是 explicit future work，在 Limitations 標明。」

### Q7: 「T-GRAG 適配 FC-MH 是否 fair？」

**A7**：
> 「我們將 ingestion order 作為 timestamp signal 餵入 T-GRAG。**T-GRAG 的核心機制（Temporal Query Decomposition）對 FC-MH query 不觸發**，因為 FC-MH query 無 explicit time keyword。這個失敗本身是 finding——揭露 explicit-conflict 方法無法處理 implicit 衝突的場景。」

## §J.4 換 Graphiti OSS 的觸發條件

依 baselines_analysis 報告 §4.2 設計：

- **不需要換**：論文 claim 停留在「Zep 在 X% 案例下衝突偵測失敗」
- **必須換**：要 claim「**為什麼**失敗 — 候選邊撈取太窄 / LLM prompt 缺陷 / 時間規則 bug」這類機制層級論點

**目前評估**：我們的論點主要是「write-time 對 implicit 衝突盲」這個**設計層級**的批評，不需要解釋「Zep 內部為什麼漏」。**所以黑盒夠用**。

**保險動作**：在 Baselines section footnote 加一句：「For mechanism-level analysis (Appendix [X]), we additionally evaluate against Graphiti v0.29.1, the official open-source implementation of Zep, on a sampled subset.」——即使最後沒寫 Appendix，也展現你**知道**黑盒的限制。

## §J.5 Reproducibility Checklist

paper 投稿前確認：
- [ ] mem0g commit hash 記錄在 paper（MABench fork 的具體 commit）
- [ ] Zep cloud evaluation date range 記錄
- [ ] HippoRAG v2 version / commit 記錄
- [ ] T-GRAG re-implementation 是否上傳 GitHub
- [ ] 所有 retrieved JSON 整理 archive 為 supplementary
- [ ] Evaluation environment（GPU、LLM 版本、seed）記錄

## §J.6 Discussion 章節的素材（turn limitation into insight）

mem0 工業界放棄圖記憶 = 強力 anecdotal evidence：

> 「Recent industry developments suggest the limitations of write-time conflict mechanisms. The mem0 project, originally pioneering graph-based conflict resolution, **removed its graph memory subsystem entirely in April 2026** (commit a488e190, ~3000 lines removed), pivoting to simpler entity-extraction-based memory. This anecdotal evidence aligns with our empirical finding (§4.1) that write-time mechanisms struggle with implicit conflicts in dynamic conversational memory.」

**這段話把對手實作的「死亡」變成我們論點的旁證**。是 Discussion 章節的好素材。

---

# §K. 🆕 給 advisor 的更新 checklist（這次討論的具體 actions）

排序前 8 項：

1. 🔴 **跑 A1a / A1b 拿到 detection F1 數字**（最緊急——驗證核心 thesis）
2. 🔴 **跑 B1a/b/c 三個 retrieval metrics**（揭露機制層級差異）
3. 🔴 **跑 D-Fair-1/2 拿到 end-to-end 數字**（main result）
4. 🔴 **mem0g vendored hard delete 事實寫進 paper §6.5 footnote**
5. 🔴 **Zep evaluation date range + JSON archive 在 supplementary**
6. 🟡 **跑 D-Fair-3/4/5 測 context format 影響**（§4.4 observation 驗證）
7. 🟡 **§H.4 failure case D 類比例 → 決定 Phase 3 工作量**
8. 🟡 **T-GRAG 適配實驗（C1）跑完**
