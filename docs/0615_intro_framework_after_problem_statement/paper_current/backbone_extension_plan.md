# Backbone Extension Plan — Mac(strong-model)× GX10(weak-model)

> **目的**:paper §Backbone/§Weak-model 的完整 target cell + priority + log requirements + fairness caveats。兩台機器共同執行 baseline,產出**對齊、可 audit、可比較**的 backbone × length × method 結果。
> **rigor SOP**:所有新 run 必經 [`analysis/rigor_audit.py`](../../../../analysis/rigor_audit.py) → 若 fail 立即 [`analysis/rebuild_aggregated_from_perqid.py`](../../../../analysis/rebuild_aggregated_from_perqid.py) → 更新 [`methods_reproduction.md §7`](methods_reproduction.md) canonical registry。
> **matcher**:v4(見 [`matcher_specification.md`](matcher_specification.md))。gemma 因無 per-qid,pool state 判定用 v4 offline 重跑(見 [`gx10_handoff_2026-07-05.md`](gx10_handoff_2026-07-05.md) 任務 A)。

---

## §1 Cost 估算(Mac 端 strong-model)

### 1.1 定價(2026 Jan)

| Model | Input($/1M tok)| Output($/1M tok)|
|:--|--:|--:|
| gpt-4o-mini | $0.15 | $0.60 |
| **gpt-4.1-mini(主)** | ~$0.15 | ~$0.60 |
| gpt-4.1(secondary)| ~$3.00 | ~$12.00(高 20x)|

### 1.2 Per-cell cost 分解(ours full pipeline @ 6k-64k)

| 階段 | Input tokens | Output tokens | Cost @ 4.1-mini |
|:--|--:|--:|--:|
| Phase 0 write-time extraction | ~200k(128 chunks × ~1.5k)| ~13k | ~$0.04 |
| Phase 2 query-time × 100 queries | ~500k | ~25k | ~$0.09 |
| Answer LLM × 100 queries | ~500k(pool 5-7k / query)| ~5k | ~$0.08 |
| **ours cell** | **≈ 1.2M in / 43k out** | | **~$0.21** |
| baseline cell(無 phase 2)| ≈ 700k in / 18k out | | **~$0.10** |

### 1.3 方案 cost 總覽

| 方案 | Cells | 內容 | Cost |
|:--|:--|:--|--:|
| **A. 64k body 主 length,5 method** | 5 | 3 ours(no_p5/struct/p3_only)+(b)+ Zep | **~$1** |
| **B. 3 lengths × 5 methods** | 15 | A × 3 lengths | **~$3-5** |
| **C. B + LCA + vanilla mem0(a)** | 21 | B + 3 length LCA + 3 length (a)| **~$5-8** |
| gpt-4.1(secondary,選跑)| C × 2 | 相同矩陣,強 model | ~$10-16 |

**加保險 buffer(retry / debug)x1.5** → 最壞 **~$25 for gpt-4.1-mini full C**。

### 1.4 Case study 預期:strong-model 救回哪些?

從 [`results/case_studies_64k.md`](results/case_studies_64k.md) finding 1:ours (no_p5) 64k **3 個 PP-New wrong(qid 0, 40, 91)全是 Mode C(LLM world-KO)**。strong backbone 有機會救回,預測 ours 64k 從 60/66 → **63/66(+3)**。

---

## §2 GX10 target cell matrix — 完整 72 cells

| 維度 | 值 | 數 |
|:--|:--|--:|
| Backbone(gemma3 via Ollama)| 1B / 4B / 12B / 27B | 4 |
| Length | 6k / 32k / 64k | 3 |
| Method | ours(struct+argmax)/ ours(p3-only+argmax)/ ours(struct+p3+argmax = no_p5)/ **(a) vanilla mem0** / (b) mem0+ours storage / Zep(k=10)| 6 |
| **Total cells** | 4 × 3 × 6 | **72** |

**⚠ 為何要加 (a) vanilla mem0**(user min set 沒列):
- (a) 於 weak-model 崩壞的 evidence(GX10 已見:1B/4B (b) store 存 5 個「Name is John」)是**寫入 LLM 崩壞** narrative 最強證據
- 沒 (a) vs (b) 對比 → 無法 attribute「extraction prompt 換掉的效果」

---

## §3 GX10 Priority tiers(6k+32k 先 → 64k 收尾)

**你的直覺對** — 若 length 不是核心 claim(memory methods 幾乎 flat across length),先跑 6k+32k 當**階段性觀察**,64k 最後。

### Tier 1(必先跑,證核心 claim)= 12 cells
- 4 backbones × 3 methods × **6k**
- Methods = ours (no_p5)、(b) mem0+P1、Zep
- **證明**:strong→weak 光譜下,ours 是**唯一穩定**的方法

### Tier 2(擴 ablation 深度)= 8 cells
- 4 backbones × 2 more methods × **6k**
- 加 ours(struct)、ours(p3_only)—— **ablation** 拆解 P3/P5 各自貢獻
- 預期:12B/27B 接近 no_p5 → P3 只在 mid+strong backbone add value

### Tier 3(write-time damage 完整 story)= 4 cells
- 4 backbones × (a) vanilla mem0 × **6k**
- 證明 **write LLM 自帶 extractor 於 weak backbone 崩壞**(1B/4B 存 prompt 範例 → bank 0 fact)

### Tier 4(length dimension)= 48 cells
- 4 backbones × 6 methods × **32k**(24 cells)
- 4 backbones × 6 methods × **64k**(24 cells)

**Total**:12 + 8 + 4 + 48 = **72**。**Tier 1-3 = 24 cells 即可支撐 paper body §Weak-model 主 story**;Tier 4 是深度,若時間有限可 defer 到 supplementary。

---

## §4 Per-cell log requirements(**必存**,寫成 CSV)

**檔案**:`docs/0615_.../handoff/gx10_run_log.csv`,一 cell 一行,git track。

| 欄位 | 說明 | 舉例 |
|:--|:--|:--|
| `date` | run 完成日期 | 2026-07-05 |
| `machine` | GX10 / Mac | GX10 |
| `backbone` | model name + version | gemma3-12b |
| `length` | 6k/32k/64k | 6k |
| `method` | canonical label | ours (no_p5) |
| `wall_time_sec` | 完整 run 時長 | 3720 |
| `peak_vram_gb` | Ollama peak(每 backbone × length)| 18.4 |
| `**num_ctx**` | Ollama num_ctx 設定 | 8192 |
| `ollama_model_hash` | `ollama show` 出的 SHA | a1b2c3... |
| `cuda_version` | `nvidia-smi` 顯示的 | 12.4 |
| `gpu_model` | 顯卡型號 | RTX 4090 |
| `n_retry` | 失敗重試次數 | 0 |
| `error_msg` | 若有 error 摘要 | "" |
| `n_bank_tokens_approx` | 寫入端估算 tokens | 5000000 |
| `n_query_tokens_approx` | 查詢端估算 tokens | 800000 |
| `per_qid_saved` | YES/NO/PARTIAL | YES |
| `aggregated_path` | canonical path | outputs/... |
| `has_pair_em` | 主指標 | 44/74 |
| `notes` | 一句話 flag | "num_ctx bug 已修" |

**用途**:
- 決定 remaining budget(還可跑幾 cell)
- 若某 backbone × length OOM → 記入 caveat
- 未來 reproducibility

---

## §5 Fairness caveats(paper 需誠實 disclose)

### 5.1 Zep 的 "backbone" 對 gemma 不完全 apply

Zep = **cloud graph(用 gemini/OpenAI)+ answer LLM(可設 local)**:
- Zep cloud graph 建構仍走 Zep 內部 LLM(**不是 gemma**)
- Zep answer LLM 可改 gemma via Ollama(需改 `methods/zep.py::OpenAIAgent`)

**Paper 敘述**:「Zep weak-model runs = Zep cloud graph(內部 LLM)+ gemma3 answer LLM(via Ollama)」。這不是 apples-to-apples 完整 backbone 對比,但仍是**「memory retrieval 品質給定,answer LLM 換 gemma」**的合理量測。

### 5.2 (a) vanilla mem0 的 write LLM 影響 3 個位置

- extraction LLM = gemma
- UPDATE 判定 LLM = gemma
- answer LLM = gemma

vs (b) mem0+ours storage:
- extraction = ours P1(held fixed,gpt-4o-mini 抽)
- UPDATE 判 = gemma
- answer = gemma

**(a) vs (b) 對比 = 「extraction 換掉」的效果隔離**,這是 write-time damage 的核心 attribution。

### 5.3 LCA(long-context)於 gemma 只能對 6k

gemma3 context window(Ollama 預設):
- 1B / 4B:8k
- 12B:8k(可調 16k)
- 27B:16k / 32k(視版本)

→ **6k 可測 LCA**(feed 6k 對話給 gemma 直接答),**32k/64k 完全不 fit gemma window** → paper 明講「LCA weak-model 僅 6k 對比」。

### 5.4 Ollama num_ctx 必須 verify(GX10 之前踩過的雷)

`preliminary_observations.md` 有記:「p3_only 4b/12b/27b 舊檔 07-01/02 是 pre-fix num_ctx 假象」。

**要求**:每 run 的 `agent_config.num_ctx` 欄位必存於 aggregated file → GX10 grep 一次就能 verify。**Mac 有時候會直接讀 aggregated 判 cell 是否可用,若 num_ctx 沒對就標 broken**。

---

## §6 SOP per run(兩台機器共用)

**每個新 cell 完成後,同步做這 3 步**:

```bash
# 1. Rigor audit
python analysis/rigor_audit.py --length <L>    # 掃全 cells,新的應顯示 OK
# 若某 cell status ≠ ✅ OK:
# 2. 重生 aggregated
python analysis/rebuild_aggregated_from_perqid.py --cell "<method>:<L>"
# 3. 若 rebuild 也修不好(per-qid 也壞)→ 檔 issue,不進 crosstab

# 4. 更新 canonical registry(methods_reproduction.md §7)
#    加入新 (method, length) 的 aggregated + per-qid path
```

**每 tier 結束後**:
- 更新 `paper_current/results/pool_acc_crosstab.md`(Mac)或 gemma 版(GX10)
- 更新 `handoff/experiment_results_shared.md`(共筆)
- 加 wall_time / VRAM / num_ctx 到 `handoff/gx10_run_log.csv`

---

## §7 執行分工(先跑什麼、誰跑)

### Mac(strong-model gpt-4.1-mini)
**現在啟動:方案 A**(64k body 5 methods,~$1,~2-3 hr)
1. `configs/agent_conf/RAG_Agents/gpt-4.1-mini/*.yaml`(從 gpt-4o-mini/ 複製 + 改 `model_name`)
2. Smoke test 1 qid × ours(no_p5)× 64k → 確認 wiring
3. Full run 5 methods × 64k
4. Post-run:rigor_audit + 更新 crosstab + landscape

**A 過關再決定 B/C**。

### GX10(weak-model gemma3)
**優先序**:C(SOP)→ A(matcher v4 對齊 6k 現有)→ B(per-qid save 準備)→ **Tier 1**(12 cells,6k × 3 methods)

**Tier 1 完成後**:發回報 → Mac 這邊審核 → 啟動 Tier 2/3;
**Tier 4(length 深度)**:除非 Tier 1-3 全綠且時間充裕,可 defer 到 supplementary。

---

## §8 Plan A(Mac gpt-4.1-mini × 64k)完成 finding(2026-07-05)

**Plan A 執行結果** —— 詳細 case study trace 於 [`results/case_studies_gpt41mini_64k.md`](results/case_studies_gpt41mini_64k.md);EM 表於 [`style_rules_tables_figures_writing.md §10.3b`](style_rules_tables_figures_writing.md)。

### 8.1 4 個 backbone-shift finding 對敘事的影響

| Finding | Δ EM @ 64k | Mechanism | Paper 意涵 |
| :--- | :---: | :--- | :--- |
| **F1** (b) mem0+P1 recovered | +21pp | 21/26 pool state 修復(4.1-mini UPDATE 判定精準)| **mem0 damage 主要是弱 backbone 產物**;強 backbone catches up |
| **F2** ours main dropped | −7pp(實質 −6pp,扣 1 D-flag)| 6 Mode C shift + 3 phase2 P3 不 remove old + qid 18 D-flag bug | gpt-4.1-mini **more faithful to pool + 特定領域更強 world prior** |
| **F3** p3_only collapse | **−31pp** ⚡ | 24 PP-New→Both;GROUPING_PROMPT 極保守 → strong LLM 讀 prompt 更 careful 不 cluster | **P3 LLM alone backbone-brittle 於光譜兩端**;(S,P) structural 才 universal |
| **F4** Zep verbose | −13 EM / +8 sEM | Type 1(qid 5 format)+ Type 2(qid 2/4 legitimate KU failure,列兩版本)| **報 EM + sEM 雙數字**;flow 對 MAB 是公平的 |

### 8.2 Paper 主敘事 shift

**舊 story**(gpt-4o-mini only):
> ours 全面碾壓 baselines,KU 是 query-time 問題

**新 story**(post gpt-4.1-mini):
> 弱-mid backbone:baselines 於 write-time UPDATE 崩壞;強 backbone 恢復到接近 ours。**ours 於全 backbone spectrum stable 80-91%,不依賴強 backbone**。實務意涵:大多數部署場景(邊緣、成本、隱私)無法用 strong LLM → **ours 的 stability 是 real-world 更關鍵的貢獻**。

### 8.3 Benchmark D-flag bug(必於 paper 明講)

64k 有 **2/66 D-flag qids**(qid 18 Tom Clancy,qid 20 Great Britain / Europe):`gt_seq < old_seq` → argmax(seq) 邏輯上不可能對,且 gt_answer 是**real world knowledge**(reverse counterfactual)。gpt-4o-mini 靠 Mode C 蒙對兩題,gpt-4.1-mini 忠於 pool 反而"錯"1 題(qid 18)。**這佔 ours main −7pp 中的 −1pp**。

### 8.4 尚未跑(Plan B / C 待決)

- **gpt-4.1-mini × 6k, 32k**:目前只有 64k。若跑其他長度 → 額外 ~$0.4 API,~1.5 hr wall time。
- **gpt-4.1(secondary strong model)**:預估 ~$10-16(20x 貴)。
- **case_study qid 91, 86 手動 verify**(4o-mini 主 method 剩 2 個 unverified wrong)。

### 8.5 Zep verbose diagnostic(defer 到 appendix)

**Zep + MAB default template rerun**(削 Zep TEMPLATE,把 edges 當 flat bullet list):
- 若 EM 提升 → verbose 是 Zep TEMPLATE + strong LLM 產物
- 若不變 → legitimate KU failure
- **Cost**:0 API,~5 min;**defer 到 paper appendix**

### 8.6 P3 reasoning debug follow-up

現行 `phase2_query.py::llm_dynamic_grouping` **不存 P3 LLM raw output**(只存 final groupings)。要 debug F3 collapse 細節需:
- 修 `llm_dynamic_grouping` 存 `{groups: [{fact, memory_ids, reasoning}]}` raw JSON
- Rerun p3_only 24 個 PP-New → PP-Both regressed qids
- 分析 reasoning 是否觸發 rule 3(multi-valued)過度 conservative
- **defer to future work,現有 finding 已足以支撐 paper narrative**

---

## §9 更新 log(此檔的 change log)

- **2026-07-05(下午)** — Plan A 執行完成;§8 加 4 findings + narrative shift + D-flag caveat + future work
- **2026-07-05(早上)** — 初版,依 case study finding + GX10 preliminary observation + Mac cost estimate 建立
