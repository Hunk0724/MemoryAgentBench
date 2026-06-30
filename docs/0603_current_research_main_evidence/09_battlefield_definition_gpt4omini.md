# 戰場定義與根因分析 — gpt-4o-mini(主軸單一事實來源,2026-06-11)

> **路線鎖定**:gpt-4o-mini(不再使用 gemini 路線)。
> **主軸 research gap**:write-time、query-agnostic、不可逆的**衝突解決**做不好 —— 具體戰場 = **old_only**(最終 vectorDB 只剩舊版、新版不在 = UPDATE 沒成功)。
> **資料來源**:mem0 ingestion 的真實 ADD/UPDATE/DELETE 事件 replay + 每題 top-100 檢索 + candidate_pool / update_decision log。文字比對用精確全文(mem0 ADD 逐字保留)。

---

## 0. 實驗設定(gpt-4o-mini)
| | LCA(Long Context Agent)| mem0 |
|---|---|---|
| 答題 LLM | gpt-4o-mini, temp 0 | gpt-4o-mini, temp 0 |
| 記憶機制 | 無,全 context 直接餵 | write-time:每 chunk 抽 fact→每 new fact 取 top-5 候選→update LLM 判 ADD/UPDATE/DELETE/NONE(不可逆)|
| 內部 update LLM | — | gpt-4o-mini, temp 0, max_tokens 16384 |
| embedder | — | OpenAI text-embedding-3-small (1536d) |
| chunk | 全 context(limit 128k)| 512(fact-aware)|
| extraction | — | L2 凍結 cache(撇除抽取變因)|
| 檢索 | — | top-100 |

---

## 1. 整體表現:mem0 遠低於 LCA 天花板
| 方法 | 6k | 32k | 64k |
|---|---|---|---|
| Long Context LLM(天花板)| 86% | 75% | 62% |
| **mem0** | **37%** | **62%** | **45%** |

## 2. FC-SH Acc 拆成題型(conflict pair vs single fact)
| 歷史長度 | FC-SH Acc(100題)| conflict pair | single fact |
|---|---|---|---|
| 6k | **37%** | 20/74 = 27% | 17/26 = 65% |
| 32k | **62%** | 31/65 = 48% | 31/35 = 89% |
| 64k | **45%** | 24/66 = 36% | 21/34 = 62% |

→ 失敗高度集中在 conflict pair。

---

## 3. 失敗歸因決策樹(conflict-pair)

```
新版正解最終在 vectorDB 裡嗎?
├─ 不在 ── 寫入層失敗
│   ├─ 舊版在 → ★old_only(戰場:UPDATE沒成功,舊版單獨存活)
│   └─ 新舊都不在(neither)
│        ├─ D0 純omission(新舊皆從未ADD)
│        ├─ D1 舊ADD後被刪 + 新從未ADD
│        └─ D2 新ADD後被UPDATE/DELETE摧毀
└─ 在 ── 寫入成功,但下游失敗
    ├─ R 沒被檢索進 top-100(檢索層飽和)
    └─ Z 檢索到了卻挑錯版本(答題/query-time層)
```

### 類別定義(論文可直接用)
每道 conflict-pair 題目對應(舊事實 $f_{old}$,新/正解事實 $f_{new}$,後者為最大序號版本)。replay 寫入事件重建最終 vectorDB,並記錄每題 top-100。EM=0 判為答錯。類別互斥:

- **old_only(戰場)**:$f_{new}\notin$ 最終庫 且 $f_{old}\in$ 最終庫。write-time update 未能讓新版取代舊版,過時版本單獨存活;檢索只能撈到舊版 → 答題必錯。**最明確對應「query-agnostic write-time 衝突解決未成功」**。
- **neither**:$f_{new}\notin$ 且 $f_{old}\notin$ 最終庫。
  - **D0**:兩版本皆從未 ADD(純漏存)。
  - **D1**:$f_{old}$ 曾 ADD 後被移除,$f_{new}$ 從未 ADD。
  - **D2**:$f_{new}$ 曾 ADD 後被後續 UPDATE/DELETE 摧毀(正解被自身寫入流程破壞)。
- **寫入成功但下游失敗**:$f_{new}\in$ 最終庫。
  - **R**:在庫但未進 top-100(檢索飽和)。
  - **Z**:已在 top-100 但模型未挑出最大序號版本(query-time 層)。
- **註**:single-fact 為**題型維度**,非失敗模式;答錯主要為 omission,另計。

---

## 4. 三大類佔「conflict-pair 答錯」的比例(分母 = 54 / 34 / 42)
| 大類 | 6k | 32k | 64k | 趨勢 |
|---|---|---|---|---|
| **★old_only(戰場)** | 11/54 = **20%** | 14/34 = **41%** | 19/42 = **45%** | **隨長度上升** |
| neither(新舊都不在)| 40/54 = 74% | 15/34 = 44% | 14/42 = 33% | 下降 |
| 寫入成功但下游失敗 | 3/54 = 6% | 5/34 = 15% | 9/42 = 21% | 上升 |

細分:
| 子類 | 6k | 32k | 64k |
|---|---|---|---|
| D0 純omission | 21 | 4 | 4 |
| D1 舊刪+新沒進 | 17 | 9 | 7 |
| D2 新被摧毀 | 2 | 2 | 3 |
| R 在庫沒檢到 | 0 | 3 | 7 |
| Z 檢到卻挑錯 | 3 | 2 | 2 |

**主軸 claim(motivation)**:
> **neither 隨對話長度下降、old_only 隨長度上升 → old_only 佔 conflict-pair 錯誤 20%→41%→45%,對話越長越主導。** 這正是記憶系統服務的長歷史情境中,write-time 衝突解決失敗成為主要病灶。

---

## 5. 為什麼聚焦 old_only,而非更大的 omission gap

(本研究刻意不以 omission 為主訴,理由如下)

1. **乾淨隔離變因**:論文主張是 *resolution timing*(write vs query)。old_only 是資訊都在、只差「解決操作本身成功與否」的失敗模式 —— 唯一能單獨隔離「解決時機」的情境。omission 是 storage/recall 失敗,與「怎麼解衝突」無關;若去打它,增益會被解讀成「只是存比較多」而非「query-time 解衝突較好」。
2. **結構 vs artifact**:omission 是 mem0「重生整份清單」update prompt × 弱 model 的實作 artifact(換 pipeline/強 model 即大幅消失);old_only 是 write-time 必須在不知未來 query 下、不可逆決定哪版勝出的**典範結構限制**,mem0/LightMem/Zep 共有。
3. **可泛化**:old_only 是典範層級,聚焦它讓 claim 推廣到整個 write-time 解衝突家族,而非單一系統 bug。
4. **命中尺度**:old_only 隨歷史長度成長,正對應記憶系統存在的長歷史情境。

**方法論後果**:gap = old_only,則評估不能讓 omission 替方法加分;headline 不用 37%,改用「conflict-pair 錯誤中 old_only 佔比 20→45% 且隨長度成長」。

---

## 6. 機制鐵證:omission 100% 出在寫入層(非抽取層)

update LLM 事件分佈(NONE 為重生清單時逐條重發既有記憶):
| 長度 | ADD | NONE | UPDATE | DELETE |
|---|---|---|---|---|
| 6k | 190 | 554 | 57 | 43 |
| 32k | 1382 | 6697 | 384 | 240 |
| 64k | 2498 | 12567 | 763 | 405 |

抽取→儲存漏斗:
| 長度 | 抽取出(唯一)| 實際 ADD | 被丟棄 | 抽取層漏失 |
|---|---|---|---|---|
| 6k | 455 | 190 | **58%** | **0** |
| 32k | 2310 | 1382 | 40% | 0 |
| 64k | 4580 | 2498 | 45% | 0 |

→ 「沒被 ADD」的事實 100% 都「有抽取到、但 update LLM 沒寫進去」(抽取層漏失=0)。**omission 責任完全在 `DEFAULT_UPDATE_MEMORY_PROMPT`。**

---

## 7. old_only 具體案例(6k,供口試說明)

追蹤格式:舊事實在第幾 chunk 被 ADD;對應新事實在第幾 chunk 被處理,**當時舊版就在它的 top-5 候選裡,update LLM 卻給舊版 event=NONE(而非 UPDATE)** → 衝突未解、舊版單獨存活、新版被丟。

| qid | Query | 舊版(serial 小) | 新版/正解(serial 大) | 舊版 ADD | 新版處理 chunk;舊在候選;舊 event | mem0 答 | GT |
|---|---|---|---|---|---|---|---|
| **25** | What is the capital of Tang Empire? | Chang'an | Beaumont | chunk 0 | chunk 4;✅在候選;**NONE** | Chang'an ✗ | Beaumont |
| **96** | (Colin Irwin 國籍) | United Kingdom | Israel | chunk 1 | chunk 11;✅在候選;**NONE** | United Kingdom ✗ | Israel |
| **97** | Who is Walter Chrysler's child? | Walter Percy Chrysler Jr. | Charles Frederick, Duke of Holstein-Gottorp | chunk 1 | chunk 5;✅在候選;**NONE** | Walter Percy Chrysler Jr. ✗ | Charles Frederick... |

**口試重點**:old_only 的 gap 定義在**結果狀態**(最終庫只剩舊、沒有新),與內部成因無關。內部成因是異質的 —— 以 6k 11 題為例,通往 old_only 至少有三條路:(a)舊版作為檢索候選擺在 update LLM 面前、它仍判 NONE 不更新(如 qid=25,最乾淨的代表性機制);(b)舊版在新事實進來時根本沒被檢索成候選,衝突連被看到的機會都沒有;(c)其他。**三條路最終結果相同:舊版留著、新版沒進 → 檢索只撈到舊 → 必錯。** 正因內部成因異質而結果一致,本研究將 gap 釘在穩定可觀測的**結果狀態**,而非單一寫入機制;qid=25 僅作為「即使舊版就在眼前也不更新」的代表性例證。

---

## 8. 評估設計(下一步要跑):聚焦診斷集 = old_only 題 + mem0 原本答對的題

- **old_only 題** → 證明我們的 query-time 非破壞方法**修好**衝突解決失敗(回收率:答對幾 / 11、14、19)。
- **mem0 原本答對的題** → 證明**沒有 regress**(維持率)。
- 乾淨 delta = old_only 回收量;自動排除 neither / single-omission(避免拿 omission 回收灌水)。

**必須誠實說明**:old_only 上的「贏」是**「非破壞保留新版(mem0 丟掉的)+ query-time 在新舊並存時挑最大序號」的套裝**,不是「純解衝突演算法較強」。claim 措辭用「把解決時機 defer 到 query-time(本質含非破壞保留)」。

**(選配)隔離解決本身的貢獻**:新舊都檢索到時,naive 直接丟給 LLM 只有 50–67% 答對;對照我們的 query-time resolution 能拉到多少 → 這段差距即「解決」本身、獨立於「保留」的貢獻。

**定位**:此為 targeted 診斷對照(題目依 mem0 失敗挑選),非 headline benchmark。

---

## 9. Caveats(寫論文前須守)
1. headline 不可用 37%(已改用 old_only 隨長度成長的佔比)。
2. old_only 的增益是「保留+解決」套裝,非純解決。
3. omission 為 mem0 實作 artifact,刻意排除在主訴外(理由見 §5)。
4. 文字比對為精確全文 + 子字串,屬保守估計。
