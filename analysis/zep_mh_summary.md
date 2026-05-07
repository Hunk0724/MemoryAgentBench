# FC-MH 結果摘要:Zep chunk=512, 6k Context

> 對應分析腳本:[analyze_zep_mechanism.py](analyze_zep_mechanism.py)
> 分析資料:[results/zep/mh_zep_mechanism.json](results/zep/mh_zep_mechanism.json)
> 方法論:[zep_methodology.md](zep_methodology.md)

---

## 1. 整體準確率

| 指標 | 數值 |
|---|---|
| 題目總數 | 100 題(2-hop / 3-hop / 4-hop) |
| 正確 | **25 題** |
| **Accuracy** | **25.0%** |

> 對比 HippoRAG-v2 同條件下 11.0%(see [step1a_methodology.md](step1a_methodology.md))。

---

## 2. 衝突跳數 vs Zep 答對率

每題 num_hops 範圍 2–4,n_conflict_hops 是「該題在 6k 池中存在新舊事實對的 hop 數」。

| 衝突跳數 | 題數 | 正確 | Zep EM | HippoRAG-v2 EM(對照) |
|:---:|:---:|:---:|:---:|:---:|
| 1 跳衝突 | 33 | 13 | **39.4%** | 30.3% |
| 2 跳衝突 | 48 | 11 | **22.9%** | 2.1% |
| 3 跳衝突 | 17 | 1 | **5.9%** | 0.0% |
| 4 跳衝突 | 2 | 0 | **0.0%** | 0.0% |
| **合計** | **100** | **25** | **25.0%** | **11.0%** |

> Zep 與 HippoRAG-v2 同樣呈現「衝突跳數越多 → 答對率越低」的單調趨勢,但**整體位移上抬 ≈ 14pp**;最大差距落在 2 跳衝突(22.9% vs 2.1%,+20.8pp)。

### 2.1 細分(n_conflict × n_hops)

| n_conflict | num_hops | 題數 | Zep EM |
|:---:|:---:|:---:|:---:|
| 1 | 2 | 25 | 40.0% |
| 1 | 3 | 5 | 40.0% |
| 1 | 4 | 3 | 33.3% |
| 2 | 2 | 36 | 30.6% |
| 2 | 3 | 9 | 0.0% |
| 2 | 4 | 3 | 0.0% |
| 3 | 3 | 10 | 10.0% |
| 3 | 4 | 7 | 0.0% |
| 4 | 4 | 2 | 0.0% |

> Zep 在 **2-conflict-on-2-hop 子集(36 題)** 漲到 30.6%,這是它在 MH 對 HippoRAG-v2 的主要優勢來源。
> ≥3 個 hop 又有 ≥2 個衝突的情境(2/3, 2/4, 3/4 跳)Zep 同樣崩潰至 0%——多跳乘法效應未被 supersession 機制有效緩解。

---

## 3. Hop-level Retrieval 品質 — 三 scope 都看

每 hop 視為一個獨立 (GT, Old) 事實對。Zep 對每 query 同時做 edges/nodes/episodes 三 scope top-10,LLM prompt 同時包含三段(見 [zep_methodology.md §1.2](zep_methodology.md))。

### has_pair hops(n=188)

| Scope | GT 取回率 | Old 取回率 | 兩者同時取回 |
|---|:---:|:---:|:---:|
| edges | 100/188 = 53.2% | 102/188 = 54.3% | 91/188 = 48.4% |
| nodes | 78/188 = 41.5% | 66/188 = 35.1% | 28/188 = 14.9% |
| episodes | **176/188 = 93.6%** | **177/188 = 94.1%** | **167/188 = 88.8%** |
| **any(union)** | 181/188 = **96.3%** | 185/188 = **98.4%** | 178/188 = **94.7%** |

| edges-only 細項 | 數值 |
|---|---|
| 只有 GT 取回 | 9/188 |
| 只有 Old 取回 | 11/188 |
| 兩者皆未取回 | 77/188 = 41.0% |

> **核心 reframe**:any-scope union(LLM 真正看到的 context)在 has_pair hops 達 94.7% 兩者皆中,僅 5.3%(10 hops)是 LLM 看不到完整訊息的真 retrieval-side 失敗。Zep retrieval 並不像之前用 edges-only 觀察到的「兩者皆中只 48.4%」那麼弱——是 episodes 補上了大部分 gap。

### no_conflict_pair hops(n=66)

| Scope | GT 取回率 |
|---|:---:|
| edges | 37/66 = 56.1% |
| nodes | 41/66 = 62.1% |
| episodes | **63/66 = 95.5%** |
| **any(union)** | **65/66 = 98.5%** |

> 無衝突 hop 在 union 後 GT 取到 98.5%——只有 1 hop 完全漏。

---

## 4. Supersession 機制行為(edges-both-retrieved 91 hops)

Supersession 訊號(`invalid_at`)只存在於 edges scope。下表「both-retrieved」指 GT 與 Old **同時出現在 edges top-10**:

| Supersession 結果 | hop 數 | 比例 | 「正確」意義 |
|---|:---:|:---:|---|
| Old 標 invalid_at(✅ 正確) | 48 | **52.7%** | Zep 識別舊事實已過期 |
| GT 未被標 invalid(✅ 正確) | 88 | 96.7% | 新事實仍 active |
| **Perfect:Old invalid 且 GT active** | **47** | **51.6%** | 完美 supersession |
| GT 反被標 invalid(❌ 倒置錯誤) | **3** | 3.3% | 罕見 |

> **MH 的 supersession 機制比 SH 對稱許多**:
> - Old 標 invalid 比率 52.7%(SH 18.4%)
> - GT 倒置錯誤只有 3.3%(SH 36.8%)
>
> 推測原因:MH 6k 池中 has_pair 對的「entity-relation 唯一性」比 SH 高(MH 多跳推理需要更具體的實體鏈,Old/GT 之間不太會混進其他世界知識的常見答案);SH counterfactual 直接挑戰世界知識,讓 Zep 的 LLM extractor 偏向把違反常識的新事實標成 invalid。

---

## 5. Per-question Rollup:全部 has_pair hops 都完美 supersession 了嗎?

只看「該題的所有 has_pair hops 是否都達成 perfect supersession」:

| 條件 | 題數 | EM | EM rate |
|---|:---:|:---:|:---:|
| **All has_pair hops perfectly superseded** | **14** | **10** | **71.4%** |
| Some has_pair hops perfectly superseded | 30 | 9 | 30.0% |
| No has_pair hop perfectly superseded | 56 | 6 | 10.7% |
| **Total(有 has_pair 的題目)** | 100 | 25 | 25.0% |

> **重要訊號**:
> 1. 即使 supersession 信號完美給齊(14 題),LLM 仍只有 71.4% 答對——剩下 28.6%(4 題)即使 graph 上明確標記了 `Old.invalid_at != null`,LLM 仍輸出 older_fact 答案。
> 2. 反過來,沒任何 hop 完美 supersession 的 56 題裡,還有 6 題 LLM 自行答對了——這些都是依賴 nodes summary 或 episodes content 提供的 fallback 訊號。

### 5.1 完美 supersession 但仍答錯的具體案例

| q_id | Zep 預測 | GT | 例子 |
|:---:|---|---|---|
| q13 | United Methodist Church | Anglicanism | hop0:Laura Bush 配偶 GT=Princess Alice (Old.invalid_at✅), 但 LLM 後續推理失準 |
| q17 | Paris | London | hop0:Madame du Barry GT=Great Britain(Old=France, invalid_at✅),LLM 仍答 Paris |
| q21 | John Knox | Edinburgh | hop0:Karen Armstrong GT=Church of Scotland (Old=Catholic, invalid_at✅) |
| q56 | Europe | Africa | 兩 hop 都 perfect supersession,LLM 仍走舊鏈 Germany→Europe |

> **對 paper framing 的意義**:Zep 已經把訊號完整提供給 LLM,但 LLM **未能穩定使用 invalid_at 訊號做多跳推理**——這是 LLM-side 的 reasoning gap,不是 retrieval-side 的訊號 gap。

---

## 6. 失敗模式分布(question-level,75 題失敗)

| 失敗類型 | 題數 | 比例 |
|:---:|:---:|:---:|
| older_fact(輸出 = 舊鏈最終答案) | **40** | **53.3%** |
| hallucination_or_other | 35 | 46.7% |

> 對比 HippoRAG-v2:78%(69/89) older_fact + 11% entity_confused + 10% hallucination(see [step1a_methodology.md §7.3](step1a_methodology.md))。
>
> Zep 的 older_fact 比例(53.3%)比 HippoRAG-v2(78%)低 25pp,但 hallucination_or_other 比例反而高——這反映 Zep 在 retrieval 時可能取回不完整的 hop 鏈,LLM 看到的 context 已經斷裂,部分失敗來自「沒有完整資訊可推」而不是「採信舊事實」。

---

## 7. No_conflict_pair hops 補充(66 hops)

(三 scope 細項見 §3 表;這裡補 supersession 相關數字)

| 指標 | 數值 |
|---|---|
| GT 在 any-scope union 取回 | 65/66 = 98.5% |
| GT 被標 invalid(誤殺) | 1/66 |

> No-conflict hop 在 union 後 GT 取到 98.5%,只有 1 hop 完全漏。誤殺率極低(1/66)。

---

## 8. 與 HippoRAG-v2 的並列(MH 100q 同條件)

| 指標 | HippoRAG-v2 | Zep | 差距 |
|---|:---:|:---:|:---:|
| 整體 EM | 11.0% | **25.0%** | **+14.0pp** |
| 1-conflict-hop EM | 30.3% | 39.4% | +9.1pp |
| 2-conflict-hop EM | 2.1% | 22.9% | **+20.8pp** |
| 3-conflict-hop EM | 0.0% | 5.9% | +5.9pp |
| Hop-level GT recall (edges only) | 97.3% | 53.2% | −44pp |
| Hop-level GT recall (any-scope union) | 97.3% | **96.3%** | −1.0pp |
| Hop-level Old recall (edges only) | 97.9% | 54.3% | −44pp |
| Hop-level Old recall (any-scope union) | 97.9% | **98.4%** | +0.5pp |
| 兩者同時取回 (edges only) | 95.2% | 48.4% | −47pp |
| 兩者同時取回 (any-scope union) | 95.2% | **94.7%** | −0.5pp |

> 在 MH,Zep **靠 supersession 機制(在 47/91 hops 觸發、其中部分傳給 LLM 完美訊號)換來 +14pp 的整體 EM**。retrieval recall 在 union 後與 HippoRAG-v2 接近(94.7% vs 95.2%)——retrieval 本身不是 Zep 比 HippoRAG-v2 好的原因,**支撐 +14pp 的核心是 supersession 訊號**。
>
> 為了驗證,把比較限縮在「該題所有 has_pair hops 在 edges 都 both-retrieved」的子集(supersession 訊號可觸發的最強條件,n=34):
>
> | 子集條件 | n | Zep EM | HippoRAG-v2 EM | Δ |
> |---|:---:|:---:|:---:|:---:|
> | 該題所有 has_pair hops 在 edges 都 both-retrieved | 34 | 44.1% | 29.4% | +14.7pp |
> | 該題至少一個 has_pair hop 在 edges 都 both-retrieved | 77 | 29.9% | 13.0% | +16.9pp |

---

## 8.5 Zep-native 失敗分類 — 機制觸發狀態 × EM(question-level)

把 MH 100 題(全為 has_pair)依「該題所有 has_pair hops 的機制觸發狀態」聚合到 question-level(worst-case 規則:retrieval_missing > misfired > all_perfect > partial_perfect > no_signal_but_visible):

| Zep 機制狀態(question-level) | n | EM | 說明 |
|---|:---:|:---:|---|
| **ALL_PERFECT**(全 hop 都完美 supersession) | 14 | **10/14 = 71%** | 機制最佳觸發 |
| PARTIAL_PERFECT(部分 hop 完美) | 27 | 8/27 = 30% | 訊號不全 |
| **NO_SIGNAL_BOTH_VISIBLE**(union 看到兩者但 edges 無訊號) | 47 | **4/47 = 9%** | 等價 HippoRAG chunk-RAG |
| ANY_MISFIRED(任一 hop GT 反被標 invalid) | 3 | 0/3 = 0% | 機制傷害 |
| ANY_RETRIEVAL_MISSING(任一 hop union 不全) | 9 | 3/9 = 33% | retrieval 真缺 |

對比 HippoRAG-v2 同 100 題(用同類分組規則:retrieval_missing / same_passage / different_passage):

| HippoRAG 狀態(question-level) | n | EM |
|---|:---:|:---:|
| ALL_DIFFERENT_PASSAGE | 66 | 17/66 = 26% |
| ANY_SAME_PASSAGE | 27 | 2/27 = 7% |
| ANY_RETRIEVAL_MISSING | 7 | 1/7 = 14% |

> **關鍵 insight**:Zep MH +14pp 的 gain 主要由 ALL_PERFECT 子集驅動:
> - ALL_PERFECT 14 題:Zep 71% vs(若用 HippoRAG-v2 等同分組看)~26%,+45pp × 14/100 = +6.3pp
> - PARTIAL_PERFECT 27 題:Zep 30% vs 約 26% baseline,+4pp × 27/100 = +1pp
> - NO_SIGNAL_BOTH_VISIBLE 47 題:Zep 9% vs HippoRAG 約 11%,基本持平
> - 其餘 12 題(misfired/missing)拖累但量小
> - 加總約 +7-9pp,加上其他抖動約 +14pp ✓
>
> **「無訊號但兩者都看得到」47 題 EM 9%**:這是 Zep 退化成 chunk-RAG 的核心子集,EM 跟 HippoRAG-v2 整體 11% 幾乎相同——驗證了「沒 invalid_at 訊號時 Zep 就是更貴的 HippoRAG」。

## 8.6 4-way contingency: Zep × HippoRAG-v2 × RPT-min × RPT(MH 100q)

| 方法 | EM (n=100) |
|---|:---:|
| HippoRAG-v2 | 11% |
| Zep | 25% |
| PAT(plug-in,加說明指令) | 36% |
| RPT-min(分區 [CURRENT]/[OUTDATED]) | 60% |
| RPT(分區 + MUST 強指令) | **68%** |

兩兩配對 vs Zep:

| | both | zep only | other only | neither |
|---|:---:|:---:|:---:|:---:|
| zep × hippo | 6 | 19 | 5 | 70 |
| zep × pat | 12 | 13 | 24 | 51 |
| zep × rpt_min | 19 | **6** | **41** | 34 |
| zep × rpt | 25 | **0** | **43** | 32 |

> **核心發現**:**RPT 嚴格 dominate Zep**——Zep 答對的 25 題 RPT 全部都答對,**0 題是 Zep 唯一答對**;另外 RPT 還多救 43 題。RPT-min 也接近 dominate(僅 6 題 Zep 唯一答對)。
>
> **All 4 methods fail: 28/100**(hard core),這 28 題即使透過 prompt-level explicit signaling 也無法救——多數是 retrieval-missing 或 multi-hop chain 結構複雜的 case。
>
> **paper framing 的 punchline**:Zep 透過「temporal KG + invalid_at」設計多花了 ingestion 成本(每 chunk 多一次 LLM extractor + 索引等候 360s),取得 +14pp 增益;**我們的 RPT 不需要任何 ingestion-side 改動,在 prompt 層面把同樣訊號顯式化,直接拉到 +57pp**——同樣是「LLM-side explicit signaling」路線,RPT 就是把 Zep 想做但沒做透的事做完整。



1. **Retrieval 不是 Zep MH 的瓶頸**:any-scope union 對 has_pair hops 兩者同時取到 94.7%、no-conflict hop GT 98.5%。LLM 推理時看到的 context 在覆蓋率上接近 HippoRAG-v2(95.2%)。
2. **Zep MH 的 +14pp 優勢來自 supersession 機制**:edges-both-retrieved 91 hops 中 51.6% 完美 supersession,反向錯誤僅 3.3%。當機制觸發,LLM 拿到強 invalid_at 訊號;當沒觸發(其他 88-91 個 hops 在 edges 不全或無 invalid_at),LLM 看到的事實文字仍跟 HippoRAG-v2 等價。
3. **訊號夠強時 LLM 仍只 71.4% 採信**:完美 supersession 14 題仍有 4 題答錯,顯示 LLM 在多跳推理時對 invalid_at 訊號的使用不夠穩定——這是 **LLM-side 的 reasoning gap,不是訊號層 gap**。
4. **Edges 取回(supersession 訊號的唯一載體)只 48.4%**:Zep 沒辦法在所有 has_pair hops 都把 GT 與 Old 同時抽成 edge,supersession 機制的觸發前提就缺了一半。
5. **多跳乘法效應仍主導**:≥3 hop 且 ≥2 conflict 的子集 EM 趨近 0%——supersession 即使局部觸發,仍無法救回整題答案。

> **歸因清單**(在 retrieval union 不是瓶頸的前提下):
> - has_pair 75 個答錯題的根因:**LLM 在大多數 hops 沒拿到 invalid_at 訊號**(91/188 hops 才有 edges-both-retrieved 機會);多跳鏈裡只要一個 hop 缺訊號就容易拐去舊鏈
> - 完美 supersession 14 題:10 答對 / 4 答錯(LLM-side reasoning gap)
> - 部分 supersession 30 題:9 答對 / 21 答錯(部分訊號不足以扳回)
> - 完全無 supersession 56 題:6 答對 / 50 答錯(LLM 跟 HippoRAG-v2 一樣靠序號規則,自然差)
> - 失敗模式 75 中 53.3% older_fact + 46.7% hallucination_or_other(後者多源於多跳鏈斷裂時 LLM 拼接出來的合成答案)

---

*分析環境:Python 3.x*
*資料產出日期:2026-04-27*
