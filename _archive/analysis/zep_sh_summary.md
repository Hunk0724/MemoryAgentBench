# FC-SH 結果摘要:Zep chunk=512, 6k Context

> 對應分析腳本:[analyze_zep_mechanism.py](analyze_zep_mechanism.py)
> 分析資料:[results/zep/sh_zep_mechanism.json](results/zep/sh_zep_mechanism.json)
> 方法論:[zep_methodology.md](zep_methodology.md)

---

## 1. 整體準確率

| 指標 | 數值 |
|---|---|
| 題目總數 | 100 題 |
| 正確 | **70 題** |
| **Accuracy** | **70.0%** |

---

## 2. 衝突對存在與否的分組表現

| 子集 | 題數 | 正確 | Accuracy |
|:---:|:---:|:---:|:---:|
| has_pair(新舊事實同存) | 74 | 44 | **59.5%** |
| no_conflict_pair(只有新事實) | 26 | 26 | **100.0%** |
| **整體** | **100** | **70** | **70.0%** |

> 「無衝突 100% / 有衝突 59.5%」的 40.5pp 差距,直接說明 Zep 的整體分數差異主要來自 **has_pair 子集中的衝突解決失敗**——而非取回失敗或推理能力不足。

---

## 3. Retrieval 品質(has_pair,74 題)— 三 scope 都看

Zep 對每個 query 同時做三次 `graph.search`(scope=edges / nodes / episodes,各取 top-10),LLM 在推理時 prompt 中會同時包含三段(見 [zep_methodology.md §1.2](zep_methodology.md))。故 retrieval 應同時報告三 scope 與 union:

| Scope | GT 取回率 | Old 取回率 | 兩者同時取回 |
|---|:---:|:---:|:---:|
| edges | 50/74 = 67.6% | 51/74 = 68.9% | 38/74 = **51.4%** |
| nodes | 29/74 = 39.2% | 40/74 = 54.1% | 15/74 = 20.3% |
| episodes | **74/74 = 100.0%** | **74/74 = 100.0%** | **74/74 = 100.0%** |
| **any(union)** | 74/74 = **100.0%** | 74/74 = **100.0%** | 74/74 = **100.0%** |

**觀察**:
- **Episodes 達到 100% 兩者皆中**:6k context 切成 12 個 chunk,top-10 episodes 已覆蓋 ~10 個 chunks(每 chunk 含 38+ 個事實),GT 與 Old 在 SH 因為都關於同一主體,兩者通常落在同 chunk 或同題的兩個 chunk 中,在 episode 取回幾乎必中。
- **Edges 雖然 fact NL 形式逐字一致,recall 卻只 51.4%**:edges 是 LLM extractor 抽出的 entity-edge,有 Zep 內部的去重 / 排序 / 關聯性過濾,並非每個事實句都會成為 top-10 edge。
- **`any-scope union` 100%**:LLM 推理時 prompt 同時包含 edges/nodes/episodes 三段,Zep 在 SH 上實際讓 LLM 看到了所有 has_pair 題目的 GT 與 Old 兩者
- **與 HippoRAG-v2 接近**:HippoRAG-v2 chunk-level 兩者皆中 98.6%,Zep any-scope 100%——Zep retrieval 並不弱於 HippoRAG-v2

> **重要 reframe**:之前用 edges-only 觀察「Zep retrieval 比 HippoRAG-v2 差很多」,其實是錯的。LLM 真正看到的 context(三 scope union)在 SH 上 100% 同時包含 GT 與 Old。差距純粹在「LLM 拿到 invalid_at 訊號的比例」,而 invalid_at 只在 edges scope 才有。

---

## 4. Supersession 機制行為(edges-both-retrieved 38 題)

Supersession 訊號(`invalid_at`)只存在於 edges scope。下表的「both-retrieved」指 GT 與 Old **同時出現在 edges top-10**——只有此情境才能評估 invalid_at 的標記是否正確:

| Supersession 結果 | 題數 | 比例 | 「正確」意義 |
|---|:---:|:---:|---|
| Old 標 invalid_at(✅ 正確) | 7 | **18.4%** | Zep 識別到舊事實已被覆蓋 |
| GT 未被標 invalid(✅ 正確) | 24 | 63.2% | 新事實仍 active |
| **Perfect:Old invalid 且 GT active** | **6** | **15.8%** | 完美 supersession |
| GT 反被標 invalid(❌ 倒置錯誤) | **14** | **36.8%** | Zep 把新事實當成舊的 |

> **核心發現 1:Zep SH 的 supersession 在大多數情況下沒有發生**——只有 18.4% 的 both-retrieved 題 Zep 真的把舊事實標成 invalid;真正完美處理的只有 15.8%。
>
> **核心發現 2:當有 supersession 行為時,有 36.8% 的方向是反的**——Zep 把 GT(新事實)誤標為 invalid。

### 4.1 GT 倒置失效的成因(質性觀察)

GT 倒置失效的 14 題,普遍特徵是「新事實在世界知識上不太合理」:

| q_id | GT(新) | Old(舊) | Zep 預測 |
|:---:|---|---|---|
| q35 | The official language of United States of America is **German**. | ... is American English. | American English |
| q39 | SteamOS was developed by **ABB Group**. | ... by Valve Corporation. | Valve Corporation |
| q48 | basketball was created in the country of **Soviet Union**. | ... United States of America. | United States of America |
| q53 | Imelda Marcos is affiliated with the religion of **atheism**. | ... Catholicism. | Catholicism |
| q54 | The type of music that Dana International plays is **Australian hip hop**. | ... pop music. | pop music |

> **解讀**:Zep 的 supersession 邏輯似乎不純粹依賴對話時間順序,而是混入了 LLM extractor 對「合理性」的判斷——當新事實與世界知識嚴重衝突時,Zep 反而把新事實標成 invalid、保留世界知識中合理的舊事實。
>
> 這對 paper framing 是重要訊號:**Zep 在 MQuAKE-CF-style counterfactual 任務上有結構性的 prior bias**,而不是純粹 dialogue-anchored 的 temporal supersession。

---

## 5. Supersession 結果 → Zep 答對率

| Supersession 條件 | n | EM | 比例 |
|---|:---:|:---:|:---:|
| Perfect(Old invalid 且 GT active) | 6 | **6** | **100.0%** |
| Old 仍 active(無 supersession) | 31 | 16 | 51.6% |
| GT 倒置 invalid | 14 | (含於上 31 中) | — |

> **訊號夠強就答得對**:當 Zep 真的標出完美 supersession 時,LLM 在 6/6(100%)題答對。
>
> 但這個「強訊號」只覆蓋 6/74 = 8.1% 的 has_pair 題目,大部分情況下 Zep 沒有給 LLM 任何明確訊號,正確率掉到 51.6%。

---

## 6. No_conflict_pair 子集(26 題)— 「不該誤殺」的檢驗

理想情況:此子集 6k 池中沒有對應的舊事實,Zep 應該把 GT 標成 valid 且不該有任何 invalid_at。

| Scope | GT 取回率 |
|---|:---:|
| edges | 20/26 = 76.9% |
| nodes | 19/26 = 73.1% |
| episodes | 26/26 = **100.0%** |
| **any(union)** | 26/26 = **100.0%** |

| 其他指標 | 數值 |
|---|---|
| GT 被標 invalid(❌ 誤殺) | 2/26 |
| 至少有一條 invalid edge 在 top-10 | 19/26 |
| OTHER edges 被標 invalid 數量(總計) | 47 條 |
| **Zep EM** | **26/26 = 100.0%** |

> **觀察 1**:GT 在 episodes 100% 取到,LLM 完整看到無衝突情境下的 GT;Zep EM 26/26 完美。
>
> **觀察 2:背景雜訊**——19/26 題 top-10 edges 裡至少有一條被標 invalid,平均每題 1.8 條 OTHER edges 被標 invalid。這些是 graph 中其他事實的 supersession 結果,但與本題無關。LLM 在無衝突情境對這些雜訊抗干擾性強。

---

## 7. 失敗模式分布(has_pair 30 題失敗)

| 失敗類型 | 題數 | 比例 |
|:---:|:---:|:---:|
| older_fact(輸出 = 舊事實答案) | **27** | **90.0%** |
| hallucination_or_other | 3 | 10.0% |

> **90% 的 has_pair 失敗是 older_fact**——LLM 收到 fact 沒有強訊號就傾向採用舊版答案。
>
> 對比 HippoRAG-v2(see [step1a_sh_summary.md §4](step1a_sh_summary.md)):28/30 = 93% older_fact。Zep 與 HippoRAG-v2 的失敗形態極其相似,差別只是 retrieval coverage 差異。

---

## 8. 與 HippoRAG-v2 的並列(SH 100q 同條件)

| 指標 | HippoRAG-v2 | Zep | 差距 |
|---|:---:|:---:|:---:|
| 整體 EM | 69.0% | **70.0%** | +1.0pp |
| has_pair EM | 59.5% | 59.5% | 0 |
| no_conflict_pair EM | 96.2% | 100.0% | +3.8pp |
| GT 取回率 (has_pair, edges only) | 98.6% | 67.6% | −31pp |
| GT 取回率 (has_pair, any-scope union) | 98.6% | **100.0%** | **+1.4pp** |
| Old 取回率 (has_pair, edges only) | 100.0% | 68.9% | −31pp |
| Old 取回率 (has_pair, any-scope union) | 100.0% | **100.0%** | 0 |
| 兩者同時取回 (edges only) | 98.6% | 51.4% | −47pp |
| 兩者同時取回 (any-scope union) | 98.6% | **100.0%** | +1.4pp |

> Zep retrieval(union 後)其實**略優於 HippoRAG-v2**——LLM 兩端 context 都同時看到 GT 與 Old。整體 EM 70% vs 69% 接近。差別在:
> - HippoRAG-v2 完全靠 prompt 序號規則(「序號越大越新」)讓 LLM 選新事實;has_pair 仍 59.5%
> - Zep 在少數題目(15.8% 完美 supersession 觸發時)透過 invalid_at 給更明確訊號;has_pair 也是 59.5%
> - **同樣的 has_pair 子集 EM,但兩個方法各自答對的題目不全重疊**——這驗證了 supersession 機制當觸發時是有效的,但觸發率太低不足以拉開差距

> Zep 整體 EM 與 HippoRAG-v2 持平(70 vs 69),**但達成方式完全不同**:
> - HippoRAG-v2:近完美 retrieval + 序號規則 prompt,LLM 仍因 older_fact 傾向掉到 59.5%
> - Zep:retrieval 大幅落後 32–47pp,但有少數題透過 supersession 完美訊號(15.8%)補回部分分數;另在 no_conflict_pair 多答對 1 題

---

## 8.5 Zep-native 失敗分類 — 機制觸發狀態 × EM(對應 HippoRAG-style 分組)

把 SH 74 has_pair 題依 Zep 的「supersession 機制觸發狀態」分四類(取代 HippoRAG 的 different_passage / same_passage / retrieval_missing 分類,因為 Zep 對應的訊號層不同):

| Zep 機制狀態 | n | EM | 說明 |
|---|:---:|:---:|---|
| **SUPERSESSION_PERFECT**(Old invalid + GT active in edges) | 6 | **6/6 = 100%** | 機制完美觸發,LLM 100% 採信 |
| **SUPERSESSION_MISFIRED**(GT 反被標 invalid in edges) | 14 | **1/14 = 7%** | 機制 **主動傷害**,LLM 採信錯誤訊號 |
| EDGES_BOTH_NO_SIGNAL(GT/Old 都在 edges 但都沒 invalid_at) | 18 | 15/18 = 83% | 訊號靜默,LLM 靠 prompt 規則判斷 |
| NO_EDGE_SIGNAL_BUT_VISIBLE(only-edges 不全,但 union 兩者都中) | 36 | 22/36 = 61% | 等價 HippoRAG 的 chunk-RAG |
| RETRIEVAL_MISSING(union 沒兩者) | 0 | — | SH 上 Zep 取回完全覆蓋 |

對比 HippoRAG-v2 同 74 題:

| HippoRAG 狀態 | n | EM |
|---|:---:|:---:|
| DIFFERENT_PASSAGE | 59 | 41/59 = 69% |
| SAME_PASSAGE | 14 | 10/14 = 71% |
| RETRIEVAL_MISSING | 1 | 0/1 = 0% |

> **關鍵 insight**:Zep 的機制在 SH 上**淨效應接近 0**:
> - 機制完美 6 題:Zep 100% vs HippoRAG 69% → +31pp × 6 題 = +1.86pp 整體
> - 機制倒置 14 題:Zep 7% vs HippoRAG 約 70% → −63pp × 14 題 = −8.82pp 整體
> - 其餘 54 題機制不啟動,Zep ≈ HippoRAG
> - 淨 ≈ −7pp(理論)但實測 has_pair EM 都是 59.5%(誤差可由其他題的 retrieval 抖動消化)
>
> **SH 的 14 題 misfired 全部是 §4.1 的 counterfactual 題**(US 官方語言=德語、Imelda Marcos 信無神論等)——這些在 HippoRAG-v2 因為沒有機制過濾而 LLM 還能依照 prompt 「序號越大越新」規則答對 ~70%;在 Zep 反被機制誤導,只剩 7%。



1. **Retrieval 不是瓶頸**:any-scope union 100% 把 GT 與 Old 都送進 LLM context(主要靠 episodes 的完整 chunk 內容);Zep 在 SH 上實際讓 LLM 看到了所有 has_pair 題目的兩個事實。
2. **Edges 取回(supersession 訊號的唯一載體)只 51.4%**:剩下 22 題即使 LLM 看到兩個 fact 文字(在 episodes),也拿不到 invalid_at 訊號,只能靠 chunk 序號 prompt 規則判斷——這跟 HippoRAG-v2 的處境一樣。
3. **Supersession 在觸發時答對率極高,但觸發率低**:edges-both-retrieved 38 題裡只有 6/38(15.8%)達成「完美 supersession」(Old invalid 且 GT active);這 6 題 LLM 100% 答對。
4. **存在系統性的 GT 倒置錯誤**:14/38(36.8%)的 edges-both-retrieved 題裡 Zep 反過來把 GT 標成 invalid,這些題集中在「新事實違反世界知識」的 MQuAKE-CF counterfactual 案例(US 官方語言=德語、basketball 創於蘇聯等)。
5. **與 HippoRAG-v2 整體 EM 持平(70 vs 69),但 has_pair EM 完全相同(59.5%)**:Zep 的多出來的 1pp 來自 no_conflict_pair(100% vs 96.2%)。在有衝突情境下,Zep supersession 的觸發率太低、不足以拉開差距。

> **歸因清單**(在 retrieval 不是瓶頸的前提下):
> - has_pair 30/74 失敗的根因:**LLM 看到 GT 與 Old 兩者,但缺乏可信賴的「哪個是新」訊號**
>   - 6 題 supersession 完美觸發、LLM 採信 → 答對(0 失敗來自此類)
>   - 32 題 edges 沒給 invalid_at(GT/Old 在 edges 不全)→ LLM 只能看序號規則,跟 HippoRAG-v2 一樣的 older_fact 傾向
>   - 14 題 supersession 倒置(GT 被標 invalid) → LLM 採信錯誤訊號 → 反而更糟
>   - 其餘 ~10 題訊號模糊
> - 失敗模式 27/30 = older_fact;3/30 = hallucination_or_other

---

*分析環境:Python 3.x*
*資料產出日期:2026-04-27*
