# Zep on FC-SH Pilot Findings（10 題）

> 實驗日期：2026-04-20
> 目的：實證 Zep 在知識衝突任務上的行為，驗證之前推論的失敗模式

---

## 0. 最終 Acc 與整體觀察

| 設置 | Acc | 題數 |
|---|---|---|
| Zep 原始 pilot（查詢時 Zep 仍在 async 處理） | 30% | 3/10 |
| Zep 完整處理後重跑 inference | **60%** | **6/10** |
| HippoRAG-v2 baseline（同 10 題對照） | TBD | ? |
| HippoRAG-v2 Oracle A（同題） | TBD | ? |

**首要教訓**：Zep 的 async processing 對 FC context 需要 **>5 分鐘**（2 × 4096 tokens），不是我們原設的 90 秒。實驗時必須充分等待。

---

## 1. 實驗設置

| 項目 | 值 |
|---|---|
| Config | `Structure_rag_gpt-4o-mini-zep.yaml`（修改為用 OpenAI） |
| Dataset | `Factconsolidation_sh_6k`（6k context, 455 facts, 100 queries） |
| chunk_size | 4096（2 chunks） |
| retrieve_num | 10 |
| 測試題數 | 10 |
| LLM | gpt-4o-mini（OpenAI，非 Azure） |

---

## 2. 關鍵發現（逐項驗證之前推論）

### 2.1 失敗模式 1 完全成立：**Zep 在 FC context 上完全不偵測衝突**

| 指標 | 結果 |
|---|---|
| Total edges 返回（跨 10 queries） | 100 |
| ACTIVE（`invalid_at = None`） | **100（100%）** |
| INVALID（有 `invalid_at`） | **0（0%）** |
| 有 `valid_at` 設定 | **0（0%）** |

**所有 100 個 edges 的時序 metadata 都是空的**（valid=None, invalid=None）。Zep 的衝突偵測機制完全沒啟動，因為：
- FC context 以兩個大 chunk 餵入（4096 token each）
- 我們先前 Test C 已證實：**同一 ingestion 內的衝突不偵測**
- FC 455 facts 擠在 2 chunks 中，所有衝突對都在 chunk 內

### 2.2 失敗模式 3 完全成立：**序號在 KG 抽取時丟失**

Zep 抽出的 edge 文字範例：
```
"quarterback is associated with the sport of American football."  ← 沒有 "31." 前綴
"quarterback is associated with the sport of Muay Thai."          ← 沒有 "50." 前綴
"Nobuhiro Watsuki is famous for Rurouni Kenshin."                 ← 沒有序號
"Nobuhiro Watsuki is famous for The Fairly OddParents."           ← 沒有序號
```

FC inference prompt 有「序號越大越新越正確」的規則，但 **edges 文字裡沒序號，這條規則失效**。

### 2.3 Zep 回傳的 context 給 LLM 看起來是什麼樣子

以 q7（quarterback → Muay Thai，GT 是 counterfactual）為例，LLM 實際看到的 retrieved_context：

```
FACTS and ENTITIES represent relevant context to the current conversation.

# These are the most relevant facts and their valid date ranges.
# format: FACT (Date range: from - to)

  - quarterback is associated with the sport of American football. (date unknown - present)
  - quarterback is associated with the sport of Muay Thai. (date unknown - present)
  - placekicker is associated with the sport of American football. (date unknown - present)
  ...
```

**LLM 看到的時間範圍全都是「(date unknown - present)」**。

→ 對 FC 任務，Zep 提供的時序 metadata 完全是雜訊。LLM 只能靠：
1. Retrieval 順序（semantic similarity 排序）
2. 自己的世界知識

### 2.4 Conflict pair 的 retrieval 表現差異懸殊

| query | GT edge 在 top-10？ | OLD edge 在 top-10？ | LLM Pred | 結果 |
|---|:---:|:---:|---|:---:|
| q0: goaltender → pesäpallo | ❌ | ❌ | Basketball（隨機） | ✗ |
| q1: Nobuhiro → The Fairly OddParents | ❌ | ✅ | Rurouni Kenshin（OLD） | ✗ |
| q2: rugby → India | ❌ | ✅ | England（OLD） | ✗ |
| q5: Marriage of Figaro → Thomas Kyd | ❌ | ❌ | Thomas Kyd | **✓ 運氣** |
| q6: Tunisia → basketball | ❌ | ❌ | basketball | **✓ 運氣** |
| q7: quarterback → Muay Thai | ✅ | ✅ | American football（OLD） | ✗ |
| q8: Japan language → Swedish | ❌ | ❌ | Swedish | **✓ 運氣** |

**關鍵觀察**：
- **3 個正確答案（q5, q6, q8）全部發生在「兩個 edge 都沒被 retrieve 到」的情況**
- 但 LLM 仍答對 counterfactual，這怎麼可能？→ **episodes（原文 chunk）包含了答案，LLM 從原文推斷**

### 2.5 q7 的「致命失敗」：兩個 edges 都被 retrieve，但 LLM 選錯

q7 是唯一**衝突對兩個 edge 都在 top-10** 的案例：

```
rank 1: quarterback is associated with the sport of American football.  ← OLD (rank 1)
rank 2: quarterback is associated with the sport of Muay Thai.          ← NEW (GT)
rank 3: placekicker...
...
LLM Pred: American football  ← 選了 rank 1（OLD）
```

**失敗原因**：
- 兩個 edge 的時序 metadata 都是「(date unknown - present)」，無區分
- LLM 默認以 rank 順序判斷重要性
- American football 作為世界真相，語意 embedding 可能更符合「quarterback sport」的語意中心
- **沒有任何線索告訴 LLM Muay Thai 是 counterfactual 版本**

### 2.6 為何 q5/q6/q8 能答對？

這三題的衝突對 edge 都**沒被 retrieve 進 top-10**，但答案仍然對：

- **q5 (Marriage of Figaro → Thomas Kyd)**：episodes 裡可能有「X. The author of The Marriage of Figaro is Thomas Kyd.」原文，LLM 從 episodes 回答
- **q6 (Tunisia → basketball)**：同樣可能從 episode 原文抓到
- **q8 (Japan language → Swedish)**：同樣

→ **當 edges 失效時，episodes（原文保留）反而成了 Zep 回答的唯一可靠來源**
→ 這也意味著 **Zep 在 FC 上的「成功」其實是 degenerated 到 "pure text search over raw chunks"**，KG 沒有發揮作用

---

## 3. Zep 在 FC 上的實際運作模式（事實 vs 之前推論）

| 之前預測的失敗模式 | 實證結果 |
|---|---|
| **Mode 1: Chunk 內衝突不偵測** | ✅ 100% 確認（100/100 edges 無 invalid_at） |
| **Mode 2: 時間戳無區分度** | ✅ 確認（0/100 edges 有 valid_at） |
| **Mode 3: 序號在抽取時丟失** | ✅ 確認（所有 edge fact 都沒序號前綴） |
| **Mode 4: 世界知識偏見** | ⚠️ 部分確認（q1, q2, q7 回答世界真相；但 q6, q8 答對 counterfactual） |

**新發現**：
- Zep 在 FC 上**退化為原文文本檢索**（episodes 成為回答的主要依據）
- **KG 完全沒發揮作用**：edges 無時序、衝突未偵測、retrieval 順序看 embedding 而非時序
- Acc 60% 基本上是 **LLM 從 episode 原文 + 自己世界知識綜合判斷** 的結果

---

## 4. 對比 HippoRAG-v2 的核心差異

| 面向 | HippoRAG-v2 | Zep |
|---|---|---|
| Passage/Edge 是否含序號 | ✅ 完整保留「1. xxx. 2. yyy.」 | ❌ 序號丟失 |
| 是否自動處理衝突 | ❌（保持原樣交給 LLM） | ⚠️ 嘗試處理但對 FC 失效 |
| Inference prompt 有衝突規則 | ✅（序號規則明確） | ❌（只用 Date range） |
| LLM 能否用明確規則 | ✅（序號 → newer） | ❌（date unknown 無區分） |
| 多跳能力 | ✅（PPR + KG traversal） | ⚠️（graph search 單次） |

**HippoRAG-v2 的結構性優勢**：
1. 把原始含序號的 passage 直接給 LLM（資訊完整）
2. Inference prompt 明確規則壓過 LLM 的世界知識偏見
3. 不自動處理衝突，反而避免像 Zep 那樣「幫倒忙」

---

## 5. 對後續研究方向的啟示

### 5.1 跑完整 100 題（FC-SH 全部）是否值得？

**建議跑全 100 題**：

- 10 題樣本太小，60% vs 30% vs HippoRAG-v2 baseline 69% 的統計差異不夠顯著
- 分組分析（has_pair vs no_conflict）需要足夠題數才有意義
- 成本可控：~200 credits for ingestion (已做) + 100 queries × (edges+nodes+episodes 搜尋)≈ 300 credits 
- 需要：完整 100 題的 edge retrieval 品質統計、衝突對 retrieval 成功率、per-question LLM 推理過程分析

### 5.2 FC-MH（多跳）預期

基於 FC-SH 的觀察，預期 FC-MH 在 Zep 上：
- 會比 HippoRAG-v2（baseline 11%）高還是低？**預測略低**
- 原因：Zep `graph.search()` 是單次 vector search，**無 multi-hop traversal**
- FC-MH 需要串接「X 的 Y 是 Z，Z 的 W 是 ...」，Zep 必須一次撈齊所有相關 edges，但每次 query 只取 top-10，無法自動擴展
- 預期 Acc 在 10% 以下

### 5.3 Zep 的「不能解決 FC」是結構性的

從這個 pilot 確認：Zep 在 FC 上失敗不是 prompt 問題，**是設計領域不匹配**：
- Zep 為「真實對話 + 真實時間戳」設計
- FC 用「序號當時間戳」模擬，Zep 的 temporal 機制無法識別
- 即使改 prompt / 加 wait time，失敗模式 1/3 仍無法解決

---

## 6. 下一步行動建議

### 優先級高
1. **跑 HippoRAG-v2 的同 10 題作為對照**，確認 Zep 60% vs HippoRAG-v2 69% 的相對關係
2. **跑完整 Zep FC-SH 100 題**，取得有統計意義的分組 Acc
3. **分析 per-question edge retrieval 品質**：衝突對 retrieval 命中率、rank 分佈

### 優先級中
4. **測試去除世界知識干擾**：把 FC entities 換成虛構名（Zaraxol, Plerion 這類），看 Zep 能否透過 ingestion 順序正確處理
5. **Per-fact ingestion 對比**：逐句餵 FC facts，看衝突偵測是否啟動（預期：仍會踩 Mode 4 世界知識偏見）

### 優先級低
6. FC-MH 10 題驗證多跳預測

---

## 附錄：完整 10 題結果表

| qid | Question（簡化） | GT | Pred | EM | GT在edges? | OLD在edges? |
|---|---|---|---|:---:|:---:|:---:|
| 0 | goaltender sport? | pesäpallo | Basketball | ✗ | ❌ | ❌ |
| 1 | Nobuhiro famous for? | The Fairly OddParents | Rurouni Kenshin | ✗ | ❌ | ✓ |
| 2 | rugby union created? | India | England | ✗ | ❌ | ✓ |
| 3 | Ferdowsi famous for? | Shahnameh | Shahnameh | ✓ | n/a | n/a |
| 4 | Joan Didion educated? | UC Berkeley | UC Berkeley | ✓ | n/a | n/a |
| 5 | Marriage of Figaro author? | Thomas Kyd | Thomas Kyd | ✓ | ❌ | ❌ |
| 6 | Tunisia FB sport? | basketball | basketball | ✓ | ❌ | ❌ |
| 7 | quarterback sport? | Muay Thai | American football | ✗ | **✓** | **✓** |
| 8 | Japan official lang? | Swedish | Swedish | ✓ | ❌ | ❌ |
| 9 | Tucson gov head? | Jonathan Rothschild | Jonathan Rothschild | ✓ | n/a | n/a |

**耐人尋味的諷刺**：q7 是唯一同時 retrieve 到衝突對兩端的題目，卻也是 Zep 最應該能用 KG 結構解決衝突的題目 —— 結果反而答錯。而 q5/q6/q8 根本沒 retrieve 到任何 conflict edge，卻靠 episodes 原文答對。這印證了 **Zep 的 KG 機制在 FC 上完全沒有加分**。
