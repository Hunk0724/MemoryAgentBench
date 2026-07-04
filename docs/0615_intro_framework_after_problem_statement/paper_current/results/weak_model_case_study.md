# FC-SH Weak-Model Case Study(gemma3 1b/4b/12b/27b,GX10 2026-07-02)

> **目的**:weak-model regime 下,structural `(S,P)`+temporal 的 KU 解析在不同大小 local backbone 的表現與答錯主因;並把**方法貢獻(Resolution)**與 **backbone reader 能力**分離。
> **核心結論**:
> 1. 用 **Resolution Accuracy**(解析後 pool 是否只含新版)看,方法貢獻 **42/44/60/60、頂端平、27B 不退步**;end-to-end EM(28/50/69/59)的起伏是 **reader 效應**(1B 太弱拖垮、27B override 拖垮、中段 reader 救)。
> 2. **12B 追平 gpt-4o-mini(93.2)** → 結構化 KU 判斷在 local model 就有效。
> 3. 殘餘錯誤**皆非 grouping 機制之過**:弱端抽取能力(recall + subject 抽反)、predicate canonicalization、**6k 專屬 ordinal-tie(可用 fact 級序號修)**、27B reader override。
> **⚠ p3_only(LLM-grouping)這條線目前無效**、不可入結論:ollama `num_ctx` 未設 + top-100 一次判過載 → grouping **100% 空群**;27B 對小 pool 其實分得對(§★.5)。
> **資料**:`outputs/.../__gemma3-{1b,4b,12b,27b}/.../results.json`(EM)、`analysis/results/{sh_6k_RUN_gt.json, resolution_vs_em_6k.json}`、qdrant `*_struct__gemma3-*` stores(Resolution 重算)。

---

## ★ 核心結果一:Resolution Accuracy 把「方法」與「reader」分離(6k)

end-to-end EM 混了兩件正交的事:**方法**(query-time KU 解析:pool 是否只留新版)與 **reader**(backbone 生成能否照 pool 答對)。拆開(N=74):

| backbone | **Resolution 正確**<br>(pool 只含新版) | **End-to-End EM** | reader 拖垮<br>(pool對·EM錯) | reader 救回<br>(pool未隔離·EM對) |
| :-- | :-: | :-: | :-: | :-: |
| 1b | **42/74 (57%)** | 28/74 (38%) | 15 | 1 |
| 4b | 44/74 (59%) | 50/74 (68%) | 1 | 7 |
| 12b | 60/74 (81%) | 69/74 (93%) | 0 | 9 |
| 27b | **60/74 (81%)** | 59/74 (80%) | 4 | 3 |

> EM = Resolution − 拖垮 + 救回(四列都對得上)。Resolution 用 word-boundary + subject-scoped 精確比對(避免 German/Germany 誤判、涵蓋 subject 抽反),與 fuzzy 結果一致。
> 圖:[`F_resolution_vs_em_6k.png`](../figures_current/F_resolution_vs_em_6k.png)(Resolution 實線 / EM 虛線,灰帶=reader 效應);struct EM 單線 [`F_struct_backbone_6k.png`](../figures_current/F_struct_backbone_6k.png)。

**三個關鍵論述:**
1. **Resolution(方法貢獻)頂端是平的:42→44→60→60**。一旦抽取夠好(12B 起),KU 解析飽和在 60/74,**backbone-robust、27B 零退步**。
2. **1B 的故事翻轉**:不是「方法只有 28」,而是「**方法解析對了 42/74,是 1B reader 拖垮 15 題**」——1B 拿到只含新版的乾淨 pool 仍讀不出答案(生成能力)。
3. **27B 的 end-to-end 反降(69→59)不在方法**:Resolution 60 = 12B 的 60(方法零退步),掉分**純粹是 reader override**(pool 已只含新版,27B 卻吐世界一致舊值,4 題)。
- reader 是雙向 wildcard:**1B 太弱往下拖(−15)、4B/12B 稱職會救(+7/+9)、27B override 往下拖(net −1)**——這是 backbone 特性,與 KU 方法正交。

## ★ 核心結果二:條件式 (S,P) 一致性(三關卡漏斗)

方法能不能解,取決於三道關卡(各欄分母已標明):

| backbone | ① both 抽到<br>(/74) | ② 同(S,P)<br>(/①) | ③ 同(S,P)+ord可分<br>(/①) | struct 實際答對(子群/①) |
| :-- | :-: | :-: | :-: | :-: |
| 1b | 48 (65%) | 36/48 (**75%**) | 33/48 (68%) | 22/48 (45%) |
| 4b | 53 (72%) | 39/53 (**73%**) | 34/53 (64%) | 39/53 (73%) |
| 12b | 74 (**100%**) | 71/74 (**95%**) | 61/74 (82%) | 69/74 (93%) |
| 27b | 74 (**100%**) | 71/74 (**95%**) | 61/74 (82%) | 59/74 (79%) |

- **① recall**:弱端第一道牆(1b 只 65%);12b/27b 100%。
- **② 同 (S,P) identity 一致性(給定①)= 核心指標**:強 model 95%、弱 model ~73–75%。**只要 triple 抽取一致,機械 (S,P)+temporal 就能解 KU,不需任何 query-time LLM。**
- **③ 再要 ordinal 可分**:12b/27b 從 95% 掉到 82%,全因 6k 的 ordinal-tie(下述)。

## ★ 錯誤模式(修正版):四類,皆非 grouping 機制之過

「struct 答錯」拆解(分母=各 size 答錯數):

| backbone | 錯 | (A) 抽取漏 new | (B) old已drop仍錯 | (C) ordinal-tie | (D) (S,P)-split |
| :-- | :-: | :-: | :-: | :-: | :-: |
| 1b | 46 | 17 | 16 | 3 | 10 |
| 4b | 24 | 10 | 1 | 4 | 9 |
| 12b | 5 | 0 | 0 | 3 | 2 |
| 27b | 15 | 0 | **4** | **8** | 3 |

**(A) 抽取 recall + (B) 生成/override**:弱端(1b A17/B16、4b A10/B1)是**模型能力**;(B) 在 1b=生成太弱、27b=參數 override(見核心結果一)。

**(C) ordinal-tie —— 6k 專屬 artifact,結構上與 backbone 無關:**
- tie = 新舊同 (S,P) 但拿到**相同 chunk-ordinal**(同 512-chunk)→ keep-all-on-tie 兩個都留。
- **tie 結構數 12b=27b=10(同樣那 10 題)**;表中「(C) 27b=8、12b=3」是**tie 造成答錯**的數,delta 全來自 reader:同 10 題,**12b 挑新 7/10、27b override 挑舊 8/10**。→ **tie 不是抽取變差,是 reader 在歧義下用先驗選舊。**
- 為何 6k 才嚴重:序號距離 |gt_seq−old_seq| 中位數 6k=144(24% 的對 ≤40 個 fact→可能同 chunk)、**32k=590(0% ≤40)** → 32k tie 率 1.6%,幾乎消失。
- **可修(fact 級序號)**:目前 ordinal 每 chunk 遞增一次(`main.py:313`),同 chunk 所有 fact 共用;改成 `chunk_ordinal*K+_fi`(`_fi`=抽取順序)即 fact 級。已驗證 8/8 tie 題 chunk 內 **old_idx<new_idx**(舊必在新前)→ 修法零反例。零 LLM 成本,query 端 `max()` 不動;唯一代價=re-ingest + 重驗主結果。修後估:27b 59→~67、12b 69→~72。

**(D) (S,P)-split —— canonicalization,分兩種:**
- **弱端(1b/4b):subject 抽反**(把「會變的值」當 subject)。實例 q47「Our Mutual Friend」:
  - 舊 `(charles_dickens, is author of, Our Mutual Friend)`、新 `(charles_darwin, is author of, Our Mutual Friend)` → subject 變兩個不同人 → 不同 (S,P)。正解 subject 應為 `our_mutual_friend`。**屬抽取能力。**
- **強端(12b/27b):subject 全對,只差 predicate 措辭**(3 題,subject 100% 一致):
  - 12b q45:`is written by` vs `is author of`(paraphrase);27b q70:`is produced by` vs **`was produced by`**(時態);27b q7:`is associated with` vs `...the sport of`(stem vs full)。**屬教科書級 canonicalization(時態/stem/paraphrase 正規化即可)。**

## ★ 為什麼曲線 rise-then-dip(1B→12B 升、27B 降)

- **上升(1B→12B):能力關卡逐步打開**——(A)抽取(17→10→0)+(B)生成(16→1→0)隨模型變強而消失,both-抽到 65%→72%→100%,12B 飽和追平 gpt-4o-mini。
- **下降(12B→27B):能力已見頂,是 reader 副作用**——**方法端(Resolution)60=60 沒退**;end-to-end 掉的 10 題 = **參數 override**(pure 4 + 把 tie 判成舊 +5)+ 1 split。**「弱 model can't(讀不出),強 model won't(不願採用 context 更新)」**;split/tie 的措辭與 chunk artifact 也隨規模略動,但主因是 reader。

## ★.5 p3_only(LLM-grouping)現況:confounded,不可入結論

`ours_p3_only_no_struct`(跳過結構路由、對 top-100 一次判 identity)在四個 size **grouping 100% 輸出空群**(`grouping_cache` 全 `[]`)→ 等於不做 dedup → 退化成 raw retrieval。診斷:
- `_ollama_chat` 用 `format:json`(排除 parse 失敗)、但**沒設 num_ctx** → top-100 的 ~3400-token prompt 被預設 ctx 截斷。
- probe:同一題 **pool 縮到相關 3 筆,27b 就正確分群**(reasoning 也對);num_ctx 拉 16384 部分題可救,但 100-pool 仍常空。
- **→ 這不是「弱 model 不會 grouping」,而是「沒有 structural pre-routing,LLM grouping 對 top-100 intractable」。反向確立 structural routing 的必要性。** p3_only 數字(6.8/35/61/19)作廢,待 num_ctx=8192 + 正確架構(structural 先、P3 只跑小 pool)重跑。

> 舊圖 `F_p3only_vs_struct_backbone_6k.png` 保留但**內含此 confound**,勿引用其 p3_only 曲線。

### 12b struct 答對(69/74)的機制拆解:靠「一致性」而非「對應 GT」

| 機制 | 題數 | 占比 |
| :-- | :-: | :-: |
| 同 (S,P) 且 predicate 字面就對應 GT | 51 | 74% |
| **同 (S,P) 但 predicate 措辭 ≠ GT(內部一致改寫)** | **16** | **23%** |
| new/old 不同 (S,P) 卻仍答對(其他機制) | 2 | 3% |

**97%(67/69)答對是靠「new/old 被抽成內部一致的同 (S,P)」,不是靠字面對應 GT。** 實例(內部一致但字面≠GT):

| qid | GT 的 predicate 字面 | 弱 model 實際抽的 predicate | 結果 |
| :-- | :-- | :-- | :-- |
| q5 | "The author of … is" | **"is author of"** | new/old 一致 → 同(S,P) → 取新 ✓ |
| q14 | "The author of … is" | **"is written by"** | 同上 ✓ |
| q19 | "chief executive officer of … is" | **"has CEO"** | 同上 ✓ |

**核心洞察**:structural robustness 來自它只要求「**一致性**」(弱 model 把 new/old 抽成同一措辭即可,機械式),**不要求「正確性 / 對應 GT」,也不要求「語意理解」**。這精確定義了 intro 的「decomposed **simple** tasks for weak model」——**一致性檢查 = simple(弱 model 做得到);語意 identity 判斷(p3_only)= complex(弱 model 崩)**。同一個 12b:做一致性 grouping 93%、做語意 grouping 只 61%。

---

## 1. (背景分析,1b/4b)has_pair 答題 Acc(最上層,先看這個)

| cell | has_pair | **ours Acc** | **struct Acc** | ours 落後 |
| :-- | :-: | :-: | :-: | :-: |
| 1b 6k | 74 | **14%** (10) | 38% (28) | −24pp |
| 1b 32k | 65 | **22%** (14) | 40% (26) | −18pp |
| 1b 64k | 66 | **33%** (22) | 41% (27) | −8pp |
| 4b 6k | 74 | **41%** (30) | 68% (50) | −27pp |
| 4b 32k | 65 | **42%** (27) | 68% (44) | −26pp |

**觀察**:
- **ours 全面輸 struct**(弱 model 上 LLM query 元件是 liability,非 asset)。
- **struct 從 1b ~40% → 4b ~68% 大幅上升** —— struct 的 query 端是 deterministic、不隨 backbone 變,**會變的只有 P1/P2 抽取**。所以這 28pp 的提升 = **抽取品質提升**。→ **「structural 平穩」只在跨長度成立;跨 backbone,P1/P2 是 struct 的天花板。**

---

## 2. ours 答錯主因(三桶)

母體 = ours 答錯的 has_pair 題,拆成互斥三桶:

| cell | ours錯 | ① 抽取沒抽全<br>(P1/P2) | ② P5 反害<br>(struct對→ours判反) | ③ 抽全卻錯<br>((S,P)/answer) |
| :-- | :-: | :-: | :-: | :-: |
| 1b 6k | 64 | **26** | 19 | 19 |
| 1b 32k | 51 | **22** | 13 | 16 |
| 1b 64k | 44 | **26** | 9 | 9 |
| 4b 6k | 44 | 14 | **22** | 8 |
| 4b 32k | 38 | 18 | **17** | 3 |

- **① 抽取沒抽全(P1/P2)= 最大宗(尤其 1b)**:new/old fact 沒進記憶 → **連 struct 都救不回**,這不是方法設計問題,是弱 model 底層能力。
- **② P5 反害 = `ours < struct` 的唯一直接來源(純 EM ground-truth,可信)**:struct 本來答對,ours 的 P5 判斷把它判反、**灌回舊值**(典型:問 Germany 在哪洲,struct 取最新 serial 答 `Africa`,ours 被常識先驗拉回答 `Europe`)。
- **dangerous middle**:4b 上 ② 反而變大(1b 19 → 4b 22),因為 4b 抽取變好、更多題「進得到 P5」,但 P5 仍不如強 model → 判反的絕對量更多。
- ③ 抽全卻錯:(S,P) canonicalize(predicate stem vs full form)/ answer LLM 太弱 / 亂答。

> **測量 caveat**:①/③ 的切分靠 triple 比對,弱 model 改寫措辭會造成假陰性(偏高估①);**②(P5 反害)是純 EM、不受影響**。絕對 P1/P2 recall 難用字串比對測準,但**跨 backbone 的相對趨勢(1b < 4b)穩健**。

---

## 3. 資源(時間 & RAM,GX10 GB10)

| model | ours/cell 耗時 | struct/cell(reuse cache) | RAM peak | ollama VRAM |
| :-- | :-: | :-: | :-: | :-: |
| 1b | 39–97 min | 1–3 min | 10.1 GB | 1.3 GB |
| 4b | 98–102 min | 1–2 min | 13.1 GB | 5.5 GB |
| 12b(預估) | ~4–5 hr | ~5 min | ~18 GB | 11 GB |

- **struct 的低耗時是「reuse 了 ours 建好的 extraction cache」** —— 若某 backbone 從未跑過,struct 仍要自己跑 ingest(= P1 抽取,隨 backbone 變慢),不是免費。
- **ours 的成本幾乎全在 ingest(P1 逐 chunk 抽取)+ query 端 100 題的 P3/P5/P4**。12b 一個 ours cell 就 ~4–5hr。

---

## 4. 對實驗方針的含意(這決定要不要繼續跑)

1. **真正的研究問題 = P1/P2 抽取的「轉折點」**:gemma3 4b/12b/27b 哪一級的 P1/P2 才夠好?**只有 P1/P2 夠好,才談得上公平比較 struct-grouping vs P3/P5 LLM-grouping** —— 否則(如 1b)結果被抽取雜訊主導,無法論述。
2. **便宜的探路路徑**:先評估各 backbone 的 **P1/P2 品質**(用現成 extraction/triple cache,或只跑 ingest),**不必先燒完整 ours 的 query 端**。確認抽取夠好的 backbone,再投入昂貴的完整 pipeline。
3. **長度**:趨勢在各長度一致(ours<struct);**先固定單一長度(32k)掃 backbone**,確定要在哪個 backbone 深入後,再決定其他長度。

---

## 5. 附:P5 反害的機制(保留)

`hurts` 題(struct 對、ours 錯)幾乎全是 `same-(S,P)`(1b 17/19、4b 20/22):代表 P1→P2→(S,P) 分群**全部成功**、struct `ordinal argmax` 明明能取到 new,**唯獨 P3/P5 這步把 new/old 判在一起後判錯 freshness、灌回 old**。這是 `ours<struct` 最乾淨的因果 —— LLM 元件是唯一多出來、且唯一搞砸的那一步。`normalize_predicate` 只做 lower/strip,故 predicate 的 stem(`is associated with`)vs full(`is associated with the sport of`)會拆成不同 (S,P) key,是 (S,P) canonicalize 的主要脆弱點。
