# FC-MH 推理過程 smoke test:LLM 怎麼看待多跳知識更新?

> 對 6 個 fair-condition 的 MH 題目(GT 在 Zep any-scope union 與 HippoRAG retrieved chunks 都有覆蓋),用診斷 prompt 讓 gpt-4o-mini 暴露推理痕跡,以理解它在 FC-MH 上如何分解、如何處理每 hop 的衝突。
>
> 腳本: [smoke_test_diagnostic.py](smoke_test_diagnostic.py)
> 完整 traces:[results/zep/smoke_test_diagnostic_traces.json](results/zep/smoke_test_diagnostic_traces.json)
> 標的選題:[results/zep/smoke_test_targets.json](results/zep/smoke_test_targets.json)

---

## 1. 診斷 prompt 結構

被診斷 prompt 強制要求 LLM 輸出三個 step:

```
[STEP 1: Decomposition]   把問題拆成 hops,標 (entity, relation)
[STEP 2: Per-hop resolution]
  ## Hop N
  Candidate facts found:  (列出所有匹配的 fact + source + signal)
  Conflict detected:     (yes/no)
  Selected answer:        (採用的值)
  Resolution criterion:   (用了什麼訊號 + 理由)
[STEP 3: Final answer]
```

對每題在 Zep retrieval(edges/nodes/episodes 三段)與 HippoRAG retrieval(10 個 passages)各跑一次,共 12 次 LLM call。

## 2. 觀察到的 7 個 reasoning pattern

### Pattern 1:LLM 確實會做多跳分解 ✅

6/6 題都正確拆出 ordered hops(例如 q1:Hop1 找 spouse → Hop2 找死亡地點)。**多跳分解能力不是瓶頸**。

### Pattern 2:Date_range 訊號清楚時 LLM 會用 ✅

**q6(Twitter CEO)** — Zep 給了兩個矛盾事實:
- "CEO of Twitter is Bernard Arnault. (2026-04-21 - present)"
- "CEO of Twitter is Jack Dorsey. (date unknown - present)"

→ Zep LLM 正確選 Bernard Arnault(France) ✓
→ HippoRAG LLM(無 date 訊號)選 Jack Dorsey(USA) ✗

這是「date_range 訊號可運作」的清楚 demo。

### Pattern 3:LLM 會幻覺自己用了什麼訊號 ⚠️

**q1(Olga of Kiev 死亡地點)** — Zep 給:
- "Olga of Kiev died in the city of Rodez. (2026-04-21T11:11:58 - present)"
- "Olga of Kiev died in the city of Kyiv. (2026-04-21T11:11:55 - 2026-04-21T11:11:58)"  ← invalid_at 設定

LLM 答對 Rodez,但寫的 resolution criterion 是:
> "I selected the fact with the **larger serial number**"

實際上 FACTS section **完全沒有 serial number**!只有 date range。**LLM 不知道自己用了什麼訊號,把 prompt 中提到的「serial number」這個詞 hallucinate 套在 date range 上。**

對 paper:這是「prompt 兩套不一致訊號(date_range vs serial)讓 LLM 混淆」的具體證據。

### Pattern 4:LLM 不會列出所有 candidate ⚠️

**q14(Andrew Carnegie 的國家元首)** — HippoRAG retrieval 確實有兩個版本(filter 確認過 gt_retrieved=True),但 LLM 在 candidate facts 只列了 Elizabeth II,**完全沒提到新版 Emmerson Mnangagwa**。即使 GT 在 context 中,LLM 也可能在自己的 scan 階段漏掉。

這意味著我們以為的「retrieval 完整 → LLM 看得到 → 應該答對」**這個鏈是斷裂的**:retrieval 完整不保證 LLM 真的把每個 candidate 都納入考慮。

### Pattern 5:當 Zep 標 invalid_at,alternative 可能完全不出現在 LLM 的 candidate list ⚠️⚠️

**q3(Tunisia football team 國家首都)** — Zep 給的 retrieval 中明明有兩個版本的 Tunisia 國家(association football / basketball),但 LLM 在 Hop 1 只列了 1 個 candidate("basketball"):

```
Candidate facts found in context:
- Tunisia national football team is associated with the sport of basketball.
  | signal: [2026-04-21T11:11:58.622Z - present]
Conflict detected: no
```

LLM **直接略過 association football 這個 invalid_at 已標記的 alternative,認為「沒衝突」**。這是 Zep 機制的副作用——當 LLM 認為 Zep 已經 pre-filter 過,就不會質疑;但 Zep 的 pre-filter 本身可能 detection 錯誤(這題實際 GT 是 association football,Zep 把 GT 標 invalid 是 misfire),導致 LLM 連懷疑的機會都沒有。

對 paper:**「Zep 的 invalid_at 訊號讓 LLM 信任 Zep 的判斷,但 Zep 本身錯誤時就災難性」** — 跟 SH 14 個 misfired counterfactual 答錯的根因一致。

### Pattern 6:無訊號時 LLM 預設用世界知識或 first-match ⚠️

**q6 HippoRAG 部分** — 兩個 CEO 候選都沒 date 訊號,LLM 寫:
> "Resolution criterion: I selected the most recent fact about Jack Dorsey"

但實際上沒有任何「recency」訊號可參考,**LLM 是用世界知識選的**(Jack Dorsey 在訓練資料中是 Twitter CEO)。FC 的 prompt 規則明明寫「serial number 越大越新」,但 LLM 沒在 chunk 中看到序號(因為 HippoRAG passage 開頭的序號被隔在每段事實列前面,LLM 沒匹配上)。

### Pattern 7:Counterfactual GT 全面失敗 ⚠️

**q4(Blair Walsh 的運動)** — GT 是 "rugby"(MQuAKE counterfactual)。Zep retrieval 含 "placekicker is associated with the sport of rugby" 與世界知識版 "American football"。但**世界知識主導 LLM 判斷**,兩個方法都答 American football。Resolution criterion 寫「the most specific and relevant」,實際是世界知識 prior。

跟 SH 14 個 misfired counterfactual 同類根因。

## 3. 對 RPT 設計的直接啟示

| 觀察 | 對應 RPT 設計 |
|---|---|
| Pattern 4:LLM 不列所有 candidate | RPT 把 [CURRENT] 與 [OUTDATED] 寫成 inline marker,**強制 LLM 看到兩個 candidate 並列** |
| Pattern 5:invalid_at 讓 LLM 太信任 Zep,連 alternative 都不考慮 | RPT 不過濾舊事實,但用 [OUTDATED FACT] 標記+ MUST NOT use 強指令,**讓 LLM 看到衝突存在但被告知不採用舊版** |
| Pattern 3:LLM hallucinate signal | RPT 統一成顯式 marker 詞彙([CURRENT]/[OUTDATED]),**LLM 不需要去 infer 訊號,直接看標籤** |
| Pattern 6:無訊號時走世界知識 | RPT 對 fair-condition 100% 覆蓋,**消除「無訊號」狀態** |

## 4. v2 三條件擴充(2026-04-28)

新跑 [smoke_test_diagnostic_all.py](smoke_test_diagnostic_all.py) — 同 6 題 × 2 方法 × 3 條件:
- **(C) 純原 inference**:original FC `rag_agent` template 完整保留,看 LLM Thought block 自發推理
- **(A) trace-first**:替換 FC template 中段為 (Evidence)(Conflict)(Chain) 結構化指令
- **(B) answer-then-explain**:Pass-1 = (C);Pass-2 帶上 prior answer,要 LLM 事後解釋

完整 traces:[results/zep/smoke_test_all_traces.json](results/zep/smoke_test_all_traces.json)

### 4.1 EM 跨條件穩定性 — 診斷有沒有干擾原 inference?

| qid | gt | hippo orig (100q dataset) | hippo C rerun | hippo A trace-first | zep orig | zep C | zep A |
|---|---|:---:|:---:|:---:|:---:|:---:|:---:|
| 6 | France | ✗ | ✗ | ✗ | ✓ | ✓ | ✓ |
| 4 | rugby | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| 14 | Emmerson Mnangagwa | ✗ | ✗ | ✗ | ✓ | ✓ | ✓ |
| 5 | Baldwin Wallace U. | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| 3 | Russellville | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| 1 | Rodez | ✓ | **✗** ⚠️ | **✗** ⚠️ | ✓ | ✓ | ✓ |
| **TOTAL** | | 1/6 | 0/6 | 0/6 | 3/6 | 3/6 | 3/6 |

> **觀察**:Zep 三條件 EM 完全一致(3/3/3)。HippoRAG 中 q1 從原本 100q dataset 的 ✓ 變成我們 rerun 的 ✗(C 與 A 都是)——可能 reasons:(i) original 100q run 含其他 stochasticity,(ii) 我們 rerun 用 temp=0 而 original 不是;這是後續 paper 寫作時要注意的小 caveat,不影響 finding 整體。
>
> **重要**:**A 條件診斷指令沒有改變 LLM 在這 6 題的最終答案** — 加診斷對 EM 沒污染,可放心當 v2 工具用。

### 4.2 (C) 純原 inference 下 LLM 自發推理 — 不一致的揭露程度

**HippoRAG 有 Thought:/Answer: 結構,LLM 自發寫推理**(q6 example,GT=France):

> "The current CEO of Twitter is stated to be **Jack Dorsey** in one fact, and later it is mentioned that the CEO is **Bernard Arnault**. Since Bernard Arnault has a **larger serial number**, he is the most recent fact. However, **there is no specific mention of his citizenship** in the provided knowledge pool. Therefore, I will refer to the earlier fact about Jack Dorsey, who is a citizen of the United States of America.
>
> Answer: United States of America."

**這段是黃金 case study**——同時暴露了三個關鍵失敗機制:

1. **LLM 確實內化了 serial-number 規則**(主動套用)
2. **LLM 在第二 hop 找不到下游事實時會 bail out 退回舊鏈**——但實際上 "Bernard Arnault is a citizen of France." 確實在 retrieved passages 中(我們驗證過),LLM 漏掉了
3. **這個 bail-out 行為是 paper 上 RPT 的核心對應**:RPT 用 [CURRENT FACT] / [OUTDATED FACT] 標記強制 LLM 不能放棄新鏈走舊鏈

**Zep 的 system prompt 是 "briefly answer",抑制了自發 Thought**(q6 Zep C 直接輸出 "France",沒有任何推理)。所以 Zep 在 (C) 條件下我們完全看不到推理過程——必須靠 (A) 或 (B) 來探查。

### 4.3 (A) vs (B) — trace-first vs post-hoc 差異很大

**q5 Zep (Ceaușescu's partner education,GT=Baldwin Wallace University)** — A 與 B 暴露不同訊息:

**(A) trace-first**:
```
Hop 1 (Nicolae Ceaușescu, partner of):
  Candidates: Elena Ceaușescu / Wilhelm II  ← 兩個都列出
  Conflict: yes
  Selected: Elena Ceaușescu
  Signal: none
  Criterion: fallback (choosing the first mentioned partner)  ← 承認沒訊號隨便選
Hop 2 (Elena, educated at):
  Candidates: University of Bucharest  ← 只列一個
  Final: University of Bucharest
```

**(B) post-hoc**:
```
Hop 2 candidates 列出:
  - Wilhelm II → University of Bonn   ← A 沒列
  - Wilhelm II → Baldwin Wallace U.    ← A 沒列(GT)
Justification: 答 University of Bucharest 因為 Elena 才是相關 partner;
              Wilhelm II 的 university 衝突與本題無關。  ← 事後合理化
```

> **重大 finding**:
> - (A) 顯示 LLM 在 Hop 1 看到兩個 partner、做了 arbitrary 選擇,在 Hop 2 只看 Elena 的 university(沒去找 Wilhelm II 的)
> - (B) 顯示 LLM 在被要求事後解釋時 **能找到** Wilhelm II 的 universities(包括 GT Baldwin Wallace)——但**它選擇用 post-hoc rationalization 把這些 fact 排除為「無關」**
> - 證實 v1 觀察的 Pattern 4(LLM 不會主動列所有 candidate)在 (A) 條件成立,但 LLM **真的有能力** scan 到完整 candidate list,只是不主動做
>
> **對 RPT 設計的對應**:RPT 用 inline marker 強制 candidates 並列在 prompt 文本中,**剝奪 LLM 「不去看」的選項**。

### 4.4 三條件方法論結論

| 條件 | 適合測量 | 缺陷 |
|---|---|---|
| (C) 純原 inference | 原 100q EM 正確再現 + HippoRAG 自發 Thought 中的 implicit reasoning | Zep 的 "briefly answer" 抑制 reasoning,看不到內部 |
| (A) trace-first | 結構化 reasoning 痕跡,可量化 candidate-recall / signal 自述 | 強制結構可能略改變 LLM 行為(但本 6 題 EM 沒變) |
| (B) post-hoc | 純粹保留原 EM,事後得到結構化解釋 | rationalization 風險 — LLM 在事後產生與當下決策不一致的「故事」(q5 直接展示) |

→ paper-rigor 路線:**(C) 為主、(A) 為輔(用 (A) 看 Zep 結構化推理 + 量化 candidate-recall);(B) 結果有 rationalization 風險,適合用來「LLM 自我矛盾」的對比論證**(如 q5 的 (B) 說有看到 Wilhelm II 但 (A) 說沒看到)。

## 5. 擴大樣本到 30 題 × 2 方法 × 2 條件(2026-04-28)

[smoke_test_diagnostic_expanded.py](smoke_test_diagnostic_expanded.py) — 30 題涵蓋 1/2/3/4 conflict-hops (9/14/6/1 distribution),選自 fair-condition 子集(Zep any-scope union 與 HippoRAG retrieval 都覆蓋所有 has_pair hops 的 GT)。共 120 calls。

量化分析:[analyze_smoke_traces.py](analyze_smoke_traces.py) → [results/zep/smoke_traces_quantified.{json,txt}](results/zep/)

### 5.1 H1 驗證 — LLM-side candidate-recall 嚴重低於 retrieval-side

對每題每個 has_pair hop,用 (A) 條件強制 LLM 列出 "Candidates found in context",檢查 GT/Old fact text 是否在 LLM 列出的 candidate string 中(substring match):

**HippoRAG (n=46 has_pair hops,GT/Old 都 100% 在 retrieved passages 中)**:

| LLM 列出狀態 | n / 46 | 比例 |
|---|:---:|:---:|
| GT in candidates | 16 | **34.8%** |
| Old in candidates | 23 | 50.0% |
| **Both** | 15 | **32.6%** |
| Neither | **22** | **47.8%** ⚠️ |

**Zep (n=48)**:
| LLM 列出狀態 | n / 48 | 比例 |
|---|:---:|:---:|
| GT in candidates | 23 | 47.9% |
| Old in candidates | 27 | 56.2% |
| Both | 22 | 45.8% |
| Neither | 20 | 41.7% |

> **H1 強烈成立**:
> - retrieval-side recall 是 **100%**(篩選條件保證)
> - LLM-side candidate-recall 只有 **34.8% (Hippo) / 47.9% (Zep)** for GT
> - **47.8% of HippoRAG hops、41.7% of Zep hops 連 GT 與 Old 都沒列**——LLM 把不相關的 candidate 列上去而 GT/Old 完全被忽略
> - 即使我們用 (A) 強制指令叫它「list ALL matching facts」,LLM 仍漏掉一半以上的對應事實
>
> **這直接證明 user 的假設**:LLM 沒辦法完整對所有 retrieved passages 搜索,有大量「明明在 retrieved passages 中但漏掉」的情況。

### 5.2 LLM 自報的訊號分布 — 「serial-number 規則」採用率約 1/3

對 (A) trace 中 LLM 自報的「Signal used」做關鍵字分類:

| Signal cited | HippoRAG | Zep |
|---|:---:|:---:|
| serial / newest | 15/46 = 33% | 22/48 = 46% |
| date(date-range) | 0 | 0 |
| none / fallback | 28/46 = 61% | 25/48 = 52% |
| other | 3 | 1 |

> **觀察**:
> - HippoRAG 只有 33% 的 hops 自報「used serial number」——大多數 hops LLM 自報「signal: none, criterion: fallback / first-mentioned」
> - Zep 46% 自報用 serial(較高,可能因為 Zep 三 scope 中的 EPISODES 帶序號)、52% 用 fallback
> - **沒有任何 hop 自報用 date-range**——Zep 的 invalid_at 訊號在 LLM 的 自我認知層面**沒被識別**為 conflict-resolution signal
>
> 對應 v1 Pattern 3:LLM 不確定自己用了什麼,常常 hallucinate 訊號名稱。

### 5.3 H3 驗證 — bail-out 語言在 expanded sample 中**罕見**,但揭露更深的問題

對 30 個 HippoRAG (C) Thought block,搜尋 8 個 bail-out 語言模式("no specific mention" / "not mentioned" / "fall back" / "refer to" / etc.):

| Bail-out keyword | Count |
|---|:---:|
| 'no specific mention' | 0 |
| 'not mentioned' | 0 |
| 'no information' | 0 |
| 'fall back' | 0 |
| 'refer to' | 1 |
| 其他 | 0 |

**幾乎沒有 bail-out 語言**——但這不是 H3 不成立,是因為 **LLM 在 (C) 條件下大多根本沒啟動衝突偵測**。實際 (C) Thought block 多半只 1-2 句:

```
q6: "The current CEO of Twitter is mentioned as Jack Dorsey... he is identified
    as a citizen of the United States of America. There is no newer fact
    contradicting this. Answer: United States of America."
    
    ← 完全沒提 Bernard Arnault,LLM 直接用世界知識答了

q14: "...current head of state in the United States of America is Donald Trump."
    ← 完全沒提 Emmerson Mnangagwa(GT),也沒提 Andrew Carnegie 是 UK 公民

q5: "The partner of Nicolae Ceaușescu is Elena Ceaușescu. ...educated at
    University of Bucharest."
    ← 沒提 Wilhelm II 配偶版本(GT)
```

> **比 bail-out 更悲觀的發現**:LLM 在原 inference 條件下,**大多數情況連 conflict 候選都沒列出來,直接拿世界知識先驗的版本答了**。bail-out 反而是「至少有看到衝突才放棄」的「相對良好」路徑——這個 expanded sample 顯示連這個都沒發生。
>
> **q6 兩次 run 不一致**:smoke_test_diagnostic_all.py(第一次)的 (C) Thought 寫了 "Bernard Arnault has a larger serial number... However, there is no specific mention of his citizenship... refer to Jack Dorsey"——展示了 bail-out。但 expanded run(第二次)同題同 prompt 同 temp=0,寫成 "Jack Dorsey... is a citizen of USA. There is no newer fact contradicting this."——完全沒看 Bernard Arnault。
>
> **這反映 OpenAI gpt-4o-mini 在 temp=0 仍有 nondeterminism**(已知 API 限制),不同次 run 的推理路徑可能差很大。

### 5.4 H2 觀察 — LLM 列出 GT 但仍答錯的比例

| 方法 | 答錯題目中 hop's candidates 含 GT 的題數 |
|---|:---:|
| HippoRAG | 14 (out of 30 wrong) |
| Zep | 14 (out of 22 wrong = 64%) |

> **約 47% (Hippo) / 64% (Zep) 答錯題目中,LLM 至少有一個 hop 列出了 GT,但最終仍答 Old**。
>
> 這對 H2(counterfactual GT 不去看)有部分支持但不能直接證實——可能 LLM 看到了 GT 但因為其他 signal(none / fallback)導致選 Old;也可能因為其他 hop 的 GT 漏掉造成鏈路斷裂。
>
> 要確切驗證 H2(counterfactual 因素),需要把 30 題的 GT 標 "world-knowledge-aligned" vs "counterfactual" 兩類,看哪類更容易被 LLM 跳過——這是後續可做的。

### 5.5 EM perturbation 跨條件

| 方法 | original 100q | rerun (C) | rerun (A) |
|---|:---:|:---:|:---:|
| HippoRAG | 4/30 | **2/30** | **0/30** |
| Zep | 9/30 | 9/30 | 8/30 |

> Zep 三條件 EM 接近 byte-equal(9/9/8),A 條件診斷指令對 Zep 沒污染。
>
> HippoRAG 的 rerun (C) 比 original 少 2 題,rerun (A) 跌到 0——可能原因:
> 1. **gpt-4o-mini temp=0 nondeterminism**(同 prompt 不同 run 結果不同,如 §5.3 q6 所示)
> 2. **A 條件診斷格式與 HippoRAG 原 Thought:/Answer: 結構衝突**——LLM 被迫跑診斷格式,Thought 結構推理品質下降
> 3. **prompt byte-level 差異**——我們重建的 FC_ORIG 與 original hippo_data 的 query 可能有空白差異
>
> 這個 perturbation 對 paper rigor 是個 caveat:**(A) 條件雖然 expose reasoning,但會傷害 HippoRAG 的 EM**——做大規模 trace 分析時要分開報告 EM 與 trace 品質。

### 5.6 對 user 三假設的最終結論

| 假設 | 結論 | 強度 | 證據 |
|---|---|:---:|---|
| **H1 LLM 漏抓 retrieved passages** | ✅ 強烈成立 | 強 | LLM-side GT recall 35% (Hippo) / 48% (Zep) vs retrieval-side 100%;47.8% 與 41.7% 的 hops 連 GT/Old 都沒列 |
| **H2 counterfactual 不去看** | 🟡 部分支持 | 中 | 47% / 64% 答錯題有列出 GT 但仍選 Old;但無法分離 counterfactual 因素 vs 訊號不足因素 |
| **H3 找不到下一 hop 退回舊鏈** | 🟡 觀察到但罕見 | 弱 | bail-out 語言 0/30;更悲觀的觀察是 LLM 在 (C) 多半連 conflict 都沒啟動,直接用世界知識 |

> **user 的判斷正確**:**最重要的是先讓 LLM 抓到 query 所需的事實**——retrieval 完整不代表 LLM 看到,LLM 漏抓是 FC-MH 的核心瓶頸之一。
>
> 多跳推理本身(chain propagation)可能不是主要問題——LLM 連第一 hop 的 candidates 都列不全,後續 chain 自然崩盤。**RPT 的 inline marker 直接強制 candidates 並列在 prompt 文字層,剝奪 LLM 「不去看」的選項**——這是 paper 的核心 design 動機。

## 6. 接下來可以做的(根據 user 提的逐步驗證路線)

1. **擴大 smoke test**:從 6 → 30+ 題,涵蓋 ALL_PERFECT / NO_SIGNAL / MISFIRED / RETRIEVAL_MISSING 五類各 6 題,觀察各類 reasoning pattern 的穩定性
2. **量化「LLM 列出的 candidates 是否完整」**:對每題 LLM 輸出的候選 list,自動比對 retrieval 中實際存在的所有 has_pair 候選,計算 LLM 的 candidate-recall(類似 retrieval recall 但是 LLM-side)
3. **量化「LLM 自稱用了什麼訊號 vs 實際 prompt 提供的訊號」**:抓出 hallucinate signal 的比例
4. **整合診斷 prompt 進主流程**:對 100 題 MH × 4 方法(Zep, HippoRAG, RPT-min, RPT)各跑一次帶診斷 prompt 的 inference,把 reasoning trace 入庫,做大規模統計
5. **對比 RPT 是否真的解掉 Pattern 5(LLM 不質疑 Zep 預判)**:在 RPT 的 [CURRENT]/[OUTDATED] 標記下,LLM 是否會在 candidates 列表都列出來

---

*分析環境:gpt-4o-mini, temperature=0*
*資料產出日期:2026-04-28*
