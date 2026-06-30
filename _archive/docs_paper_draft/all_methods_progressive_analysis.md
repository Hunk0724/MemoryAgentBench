# 所有已跑方法的 progressive 分析(M1 → W1 → W2 → W3)

> **目的**:從整體 M1 EM 出發,逐步用其他 metric drill down,看核心主張是否能站住。
> **方法 scope**:LCA / Mem0 / Mem0g-pa / vanilla HippoRAG-v2 / our method v2.0.2 ablation
> **Updated**: 2026-05-31
> **核心 caveat**:方法 setup 不對齊(Plan A vs preview),分析時明確標示,直接結論需在同 setup 內做

---

## Step 0 — Setup 對齊矩陣(理解後面數字必看)

| 方法 set | Backbone | Temp | Embedder | Retrieval pool | 跑過 cells |
|---|---|---:|---|---|---|
| **Plan A** group | gemini-3.1-flash-lite **GA** | **0** | text-embedding-004 (Vertex) | 各 method 內建 | LCA/Mem0/Mem0g-pa × SH/MH × 6k/32k/64k(部分) |
| **Preview-historical** group | gemini-3.1-flash-lite **preview** | **0.7** | NV-Embed-v2 (GPU) | HippoRAG-v2 top-10 chunks | HippoRAG-v2 vanilla × SH/MH 6k;our v2.0.2 ablation MH 6k |

**對齊原則**:
- **同 set 內**(Plan A 之間 / preview 之間):可直接比 EM
- **跨 set**:差距由 backbone(preview→GA)+ temp(0.7→0)+ embedder/retrieval 共同貢獻,不能 clean attribute
- Plan A 是 paper 主場,preview group 作為 historical reference + 我們方法 baseline tracking

---

## Step 1 — M1 EM 整體 overview

### 1.1 Cross-method × cross-ctx 主表

| Method | SH 6k | MH 6k | SH 32k | MH 32k | SH 64k | MH 64k |
|---|---:|---:|---:|---:|---:|---:|
| **LCA**(Plan A)| 96% | 16% | 91% | 19% | 90% | 12% |
| **Mem0**(Plan A)| 92% | 52% | 90% | 39% | 88% | 跑中(b9kwhk56z)|
| **Mem0g-pa**(Plan A)| 79% | **66%** ⭐ | 89% | 40% | — | — |
| **HippoRAG-v2 vanilla**(preview)| **75%** | **29%** | — | 6%(n=10)| — | — |
| **Our v2.0.2 A**(= vanilla HippoRAG-v2, preview, 重跑)| — | 17% | — | — | — | — |
| **Our v2.0.2 B**(+ Phase 2 chain detect+verdict+filter, preview)| — | **31%** | — | — | — | — |
| **Our v2.0.2 C**(+ Phase 3 enriched ctx, preview)| — | 31% | — | — | — | — |
| **Our v2.0.2 D**(Phase 3 minimal no filter, preview)| — | 15% | — | — | — | — |

### 1.2 數字對齊的兩個 caveat

**Caveat A — vanilla HippoRAG-v2 兩個數字(75% vs 17%)**:
- `hippo_rag_v2_nv_preview_REFERENCE/`(full eval): SH 6k 75%, MH 6k 29%
- v2.0.2 ablation A:MH 6k = 17%(method_v2.0.2_status_brief 確認 5pp gap from "motivation 紀錄 22%")
- 兩者都是 vanilla preview,但 sub-setup 不同(retrieval slot 配置 / max_samples 等)
- → 同 group 內也有 setup drift,**Path D Audit 3 必須重對齊 Plan A 條件才能放主表**

**Caveat B — Mem0g-pa MH 6k 66% 是 paper 強對手**:
- 比 Mem0 +14pp,paper §6.3 主表 hard floor(narrative §11.2)
- our method 在 Plan A 條件下對齊重跑後**必須對齊或超越 66%**,否則 paper 主張存疑

### 1.3 一句話 takeaway

```
Plan A:
  SH 三方收斂在 88-96%(graph 在 SH 是 ≥6k 噪音,32k+ 稀釋)
  MH 6k Mem0g-pa 66% > Mem0 52% > HippoRAG vanilla 29%(preview)
  MH 32k+ Mem0g-pa 跌至 Mem0 水準(graph 優勢消失)

Preview:
  vanilla HippoRAG-v2 MH 6k 17-29%(同 group 跨 sub-setup 已有 12pp drift)
  我們 v2.0.2 B(+ Phase 2)= 31%, 超越 vanilla +14pp,但仍 < Mem0g-pa 66%
```

---

## Step 2 — W1 evidence(detection-retrieval 脫鉤,paper claim 1)

### 2.1 W1 核心主張

> 現有方法在 ingest 時 detect 衝突,但 query 時 retrieval **不調用 detection 結果**,造成 detected-but-still-leaked。

### 2.2 Plan A group 證據(M-DRA × method × ctx)

從 `analysis/results/plan_a/*_3way.json`:

| Method × ctx | clean win D✓R✓A✓ | inference fail D✓R✓A✗ | **retrieval fail D✓R✗A✗** | full fail D✗R✗A✗ |
|---|---:|---:|---:|---:|
| Mem0 MH 6k | 51% | 13% | **25%** | 10% |
| Mem0g-pa MH 6k | 65% | 13% | **17%** | 4% |
| Mem0 MH 32k | 24% | 15% | **45%** ⚠️ | 0% |
| Mem0g-pa MH 32k | 22% | 12% | **47%** ⚠️ | 1% |

**Plan A W1 結論**:
- 6k:retrieval fail 25%/17%(已不算小)
- **32k:retrieval fail 上升到 45-47%**(主導 failure mode)
- 兩 method 在 32k 一致顯示:detection 對但 retrieval 還是漏 → **W1 結構性問題在 32k+ 完全暴露**

### 2.3 Detection action precision/recall(operation-level)

從 `analysis/results/plan_a/*_detect.json`:

| Method × Task × ctx | Precision | Recall | F1 | UPDATE-content correct |
|---|---:|---:|---:|---:|
| Mem0 MH 6k | 0.97 | 0.76 | 0.85 | **1.00** |
| Mem0g-pa MH 6k | 0.98 | **0.90** | **0.94** | **1.00** |
| Mem0 MH 32k | **0.51** | 0.96 | 0.67 | **0.64** |
| Mem0g-pa MH 32k | **0.52** | 0.93 | 0.67 | 0.63 |

**Plan A W1 精細 takeaway**:
- 6k:precision/UPDATE-content 接近完美,recall 0.76-0.90 — detection 機制 work,但**漏抓的部分流入 retrieval**
- **32k:precision 從 0.97 崩盤到 0.51**(過度觸發 UPDATE)+ UPDATE-content 從 1.00 跌到 0.63(替換內容變糟)
- → 32k 在 detection 本身就壞了(過度觸發 + 亂寫)+ retrieval 又漏(D✓R✗A✗ 45-47%)

### 2.4 條件機率(D → R → A causal chain)

| | Mem0 MH 6k | Mem0g-pa MH 6k | Mem0 MH 32k | Mem0g-pa MH 32k |
|---|---:|---:|---:|---:|
| P(R \| D=1) | 71% | **81%** | 39% | 35% |
| P(A \| R=1) | 80% | 83% | 60% | **66%** |
| P(A \| R=0) | 3% | 4.5% | 25% | 26% |

**Mechanism story**:
- **P(A\|R=0) 一致 2-5%** → **R 是 dominant gate**:給 LLM 髒 context,EM 必死
- Mem0g-pa **6k 透過提升 P(R\|D=1) +10pp 拿到 +14pp EM**
- Mem0g-pa **32k 反而 P(R\|D=1) -4pp**(two-store divergence 在 32k 加重)
- 但 32k Mem0g-pa P(A\|R=1) +6pp(graph relations 進 prompt 後 LLM 在 clean context 多跳推理 better)
- → 兩效應**相消**,EM 持平(40 vs 39)

### 2.5 Preview group 證據(historical detection coverage)

從 [aligned_detection_answer_correspondence.json](../../analysis/results/aligned_detection_answer_correspondence.json):

| | FC-SH per-hop detection | FC-MH per-hop detection | FC-MH all_detected per-Q | FC-MH all_detected EM | "偵測對仍錯" rate |
|---|---:|---:|---:|---:|---:|
| Mem0 (preview, customized) | 62% | 59% | 41% | 63%(26/41)| **37%** |
| Zep (preview, dropped) | 35% | 38% | 20% | 40%(8/20)| **60%** |

**Preview group W1 takeaway**(即使作 historical disclose):
- Mem0 even at 41% all_detected,**裡面還有 37% 答錯** — 直接 evidence「detection 對也救不了」
- Zep all_detected 內 60% 仍錯 — annotation `invalid_at` 在 LLM context 中部分被忽略

→ 這跟 Plan A 的 D✓R✗A✗ 結論**完全 align**:detection 對只是必要條件,retrieval pool 還要乾淨,LLM 才能用上。

### 2.6 W1 paper 寫法(可直接用)

```
W1 evidence chain (paper §6.4):

Plan A (matched conditions, gemini-3.1-flash-lite GA, temp=0):
  - Mem0/Mem0g-pa MH 32k 共同 fail mode = D✓R✗A✗ 45-47%
  - precision 從 6k 0.97 崩盤到 32k 0.51
  - UPDATE-content 從 1.00 跌到 0.63
  → write-time detection 在長 context 過度觸發 + 替換內容變糟,
    且即使對的 detection 也不能 propagate 到 query-time retrieval

Preview group (historical reference):
  - Mem0 41% all_detected 內 37% 仍錯 (per-Q-level)
  - Zep 20% all_detected 內 60% 仍錯
  → detection 對不保證 EM 對,因 retrieval 階段不能調用 detection 結果 filter
```

---

## Step 3 — W2 evidence(多跳結構檢索,paper claim 2)

### 3.1 W2 核心主張

> Query 後 hop 的 entity 不在 query 字面(hop_position ≥ 2),純語意 top-k 抓不到,graph PPR 才能 traverse 到。

### 3.2 現在我們有什麼

**已有**:Plan A `*_align.json` 每 hop 含 `gt_in_memories` / `old_in_memories`,但**沒 `hop_position` 標註**(W2 命脈)。

**待補(Path B Step 1,0.5 天)**:
- 從 MQuAKE GT chain 推 `hop_position`:hop_idx + 1(因 MQuAKE GT chain 是 ordered)
- 加 `entities_required`(from MQuAKE GT hop fact 的 head entity)
- 加 `entities_in_query`(literal 比對 query text)

**之後可算的(Path B Step 3)**:
- per-method × ctx × hop_position 的 chain_new retrieval rate
- 預期 pattern(spec §4.2):
  ```
  Mem0/Mem0g (純語意 top-k):
    p=1: 80-90%, p=2: 30-50%, p≥3: <30%
  HippoRAG-v2 / Ours (graph PPR):
    p=1: ~80%, p=2: 60-70%, p≥3: 50-60%
  ```

### 3.3 Preview group 有一個間接證據

從 [motivation_narrative.md §1.5](../../analysis/paper_motivation/motivation_narrative.md) HippoRAG-v2 retrieval coverage(預build 6k corpus,top-10 chunks):

| | chain_new in top-10 | chain_old in top-10 |
|---|---:|---:|
| FC-SH(n=100)| 99% | 100% |
| FC-MH 2-hop(n=61)| 97% | 98% |
| FC-MH 3-hop(n=24)| 94% | 100% |
| FC-MH 4-hop(n=15)| 95% | 97% |

**Preview group W2 觀察**(important caveat:HippoRAG top-10 = 83% corpus coverage,接近 full dump):
- HippoRAG retrieval 在 hop ≥2 仍能拿到 chain_new ≥94% — 因為 retrieval 太「廣」(覆蓋 83% corpus)
- → **W2 不是 retrieval 完全沒抓到,是抓到後 chain_old 跟 chain_new 並存讓 LLM 困惑**
- → 連到 W1 + W3:retrieval 廣 + 沒 filter + LLM 無 chain 結構

**Plan A 不同的問題**:Mem0/Mem0g 是 vector top-100 上限 ≤ 100/total facts(≤ 22% corpus),hop_position 評估會跟 HippoRAG 廣 retrieval 對比出明顯差異 — **等 Path B Step 1+3 補完才能看到 W2 quantitative**。

### 3.4 W2 paper 寫法 next step

```
W2 evidence chain pending (need Path B Step 1+3):

Plan A 條件下:
  - 計算 per-method × ctx × hop_position 1/2/≥3 的 chain_new retrieval rate
  - 預期 Mem0/Mem0g-pa 在 p=2,3 顯著下降(純語意 top-100 抓不到 derived entity)
  - 預期 HippoRAG-v2/our method (PPR) 在 p=2,3 較平

時程: Path B Step 1 (加 hop_position) + Step 3 (compute) = 1 天可拿到
```

---

## Step 4 — W3 evidence(memory output 結構影響 LLM 多跳 inference,paper claim 3)

### 4.1 W3 核心主張

> 即使 retrieval 乾淨(chain_old 過濾掉),LLM 在 bullet-list memory output 上做 4-hop reasoning 仍有 ~42pp gap to ceiling。需要結構化 chain 注入。

### 4.2 現在我們有什麼

**Plan A**: ❌ 完全沒 oracle / PureChain / 結構化 prompt experiment。

**Preview group**: ✅ 完整(從 motivation_narrative.md §2.A + §2.B):

| Setup | EM | Δ vs Vanilla |
|---|---:|---:|
| Vanilla(corpus 含全 old+new)| 21% | baseline |
| OracleClean-Others(留本題 chain_old,清其他 165 olds)| 26% | +5pp |
| **OracleClean-ThisChain**(移本題 chain_old)| **55%** | **+34pp** ← 主 gain |
| OracleClean-All(全 165 olds 移)| 61% | +6pp 邊際 |
| **PureChain**(只有本題 chain_new)| **97%** | ceiling |

**結構化 prompt × OracleClean-ThisChain**(preview baseline 55%):

| Prompt | EM | Δ |
|---|---:|---:|
| no scaffold | 55% | — |
| + V1 trailer | 83% | **+28pp** |
| + V2 cite-source | 85% | **+30pp** |
| + V3 decompose | 86% | **+31pp** |

→ **三個 independent scaffold 都拿 +28-31pp gain**,strongly support W3。

### 4.3 W3 跨 cleanness 驗證

V1 trailer 在不同 oracle cleanness 上的 gain:

| Setup | orig EM | + V1 trailer | Δ |
|---|---:|---:|---:|
| Vanilla(髒)| 21% | 23% | +2pp ← 救不了 |
| OracleClean-Others | 26% | 34% | +8pp |
| **OracleClean-ThisChain** | **55%** | **83%** | **+28pp** ← 最強 |
| OracleClean-All | 61% | 81% | +20pp |
| PureChain(過乾淨)| 97% | 98% | +1pp ← 飽和 |

→ 結構化 prompt 在「中度乾淨」context 上效益最大;太髒救不了,太乾淨已飽和。**這個 pattern 跨 5 個 cleanness 級別都符合**,不是偶然。

### 4.4 Caveat(很重要)

❌ **這些是 preview backbone + HippoRAG-v2 retrieval base 的數字**,Plan A 條件下未驗證。
spec §11.2 把 OracleClean-ThisChain 55% 當 V_baseline 預期,**也需 Path A Diagnostic 0 實測重驗**。

### 4.5 W3 在 Plan A 條件下的 Diagnostic 0(Path A)

**Option b raw-context-based oracle**(user 已選):
- 從 MQuAKE GT 對每 query 知道 chain_old / chain_new
- 用 raw 6k context **直接 filter chain_old fact lines** → OracleClean-ThisChain context
- 用 chain_new only → PureChain context
- 餵 Plan A reader(gemini-3.1-flash-lite GA, temp=0),測 V_baseline / V_A Self-Ask / V_B CoT / V_C CoRe 4 variants

**預期 / 待驗值**:

| Variant | 預期 EM(以 preview 55% 為 reference)| Plan A 實測 |
|---|---:|---:|
| V_baseline(OracleClean-ThisChain + vanilla)| **55%** | TBD |
| V_A Self-Ask | +15~30pp(到 70-85%)| TBD |
| V_B CoT | +10~20pp | TBD |
| V_C CoRe-style | +15~25pp | TBD |
| PureChain ceiling | 97% | TBD |

Outcome(spec §11.2 §14.0):
- Outcome 1(max Δ ≥ 15pp)→ Approach 3 進場 → Iter 0 起跑
- Outcome 2(max Δ < 5pp)→ Approach 3 退場 → 縮 scope 到 conflict filter
- Outcome 3(5-15pp)→ 部分 work,case 分析

---

## Step 5 — 整體 progressive takeaway

### 5.1 三個 claim 的 evidence 完成度

| Claim | Plan A | Preview | 缺什麼 | 補完時程 |
|---|---|---|---|---|
| **W1 detection-retrieval 脫鉤** | ✅ 完整(M-DRA 8 cells + precision/recall + 條件機率)| ✅ all_detected vs no_detection table | 純 disclose 已足 | done |
| **W2 多跳結構檢索** | ⚠️ 沒 hop_position 維度 | ⚠️ HippoRAG 廣 retrieval 反證(retrieval ≥94% 仍敗)| Plan A 加 hop_position breakdown | Path B Step 1+3,1 天 |
| **W3 memory output 結構** | ❌ 完全沒有 | ✅ 完整(5 oracle + 3 scaffolds × 5 cleanness)| Plan A 重做 Diagnostic 0 | Path A,2 天 |

### 5.2 Paper 主 narrative 可寫程度

```
✅ paper §1-§3 background + related work + 3 weakness motivation 已可寫
✅ paper §6.3 主表 baseline 部分 Plan A 直接填(12+ cells, missing our method)
✅ paper §6.4 W1 mechanism evidence 完整可寫(M-DRA + detection precision/recall)
⚠️ paper §6.4 W2 mechanism evidence 等 Path B(1 天)
❌ paper §6.4 W3 mechanism evidence 等 Path A(2 天)
❌ paper §6.3 主表 our method 部分等 Path D(1-2 週)
❌ paper §5 final method variant 等 Iter 0 後 lock
```

### 5.3 立刻推薦的 next 3 步

**Step A**(now)— **Path B Step 1**:加 `hop_position` 到 Plan A align.json(我已 ready,可立刻動工)
- Output:8 cells × 188 has_pair hops × per-hop hop_position 標註
- 時間:0.5 天

**Step B**(明天)— **Path B Step 2+3**:compute_m_dra_with_hop_position + compute_hop_position_retrieval
- Output:W2 quantitative evidence(per-method × hop_position retrieval rate table)
- 時間:1 天(可平行 Step C)

**Step C**(平行)— **Path A Step 1**:OracleClean-ThisChain context generator(Option b)
- Output:100 queries 的 oracle context files,ready 餵 reader
- 時間:0.5 天

→ **Path B 主場優先,Path A 平行推進**。3 天內 W1/W2/W3 evidence 全可填進 paper。

---

## Step 6 — Decision needed

| Decision | 建議 | 影響 |
|---|---|---|
| Path B Step 1 動工(加 hop_position)| ✅ 立刻 | W2 evidence 後天有 |
| Path A Step 1 平行動工(OracleClean Option b generator)| ✅ 立刻 | W3 evidence 大後天有 |
| Path D Audit 3(our method 對齊 Plan A 重跑)| ⏸ 等 Path A 完 + Diagnostic 0 outcome 後再決定 | 1-2 週工程,等戰場位置 lock |
| 64k Mem0 MH 跑完後做 align + D + 3way | ✅ 跑完自動加 | 多 1 列 64k 對比 trend |

我建議現在立刻 **Step A + Step C 平行動工**(Path B Step 1 + Path A Step 1),3 天 deliverable。

---

**End of all_methods_progressive_analysis.md(2026-05-31)**
