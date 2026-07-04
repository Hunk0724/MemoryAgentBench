# FC-SH 6k has_pair — (S,P) 合併歸因 + rescue/未隔離案例紀錄

> 目的:回答「12b 99% 是 P2 抽取全成功?還是 L1/L2 救的?」以及把「pool 同時給新舊兩版、reader 挑到新版」的 rescue 案例逐題記錄。
> 產生:`analysis/attribute_sp_merge_6k.py`(離線讀 triple cache,不需 embedding/store/GPU)。
> 日期:2026-07-04(新 code:normalize L1/L2 + fact-level ordinal)。

## 1. 歸因表(每 has_pair 對的 old/new triple,其 (S,P) 靠哪一層對上)

| size | P2-exact | L1 | L2 | 未合併 | 離線合併小計 | **pool-based Resolution(權威)** | 一致? |
| :-- | :-: | :-: | :-: | :-: | :-: | :-: | :-: |
| 1b | 74 | 0 | 0 | 0 | 74 | **43** | ❌ |
| 4b | 74 | 0 | 0 | 0 | 74 | **48** | ❌ |
| 12b | 70 | 0 | 0 | 4 | 70 | **68** | ✅ 接近 |
| 27b | 70 | 0 | **1** | 3 | 71 | **69** | ✅ 接近 |

**判讀:**
- **12b 的高表現由 P2 抽取一致性驅動**(70 題 old/new 的 raw (S,P) 本來就相同),**L1=0、L2=0——normalize 在 12b has_pair 完全沒出力**。並非「P2 全成功」(仍有 4 題未合併),而是「一致到 raw (S,P) 直接對上」。
- **L1/L2 幾乎不在 FC-SH has_pair 出力**:全 size L1=0;L2 只有 27b **1 筆**(見 §3)。→ FC-SH 的 workhorse 是「抽取一致 + (S,P) exact」,不是 normalize。(normalize 的價值預期在措辭更雜的 **LongMemEval** 才會顯現——待驗。)
- ⚠ **離線 (S,P)-cache proxy 只在 12b/27b 對得上 pool-based Resolution;1b/4b 完全不符(74 vs 43/48)。** 這代表此 proxy 測的是「那一對 old/new triple 的 (S,P) 一致性」,**不等於 pool 隔離**。弱模型低 Resolution 的真正機制**需 query-time retrieved pool(embedding)才能定論**,此處不臆測。

## 2. 12b 未合併/rescue 案例(離線可確定)

未合併 = old/new 的 (S,P) 不同 → 兩版都留 pool → reader 決定。皆因 **P2 predicate 抽取不一致/抽壞**:

| qid | NEW (S,P,O) | OLD (S,P,O) | EM | 結果 |
| :-- | :-- | :-- | :-: | :-- |
| q8 | (Japan, **"is"**, Swedish) | (Japan, **"has language"**, Japanese) | ✅ | RESCUE(reader 挑到新) |
| q35 | (USA, **"is"**, German) | (USA, **"has official language"**, American English) | ✅ | RESCUE |
| q40 | (University of Bucharest, **"is located in"**, Ankara) | (…, **"has headquarters in"**, Bucharest) | ✅ | RESCUE |
| **q45** | (A Wizard of Earthsea, **"is author of"**, Pius XII) | (…, **"is written by"**, Ursula K. Le Guin) | ❌ | **WRONG**(reader 挑錯) |

> ⚠ pool-based `compute_resolution` 對 12b 記 **6 題未隔離(5 rescue + q45)**;離線只抓到 **4 題(3 rescue + q45)**。差 2 題 = 「cache 的 (S,P) 對上、但 query-time pool 仍留舊版」(其他 retrieved fact 帶舊值)→ 需實際 pool 才能列出那 2 題。

## 3. 27b 的唯一 L2 命中(具體證據 normalize 有作用的一筆)

| qid | NEW (S,P) | OLD (S,P) | 靠哪層合併 |
| :-- | :-- | :-- | :-- |
| q70 | (AP1000, **"was produced by"**) | (AP1000, **"is produced by"**) | **L2**(copula `was/is → be`)→ 同 (S,P) → 合併 |

→ 這是 L2(copula 正規化)在 FC-SH 唯一救到的一筆;佐證 L2 邏輯正確、只是 FC-SH 觸發率極低。

## 3.5 ★ no_p5 ablation:P3 LLM grouping 的「能力梯度」(headline)

`ours_no_p5`(struct + P3 LLM identity grouping,P5 關)vs `ours_struct`(純 struct)6k has_pair EM:

| size | struct | no_p5 | Δ | 判讀 |
| :-- | :-: | :-: | :-: | :-- |
| 1b | 29/74 | **25/74** | **−4** | P3 對弱模型**淨傷害**(亂合併) |
| 4b | 54/74 | 54/74 | 0(diff=4 互抵) | 中性 |
| 12b | 73/74 | 73/74 | 0(逐題全同,grouping 99/100 空) | no-op |
| 27b | 65/74 | **70/74** | **+5** | P3 對強模型**淨幫助**(正確合併,壓抑 reader-override,EM 65→70≈Res 69) |

**結論(修正先前「P3 是 no-op」的以偏概全——那只在 12b crossover 點成立)**:
- **P3 LLM grouping 的效果隨 backbone 能力單調變號:弱(1b)有害 → 中(4b/12b)中性 → 強(27b)有益**。
- 而**確定性 structural core 全程穩定**。→ 直接量化支持論文主張:**結構錨定 backbone-robust;LLM-based judgment 在弱模型崩壊(且主動有害)**。
- 對「P3 能否 rescue 4b/12b」的答案:**不能**(中性);P3 的價值是 **capability-gated**。
- per-query diff:1b `[4,24,26,49,59,62,63,74,98]`、4b `[1,35,51,70]`、27b `[7,12,19,53,54,63,72,80]`(12b diff=0)。

## 4. 待補(需 embedding,已備 `compute_resolution_per_query_6k.py`,讀 OPENAI_API_KEY_FOR_GX10)
- 1b/4b Resolution 43/48 的真正機制(pool 為何未隔離)。
- 12b 那 2 題額外未隔離 + 完整 5 題 rescue 清單。
- 方法:`compute_resolution_acc_6k.py` 加 per-query dump(需 `OPENAI_API_KEY_A` embedding)。
