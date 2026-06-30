# 2026-06-01 研究進度報告 — ours vs mem0g(寫給教授看)

> **本次目標**:確認對手(mem0g, ECAI 2025)的對齊;在此對齊下評估「目前研究主張」的初步證據;指出下一步必做的實驗。
> **盤點原則**:每個 claim 配 1-2 個社群標準 metric;先報結果與解讀,再列 caveat 與下一步。
> **限制 disclose**:我們 method 目前數字仍在不同 backbone(preview, temp=0.7),paper 主表的對齊重跑列在 §6 TODO。

---

## §0 對手對齊(關鍵 reproducibility 工作)

**稻草人 = mem0g [Chhikara et al., ECAI 2025]**。理由:mem0g 有 graph 結構,能直接對應我們「多跳 + 衝突偵測」的研究問題;mem0 只有 vector 結構,放在比較鏈中位於 mem0g 的 vector path baseline 位置。

### 0.1 對齊過程
1. **MemoryAgentBench 框架中 mem0g 有 bug**:wrapper 不把 graph path 的記憶回傳給 inference 使用([agent.py:899](../../agent.py#L899) 只取 `["results"]`)。
2. **回溯 mem0 官方 repo**:確認 MABench 內 vendored 的 mem0 = upstream commit `55df395f`(2025-04-09, ECAI 投稿前的最後穩定版本),md5 一致驗證。
3. **修補**:按 mem0 官方 cookbook 的範例 pattern([Choose Vector vs Graph Memory](../baseline_methods/mem0g_reproducibility.md)),把 graph relations 串成 prompt 一部分回傳給 inference。稱為 `Mem0g-prompt-aware`(下文簡稱 mem0g)。
4. **校正後 EM** vs **未校正(MABench-as-is)EM** 在 FC-MH 6k:**66% vs 41%**(25pp 差) — 之前 reproducibility 工作已經 disclose。

### 0.2 統一實驗條件(Plan A)
| 項目 | 值 |
|---|---|
| Backbone LLM | `gemini-3.1-flash-lite` GA (Vertex) |
| Embedder | `text-embedding-004` (Vertex) |
| Chunk size | 512(各方法統一 → 跨方法比較公平)|
| Top-level temperature | 0(deterministic,單 trial 確定可重現)|
| mem0 internal LLM temperature | 0 |

---

## §1 整體表現:EM 隨對話歷史長度退化

### 1.1 Metric 與設定
- **Metric**: M1 EM(per-query exact match,任務標準指標)
- **Setting**: FC-MH(Multi-hop fact consolidation, MABench Conflict Resolution task), n=100 queries
- **Reader**(最終答題 LLM):同一 LLM 跨方法

### 1.2 結果

| Method | MH 6k | MH 32k | MH 64k | 設定 caveat |
|---|---:|---:|---:|---|
| **LCA**(long-context only,no memory module)| 16% | 19% | 12% | Plan A |
| **mem0**(= mem0g 的 vector path)| 52% | 39% | 跑中 | Plan A |
| **mem0g**(prompt-aware)| **66%** | **40%** | 不跑 | Plan A |
| **Ours v2.0.2** | 29-31% | — | — | preview backbone, temp=0.7,**待 Path D 對齊** |

### 1.3 觀察
- **6k → 32k 三個方法都明顯 drop**:LCA 持平、mem0 -13pp、**mem0g -26pp**
- **mem0g 在 6k 明顯領先 mem0(+14pp)**,但 32k 時兩者收斂至 ~40% → **graph 在長 ctx 失去優勢**
- **Ours 目前在 6k 落後 mem0g(31 vs 66)**;這是不對齊 setup 的結果,主表必須等 Path D 對齊重跑

### 1.4 給教授看的 takeaway
> 在「對話歷史增加」這個 axis 上,**最強的 baseline(mem0g)從 66% 掉到 40%**。我們的主張是:這個 drop 並非偶然,而是 mem0g 兩個結構限制(write-time 衝突偵測 + 圖結構不支援多跳檢索)在長 ctx 上的必然結果。後面 §2 §3 用 mechanism metric 拆解這兩個結構限制。

---

## §2 Claim 1:write-time 衝突偵測在長 ctx 失效(母體池過大)

### 2.1 主張
> mem0g 在 ingest 時對「已累積的整庫」判斷衝突。context 越長,新 fact 看到的「既有相似 fact 候選池」越大,LLM 無法精準判矛盾 → 偵測 precision 崩盤。

### 2.2 Metric 設計

| Metric | 定義(直白版)| 為什麼合理 |
|---|---|---|
| **Precision** | 系統 fire detect 事件中,真的對應 GT chain_old 的比例 | 標準分類 metric。Precision 低 = 系統「亂判」 |
| **Recall** | GT chain_old 事實中,有 fire detect 事件的比例 | Recall 低 = 系統「沒看到」 |

- **mem0g 拆兩個 path 分別評估**(本次新做):
  - **L2 (vector path)**:對每 new fact 從向量庫取 top-5 相似 existing fact,LLM 判 ADD/UPDATE/DELETE/NONE
  - **G4 (graph path)**:對每 new fact 抽 entity,從 graph 取 ≤100 個相關 triple,LLM 判 DELETE entity

### 2.3 結果(隨 ctx 長度的變化)

| Path | 指標 | 6k | 32k | 32k vs 6k |
|---|---|---:|---:|---:|
| **mem0g L2(vector)** | precision | 0.98 | **0.52** | **崩 -46pp** |
| | recall | 0.90 | 0.93 | 持平 |
| | UPDATE-content correct | 1.00 | 0.63 | -37pp |
| | total events | 330 | 2199 | 6.7x |
| **mem0g G4(graph)** | precision | 0.96 | **0.17** | **崩 -79pp** |
| | recall | 0.57 | 0.73 | +16pp |
| | total events | 104 | 716 | 6.9x |

### 2.4 解讀(直接回答你的問題:precision 崩但 recall 持平怎麼解釋?)

- **Recall 0.9 持平 = 大多數 GT chain_old 都被 detect 動到** 
  → 因為 chain_new 跟 chain_old 語意非常接近(本來就是同 head entity 不同 tail),top-5 vector search 大概率把 chain_old 撈進候選池。
- **Precision 從 0.98 崩到 0.52 = detect 動作中只有一半是對的**
  → 32k 時 top-5 候選池裡除了真 chain_old,還有 4 個語意接近但不在衝突對中的 fact。LLM 在更長 prompt 下無法精準辨別「真衝突 vs 巧合相似」,**指鹿為馬地把無關 fact 也 UPDATE 掉**。
- **UPDATE-content 從 1.00 跌到 0.63 = 寫進去的新內容也常錯**
  → 同樣是 LLM 看長 prompt 後決策品質下降 — 即使動對 fact,也寫錯內容。
- **G4 precision 0.17 比 L2 0.52 還慘**
  → graph 候選池是 「entity × ≤100 triple」,隨圖規模膨脹,LLM 比 vector 路徑更早崩。

**Mechanism 圖譜**(可以畫):
```
ctx 變長 → store 內 fact 數變多 → top-5/100 候選池更密集 → 語意相似但無關 fact 增加 → 
LLM 在長 prompt 中無法 disambiguate → 對「真衝突」+「語意相似 noise」都 fire UPDATE/DELETE → 
precision 崩 + 寫入內容也錯 → store 被污染 → query 時拉回錯內容 → EM 跌
```

→ **這就是「query-time 衝突偵測」(我們 method)的 motivation**:把判斷時機推遲到 query 時,只對「跟當前 query 真正相關的小候選池(<10 props)」做 verdict,避免長 prompt + 大候選池的 LLM 判斷失準。

### 2.5 我們 method v2.0.2 在同框架下的 detection 表現

| 階段(對應 mem0g 框架)| 對應 mem0g 路徑 | 我們 method 表現 |
|---|---|---|
| **(A) 候選池 recall** =「該被 LLM 看到的 GT chain_old 是否進入候選池」| mem0g L2 top-5 + G4 top-100 entity | Our: chain enumeration top-5 chains → **66%**(180 GT, 118 進池, 62 漏)|
| **(B) Verdict precision** =「LLM 判 superseded 的 prop 是否真為 chain_old」| mem0g LLM 判 ADD/UPDATE/DELETE 的精準度 | Our: **45%**(verdict 判 superseded 中,真為 chain_old 113 / 共 252)|

→ **Caveat**:Our v2.0.2 在 preview backbone + temp=0.7,跟 mem0g(Plan A)setup 不對齊,絕對值不能直接比。但**框架已經對齊**:可以直接看「同樣的指標,長 ctx 下我們是否更 robust」(待 Path D 重跑)。

### 2.6 數據缺口(必須補)
- mem0g 64k / 262k 的 L2 + G4 precision/recall(目前只有 6k + 32k 2 個點,trend 線只能畫 2 點)
- mem0g G4 實際看到的候選池大小 vs ctx 的 instrument(直接驗證「池過大」hypothesis)
- our method 對齊 Plan A 後的 detection 指標

---

## §3 Claim 2:mem0g 圖結構僅支援 1-hop ego-network,多跳結構性失敗

### 3.1 主張
> mem0g graph 檢索 = query entity → 直接鄰居 → BM25 top-5 triple。**僅 1-hop**。多跳推理需要的鏈中段 entity 不會出現在這個 ego-network 裡。

### 3.2 Metric 設計

| Metric | 定義(直白版)| 為什麼合理 |
|---|---|---|
| **B(query-level all-hops retrieved)** | 該題每個 hop(含 no_pair 和 has_pair)的 GT chain_new fact 都在 retrieved memories | per-query binary。LLM 答對的「必要條件」(沒拿到全 hop 素材,推理就斷)|
| **B × n_hops 拆分** | 把 query 按 hop 數(2/3/4)分桶看 B | hop 越多 = 推理鏈越長 = retrieval 壓力越大。**這個 axis 直接量化「結構性多跳能力」** |

### 3.3 結果(mem0g vs 我們 method,by hop count)

**mem0g 6k**(vector path only vs vector + graph union):

| n_hops | n | B(vector only)| B(vec ∪ graph)| **graph 真實貢獻 Δ** |
|---:|---:|---:|---:|---:|
| 2 | 61 | 79% | **80%** | +1pp |
| 3 | 24 | 88% | 88% | 0 |
| 4 | 15 | 60% | 60% | 0 |
| all | 100 | 78% | 79% | **+1pp** |

**mem0g 32k**:

| n_hops | n | B(vector only)| B(vec ∪ graph)| **graph 真實貢獻 Δ** |
|---:|---:|---:|---:|---:|
| 2 | 58 | 31% | **41%** | **+10pp** ⭐ |
| 3 | 26 | 12% | 15% | +4pp |
| **4** | 16 | **0%** | **0%** | **0(graph 救不了 4-hop)** |
| all | 100 | 21% | 28% | +7pp |

### 3.4 解讀
- **mem0g 6k:graph 幾乎沒貢獻**(+1pp)— vector top-100 已經覆蓋大部分 fact(store 才 290 facts)。
- **mem0g 32k:graph 在 2-hop 有 +10pp 貢獻**(直接從 1-hop ego-network 拉到 chain_new)
- **mem0g 32k 4-hop:graph 0%** — **graph 結構性無法支援 4-hop**,即使 1-hop 鄰居有 chain_new,4-hop 鏈中段(第 2-3 跳)不會出現在 ego-network。
- → 直接 empirical support claim 2:**hop 越多 + ctx 越長,mem0g 越無法 retrieve 全 chain_new**。

### 3.5 我們 method 在同框架下的 retrieval(passage-level,6k)

| n_hops | n | B(top-10 passages,純檢索)| B(filter 後保留 passage)|
|---:|---:|---:|---:|
| 2 | 61 | **87%** | 61% |
| 3 | 24 | 83% | 50% |
| 4 | 15 | 53% | 27% |
| all | 100 | **81%** | 53% |

→ **Top-10 passage 純檢索 B = 81%**(對標 mem0g vec∪graph = 79%)
   - 6k 兩方法都接近 ceiling,看不出顯著差異 — caveat:用 ~12 個 chunk 取 10 個本來覆蓋率高
- **Filter 後 B 掉 28pp**(81% → 53%)
   - 這是目前 method 的已知 limitation:rescue chunk 邏輯把含 chain_new 的 passage 也誤刪
   - **下一步 memory output 設計要解這個**

### 3.6 數據缺口(必須補)
- mem0g 64k / 262k 的 B × n_hops(目前 6k+32k,2 個點)
- ours 對齊 Plan A 後的 6k/32k/64k B × n_hops(目前只有 6k preview)
- → 預期:**mem0g 4-hop 在長 ctx 持續 0%,我們 method 因 passage-level + chain enumeration 應該維持 > 0%**(這是 paper 主表的 winning trend)

---

## §3.5 SH 對照 — 證實兩個 mechanism 沿不同 axis 失效(本次新加分析)

我們**追加 SH(single-hop)的同框架分析**,以對照 MH 上看到的退化是否真的源自我們主張的兩個結構原因。SH 跟 MH 唯一差別是「query 需要的 hop 數」(SH=1, MH=2/3/4),其他變數(corpus, retrieval pool, ingestion)完全一致 → **乾淨的 controlled comparison**。

### 結果

| 方向 | 觀察 | 解讀 |
|---|---|---|
| **Detection precision × ctx** | mem0 SH 6k 0.66 → 32k 0.42 / mem0g-pa SH 0.63 → 0.42<br>mem0 MH 6k 0.97 → 32k 0.51 / mem0g-pa MH 0.98 → 0.52 | **SH 跟 MH 都崩**。確認 claim 1 的「ctx 變長 → 候選池過大 → precision 崩」是 **ctx-axis effect**,**與單跳/多跳無關** |
| **Retrieval gt_in_mem × hop count** | mem0/mem0g SH 6k 81-91% → SH 32k 85-86%(穩定)<br>mem0/mem0g MH 6k 80-88% → MH 32k **55-59%**(崩) | **SH 在 32k 還能 retrieve 85%,MH 在 32k 跌到 55-59%**。確認 claim 2 的「多跳結構性失敗」是 **hop-axis effect**,**與 ctx 無關**(structural) |
| **EM × cell** | mem0 SH 6k 92% → 32k 90%(retrieval 穩 → EM 穩)<br>mem0 MH 6k 52% → 32k 39%(retrieval 崩 → EM 崩) | **SH 即使 detection 崩,EM 仍 90%**;**MH retrieval 崩 → EM 必崩**。**「Multi-hop is the real research problem」被 SH 對照證實** |

### 兩個 mechanism 的乾淨分離

```
ctx 變長(write-time pool 大)  →  detection precision 崩 (SH 跟 MH 都崩,但 SH retrieval 穩,EM 不受傷)
hop 數變多(多跳鏈中段 entity 在 query 外) →  retrieval B 崩 (SH 沒這問題,MH 崩,EM 直接受影響)
```

→ **兩個結構限制各自獨立**,各對應一個 axis,構成 paper claim 1 / claim 2 的**雙重支撐**。
→ 我們 method 的兩個 attack 對應這兩個 axis:**query-time 偵測(解 ctx-axis)+ 多跳 chain enumeration(解 hop-axis)**。

---

## §4 整合 — 我們研究主張的初步證據與還缺什麼

| 主張 | 證據完成度 | 缺什麼 |
|---|---|---|
| **Claim 1**(write-time 偵測 → 長 ctx pool 過大)| ✅ L2 precision 6k 0.98 → 32k 0.52<br>✅ G4 precision 6k 0.96 → 32k 0.17<br>✅ Recall 持平 + UPDATE-content drop 一致(機制成立)| 64k+ 的 trend 點;候選池實際大小 instrument |
| **Claim 2**(graph 1-hop ego-network → 4-hop 失敗)| ✅ mem0g 32k 4-hop B = 0%(graph 加進來也 0%)<br>✅ graph 真實貢獻僅 +1pp(6k)/ +7pp(32k)| 64k+ 的 trend;ours 對齊 Plan A 看 ours 是否 4-hop 維持 > 0% |
| **Claim 3**(memory output 設計影響多跳 inference)| ❌ Plan A 沒做 | 全部 — Path A Diagnostic 0 跑 oracle context × 結構化 prompt |

---

## §5 接下來 TODO(優先級)

### 5.1 工程 — 直接讓 ours 跑得對齊
1. **借用 PropRAG 整套 retrieval 元件**(取代自寫 beam,beam L=3 是死穴)
   - 流程:HippoRAG-v2 PPR base + PropRAG `BeamSearchPathFinder`
   - 參數:採用 PropRAG 文獻默認值(focus_top_k=50, beam_width=8, depth=4)
2. **衝突機制設計**:LLM 做語意分組 + timestamp metadata 仲裁方向
   - **避免**:純 LLM 自己猜 recency(prior art Zep bi-temporal 已做過,差異化不夠)
   - **我們的差異化**:時機 = query-time;scope = 單一候選鏈內(<10 props);機制 = LLM 分組 + code 仲裁
3. **Memory output 設計**(2 個 candidate):
   - **(a) Filter design**:用 LLM prompt 從 passage 中移除偵測到的 chain_old
   - **(b) Append design**:不改 top-N passage,額外附「衝突更新列表」一起回傳給 inference LLM
   - **不採用** CoT / Self-RAG 等 inference-side scaffold(社群慣例是只動 memory output,不動 inference loop,以保持公平比較)

### 5.2 數據 — 主表完整化
1. **Path D Audit 3 — Ours 對齊 Plan A 條件重跑**(GA backbone + temp=0 + chunk_size=512)
   - 完成後 §1 表 ours 行才能與 mem0g 直接比
2. **mem0g 64k 的 L2/G4 precision/recall + B**(成本 ~9hr,但 trend 線從 2 點變 3 點)
3. **mem0g G4 候選池大小 instrument**(直接驗證 claim 1 的 mechanism)

### 5.3 分析 — Claim 3 啟動
- Path A Diagnostic 0(spec §11):用 raw 6k context filter chain_old 直接構造 oracle context,測 4 個 scaffold variants(V_baseline / V_A Self-Ask / V_B CoT / V_C CoRe-style)的 EM
- 預期:max Δ ≥ 15pp → memory output 結構化是有效攻擊面 → Approach 3 進場

---

## §6 給教授看的一段話 summary

> 過去 6 個月我們:(1)確認對手 mem0g (ECAI 2025) 的官方實作在 benchmark 中有 wrapper bug 並修補;(2)在統一條件下(GA backbone + temp=0)重新評估 mem0g vs 我們 method 的初步指標。
>
> **核心觀察**:mem0g 在 6k 條件下 EM 66%(主對手強),但在 32k 條件下掉到 40%。我們透過拆解 detection 與 retrieval 兩個 mechanism 指標,確認這個 drop 來自 **mem0g 兩個結構限制**:(a) write-time 衝突偵測在長 ctx 時 LLM 候選池過大,precision 從 0.98 崩到 0.52,寫入內容也錯;(b) graph 檢索僅支援 1-hop ego-network,4-hop 在 32k 時 B=0%,圖也救不了。
>
> **我們 method 目前在不對齊 setup 下(preview backbone)EM 31%,落後 mem0g**。下一步是把 method 對齊 Plan A 條件重跑(工程 1-2 週),預期 mem0g 在 32k+ 失效時,我們的 query-time + 多跳檢索 + 衝突機制能穩住 EM。最終 paper 主表將呈現「6k 略輸 / 32k+ 反超」的 scaling trend,而非單點 EM 比較。

---

**End of progress_report_2026-06-01.md**
