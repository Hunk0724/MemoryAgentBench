# FC 衝突解決 — 現況彙整與方法論述(碩論用,2026-06-09)

> **用途**:把目前所有已驗證/待補的結果,串成一份**邏輯自洽、學術嚴謹、可讀**的完整論述,作為碩論主體骨架。配套詳見 [01](01_mem0_fc_setup_and_results.md)(write-time 設定/結果)、[02](02_fc_sh_6k_failure_deepdive.md)/[03](03_fc_sh_32k_failure_deepdive.md)/[04](04_fc_sh_64k_failure_deepdive.md)(逐案 trace)、[05_research_framing](05_research_framing_and_method_draft.md)(框架草稿)、[05_expanded_eval_set](05_expanded_eval_set.md)(擴充集/重建/戰場方法)。
> **標記**:✅ 已驗證 ／ 🔶 部分(需補/單一長度)／ ⬜ 待做 ／ 🩺 純診斷工具(非主結果)。

---

## 0. 一句話主張(收斂版 — 軸是「時機」,非「可逆性」)

> 增量記憶中的**知識衝突 resolution,應從 write-time 延到 query-time**。write-time resolution 是 **query-agnostic、候選僅來自 embedding-local、且不可逆** → 系統性地讓 query 所需版本**檢索不到(H1)、留錯版(H2)或直接摧毀(A4)**,下游檢索/推理都救不回。把 resolution(及對應記憶更新)延到 query-time,以 **query 導向檢索取得正確 slot 的新舊版本、可逆地解決並回寫**,能在弱 backbone(gpt-4o-mini)上大幅救回這類錯誤。
> *範圍*:以 MemoryAgentBench 的 FactConsolidation(FC,反事實覆蓋,recency 政策)作為**受控測試台**驗證此框架;「resolution 隨 query intent 而變」的更強版與真實 messier 衝突列為 future。

---

## 1. 問題定義

### 1.1 場景
長期記憶 agent 把對話歷史**增量**寫入外部記憶庫;同一 (主詞,關係) slot 的新值陸續到來 → 記憶庫同時存在新舊版本。query 進來時,系統須回傳「對該 query 正確」的乾淨 context。

### 1.2 KU vs FC,本研究聚焦 FC
- **KU**(個人資訊更新):LLM 參數知識沒有 → 忠實取用即可。
- **FC**(反事實世界事實覆蓋,如「France 首都」先 Paris 後 Harare,問首都應答 Harare):新值與 LLM 參數知識**相反** → 是隔離「記憶庫衝突處理」最乾淨的壓力測試。FC 政策 = **最大序號(最新)勝**。

### 1.3 為何衝突 resolution 是記憶方法的職責
記憶方法應回傳「忠實於記憶庫當前狀態」的乾淨 context;下游 LLM 是否採信反事實是另一問題(本研究控制掉:用 benchmark 內建 prompt + 比較同 backbone)。

---

## 2. 整體表現(總體 → 細節的第一層)

**FC-SH EM%(官方 100 題)**:
| | 6k | 32k | 64k | 262k | 備註 |
|---|---|---|---|---|---|
| LCA(全 context)| 99 | 96 | 94 | 74 | ✅ gemini;天花板,但 262k 崩 |
| mem0(gemini, L2)| 93 | 94 | 94 | ⬜ | ✅;**強 model 遮蔽失敗** |
| **mem0(gpt-4o-mini, L2 clean)** | **48** | ⬜ | ⬜ | ⬜ | ✅ 6k;**標準 model 直接失敗** |
| **our method(gpt-4o-mini)** | **96** | 🔶 | 🔶 | ⬜ | ✅ 6k(序號版);新 prompt 版/scale 待 |

**讀法**:gemini(強)把 mem0 的失敗遮到 93%;換 benchmark 標準的 **gpt-4o-mini → mem0 直接掉到 48%**(失敗在標準 QA 就可見,**無須構造戰場**)。our method 把它救回 96%。
- 🩺 **擴充 query 集 → 降為診斷工具**(算錯誤模式佔比用 N 大;非頭條)。

---

## 3. 錯誤分類(三桶,界定我們能 claim 的範圍)

把 FC-SH 的錯誤歸到**互斥三桶**:
| 桶 | 定義 | our method 能救? |
|---|---|---|
| **A. write-time 毀損** | 正確版在 ingestion 被毀/錯留(final-store = old_only / neither / both)| ✅ 能(非破壞)|
| **B. 檢索失敗** | 正確版**在 store**,但沒進 top-k | ❌ 不能(且 store 更大可能更糟)— 正交問題 |
| **C. 答題失敗** | 正確版檢索到,LLM 仍答錯(cross-fact / 沒挑最新)| ⚠️ 部分(顯式 resolution 或可幫)|

→ **A 桶才是我們的 claim 範圍**。prototype 48→96 已暗示 A 桶很大(~48/52 可救),殘 ~4% 為 B/C/artifact。
- ⬜ **待做:嚴謹三桶拆解 per-scale(6k/32k/64k)** — 這是碩論核心數字。

---

## 4. 為何只看 cross-chunk(排除 same-chunk)

衝突對依新舊是否落同 chunk 分:
- **same-chunk**:新舊在同一 chunk 被一起抽取 → 共用 ingestion 時間戳 → **屬 extraction/架構層問題**,our method 只給 chunk-order 也無法區分(需 extraction 端額外設計)。**排除**。
- **cross-chunk**:新舊跨 chunk → 有時序可分 → 是「衝突 resolution」真正的戰場。
→ 排除 same-chunk 是為了**乾淨隔離「resolution 時機」這個變量**,非迴避。

---

## 5. write-time resolution 的失敗機制(為何 mem0/zep 這類做不好)

mem0 在 ingestion 每 chunk 用 **update LLM** 對「新 fact 的 embedding-local top-5 候選」做 ADD/UPDATE/DELETE/NONE,**不可逆**。失敗收斂到:
- **R1 候選鍵控錯誤(embedding 按關係模板/實體重疊排序 ≠ 槽位身分)**:
  - **H1-miss**:真舊版被「同關係不同主詞」擠出 top-5 → 沒看到 → 兩版都 ADD(final `both`)。
  - **A4 over-fire**:「同主詞/同受詞不同關係」fact 擠進 top-5 → update LLM 誤判衝突 → **覆蓋摧毀正確版**(final `old_only`/`neither`)。
- **R2 不可逆裁決品質**:
  - **H2-refuse**:舊版在候選卻不 UPDATE(參數知識拒寫反事實)→ 留舊(final `old_only`)。
- **共同根因**:write-time **沒有 query、候選只有 embedding-local、且 commit 不可逆** → 被迫盲裁、選錯永久。

**最終 store 狀態 = QA 真相**(非 awt 逐事件 bucket;A4 可讓 awt-resolved 的對最終 `neither`,見 [05_expanded_eval](05_expanded_eval_set.md) §D4)。

**毀損率(同一批 fact、同檢索,只換 update LLM;cross-chunk 145 對)**:✅
| final-store | gpt-4o-mini | gemini |
|---|---|---|
| old_only | 27 | 2 |
| **neither(新舊全毀)** | **52** | 2 |
| both | 7 | 2 |
| **毀損合計** | **86 / 145 (59%)** | 6 / 145 (4%) |
| 最終記憶數 | 181 | 297 |

→ **頭條:write-time verdict 毀損率 gpt-4o-mini 59% vs gemini 4%**;標準 model 下 mem0 over-delete(store 縮 1/3,52 對新舊全刪)。
- 🔶 **per-scale 趨勢**:gemini 的 neither 隨長度 2→16→47(6k→32k→64k)→ ⬜ gpt-4o-mini per-scale 待補。
- **zep 等同流派**:同屬 write-time 不可逆裁決 → 預期同病(⬜ 待補 zep 數據以支撐「流派」claim)。

---

## 6. 我們的方法 — 延後 resolution 到 query-time

### 6.1 設計(三件事,各堵一個機制)
| 機制問題 | 對策 |
|---|---|
| 不可逆毀損 | **非破壞 ingestion**:所有抽取 fact 都 ADD,不 UPDATE/DELETE,帶 ingestion-order metadata |
| 候選 embedding-local(漏舊版,H1)| **query-time 對 query 檢索 top-k** → 取到正確 slot 的新舊版 |
| query-agnostic 盲裁 | **query-time 做 resolution**(知道問哪個 slot)|
| store 無界成長(我們自招的代價)| **query-time 可逆回寫**(被 query 觸碰才 lazy consolidate,版本化/tombstone)|

### 6.2 Prototype 版本
- **v1(最小 ablation,✅ 已跑)**:非破壞 store + 檢索 top-100 + 每條前綴 ingestion-order 序號 + **benchmark 原答題 prompt**(那句「用最大序號」)→ 答。**FC-specific**(靠序號 + recency prompt),用來證明 insight floor。
- **v2(主 prototype,⬜ 待跑)— 控制「只變時機」**:非破壞 store + 檢索 top-k + **沿用 mem0 自己的 update prompt** 在 **query-time** 對 top-k 解衝突 → 乾淨集 → 答。
  - **意義**:prompt 與 mem0 write-time **幾乎相同**,差異只剩**時機 + 候選集**(query 導向 vs embedding-local)。**若 v2 贏 → 直接證明「不是 prompt 更好,是時機更對」**,且**不 FC-specific**(mem0 prompt 是通用衝突處理)。
  - 細節:top-k 標 ingestion-order 餵 update prompt;先**不給 query**(維持與 mem0 一致),「給 query 的 query-aware resolution」當增強。
  - 成本 caveat:query-time 多一次 resolution call(每次只處理 top-k 小集,非 mem0 O(n²) 全清單);量級待測。

### 6.3 與 RAG / LCA 的區別(novelty 定位)
- vs **plain RAG**:RAG 也保留 fact,但**剝時序、不做衝突 resolution** → 靠答題 LLM 瞎猜。我們**保留時序 + 顯式 query-time resolution + 回寫**。
- vs **LCA**:LCA 非破壞但塞**全 context**/query → 成本高、262k 崩(74)。我們用 **retrieval(top-k)→ 低成本可 scale**。

---

## 7. 已有的改善證據(✅ 6k,gpt-4o-mini)

**官方 100**:mem0 48% → our method(v1)**96%**(+48pp),超過 mem0 gemini(93%)、逼近 LCA 天花板(99%)。stale 洩漏 4%。
**戰場逐組救回**:
| mem0 final-store | mem0 EM | prototype EM |
|---|---|---|
| old_only | 0 | **100** |
| neither | 0 | **100** |
| both | 83 | **100** |
| new_only(對照)| 100 | 96(不退步)|

→ **核心 insight 證實**:write-time verdict 是難題(同 gpt-4o-mini 崩 48%)、query-time resolution 是易題(96%)。
- ⬜ **待補**:v2(mem0-prompt 版)數字;32k/64k(scale 是否守住 = 誠實必答);全 OpenAI authentic 版。

---

## 8. 與原 benchmark 設定的差異(透明表)

| 項目 | 原 benchmark 預設 | 我們的設定 | 理由 |
|---|---|---|---|
| extraction prompt | Personal-Info-Organizer | **L2 knowledge-extractor + frozen cache** | 預設對 FC 通用知識**抽 0 fact**;L2 確保完整、凍結確保兩 backbone 同一批 fact(隔離 verdict)|
| chunker | nltk 句子 | **fact-aware(行為單位,512)** | 讓每 fact 落唯一 chunk(same-chunk 標記前提)|
| generation_max_length | 10 | **256** | 預設 10 截斷 → 空輸出 artifact |
| mem0 內部 LLM temp | 0.1 | **0** | 診斷確定性 |
| 答題 temp | 0.7 | **0** | 控制比較乾淨訊號(authentic 表格再用 0.7 多 trial)|
| embedder | OpenAI(gpt-4o-mini 預設)| **text-embedding-004 (Vertex)** ⚠️ | **為隔離(與 gemini 同檢索)**;⬜ **authentic 版應改回 OpenAI embedding** |
| thinking(gemini)| budget=0(對 G3 無效)| minimal | G3 無法全關 |

⚠️ **目前數字(48%/96%)用 Vertex embedding(隔離版)**;benchmark-authentic 主線**應改全 OpenAI 重跑**(⬜)。

---

## 9. 誠實範圍與限制(碩論 limitations)

1. **FC 是受控測試台,非真實 generality**:FC = 模板化 fact + 明確 overwrite + recency 政策。它乾淨隔離「resolution 時機」,但**單靠 FC 不能證明真實世界通用性**;「resolution 隨 query intent 而變」需 messier 場景(future)。
2. **B 桶(檢索 at scale)非我們解的問題**(正交、retrieval 共有);但 mem0 的 consolidation 讓它**更糟且隱形**(毀了正確答案,再好檢索也救不回),我們至少保持可檢索。⬜ **prototype scale 是否守住為必答 empirical**。
3. **cost 只剩方向性 claim**(省掉 write-time update-LLM 呼叫);**量級待在全 OpenAI authentic 設定上量**(先前把慢歸給 update 是錯的,主因是 Vertex embed,已更正)。
4. **store 無界成長**:用 query-time 可逆回寫 + 非破壞 dedup 緩解,但 FC 獨立 query eval 不直接獎勵回寫(其值在 store-size/成本攤銷,需另設情境)。
5. **「流派」claim 需 ≥2 系統**:目前只有 mem0;⬜ 補 zep/mem0g 以支撐「write-time 流派」。

---

## 10. 待補數據清單(優先序)

1. ⬜ **FC-SH 錯誤三桶拆解(A/B/C)per-scale** — 核心數字。
2. ⬜ **prototype v2(mem0-prompt @ query-time)** — 主證據(只變時機)。
3. ⬜ **全 OpenAI authentic 重跑**(mem0 + prototype)— 正統性 + cost。
4. ⬜ **prototype 跑 32k/64k** — scale 是否守住。
5. ⬜ **cost 量化**(mem0 update-LLM tokens vs ours 0)。
6. ⬜ **query-time 回寫** 功能 + 小情境。
7. ⬜(加強)zep/mem0g 同病、gpt-4o-mini LCA 天花板、messier 衝突 generality。
