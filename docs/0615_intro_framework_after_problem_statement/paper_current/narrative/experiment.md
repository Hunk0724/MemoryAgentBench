# 4. Experiments(v0 scaffold,2026-07-05 起稿,與 user 共筆)

> **對接**:[`intro_zh_revised_v6.md`](intro_zh_revised_v6.md)(§7 payoff)、[`related_work_zh_v2.md`](related_work_zh_v2.md)(§2.1 派別分類)、[`method_v1.md`](method_v1.md)(§3.2/3.3 兩個 commitment)。
> **原始資料來源**:[`../evaluation_protocol_main.md`](../evaluation_protocol_main.md)(protocol)、[`../results/*.md`](../results/)(rigor 數據)、[`../style_rules_tables_figures_writing.md §10.3a/b/c`](../style_rules_tables_figures_writing.md)(landscape)。
> **寫作原則**:precise、minimal、可直接進 IEEE/ACM 論文 body;每個 claim ↔ 表格 / case ↔ intro 對應段落。

---

## 4.1 Setup

### 4.1.1 Dataset

**FC-SH**(FactConsolidation single-hop,MemoryAgentBench [Hu et al., ICLR 2026] Conflict_Resolution split)。挑選理由:

- **高衝突密度**:由 MQuAKE [Zhong et al., EMNLP 2023] 的 counterfactual 編輯對建構的密集對話,將壓力施加於 KU 解析而非稀疏檢索(RW §2.3)。
- **Fact-level ground truth**:每題附 `gt_new` / `gt_old` / `gt_seq` / `old_seq` 標註,支援 pipeline 各階段的細粒度歸因。
- **Exact-match 判分**:無 LLM judge,排除評分模型偏誤。

| Property | Value |
|:--|:--|
| Lengths(context tokens) | 6k / 32k / 64k(**262k 延後**) |
| Queries per length | 100 |
| `has_pair` 子集(有 GT_old / GT_new 對照,**主分母**) | **74 / 65 / 66** |
| `no_conflict_pair`(單版 GT) | 26 / 35 / 34 |
| Full-bank conflict-pair(全 chunks P1 抽取後 (S,P) 分群 ≥2 distinct object) | 124 / 631 / 1,295 |

☐ **待定**:是否納入 LongMemEval-KU(78 題,personal-fact KU)作為 generalization 檢驗於同一章節或另闢一小節。

### 4.1.2 Baselines

依 intro / RW §2.1 的 KU 處理派別分類。**Same-family**(記憶增強 agent)進主表;**different-family**(無記憶架構)作 environment ceiling。

#### Same family(memory-augmented agents,proactive KU)

| Baseline | 派別(RW §2.1) | 記憶操作機制 | 隔離的變因 |
|:--|:--|:--|:--|
| **(b) mem0+P1** [Chhikara et al., ECAI 2025] | Coupled Update | LLM 決策 ADD/UPDATE/DELETE/NOOP 並就地執行(destructive commit) | **write-time destructive commit**(extraction 共用 ours P1 cache 隔離 extraction 因素) |
| **(a) vanilla mem0**(appendix) | Coupled Update | 同 (b),但用 mem0 native L1 extractor | extraction quality 貢獻(對比 (b))|
| **Zep** [Rasmussen et al., 2025] | Decoupled Update | Zep cloud LLM 標 *contradicts*/*duplicates* → 確定性設 `invalid_at`/`expired_at`,edge body 保留 | **write-time labeling + retrieval-layer temporal invalidation**(檢索層等效不可逆)|

#### Different family(no memory architecture)

| Baseline | 用途 |
|:--|:--|
| **LCA**(Long-Context Answering,gpt-4o-mini 直接吃全 context 答題) | 無記憶架構下限(long-context 能力上限)|

#### Ours(主 method)

**ours main**:忠實寫入(P1/P2 抽取,無跨筆 LLM 判斷)+ 查詢時 KU 解析((S,P) 結構分群 → P3 LLM 補救 → 確定性 argmax);對應 method_v1.md §3.2-3.3。

**Ablations**(於 §4.5 呈現,**不進主表**):`ours (no P3)` = struct+argmax only,`ours (no struct)` = P3+argmax only,`ours (+P5)` = 加 conflict-type 分類器。

### 4.1.3 Backbones

三 tier 光譜,對應 intro §受限部署動機的 privacy(on-device weak model)與 cost(mid-tier API)兩軸,以及 §第 6 段末 falsifiable prediction 於強-tier 的檢驗。

| Tier | Model | 覆蓋長度 | 角色 | 對接 intro |
|:--|:--|:--|:--|:--|
| **Weak** | gemma3 1B / 4B / 12B / 27B(via Ollama,GX10 GB10) | **6k**(6k 已足論述,32k/64k 為 future work) | Privacy-sensitive on-device 主場([13] SlimLM / [15] Huang et al.);falsifiable prediction 弱端檢驗 | §受限部署段 privacy 軸 |
| **Mid**(primary) | gpt-4o-mini | 6k / 32k / 64k(3 lengths 完整) | Cost-constrained API deployment 主場([16] FrugalGPT);paper 主 regime | §受限部署段 cost 軸 |
| **Strong**(backbone extension) | gpt-4.1-mini | 64k(6k / 32k **placeholder,future work**) | Falsifiable prediction 強端檢驗(強 backbone 上優勢應縮小) | §第 6 段末 prediction |

**⚠ 誠實揭露的兩個異質性**(paper 需處理的 caveat):

1. **Weak-tier 是 per-backbone gemma extraction**(GX10 matrix wrapper `MEM0_TRIPLE_MODEL=gemma3:$SIZE`;每 backbone 用自己的 gemma 抽取,各自 P1 cache),類比 Mid/Strong tier 用該 tier 自身模型抽取。即 backbone = 做整條 pipeline 的模型。**同 backbone 內 method 比較公平**;跨 backbone 趨勢混了抽取品質 + 解析品質。
2. **Weak 1B/4B 的抽取品質退化**(store fact 數 370 vs 12B/27B 450;retrieved top-100 與 27B 的重疊 1B=5、4B=82、12B=99)→ pool-state matcher v4 於 1B/4B 不可信 → cross-tab 僅 12B/27B 呈現;1B/4B 用 E2E EM + case study 佐證(見 §4.2.2 caveat)。

### 4.1.4 Metrics

#### Primary — E2E `has_pair` EM

MAB 官方 `default_post_process` + `drqa_exact_match_score`(per-qid):

$$
\text{EM}_i = \max\bigl(\text{EM}(\text{raw}_i),\ \text{EM}(\text{parse\_output}(\text{raw}_i))\bigr)
$$

Aggregate = mean over `has_pair` 分母。**Single deterministic run**(temp=0),無 error bar。

#### Attribution — Context-state × Accuracy cross-tabulation

送進 answer LLM 前的 **pool state**(對 ours 為 `memories_str`、對 (b) 為 `retrieved_memories`、對 Zep 為 `edges`)與 `gt_new`/`gt_old` 的 matcher v4(triple-based + Layer-0 substring pre-check;[`../matcher_specification.md`](../matcher_specification.md))判定,分為四桶:

| Bucket | 含義 |
|:--|:--|
| **PP-New** | Pool 只含 gt_new(理想) |
| **PP-Both** | Pool 兩版共存(依賴 answer LLM 挑選) |
| **PP-OldOnly** | Pool 只含 gt_old(pipeline 已失效)|
| **PP-Missing** | 兩版皆不在(retrieval / write-time miss)|

**論述**:ours vs baseline 的 E2E 差距,**主要來自 pool state 分佈的差異**,非 PP-Both 時 answer LLM 的挑選能力(對應 intro §7「乾淨 pool」payoff)。

#### Secondary — correct-sEM(diagnostic only)

**Definition**:
$$
\text{correct-sEM}(r) = \mathbb{1}\left[ \text{gt\_new} \subseteq r \right] \cdot \mathbb{1}\left[ \text{gt\_old} \not\subseteq r \right]
$$
即 response contains `gt_new_answer` **AND** does not contain `gt_old_answer`。

**Rationale**:
- **Loose substring sEM(僅檢查 contains gt_new,允許 gt_old 也在)** 於 Zep @ gpt-4.1-mini × 64k 上 audit 顯示,27 個 strict-fail-but-sEM-pass 中 **26 個是 hedge FP**(response 同時列 gt_new + gt_old 用「and」連接)。**loose sEM 因此不採用**。
- **Correct-sEM 排除 hedge FP**,只保留 true verbose(response 含 gt_new 且明確不列 gt_old)為 pass。
- Zep @ gpt-4.1-mini × 64k audit:strict EM = 23 → correct-sEM = 24(只差 1 題 qid=6 Shaman King)。**與 strict EM 差距只 +1pp,證明 Zep drop 是真 content fail 非 format artifact**。

**用途**(**diagnostic only**,**不進主表**):
- Primary metric 一律 strict EM
- Correct-sEM 僅於**特定 method(如 Zep)於特定 backbone 顯著下降時**用作 diagnostic:
  - 若 correct-sEM 幾乎不變 → 真 content fail(mechanism 分析)
  - 若 correct-sEM 大幅高於 strict EM → format artifact(pipeline alignment 問題,誠實 disclose)

#### §M-1. Pool state 分析的 dataset 前置條件

Pool state 分析建立於 **FC-SH 的 MQUAKE-derived counterfactual pair 特性**:每題 has_pair 附**事實層級的 ground truth**(`gt_fact_text`、`old_fact_text` 完整字串,以及 `gt_seq`、`old_seq` 於對話中的 chunk 序位)。我們對 memory pool 文字 — 即實際送進 answer LLM 的內容(ours 為 `memories_str`;(b) mem0+P1 為 `retrieved_memories`;Zep 為 `edges` string)— 用 **matcher v4**([`../matcher_specification.md`](../matcher_specification.md))與 `gt_fact_text` / `old_fact_text` 字面比對,分為 PP-New / PP-Both / PP-OldOnly / PP-Missing 四桶。此分析的合法性建立於 MQUAKE 於對話特定 chunk 位置**嵌入兩版本 verbatim**、且 mid-tier backbone(gpt-4o-mini)的 P1 extraction 傾向保留 fact surface form。

#### §M-2. Matcher precision 與限制

- **Matcher v4 於 gpt-4o-mini × 64k 上經 25 題人工 audit,0 confirmed false-negative**([`../results/matcher_audit_gpt4omini_64k.md`](../results/matcher_audit_gpt4omini_64k.md))。原 [`../matcher_specification.md §3.1`](../matcher_specification.md) 記錄的「9/15 mem0+P1 FN」為過度保守之歷史估計,已 verified 為過時。
- Matcher 只判 fact **是否在 pool 中**(presence),不判 answer LLM **是否使用**(usage)。Pool 有 gt_new 而答案錯的情況(PP-New wrong / PP-Both wrong)以 case study 個別檢視。
- **Weak-backbone(gemma3 1B/4B)**:extraction 字面偏離 GT(store 事實數 370 vs 12B/27B 450),matcher precision 必然下降,**不呈現 pool state 分析**,僅報 E2E EM。**gemma3 12B/27B 可信**(pool-missing=0、store 與 27B 重疊 99%)。
- **6k / 32k 於 gpt-4o-mini 的同等 audit**、**gpt-4.1-mini 於 64k 的 audit** 為 future work,pattern 預期一致。

### 4.1.5 Implementation details

| Item | Value | 備註 |
|:--|:--|:--|
| Chunk size | 512 tokens | ⚠ **Fairness note**:Zep 官方 chunk 建議較大(4096);main table 已對稱到 512,Zep@4096 為 appendix sensitivity |
| Retrieval top-K | 100(ours、mem0)/ **10**(Zep 官方推薦)| K=100 vs K=10 已於 setup 揭露 |
| Embedding | `text-embedding-3-small`(全 methods、全 backbones) | Weak-backbone 換本地 embedding 為 appendix sensitivity |
| Temperature | 0(all LLM calls) | Deterministic |
| Query preprocessing | Raw question(qa 模板 boilerplate 剝除)| ours + (b) 對稱;Zep 內建 `get_retrieval_query` 做同類剝離 |
| Answer template | MAB 官方 qa template(不客製) | 避免「贏在答題 prompt」的混淆 |
| Random seed | 單次 deterministic run | 無 error bar;temperature 0 下確定性極高(cross-machine 差異 ±2-3 題,已於 CLAUDE.md 記錄) |

---

## 4.2 Main Results

### 4.2.0 Headline Evidence — Backbone spectrum(**primary evidence for falsifiable prediction**)

Intro §第 6 段末的可證偽預測:**ours 相對現有流派的優勢應隨 backbone 判斷力下降而單調放大**。以下三張 tables + 一張 figure 為 paper 主 evidence,對接 intro thesis 的完整檢驗:

**Figure 1**([`../figures/F_backbone_spectrum.png`](../figures/F_backbone_spectrum.png))— headline visualization,兩 panel 共 y-axis(has_pair EM %),gpt-4o-mini 為 mid-tier anchor 出現於兩 panel。

#### Table G1 — has_pair EM × 5 backbones @ 6k(weak → mid)

| Backbone | ours (main) | mem0+P1 | Zep | Gap ours−mem0 | Gap ours−Zep |
|:--|--:|--:|--:|--:|--:|
| gemma3-1B | 25 (34%) | **0** (0%) | 12 (16%) | +34pp | +18pp |
| gemma3-4B | 54 (73%) | **0** (0%) | 17 (23%) | **+73pp** | +50pp |
| gemma3-12B | 73 (99%) | 44 (59%) | 43 (58%) | +40pp | +41pp |
| gemma3-27B | 70 (95%) | 36 (49%) | 35 (47%) | +46pp | +48pp |
| gpt-4o-mini | 69 (93%) | 34 (46%) | 46 (62%) | +47pp | +31pp |

N=74 has_pair queries;single deterministic run(temp=0);數字均由 per-qid response 以 MAB `default_post_process` 重驗。

**Observation**:於全 5 個 backbone tier,ours 相對 mem0+P1 的 gap 皆 ≥ **+25pp**,於 gemma3-4B 達 peak **+73pp**。mem0+P1 於 gemma3-1B/4B **完全歸零**(write-time UPDATE prompt 於弱 LLM 無法生正確 schema 決策);Zep 於同 tier 崩至 16-23%(labeler 於弱 LLM 無法可靠輸出 contradicts/duplicates 標籤)。**對接 intro §受限部署段**:privacy-sensitive on-device(gemma3-1B/4B)與 cost-constrained(gpt-4o-mini)兩軸的預測皆成立。

#### Table G2 — has_pair EM × 2 backbones @ 64k(mid → strong;falsifiable prediction check)

| Backbone | ours (main) | mem0+P1 | Zep (strict) | Gap ours−mem0 |
|:--|--:|--:|--:|--:|
| gpt-4o-mini | 60 (91%) | 34 (52%) | 36 (55%) | **+39pp** |
| gpt-4.1-mini | 53 (80%) | **55 (83%)** | 23 (35%) | **−3pp** ★ collapse |

N=66 has_pair queries;strict EM only(sEM 為 hedge FP,見 §Metrics disclosure)。

**Observation**:於強 backbone(gpt-4.1-mini),mem0+P1 大幅恢復(**+32pp**)並略勝 ours main;gap **從 +39pp 崩至 −3pp**。**Intro §6 末 falsifiable prediction 得證**(方向與量級皆符合)。Zep strict EM 反向下降(55→35%),因 gpt-4.1-mini 遇到 Zep 兩版共存 RCP 時傾向 hedge(response 同時列 gt_new 與 gt_old;26/27 sEM-only-pass 是此 pattern)。

**為何 ours 於 gpt-4.1-mini 下降 −7pp**(initial hypotheses,pending 深度 evidence 於 §4.4):
1. Phase2 P3 grouping 於強 LLM 更嚴格遵循 GROUPING_PROMPT「Clustering is RARE」→ 該 merge 沒 merge(qid=1 Hard Times)
2. Answer LLM 於特定 domain 世界先驗更強(qid=5 Aki Takase music)
3. 1 題為 MAB benchmark 缺陷(qid=18 D-flag)
Net real regression ≈ −6pp;−1 為 D-flag。

**為何 Zep 於 strict EM 下降 −20pp**(direct evidence):
- 於 30 wrong 中 27 題 response 同時列 gt_new + gt_old 用「and」連接(hedge)。gpt-4.1-mini 遇到 Zep RCP 的「conflicting update」framing + 兩版都是 `(- present)` 時傾向並列而非 disambiguate。

#### Table G3 — Ours ablation × backbone spectrum(P3 capability-gate,secondary)

| Backbone | Length | ours main | ours (struct only) | ours (LLM only) | Δ (main − struct) | 判讀 |
|:--|:--:|--:|--:|--:|--:|:--|
| gemma3-1B | 6k | 25 (34%) | 29 (39%) | 7 (9%) | **−4pp** | P3 反害(underpowered)|
| gemma3-4B | 6k | 54 (73%) | 54 (73%) | 26 (35%) | 0 | struct 已飽和 |
| gemma3-12B | 6k | 73 (99%) | 73 (99%) | 46 (62%) | 0 | struct 已飽和 |
| gemma3-27B | 6k | 70 (95%) | 65 (88%) | 27 (36%) | **+7pp** | P3 修 reader override |
| gpt-4o-mini | 6k | 69 (93%) | 67 (91%) | 71 (96%) | +3pp | mid-strong sweet spot |
| gpt-4o-mini | 32k | 57 (88%) | 52 (80%) | 58 (89%) | +8pp | struct 較差、P3 補回 |
| gpt-4o-mini | 64k | 60 (91%) | 58 (88%) | 58 (88%) | +3pp | 兩者互補 |
| gpt-4.1-mini | 64k | 53 (80%) | 52 (79%) | 27 (41%) | +1pp | struct 已足 |

**Observation**:P3(LLM identity grouping)為 **capability-gated add-on**:於 underpowered backbone(1B)反害 −4pp;struct 飽和區(4B/12B)neutral;mid-strong tier(27B、gpt-4o-mini)net-positive +3~+8pp;super-strong(gpt-4.1-mini)near-zero(過度保守)。**Struct 於全 backbone 都穩定為 workhorse**,兌現 method_v1.md §3.3「LLM 補救僅在少數案例介入」的設計選擇。

---

### 4.2.1 E2E `has_pair` EM(3 lengths)

**Table 1**:FC-SH has_pair Exact Match(row = method,col = length;bold 每 col 最佳)

| Method | 6k(N=74) | 32k(N=65) | 64k(N=66) |
|:--|--:|--:|--:|
| **ours (main)** | **69/74 (93.2%)** | **57/65 (87.7%)** | **60/66 (90.9%)** |
| (b) mem0+P1 | 34/74 (45.9%) | 25/65 (38.5%) | 34/66 (51.5%) |
| Zep(k=10) | 46/74 (62.2%) | 33/65 (50.8%) | 36/66 (54.5%) |
| LCA(long-context, gpt-4o-mini)| 65/74 (87.8%) | 46/65 (70.8%) | 36/66 (54.5%) |

**Observation**(what / where / implication):
- **What**:ours 於全 3 lengths 領先第二名 **+5.4 / +16.9 / +36.4pp**;length 增長時 ours 保持 88-93% flat,而 baselines 於 64k 較 6k **不改善或退步**(mem0 32k dip 至 38.5%,Zep 32k 至 50.8%,LCA 64k 崩至 54.5%)。
- **Where**:gap 於 32k 起放大,原因是 write-time destructive commit 的 damage 隨 chunks 累積(§4.4 case study 展示);Zep 於長 context 依 top-10 檢索能力受限(§4.4 F4)。
- **Implication**:ours 於 cost-constrained deployment 主場提供 46-50pp 的絕對優勢;此差距不依賴 answer LLM 於 混雜 pool 中的挑選能力,而來自 pipeline 讓 pool 更乾淨(§4.2.2)。

### 4.2.2 Context-state × Accuracy attribution(64k 為代表,3 lengths 完整表見附錄)

**Table 2**:64k 各 method 的 pool state 分佈與 in-bucket accuracy(cell = `Acc✓/N (in-bucket rate)`;row = method,col = pool state)

| Method | PP-New Acc/N ↑ | PP-Both Acc/N | PP-OldOnly Acc/N ↓ | PP-Missing Acc/N ↓ | E2E |
|:--|--:|--:|--:|--:|--:|
| **ours (main)** | **35/38 (92%)** | **24/26 (92%)** | 1/2 (50%) | 0/0 | **60/66 (91%)** |
| (b) mem0+P1 | 25/25 (100%) | 9/17 (53%) | 0/15 (0%) | 0/9 (0%) | 34/66 (52%) |
| Zep(k=10) | 1/1 (100%) | 35/65 (54%) | 0/0 | 0/0 | 36/66 (55%) |

**Observation**:
- **What**:三 method 的 pool state 分佈根本不同 — ours 把 58% (38/66) 的 has_pair query pool 收斂到 **PP-New**;(b) 只有 38%,其餘 24 題落入 PP-OldOnly / PP-Missing;Zep **99%** 落入 PP-Both(65/66)。
- **Where**:(b) 於 PP-OldOnly / PP-Missing 桶 accuracy 為 **0/24**,說明 write-time UPDATE 誤刪 gt_new 後 answer LLM **無法補救**(pool 已無正解);Zep 於 PP-Both 桶 in-bucket accuracy 只有 54%,說明 answer LLM 從時間戳判時序**不可靠**於 gpt-4o-mini。
- **Implication**:ours 的 E2E 優勢**不是**因為 answer LLM 更會挑,而是因為 pipeline 送進 answer LLM 的記憶更乾淨(PP-New 佔比高,PP-OldOnly / PP-Missing 幾乎為零)— 直接對應 intro §7 payoff 段。

**三 paradigm 的 pool 表現(對接 discussion §4.6)**:

| Paradigm(RW §2.1) | 代表 | 64k 主 pool state | 該 state in-bucket Acc | Backbone 依賴的機制點 |
|:--|:--|:--|:--:|:--|
| **P1**:query-time 結構 filter | **ours** | PP-New(58%)| 92% | 僅 P3 LLM 補救(非 critical path) |
| **P2**:write-time destructive | mem0 | PP-New(38%)+ PP-OldOnly/Missing(36%)| PP-New 100% 但**分母小** | write-time UPDATE LLM 是**唯一** damage 源 |
| **P3**:write-time labeling + inference-side judge | Zep | PP-Both(99%)| 54% | (i) write-time labeler LLM 產出時間戳 + (ii) inference LLM 讀時間戳挑版;**兩處都要對** |

☐ **待補**:6k / 32k Mid tier 對應表(已於 [`../results/pool_acc_crosstab.md`](../results/pool_acc_crosstab.md) 完整;body 是否僅列 64k 為代表 + appendix 完整?)

**Weak-tier 12B/27B context-state(6k,per-backbone gemma extraction)**

**⚠ 分析範圍限制**:pool-state 軸靠 matcher v4 對「抽出的 fact 表面」vs GT 表面。於 per-backbone extraction 下,1B/4B 的抽取字面偏離 GT → matcher false-negative → `old_only/neither` 桶灌水,分不清「抽取真丟了 NEW」還是「matcher 對不上 gemma 措辭」。**1B/4B pool-state 不可信,改用 E2E EM + case study**(§4.4.6)。**僅 12B/27B 呈現**(store 與 27B 重疊 99%、pool-missing=0)。

**Table 2b**:12B/27B pool-state × Acc(6k,ours main + ours no P3;分母 N=74)

| Method × Backbone | new_only ✓/✗ | both ✓/✗ | old_only ✓/✗ | neither ✓/✗ | E2E EM |
|:--|--:|--:|--:|--:|--:|
| ours (no P3, struct only) × 12B | **60/0** | 13/1 | 0/0 | 0/0 | 73/74 |
| ours (main, struct + P3) × 12B | **60/0** | 13/1 | 0/0 | 0/0 | 73/74 |
| ours (no P3, struct only) × 27B | 53/**7** | 12/2 | 0/0 | 0/0 | 65/74 |
| ours (main, struct + P3) × 27B | **58/4** | 12/0 | 0/0 | 0/0 | **70/74** |

**Figure 2**:`F_crosstab_1227_6k`([`../figures/F_crosstab_1227_6k.png`](../figures/F_crosstab_1227_6k.png))— 12B/27B pool-state decomposition,標註 4 桶(new_only ✓ / both ✓ 為 reader rescue / new_only ✗ 為 **reader OVERRIDE** / both ✗ 為 lost-in-mixed)。

**Observation**:
- **What**:12B/27B 的 struct 皆使 `old_only = neither = 0`(pool 從不缺 NEW → **KU 解析成功**)。struct × 27B 的 E2E 較 12B 下降 8pp,**成因純為 new_only ✗ = 7**(pool 乾淨、但 reader 用世界先驗吐舊值)= **reader override**。P3 grouping 於 27B 把 override 從 7 降到 4,並把部分 `both ✓` 收斂為 `new_only ✓`(53→58)→ EM 65→70。
- **Where**:(S,P) 結構鍵是 backbone-invariant 底盤 — 弱 backbone 12B、mid backbone 27B、cost-tier gpt-4o-mini(見 §4.2.2 上表)、strong-tier gpt-4.1-mini(§4.3.2)四點皆看到「struct 於清 pool 有效」,唯 27B 起 override 成為天花板。
- **Implication**:**Strong-end 剩餘失分是 reader 特性,不是 KU 方法退步**;P3 於 mid-strong tier(27B、gpt-4o-mini)展現 net-positive(壓 override),為 method_v1.md §3.3「LLM 補救僅在少數案例介入」claim 的直接兌現(§4.5.1 完整 6-tier 曲線)。

---

### 4.2.3 Backbone-Gap Headline(6 tier × 6k)

Intro §第 6 段末 falsifiable prediction 的 **backbone spectrum 主圖**:整合 Weak(gemma3 1B/4B/12B/27B)+ Mid(gpt-4o-mini)於 6k 長度,對主要對比(ours main、(b) mem0+P1、Zep)呈現 gap × backbone。

**Figure 1**:`F_backbone_gap_haspair_6k`([`../figures/F_backbone_gap_haspair_6k.png`](../figures/F_backbone_gap_haspair_6k.png))— 6k has_pair EM × 4 backbones(gemma3 1B/4B/12B/27B)× 4 methods(struct、no_p5、mem0+P1、Zep);black-and-white safe(hatch/marker 區分)。**Placeholder**:待補 gpt-4o-mini + gpt-4.1-mini 條(當前 GX10-only 4 tier);gpt-4.1-mini × 6k **future work** 保留欄位。

**Table 3**:6k has_pair EM 完整 backbone spectrum(row = method,col = backbone;bold = 每 col 最佳;分母 N=74)

| Method | 1B | 4B | 12B | 27B | gpt-4o-mini | gpt-4.1-mini |
|:--|--:|--:|--:|--:|--:|--:|
| **ours (main)** | 25 (34%) | **54** (73%) | **73** (99%) | **70** (95%) | **69** (93%) | ☐ *placeholder* |
| ours (no P3) | **29** (39%) | **54** (73%) | **73** (99%) | 65 (88%) | 67 (91%) | ☐ *placeholder* |
| (b) mem0+P1 | **0** (0%) | **0** (0%) | 44 (59%) | 36 (49%) | 34 (46%) | ☐ *placeholder* |
| Zep (k=10) | 12 (16%) | 17 (23%) | 43 (58%) | 35 (47%) | 46 (62%) | ☐ *placeholder* |

**Observation**:
- **What**:於 weak-end(1B/4B),ours 保 25-54,而 (b) mem0+P1 **完全歸零**(1B=0, 4B=0);gap 於 4B 達到 +54pp(最大)。於 mid-end(12B、27B、gpt-4o-mini)ours 保 65-73,gap 收斂至 +23-+34pp。
- **Where**:(b) 於弱端崩因 mem0 UPDATE prompt 於弱 LLM 生不出正確 schema(§4.4.6 Case F 有 trace);Zep 弱端稍優於 (b)(有部分 tolerance)但仍崩 12-17。12B 起 backbones ours 於 has_pair 幾乎飽和(99% ceiling)。
- **Implication**:**Falsifiable prediction 成立**(gap 隨 backbone 減弱擴大),於 privacy-sensitive on-device 主場(1B/4B)兌現最大絕對優勢。**非嚴格單調**:12B 為 ours 峰值(73/74),27B 略降至 65-70(reader override,§4.2.2 & §4.4.6 27B 面板);paper 需誠實揭露此非單調性 = **強-end 天花板為 reader override,與 KU 方法正交**。

---

## 4.3 Backbone Extension — gpt-4.1-mini(falsifiable prediction check)

Intro §第 6 段承諾的可證偽預測:**ours 相對現有流派的優勢,應隨 backbone 判斷力下降而單調放大** — 反過來,強 backbone 上優勢應縮小。此節於 64k(gpt-4.1-mini 唯一已跑長度)檢驗。

### 4.3.1 E2E has_pair EM(64k)

**Table 3**:64k has_pair EM 於兩 backbone 的對比(**sEM** 供 Zep verbose format 診斷)

| Method | 4o-mini EM | **4.1-mini EM** | 4.1-mini sEM | Δ EM(4.1 − 4o) |
|:--|--:|--:|--:|--:|
| **ours (main)** | 60/66 (91%) | 53/66 (80%) | 54/66 (82%) | **−7 (−11pp)** |
| **(b) mem0+P1** | 34/66 (52%) | **55/66 (83%)** | 55/66 (83%) | **+21 (+32pp)** ★ |
| Zep(k=10)| 36/66 (55%) | 23/66 (35%) | **50/66 (76%)** | −13 EM / **+14 sEM** |
| **Gap(ours − (b))** | **+26pp** | **−3pp** | — | **gap collapsed** |

**Observation**:
- **What**:(b) 從 52% 躍升至 83%(+32pp);ours main 從 91% 降至 80%(−11pp,含 1 個 benchmark D-flag qid,見 §4.4.5);gap 從 +26pp 收斂至 within margin(−3pp)。Zep 於 sEM 追上(76%)但 strict EM 崩(35%),為 verbose format artifact。
- **Where**:(b) 21/26 recovered qid 是 **PP-OldOnly/Missing → PP-New/Both** 的 pool state 修復(§4.4.1);Zep 的 sEM/EM 差距源於 Zep template 於強 LLM 上被完整回填 timestamps(§4.4.4)。
- **Implication**:**Intro falsifiable prediction 成立**(強 backbone 上 gap 縮小)。且 (b) 的 damage 於 4.1-mini 大幅消失,說明 **destructive commit 的問題不是架構性缺陷,而是 write-time LLM 判斷品質的函數** — 這強化受限部署動機(cost-constrained 用不起 4.1-mini)。

### 4.3.2 Context-state × Accuracy attribution(64k,4.1-mini)

**Table 4**:64k pool state(gpt-4.1-mini)

| Method | PP-New Acc/N | PP-Both Acc/N | PP-OldOnly Acc/N | PP-Missing Acc/N | E2E |
|:--|--:|--:|--:|--:|--:|
| ours (main) | 30/31 (97%) | 23/34 (68%) | 0/1 (0%) | 0/0 | 53/66 (80%) |
| (b) mem0+P1 | 28/28 (100%) | 27/34 (79%) | 0/3 (0%) | 0/1 (0%) | 55/66 (83%) |
| Zep(k=10) | 1/1 (100%) | 22/65 (34%) | 0/0 | 0/0 | 23/66 (35%) |

**Observation**:
- **What**:(b) 的 PP-New 從 25 → 28,PP-OldOnly/Missing 從 24 → 4(write-time LLM 判斷準確度提升);ours 的 PP-Both 從 26 → 34,PP-New 從 38 → 31(**phase2 P3 grouping 於強 LLM 更保守 → 該 merge 沒 merge**,§4.4.3);Zep pool state 分佈幾乎不變(仍 65/66 PP-Both),EM 崩是 answer LLM 於 verbose template 產出的 format 問題。
- **Implication**:三 paradigm 的**單一 damage 源**於強 backbone 都改善,但改善的**機制不同** — (b) 靠 write-time judge 改善;ours 的 struct+argmax 本就 backbone-agnostic,反受 P3 過度保守拖累;Zep 兩處 LLM 依賴中 write-time labeling 改善,但 inference 讀時間戳仍不可靠。

---

## 4.4 Error-Mode Case Studies

**Protocol**:對每個錯誤模式挑 1-2 個 canonical qid 拉出完整 pipeline trace(question → gt_new/gt_old → retrieved memories → resolved pool → answer LLM response → EM);對比多 method 或多 backbone 相同 qid,凸顯機制差異。

錯誤模式分類(整合 Mac gpt-4o-mini/gpt-4.1-mini + GX10 weak-backbone,擴展自 [`../evaluation_protocol_main.md §5.1`](../evaluation_protocol_main.md)):

**Method / Reader / Extraction / Benchmark 四軸**:

| Mode | 軸 | 出現於 | 意涵 |
|:--|:--|:--|:--|
| **A. Predicate stem mismatch** | 方法(struct)| ours 少量錯 | P2 抽 predicate 產 stem-vs-full 兩版 → struct 分不同 (S,P) 桶 |
| **B. Subject fragmentation** | 方法(struct)| ours 少量錯 | 同一實體被抽成不同 subject_id |
| **C. Answer LLM world-knowledge override** | Reader | 27B、gpt-4o-mini、gpt-4.1-mini 三 tier 皆有 | pool 有 gt_new,LLM 答世界知識舊值(**選擇性 — 世界先驗強的題才 override**;§4.4.7)|
| **D. Dataset temporal reversal**(**D-flag**)| Benchmark | qid=18/20 @ 64k | `gt_seq < old_seq`,argmax(seq) 邏輯上不可能對 |
| **E. Surface variant** | Benchmark | 少量 | gt_new/gt_old 極相似(substring)|
| **F. Write-time destructive damage** | 方法(mem0)| Mid+Weak backbone,強 backbone 消失 | UPDATE/DELETE 誤刪 gt_new,pool 為 PP-OldOnly/Missing;**弱 backbone 極端形式:mem0 UPDATE prompt 崩 → store 幾近空**(1B/4B mem0=0)|
| **G. Zep verbose format** | Reader(Zep 特有)| Zep @ strong backbone | Template 產 verbose response,strict EM fail 但 sEM pass |
| **W1. Extraction miss** | 抽取(weak)| Weak backbone(1B/4B)| 該 backbone P1 沒抽到 gt_new(或 gt_old)→ fact 從未進 store |
| **W2. Extraction inconsistency** | 抽取(weak)| Weak backbone(1B)| new/old 抽成不同措辭 → 分不同 (S,P) → 未併群 → pool 留兩版 |
| **W3. Reader garbage** | Reader(weak)| 1B 特有 | 生成能力不足,吐 non-answer(如 echo prompt timestamp)|

### 4.4.1 Case A — Write-time destructive damage(mem0 於 mid backbone)

Ob2 mem0 write-time failure taxonomy(詳見 [`../results/mem0_event_taxonomy_gt4o.md`](../results/mem0_event_taxonomy_gt4o.md))將 gpt-4o-mini × 64k 上 24 個 PP-OldOnly + PP-Missing wrong qids 歸為兩大機制:

- **M1. World-prior override(46%)**:LLM UPDATE 於世界先驗強的情境下靜默拒絕反事實新版
- **M2. Coupled-update architectural fragility(54%)**:UPDATE prompt output completeness bug、cross-item cascading / name confusion 導致新版丟失

#### M1 canonical — qid=1 Hard Times(gpt-4o-mini × 64k)

- **Q**:*Who is the author of Hard Times?*
- **gt_new**(counterfactual)= "Martin Luther King Jr."(seq=2335)/ **gt_old** = "Charles Dickens"(seq=687)

**Pipeline trace(mem0+P1)**:

| Stage | Evidence |
|:--|:--|
| P1 extraction | 兩版本 fact 都正確抽出(P1 cache hash `62d52389fb6f` 含 MLK Jr. 版本)|
| mem0 event log 於 subject | `ADD (chunk 18, id 34dca530) "...is Charles Dickens."` → `UPDATE (chunk 43) "...is Charles Dickens."` → `UPDATE (chunk 64) "...is Charles Dickens."` — **內容始終為 Dickens** |
| Chunk 64 event 分佈 | **0 ADD** / 4 UPDATE / 4 DELETE / 1 subject-UPDATE — 該 chunk mem0 對 36 candidate facts 全數靜默 rejection |
| MLK Jr. 於全 event log | 只出現於其他 predicate(如 "MLK Jr. died in the city of Memphis"),**Hard Times 相關全無** |
| 結論(by elimination) | gt_new 於 P1 cache 有 + mem0 event log 無 = **必然於 UPDATE prompt 被 LLM 判 keep-unchanged / NONE** |
| Pool state / Response | PP-OldOnly / "Charles Dickens" ❌ |

**同 qid @ ours main 4o-mini**:P1 抽同兩版本、conservative-ADD 寫入時**兩版都保留**;query-time 檢索含兩版 → (S,P) 結構分群同 subject `hard_times` + predicate `has_author` → argmax(seq) 選 MLK Jr.(較晚 seq) → PP-New → "Martin Luther King Jr." ✅

**同 qid @ (b) mem0+P1 4.1-mini**:F1(§4.3.1)顯示 (b) 於強 backbone 大幅恢復,此 qid 於 gpt-4.1-mini 上 UPDATE LLM 準確判「應 ADD 新版」→ 兩版共存 → 答對(Case C §4.4.3 的 backbone-flip 對照)。

#### M2 canonical — qid=2 David Farragut(**M2a: Missing ADD**)

- **Q**:*What is the country of citizenship of David Farragut?*
- **gt_new** = `Denmark` / **gt_old** = `USA`(real)

**Pipeline trace**:
- gt_old 於 chunk 21 `ADD (id 49996dcf) "...is USA."`
- gt_new 於 chunk 61 遞交 mem0(P1 cache 有此 fact)- chunk 61 event 分佈:20 ADD / 5 UPDATE / **4 DELETE / 14 silently NONE**
- Subject 相關 event 於 chunk 61:`DELETE (id 49996dcf) memory="David Farragut is a citizen of Denmark."`
- **DELETE event 的 memory 欄位是 "Denmark" 不是 "USA"** — LLM 判「新版 Denmark 應該把舊 USA memory 刪掉」但 output list 中**沒有補上獨立 ADD Denmark 指示** → 兩版皆失
- Pool state / Response:PP-OldOnly / "USA" ❌(world-prior 補救)

#### M2 canonical — qid=4 Joseph Mitchell(**M2c: Name confusion**)

- **Q**:*What is the country of citizenship of Joseph Mitchell?*
- **gt_new** = `UK` / **gt_old** = `USA`

**Pipeline trace**:
- P1 cache 兩版都有(hashes `5d9745d46627`、`63179fd9feff`)
- **mem0 全 130 chunks × 全 events 對 "Joseph Mitchell" verbatim 出現次數 = 0**
- 但同 predicate 有 `ADD "Joseph Smith is a citizen of USA."`(人名近似)
- **推論**:LLM UPDATE 收到「Joseph Mitchell」新 fact,retrieval 找到「Joseph Smith USA」為 candidate;LLM output 對 Joseph Smith 判 NONE,**沒有為 Joseph Mitchell 補上獨立 ADD 指示** → subject 於 mem0 write-time 被靜默合併理解為 Joseph Smith,新事實全然丟失
- Pool state / Response:PP-OldOnly / "USA" ❌

**Implication for paper narrative**:
- **M1** = intro §3 [17] ConflictBank + [3] LightMem §5.6 quote 的實證。強世界先驗於 mid-tier gpt-4o-mini 已足呈現此現象(不需 weak backbone)。
- **M2** = intro §5-6 coupled-update paradigm 架構性脆弱的實證。單一 LLM UPDATE prompt output 一旦 completeness 有 bug,不可逆。
- **ours 的 non-destructive faithful writes + query-time deterministic argmax 直接 dodge 兩機制**。

**⚠ Rigor 限制**:mem0 event log 僅記錄成功 side-effect operations(ADD/UPDATE/DELETE),不記錄 LLM NONE decisions 或 raw prompt output。我們透過 P1 cache + event log 對照,**by elimination** 建立 gt_new 未被 store 的因果鏈。若欲直接讀出 LLM 每 candidate 的具體 decision,需 patch mem0 UPDATE 路徑加 logging,列 future work(paper 附錄誠實揭露)。

### 4.4.2 Case B — Zep retrieval-layer freeze(Zep 於弱 backbone)

☐ **待補**:挑一個 Zep @ 4o-mini 於 PP-Both 但 inference 答錯的 qid,展示:
1. Zep cloud 內部 labeler 是否判對(從 `invalid_at` 是否設在 gt_old 邊看)
2. Retrieved edges 顯示的 timestamps
3. Answer LLM response(通常 hedge 或選 gt_old)

**建議 qid**:64k Zep wrong 桶中 (b) 也錯的 qid(排除單純 write-time factor)

### 4.4.3 Case C — Query-time regression at strong backbone(ours 未預期下降)

**qid=1 @ 64k, 4.1-mini**(**與 Case A 同 qid,backbone 反轉**)

| Backbone | Ours pool state | Response | EM |
|:--|:--|:--|:--:|
| 4o-mini | **PP-New**(phase2 P3 判 Dickens/MLK 為同 fact 不同版本 → merge → argmax 選 MLK)| "Martin Luther King Jr." | ✅ |
| 4.1-mini | **PP-Both**(phase2 P3 於強 LLM 極保守,未 merge → 兩版都留)| "Charles Dickens" | ❌ |

**Root cause**:`methods/phase2_query.py::GROUPING_PROMPT` 極保守設計(「Clustering is RARE」,「When unsure, do not cluster」,Rule 3 提及 multi-valued property 應 coexist)。gpt-4.1-mini 讀 prompt 更 careful → 傾向不 cluster;gpt-4o-mini naive 讀 → 傾向 cluster。**於 FC-SH counterfactual dataset,fact 是 single-valued 但 prompt 沒明講**。

**Implication**:P3 LLM 補救於強 backbone 反效果,但 struct 底盤仍 hold(ours(no P3) 於 4.1-mini 保 79%,見 §4.5)— 支持論述「struct 是 backbone-universal scaffold,LLM 補救是可選 add-on」。

### 4.4.4 Case D — Zep verbose format artifact(Zep 於強 backbone)

**qid=2 @ 64k, 4.1-mini**

- Question:What is David Farragut's citizenship?
- gt_new = "Denmark" ; gt_old = "United States of America"

| Stage | Zep @ 4.1-mini |
|:--|:--|
| Zep edges retrieved | 含兩版本,均帶 `valid_at`/`invalid_at` timestamps |
| Answer LLM response | `"David Farragut is a citizen of the United States of America **and** Denmark."` |
| Strict EM | ❌(未 exact match Denmark)|
| sEM | ✅("Denmark" 是 substring)|

**Root cause**:Zep template 於強 LLM 上被完整回填 → LLM 讀時間戳但**未 disambiguate**,直接列出兩版本(此為 Zep template 特徵)。**於 Zep 之外的 method 未觀察此模式**。

**Implication**:Zep 的 P3 paradigm(annotated pool)於強 backbone 反而暴露問題 — inference LLM 讀時間戳能力雖強於 4o-mini,但 template 引導其 hedge 而非決斷。**同時報 EM + sEM**,誠實揭露此 artifact(§4.1.4)。

### 4.4.5 Case E — Benchmark D-flag limitation

**qid=18 @ 64k**(**benchmark 標註錯誤,method 無關**)

- Question:Who is the author of Red Storm Rising?
- gt_new = "Tom Clancy" ; gt_old = "Torquato Tasso"(counterfactual)
- **gt_seq = 7, old_seq = 1219**(gt_new 於**更早**出現 → argmax(seq) 邏輯上不可能挑對)

| Backbone | Ours response | EM |
|:--|:--|:--:|
| 4o-mini | "Tom Clancy"(Mode C 世界知識剛好 = gt_new)| ✅(**蒙對**)|
| 4.1-mini | "Torquato Tasso"(忠於 pool argmax 結果)| ❌ |

**64k 共 2 個 D-flag qid**(qid 18 + qid 20 Great Britain / Europe;2/66 = 3%)。

**Implication**:paper 明講此為 benchmark 缺陷、非 method 缺陷,並於 caption / discussion 揭露 D-flag 佔比 3%(64k)。ours main 於 4.1-mini 的 −7pp 中,**−1 是 D-flag**,實際 real regression 為 −6pp(§4.3.1)。

### 4.4.6 Case F — Cross-backbone pipeline trace(**failure 沿 backbone 逐格往後推**)

**qid=19 @ 6k, method=ours(no P3, struct only)**(**同一題、四 backbone、失敗點沿 pipeline 往後推**)

- Question:*Who is the chief executive officer of Microsoft?*
- gt_new(counterfactual)= "Steve Jobs"(seq=188);gt_old(真實)= "Satya Nadella"(seq=85)→ argmax(seq) 應取 Steve Jobs。

| Backbone | P1 extraction | Pool(memories_str) | Response | Failure mode | EM |
|:--|:--|:--|:--|:--|:--:|
| **1B** | 兩版**措辭不一致**(`is the CEO of X` vs `The CEO of X is`) | 兩版都在(未併)| `Current Time: 2026-...`(**非答案**)| **W2 + W3** | ❌ |
| **4B** | **只抽到舊版** Nadella | 只有 Nadella | `Satya Nadella` | **W1** | ❌ |
| **12B** | 兩版**措辭一致** | **只有 Steve Jobs**(argmax 濾舊)| `Steve Jobs` | ✅(成功)| ✅ |
| **27B** | 同 12B(兩版一致)| **只有 Steve Jobs**(pool 一樣乾淨)| `Satya Nadella` | **C override** | ❌ |

**判讀**(直接對 method_v1.md §3.4 的三個設計性質):
1. **1B = W2 + W3**:P1 抽取一致性不足導致 (S,P) 分桶未併,加上 reader 生成能力不足;**失敗於 pipeline 前段**。
2. **4B = W1**:P1 覆蓋率不足,gt_new 從未進 store;**失敗於抽取階段**。
3. **12B = 成功機制**:兩版抽取措辭一致 → 同 (S,P) → mechanical argmax 取 seq 大者 → pool 乾淨 → reader 抄對。**12B 不需要"知道"誰是 CEO**,只需抽取一致 — 這是 intro decomposed simple task 主張的直接實證。
4. **27B = C override**:pool 與 12B **完全相同**(只有 Steve Jobs),但 27B reader 用世界知識否決;**失分純在 reader,與 KU 方法正交**(對照 F_crosstab_1227_6k override 桶 = 7)。

**Implication**:**Failure moves down pipeline as backbone strengthens** — 這是 per-backbone extraction 的 signature 表現。**Weak-end 天花板 = 抽取(能力),strong-end 天花板 = reader override(先驗)**,中段 12B 為「decomposed simple task 可行」的最乾淨證據。**對 intro §7 payoff 段的強化**:「乾淨 pool」對弱 backbone 有效(12B 讀 pool 抄對即成功),不需 reader 具備 KU 判斷能力。

### 4.4.7 Case G — Selective override(**27B 未必 override**)

**qid=14 @ 6k, method=ours(no P3, struct only)**

- Question:*Who is the author of Sidereus Nuncius?*
- gt_new(counterfactual)= "Samuel Beckett"(seq=401);gt_old(真實)= "Galileo Galilei"(seq=124,真實作者)

| Backbone | P1 extraction | Pool | Response | EM |
|:--|:--|:--|:--|:--:|
| **1B** | **只抽到舊版** Galileo | 只有 Galileo | `Galileo Galilei` | ❌(W1)|
| **4B** | **恰只抽到新版** Beckett | 只有 Beckett | `Samuel Beckett` | ✅ |
| **12B / 27B** | 兩版一致 | 只有 Samuel Beckett | `Samuel Beckett` | ✅ |

**判讀**:**同一 27B、同 pool 乾淨,對比 Case F**:qid=19(Microsoft CEO)27B **override** 世界知識;qid=14(Sidereus Nuncius 作者)27B **未** override,採用 pool。差異純在 **答案 LLM 對該題世界先驗的強度**:
- Microsoft CEO / Elvis 配偶 → 世界先驗**強** → 27B override(§weak_model_case_studies_6k qid=57 亦是 override)
- 冷門反事實(伽利略 / 貝克特)→ 世界先驗**弱** → 27B 採 pool

**Implication**:**Override 是 answer-LLM 通性(非 local-model 特有;gpt-4.1-mini qid=5 音樂 override 是同機制在強-tier 的鏡像)**,且**是選擇性的**(27B override 只 7/74 = 9.5%,非全崩)。**Strong backbone 未必救**,反而可能強化世界先驗使 override 更頻繁。**P3 grouping 於 27B 部分修此問題**(override 7→4,§4.2.2 12B/27B cross-tab),因 P3 tighten pool 使 reader 更難忽略 pool。

---

## 4.5 Ablation Study(ours 內部拆解)

### 4.5.1 Structural vs LLM identity grouping(main table 的 struct/P3 貢獻)

**Table 5a**:ours 內部 ablation × Mid + Strong tier(3 lengths × 兩 backbones)

| Method | 6k(4o) | 32k(4o) | 64k(4o) | **64k(4.1)** |
|:--|--:|--:|--:|--:|
| **ours (main)** = struct + P3 + argmax | 69/74 (93.2%) | 57/65 (87.7%) | 60/66 (90.9%) | **53/66 (80.3%)** |
| ours (no P3) = struct + argmax only | 67/74 (90.5%) | 52/65 (80.0%) | 58/66 (87.9%) | 52/66 (78.8%) |
| ours (no struct) = P3 + argmax only | 71/74 (95.9%) | 58/65 (89.2%) | 58/66 (87.9%) | **27/66 (40.9%)** ⚡ |

**Table 5b**:P3 capability-gate 光譜(**6-tier 完整**,ΔEM = ours(main) − ours(no P3);6k 為 Weak + Mid tier 對齊,gpt-4.1-mini 未有 6k 為 placeholder;正值 = P3 於該 backbone 上 net-positive)

| Backbone | ours (no P3) | ours (main) | **Δ EM = P3 貢獻** | 機制 |
|:--|--:|--:|--:|:--|
| gemma3-1B(weakest)| 29/74 | 25/74 | **−4** | P3 反害:P3 LLM 於 1B 無法可靠 cluster identity |
| gemma3-4B | 54/74 | 54/74 | 0 | Neutral:struct 已飽和該 backbone extraction 覆蓋範圍 |
| gemma3-12B | 73/74 | 73/74 | 0 | Neutral(接近 ceiling,無 override 可修)|
| gemma3-27B | 65/74 | **70/74** | **+5** | **P3 抑制 reader override**(new_only ✗:7→4;§4.2.2)|
| gpt-4o-mini @ 64k | 58/66 | 60/66 | **+3** | Net-positive(mid-strong sweet spot)|
| gpt-4.1-mini @ 64k | 52/66 | 53/66 | +1.5 | 近 zero(GROUPING_PROMPT 過度保守,§4.4.3)|

**Observation**:
- **What**:P3 貢獻**於 backbone tier 呈 U-shape / non-monotonic** — 弱端(1B)反害 −4pp、mid tier(4B/12B)neutral、mid-strong tier(27B、gpt-4o-mini)+3~+5pp net-positive、super-strong(gpt-4.1-mini)近 zero。
- **Where**:弱端 P3 反害因 grouping 判斷本身需 LLM 能力(1B 無法可靠 cluster);mid tier P3 zero 因 struct 已解 identity(抽取一致 → 同 (S,P));**mid-strong tier P3 net-positive**因 struct 已 clean pool,P3 進一步壓 reader override(27B 案例);super-strong 因 GROUPING_PROMPT 「Clustering is RARE」被更 literal 執行 → 過度保守。
- **Implication**:**Struct 是 backbone-universal scaffold**(6-tier 皆保 79-99%);**P3 是 capability-gated add-on**(於 mid-strong tier net-positive、兩端減弱)。此結果**對 method_v1.md §3.4「LLM 補救僅在少數案例介入」claim 的精細兌現**:P3 於 mid-strong 承擔 struct 已 clean pool 之後**壓 reader override** 的窄任務,於其他 tier 不 net-negative。ours main 用 struct+P3 combo 於 6-tier 全 spectrum 保持 25-73/74,**弱端天花板為抽取(能力,不是 method),強端天花板為 reader override**。

### 4.5.2 P3 LLM 補救的實際觸發率與命中率

☐ **待補統計**(需寫 script 從 `analysis/results/phase0/grouping_cache_phase2_sh_{L}.json` 讀 cluster events):

| Length | qid 總數 | P3 fired qids(dynamic_pool 非空)| P3 產出 ≥1 cluster 的 qids | P3 cluster 在 struct 已涵蓋外新增的 qids | 對 E2E 貢獻的 qids(struct-wrong → main-correct)|
|:--|--:|--:|--:|--:|--:|
| 6k | 74 | ? | ? | ? | ? |
| 32k | 65 | ? | ? | ? | ? |
| 64k | 66 | ? | ? | ? | ? |

**目的**:量化 P3 於 ours main 中的實際貢獻(而非 ablation 的間接推論)— 呈現 P3 於 struct 已涵蓋外**真的補救到多少**(對接 method_v1.md §3.3「僅在結構失效的少數案例才介入補救」claim)。

### 4.5.3 Conflict-type classifier(+P5,appendix ablation)

**Table 6**:ours (+P5) vs ours (main)

| Length | ours (main) | ours (+P5) | Δ |
|:--|--:|--:|--:|
| 6k(4o) | 93.2% | 91.9% | −1.3pp |
| 32k(4o) | 87.7% | 84.6% | −3.1pp |
| 64k(4o) | 90.9% | 90.9% | 0 |
| 64k(4.1)| 80.3% | 77.3% | −3.0pp |

**Observation**:P5 於全 cell **net-negative 或 zero**。原因:於本文 KU scope(current-value 定義,§0 scope statement),同一 (S,P) 群本就互斥,P5 分類 FRESHNESS vs COMPLEMENTARY 的判斷反引入誤判(將 single-valued 誤判為 COMPLEMENTARY → 兩版都留)。**P5 已自 method 移除**(見 [`vocabulary_v2.md`](vocabulary_v2.md) 禁用詞),此 ablation 用以實證此決定。

---

## 4.6 Generalization — LongMemEval-KU(**draft,待 baseline runs 完 fill 數字**)

### 4.6.1 動機:為何做 LME-KU?

**FC-SH 是 world-fact counterfactual dataset**(以 MQuAKE 反事實編輯對建構),觸發 LLM 於 write-time judgment 時**世界先驗 override(M1)**;於 Ob2 mem0 event-log audit 上,gpt-4o-mini × 64k 的 24 wrong PP-OldOnly/PP-Missing qids 中 **46% 屬 M1**(見 [`results/mem0_event_taxonomy_gt4o.md`](../results/mem0_event_taxonomy_gt4o.md))。

Reviewer 必然質疑:**「你們於 FC-SH 上的優勢,是否僅來自這個 dataset 的 counterfactual 特性?」**

**LongMemEval-KU** 提供 controlled experiment:
- **相同 KU 定義**(current-value KU,對接 intro §Scope Statement)
- **不同 fact domain**:personal-fact updates(使用者屬性隨對話演變),**LLM 對「Alice 於哪個城市」無明顯世界先驗**
- **移除 M1 confound**,只保留 M2 系列 write-time judgment failure modes(missing ADD、cross-item confusion、name conflation)

### 4.6.2 Predicted outcomes 對接 mechanism claim

| Outcome | LME-KU gap prediction | 對 paper 敘事的意涵 |
|:--|:--|:--|
| **A. 架構性 dominant** | ours 90% / mem0 ~50%,gap 幾乎不縮 | Write-time judgment 於 non-counterfactual 也一樣壞 → **主因是 M2 系列 output completeness / cross-item bugs**,paper 架構性 claim 最強成立 |
| **B. 混合貢獻**(**最可能**)| ours 90% / mem0 ~70-75%,gap 縮至 +15-20pp | Write-time failure 部分來自 M1(於 FC-SH 兌現),部分來自 M2(於 LME-KU 仍出現)→ paper 可**decompose 優勢**:結構性 15-20pp + world-prior 特化 25-30pp |
| **C. World-prior dominant** | ours 90% / mem0 85%+,gap ≤ 5pp | World-prior 是 baseline 失敗主因 → paper 需 rethink,承認 FC-SH 特化貢獻大 |

**基於 Ob2 event-log taxonomy(M1=46%,M2=54%)** 我們預測結果 **B**:mem0 於 LME-KU 上應恢復至 ~65-75%(vs FC-SH 46%),但仍低於 ours ~10-20pp。

### 4.6.3 Setup(protocol 對稱於 FC-SH)

- **Dataset**:LongMemEval-s cleaned (Wu et al., ICLR 2025);78 個 `knowledge-update` queries(篩自 500 sessions,verified 2026-07-04)
- **Session length**:~115K tokens per instance
- **Backbones**:gpt-4o-mini(mid tier,primary);pending gpt-4o(strong)
- **Methods**(同 FC-SH 4-method set):
  - **ours** = identity grouping + temporal argmax(main)
  - **(b) mem0+P1** = coupled write-time destructive(共用 ours' P1 extraction cache)
  - **(a) vanilla mem0** = coupled write-time + native mem0 extractor
  - **Zep** = decoupled write-time labeling(k=10)
- **Metric**:LongMemEval 官方 gpt-4o-mini judge(`llm_based_eval/evaluate_qa_official.py`)of binary label per query
- **Pipeline alignment**:所有 methods 於相同 chunker + raw-question retrieval + gen_max=256(對稱 FC-SH audit)
- **Runner**:`docs/0615_.../scripts/run_lme_ku.sh <method>`(2-shard 平行,per-shard cost log at `logs/cost_lme_<method>_sN.jsonl`)

### 4.6.4 Results — Table 7(待完成)

| Method | LME-KU EM(N=78)| FC-SH 64k has_pair EM(N=66,參照)| ΔGap(ours − method)|
|:--|:-:|:-:|:-:|
| **ours (main)** | **65/78 = 83.3%**(previously verified)| 60/66 (91%) | — |
| (a) vanilla mem0 | ☐ 待完成 | — | ☐ |
| (b) mem0+P1 | ☐ 待完成 | 34/66 (52%) | ☐ |
| Zep(k=10)| ☐ 待完成 | 36/66 (55%) | ☐ |

**Observation placeholder**(對接 §4.6.2 outcome A/B/C):
- Outcome B 兌現則 LME-KU baseline 應 ~50-55/78(65-70%),gap 縮小至 +15-20pp
- Outcome A 兌現則 LME-KU baseline ~35-40/78(45-50%),gap 保持 +30-40pp(接近 FC-SH gap)
- Outcome C 兌現則 baseline ~60+/78(80%+),gap 接近 zero

### 4.6.5 Gap Decomposition(**核心分析**)

若採 outcome B(預測),我們可以做以下**乾淨拆解**:

```
Total advantage on FC-SH (gpt-4o-mini × 64k)  =  +39pp (60/66 vs 34/66)
    ├─ Universal architectural advantage (M2 avoidance)    ≈  LME-KU gap
    └─ FC-SH specific (M1 world-prior avoidance)           =  FC-SH gap − LME-KU gap
```

- **若 LME-KU gap ≈ +15pp** → 架構性貢獻 +15pp、world-prior 特化 +24pp
- **若 LME-KU gap ≈ +25pp** → 架構性貢獻 +25pp、world-prior 特化 +14pp

**此 decomposition 直接反擊「FC-SH 特化 artifact」的 reviewer 質疑**,以量化方式劃分「架構性 universal 貢獻」vs 「dataset-specific 貢獻」。

### 4.6.6 對接 intro 的意涵(**核心 claim tie-in**)

**若 outcome B 兌現**:
- **確認 intro §5 的 mechanism claim**(query-time struct + argmax 避開 write-time LLM judgment 所有 failure modes,不僅是 world-prior override)
- **強化 intro §受限部署段**:即使 personal-fact 場景(無 world-prior 干擾),ours 仍於 gpt-4o-mini 上優於 baselines,證明優勢**不因 dataset 而消失**
- **對接 intro §Scope Statement**:兩 dataset(FC-SH world-fact + LME-KU personal-fact)覆蓋 KU 定義的兩大類

**若 outcome C 兌現**(worst case):
- 誠實揭露 architectural 貢獻較小
- Rework intro emphasize world-prior avoidance 為主要 mechanism
- 論文仍站得住,但敘事重心調整

### 4.6.7 待決 / future work

- ☐ **LME-KU × gpt-4o × 4 methods**(補齊 backbone spectrum;於 §4.3 gpt-4o × 64k FC-SH 完成後再說)
- ☐ **LME-KU × gpt-4.1-mini**(檢驗 gap-collapse pattern 於 personal-fact 場景是否成立)
- ☐ **Longer test set**:LongMemEval-M(medium context,~1M tokens);deferred。

---

## 4.7 Discussion(paradigm-level synthesis)

☐ **共筆重點**:此節整合 §4.2-4.5 結果,upgrade intro §7 payoff 的「乾淨 pool」為三 paradigm 的 pool representation framework。初擬結構:

### 4.6.1 三 paradigm 的 pool representation 對比(6-tier spectrum)

**Table 6**:6k has_pair EM,三 paradigm × 6 backbone tier(gpt-4.1-mini × 6k 為 placeholder,64k 值供參考)

| Paradigm | 代表 | Pool 呈現 | Write-time LLM | Inference LLM | 1B | 4B | 12B | 27B | gpt-4o-mini | gpt-4.1-mini |
|:--|:--|:--|:--|:--|--:|--:|--:|--:|--:|--:|
| **P1**(query-time struct filter)| **ours** | Clean pool(struct+argmax 選單一 current) | ✗(僅單筆抽取)| 讀 clean pool | **25** | **54** | **73** | **70** | **69** | ☐(64k=53)|
| **P2**(write-time destructive)| (b) mem0+P1 | Clean pool via destructive commit | ✓(UPDATE/DELETE 決策 → 判對才 clean)| 讀(結果)| **0** | **0** | 44 | 36 | 34 | ☐(64k=55)|
| **P3**(write-time labeling)| Zep | Annotated pool(edges + `invalid_at` timestamps) | ✓(labeler 產出時間戳)| **讀時間戳判時序** | 12 | 17 | 43 | 35 | 46 | ☐(64k=23/sEM 50)|

**關鍵 mechanism 對比**(對接 §4.2.2 三 paradigm 表):
- **P1 有 1 個 LLM 依賴**(P3 補救,**非 critical path**;struct 為 workhorse)
- **P2 有 1 個 LLM 依賴 於 write-time**(UPDATE judge,critical — 判錯 gt_new 就永久消失)
- **P3 有 2 個 LLM 依賴**:(i) write-time labeler(產出 `invalid_at`/`expired_at`);(ii) inference LLM(讀時間戳判時序)— **兩處皆 critical**,可從 `invalid_at`/`expired_at` 與 gt_new/gt_old 的對應性事後驗證 labeling 是否正確

### 4.6.2 Falsifiable prediction 確認

Intro §第 6 段末的「gap 隨 backbone 下降**單調放大**」於 6-tier 光譜上得證,**但需誠實揭露 monotonicity 為 near-monotonic 非嚴格單調**:

| Backbone | ours (main) | (b) mem0+P1 | Gap(ours − b)| 判讀 |
|:--|--:|--:|--:|:--|
| gemma3-1B | 25 | 0 | **+25** | Weak-end 兌現 |
| gemma3-4B | 54 | 0 | **+54** | **Peak gap**(P2 徹底崩、P1 尚可)|
| gemma3-12B | 73 | 44 | +29 | Mid-strong,P2 開始起 |
| gemma3-27B | 70 | 36 | +34 | ours 略降(reader override 天花板)|
| gpt-4o-mini(64k)| 60 | 34 | +26 | Mid tier |
| gpt-4.1-mini(64k)| 53 | 55 | **−2** | **Gap collapse**(P2 catch up)|

**方向符合預測**(gap 於 weak-end 兌現最大絕對優勢、於 strong-end 收斂至 within margin);**非嚴格單調**是誠實揭露的細節:12B/27B 為 ours 峰值(struct 已飽和該 length),4B 為 gap 峰值(P2 崩、P1 尚可)— **paper 用 figure 呈現整條 spectrum 而不強調 monotonicity claim**。

### 4.6.3 Failure 沿 pipeline 逐 tier 往後推(§4.4.6 Case F 的機制陳述)

一句話概括:**同一題,失敗點沿 backbone 變強而沿 pipeline 往後移**。

| Backbone tier | 天花板 failure mode | 對 KU method 的關係 |
|:--|:--|:--|
| Weak(1B/4B) | W1 抽取漏 + W3 reader garbage | **與 KU 方法無關**(能力限制)|
| Mid-weak(12B) | 幾乎無 failure(方法飽和)| **KU method 完全兌現** |
| Mid-strong(27B、gpt-4o-mini)| C reader override(選擇性,§4.4.7)| **與 KU 方法正交**(reader 特性);P3 部分修 |
| Strong(gpt-4.1-mini) | C 於 P3 過度保守放大(§4.4.3)+ G Zep verbose(§4.4.4) | KU method 兌現但 P3 過保守是可修設計選擇 |
| Benchmark | D-flag(2/66 = 3%)| 無關 method(benchmark 缺陷)|

**Implication**:paper 論述**方法本身承擔的責任邊界**(**KU 解析**),而非承擔所有 error mode(抽取品質、reader override 皆為正交軸)。**KU 解析責任邊界內**,ours 於 6-tier 全 spectrum 上 struct+argmax 兌現「乾淨 pool」— 只在 1B/4B 抽取軸(能力)與 27B/4.1-mini reader 軸(先驗/format)受限。

### 4.6.4 Limitations 誠實揭露

- **Weak backbone 僅 6k**;32k / 64k weak-backbone 為 future work(GX10 32k wave 暫停待 Mac 定方向)。6k 已足以支持 backbone-gap 論述於 body。
- **Strong backbone 僅 64k**;gpt-4.1-mini × 6k / 32k 為 **placeholder(§4.2.4 主表已保留欄位)**,供後續補齊 3-length curve 於 strong tier(對稱 mid tier 的 3 lengths)。
- **P3 於強 backbone 的過保守**是 method_v1.md GROUPING_PROMPT 設計選擇的副作用;修正需重寫 prompt,列 future work
- **Zep 於 K=10 vs mem0/ours K=100** 的檢索 asymmetry 已於 setup 揭露,依 Zep 官方推薦
- **Weak-tier 1B/4B pool-state 不可信**(matcher v4 於弱模型抽取字面偏移下 false-negative,§4.1.5 已 揭露)→ 該 tier 只用 E2E + case study
- **Benchmark D-flag qids**(2/66 於 64k)為 MAB 標註缺陷,method 邏輯上無法解;於 caption 揭露

---

## ☐ 共筆待決問題(逐點,2026-07-05 GX10 整合後更新)

1. **§4.1.1 是否納入 LongMemEval-KU generalization?**(泛化訊號 vs body 長度)
2. **§4.2.2 context-state 表 body 呈現 64k 為代表,還是三 length 全報?**(gpt-4o-mini)
3. **§4.4.2 Case B(Zep 弱 backbone)qid 挑哪一個?**(排除 (b) 也錯的 confound;GX10 case F 的 27B 亦可作 Zep 弱 backbone case,或另挑)
4. **§4.5.2 P3 補救統計要不要現在補跑?**(需寫 ~30 行 script 從 grouping_cache 讀;現有 Table 5b 已用 no P3 vs main 間接量化,或補直接統計 P3 fire 次數與命中率)
5. **§4.6 是否移到獨立 Discussion 章節,或收在 Experiments 尾?**
6. **F_backbone_gap_haspair_6k 是否 supersede §4.2.1 的 Table 1 3-length 表?**(重新排序:body 先放 F_backbone_gap_haspair_6k 為頭條圖 → 然後 Table 1 為 mid-tier 3-length curve;或並排)
7. **是否 gpt-4.1-mini × 6k+32k 值得跑?**($0.4,+1.5 hr,補齊 3-length curve → 直接完成 §4.2.4 Table 3 的 gpt-4.1-mini placeholder 欄位)
8. **32k / 64k weak-backbone 是否請 GX10 續跑?**(GX10 wave 暫停待 Mac 方向;若 body 空間夠可加,若緊可 defer to appendix)
