# Zep KU-resolution — bi-temporal mediator（非文字 pool_state）

> **目的**:證明 Zep 的 KU 行為**無法**用文字 pool_state(PP-Both/OldOnly/…)量測,必須讀 bi-temporal 欄位(`valid_at`/`invalid_at`)。這是跨方法 pool_state 不可比性的實證(見 [`matcher_specification.md`](../matcher_specification.md) §3.4)。
>
> **產生**:`python analysis/classify_zep_ku_resolution.py`(canonical;import `match_pair` + `_em_from_perqid`,MABench env)。
> **資料**:`outputs/rag_retrieved/Structure_rag_zep/k_10/factconsolidation_sh_{6k,32k,64k,262k}/chunksize_512/query_*_context_*.json`;backbone = gpt-4o-mini × temp 0;k=10。
> **日期**:2026-07-07(6k/32k/64k)、2026-07-16(262k + invalidation coverage 統計)。

---

## §1 為什麼文字 pool_state 對 Zep 失效

Zep search **不過濾 invalid edges**——active + invalid 一起回傳(black-box 驗證見 `analysis/results/oracle_a/zep_mechanism_deep_dive.md` Q4;開源 graphiti `resolve_extracted_edge` 機制佐證)。因此只要 gt_new 與 gt_old 兩句都被抽成 edge,**兩版恆同時出現在 top-10**,文字 classifier 一律判 `PP-Both`。

實測(has_pair,兩版皆在 top-10 edges):**64k = 65/66(~98%)PP-Both**。文字 pool_state 對 Zep **零鑑別力**——它把「Zep 正確解 KU」「Zep 沒解」「Zep 解反」三種機制相反的情況全壓成同一桶。

Zep 的 KU 決定寫在 **bi-temporal 欄位**,不在文字。要量測必須讀 `valid_at`/`invalid_at`。

---

## §1B Write-time orchestration(機制背景,解釋 §3 的長度趨勢)

> 來源:graphiti-core `main` 原始碼(`extract_edges.py` / `edge_operations.py::resolve_extracted_edges`;Zep Cloud 底層引擎)+ MemoryAgentBench 餵法(`agent.py:1151` `graph.add(type="text", data=chunk)`,**每個 chunk = 一次 add = 一個 text episode**)。

**每個 chunk(episode)的兩段、不同顆粒度處理**:

```
1. extract_nodes    ── 對整個 chunk 一次抽出所有 entity(1 次 LLM call,batch)
2. resolve_nodes    ── entity 對既有圖 dedup
3. extract_edges    ── 對整個 chunk 一次抽出所有 fact/edge(1 次 LLM call,batch)
                       valid_at/invalid_at 於此步 inline 抽出
4. resolve_extracted_edge  ── 【KU 判斷】對「每一個」新 edge 各做一次,但:
                       · 並行(semaphore_gather),非嚴格由上到下依序
                       · 候選集只來自【已持久化的圖】(先前 episode 的 edges)
                       · contradiction 候選 = bounded top-k 語意搜尋(EDGE_HYBRID_SEARCH_RRF)
                       · 同 batch sibling 只有 exact-string fast dedup,語意衝突不互比
```

- **抽取 = chunk 批次**(不是逐 fact 抽);**KU 判斷 = per-fact**,但**並行**、且**只跟已存的圖比**。

**由此推出兩條「衝突偵測失效 → Additive-NoKU」路徑**:

1. **同 episode 內衝突不偵測**:嚴格 graphiti 下,同一 batch 的 sibling edges 只跟「batch 前的圖 snapshot」比、彼此不可見 → 若 old/new 兩版落在同一 batch,兩者都對不到對方 → 皆 active = Additive。
2. **跨 episode 但 bounded top-k miss**:新版在後面的 episode,理論上能搜到已存的舊版;但候選是**有界 top-k**——**圖越大,那條特定舊 edge 越易掉出 top-k 窗** → 沒進候選 → 不觸發 contradiction → Additive。

**這解釋 Additive-NoKU 隨長度上升(39%→77%→74%)**:第 2 條隨總 fact 數放大(6k 圖小、舊 edge 常還在候選窗 → 較多 Resolved;64k 圖大 → miss 率高 → additive 主導);第 1 條為跨長度大致固定的底噪。

> **rigor 註**:第 1 條(sibling 不互比)為原始碼確定行為;第 2 條(圖大 → top-k miss)為「與 bounded top-k 事實一致的機制推論」,非直接量測候選窗命中率(Zep Cloud 內部不可觀測)。

---

## §2 Bi-temporal KU-resolution 分類(4+1 桶,handoff-verified)

對每個 has_pair query,於 top-10 edges 找**所有**比中 gt_new / gt_old 的 edge,讀其 bi-temporal。

**關鍵 rigor**:Resolved-* 兩桶**要求驗證 pairwise handoff**,不是只看「有沒有 edge 帶 invalid_at」。graphiti 於衝突時把 loser 的 `invalid_at` **設成 winner 的 `valid_at`**,所以這兩版之間真正發生 KU 的簽章是 `loser.invalid_at == winner.valid_at`。**不驗這條**,則「new 被第三個 fact invalidate」或「matcher 在 generic (S,P) stem 上 over-match 到別 entity 的 edge」都會被誤記成 backward/forward resolution(見 §6 caveat,multi-edge 佔 26–35%)。不成立者一律歸 Other-Ambiguous。

| bucket | 定義(handoff-verified)| Zep 對這對 (new,old) 做了什麼 |
| :--- | :--- | :--- |
| **Resolved-Correct** | 存在 old-edge `invalid_at` == new-edge `valid_at` | ✅ 正確 supersede 舊版 |
| **Resolved-Backward** | 存在 new-edge `invalid_at` == old-edge `valid_at` | ❌ world-prior 誤失效新(counterfactual)版 |
| **Additive-NoKU** | 兩版所有 matching edge 的 `invalid_at` **皆 None** | ⚠ 完全沒偵測到衝突 → 兩句 co-active 丟給答題 LLM |
| **Other-Ambiguous** | 有 `invalid_at` 但**無**乾淨單向 handoff(第三方 invalidate / both-invalid / 缺 valid_at / multi-edge over-match)| 殘差 tail,報 % 不過度解讀 |
| **NotBothExtracted** | 一版或兩版不在 top-10 | 檢索/抽取 miss,非 KU 決定 |

---

## §3 結果(gpt-4o-mini × temp 0)

### 3.1 分桶 × EM（handoff-verified）

**6k**（has_pair N=74;multi-edge 26/74）
| bucket | n | pct | EM✓ | EM✗ | acc% |
| :--- | ---: | ---: | ---: | ---: | ---: |
| Resolved-Correct | 17 | 23.0% | 15 | 2 | 88.2% |
| Resolved-Backward | 22 | 29.7% | 8 | 14 | 36.4% |
| Additive-NoKU | 29 | 39.2% | 20 | 9 | 69.0% |
| Other-Ambiguous | 6 | 8.1% | 3 | 3 | 50.0% |
| NotBothExtracted | 0 | 0.0% | — | — | — |
| **TOTAL** | **74** | | **46** | **28** | **62.2%** |

**32k**（has_pair N=65;multi-edge 19/65）
| bucket | n | pct | EM✓ | EM✗ | acc% |
| :--- | ---: | ---: | ---: | ---: | ---: |
| Resolved-Correct | 6 | 9.2% | 6 | 0 | 100.0% |
| Resolved-Backward | 2 | 3.1% | 2 | 0 | 100.0% |
| Additive-NoKU | 50 | 76.9% | 22 | 28 | 44.0% |
| Other-Ambiguous | 4 | 6.2% | 2 | 2 | 50.0% |
| NotBothExtracted | 3 | 4.6% | 1 | 2 | 33.3% |
| **TOTAL** | **65** | | **33** | **32** | **50.8%** |

**64k**（has_pair N=66;multi-edge 20/66）
| bucket | n | pct | EM✓ | EM✗ | acc% |
| :--- | ---: | ---: | ---: | ---: | ---: |
| Resolved-Correct | 11 | 16.7% | 11 | 0 | 100.0% |
| Resolved-Backward | 0 | 0.0% | — | — | — |
| Additive-NoKU | 49 | 74.2% | 20 | 29 | 40.8% |
| Other-Ambiguous | 5 | 7.6% | 4 | 1 | 80.0% |
| NotBothExtracted | 1 | 1.5% | 1 | 0 | 100.0% |
| **TOTAL** | **66** | | **36** | **30** | **54.5%** |

**262k**（has_pair N=77;multi-edge 5/77;2026-07-16 補跑)
| bucket | n | pct | EM✓ | EM✗ | acc% |
| :--- | ---: | ---: | ---: | ---: | ---: |
| Resolved-Correct | 5 | 6.5% | 4 | 1 | 80.0% |
| Resolved-Backward | 1 | 1.3% | 0 | 1 | 0.0% |
| Additive-NoKU | 6 | 7.8% | 3 | 3 | 50.0% |
| Other-Ambiguous | 2 | 2.6% | 1 | 1 | 50.0% |
| **NotBothExtracted** | **63** | **81.8%** | 3 | 60 | **4.8%** |
| **TOTAL** | **77** | | **11** | **66** | **14.3%** |

### 3.2 分桶佔比 × 長度（趨勢）

| length | Resolved-Correct | Resolved-Backward | Additive-NoKU | Other-Ambiguous | NotBothExtracted | overall acc |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: |
| 6k | 23% | 30% | 39% | 8% | 0% | 62% |
| 32k | 9% | 3% | 77% | 6% | 5% | 51% |
| 64k | 17% | 0% | 74% | 8% | 2% | 55% |
| **262k** | 6% | 1% | **8%** | 3% | **82%** | **14%** |

**哪些桶穩健(引用時的信心分級)**:
- **Additive-NoKU = headline,且為保守下界**:matcher over-match 只會把 query 踢**出** additive(多抓一個 invalid edge → 移到 Other/Resolved),故真實 additive ≥ 報告值。32k/64k 74–77% 站得住。
- **Resolved-Correct 穩**:handoff-verified + acc 88–100%(Zep 設對時序 → LLM 讀對)。
- **Resolved-Backward 真實但最敏感**:6k ~30% 反映短 context 的 world-prior 反向 supersede,確切數字受 over-match 影響;32k/64k 已 ≤3%,勿過度解讀單一數字。
- **Other-Ambiguous 6–8%**:殘差(第三方 invalidate + matcher over-match),預期存在,不解讀。

### 3.3 contradiction-handoff 驗證(機制真實性)

Resolved-* 桶本身即以 `loser.invalid_at == winner.valid_at` 為判準,故全桶皆滿足此簽章。人工細查 6k Resolved-Backward 17 例(first-match 版):**15/17 為乾淨單 entity 的 counterfactual 反向失效**(如 Imelda→atheism 失效留 Catholicism、Sable→Czech 失效留 USA、Darwin→Amala Paul 失效留 Emma),2/17 為 matcher over-match(如 qid=15「X located in continent Y」跨 entity 叢集)→ 已於 handoff-verify 後歸類。→ 證實開源 graphiti「衝突時 `loser.invalid_at = winner.valid_at`」機制在 **Zep Cloud** 產出的資料上屬實(非猜測)。

### 3.4 Invalidation coverage(全 test set 邊層統計,2026-07-16 新增)

**metric**:對每 length 的 Zep top-10 dump,統計 `(帶 invalid_at 的 edge) / (全 edge)` 於 100 queries × 10 edges 的樣本空間。這是「Zep 有多常給 edge 貼 invalidation tag」的整體指標,對應 fc_sh_main_table_4length.md caveat 引述的「僅 X% of retrieved edges 帶 `invalid_at`」。

| length | invalidated / total edges | coverage |
| :--- | ---: | ---: |
| 6k | 219 / 1000 | **21.90%** |
| 32k | 62 / 1000 | 6.20% |
| 64k | 97 / 1000 | 9.70% |
| **262k** | **63 / 1000** | **6.30%** |

- **6k 21.90%** 對應 §3.1 的高 Resolved-Correct + Resolved-Backward 佔比(23%+30% = 53% has_pair 觸發 KU 判斷)—— 短 context 密度高,contradiction 觸發率也高。
- **32k 6.20% → 64k 9.70%**:32k 的低 coverage 對應 §3.1 additive-NoKU 77%(bounded top-k 搜尋 miss 舊 edge → 不觸發 contradiction);64k 略回升與 has_pair 分母(65→66)+ Resolved-Correct 佔比(9%→17%)一致。
- **262k 6.30%**(= fc_sh_main_table_4length.md caveat 引述的 6.3% source):write-time 側 contradiction 觸發率確實極低;但**單此無法解釋 262k crash 到 14%**(64k 覆蓋率 9.70% 但 acc 55%)。真正主因見 §4C。

---

## §4 判讀(three-段論)

1. **What**:Zep 對 has_pair 的 KU,長 context 下**主導行為是 Additive-NoKU**(39%→77%→74%);真正正確 supersede(Resolved-Correct)僅 9–23%。短 context(6k)則多了一塊 Resolved-Backward(30%)。
2. **Observation**:
   - **失敗在觸發率,不在讀取**:Resolved-Correct 桶 acc = 88/100/**100%** — Zep 一旦設對時序,答題 LLM 就讀得對。問題是 Zep **越長越少正確觸發**(跨 chunk / 跨 ingestion 衝突不偵測 + FC 事實無 state-change 語意)。
   - **Additive 桶 acc 崩**:69%→44%→41% — 無時序信號時 LLM 靠 world-prior,counterfactual 系統性答錯。
   - **Resolved-Backward = world-prior 誤判**:6k 佔 30%、acc 僅 36%(Zep 把新版 counterfactual 失效 → LLM 傾向舊版 → 錯);長 context 幾乎消失(≤3%)。
   - **length interaction(新故事)**:短 context Zep **嘗試**解 KU 但常反向(world-prior);長 context Zep **停止偵測**衝突 → additive。兩者對 counterfactual FC 皆為失敗。
3. **Implication**:Zep 把 KU 負擔**延後到 inference**(呈現 date range 讓 LLM 自判),但**80% 的 case 連時序信號都沒生出來**,等於未解決的一對 co-active 事實直接外包給答題 LLM。這是「write/inference 端做 KU 皆有代價」的反例;對照 ours 於 query-time 用結構化 (S,P)+temporal 收斂(both→new_only),has_pair 86–92% flat。

---

## §4B 為何 6k 的 Resolved-Backward 特別高(30%)

長度趨勢的兩端各由**不同**失效路徑主導:長 context 是 §1B 第 2 條(bounded top-k miss → additive);**短 context(6k)則多出一整塊 Resolved-Backward**,機制如下。

**密度**:6k 以 chunk_size=512 只切 ~12 個 chunk(64k ~128 個)。同一事實的新舊兩版於**對話中位置相近**,因此在 6k **遠比 32k/64k 更常落入同一次 `graph.add`(同 chunk)**。

**觸發 + 方向**:一旦兩版足夠靠近而被 Zep 連上(同 chunk 內經 Zep Cloud 內部 episodic 切分成相鄰 sub-episode、或相鄰 chunk),KU **會觸發**;此時方向由「誰先持久化」× world-prior 決定:

- resolve 是**並行、非嚴格由上到下**(§1B step 4)→ 存在 GT-new(counterfactual)**先**被持久化的可能。
- 隨後處理到 GT-old(= 真實世界事實)時,contradiction judge 看到「incoming GT-old 與已存 GT-new 矛盾」→ 判 invalidate 既有者。**此時 world-prior 與「incoming 覆蓋 existing」同向**:LLM 對「用世界真相覆蓋反事實」特別願意 → **GT-new 被失效 = Resolved-Backward**。
- 反向(GT-old 先存、GT-new 後到)則 world-prior 與「incoming 覆蓋」**逆向**,LLM 猶豫 → 傾向不動作(additive)或正確覆蓋。

**觀測佐證**:6k backward 案例的 handoff 簽章 `new.invalid_at == old.valid_at` 成立(見 §3.3),即「GT-old 被處理的當下,失效了一個**已存在**的 GT-new」——與「GT-new 先入、GT-old 後到覆蓋之」一致。且這些案例的 `new.valid_at` 多為今日 00:00:00(vague-date fallback)、`old.valid_at` 為實際 ingestion 秒級時戳,符合兩版於不同時點被處理。

> **rigor 校準**:此機制要求「同 chunk 兩版能互相看見」,而嚴格 graphiti(單 episode batch、sibling 不互比)反而預測同 chunk → additive。兩者相容的解釋是 **Zep Cloud 把一次 `graph.add(type="text")` 的長文內部再切成多個 sub-episode 依序持久化**(raw graphiti 的單 `add_episode` 不會),使同 chunk 兩版落入相鄰 sub-episode 而可互比。此為**與 Zep Cloud 內部 episodic 分段一致的推論**;直接驗證需 edge 的 source-episode metadata 判定 backward 對是否 intra-chunk(列 future check)。**不依賴 intra/cross-chunk 細節的穩健結論**:6k 兩版近 → 觸發 resolution 的機率高 → world-prior 把觸發導向 backward;長 context 兩版遠 → 不觸發 → additive。兩者對 counterfactual FC 皆為失敗。

---

## §4C 為何 262k 崩塌 = **query-time retrieval miss 主導**(2026-07-16 新增)

先前推論(§4B 之外的長度趨勢)以「圖越大 → bounded top-k semantic search 越常 miss 舊 edge → additive-NoKU 單調上升」外推 262k,預期 additive-NoKU 佔比繼續升高、write-time invalidation 覆蓋率繼續下降。**262k 補跑資料完全推翻此外推**——additive-NoKU 於 262k **反而崩到 8%**(vs 32k 77% / 64k 74%),NotBothExtracted 一舉升到 **82%**(63/77 has_pair 於 top-10 沒同時看見 old + new 兩版)。

**修正機制**:

1. **262k 主因 = query-time top-10 retrieval miss**,而非 write-time invalidation 覆蓋不足。圖大小(chunk 數約 6k 12 個 → 262k 512+ 個)使 Zep semantic search 於 has_pair 之 target edge 對抗大量 distractor 時,**單一 target(gt_new 或 gt_old)已難進 top-10,兩版同時進 top-10 幾乎不可能**(6k 100% both 進 → 262k 只 18% both 進)。
2. **Additive-NoKU 崩塌是 NotBothExtracted 主導的副作用**:262k 中僅 14/77 has_pair 的 both 版本進了 top-10;於此小樣本內 additive 佔 6/14 ≈ 43%(與 64k additive/(has_pair − NotBothExtracted) = 49/65 = 75% 相比仍下降,但已非誇張的 8%)。**分母口徑對 § 3.2 的長度趨勢讀法有影響**:應以「NotBothExtracted 是否主導」為第一層判讀,再看剩餘分桶。
3. **6.3% invalidation coverage 為 write-time 側的次要指標**:262k 中 63/1000 edges 帶 `invalid_at`,雖確實極低,但**若母數只算「both 版本進 top-10 且 has_pair」的 14 例,invalidation 觸發率並不特別差於 32k/64k**。fc_sh_main_table_4length caveat 引用「6.3%」時應同時揭露 82% NotBothExtracted 主因,否則會誤導 paper 讀者以為 crash 完全是 write-time invalidation 不足。

**與先前 top-K asymmetry 驗證的一致性**:Zep top-50 於 262k(46/100 queries before rate-limit)= 28.3% ≈ k=10 29%,先前解讀為「top-K 上限不是崩塌根因」→ 現機制解讀為「262k 圖太大 → 語意 rank 上 target edge 被 distractor 淹沒 → 拉到 top-50 也抓不到 both 版本」;top-K 排除實驗與 82% NotBothExtracted 是同一機制的兩個表徵。

**262k 崩塌完整敘述(供 paper 引用)**:
> Zep 於 262k 的 crash(overall 29%、has_pair 14%)由 write-time / query-time **兩層問題**構成,兩層皆為「圖大小 → semantic search 對特定 target edge 難以精準檢索」的表徵。**write-time 側**:bounded top-k 語意搜尋於大圖上使 contradiction 觸發率下降(invalidation coverage 從 6k 21.9% 降至 262k 6.3%);**query-time 側**(主因):top-10 retrieval 於 has_pair 中 82% 抓不到 both 版本,答題 LLM 於 pool 內沒有 old + new 可比 → 只能靠世界先驗猜舊值 → has_pair acc 14.3%。單看 write-time invalidation 覆蓋率不足以解釋 crash(64k 覆蓋率 9.7% 但 acc 55%);query-time NotBothExtracted 主導才是主因。

---

## §5 對 paper 分析方法的結論

- **文字 pool_state → Acc 的中介分析**對 **mem0 / ours 有效**(其 KU resolution 落在 pool 文字:mem0 write-time 刪、ours query-time 解成 new-only),對 **Zep 無效**(KU 在 bi-temporal 呈現層)。
- **跨方法只在 E2E Acc 對齊比較**;機制歸因**各用各的 mediator**——mem0/ours 用文字 pool_state,Zep 用本檔 bi-temporal resolution state。這是尊重 resolution-locus 差異的 rigor,不是分析不一致。
- 現行 crosstab 若把 Zep 的 PP-Both 與 mem0 的 PP-OldOnly 並列,**低估** Zep 的 KU 失敗(PP-Both 看似「兩版都在沒問題」,實際 80% 未解)。正式論述應引本檔 4 桶數字。

---

## §6 caveat / 未做

- top-10 per query 為**答題 LLM 實際所見**;若要「Zep graph 全域 bank state」需 full graph dump(現只有 top-10 union,見 `zep_audit`)。本檔問的是「這題答題 LLM 拿到的一對版本,Zep 標了什麼時序」,top-10 正確。
- **matcher over-match(最大 caveat)**:gt_new/gt_old ↔ edge 的對應用 `match_pair`(v4),於 generic (S,P) stem(如「X located in continent Y」「X is a citizen of Y」)會**跨 entity over-match**多個 edge(multi-edge 26/74、19/65、20/66,約 30%)。因此:①Resolved-* 已改用 handoff-verify(`loser.invalid==winner.valid`)過濾大部分 spurious;②殘餘噪音落 Other-Ambiguous;③Additive-NoKU 因 over-match 只會被**低估**(保守),為安全下界。**引用信心**:Additive-NoKU(headline)> Resolved-Correct > Resolved-Backward 單一數字。
- Resolved-Backward / Other 於 32k/64k n 很小(≤5),acc 勿過度解讀;主敘事用 Additive-NoKU 的長 context 主導 + Resolved-Correct 的高 acc 對比。
- backbone 僅 gpt-4o-mini;gpt-4.1-mini / gemma 未跑本分類(Zep 路徑非各 backbone 都有 edges dump)。
- **未來精修(非必要)**:改用「與完整 gt fact 最接近的單一 edge」取代 stem-based match_pair,可壓低 multi-edge 噪音、收斂 Other-Ambiguous;但 headline(Additive 主導、Resolved-Correct 高 acc)不受影響,列 optional。

---

## 更新紀錄

- **2026-07-07**:建檔;6k/32k/64k 4-bucket + handoff-verified + §4B 短 context backward 機制。
- **2026-07-16**:補 262k(N=77;§3.1 表 + §3.2 趨勢加 262k row)+ §3.4 invalidation coverage 全 4-length 對照(找回 fc_sh_main_table_4length caveat 引述的 6.3% source)+ §4C 262k crash 機制修正(query-time retrieval miss 主導,非 write-time invalidation 不足)。腳本 patch:`analysis/classify_zep_ku_resolution.py`(LENGTHS 加 262k、`analyze_length`/`print_report` 加 invalidation coverage)+ `analysis/compute_pool_acc_crosstab.py`(GT_PATHS 加 262k → `sh_262k_mquake_analysis.json`)。
