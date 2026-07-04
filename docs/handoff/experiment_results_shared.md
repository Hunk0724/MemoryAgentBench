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
| GX10 | gemma3:{1b,4b,12b,27b} | FC-SH | 6k | ours_p3_only (LLM only) | _TBD_ | | | | | | | 預期 top-100 過載仍弱 |
| Mac | gpt-4o-mini | FC-SH | 6k | ours_struct / no_p5 / p3_only | _TBD_ | | | | | (API) | | pull 後重驗(target struct ~69/74) |
| Mac | gpt-4o-mini | FC-SH | 6k | Zep / Mem0 | _TBD_ | | | | | (cloud) | | baseline |
| Mac | (大模型待定) | FC-SH | 6k | ours_* / Zep / Mem0 | _TBD_ | | | | | (API) | | 預期 prior work 略贏 |
| … | … | … | 32k/64k/262k | … | _TBD_ | | | | | | | 同長度湊齊後往長 |

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
