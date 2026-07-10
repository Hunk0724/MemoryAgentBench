# Canonical FC-SH E2E metrics — single source of truth

> **產生方式**:[`analysis/rescore_canonical.py`](../../../../analysis/rescore_canonical.py)(2026-07-10)。
> 從每格**唯一 canonical 檔**的 raw `output` + `answer`,以 MemoryAgentBench 官方
> `normalize_answer` + `parse_output` + `max(raw, parsed)` 語意重算,限 `has_pair` 分母。
> 資料檔:[`analysis/results/canonical_fc_sh_metrics.json`](../../../../analysis/results/canonical_fc_sh_metrics.json)。

## 三個 metric 的定義

| Metric | 定義 | 角色 |
|:--|:--|:--|
| **correct-sEM**(主)| `gt_new` 為 response 子字串 **且** `gt_old` surface **不**在 response | **paper 主 metric**(2026-07-10 定案):格式穩健 + 排除 hedge |
| strict EM | `normalize(pred) == normalize(gt_new)`（含 parse_output）| 對照(對 verbose 答案偏嚴)|
| official SubEM | `normalize(gt_new) in normalize(pred)` | MemoryAgentBench 官方 CR metric(對 hedge 偏鬆）|

**為何主 metric 用 correct-sEM(而非官方 SubEM 或 strict EM)**:
- ours / mem0 / LCA 答案精簡,**三 metric 幾乎全等**(差 ≤1)→ 對主 claim 無影響。
- **只有 Zep 三者分岔**(verbose 答句):
  - strict EM **系統性低估** Zep(把「Goaltender is associated with the sport of pesäpallo.」判錯)——原 benchmark README 正因此把 CR 官方 metric 設為 substring。
  - 官方 SubEM **系統性高估** Zep(把 hedge「... USA **and** Denmark」判對)——對 KU 不誠實。
  - **correct-sEM 兩者兼顧**:verbose-correct 算對、hedge 算錯;比官方 substring 更嚴、對 KU 更忠實。

## Canonical 表(cell = `correct-sEM / N`;括號 = strict EM | official SubEM)

### gpt-4o-mini(mid tier,主 regime)

| Method | 6k (N=74) | 32k (N=65) | 64k (N=66) |
|:--|:--|:--|:--|
| **ours (main)** | **69 (93%)** ‹69\|69› | **57 (88%)** ‹57\|57› | **60 (91%)** ‹60\|60› |
| ours (no P3) | 67 (91%) ‹67\|67› | 52 (80%) ‹52\|53› | 58 (88%) ‹58\|58› |
| ours (+P5) | 68 (92%) ‹68\|68› | 55 (85%) ‹55\|56› | 60 (91%) ‹60\|60› |
| (b) mem0+P1 | 34 (46%) ‹34\|34› | 25 (38%) ‹25\|26› | 34 (52%) ‹34\|34› |
| **Zep (k=10)** | **55 (74%)** ‹46\|56› | **39 (60%)** ‹33\|45› | **41 (62%)** ‹36\|42› |
| LCA | 65 (88%) ‹65\|65› | 46 (71%) ‹46\|46› | 36 (55%) ‹36\|36› |

### gpt-4.1-mini(strong tier,falsifiable-prediction check)

| Method | 6k (N=74) | 32k (N=65) | 64k (N=66) |
|:--|:--|:--|:--|
| **ours (main)** | 66 (89%) ‹66\|66› | 51 (78%) ‹51\|52› | 54 (82%) ‹53\|54› |
| (b) mem0+P1 | 56 (76%) ‹56\|56› | 53 (82%) ‹53\|53› | 55 (83%) ‹55\|55› |
| **Zep (k=10)** | 48 (65%) ‹46\|55› | 21 (32%) ‹20\|42› | 24 (36%) ‹23\|50› ⚠ |

⚠ **gpt-4.1-mini Zep 64k**:該 backbone×length **無官方 main.py 檔**,僅 `backbone_swap` custom 檔;上表數字為該檔 raw output 之官方重算(strict/SubEM 與 paper 既有 23/50 一致,correct-sEM=24)。

## 對 paper 敘事的關鍵意涵(correct-sEM 揭露、其他兩 metric 遮蔽的訊號)

**Zep 隨 backbone 增強而真實退化,correct-sEM 才看得清:**

| Zep correct-sEM | 6k | 32k | 64k |
|:--|:--|:--|:--|
| gpt-4o-mini | 74% | 60% | 62% |
| gpt-4.1-mini | 65% | **32%** | **36%** |

- strict EM 於 mid-tier **不公**(低估 verbose-correct),official SubEM 於 strong-tier **被 hedge 灌水**(4.1-mini 32k SubEM=65% 掩蓋真實 32%)。
- **只有 correct-sEM 同時避開兩種偏誤**,呈現 Zep 的真實 KU 能力:mid→strong **不升反降**(74→65、60→32、62→36),印證「decoupled labeling + inference 讀時間戳」於強 backbone 反被 verbose hedge 拖累。

**對主 claim 無衝擊**:ours vs mem0 三 metric 全等,gap(mid-tier)維持 +47/+50/+39pp(6k/32k/64k);ours vs Zep 縮為 +19/+28/+29pp(仍明顯勝)。
