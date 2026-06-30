# Zep FC-SH 完整 100 題分析（chunk=512）

> 實驗日期：2026-04-20
> 實驗 setup：Zep chunk_size=512 在 FC-SH 6k 100 題上完整跑完

---

## 0. 超乎預期的核心發現

**Zep chunk=512（70%）≈ HippoRAG-v2 chunk=512（69%）**，has_pair Acc **完全相同 (44/74 = 59.5%)**。

**但更重要的是**：Zep 的**衝突決策機制在 FC 上其實是「雙面刃」**：

| Zep 的衝突處理結果 | 題數 | Zep Acc | HippoRAG Acc | 差距 |
|---|:---:|:---:|:---:|:---:|
| **正確 invalidate 舊事實**（FC 規則生效） | 7 | **86%** | 43% | **+43pp** |
| **錯誤 invalidate 新事實**（FC GT） | 14 | **7%** | 57% | **-50pp** |
| **未 invalidate 任何事實** | 52 | 71% | 62% | +9pp |

**關鍵 insight**：
- Zep 衝突決策**正確時**，Acc 接近 Oracle A 水準（86% vs Oracle A 81%）✨
- Zep 衝突決策**錯誤時**，Acc 崩潰到 7%（比 baseline 差 50pp）
- **錯誤率是正確率的 2 倍**，因此整體淨效應 ≈ 0，Acc 和 HippoRAG-v2 相當

---

## 1. 跨系統 100 題對比

| 系統 | 整體 Acc | has_pair Acc (74) | no_conflict Acc (26) |
|---|:---:|:---:|:---:|
| HippoRAG-v2 chunk=512 | 69% | 44/74 = 59.5% | 25/26 = 96.2% |
| **Zep chunk=512** | **70%** | **44/74 = 59.5%** | **26/26 = 100.0%** |

**表面上 Zep 微幅勝出**，但 has_pair 核心部分完全打平。Zep 唯一贏的是 no_conflict 那 1 題（HippoRAG-v2 有一個 GT 沒被 retrieve 到，Zep 的 episodes 救了這題）。

**重要統計對照組**：HippoRAG-v2 + Oracle A 在 has_pair 上是 **52/64 = 81%**（usable 題目）。

---

## 2. Zep 的衝突偵測統計（100 題 retrieval 跨 1000 edges）

| 指標 | chunk=4096 (10 題) | **chunk=512 (100 題)** |
|---|:---:|:---:|
| Total edges retrieved | 100 | **1000** |
| ACTIVE (invalid=None) | 100 (100%) | **810 (81%)** |
| INVALID (has invalid_at) | 0 (0%) | **190 (19%)** |
| With valid_at set | 0 (0%) | **770 (77%)** |
| Unique invalidated facts | 0 | **48** |

chunk=512 讓 Zep 的衝突偵測機制大量啟動（19% invalidated），與之前 10 題觀察一致。

---

## 3. 衝突決策準確率：**Zep 的 LLM 比隨機猜還差**

交叉比對 48 個被 invalidated 的事實與 FC context，檢查每個決策是否符合「序號大 = 新 = 正確」的 FC 規則：

| 決策類別 | 數量 | 說明 |
|---|:---:|---|
| **正確（invalidated 較小 seq）** | **16** | 符合 FC 規則 |
| **錯誤（invalidated 較大 seq）** | **31** | 違反 FC 規則 |
| 無法判斷（無匹配或無 counterpart） | 1 | — |

**Zep 衝突決策準確率 = 16/47 = 34.0%**（遠低於隨機猜測 50%）

### 3.1 為何準確率這麼低？世界知識偏見的清晰 pattern

觀察 31 個錯誤決策，可以歸納一個規律：

**Zep 的 LLM 以世界知識強度決定是否觸發衝突解決**：
- **世界知識「強烈」的 entity**：Zep 用 world-truth 覆蓋 FC counterfactual（錯）
- **世界知識「薄弱」的 entity**：Zep 退回 ingestion 順序（可能對）

**錯誤決策典型範例**（全部是世界知識強的 entity）：
- `seq=348 basketball→Soviet Union` (FC GT) invalidated, `seq=216 basketball→USA` (world truth) kept
- `seq=326 Rand al'Thor→Ferdowsi` (FC GT) invalidated, `seq=66 Rand al'Thor→Robert Jordan` (world truth) kept
- `seq=346 Bo Ryan→association football` (FC GT) invalidated, `seq=194 Bo Ryan→basketball` (world truth) kept
- `seq=340 Sandy Alderson→association football` (FC GT) invalidated, `seq=215 Sandy Alderson→baseball` (world truth) kept

**正確決策範例**（通常是世界知識較弱的 entity）：
- `seq=81 Carlos Gómez→baseball` invalidated, `seq=405 →basketball` kept（Gómez 不夠有名，LLM 不確定）
- `seq=91 Nobuhiro Watsuki→Rurouni Kenshin` invalidated, `seq=259 →The Fairly OddParents` kept（奇怪地對了，可能 LLM 對 Watsuki 的知識更新至 seq 259）

---

## 4. 衝突決策對 Acc 的實際影響（per-query 分析）

### 74 個 has_pair 題目，按 Zep 的 invalidate 結果分組

| 組別 | 題數 | Zep Acc | HippoRAG Acc | 相對差距 |
|---|:---:|:---:|:---:|:---:|
| **GT 被 invalidate（錯誤決策）** | 14 | **1/14 = 7%** | 8/14 = 57% | **-50pp** |
| **OLD 被 invalidate（正確決策）** | 7 | **6/7 = 86%** | 3/7 = 43% | **+43pp** |
| 兩者都沒 invalidate | 52 | 37/52 = 71% | 32/52 = 62% | +9pp |

### 這張表告訴我們什麼

1. **衝突解決做對時是 Oracle A 級的效果**：86% Acc 直逼 Oracle A 的 81%
2. **衝突解決做錯時完全毀掉 LLM 判斷**：從 57%（HippoRAG baseline）掉到 7%
3. **大多數題目 (52/74)** Zep 沒啟動衝突解決 → 跟 HippoRAG 行為差不多（71% vs 62%）
4. **錯誤與正確決策比例 2:1**（14 vs 7）→ 淨效應接近零，所以總 Acc 等於 HippoRAG

### 為何錯 invalidate 時 Acc 會掉這麼多？

當 GT edge 被標 `invalid_at` 時，LLM 看到的 context 是：
```
- [GT fact] (Date range: ... - <invalid_at timestamp>)  ← 過期標記
- [OLD fact] (Date range: ... - present)                ← 仍有效
```

LLM 解讀：**「過期 = 不該用」→ 選 OLD fact → 答錯**。所以 Zep 的錯誤 invalidate 實際上**強化了錯誤答案**，比完全不 invalidate（兩者並列）更糟。

---

## 5. 核心 insight：Zep 是個「條件機率優劣的黑盒子」

### Zep 的價值取決於 LLM 是否能判對衝突

重新看那三組數字：
- **Zep 衝突判斷對 → 86% (接近 Oracle A)**
- **Zep 衝突判斷錯 → 7%** (崩潰)
- **Zep 不判斷（其實是多數情況）→ 71%** (與 HippoRAG 差不多)

意味著 **「如果我們能讓 Zep 的 LLM 不要有世界知識偏見」**，Zep 就能超越 HippoRAG-v2 + Oracle A。但實際上做不到——因為：
1. LLM 的世界知識無法關掉
2. FC 的 counterfactual 必然觸發世界知識偏見
3. Zep 的 conflict detection 用的是 LLM，所以失敗是結構性的

### 這個實驗真正的研究 insight

**比 Acc 數字更重要**：我們從 Zep 身上看到的是**「LLM 主導衝突解決」這個方法在 counterfactual 任務上的理論上限與實際下限**：
- **理論上限**（做對時）= Oracle A 水準
- **實際下限**（做錯時）= 幾乎全錯
- **實際期望值** ≈ 隨機猜測結果（≈ HippoRAG baseline）

**這驗證了你的研究核心假設：在 counterfactual 衝突任務上，不應依賴 LLM 自動解衝突，而應該用顯式規則（序號、時序標記）或在 retrieval 階段用結構化方式識別衝突對。**

---

## 6. 對 HippoRAG-v2 + Conflict Filter 設計的具體建議

從 Zep 的成功與失敗學到：

### 應該做的 ✓
1. **保留 HippoRAG-v2 的 serial-number passage 輸出**（保住 FC 的顯式時序訊號）
2. **在 retrieval 後做 conflict pair detection**，不依賴 LLM 判斷
3. **用非 LLM 的結構化規則**：e.g., `(subject, predicate) 相同 + object 不同` → 衝突對
4. **保留 newer（較大 seq）**，符合 FC 規則

### 不應該做的 ✗
1. ❌ 不要讓 LLM 判斷「哪個是新事實」（會觸發世界知識偏見，Zep 已證明 34% 準確率）
2. ❌ 不要用「替代語意詞彙」（moved, now）作為衝突線索（FC 事實都是 stative）
3. ❌ 不要依賴 temporal metadata 自動判定（FC 序號不是時間戳）

### 預期 Conflict Filter 的效果
- 若設計得當，應該達到 **Oracle A 的 81%**（SH has_pair）
- 對應 Zep 的「correct invalidation」組別的 86%

---

## 7. 實驗資料總覽

| 檔案 | 說明 |
|---|---|
| `outputs/rag_retrieved/Structure_rag_zep/k_10/factconsolidation_sh_6k/chunksize_512/FULL_100queries.json` | Zep chunk=512 100 題完整結果（含 edges/nodes/episodes/response） |
| `outputs/rag_retrieved/Structure_rag_zep/k_10/factconsolidation_sh_6k/chunksize_4096/PROPER_10queries.json` | Zep chunk=4096 10 題對照 |
| `outputs/gpt-4o-mini-zep/Conflict_Resolution/factconsolidation_sh_6k_...chunk512_results.json` | Zep 原始跑出的 results（但 ingestion wait 不夠，edges 很多是空的） |

---

## 8. 後續實驗建議

### 優先級高
1. **不需要跑 Zep chunk=4096 100 題**：chunk=512 已經告訴我們所有關鍵 pattern
2. **可以跑 FC-MH 100 題 Zep chunk=512**：驗證多跳情境（預期 Zep 多跳會非常差 <10%，因為缺 multi-hop retrieval）
3. **與 HippoRAG-v2 Oracle A 直接對比**：用 Zep 的「correct invalidation」組別（86%）vs Oracle A（81%）做圖表

### 優先級中
4. **Zep fictional-entity 驗證**：把 FC entities 全部替換成虛構名，看 Zep 能否接近 Oracle A
   - 若能 → 證明 world-knowledge bias 是唯一瓶頸
   - 若不能 → Zep 還有其他問題

### 研究 writing
5. **將 Zep 分析整合進 paper draft**：
   - Section: "Why does LLM-based conflict resolution fail on counterfactual tasks"
   - Figure: Zep's 7% / 86% / 71% three-way split
   - Argument: HippoRAG-v2's "no auto-conflict" design is a feature, not a bug
