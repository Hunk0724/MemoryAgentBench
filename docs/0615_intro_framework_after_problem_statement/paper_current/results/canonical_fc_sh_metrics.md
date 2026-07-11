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

## ⚠ 待補:weak-tier(gemma3 1B/4B/12B/27B)

gemma raw outputs 於 GX10,**本機 `outputs/` 無**,故上表未含 weak tier。
**GX10 action**:把 gemma run dir 加進 [`analysis/rescore_canonical.py`](../../../../analysis/rescore_canonical.py) 的 `REGISTRY`,重跑產出 gemma 的 **overall-100 官方 SubEM**,回填 §4.2.0 G1/G3、§4.2.3 Table 3、§4.5 Table 5b、§4.7 Table 6 的 gemma 欄(目前標 pending)。

## 已知殘餘不一致(與 metric 無關)

- **LCA 64k**:paper 舊值 38/66,canonical 重算為 **36/66**(strict 亦 36)→ 屬既存計數誤差,非 metric 造成;主表已更正為 36/54.5%(overall 65/100)。
