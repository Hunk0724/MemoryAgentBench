# 論文用 Table / Figure 數據(FC-SH,gpt-4o-mini,2026-06-27)

> 從目前實測數據整理成論文呈現格式。詳細題數見 `experiment_results.md` §1.1;latency 見 §1.4。
> 圖在 `figures_current/`(`scripts/current_figures.py` 產;**舊 `evidence_figures/` 是過時 L2 數據,勿用**)。
> **Provenance**:✓ 實測 / 🔄 跑中 / ⚠ 待跑。

---

## Table 1 — Main:FC-SH KU accuracy(has_pair EM % / overall EM %)

| Method(family) | 6k | 32k | 64k | 262k |
|---|---|---|---|---|
| **Ours**(query-time resolution) | **92 / 92** | **86 / 89** | **91 / 94** | **88 / 91** |
| LCA(no-memory,full-context) | 88 / 88 | 71 / 74 | 55 / 65 | 31 / 42 |
| Zep(proactive·decoupled) | 68 / 76 | 55 / 69 | 67 / 78 | ⚠ |
| mem0+P1=(b)(proactive·coupled,destructive) | 46 / 51 | 45 / 61 | 41 / 58 | ⚠(M.C.~13hr) |
| vanilla mem0=(a)(stock) | 0 / 16 | 3 / 22 | 3 / 26 | 1 / 17 |

- has_pair 題數:6k=74、32k=65、64k=66、262k=77;其餘為 no_conflict(共 100)。
- **讀法**:**ours has_pair flat 86–92% 跨 40× context;LCA 崩 88→71→55→31;ours−LCA gap +4→+15→+36→+57**。
- **→ Figure `F_robust_haspair`(killer)** + `F_overall`。

## Table 2 — Additive ablation(FC-SH has_pair %;隔離兩個貢獻)

| | 6k | 32k | Δ 解讀 |
|---|---|---|---|
| (a) native(stock mem0) | 0 | 3 | 抽取在 FC 失敗 → store 近空 |
| (b) mem0 + P1 抽取(破壞性更新) | 46 | 45 | **+46/+42 = 忠實抽取**(事實存進 store);但破壞性更新仍丟約一半衝突 |
| (c) **ours**(保守 + query-time 解析) | **92** | **86** | **+46/+41 = query-time 解析**把剩下那半救回 |

- **→ Figure `F_ablation`**。兩個 delta 皆我方貢獻。

## Evidence(機制:為什麼贏)— L1/L2 context-state(已產圖)

> 抽取器 `scripts/state_extractor.py` → `state_eval_current.json`;圖 `scripts/evidence_figures_current.py` → `figures_current/`。
> 因果鏈:**L0 記憶庫狀態 → L1 檢索態 → L2 解析後 → EM**。

**E-L0(`F_bank_recall`,★ write-time 不可逆性的直接證據)— 記憶庫 GT-recall(掃整庫,非 top-k;`scripts/l0_bank_state.py`):**
| 方法 | 6k | 32k | 64k | 262k | 庫大小(facts) |
|---|---|---|---|---|---|
| **ours**(保守) | 100 | 98 | 95 | 92 | 455→18324(隨長度長大) |
| **mem0+ours storage**(破壞性) | **51** | **49** | **41** | (262k 排除*) | 219/1162/2076(較小,刪除縮水) |
| **mem0**(native) | 0 | 0 | 0 | 0 | 0(抽不到) |
> **★ 殺手論證:破壞性 baseline 的 L0(整庫)== L1(檢索 top-100),每個長度完全相等** → **損失發生在 write-time(庫裡就沒有新版),不是檢索**(若是檢索問題 L0 會 > L1)。ours 的庫保有新版(95-100%),破壞性更新在 write-time 不可逆刪掉約一半。*dest 262k 排除(prohibitive 被殺在 53/531 chunk 的殘缺 run)。**Zep 不納入**(非破壞性:raw episodes 留全版 → 庫恆 both,無 write-time 毀損可測)。

**E-rec(`F_recoverable`,irreversibility killer)— 新版仍可救率(both+new_only @L1,% of has_pair):**
| 方法 | 6k | 32k | 64k | 262k |
|---|---|---|---|---|
| **ours**(保守) | **100** | **98** | **95** | **92** |
| (b)mem0+P1(破壞性) | 51 | 49 | 41 | ⚠ |
| (a)vanilla | 0 | 0 | 0 | 0 |
> *Observation*:**ours 保守寫入 → 新版幾乎全可救(92-100%);mem0 破壞性更新在 write-time 即永久丟掉 ~一半新版(~50%)、不可逆;vanilla 抽不到 → 0。* → intro 主張①的直接證據。

**E-L1(`F_L1_state_pie`,**圓餅 grid,取代舊 `F_L1_state`**)— has_pair L1 檢索態組成(vector-memory 方法;full-fact 比對):**
- **ours**:都是 **both**(新版可救 **100/98/95/92%** 跨 6k→262k)。
- **mem0(b)**:**old_only + neither(新版 write-time 永久丟失)隨長度增長** → 可救率 **51→49→41%**(both 9/7/4、new_only 29/25/23、old_only 14/11/14、neither 22/22/25)。
- **vanilla**:全 **neither**(native 抽不到)。
- **★ Zep 誠實排除**:Zep 的 fact/edge 層**新舊兩版幾乎都當有效 edge 留著**(`invalid_at` 鮮少作動,實測 edges 35/40 both)、措辭異於 GT → **無法在檢索層嚴謹歸因 GT_old/GT_new**;故此診斷只比 **vector 記憶形式**,Zep 改以 overall EM(Table 1)+ 機制註記比較。

**E-L1L2(`F_ours_L1L2_pie`,**圓餅,取代舊 `F_ours_L1L2`**)— ours 解析前後**:L1 **both 100/98/95/92%** → **L2 收斂成 new_only 70/85/86/79%**(6k 52/74、32k 55/65、64k 57/66、262k 61/77)。green(both)→blue(new_only)的轉換 = **query-time 解析價值的量化**(且這是 mem0(b) 做不到的——它在 write-time 已毀掉一版)。

**E4(`F_state_to_em`)— final-context 狀態 → EM(pooled 全方法×長度,has_pair;script `e4_state_to_em.py`):**
| 最終狀態 | EM |
|---|---|
| **new_only**(只剩新版) | **287/302 = 95%** |
| both(新舊並存) | 39/59 = 66% |
| old_only | 1/46 = 2% |
| neither | 20/362 = 6% |
> *Observation*:**答對率幾乎完全由最終 context 狀態決定**(new_only→96%,其餘→低)。*Implication*:整場遊戲就是「把 context 收斂成 new_only」——ours 靠保守寫入(新版可救)+ query-time 解析做到;破壞性 baseline 卡在 old_only/neither 而不可逆。**完整因果鏈閉環**:E-rec → E-L1 → E-L1L2 → E4。

**圖檔**:`figures_current/F_recoverable.png`、`F_L1_state.png`、`F_ours_L1L2.png`、`F_state_to_em.png`(+ `F_robust_haspair` / `F_overall` / `F_ablation`)。

---

## Table 3 — Latency(M.C. / Q.E.,Table-12 式)
見 `experiment_results.md` §1.4(完整 provenance 表)。重點(M.C. total = benchmark `memory_construction_time` × 100 queries;✓ 實測):
- mem0(b) M.C. **32k 4843s=ours 2.3×、64k 8610s=ours 2.05×**;262k 估 **≈13hr**(coupled 不 scale,prohibitive)。
- ours M.C. 6k/32k/64k/262k = 476/2102/4208/17041s(262k=**4.73hr 實測**,保守寫入但 single-pass)。
- vanilla M.C. 快(262k 1058s=17.6min)**只因抽≈0條**(⚠ caveat,非真省)。
- ours 以 Q.E. ~30s/q(query-time 解析)換正確,vs baselines ~1-2s/q → 量化 intro「write-time 省成本/query-time 換正確」取捨。

---

## Narrative arc ↔ Table / Figure

| intro 主張 | 用哪個 Table/Figure 證 |
|---|---|
| ① 破壞性寫入丟掉衝突(且 write-time 成本高) | **Table 2**((a)→(b):抽取補好但破壞性仍丟半)+ **Table 3**(mem0 write-time 貴且不 scale) |
| ② 保守寫入 + query-time 解析救回 | **Table 2**((b)→(c) +41/46pp)+(待)L1→L2 context-state 圖 |
| ③ robust:長度 / 弱模型 | **Figure F_robust_haspair**(ours flat vs 全部隨長度/設計崩);(待)能力軸 dose-response |
| ④ 機制(為什麼贏) | (待)final-context 純度(ours vs Zep 多顆粒洩漏)+ Zep fact-level KU(invalid_at 少作動) |
| 系統定位(不是只在 niche) | **Table 1**(贏 LCA/RAG-family)+ Zep/mem0(同類) |

---

## 待補(完成後填上表的 ⚠/🔄)
1. ✅ **mem0(b) 64k 完成**(has_pair 41 / overall 58;M.C. 8610s=ours 2.05×;E-rec 可救 41%)→ Table 1/3/E-rec 已補實測;262k 仍估算(prohibitive)。
2. ✅ **Zep 64k 完成**(has_pair 44/66=67 / overall 78;同 runner bare-raw-q k=10 多顆粒;ingestion 130 episodes 全收齊,edge-recall 13/15)→ Table 1 已補。**262k 仍 prohibitive**(cloud 端 1/15@1hr)。Zep has_pair 非單調 68→55→67(真實,64k 多 episodes 回升)。
3. ✅ **L1→L2 context-state 圖**已產(`F_recoverable`/`F_L1_state`/`F_ours_L1L2`,mem0-family);**待加 Zep / LCA state**(Zep 需重存分顆粒度 context;LCA 全塞→ both 恆在,失敗純推理)。
4. **state→Acc(E4)**:L3 數據已在 `state_eval_current.json`,待繪(各 L2 態 × EM)。
5. **final-context 純度(E5)**:ours vs Zep 多顆粒洩漏,Zep 檢索 json 有分顆粒度資料可算。
6. **能力軸 dose-response**(強/中/弱 model × ours/mem0(b)/Zep)= intro ③ 決定性圖,**尚未跑**。
7. **LongMemEval KU**(Zep 主戰場)。
