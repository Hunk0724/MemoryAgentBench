# Canonical FC-SH E2E metrics — single source of truth

> **產生方式**:[`analysis/rescore_canonical.py`](../../../../analysis/rescore_canonical.py)(2026-07-11)。
> 從每格**唯一 canonical 檔**的 raw `output` + `answer`,以 MemoryAgentBench 官方
> `normalize_answer` + `parse_output` + `max(raw, parsed)` 語意重算。
> 資料檔:[`analysis/results/canonical_fc_sh_metrics.json`](../../../../analysis/results/canonical_fc_sh_metrics.json)。

## Metric 與分母(2026-07-11 定案)

| 項目 | 定案 | 理由 |
|:--|:--|:--|
| **主 metric** | MemoryAgentBench **官方 `substring_exact_match`** | CR 任務官方判分(README §Clarification);對 Zep verbose 答句公平;對 ours/mem0/LCA 與 strict EM 差 ≤ 1 |
| **主分母** | **overall = 全 100 題** | 對齊 benchmark 官方 task accuracy;避免只報子集的 cherry-pick 觀感 |
| **分析分母** | **has_pair**(74/65/66)| KU 真正發生處;pool-state × Acc 歸因(§4.2.2)本就只能在 has_pair 上做 |

- 主表 / 主圖用 **overall 100**;has_pair 留給 §4.2.2 歸因與 §4.4 case study。
- strict exact-match 逐 cell 併列於 JSON,供對照(僅 Zep 兩者分岔)。

## Overall(全 100 題,官方 SubEM)— 主表數字

### gpt-4o-mini(mid tier,主 regime)

| Method | 6k | 32k | 64k |
|:--|:--|:--|:--|
| **ours (main)** | **94%** | **91%** | **94%** |
| ours (no P3) | 91% | 87% | 92% |
| ours (+P5) | 93% | 90% | 94% |
| (b) mem0+P1 | 52% | 52% | 65% |
| Zep (k=10) | 82% | 80% | 76% |
| LCA | 88% | 74% | 65% |
| **gap ours−mem0** | **+42pp** | **+39pp** | **+29pp** |

### gpt-4.1-mini(strong tier,falsifiable-prediction check)

| Method | 6k | 32k | 64k |
|:--|:--|:--|:--|
| **ours (main)** | 92% | 87% | 88% |
| (b) mem0+P1 | 81% | 87% | 88% |
| Zep (k=10) | 81% | 77% | 84% |
| **gap ours−mem0** | **+11pp** | **0pp** | **0pp** |

**falsifiable prediction 成立**:ours−mem0 gap 隨 backbone 增強收斂(mid +29~+42pp → strong 收至 parity)。

## has_pair(N=74/65/66,官方 SubEM)— 分析用(§4.2.2 / §4.4)

| Method × backbone | 6k | 32k | 64k |
|:--|:--|:--|:--|
| ours (main) × 4o-mini | 69/74 (93%) | 57/65 (88%) | 60/66 (91%) |
| (b) mem0+P1 × 4o-mini | 34/74 (46%) | 26/65 (40%) | 34/66 (52%) |
| Zep × 4o-mini | 56/74 (76%) | 45/65 (69%) | 42/66 (64%) |
| ours (main) × 4.1-mini | 66/74 (89%) | 52/65 (80%) | 54/66 (82%) |
| (b) mem0+P1 × 4.1-mini | 56/74 (76%) | 53/65 (82%) | 55/66 (83%) |
| Zep × 4.1-mini | 55/74 (74%) | 42/65 (65%) | 50/66 (76%) |

## Zep 於官方 SubEM 下為穩定 baseline(無戲劇崩潰)

| Zep overall | 6k | 32k | 64k |
|:--|:--|:--|:--|
| gpt-4o-mini | 82% | 80% | 76% |
| gpt-4.1-mini | 81% | 77% | 84% |

Zep 跨 backbone、跨長度平穩在 ~76–84%(decoupled labeling 有效但天花板低於 ours),**不因強 backbone 崩潰**。先前 strict-EM 下「Zep 於 gpt-4.1-mini × 64k 崩至 35%」為 verbose 答句被 strict 冤枉的格式假陰性,官方 substring 已修正(同格 = 84% overall / 76% has_pair)。

## weak-tier(gemma3 1B/4B/12B/27B,GX10,官方 SubEM)— 2026-07-11 回填

> GX10 **per-backbone gemma extraction**(`MEM0_TRIPLE_MODEL=gemma3:$SIZE`,非 held-fixed gpt-4o-mini;dir 名 `gpt-4o-mini-…__gemma3-{s}` 的 "gpt-4o-mini" 是 legacy template tag,見 [`weak_model_6k_analysis.md`](weak_model_6k_analysis.md))。主軸 = backbone spectrum @ 6k(全 method 完整);由 `rescore_canonical.py` REGISTRY 的 gemma tier 產出。

### Overall(全 100 題,官方 SubEM)@ 6k — 主表數字

| Method | 1B | 4B | 12B | 27B |
|:--|:--|:--|:--|:--|
| **ours (main)** = no_p5 | 44% | 79% | **99%** | **99%** |
| ours (no P3) = struct | 52% | 79% | 99% | 97% |
| ours (LLM only) = p3_only | 27% | 50% | 72% | 59% |
| ours (+P5) | 27% | 55% | — | — |
| (b) mem0+P1 | 5% | 11% | 64% | 54% |
| (a) vanilla | — | 11% | 53% | 45% |
| Zep (k=10) | 29% | 32% | 58% | 62% |

（32k,ours(main):1B 54% / 4B 70% / 12B 98% / 27B 98%;struct 32k 因早期 `_final` bug 未完整。）

### has_pair(N=74,官方 SubEM)@ 6k — 分析用

| Method | 1B | 4B | 12B | 27B |
|:--|:--|:--|:--|:--|
| ours (main) | 27 | 54 | 73 | **73** |
| ours (no P3) | 32 | 54 | 73 | 71 |
| ours (LLM only) | 8 | 26 | 46 | 33 |
| (b) mem0+P1 | 0 | 0 | 44 | 37 |
| (a) vanilla | — | 0 | 32 | 29 |
| Zep (k=10) | 20 | 18 | 43 | 42 |

### 觀察(backbone-gap / P3 capability-gate / metric 遷移)
1. **ours 於每個 backbone 主導**;write-time baseline(b/vanilla/Zep)於弱端崩最重(b=5%/11% @ 1B/4B)。
2. **P3 capability-gate**(main − no P3,overall):1B **−8pp**(反害)、4B/12B **0**、27B **+2pp**。
3. **SubEM 下「27B dip」大幅縮小**:strict-EM 下 no_p5/struct has_pair 為 70/65(/74),官方 SubEM 為 **73/71** → no_p5 幾乎無 dip(overall 99/99)、struct 僅 2pp。原 dip 有 3–6 題是 **verbose-correct 被 strict 冤枉**,非真 override;**真 override 殘留 struct ~3、no_p5 ~1 題**(qid 19/57 答舊值 SubEM 亦錯,見 [`weak_model_case_studies_6k.md`](weak_model_case_studies_6k.md))。
4. **1B/4B has_pair pool-state cross-tab 不可信**(per-backbone gemma 抽取字面偏移 → matcher FN)→ 用 E2E + case study(§ [`weak_model_6k_analysis.md`](weak_model_6k_analysis.md) §2)。

## 已知殘餘不一致(與 metric 無關)

- **LCA 64k**:paper 舊值 38/66,canonical 重算為 **36/66**(strict 亦 36)→ 屬既存計數誤差,非 metric 造成;主表已更正為 36/54.5%(overall 65/100)。
