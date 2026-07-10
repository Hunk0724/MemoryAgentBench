# narrative_chain — Experiments 論證鏈(claim → evidence,逐步共筆)

> **這份是什麼**:把 Experiments 章寫成一條「主張 → 該用哪張圖/表 → 觀察 → 對主軸的意義」的骨架。與 [`README.md`](README.md) 的 evidence map 互補:README 說「哪個節點用哪張圖」,本檔說「那張圖要講出哪一句、對主軸貢獻什麼」。paper-ready caption 直接寫在這,body 可 lift。
> **數字一律回引** [`../results/objective_data_consolidated.md`](../results/objective_data_consolidated.md)(canonical)。
> **狀態**:2026-07-07 起筆,**從 §3.1 開始逐步填**(其餘為 stub,待共筆)。

---

## 主軸(一句話貫穿全章)

> **KU 是「需要 query 才判得準、且判錯會毀」的決定。過去派在 write-time(沒有 query、只看前綴、還得改動共享記憶)就對每一筆事實 commit;我們把 KU 延到 query-time——保留全版本、只在被問到時、帶著 query、可回復地解析。**

**先劃清「三派共享、非我方優勢」(誠實)**:① 找候選 recall 隨庫變大而降(write/query 都有)② reader 對乾淨 pool 仍 override(下游共享,受呈現格式調節)③ 抽取品質。→ 我方優勢**精確定位在「找到候選之後、怎麼判」= 有沒有 query**。

**四步鏈 TOC(status)**:Step 1 研究內容[stub] → Step 2 baseline 核心[stub] → **Step 3 experiment[✅ 3.1–3.4 齊]** → 跨 benchmark FC→LongMemEval[🔴 待 LME baselines]。

---

# Step 3 — Experiment 核心

## §3.1 — Observation 1：優勢是「backbone-conditional」,不是固定刷分

**Claim**:ours 相對 write-time KU 派(mem0 / Zep)的優勢**隨 backbone 判斷力變弱而放大、變強而收合**——因為 write-time KU 的品質被 backbone 的 LLM 判斷力綁死(弱 LLM 連合法的 write-time 決策都產不出),而 ours 的**結構 (S,P)+確定性 recency** 提供一個 LLM 弱時仍撐得住的地板。這是**範式性質(paradigm property)**,不是 leaderboard 分數。

**Evidence A — Figure 1｜backbone spectrum @ 6k(6-tier)**
[`../figures/F_backbone_spectrum.png`](../figures/F_backbone_spectrum.png)

> **Figure 1. FC-SH `has_pair` EM across the backbone spectrum @ 6k.**
> *(What)* 固定 6k 長度,三個 method(ours = struct + identity grouping / Zep = decoupled write-time labeling / mem0+unified-extract)橫跨六個 backbone tier(gemma3-1B → 4B → 12B → 27B → gpt-4o-mini → gpt-4.1-mini,弱→強);同一 tier 內抽取 held-fixed,故 tier 內 method 差距為乾淨量(跨 tier 絕對值混抽取品質,故只讀 gap 趨勢)。
> *(Observation)* ours 於**每一個** tier 皆最高。mem0 於 gemma3-1B/4B **歸零**(弱 LLM 無法生合法的 write-time UPDATE 決策),隨 backbone 增強一路爬到 gpt-4.1-mini 的 76%;ours−mem0 的 gap 於弱端最大(4B **+73pp**、mem0=0),收合至 gpt-4.1-mini 的 **+13pp**。Zep 全程 16–62%,從未追上 ours。
> *(Implication)* write-time 派的 KU 品質**被 backbone 判斷力瓶頸**;ours 的結構地板讓它在 LLM 弱時仍站得住 → 優勢是**conditional on backbone、於弱/受限部署 regime 最值錢**(對接 intro §受限部署:on-device gemma、cost-constrained gpt-4o-mini)。
> *(縮寫)* struct = (S,P) structural grouping;EM = exact match;pp = percentage points。

**Evidence B — Table 3.1｜ours vs 兩派 × {4o-mini, 4.1-mini} × 3 長度(誠實揭露:gap 於強端收合甚至反轉)**

| Method | 6k · 4o | 6k · 4.1 | 32k · 4o | 32k · 4.1 | 64k · 4o | 64k · 4.1 |
|:--|--:|--:|--:|--:|--:|--:|
| **ours (main)** | **93** (69/74) | **89** (66/74) | **88** (57/65) | 78 (51/65) | **91** (60/66) | 80 (53/66) |
| (b) mem0+P1 | 46 (34/74) | 76 (56/74) | 38 (25/65) | **82** (53/65) | 52 (34/66) | **83** (55/66) |
| Zep (k=10) | 62 (46/74) | 62 (46/74) | 51 (33/65) | 31 (20/65) | 55 (36/66) | 35 (23/66) |
| **gap = ours − mem0 (pp)** | **+47** | +13 | **+49** | −3 | **+39** | −3 |

> **Table 3.1. `has_pair` EM (%) at the two API tiers across length; gap = ours − mem0+P1.**
> *(What)* 把 Figure 1 的 mid/strong 兩點展開到三個長度。*(Observation)* 於 **gpt-4o-mini(mid)** ours 於**全長度**領先 **+39~+49pp**;升到 **gpt-4.1-mini(strong)** gap 崩塌,且於 **32k/64k 反轉**(mem0 反超 −3pp),ours 僅於 6k 仍領先 +13pp。*(Implication)* **可證偽預測得證**——backbone 夠強時 write-time KU 自己就做得好,架構安全網的邊際價值下降;優勢是**針對弱/中 backbone**,非普適。此表與 Figure 1 搭配:圖給乾淨的弱端故事,表誠實揭露強端收斂/反轉。
> *(caveat)* Zep 4.1-mini strict EM 反降(hedge:同列兩版),另有 sEM 診斷(見 experiment.md §4.3.4 / style_rules §10.3b);此處一律 strict EM。64k 有 D-flag benchmark bug 2/66,影響 ours −1pp。

**讀者會問的兩個問題(先擋)**:
- **「為什麼 Zep 全程都低?」**→ 3.1 只給現象,**為何**在 §3.2/§3.3 答(Zep ~98% PP-Both、多半 additive 沒給時序 → reader 靠 world-prior 猜)。
- **「為什麼 12B 到 99%、之後往強端反而降(95→93→89)?」**→ ① **跨 backbone 絕對值不可直接比**:weak-tier 是 per-backbone gemma 各自抽取,12B 的高分部分反映其抽取貼近 GT surface + matcher 精度 → **thesis 只讀同 backbone 內的 gap,不讀絕對線高低**。② **強端下降 = reader override**:backbone 越強、當 answer LLM 的 world-prior 越強,即使 ours 交出乾淨 new_only pool,強 reader 仍可能用參數知識覆蓋回世界真相舊版(Resolution 高、EM 降)——這是 **E-D 邊界**提早現身,非 bug。

**對主軸的意義(接下一節)**:§3.1 只回答**「何時」**ours 贏(弱/中 backbone)。它逼出 §3.2 的**「為何」**——差距從哪來?答案是 pool state(乾淨 vs 汙染),而弱 reader 正是最需要乾淨 pool 的人。

**Evidence 狀態**:🟢 全到位(COVERAGE.md:6-tier @6k 齊、4o/4.1 × 3 長度齊;唯 gemma 長 context 為 optional）。

---

## §3.2 — Observation 2：差距來自「回傳記憶的狀態」,不是 reader（呈現 → E2E）

§3.1 給了「何時」ours 贏;§3.2 答「為何」。核心:**三派用不同方式把 KU 寫進「回傳給 answer LLM 的記憶」,所以要用不同 lens 讀那份記憶**——mem0/ours 把 KU 寫進**文字**(用 pool_state 讀),Zep 把 KU 寫進**時間標註**(用 bi-temporal 讀)。跨方法只在 E2E 對齊。

### 3.2.1 定義：pool_state（mem0 / ours 的 lens）

**mem0/ours 的 KU 都改變「回傳文字」本身**:mem0 於 write 時實刪/覆寫舊版 → 回傳的是存活的文字;ours 於 query 時把同一事實的版本解析成新版(both→new_only)→ 回傳的是 resolved 後的文字。因此對兩者,**「答題 LLM 看到什麼」= KU 結果**。

**pool_state**(matcher v4,[`../matcher_specification.md`](../matcher_specification.md)):把回傳記憶文字與該題 `gt_new_fact` / `gt_old_fact` 字面比對,分四桶——
- **PP-New**:只有新版(KU 成功,舊版已解掉) · **PP-Both**:兩版都在 · **PP-OldOnly**:只有舊版(新版被毀) · **PP-Missing**:兩版皆無。
> 讀法:PP-New 是理想;PP-OldOnly/PP-Missing 是「正確版不在回傳記憶裡」→ answer LLM 再強也答不出。

**呈現**:此節用 **table**(pool_state 是無趨勢的分類 composition,依圖表規範用表;數字來源 [`../results/pool_acc_crosstab.md`](../results/pool_acc_crosstab.md))。Zep 不在此節(它的 KU 不寫在文字,見 3.2.4);既有 `F_pool_diagnostic.png` 含 Zep 欄 + LCA 線,**不適用本節**,待重製或棄用(見本節末備註)。

### 3.2.2 ours（table）

| length | PP-New | PP-Both | PP-OldOnly ↓ | PP-Missing ↓ | E2E |
|:--|--:|--:|--:|--:|--:|
| 6k | 52/53 (98%) | 17/21 (81%) | 0/0 | 0/0 | 69/74 (93%) |
| 32k | 39/40 (98%) | 17/22 (77%) | 0/2 (0%) | 1/1 | 57/65 (88%) |
| 64k | 35/38 (92%) | 24/26 (92%) | 1/2 | 0/0 | 60/66 (91%) |

> **Observation（ours）**:回傳記憶**幾乎全落在 PP-New / PP-Both,破壞性桶(OldOnly+Missing)≤2 題**。PP-New 桶內 acc 92–98%。→ **非破壞 write + query-time 解析**保證「正確版一定在回傳記憶裡、且多數已收斂成 new_only」。

### 3.2.3 mem0（table）

| length | PP-New | PP-Both | **PP-OldOnly ↓** | **PP-Missing ↓** | 毀損質量 | E2E |
|:--|--:|--:|--:|--:|--:|--:|
| 6k | 25/27 (93%) | 9/12 (75%) | **0/15 (0%)** | **0/20 (0%)** | 35/74 (47%) | 34/74 (46%) |
| 32k | 21/22 (95%) | 4/14 (29%) | **0/11 (0%)** | **0/18 (0%)** | 29/65 (45%) | 25/65 (38%) |
| 64k | 25/25 (100%) | 9/17 (53%) | **0/15 (0%)** | **0/9 (0%)** | 24/66 (36%) | 34/66 (52%) |

> **Observation（mem0）**:PP-New 桶 acc **93–100%**——**reader 拿到乾淨 pool 時和 ours 一樣強**。但 mem0 有 **36–47% 的題落在 PP-OldOnly+PP-Missing,且該質量 acc 全 0%**:write-time UPDATE 把新版刪掉/覆寫 → 正確版根本不在庫裡 → retriever 再好也救不回。**這團毀損質量 = mem0 的 E2E 缺口**。

> **★ 3.2.2 vs 3.2.3 的合證表(接主軸)**：把兩表的關鍵三量並排——

| length | 毀損質量 (OldOnly+Missing) ours | mem0 | PP-New 桶 acc ours | mem0 | E2E ours | mem0 |
|:--|--:|--:|--:|--:|--:|--:|
| 6k | 0/74 (0%) | **35/74 (47%)** | 98% | 93% | 93% | 46% |
| 32k | 3/65 (5%)† | **29/65 (45%)** | 98% | 95% | 88% | 38% |
| 64k | 2/66 (3%) | **24/66 (36%)** | 92% | 100% | 91% | 52% |

> † ours 的 OldOnly/Missing 為零星 extraction/D-flag edge case(非系統性毀損);mem0 的則是 write-time UPDATE 系統性刪掉正確版。
>
> **讀法(精準)**:**PP-New 桶 acc 兩派幾乎相同(~93–100%)**(reader 對乾淨 pool 一樣強)、**且共用同一 embedder**(retrieval 被控成常數)→ reader 與 retrieval **不是 ours vs mem0 差距的來源**(它們是共享/被控的;**不是說它們沒問題**——reader 在 PP-Both 要自判會掉、強端還會 override,retrieval recall 也是共享難題)。→ **差距來自 pool 組成**(ours ~0% vs mem0 36–47% 毀損)。這把 §3.1 的 gap **因果歸因到 write-time 破壞**,兌現主軸「判錯就毀、正確版在被問到前就消失」。
>
> **⚠ 不宜硬講的一點(誠實)**:**跨方法比較「PP-Both 桶內 acc」不嚴謹**——各方法 PP-Both 裝的是**不同 query 子集**(ours=沒解成 new_only 的殘餘、mem0=剛好留兩版、Zep=全部),難度不同,是 selection bias,**不能宣稱「同 PP-Both 我方 reader 較強」**。真正穩健的是**同一方法內**:PP-New(乾淨)acc **≳** PP-Both(需自判)acc(ours 98/98/92 vs 81/77/92;mem0 93/95/100 vs 75/29/53)→ **乾淨 pool 幫到 reader**,而 ours 產出的多是 PP-New。這才是「乾淨 pool 有價值」的乾淨證據。

> **備註（F_pool_diagnostic 的處置)**:現有 `F_pool_diagnostic.png`(ours/mem0/**Zep** × 3 長度 + LCA 線)對本節**不適用**(Zep 不該用 pool_state、LCA 離題、雙 row stacked 難讀)。§3.2 改以上表為主。**若仍要一張視覺**,建議重製為精簡版:**只 ours + mem0、兩桶(乾淨=New/Both vs 毀損=OldOnly/Missing)、無 LCA、無 Zep**——但 table 已足,圖非必要(待你決定要不要做)。

### 3.2.4 定義：bi-temporal（Zep 的 lens）

**Zep 不刪舊版**:它在 fact-level 對新舊記憶**各自標時間有效範圍**(`valid_at`/`invalid_at`),把「挑哪版」外包給 answer LLM 讀時間範圍自判。因此 Zep 的回傳記憶**~98% 是 PP-Both**(兩版都在)→ **pool_state 對 Zep 零鑑別**。要知道 Zep 做了什麼 KU,只能讀 bi-temporal 欄位(是否給舊版設了 `invalid_at`):**Resolved-Correct**(舊版被標失效)/ **Resolved-Backward**(反而標失效新版)/ **Additive-NoKU**(兩版都沒標)/ **Other**。詳見 [`../results/zep_ku_resolution_bitemporal.md`](../results/zep_ku_resolution_bitemporal.md)。

### 3.2.5 Zep（table + figure）

[`../figures/F_zep_ku_resolution_6k_32k_64k.png`](../figures/F_zep_ku_resolution_6k_32k_64k.png)(objective_data §4B Table D)

| length | Resolved-Correct | Resolved-Backward | **Additive-NoKU** | Other | E2E |
|:--|--:|--:|--:|--:|--:|
| 6k | 23% (acc 88%) | 30% (acc 36%) | **39% (acc 69%)** | 8% | 62% |
| 32k | 9% (acc 100%) | 3% | **77% (acc 44%)** | 6% | 51% |
| 64k | 17% (acc 100%) | 0% | **74% (acc 41%)** | 8% | 55% |

> **Observation（Zep）**:當 Zep **真的標對時序**(Resolved-Correct),answer LLM 用時間範圍就答對,**acc 88–100%**——證明「時間標註呈現」在**有做到 KU 時**確實有效。但 Zep **多數 case(39→77→74%)是 Additive-NoKU:根本沒標**,把一對 co-active 事實丟給 reader 自己猜 → 該桶 acc 崩到 41–69%。→ Zep 的機制把「挑版」延後到 inference,但**寫入端多半沒生出可判的時序信號**。

**對主軸的意義(接下一節)**:§3.2 證明「回傳記憶的狀態」預測 E2E,且該狀態由**寫入端如何做 KU**決定(mem0 毀損文字、Zep 多半沒標、ours 乾淨)。§3.3 再往內一層,用各自機制**回推這些狀態怎麼產生的**(mem0 M1/M2、Zep additive/backward),把因果鎖到 write-time 架構。

**Evidence 狀態**:🟢 全到位(pool_acc_crosstab 3 長度、F_pool_diagnostic、Table D / F_zep_ku_resolution)。
## §3.3 — Observation 3：各自機制如何造成該「回傳狀態」（fail mode + case study）

§3.2 給了「回傳記憶落在什麼狀態」;§3.3 用各自機制**回推這些狀態怎麼產生的**。此節不列比例(見機制檔),只**舉 case + 口頭說明我們主要觀察到什麼**。

### 3.3.1 招牌 case：同一題,三方法(qid=1「Who is the author of Hard Times?」@64k)

- **GT_new**(counterfactual,對話較晚出現)= *Martin Luther King Jr.*(seq 2335)
- **GT_old**(真實世界)= *Charles Dickens*(seq 687)

| 方法 | 機制動作(何時、怎麼判)| 回傳記憶狀態 | 答案 |
|:--|:--|:--|:--|
| **mem0** | **write-time**:UPDATE prompt 見 MLK 新事實 + 檢索到 Dickens 舊記憶;**recency 非確定性規則**(交 LLM 語意裁決)→ counterfactual 遇 **world-prior 判「保留 Dickens」**(MLK 靜默 NONE,全 event log 無 Hard-Times MLK 事件)| **PP-OldOnly**(只有 Dickens)| Charles Dickens ❌ |
| **Zep** | **write-time**:兩版各抽成 edge,**未判為衝突 → 都不設 `invalid_at`**(Dickens valid=…、MLK valid=None,皆無 invalid)| **PP-Both**(兩版都在、**無時序可判**)| Charles Dickens ❌(reader 靠 world-prior 挑)|
| **ours** | **query-time**:(S,P)=(Hard Times, author) 分組 → **argmax ordinal**(MLK 2335 > Dickens 687)| **new_only**(只有 MLK)| **Martin Luther King Jr. ✓** |

> **一句話**:同一題、同一對事實,三種**「何時、用什麼判」**的差異,直接產生三種回傳狀態、三種答案。mem0 在 write 時就把正確版判掉、Zep 在 write 時沒判(丟給 reader 用 world-prior 猜)、ours 延到 query 時用確定性 recency 判對。**這正是主軸的縮影。**

> **術語(供讀者)**:**input 時序** = 某事實在對話中被講出的先後(較晚 = 較新版本);ours 以 per-fact `ordinal`(越大越新)顯式編碼、用確定性 argmax 挑最新,**LLM 從不裁決 recency**。**前綴(prefix)** = write-time 逐 chunk 處理時「到目前為止看到的開頭那段對話」(處理 chunk *i* 只 ingest 了 1..*i*,還沒看到之後);query-time 則是整庫 ingest 完才判,看到**完整資訊**。

### 3.3.2 mem0 的 fail mode（主要觀察到兩類,均 write-time 不可逆)

**(M1) world-prior rejection → PP-OldOnly**（case = 招牌 qid=1 Hard Times,見上表）
新事實與模型參數知識衝突(counterfactual)時,mem0 的 UPDATE **不把 input 時序當確定性規則**,交 LLM 語意裁決 → world-prior 判「保留世界真相舊版、靜默 NONE 掉新版」。qid=1 即:MLK(新)雖較晚進來,仍被判不採納,庫裡只剩 Dickens。*(同類:qid=9 Kermit creator、qid=60 sport)*

**(M2) coupled-update damage → PP-Missing**（case = qid=2「David Farragut 的公民身分?」)
- GT_new = *Denmark*(較晚)· GT_old = *USA*(較早,先於 chunk 21 ADD 入庫)。
- mem0 於後續 chunk 收到 Denmark,UPDATE prompt **判斷正確**(Denmark 應取代 USA)→ 對 USA 那格發 `DELETE`;**但單一 output list 漏了對應的 `ADD Denmark`**(判斷與執行綁一起的 completeness bug)。
- 結果:USA 被刪、Denmark 從未入庫 → **兩版皆失(PP-Missing)** → answer LLM 面對空 pool,退回 world-prior 幻覺答「**USA**」❌。
- 對照 **ours**:USA/Denmark 兩版都保留,query 時 (S,P) 分組 → argmax ordinal → **Denmark ✓**。
- *(另一 M2 變體:cross-item cascade DELETE — 無關 chunk 處理時,retrieval 誤把已存正確版當 similar candidate 而 DELETE)*

> **口頭說明**:我們主要觀察到 mem0 的失分**集中在 PP-OldOnly / PP-Missing**——根因都是 **write-time 對每筆事實下不可逆決定、且把 recency 交給易錯的 LLM 語意**:判錯(world-prior,M1)或執行漏項(coupled,M2)都直接毀掉正確版。詳見 [`../results/mem0_ku_mechanism.md`](../results/mem0_ku_mechanism.md) / [`../results/mem0_event_taxonomy_gt4o.md`](../results/mem0_event_taxonomy_gt4o.md)。

### 3.3.3 Zep 的 fail mode（主要觀察到「根本沒判」)

Zep 不刪舊版,而是對 fact-level edge 各標時間有效範圍(`valid_at`/`invalid_at`)讓 reader 自判。它的失分不是「正確版不見」,而是**沒生出可判的時序信號**。

**(主) Additive-NoKU → PP-Both 但無時序**（case = 招牌 qid=1 Hard Times,見上表)
兩版都被抽成 edge、都在回傳裡,但 **Zep 沒對它們設 `invalid_at`**(additive)。qid=1 即:Dickens(valid 設)、MLK(valid=None),**兩者 invalid 皆 None** → 一對 co-active 事實原封丟給 reader、無範圍可依 → reader 靠 world-prior 挑 Dickens ❌。

> **⚠ 誠實限制(Zep 與 mem0 的可觀測性不對稱)**:**為何** Zep 沒設 invalid_at——是「候選檢索沒撈到舊版」還是「撈到了但沒判 contradicted」——**無法從回傳確定**(Zep Cloud 閉源;我方讀 open-source graphiti 內部候選邏輯結論不一致)。列 future work(instrument open-source graphiti 才能定,對稱於 mem0 的 `MEM0_CAND_LOG_DIR`)。相對地,**mem0 有 event log 可追到具體 decision**(§3.3.2 的 M1/M2)。此不對稱本身即誠實揭露,不影響結論(兩派都在 write-time KU 失敗)。

**(次) Resolved-Backward → 標錯方向**（case = qid=53「Imelda Marcos 的宗教信仰?」)
- GT_new = *atheism*(counterfactual,較晚)· GT_old = *Catholicism*(世界真相,較早)。
- 短 context(6k)兩版相近而**觸發**了判斷,但 world-prior + 到達順序把方向弄反:Zep 對**新版 atheism 設 `invalid_at`**(valid 00:00 → invalid 17:56:41)、**保留 Catholicism active**(valid 17:56:41、invalid=None)。
- reader 看到「atheism(已標失效)+ Catholicism(有效)」→ 選有效的 → 答「**Catholicism**」❌(GT=atheism)。
- 這是「標對版」的鏡像:Zep **有判,但判反**——把該留的 counterfactual 新版標失效了。

> **口頭說明**:我們主要觀察到 Zep **很少破壞(不刪)、但多半沒把 KU 做出來**(Additive 佔多數);少數有判的又可能像 qid=53 判反。所以它的失分集中在「**沒給 / 給錯 reader 可判的時序信號**」。詳見 [`../results/zep_ku_resolution_bitemporal.md`](../results/zep_ku_resolution_bitemporal.md)。

### 3.3.4 小結：過去派卡在 write-time 的「一次檢索 + 兩步 LLM 判斷」

把 §3.3.1–3.3.3 收成一句:**write-time 要做 KU,得先「找出候選記憶」,再對每一筆事實用 LLM 判兩件事**——(i) **從候選中認出同一事實的不同版本**(identity)、(ii) **選出正確版本**(recency)。**只要任一步錯,正確版就進不了 memory**:
- **mem0**:(i)/(ii) 判錯即**實刪/覆寫**(M1 world-prior、M2 coupled)→ PP-OldOnly/Missing(event log 可追)。
- **Zep**:常在 (i) 之前就**沒把舊版湊進候選** → 沒判 → additive(只能觀察 outcome,內部原因待 instrument)。

→ 共同根因:**在「沒有 query、只看前綴、須改動共享記憶」下,對每筆事實下不可逆的兩步 LLM 判斷**。§3.4 說明我們如何用架構 + 機制避開這兩步的不可逆風險。

**Evidence 狀態**:🟢 case 全實測(qid=1 三方 @64k 已核;qid=2 mem0 event-log grounded;qid=53 Zep backward 已核);Zep additive 內部原因誠實列 future work。
## §3.4 — Observation 4：我們的架構 + 機制設計（為何能避開上述失敗)

§3.3 顯示過去派卡在 write-time 的「一次檢索 + 兩步 LLM 判斷」,任一步錯即毀正確版。我們的設計對應地拆解這個風險。

### 架構：Faithful write + defer KU 到 query-time
過去派對**每筆事實**在 write-time 下不可逆判斷;我們**忠實寫入所有事實、write 時不做跨筆判斷** → **從一開始就保證庫裡一定含正確版本**。KU 判斷 defer 到 query-time:
- **只對每個 query「找一次候選」**(而非 write-time 對每筆事實找)→ 判斷次數從 **O(F)**(64k F≈4000 筆事實)降到 **O(Q)**(≈100 個 query),且 **read-only、錯了下次可重判**(非破壞)。
- 「找候選 recall 隨庫降」是三派共享難題,但只有 write-time 把該步的錯**烙成不可逆**;我們在 query 時找候選,miss 只是這次沒分組、版本仍在庫。

### 機制：在 query 縮小的候選裡,把 LLM 語意誤判降到最低
把 KU 拆成兩件、各用最不易錯的方式做:
- **認出同一事實不同版本(identity)**:先用**結構 (S,P) exact 索引**盡量分群(hash 精確、**不隨庫變大退化**——正是 Zep fuzzy 檢索的解藥);**LLM 只做「結構分不出來時」的補救 identity grouping**。
- **選對版本(recency)**:交**確定性 ingestion ordinal argmax**(最新勝);**不讓 LLM 語意決定 recency** → world-prior 無從介入(對照 mem0 的 M1)。

→ LLM 只碰「識別的補救」、不碰「recency」→ **關鍵判斷的 LLM 比例降到最低 → 中小模型也穩**。

### 證據：ablation × backbone（E-C）
Table B（`objective_data_consolidated.md` §3;`F_struct_vs_p3_overall_6k.png`),has_pair EM %:

| 變體 | 1B | 4B | 12B | 27B | 4o-mini |
|:--|--:|--:|--:|--:|--:|
| ours (main) = struct + P3 + argmax | 34 | 73 | 99 | 95 | 93 |
| **ours (struct)** = struct + argmax（**無 LLM identity**) | **39** | 73 | 99 | 88 | 91 |
| ours (p3-only) = LLM identity + argmax（**無結構**) | 9 | 35 | 62 | 36 | 96 |
| **P3 淨 Δ = main − struct（pp)** | **−5** | 0 | 0 | **+7** | **+2** |

> **Observation**:
> - **struct-only 已達 main 的絕大部分**(1B 39、4B 73、12B 99、27B 88、4o 91)→ **確定性 (S,P)+argmax 是 workhorse**。
> - **p3-only 在弱 backbone 崩**(1B 9、4B 35、27B 36)→ 純 LLM identity 路徑 **capability-gated**。
> - **P3 淨 Δ(= main − struct)隨 backbone 單調變號**:**1B −5 → 4B 0 → 12B 0 → 27B +7 → 4o +2**——在**最弱** backbone 上加 LLM identity **反而略害**(弱 LLM 誤分群),要到 mid-strong 才轉正 → **P3 是 capability-gated add-on,不是主幹**。
> **Implication**:ours 於弱 backbone 的地板**來自結構、不是 LLM**——直接兌現「降低 LLM 比例 → 弱 backbone 仍穩」,也回答 §3.1「為何 ours 在弱端不崩」。**遞迴論證**:連我方自己的 LLM 元件(P3)都逃不過「弱 backbone LLM 判斷脆弱」,故把 KU 主幹交給確定性結構。

### 誠實邊界（接 E-D）
ours 的架構優勢**止於把乾淨 pool 交到 reader**。若 reader 對乾淨 pool 仍 world-prior override(強 backbone 亦見,Resolution > EM),ours 與過去派同樣答錯——這是三派共享的下游,屬 **E-D 責任邊界**(reader override / 抽取 / 檢索 recall / D-flag)。

**Evidence 狀態**:🟢 E-C ablation × backbone 6k 齊(Table B);reader-override 佐證見 E-D(F_struct_backbone / case study)。
## 跨 benchmark — FC → LongMemEval（拆 world-prior vs 架構)

**Claim**:把主張從 FC-SH(general/counterfactual fact)推廣到 **LongMemEval(KU),由 personal fact 組成的知識更新題**,目的是**排除一個潛在 confound**,讓「架構(query-time)」的貢獻被單獨看見。

**為何需要這步(confound-removal 設計)**:
- FC-SH 的新版是 **counterfactual**(與世界知識衝突,如「MLK 寫了 Hard Times」)。→ reviewer 可質疑:mem0/Zep 的失敗**不是 write-time 架構問題**,而是「**反事實內容與 LLM 參數知識衝突 → LLM 抗拒更新(world-prior)**」——這是 counterfactual **資料**的性質,不是 write-time **時機**的問題。
- **LongMemEval 用 personal fact**(如 user 的現居城市、職業、婚姻狀態)——LLM **對特定使用者無參數先驗** → **world-prior confound 被移除**。

**預期與論證力**:
- 因為 world-prior 這條**對 baseline 也消失**,LongMemEval 上 baseline 可能變好、**ours 的 margin 縮小**(預期**仍略贏**)。
- **關鍵**:若 ours 在**沒有 world-prior 順風**下**仍略贏**,則優勢**無法**用「反事實坑 LLM」解釋 → **只能歸因於架構**(write-time 的其餘失效:coupled-update、無 query、跨筆 cascade、不可逆)。
- → 兩 benchmark **共同把 FC 的優勢分解**:FC = **架構 + world-prior**(大 margin);LongMemEval = **架構-only**(小但仍在);差值 ≈ world-prior 貢獻。這比「換資料集再贏一次」強,直接反制「你們只是靠 counterfactual 坑 LLM」。

**額外收穫**:LongMemEval 多含**多值 personal fact**(hobbies、去過的城市…)→ 讓 FC 上 dormant 的 **query-dependence(單值 vs 多值須看 query)** 與 ours 的 **query-aware conflict-type(P5)** 真正 earn its keep(FC 97% freshness 用不到 P5)。

**Evidence 狀態**:🔴 **LME baselines full(mem0/vanilla/Zep)待跑**——此步論述的前置;ours KU 已驗 ~83%(gpt-4o-mini judge)。(lme_hyps 已有 ours_no_p5 / vanilla 部分輸出,baselines full + judge 對齊待完成。)
