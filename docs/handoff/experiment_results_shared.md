# 共筆實驗結果紀錄(GX10 + Mac,可重現、公平比較)

> **目的**:跨機器共同記錄 KU 實驗。**程式碼 + 模型都可重現**(同 branch `exp/v2-llm-judge`、同 chunk 512 / top-100 / temp 0 / OpenAI embedding),所以**不論哪台跑的結果都公平、可一起觀察比較**。
> **填寫規則**:每跑完一個 cell 就在下方主表加一列(或更新 status)。改完 `git commit` 這個檔 + `git push`,另一台 `git pull` 即同步。**衝突就手動 merge 這個 md**(純表格,好合)。
> **機器分工**:
> - **GX10(這台,gemma local)**:gemma3 1b/4b/12b/27b。⚠ 27b × 長 context 極慢(32k ingest ~312s/chunk)→ **優先「同一長度先有全 backbone 結果」**,再往長。
> - **Mac(M2 Ultra)**:gpt-4o-mini(mid)、大模型(API)、Zep / Mem0(不需 local GPU)。
> - 最後更新:2026-07-04

---

## 設定維度(scope)

| 維度 | 選項 |
| :-- | :-- |
| **backbone** | 大模型(**待定**:GPT 最新 or Opus 最新)· 中模型 `gpt-4o-mini` · 小模型 `gemma3:{1b,4b,12b,27b}` |
| **dataset / length** | MemoryAgentBench **FC-SH** `6k / 32k / 64k / 262k`(時間關係:**同長度先湊齊,再往長**) · **LongMemEval KU** `128k` |
| **method / baseline** | `ours(struct+取最新)`=`ours_struct` · `ours(LLM+取最新)`=`ours_p3_only_no_struct` · `ours(LLM+struct+取最新)`=`ours_no_p5` · `Zep` · `Mem0` · **`ours-full(+P5)` 最後測**(多值/complementary 目前不在 scope) |
| **metric** | FC-SH:**has_pair EM**(主)+ **Resolution Acc**(方法端,pool 是否只含新版)+ overall/100;LME-KU:KU accuracy(官方 judge,驗證期 gpt-4o-mini) |
| **resource** | write-time(ingest)min · query-time min · VRAM peak · 全機 RAM peak |

> **★ KU 定義對齊**:我們此輪只對齊「**取最新版本事實**」(freshness / single-value)。**P5(conflict-type / arity guard)先關閉**(`MEM0_P5_SKIP=1`),多值 coexistence 不在目前 scope。

## 預期(hypothesis,填結果時對照)
- **大模型**:過去流派(Zep/Mem0 write-time)預期**略贏**我們(強 model 能力補足其 write-time 判斷)。
- **中 / 小模型**:我們方法(defer 到 query-time + structural 錨定)預期**更能駕馭**(prior work 隨 backbone 變弱而崩,ours 相對穩)。

---

## 主表(FC-SH)

> 每格:`has_pair EM (x/N)` / `Resolution (x/N)` / `overall (x/100)`。has_pair 分母:6k=74、32k=65、64k=66。

| machine | backbone | dataset | len | method | has_pair EM | Resolution | overall | write min | query min | VRAM peak | date | status / notes |
| :-- | :-- | :-- | :-: | :-- | :-: | :-: | :-: | :-: | :-: | :-: | :-- | :-- |
| GX10 | gemma3:1b | FC-SH | 6k | ours_struct | 28/74 | 43/74 | 47/100 | ~1(cache reuse) | ~1 | ~2 GB | 07-04 | ✅ 新 code。reader 太弱(drag 16>rescue 1)→ EM<Res |
| GX10 | gemma3:4b | FC-SH | 6k | ours_struct | 54/74 | 48/74 | 79/100 | ~1 | ~1 | 5.5 GB | 07-04 | ✅ 新 code。reader rescue +7 → EM>Res |
| GX10 | gemma3:12b | FC-SH | 6k | ours_struct | **73/74** | 68/74 | **99/100** | ~1 | ~1.5 | 11 GB | 07-04 | ✅ 新 code。sweet spot(reader 忠實+rescue)|
| GX10 | gemma3:27b | FC-SH | 6k | ours_struct | 65/74 | **69/74** | 90/100 | ~1 | ~2 | 19.7 GB | 07-04 | ✅ 新 code。Res 最高但 reader override(drag 7)→ EM 掉 |
| GX10 | gemma3:1b | FC-SH | 6k | ours_no_p5 (LLM+struct) | **25/74** | _need key_ | 42/100 | ~1 | ~5 | ~2 GB | 07-04 | ⬇ **vs struct −4**:P3 弱模型亂合併=傷害 |
| GX10 | gemma3:4b | FC-SH | 6k | ours_no_p5 (LLM+struct) | 54/74 | _need key_ | 79/100 | ~1 | ~8 | 5.5 GB | 07-04 | ＝ struct(4 題互抵,淨 0)中性 |
| GX10 | gemma3:12b | FC-SH | 6k | ours_no_p5 (LLM+struct) | **73/74** | _need key_ | **99/100** | ~1 | ~12 | 11 GB | 07-04 | ＝ struct **逐題全同**(grouping 99/100 空)no-op |
| GX10 | gemma3:27b | FC-SH | 6k | ours_no_p5 (LLM+struct) | **70/74** | _need key_ | **94/100** | ~1 | ~30 | 19.7 GB | 07-04 | ⬆ **vs struct +5**:P3 強模型正確合併,壓抑 reader-override |
| GX10 | gemma3:1b | FC-SH | 6k | b = mem0 destructive (ours extract) | **0/74** | — | 5/100 | ~1 | ~0 | ~2 GB | 07-04 | 💥 collapse:update-LLM 吐 "Name is John"×5,store 空 |
| GX10 | gemma3:4b | FC-SH | 6k | b = mem0 destructive (ours extract) | **0/74** | — | 10/100 | ~1 | ~0 | 5.5 GB | 07-04 | 💥 collapse(同上,弱模型 update 崩壊)|
| GX10 | gemma3:12b | FC-SH | 6k | b = mem0 destructive (ours extract) | 44/74 | — | 64/100 | ~19(write) | ~1 | 11 GB | 07-04 | update 開始能用,但仍 ≪ struct 73/99 |
| GX10 | gemma3:27b | FC-SH | 6k | b = mem0 destructive (ours extract) | 36/74 | — | 53/100 | ~45(write) | ~2 | 19.7 GB | 07-04 | 非單調回落(<12b);仍 ≪ struct 65/90 |
| GX10 | gemma3:1b | FC-SH | 6k | ours_p3_only (LLM only) | **7/74** | — | 26/100 | ~1 | ~90 | ~2 GB | 07-05 | 💥 grouping 0/100 空(1B 產不出合法 JSON);≪ struct 29 |
| GX10 | gemma3:4b | FC-SH | 6k | ours_p3_only (LLM only) | 26/74 | — | 50/100 | ~1 | ~4 | 5.5 GB | 07-05 | grouping 4/100;≪ struct 54(num_ctx=8192 clean)|
| GX10 | gemma3:12b | FC-SH | 6k | ours_p3_only (LLM only) | 46/74 | — | 72/100 | ~1 | ~22 | 11 GB | 07-05 | grouping 10/100;≪ struct 73(對照 Mac 4o-mini p3_only 71)|
| GX10 | gemma3:27b | FC-SH | 6k | ours_p3_only (LLM only) | 27/74 | — | 52/100 | ~1 | ~46 | 19.7 GB | 07-05 | 反常 <12b:grouping 53/100 但亂合併+override → 27<46 |
| — | | | | | | | | | | | | |
| Mac | gpt-4o-mini | FC-SH | 6k | ours (full P3+P5) | 68/74 | — | 93/100 | ~35 | ~40 | (API) | 07-04 | ✅ post-9ced3c2 |
| Mac | gpt-4o-mini | FC-SH | 6k | ours_struct | 67/74 | — | 91/100 | reuse | ~2 | (API) | 07-04 | ✅ post-9ced3c2(Δ -2)|
| Mac | gpt-4o-mini | FC-SH | 6k | ours_no_p5 | 69/74 | — | 94/100 | reuse | ~5 | (API) | 07-04 | ✅ post-9ced3c2(Δ +2)|
| Mac | gpt-4o-mini | FC-SH | 6k | **ours_p3_only** | **71/74** | — | **97/100** | reuse | ~10 | (API) | 07-04 | ✅ **post-9ced3c2(Δ +3,新最高)** |
| Mac | gpt-4o-mini | FC-SH | 6k | (b) mem0+P1(destr.)| 34/74 | — | 51/100 | ~35 | ~15 | (API) | 06-30 | ✅ 有效(不經 9ced3c2) |
| Mac | gpt-4o-mini | FC-SH | 6k | Zep(k=10)ᵇ | 46/74 | — | 72/100 | (cloud async) | ~2 | (cloud) | 06-30 | ⚠ Zep 全走 k=10(cloud 限)|
| Mac | gpt-4o-mini | FC-SH | 6k | LCA(long-ctx,no memory)| 65/74 | — | 88/100 | 0 | ~5 | (API) | 06-30 | ✅ 有效 |
| — | | | | | | | | | | | | |
| Mac | gpt-4o-mini | FC-SH | 32k | ours (full P3+P5) | 55/65 | — | 89/100 | ~65 | ~45 | (API) | 07-04 | ✅ post-9ced3c2(Δ -1)|
| Mac | gpt-4o-mini | FC-SH | 32k | ours_struct | 52/65 | — | 82/100 | reuse | ~4 | (API) | 07-04 | ✅ post-9ced3c2(Δ +1;Cat A 部分修)|
| Mac | gpt-4o-mini | FC-SH | 32k | ours_no_p5 | 57/65 | — | 92/100 | reuse | ~15 | (API) | 07-04 | ✅ post-9ced3c2(Δ +2)|
| Mac | gpt-4o-mini | FC-SH | 32k | **ours_p3_only** | **58/65** | — | **91/100** | reuse | ~20 | (API) | 07-04 | ✅ **post-9ced3c2(Δ +1,新最佳)** |
| Mac | gpt-4o-mini | FC-SH | 32k | (b) mem0+P1 | 29/65 | — | 61/100 | ~65 | ~25 | (API) | 06-30 | ✅ 有效 |
| Mac | gpt-4o-mini | FC-SH | 32k | Zep(k=10)ᵇ | 4/65 | — | 24/100 | (cloud async) | ~2 | (cloud) | 06-30 | ⚠ k=10 上限重傷 |
| Mac | gpt-4o-mini | FC-SH | 32k | LCA | 46/65 | — | 74/100 | 0 | ~10 | (API) | 06-30 | ✅ 有效 |
| — | | | | | | | | | | | | |
| Mac | gpt-4o-mini | FC-SH | 64k | ours (full P3+P5) | 60/66 | — | 94/100 | ~150 | ~45 | (API) | 07-04 | ✅ post-9ced3c2(Δ 0)|
| Mac | gpt-4o-mini | FC-SH | 64k | ours_struct | 58/66 | — | 92/100 | reuse | ~5 | (API) | 07-04 | ✅ post-9ced3c2(Δ +1)|
| Mac | gpt-4o-mini | FC-SH | 64k | ours_no_p5 | 60/66 | — | 94/100 | reuse | ~20 | (API) | 07-04 | ✅ post-9ced3c2(Δ 0)|
| Mac | gpt-4o-mini | FC-SH | 64k | ours_p3_only | 58/66 | — | 92/100 | reuse | ~25 | (API) | 07-04 | ✅ post-9ced3c2(Δ -1)|
| Mac | gpt-4o-mini | FC-SH | 64k | (b) mem0+P1 | 27/66 | — | 58/100 | ~150 | ~30 | (API) | 06-30 | ✅ 有效 |
| Mac | gpt-4o-mini | FC-SH | 64k | Zep(k=10)ᵇ | 36/66 | — | 70/100 | (cloud async) | ~2 | (cloud) | 06-30 | ⚠ k=10 上限 |
| Mac | gpt-4o-mini | FC-SH | 64k | LCA | 36/66 | — | 65/100 | 0 | ~15 | (API) | 06-30 | ✅ 有效 |
| — | | | | | | | | | | | | |
| Mac | (大模型待定) | FC-SH | 6k | ours_* / Zep / Mem0 | _TBD_ | | | | | (API) | | 預期 prior work 略贏 |
| … | … | … | 262k | … | _TBD_ | | | | | | | 6k/32k/64k 同長度湊齊後往長 |

**表格 caveats(對應上腳註):**
- **ours ablation post-9ced3c2 完成(2026-07-04)**。核心發現:
  - **ours_p3_only 是新的最佳 method**:6k 71/74(**95.9%**,史上最高)、32k 58/65(89.2%)、64k 58/66(87.9%)。**LLM identity clustering + fact-level ordinal + L2 normalize = 強組合**。
  - **ours_no_p5 全面接近或超越 full**:6k/32k no_p5 都超越 full(P5 對 FC 為負收益的直接證據)。
  - **struct 效果 mixed**:6k -2、32k +1、64k +1。L2 只 merge tense + article,不動 domain nouns(religion/country/sport)→ struct Cat A 只部分修好。
  - **paper 主 method 建議改為 `ours_p3_only`**(核心版無 struct、無 P5)。
- **ᵇ** Zep 全部 k=10(top-10 retrieval,Zep cloud rate 限制),與其他方法的 k=100 不對稱;32k 幾乎全崩(4/65)是 k=10 上限的直接後果。**Zep 建議未來加 chunk=4096 / k=100 補測**(未進行)。

## 主表(LongMemEval — KU,128k)

| machine | backbone | method | KU acc | judge | query min | date | status / notes |
| :-- | :-- | :-- | :-: | :-- | :-: | :-- | :-- |
| Mac | gpt-4o-mini | ours_no_p5 | _TBD_ | gpt-4o-mini | | | ★ P2b / subject-match 只在 LME 才測得到(FC triple-null=0%) |
| Mac | gpt-4o-mini | Zep / Mem0 | _TBD_ | gpt-4o-mini | | | baseline |
| GX10 | gemma3:* | ours_* | _TBD_ | gpt-4o-mini | | | local KU 泛化 |

---

## 已知 caveat / 待辦
- **P2b(subject fallback)+ query-time subject-match**:FC-SH triple-null=0% → **測不到**;要在 **LME-KU** 才會觸發 → **儘快跑完 FC 往 LME**。
- **fact-level ordinal + normalize** 已 landed(commit 9ced3c2)→ 所有 gemma store **需 full re-ingest**(run_fc_sh 已修 store-wipe path bug)。
- **Mac 重驗 gpt-4o-mini 主表不 regress**(has_pair 6k target ~68-69/74,±2-3)。
- **大模型 override confound**:FC-SH new 值反事實 → 大模型 answer-time 可能 override → 大模型公平對照**主打 LME(真實事實,無 override)**,FC 大模型並列報 Resolution Acc。
