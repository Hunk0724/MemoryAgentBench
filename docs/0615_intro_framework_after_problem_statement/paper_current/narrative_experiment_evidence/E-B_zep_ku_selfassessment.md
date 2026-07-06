# E-B(Zep 支線)— Zep 用「自身 KU resolution 行為」解釋 E2E

> **掛在哪**:論證鏈 **E-B「機制:gap 從何而來 = pool state」**(見 [`README.md`](README.md) §A/§B)。
> **這份補什麼**:README 對 Zep 的定位是「**Zep/both-present 靠 reader 挑版**」。本檔把這句從「PP-Both 讓 reader 挑」**精確化並下修**成——**Zep 有 ~80% 的 has_pair 根本沒生出時序信號(Additive-NoKU),reader 無從挑**;會挑的前提(乾淨時序)Zep 自己就先崩了。這正是 thesis「乾淨 pool 靠 LLM 判斷派在弱 backbone 上崩」在 Zep 這一派的**寫時(write-time)版本**。
> **canonical 數字**:一律回引 [`../results/objective_data_consolidated.md`](../results/objective_data_consolidated.md)。詳細機制與分桶:[`../results/zep_ku_resolution_bitemporal.md`](../results/zep_ku_resolution_bitemporal.md)。

---

## §1 為何 Zep 不能用 pool-state cross-tab 解釋(方法前提)

E-B 主線用**文字 pool-state × Acc**(mem0/ours 有效:KU 落在 pool 文字)。**Zep 例外**:

- Zep search **不過濾 invalid edges** → 兩版恆同時回傳 → 文字 classifier 對 Zep **~98% 判 PP-Both**(64k 65/66),零鑑別力。
- Zep 的 KU 決定寫在 **bi-temporal 欄位(`valid_at`/`invalid_at`)**,不在文字。

→ Zep 的 E-B mediator 必須換成 **bi-temporal KU-resolution state**(下 §3)。跨方法只在 **E2E Acc** 對齊;機制歸因各用各的 mediator。**勿把 Zep 的 PP-Both 與 mem0 的 PP-OldOnly 並列**(會低估 Zep 的 KU 失敗)。完整論證見 [`../matcher_specification.md` §3.4](../matcher_specification.md)。

---

## §2 Zep 的 KU 是「decoupled write-time labeling」(定位一句話)

| 派別 | KU 發生在 | 對舊版做什麼 | 給 reader 的 pool | 乾淨怎麼來 |
|---|---|---|---|---|
| mem0 | write-time | 實刪/覆寫 | 存活文字 | 破壞性刪除(不可逆) |
| **Zep** | **write-time labeling → 延後判讀到 inference** | 保留 + 標 `invalid_at` | **兩版都給 + date range** | 不變乾淨;**外包給 reader 讀時序** |
| ours | query-time | 全版本保留、查詢時解 | resolved 後 new-only | 非破壞性、query-time 選 |

Zep 是三派中唯一把「乾淨」責任**丟給 reader**的;因此 Zep 的 E2E 天然是 **P(Zep 標對時序) × P(reader 讀對)** 的兩段乘積,弱 reader 首當其衝。

---

## §3 Evidence:Zep 自身 KU resolution 分桶 × E2E

**bi-temporal 4 桶**(handoff-verified;完整定義/表見 results 檔 §2–3),gpt-4o-mini × has_pair:

| length | Resolved-Correct | Resolved-Backward | **Additive-NoKU** | Other | E2E acc(canonical) |
|---|---:|---:|---:|---:|---:|
| 6k | 23%(acc 88%) | 30%(acc 36%) | **39%**(acc 69%) | 8% | 46/74 = **62.2** |
| 32k | 9%(acc 100%) | 3% | **77%**(acc 44%) | 6% | 33/65 = **50.8** |
| 64k | 17%(acc 100%) | 0% | **74%**(acc 41%) | 8% | 36/66 = **54.5** |

> **一致性檢查**:4 桶正好 partition canonical has_pair 集,各桶 EM 加總 = canonical Zep E2E(62.2/50.8/54.5,對 `objective_data_consolidated.md` §2/§4)。分解無殘漏。

**三個掛 E-B 的 claim**:

1. **失敗在「Zep 標不標」,不在「reader 讀不讀得懂」**:Resolved-Correct 桶 acc = **88 / 100 / 100%** — Zep 一旦標對時序,連 gpt-4o-mini reader 都答對。→ 瓶頸是 write-time 觸發率,不是 reader。
2. **Additive-NoKU 是主導失效,且隨長度暴增**(39→77→74%,且為**保守下界**,見 results §3.2):Zep 越長越測不到衝突 → 把**未解的一對 co-active 事實**丟給 reader、**無任何時序可挑** → Additive 桶 acc 崩(69→44→41%),reader 只能靠 world-prior 猜 → counterfactual 系統性錯。
3. **短 context 的 Resolved-Backward = world-prior 寫時誤判**(6k 30%、acc 36%):兩版近 → 觸發 resolution,但 world-prior 把方向導成「用世界真相覆蓋反事實新版」→ 失效 GT-new。機制見 results §4B。

**接榫回 thesis**:Zep 印證「靠 LLM 判斷才能乾淨」在**寫時端**同樣脆弱——不是 reader 挑不動,而是 **Zep 自己 80% 沒把 pool 標乾淨**,reader 根本沒有可挑的乾淨信號。這與 mem0(write-time 刪錯)是同一個 thesis 的兩種寫時失效,共同對照 ours 的「確定性、query-time 保證乾淨」。

---

## §4 機制根因(write-time orchestration,支撐 §3 趨勢)

Zep 底層 graphiti:**抽取 = chunk 批次一次抽;KU 判斷 = per-fact 並行、只跟已存圖比(bounded top-k)、同 batch sibling 不互比**(原始碼佐證,見 results §1B)。由此:

- **Additive 隨長度上升**:圖越大 → contradiction 候選 top-k 越易 miss 掉那條特定舊 edge → 不觸發 → additive。
- **6k Backward 偏高**:6k 僅 ~12 chunk → 兩版常同 chunk / 相近 → 觸發 resolution;world-prior 導向 backward(rigor 校準見 results §4B)。

---

## §5 呈現建議(寫作時)

- **主圖沿用** E-B 的 [`figures/F_pool_diagnostic.png`](figures/F_pool_diagnostic.png);Zep 那欄的「PP-Both」**在正文用一句 footnote 導向本支線**:PP-Both 對 Zep 非鑑別,真實分解見 bi-temporal 4 桶。
- **新圖(已繪)**: [`figures/F_zep_ku_resolution_6k_32k_64k.png`](figures/F_zep_ku_resolution_6k_32k_64k.png) — 2-panel line 圖:(a) 4 桶 share × length(Additive 上升為主線)、(b) 各桶 EM × length(Resolved-Correct 高平、Additive 崩、overall 參考線)。B&W-safe(linestyle+marker+灰階),`scripts/make_zep_ku_resolution.py` 產生。canonical 表 = objective_data §4B Table D。
- **引用信心分級**(勿被 reviewer 抓):Additive-NoKU(headline,保守下界)> Resolved-Correct(handoff+高 acc)> Resolved-Backward 單一數字(matcher over-match 敏感,見 results §6)。

---

## §6 caveat（誠實揭露，與 results 檔一致）

- Zep = 雲端閉源;機制以 graphiti open-source 原始碼 + 黑箱行為交叉驗證(非白箱)。
- bucket 用 `match_pair` v4 對應版本,generic (S,P) stem 有 over-match(multi-edge ~30%)→ Resolved-* 已 handoff-verify,殘餘落 Other-Ambiguous;Additive 因 over-match 只會被低估(保守)。
- 僅 gpt-4o-mini backbone(Zep 路徑非各 backbone 都有 edges dump);強/弱 backbone 的 Zep bi-temporal 未同等分析,列 future。
- §4B 的 6k-backward intra/cross-chunk 判定需 edge source-episode metadata,列 future check;穩健結論不依賴該細節。
