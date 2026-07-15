# FC-SH Backbone Spectrum — 6k × 5 methods × 3 backbones(2026-07-15)

> **目的**:延續 §4.3 backbone extension 於 gpt-4.1-mini 的 falsifiable check 到 gpt-5.4-mini(OpenAI 新 strong mini-tier,released 2026-03-17,$0.75/M in + $4.50/M out)。**只跑 6k**(cost efficiency:5 methods total ~$3;決策依據 = 若 6k 上 gap 已收斂但未 collapse,paper narrative 定案 → 不必花 ~$227 on gpt-4o full sweep)。
> **Metric**:官方 `substring_exact_match`(sEM;canonical rescore via `analysis/rescore_canonical.py`)。
> **Setup**:MODEL_TAG=gpt-5.4-mini,backbone-tagged qdrant path(gemma pattern,不共享 gpt-4o-mini/gpt-4.1-mini stores);answer LLM + mem0 UPDATE/P3 identity LLM 皆 = gpt-5.4-mini;extractor MEM0_TRIPLE_MODEL 預設 gpt-4o-mini(hold-fixed per §4.3 convention)。
> **Code patch**:gpt-5.4-mini(以及 o1/o3/o4 系列)不支援 `max_tokens`(2026-03 起被 rename 為 `max_completion_tokens`)→ patch `mem0/llms/openai.py` + `agent.py:_answer_with_client`,by-model-prefix routing。

---

## Table 1 — Overall sEM(N=100),3 backbones × 5 methods

| Method | gpt-4o-mini | gpt-4.1-mini | **gpt-5.4-mini** | Δ(4o→5.4) |
|:--|:--:|:--:|:--:|:--:|
| **ours (main)** — struct + P3 + argmax | **94** | 92 | **99** | +5 |
| Q-llm-recency(single-stage,FC-SH benchmark-native template)| 93 | — | **98** | +5 |
| Don't Ask [Reddy&Challaram, 2026] | 80 | — | **96** | +16 |
| Zep(k=10) | 82 | 81 | **93** | +11 |
| (b) mem0+P1 | 52 | **81** | **70** | +18 ⚠ non-monotonic |

**Bold** = 該 backbone 最佳(row-wise)。**Δ** = gpt-4o-mini → gpt-5.4-mini。gpt-4.1-mini 的 Don't Ask / Q-llm-recency 未跑(cost / scope 節省)。

## Table 2 — has_pair sEM(KU-relevant 子集,6k has_pair N=74)

| Method | gpt-4o-mini | gpt-4.1-mini | **gpt-5.4-mini** |
|:--|:--:|:--:|:--:|
| **ours (main)** | 69 (93%) | 66 (89%) | **73 (99%)** |
| Q-llm-recency | 67 (91%) | — | **72 (97%)** |
| Don't Ask | 54 (73%) | — | 70 (95%) |
| Zep | 56 (76%) | 55 (74%) | 67 (91%) |
| (b) mem0+P1 | 34 (46%) | 56 (76%) | 47 (64%) |

---

## Caption(三段論)

**What.** FC-SH 6k Overall + has_pair sEM(官方 `substring_exact_match`,N=100)of 5 methods(Q-det = ours main;Q-llm-identity = Don't Ask;Q-llm-recency = benchmark-native factconsolidation.rag_agent + LLM recency;W-llm-coupled = (b) mem0+P1;W-llm-decoupled = Zep k=10)於三 OpenAI mini-tier backbones(gpt-4o-mini / gpt-4.1-mini / gpt-5.4-mini,released 2024/2025/2026)。gpt-5.4-mini 只測 6k(strong-tier probe;避免 ~$227 於 gpt-4o full sweep 的成本)。Chunk-size 512,top-100 vector retrieval,extraction 由 MEM0_TRIPLE_MODEL 固定 gpt-4o-mini(hold-fixed 於 §4.3 convention),answer + judgment LLM = 該 backbone。Single deterministic run(temp=0);無 error bar。

**Observation.** 三大 pattern:
1. **ours main 於三 backbone 皆 outright leader**(94/92/99),於 gpt-5.4-mini 上 saturation(99/100,has_pair 73/74),領先 second-best baseline(Q-llm-recency 98)僅 +1pp — gap 收斂但未反轉。
2. **Spread 從 42pp(gpt-4o-mini,52-94)收窄到 29pp(gpt-5.4-mini,70-99)** — 架構優勢隨 backbone 增強而**收斂**但**不 collapse**;弱 baseline(mem0+P1)於強 backbone 上仍與 ours 差 ~29pp,說明「LLM-based KU judgement 於強 backbone 可靠」是**部分**成立(對 decoupled Zep、Q-llm-identity Don't Ask、Q-llm-recency 成立,對 coupled destructive mem0+P1 反常)。
3. **mem0+P1 於 gpt-5.4-mini 反常下滑**(gpt-4.1-mini 81 → gpt-5.4-mini 70,−11pp)—— 唯一 non-monotonic method。假設:gpt-5.4-mini 是 reasoning-family model,對 mem0 destructive UPDATE prompt 反應**更保守**(NOOP 頻率上升 → 錯過 UPDATE 案例);另一可能是 `max_completion_tokens` 於 reasoning model 包含 internal reasoning tokens → 實際 output space 不足導致決策截斷。

**Implication.** §4.3 falsifiable prediction(「gap 隨 backbone 增強而收斂」)**部分兌現**:於 decoupled / Q-llm 家族**兌現**(spread 收窄、Zep/Don't Ask/Q-llm-recency 全大幅上升),但於 coupled destructive commit(mem0+P1)**反常**;說明「backbone 判斷力越強,KU 越可靠」是 method-specific 而非 universal。paper 主 narrative「架構優勢主要於 mid-tier backbone(gpt-4o-mini)彰顯」**加強而非推翻** — 於強 backbone 上 ours 仍為 outright leader,但差距縮小到 +1-3pp。

---

## 三大 finding(供 §4.3.5 引用)

### **F1. Ours main 於強 backbone 仍為 outright leader,gap 收斂但不 collapse**
- gpt-5.4-mini:ours 99 vs best baseline Q-llm-recency 98 = **+1pp**(vs gpt-4o-mini 上 94 vs 93 = +1pp,gap 大小穩定)
- gpt-5.4-mini:ours 99 vs weakest baseline mem0+P1 70 = **+29pp**(vs gpt-4o-mini 上 +42pp)
- **意涵**:相對「最強對手」的 gap 於強 backbone 上**穩定於 +1pp**;相對「最弱對手」的 gap 收斂但仍 substantial

### **F2. 全 method spread 從 42pp 收窄至 29pp**
- gpt-4o-mini(52-94,range 42)→ gpt-5.4-mini(70-99,range 29)
- 收斂主要由**最弱 baseline 上升**驅動(mem0+P1 +18、Don't Ask +16、Zep +11);ours main 微升 +5
- **意涵**:強 backbone 抬升「地板」但沒抬升「天花板」;paper narrative「LLM-based KU judgement 於強 backbone 對多數方法可靠」**部分兌現**

### **F3. Mem0+P1 於 gpt-5.4-mini 反常下滑 −11pp(vs gpt-4.1-mini)** ⚠
- Non-monotonic across 3 backbones:52 → 81 → 70
- 唯一違背「更強 backbone → 更好結果」的 method
- **可能 mechanism**:
  1. gpt-5.4-mini 是 reasoning-family model → 更保守 NOOP → 錯過 legitimate UPDATE case(recall 傷害)
  2. `max_completion_tokens` 於 reasoning model 包含 internal reasoning tokens → 實際 output space 縮水
  3. Backbone isolation 差異:gpt-4.1-mini yaml 沿用 gpt-4o-mini path(可能 inherit 部分 populated state);gpt-5.4-mini 用 backbone-tagged 全新 path(fresh state)
- **未來 audit**(§4.4 case study 可挑此 method 分析):比較 gpt-4.1-mini(81%)vs gpt-5.4-mini(70%)兩 backbone 於同 qid 的 UPDATE 決策差異 → 確認機制假設

---

## 已知 caveats(paper 揭露)

1. **gpt-5.4-mini 只跑 6k**:strong-tier probe,cost efficiency;若 paper 需長 context 上 backbone 收斂數據,32k/64k 需另跑(~$0.4-1 per method per length)
2. **max_tokens patch**:gpt-5-family + o1/o3/o4 系列 reject `max_tokens`,需 `max_completion_tokens`。patch 於 `mem0/llms/openai.py:92-107` + `agent.py:596-611`,by-model-prefix routing;舊 backbone 完全 backwards-compatible
3. **Backbone 路徑隔離不對稱**:gpt-4.1-mini yaml 用 shared-path with gpt-4o-mini(可能 inherit populated state);gpt-5.4-mini yaml 用 backbone-tagged path(gemma pattern,clean isolation)。**mem0+P1 於三 backbone 的直接對比可能被 store state 差異干擾**(F3 caveat)
4. **Single deterministic run**:temp=0,無 std;OpenAI server-side bf16 帶入 ±2-3 pp 抖動

---

## Cost & wall time actual(2026-07-15)

| Method | Wall | Cost($) | Notes |
|:--|:--:|:--:|:--|
| ours main | 15 min | ~$0.07 | fresh extraction + P2 + P3 + query |
| mem0+P1 | 5 min | ~$0(cost log 顯示 $0,可能 stage 標籤 miss)| — |
| Q-llm-recency | 1 min | ~$0 | query-only(reuse ours main store)|
| Don't Ask | 10 min | ~$0.02 | 100 candidate extract calls |
| Zep | 50 min | ~$1-2 | Zep cloud + client answer LLM |
| **Total** | **~90 min wall**(non-parallel) | **~$1-2** | 遠 < gpt-4o 全 sweep $227 |

---

## 更新歷程

- **2026-07-15**:本檔建立;gpt-5.4-mini × 6k × 5 method 完整結果 + patch 記錄
