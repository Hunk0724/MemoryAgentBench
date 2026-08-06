# Backbone / local-model 論述修正參考(2026-07-19 討論整理)

> 用途:修正 `paper_experiment.md` 中對 cross-family / local-model backbone 的錯誤論述。
> 核心結論:**論文宣稱 cross-family 用「held-fixed gpt-4o-mini extraction」是錯的。實際上所有 local model 都是 per-backbone extraction(每個 backbone 用它自己跑我們的 extraction)。真正的對照軸是 across-method(同 backbone 內共用該 backbone 自抽的 bank),不是 across-backbone 固定到 gpt-4o-mini。**

---

## 1. Ground truth:每組實驗實際跑了什麼

| 實驗組 | paper 現在宣稱 | 實際 | 狀態 |
|---|---|---|---|
| gemma3 4 tier (1B–27B) | per-backbone | per-backbone | ✅ 正確 |
| **cross-family (llama/qwen/gemma2/mistral)** | held-fixed gpt-4o-mini | **per-backbone(各自抽)** | ❌ 要改 |
| OpenAI tier (gpt-4o-mini / gpt-5.4-mini) | held-fixed gpt-4o-mini | gpt-5.4-mini 也自抽,但與 gpt-4o-mini 等價(僅句尾句點差異) | ⚠ 措辭不精確但無害 |

**local model 上的抽取分工(除 Zep、vanilla Mem0):每個 backbone 用它自己跑我們的 fact extraction + triple extraction,同 backbone 內所有 method 共用這一份 bank。**

---

## 2. 鐵證:四個 cross-family model 有各自獨立、fact 數不同的 extraction cache

6k P1 fact 數(`analysis/results/p1_caches__<model>/extraction_cache_p1_6k.json`):

| backbone | 6k P1 fact 數 |
|---|---|
| gpt-4o-mini | 455 |
| llama3.1-8b | **338**(−26%) |
| qwen2.5-7b | 451 |
| gemma2-9b | 455 |
| mistral-7b | 452 |

- 若真 held-fixed,四者會共用同一份 455 筆 gpt-4o-mini bank;實際是四份不同的、各 backbone 自抽。
- `p1_caches__llama3.1-8b/` 內含 `triple_cache` / `subject_cache` / `grouping_cache` → 連 triple extraction、(s,p) 結構輸入都是 per-backbone。
- narrative 佐證:`paper_current/narrative/experiment.md:358–360`(Table G5)白紙黑字「全 per-backbone 部署(P1 抽取=該 backbone 自身);P1 抽取數:llama 338 / qwen 451 / gemma2 455 / mistral 452」。

### 2.1 逐檔 fact-set 驗證(2026-07-19 實跑,確認非格式假象)

對 6 份 6k extraction cache 做兩兩 fact-set 比對:

| 檢查 | 結果 | 意義 |
|---|---|---|
| 任兩份是否 byte-identical | **全部 different**(raw Jaccard 0.046–0.599,無一 = 1.0) | held-fixed/複製會使各份與 gpt-4o-mini 完全相同(Jaccard=1.0、455 筆);實際沒有 → 各自獨立抽取 |
| fact count | 455 / 338 / 451 / 455 / 452(gpt-5.4 455) | 數量就不同 |
| 檔案大小(B) | 26117 / 18847 / 25656 / 26001 / 25295 | byte 數都不同 |
| **llama 語意層是否真少抽** | **缺 gpt-4o-mini 的 152 筆(33%),另多抽 35 筆** | 非格式差異,是真的抽漏(normalized Jaccard 僅 0.618) |

llama 漏抽的是實打實 MQuAKE facts,例:`association football was created in the country of england`、`buddhism was founded by gautama buddha`、`canada is located in the continent of north america`。

**Nuance(誠實記下):** raw Jaccard 低有一部分來自格式(句尾句點、大小寫)。normalized 後強 model 收斂高(qwen vs gpt-4o-mini 0.944、gpt-5.4-mini 0.932 → 語意幾乎相同,只格式不同),**但 llama normalized 仍只 0.618 = 真退化**。這不動搖 per-backbone 結論:格式差異本身即代表「各自重跑過抽取」(複製不會重新格式化),llama 的語意差異則證明弱 backbone 抽取實質退化 —— 兩者都指向 per-backbone。

**復現指令:** 逐檔比對腳本見對話紀錄(讀各 `p1_caches__<model>/extraction_cache_p1_6k.json`,flatten 成 fact list,算 pairwise Jaccard 與 raw/normalized 集合差)。

---

## 3. 根因:兩種「held-fixed」被搞混

你的 §M-6「共用抽取鎖」真實語意 = **同一 backbone 內,所有 method 共用「該 backbone 自抽」的 P1 bank**。

- ✅ 真:held-fixed **across methods**(method 之間不因抽取多寡占便宜)→ method 比較公平。
- ❌ 假:held-fixed **to gpt-4o-mini across backbones**(把 extraction 品質固定住)。

paper 把前者誤寫成後者。**全論文沒有任何「跨 backbone 把 extraction 固定在 gpt-4o-mini」的實驗。**

---

## 4. 正確的論述軸(取代 held-fixed)

**「per-backbone 共用該 backbone 自抽 bank → 每個 backbone 上 method 比較都公平 + ours 自身分數下界 recall → baseline 落後來自 KU 判斷。」**

### 4a. 公平性掛在共用 bank 上,不依賴 bank 品質
同 backbone 內 ours / Vanilla-RAG / Don't Ask / Mem0+P1 用**同一份** bank,差異只在 KU 判斷那一步。就算 llama 抽得爛(338 筆),大家用同一份爛 bank → 比較仍公平。**這在每個 backbone 都成立,不需要 held-fixed。**

### 4b. 用 ours 自己的分數推出 recall 足夠(不必假設「抽全」)
共用 bank + retrieval → **ours 在該 bank 上的分數 = bank 內 gt 覆蓋率的下界**(這招你在 `paper_experiment.md:138` 對 gpt-4o-mini 已用過)。
- llama 上:ours=**81**,Vanilla-RAG=70,Mem0+P1=8,同一份 338 筆 bank。
- ours 能到 81 → bank 至少含 81% query 的正解 → baselines 落到 70 / 8 **不能歸因於少撈**,只能是 KU 判斷失效。

### 4c. 必須把兩個層次切開(否則變成新的錯誤)

| | 成立嗎 | 說明 |
|---|---|---|
| (a) 同 backbone 內 method 比較 | ✅ 永遠公平 | 共用該 backbone 自抽 bank,差異只在 KU 判斷 |
| (b) ours 跨 backbone 的絕對值 | ⚠ 仍受 extraction 品質污染 | llama 的 81 有一部分被它自己 338 筆爛 bank 壓低(對照 gpt-4o-mini 94) |

原本 paper 錯在宣稱 cross-family 靠 held-fixed 讓 (b) 也乾淨。**(b) 從沒被隔離**,跟 gemma3 tier 一樣有 extraction confound(你在 269 行對 gemma3 已誠實揭露,cross-family 要比照,不能說「cross-family 不含此 confound」)。

---

## 5. 例外清單(不套用「共用該 backbone 自抽 bank」的 method)

| method | 例外原因 | 出現在哪組表 |
|---|---|---|
| **vanilla Mem0** | 用自己 write-time coupled 抽取(單次 ADD/UPDATE/DELETE/NOOP),非我們的 | gemma3 tier、main;**不在 cross-family 表** |
| **Zep** | graph 固定用 cloud gpt-4o-mini,只有 answer-gen 走本地 → 只反映 answer-gen 退化 | cross-family(narrative 版)、gemma3 tier |
| Don't Ask(非 extraction 例外,但要一起帶) | **沒有 answer-gen step**,直接輸出抽取欄位 → 跟它比時多一層 answer-gen 不對稱(gemma2-9B 上 Don't Ask 80 > ours 72 即此) | cross-family、gemma3 tier |

註:Mem0 + Fact Extraction(= Mem0+P1)**有**用我們的 extraction,不是例外。

---

## 6. `paper_experiment.md` 逐行要改清單

| 行 | 現在寫的 | 問題 |
|---|---|---|
| 70 | 「Cross-family…held-fixed gpt-4o-mini 承擔 extraction…僅換 query-time」+ 整段「兩組互補」 | 全錯;cross-family 與 gemma3 都是 per-backbone,「互補」對比基礎不存在 |
| 78 | 「Extraction 於 cross-family held-fixed 為 gpt-4o-mini」 | 錯 |
| 202 | 「cross-family…以 held-fixed extraction 隔離…淨影響」 | 錯 |
| 206(圖 caption) | 「右側 gpt tier held-fixed / 左側 gemma3 per-backbone」分區 | cross-family 也是 per-backbone,分區標示要改 |
| 209(小節標題) | `Cross-family Results with Held-fixed Extraction` | 標題直接錯 |
| 211 | 「採用 held-fixed gpt-4o-mini extraction…不含 extraction 品質變化…最受控」 | 錯 |
| 215(表 caption) | 「held-fixed gpt-4o-mini extraction」 | 錯 |
| **234** | 「Struct-Only 輸出的 Current Version(s) 於 4 backbone 上**完全相同**」 | **最嚴重:可證偽為假**(banks 不同 338/451/455/452 → 候選不同 → 輸出不同)。此句必刪或重寫 |
| 269 | 「cross_family 的 held-fixed 設定不含此 confound…可作 KU 判斷實際優勢參考」 | 錯;cross-family 也有 extraction confound |
| 271 | 「gpt-4o-mini 為 held-fixed extraction」(跨列註記) | 主 backbone gpt-4o-mini 本來就自抽,措辭一併看 |
| 275 / 279 | OpenAI tier「held-fixed gpt-4o-mini extraction」 | 技術上 gpt-5.4-mini 也自抽但等價;改「gpt-5.4-mini 抽取與 gpt-4o-mini 等價(僅標點差異)」或「extraction 品質相當」 |
| 299 | 「於 extraction 受控的 cross-family 上則張至 11 至 64 pp」 | 「extraction 受控」錯 |

---

## 7. 不用改的部分(安全)

- **abstract(paper_abstract.md:6)**、**introduction(paper_introduction.md:35)**、**methodology**:只做「KU 表現隨 backbone 能力減弱而退化、ours 退化較小」的一般主張,per-backbone 實驗支撐得起,**不受影響**。
- held-fixed / cross-family / per-backbone 字樣**只出現在 paper_experiment.md**,修正範圍收斂在單一檔案。

---

## 8. 待你決定的 framing 選項

1. cross-family 與 gemma3 都是 per-backbone,是否合併成同一「per-backbone 部署」大標題下的兩個 view(gemma3 = 同 family 能力階梯;cross-family = 固定 7–9B 換 4 family,證明是能力門檻非單一系列 quirk)?
2. 「隔離 KU 判斷 vs extraction」要保留(改掛第 4 節論述軸 + bank-swap invariance)還是砍掉(cross-family 純當跨 family robustness)?
   - bank-swap invariance 佐證:narrative experiment.md:356 —— Don't Ask bank 由 gpt-4o-mini 換成 gemma 自身,結果幾乎不變(27B 96→95、12B 84→84、4B 36→38、1B 2→1)→ 決策 LLM 才是瓶頸,與 bank 品質無關。
3. OpenAI tier 的 held-fixed 措辭要嚴謹化還是簡化。

---

## 附:cross-family 6k 結果(paper 版 Table,overall-100 SubEM %)

| Method | Gemma2-9B | Llama3.1-8B | Qwen2.5-7B | Mistral-7B |
|---|---|---|---|---|
| Mem0 + Fact Extraction | 27 | 8 | 21 | 19 |
| Vanilla-RAG | 38 | 70 | 27 | 26 |
| Ours (Struct-Only) | 71 | 81 | 83 | 64 |
| Ours (Struct + LLM-Fallback) | 72 | 81 | 91 | 66 |

narrative 版(experiment.md:362–369)另含 Don't Ask(llama 48 / qwen 42 / gemma2 80 / mistral 21)與 Zep(63 / 51 / 73 / 52)。
