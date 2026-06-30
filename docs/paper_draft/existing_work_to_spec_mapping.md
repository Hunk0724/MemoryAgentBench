# Existing Work → research_narrative / fc_metric_spec 對應 mapping

> **目的**:列出我們**已完成**的工作,精確 mapping 到 [research_narrative.md](research_narrative.md) 或 [fc_metric_spec.md](fc_metric_spec.md) 的哪個段落。Claude chat 拿這份 doc 即可知道「哪些數字可以直接填、哪些要先驗證、哪些缺」。
>
> **Updated**: 2026-05-31
> **Status**: 給 Claude chat 整合用的中間 doc;不是 paper 本身。
> **核心對齊問題**:
> 1. Plan A pilot 用 **gemini-3.1-flash-lite GA + temp=0 + text-embedding-004**
> 2. 舊 motivation work 用 **gemini-3.1-flash-lite-preview + temp=0.7 + HippoRAG-v2/NV-Embed-v2 top-10**
> 3. 兩者 setup 不對齊,Plan A pilot 沒有 oracle/PureChain 數字,需處理。

---

## 1. 已完成工作分類概覽

### 1.A Plan A pilot(2026-05-30 完成,Plan A 鎖定條件)

| 工作 | 檔案 | spec/narrative 對應 |
|---|---|---|
| 12+ verified cells M1 EM | [RESULTS_MASTER.md](../RESULTS_MASTER.md) | narrative §2.1 主表 + spec §13.1 Stage 0 表 |
| 三大 finding F1/F2/F3 | 同上 | narrative §6.3 Stage 0 三大 finding 段 |
| M-DRA 3-way contingency × 8 cells | `analysis/results/plan_a/*_3way.json` | spec §5 + narrative §7 M-DRA 完整 |
| Detection-action precision/recall | `analysis/results/plan_a/*_detect.json` | spec §5.2 D 維度 + narrative §2.2 W1 evidence |
| 條件機率 P(R\|D=1) / P(A\|R=1) | 同上 | spec §6.2 + narrative §4.1 |
| Mem0g pipeline + two-store divergence narrative | [mem0g_reproducibility.md §7+§8](../baseline_methods/mem0g_reproducibility.md) | narrative §3.2 Mem0g critique |

### 1.B 舊 motivation work(2026-05 上半,**setup 跟 Plan A 不對齊**)

| 工作 | 檔案 | spec/narrative 對應 | Plan A 對齊? |
|---|---|---|---|
| 6 oracle setup × FC-MH 100Q EM(Vanilla 21% / OracleClean-Others 26% / OracleClean-ThisChain 55% / OracleClean-All 61% / PureChain 97%)| [analysis/paper_motivation/motivation_narrative.md §2.A](../../analysis/paper_motivation/motivation_narrative.md) | narrative §2.1 oracle ceiling 表(line 137-143) + spec §11.2 Diagnostic 0 V_baseline 預期 ~55% | ❌ **preview backbone + HippoRAG-v2 NV-Embed top-10**, 需在 Plan A 條件下重跑 |
| Mode C dose-response(n_inject=0 58% / =1 9% / =2 3% / =3 0% / =4 0%)| 同上 §2.A.b2 | narrative §2.2 W3 emergent gap 證據(§1.B 25.8pp gap, §2.A.X) | ❌ 同上 |
| Per-hop EM by num_hops(2/3/4-hop = 80%/78%/75%)| §2.A.X.0 | narrative §2.2 (per-hop independence 證據) | ❌ 同上 |
| 結構化 prompt(V1 trailer/V2 cite/V3 decompose) +28~31pp gain in 55%→ 83-86% | §2.B | spec §11.2 Diagnostic 0 V_A/V_B/V_C 預期結果 | ❌ 同上 |
| Cross-cleanness × prompt(5 cleanness × 1 prompt)| §2.B Table | narrative §4.3 Weakness 3 evidence | ❌ 同上 |
| Detection vs answer correspondence(per-hop / per-question / all_detected / no_detection by SH/MH × Mem0/Zep)| §4.2-§4.3 + [aligned_detection_answer_correspondence.json](../../analysis/results/aligned_detection_answer_correspondence.json) | narrative §3 related work(Mem0/Zep critique)+ spec §5 M-DRA 跨方法定義 | ⚠️ 部分:Mem0 detection 邏輯已在 Plan A 重算過,Zep 不對齊 |
| 6 figures(fig1-fig6) | `analysis/paper_motivation/figures/slides/` | paper §3 motivation + §6 results figures | ❌ 數字 stale,需重畫 |

### 1.C 工具 / 腳本(可重用)

| 工具 | 檔案 | 用途 |
|---|---|---|
| Oracle context 生成 | `analysis/oracle_a_phase1_validate_gemini.py` 等 | Path A Diagnostic 0 可 base on 此重寫 |
| MQuAKE alignment | `analysis/align_mem0_mquake.py` | Plan A 已用,可加 `hop_position` 欄位 |
| 結構化 prompt scaffold | `analysis/run_oracle_a_phase2_inference_gemini.py` 等 | Path A Diagnostic 0 V_A/V_B/V_C 可改造 |

---

## 2. 精確 mapping — 哪段填什麼數字

### 2.1 narrative §2.1 整體 multi-hop 崩潰主表

> **位置**: [research_narrative.md:128-136](research_narrative.md) "現有方法在 FC-MH 失敗" 表

**現狀**:
```
| Method × Task | 6k | 32k | 64k | 262k |
| LCA × SH | 96% | 91% | TBD | TBD |
| ...
| Mem0g-pa × MH | 66% ⭐ | 40% | TBD | TBD |
```

**我們可填的數字(從 Plan A 主表)**:
- LCA SH/MH × 6k/32k: 96/16/91/19 ✓
- Mem0 SH/MH × 6k/32k: 92/52/90/39 ✓
- Mem0g-pa SH/MH × 6k/32k: 79/66/89/40 ✓
- LCA × 64k SH/MH: **90/12**(Plan A 已跑)
- Mem0 × 64k SH/MH: SH=88(完),MH 跑中(b9kwhk56z)
- Mem0g-pa × 64k/262k: 跳過(成本太高,narrative §0 已 lock)
- 262k 全部:暫不跑

**填法**: 把 TBD 換成上面數字。

---

### 2.2 narrative §2.1 Oracle ceiling 表(line 137-143)

> **位置**: [research_narrative.md:137-143](research_narrative.md):
> ```
> - PureChain: 97%
> - OracleClean-ThisChain: 55%
> - OracleClean-All: 60%
> - Vanilla: 20%
> ```

**現狀**: 這些數字**來自舊 motivation work**,setup 是:
- gemini-3.1-flash-lite-**preview**(我們現在 GA)
- HippoRAG-v2 + NV-Embed-v2 top-10 retrieval(我們 GPU 缺,改用 historical reference 框定)
- temp 不確定但很可能 0.7

→ **Plan A 條件下這些數字未驗證**。spec §11.2 把 OracleClean-ThisChain 55% 當 V_baseline 預期值,**也需 Path A Diagnostic 0 實測重驗**。

**處理方案**(三選):

| 方案 | 動作 | 風險 |
|---|---|---|
| **A**(推薦) | Path A Diagnostic 0 同時 verify 5 個 oracle EM(用 Plan A 條件)+ baseline 對齊 | 多 0.5 天但 paper-safe |
| B | 引用舊 motivation 數字 + 註腳 disclose backbone 差異 | reviewer 攻擊面 |
| C | 全部 oracle 用 Plan A 條件重跑(包括結構化 prompt) | 3-5 天 |

→ **Recommendation A**:Path A 加 V_baseline = OracleClean-ThisChain × Plan A reader(實測 55% 數字),同時用 V_A/V_B/V_C 三個結構化 prompt 拿 Δ。

---

### 2.3 narrative §2.2 W1 evidence(line 168-173)

> **位置**: [research_narrative.md:168-173](research_narrative.md):
> ```
> Mem0 MH 32k: D✓R✗A✗ = 45%
> Mem0g-pa MH 32k: D✓R✗A✗ = 47%
> Mem0 32k L2 precision 0.97 → 0.51
> Mem0 32k UPDATE-content 1.00 → 0.63
> ```

**現狀**: ✅ Plan A pilot **完全可填**。

**檔案來源**:
- D✓R✗A✗: `analysis/results/plan_a/mem0_mh_32k_3way.json` summary.cells → "retrieval fail (D✓R✗A✗)" 45%
- 同上 mem0g_pa_mh_32k_3way.json → 47%
- L2 precision: `mem0_mh_32k_detect.json` → 0.51
- UPDATE-content: 同上 → 0.63

→ **Filled** ✓ 數字一致,可直接 cite。

---

### 2.4 narrative §2.2 W2 evidence

> **位置**: [research_narrative.md:199-225](research_narrative.md) — Darwin/Amala/Belgium example

**現狀**: 是 conceptual example,**沒有 quantitative evidence**。
**spec §4.2 預期**(line 506-516):
```
Mem0/Mem0g (純語意 top-k):
  p=1: 80-90%, p=2: 30-50%, p≥3: <30%
HippoRAG-v2 / Ours (graph PPR):
  p=1: ~80%, p=2: 60-70%, p≥3: 50-60%
```

**我們有的 data**: Plan A `*_align.json` 每 hop 已有 `gt_in_memories` / `old_in_memories`,但**沒 `hop_position` 標註**。

→ **需要 Path B Step 1**:加 `hop_position` 後 compute per-hop retrieval rate × hop_position。可從 MQuAKE GT 推 hop_position 1/2/≥3。

**預估**: 加欄位 0.5 天,跑分析 2 hr,寫進 narrative 半天。

---

### 2.5 narrative §2.2 W3 evidence(line 232-245)

> **位置**: [research_narrative.md:232-245](research_narrative.md):
> ```
> Plan A oracle experiment:
>   PureChain (only chain_new): 97%
>   OracleClean-ThisChain: 55%
>   → 42pp gap 來自 memory output 含 distractor
> ```

**現狀**: ❌ Plan A pilot 完全沒做 oracle experiment。這兩個數字是**從舊 motivation work 引用**。
**Path A Diagnostic 0(spec §11)** 就是要實測這個 gap 在 Plan A 條件下是否仍 ~42pp。

**處理**: 全部待 Path A Diagnostic 0 後填。

---

### 2.6 spec §11.2 Diagnostic 0 SOP

> **位置**: [fc_metric_spec.md:783-837](fc_metric_spec.md)

**現狀**: 全 pending。

**舊 motivation 可直接借用**:
- 結構化 prompt V1 trailer / V2 cite-source / V3 decompose([motivation_narrative.md §2.B](../../analysis/paper_motivation/motivation_narrative.md))
- → spec V_A Self-Ask / V_B CoT / V_C CoRe-style 三 variants 可參考舊設計

**設定對齊**:
- 舊用 HippoRAG-v2 retrieval pool;Plan A 條件下:
  - **Option a**: 用 Mem0 retrieval pool(我們 Plan A 主對手)+ filter chain_old → 構造 OracleClean-ThisChain
  - **Option b**: 用 raw 6k context 直接 filter chain_old(無 retrieval,直接拿 GT 對應 facts)
  - **Option c**: 同舊版用 HippoRAG-v2 reference pool(但 GPU 缺問題)

→ **Recommendation**: Option b(最乾淨,no retrieval confound)— 反正 oracle 本意是「context 內容控制」,直接用 raw context 過濾最 clean。

**Path A 具體實作**: 已寫進前面的 path A/B 執行 plan,我用 Option b base 重做即可。

---

### 2.7 narrative §3 related work — Mem0/Mem0g critique

> **位置**: [research_narrative.md:298-388](research_narrative.md)

**現狀**: ✅ 完全可從現有 doc 填:
- [mem0g_reproducibility.md §7](../baseline_methods/mem0g_reproducibility.md) — Mem0/Mem0g pipeline 完整對照
- 同上 §8 — Two-store divergence 結構性 limitation

→ **可直接 cite**。Plan A pilot 補強 quantitative evidence。

---

### 2.8 narrative §7 + spec §5 M-DRA framework

> **位置**: [research_narrative.md:1062-1144](research_narrative.md) + [fc_metric_spec.md:379-482](fc_metric_spec.md)

**現狀**: ✅ 我們有 Plan A 8 cells × D × R × A 完整,可直接寫進 paper §6.4。

**數字來源**:
- `analysis/results/plan_a/*_3way.json`
- 8 cells 表已在 [RESULTS_MASTER.md mechanism 段](../RESULTS_MASTER.md)

→ **完成,直接 cite**。

---

### 2.9 spec §8.3 Two-store divergence audit

> **位置**: [fc_metric_spec.md:587-619](fc_metric_spec.md)

**現狀**: ⚠️ 有 narrative([mem0g_reproducibility.md §8](../baseline_methods/mem0g_reproducibility.md)),**但無實際 audit 數據**(per-hop vector/graph state 對比)。

**spec 預期**:
```
6k:    divergence_rate ~5-10%
32k:   divergence_rate ~20-30%
64k+:  predict 更高
```

→ **Path B Step 4 Sub-scale B 待做**(0.5 天):從 `mem0g_label_audit.jsonl` 重建 Neo4j state + 比對 vector store events。

---

### 2.10 narrative §4.1 Analysis 1(W1 evidence)

> **位置**: [research_narrative.md:469-494](research_narrative.md)

**現狀**: 直接從 Plan A `analysis/results/plan_a/*_3way.json` summary 拿 D×R×A 8-cell table。**✅ ready to cite**。

---

## 3. 缺什麼(必須補)

| 缺項 | 屬 spec/narrative 哪段 | 行動 | 預估 |
|---|---|---|---|
| OracleClean-ThisChain EM under Plan A | narrative §2.1 + spec §11 V_baseline | Path A Diagnostic 0 | 1 天 |
| PureChain EM under Plan A | narrative §2.1 ceiling | Path A 同時加 | 0.5 天 |
| 結構化 prompt Δ under Plan A | spec §11 V_A/V_B/V_C | Path A 同時加 | 0.5 天 |
| `hop_position` 標註 + per-hop retrieval breakdown | narrative §2.2 W2 + spec §4.2 | Path B Step 1+3 | 0.5+0.25 天 |
| Two-store divergence per-hop audit | spec §8.3 | Path B Step 4 Sub-scale B | 0.5 天 |
| Top 20 D✓R✗A✗ case dump | spec §17 Path B output | Path B Step 5 | 0.5 天 |
| 圖表更新(fig1-fig6 用 Plan A 數字)| paper figures | 寫進 generate_slides_figures.py | 1 天 |

**總時程**:3-4 天可補完 Path A + Path B 所有 gap。

---

## 4. 「已可填」vs「待 Path A/B 後填」分類

### 4.A 已可直接填(可 paper 直接 cite)

```
narrative §1 Background, §3 Related Work — 直接寫
narrative §2.1 main 12+ cells EM table — Plan A 直填
narrative §2.2 W1 D✓R✗A✗ 45/47% — Plan A 直填
narrative §2.2 W1 Mem0g two-store divergence narrative — mem0g_reproducibility.md §8 cite
narrative §3.2 Mem0/Mem0g pipeline diff — mem0g_reproducibility.md §7 cite
narrative §4.1 Analysis 1 — Plan A 直填
narrative §5 Design principles — locked
narrative §7 M-DRA framework — Plan A 直填
narrative §8.1 Case 1 (Weakness 1) — Plan A D✓R✗A✗ case 抓 1 個範例
spec §1 Metric hierarchy — locked
spec §2 GT alignment schema — Plan A align.json 結構 close (待加 hop_position)
spec §3 M1 — Plan A
spec §4 M-core — Plan A 已可算
spec §5 M-DRA — Plan A 已可算
spec §6 M-inference (P(A|R=1) part) — Plan A 已可算
spec §13.1 Stage 0 Plan A verified table — Plan A 直填
spec §15 Prior art alignment — locked
```

### 4.B 待 Path A 後填

```
narrative §2.1 oracle ceiling 表 (5 setups EM under Plan A)
narrative §2.2 W3 42pp gap 證據 (PureChain − OracleClean-ThisChain)
narrative §4.3 Diagnostic 0 outcome (Outcome 1/2/3) + Approach 3 進場決策
narrative §8.3 Case 3 (Weakness 3) — Diagnostic 0 + Self-Ask Δ case
narrative §9 Three scenarios A/B/C/D — Iter 0 後 lock
spec §11.4 Diagnostic 0 report output
spec §14.0 Approach 3 進場決策
spec §17 Path A output
```

### 4.C 待 Path B 後填

```
narrative §2.2 W2 hop_position breakdown 表 (預期 p=1 80-90% / p=2 30-50% / p≥3 <30%)
narrative §3.2 Mem0g two-store divergence quantitative rate × ctx
narrative §4.2 Analysis 2 per-hop × hop_position table
narrative §8.1 Case 1 + §8.2 Case 2 raw case dump
spec §8 M-pool + two-store divergence rate
spec §13.2 Audit 1 report 含內容
spec §17 Path B output
```

### 4.D 待 Path D 後填(我們 method 對齊)

```
narrative §6.3 Stage 1+ our method M1 + M-DRA
narrative §6.5 generalizable claim 數字
spec §5.9 Decision rules with our method P(D✓R✗A✗) ≤ 15% 驗證
```

---

## 5. 建議的執行順序(對齊 spec §17 To-do)

**Stage A**(本週)— 補 Path A + Path B 的數據:

1. **Day 1**:
   - Path B Step 1: 加 `hop_position` / `entities_required` / `entities_in_query` 到 align.json
   - Path A Step 1: 寫 OracleClean-ThisChain context generator(Option b raw context based)

2. **Day 2**:
   - Path B Step 2-3: compute_m_dra_with_hop_position + compute_hop_position_retrieval
   - Path A Step 2: 實作 4 variants(V_baseline / V_A Self-Ask / V_B CoT / V_C CoRe-style)

3. **Day 3**:
   - Path A Step 3: 跑 100Q × 4 variants × fixed reader = 1 hr 跑時間
   - Path B Step 4: Two-store divergence audit
   - Path B Step 5: Top 20 D✓R✗A✗ case dump

4. **Day 3 evening - Day 4**:
   - 寫 Diagnostic 0 report → 填 narrative §4.3 + spec §11.4
   - 寫 Audit 1 report → 填 narrative §4.1/§4.2 + spec §13.2
   - Update narrative §0 Sync Status 把 Path A/B 標 ✅
   - Decision: Approach 3 進場與否 → narrative §11 Iter 0 啟動

**Stage B**(下週)— Path D 工程(our method 對齊 Plan A):

5. **Day 5+**:Path D 工程(spec §13.2 Path D)— 視 Stage A 結果決定範圍

---

## 6. 給 Claude chat 整合的 checklist

當 Stage A 完成後,Claude chat 可以用此 checklist 整合進 paper:

```
□ 把 narrative §2.1 主表 12-15 cells 填好(去掉 TBD)
□ 把 narrative §2.1 oracle ceiling 表更新為 Plan A 條件實測值
□ 把 narrative §2.2 W2 hop_position evidence 表填好
□ 把 narrative §2.2 W3 42pp gap evidence 用 Plan A Diagnostic 0 數字填
□ 把 narrative §3.2 Mem0g two-store divergence rate × ctx 填(從 audit 1 sub-scale B)
□ 把 narrative §4.1/§4.2/§4.3 Analysis 1/2/3 evidence 全更新為 Plan A
□ 把 narrative §6.3 Stage 0 主表填(已 ready)
□ 把 narrative §7 M-DRA Plan A 8 cells 完整 cite
□ 把 narrative §8 Case studies 1/2/3 各抓 1 個 representative case
□ 把 spec §11.4 Diagnostic 0 report 填 (Outcome 1/2/3)
□ 把 spec §13.2 Audit 1 report 填
□ 把 spec §13.3 Iter 0 Approach 3.1 結果 (等執行)
□ 把 narrative §0 Sync Status pending data 全標 ✅
□ 把 narrative §9 Three scenarios 對 Plan A + Iter 0 結果 lock 戰場
```

---

## 7. 重要 caveat — 給 claude chat 知道

1. **舊 motivation work 數字(55% / 97% / V1/V2/V3 28-31pp)是 preview backbone,Plan A 待重驗**。
   - 若 Path A Diagnostic 0 重跑 V_baseline 不在 50-60% 區間,整個舊 motivation narrative 要重整。
2. **HippoRAG-v2 在 Plan A 條件下沒對應數字**(no GPU torch + NV-Embed-v2 限制)。
   - 用 historical reference + paper appendix disclose。
   - paper §3 related work 仍 cite,但不放主表。
3. **我們 method(HippoRAG-v2 base + Phase 2)在 Plan A 條件下也沒對應數字**。
   - method_v2.0.2_status_brief 的 31% 數字是 preview backbone。
   - Path D Audit 3(spec §13.2)需要 1-2 週工程才能對齊。
   - 暫時 narrative §6 Stage 1+ 留 TBD。
4. **Approach 3 是否進場 = Path A Diagnostic 0 outcome 決定**(Outcome 1/2/3)。
   - 在這之前,narrative §5.4 列的 approach1/2/3.1/3.2/3.3/4 都是 candidate,不 lock。
5. **Plan A 的 Mem0g-pa MH 6k 66% 是 paper 強對手**(narrative §11.2 hard floor),our method 必須對齊或超越。
6. **embedder mismatch**:Mem0/Mem0g 用 text-embedding-004,HippoRAG-v2 用 NV-Embed-v2(only reference),我們 method 待定。Paper appendix disclose embedder choice rationale(已在前面討論)。

---

**End of existing_work_to_spec_mapping.md(2026-05-31)**
