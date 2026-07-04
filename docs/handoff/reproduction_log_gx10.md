# GX10 重現紀錄 — Weak-Model Regime FC-SH（gemma3 1b/4b/12b）

> 對應 [reproduction_log_mac_studio.md](reproduction_log_mac_studio.md);這份是 **ASUS Ascent GX10（NVIDIA GB10 Superchip）上跑 gemma3 weak-model matrix** 的單機紀錄。
> 驗證主張:**LLM 元件（P3 grouping + P5 conflict-type）貢獻隨 backbone 變弱而下降、structural-only 平穩** → 弱 model 上甚至 **ours < ours_struct（LLM 反害）**。
> **27b:6k 已跑(struct 59/74、p3_only 14/74 — 見 backbone 曲線節);32k/64k 因 ingest 爆炸(312s/chunk）跳過**（2026-07-02）。

---

## 機器 + 環境

| 項 | 值 |
| --- | --- |
| 機器 | ASUS Ascent GX10,**NVIDIA GB10 Superchip**(Grace 20-core ARM + Blackwell GPU) |
| 架構 | **aarch64**(★ 非 x86_64;handoff §2.1 的 installer 需改) |
| 記憶體 | 119 GiB **unified**(CPU+GPU 共用) |
| OS / GPU | Ubuntu kernel 6.14,CUDA 13.0,driver 580.95.05 |
| Python | 3.10(miniforge3 **aarch64** → `~/miniconda3` symlink) |
| Conda env | `MABench`,`requirements-core.txt` 釘版 |
| 關鍵套件 | **torch 2.12.1+cu130**(aarch64 CUDA13 wheel,意外可用且含 GPU)、transformers 5.12.1、langchain-core 1.4.8、editdistance 0.8.1 |
| Ollama | 0.13.0(library=CUDA,compute 12.1 Blackwell,iGPU 119.6GiB),client 0.6.2 |
| Backbone | `gemma3:{1b,4b,12b}` Q4_K_M,temperature 0 |
| num_ctx | **實際 4096**(daemon 預設;`OLLAMA_NUM_CTX=8192` 未傳進 mem0 ollama provider)→ 對所有 size 一致,FC-SH 多數 prompt 在 4096 內(caveat 見下) |
| Embedding | OpenAI `text-embedding-3-small`(隔離 LLM 變數,只切 backbone) |
| 日期 | 2026-07-01 |

---

## GX10 適配改動（branch `exp/gx10-weak-model`,**mac 版完全不動**）

1. **miniforge installer**:`x86_64` → **`aarch64`**(handoff §2.1 盲點;`uname -m=aarch64` 證實)。
2. **`tools/sample_resource_linux.sh`**(新增):Linux `/proc`-based sampler(mac 版 `sample_resource.sh` 用 `vm_stat`/`top -l`/`sysctl`,在 Linux 採空值);`run_gemma_matrix.sh` 加 `uname` 分支選用,**JSONL schema 不變** → `summarize_resource.py` 零改、mac 可攜性保留。
3. **`mem0/embeddings/openai.py` `embed_batch`**(robustness fix):弱 model(gemma)偶爾吐**空字串 fact** → OpenAI embedding 回 `400 input cannot be an empty string` → 整個 chunk batch + run 掛(1b 64k 撞到、1min 就死)。修法:空/空白字串換單一空格 placeholder,**保持與呼叫端 `new_retrieved_facts`/`triples`/`_fact_embs` 的 index 對齊**,該 blank fact 變語意惰性(永不 match 真實 query),**非空 fact 零影響 → gpt-4o-mini 結果完全不變**。

---

## 主表 — `gemma3:1b` FC-SH（has_pair / overall / time）

每格:`has_pair` / `overall/100` / `wall-time`。num_ctx 4096,temp 0。

| 長度 | ours | ours_struct |
| :---: | :---: | :---: |
| **6k** | 10/74 / 27 / 47min | **28/74** / 47 / 1min |
| **32k** | 14/65 / 39 / 97min | **26/65** / 47 / 2min |
| **64k** | 22/66 / 45 / 87min | **27/66** / 50 / 3min |

> 64k 是修掉空-fact bug 後重跑的(原始 run 在 64k ingest 撞空 fact 掛掉)。

---

## ★ Ablation trend — ours vs ours_struct（核心發現）

| 長度 | 1b ours hp | 1b struct hp | **Δ(struct−ours)** | 對照 gpt-4o-mini（Mac Studio）Δ |
| :---: | :---: | :---: | :---: | :---: |
| 6k | 10/74 (13.5%) | 28/74 (37.8%) | **+18** | 0(69=69) |
| 32k | 14/65 (21.5%) | 26/65 (40.0%) | **+12** | −6(ours 57 > 51) |
| 64k | 22/66 (33.3%) | 27/66 (40.9%) | **+5** | −3(ours 60 > 57) |

**觀察(what / observation / implication):**
- **what**:gpt-4o-mini 上 ours ≥ struct(LLM 元件加分或持平);**1b 上 struct > ours 全長度**(Δ +18/+12/+5)。
- **observation**:從 gpt-4o-mini → 1b,**ours 暴跌**(69→10、57→14、60→22),struct 跌得溫和(69→28、51→26、57→27)。Δ 隨長度**遞減**(18→12→5)。
- **implication**:弱 model 的 **LLM grouping/conflict-type 不只失效、還反害**(把純結構能答對的搞砸)。短 context 反害最重(structural 已足、LLM 多此一舉引入 noise);長 context structural 本身也難,反害空間縮小。**→ structural 是 robust workhorse,LLM 元件是「強 model 的 bonus、弱 model 的 liability」**,正是 weak-model regime 主張。

---

## 資源（1b,`sample_resource_linux.sh`）

| | mean | peak |
| --- | :---: | :---: |
| RAM used(total) | 7.9 GB | 9.1 GB |
| ollama VRAM(1b loaded) | 1.19 GB | 1.21 GB |

→ 遠低於 119GB unified,**serial 一次一個 model、用完即 `ollama stop`**,對同機其他使用者零風險。

---

## 時間（1b 實測,精校 Stage D 預估）

- **ours**:6k 47min / 32k 97min / 64k 87min(ingest 主導,弱 model 抽取 ~29s/chunk + query ~13s/題)。
- **ours_struct**:1–3min(reuse `extraction_cache_p1`,query 純結構、無 P3/P5)。
- 1b 完整 ~4hr。粗外推 **4b ~10hr、12b ~27hr**(gen tok/s 196→78→29)。

---

## Caveats

1. **num_ctx 實際 4096**(非設計的 8192):`OLLAMA_NUM_CTX` 環境變數沒被 mem0 ollama provider 採用。對所有 size 一致(隔離性仍成立),64k 也跑通(無致命 truncation),但長 context 可能有 silent truncation。**若要嚴格對齊 8192 需在 yaml 的 `mem0_config.llm.config` 加 `num_ctx`,屆時所有 size 需一致重跑。** 目前保持 4096 一致。
2. **confidence 多為 0.0**(弱 model 填 JSON 不穩,handoff caveat 1)— 不影響功能(method 無 confidence gate)。
3. GX10 數字屬「本機重現 + weak-model 探索」,**不入 paper baseline**。

---

## ★ p3_only vs ours_struct — grouping backbone 曲線(6k,2026-07-01)

新 method `ours_p3_only_no_struct`(P3 LLM identity grouping,無 (S,P)、無 P5)vs `ours_struct`。寫入相同(reuse extraction cache),只差 query-time grouping 方式。**這是比 ours-vs-struct 更 apple-to-apple 的「grouping 該用結構還是 LLM」對比。**

| backbone | struct has_pair | p3_only has_pair | Δ | struct time | p3_only time |
| :-- | :-: | :-: | :-: | :-: | :-: |
| 1b | 28/74 (37.8%) | 5/74 (6.8%) | +31pp | 1min | 92min |
| 4b | 50/74 (67.6%) | 26/74 (35.1%) | +33pp | 1min | 94min |
| 12b | 69/74 (93.2%) | 45/74 (60.8%) | +32pp | 24min | 54min |
| **27b** | **59/74 (79.7%)** | **14/74 (18.9%)** ↓↓ | **+61pp** | 64min | ~160min |
| gpt-4o-mini(Mac,Table 3)| 93.2% | 91.9% | +1.3pp | — | — |

> 27b 的 struct/p3_only 是「自建 cache」(該 backbone 沒先跑 ours),64min 含完整 ingest;純 query 端 struct 一樣 ~1min。

圖:`figures_current/F_p3only_vs_struct_backbone_6k.png`

**觀察(兩個獨立發現,勿混談):**
- **【發現 1:記憶機制】structural >> LLM grouping,gap 橫跨全 gemma、27b 拉到 +61pp**:struct 38→68→93→80、p3_only 6.8→35→61→**19**。struct 與 p3_only **共用同一 27b answer LLM**,故 answer-override 是共模、被抵銷 → **兩者 gap 乾淨隔離 grouping 貢獻**。27b 上 **p3_only 的 46 題失敗純粹是 grouping 的錯**(struct 對、p3 錯、100% 送舊值,見下 2×2)。**LLM 對 top-100 一次判 identity 太複雜、27b 也崩;(S,P) 機械分群零失誤 → structural anchoring 對 local 部署必要。**
- **【發現 2:answer-time confound,非機制】** 27b 的**絕對準確度**(struct 80、p3_only 19)被壓低,主因是 FC-SH 的 new 值刻意反事實、**27b 在生成端拒絕覆述**(見「為什麼 27b 反降」節)。這是 knowledge-conflict / faithfulness 問題,**與 KU 記憶機制正交**,不可當成 grouping/struct 的失敗。struct 的機制本身在 27b **沒因 grouping 損失**(它的 15 題失敗幾乎全落在這 confound)。
- **p3_only 又慢**:1b 92 / 4b 94 / 12b 54 / 27b 158min(vs struct query 端 ~1min)——對 100 candidates 一次判 identity、生成不穩大 JSON。這是「LLM grouping 不適合 on-device」的第二重(時間)證據。

### ★ 27b 反降的兩個獨立成因(2×2 拆解,已釘死)

用 **struct 當「完美 grouping」對照**(同一批 27b extraction cache、同一 retrieval,只差 grouping 方式),把 p3_only 的失敗一刀切開:

| | p3_only 對 | p3_only 錯 |
| :-- | :-: | :-: |
| **struct 對** | 13 | **46** ← 純 grouping 成本 |
| **struct 錯** | 1 | **14** ← 共模 confound |

- **46 題 = 純 grouping 失敗**:這些題 struct 明明答對(證明 retrieval 撈到 new、answer LLM 也肯講 new),p3_only 唯一差別是 LLM grouping → **46/46 全部把舊值送進答案**(new=0、garbled=0)。**LLM 對 top-100 一次判 identity 太複雜、27b 也照崩;(S,P) 機械分群零失誤。**
- **14 題 = answer-override confound**(下節,非 grouping 的錯):兩者都錯,其中 12 題 struct 也輸出「世界一致舊值」。

> 修正前一版誤植:曾寫「27b = 參數先驗在 grouping 覆蓋 freshness」。實測拆解後,**grouping 失敗(46)與 answer-override(12)是兩個不同階段的成因**,不可混談。

### 12b struct 答對(69/74)機制:靠「一致性」非「對應 GT」

| 機制 | 題數 |
| :-- | :-: |
| 同 (S,P) 且 predicate 字面對應 GT | 51 |
| **同 (S,P) 但措辭≠GT(內部一致改寫)** | 16 |
| 不同 (S,P) 卻仍答對 | 2 |

**97% 靠「new/old 被抽成內部一致的同 (S,P)」,非字面對應 GT。** 實例:q19 弱 model 抽 predicate `has CEO`(GT 為 `chief executive officer of … is`),但 new/old 一致 → 同 (S,P) → 取新 → 答對。**→ structural 只需「一致性」不需「語意理解」**(詳見 [weak_model_case_study.md](../0615_intro_framework_after_problem_statement/paper_draft&materials/weak_model_case_study.md) §★)。

---

## ★ 資源 / 時間 profile 統整(deployment cost 權威來源)

> 全 GX10 / GB10、gemma3 Q4_K_M、temp 0、OpenAI embedding、num_ctx 4096、chunk 512、top-100。
> 數據來源:`logs/gemma_matrix_*_summary.md`(時間)+ `logs/gemma_resource/*.jsonl` → `summarize_resource.py`(資源)。

### A. 資源 by backbone(單 model 隔離、serial)

| backbone | Ollama VRAM(權重+KV) | 全機 RAM used peak | RAM mean | 占 119GB unified |
| :-- | :-: | :-: | :-: | :-: |
| gemma3:1b | 1.2 GB | 9.1 GB | 7.9 GB | ~1% |
| gemma3:4b | 5.1 GB | 12.6 GB | 12.1 GB | ~4% |
| gemma3:12b | 10.5 GB | 21.0 GB | 17.5 GB | ~9% |
| gemma3:27b | 19.7 GB | 28.9 GB | 26.8 GB | ~17% |

> RAM used 含全機 baseline(其他使用者 ~5–8GB);VRAM 是 ollama 實報 `size_vram`。**峰值最重的 27b 也只吃 ~29/119GB → 對同機他人零風險。** 早期 12b/27b 的 resource log(160908/180226)因多 run 重疊被汙染(peak 顯示 28.9、models seen 混 4 種),上表採**乾淨隔離 run**(214618 / 230520)。

### B. 時間 by method(三類 method 成本差一個數量級)

| cell | **ours**(full P1–P5) | **ours_struct** | **p3_only** |
| :-- | :-: | :-: | :-: |
| 1b 6k | 47 min | 1 min¹ | 92 min |
| 1b 32k | 97 min | 2 min¹ | — |
| 1b 64k | 87 min | 3 min¹ | — |
| 4b 6k | 98 min | 1 min¹ | 94 min |
| 4b 32k | 102 min | 2 min¹ | — |
| 4b 64k | 95 min | 3 min¹ | — |
| 12b 6k | (未單跑) | **24 min²** | 54 min |
| 27b 6k | (未單跑) | **64 min²** | **158 min** |

¹ **1min 級 struct = reuse 了同 cell 先跑的 `ours` 建好的 extraction cache**,query 端純結構、無 LLM call。
² **12b/24min、27b/64min 的 struct 是「自己從零建 cache」**(該 backbone 沒先跑 ours)→ 含完整 ingest;純 query 端一樣 ~1min。

### C. 成本結構三個關鍵事實

1. **成本幾乎全在 ingest(P1 逐 chunk 抽取)**:`ours` 一個 cell 47–102min 幾乎都在寫入端;structural query 端只要 ~1–3min。
2. **generation 速度隨 size 崩**:gen tok/s **196(1b)→78(4b)→29(12b)→~15(27b)**;27b × 32k 實測 **312 s/chunk**(單 cell 估 8–12hr)→ 32k/64k 放棄的直接原因。
3. **p3_only 是唯一「query 端也昂貴」的 method**:1b 92 / 4b 94 / 12b 54 / **27b 158**min —— 對 top-100 candidates 一次生成大 identity-cluster JSON,弱/大 model 又慢又不穩。**這條時間曲線本身就是「LLM identity grouping 不適合 on-device」的第二重證據**(第一重是準確度非單調崩)。

---

## ★ 為什麼 27b 反降?兩個獨立成因(已用證據釘死)

**現象**:struct 93→**80**↓、p3_only 61→**19**↓↓,只在 gpt-4o-mini 回到 93/92。拆解後是**兩個不同階段、彼此獨立**的成因,不可混為一談。

**先排除的假設**(有證據):
- ❌ 抽取壞掉 → 27b cache **455 facts、零空 fact**,與 12b(456)幾乎一樣;抽樣 13 題,new/old 都抽得**與 GT 一致、彼此同 (S,P)**(見下例)。
- ❌ model 整體變笨 → 27b **non-has_pair 25/26 正常**;崩潰只在衝突題。
- ❌ retrieval 沒撈到 new → q19 的 **input_len 27b=2083 ≈ 12b=2065**,new fact("Steve Jobs")確實在兩者的 knowledge pool 裡。

### 成因 A:answer-time 反事實拒絕(壓低「絕對準確度」;非記憶機制)

**證據(q19,struct,兩者都選對了新版 fact,只差生成)**:prompt **明文**要求「answer **only** from the knowledge pool… **rather than the real facts in real world**」(還附反事實範例:俄國總統=Donald Trump)。

| | new(反事實) | 27b 輸出 | 12b 輸出 |
| :-- | :-- | :-- | :-- |
| q19 CEO of Microsoft | Steve Jobs | **Satya Nadella**(違抗指令、吐真實) | Steve Jobs ✓ |
| q34 Christianity 建於 | Taipei | **Jerusalem** | Taipei ✓ |
| q31 Ernst Heinkel 國籍 | Tang Empire | **Germany** | Tang Empire ✓ |

**13 題「12b 對、27b 錯」中 10 題如此**:27b 世界知識太強,拿到反事實正解 fact 時**在生成端拒絕覆述、改吐世界一致舊值**,即使 struct 已正確選到新版、prompt 明文叫它只用 pool。**這是 context-vs-parametric knowledge conflict / faithfulness 問題,與 KU 記憶機制正交**,只是被 FC-SH「new=反事實」的設計放大。**推論反而強化 weak-model 主張:12b 更 faithful 於解析後的記憶 → 弱 model 不只便宜,還更「聽話」。**

### 成因 B:LLM identity grouping 崩(壓低 p3_only 的「相對」表現;真·機制證據)

用 struct 當完美 grouping 對照,2×2 拆 p3_only 的 60 個衝突題失敗:

| | p3_only 對 | p3_only 錯 |
| :-- | :-: | :-: |
| **struct 對** | 13 | **46**(純 grouping 成本) |
| **struct 錯** | 1 | 14(= 成因 A 共模,12/14 struct 也吐舊值) |

- **46 題純 grouping**:struct 對(retrieval 有 new、answer LLM 肯講 new),p3_only 唯一差別是 LLM grouping → **46/46 全送舊值**。27b 對 top-100 一次判 identity 依然崩;(S,P) 機械分群零失誤。
- struct 與 p3_only 共用同一 27b answer LLM → 成因 A 是**共模、在兩者相減時抵銷**,故 **struct vs p3_only 的 gap 乾淨隔離 grouping**。

**對論文的意義**:
- **主張(相對、confound-controlled)**:local LLM identity grouping 不可靠(27b 仍崩、46 題純 grouping 失敗),structural (S,P)+serial 機械式、backbone-robust → **structural anchoring 對 on-device 部署必要**。這條**不受成因 A 影響**。
- **附帶發現(誠實揭露)**:強 model 在 answer-time 拒絕反事實更新,是 KU 之外的 faithfulness 現象;它壓低 27b 絕對分數,但**不是 struct/grouping 機制的失敗**。撰稿時兩者須分開陳述,避免把 confound 當成機制證據。

---

## 完成度 / 待補
- ✅ **6k backbone 曲線完成**(1b/4b/12b/27b × struct/p3_only + gpt-4o-mini 參照),圖 `F_p3only_vs_struct_backbone_6k.png` 已含 27b。
- ✅ **27b 反降已拆解釘死(兩個獨立成因)**:成因 B = LLM grouping 崩(46 題純 grouping 成本,struct 對照隔離)= 真機制證據;成因 A = 27b answer-time 拒絕反事實(共模 confound,~12 題)= 與機制正交,已誠實分開陳述。見「為什麼 27b 反降」節。
- ⏸ **32k backbone**(p3_only 在強端 +6 的 sweet-spot 翻轉)因 27b ingest 過慢(312s/chunk、單 cell ~8–12hr)暫緩。
