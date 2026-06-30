# 第五章 Experiments — 完整初稿(2026-06-30)

> ⚠️ **所有數字皆為 PROVISIONAL(暫定 / 佔位),不是 paper-final。** 本初稿的數值來自**本機研究演進過程**的既有結果(不同時間、部分為中途設定,跨版本曾變動,如 64k overall 65→94)。它們**只提供敘事與結構骨架**。
> **論文最終每一個數字,必須由穩定機器、在「定版統一 pipeline + 完全相同設定(同 backbone / chunk / top-k / judge 決策 / seed 規則)」下,把全矩陣(所有方法 × 所有長度 × 兩 benchmark)一次性重跑取代**,才算公平、嚴謹、可交叉比較。在那之前請**勿**把本檔數字當 paper-final 引用。執行見 `docs/handoff/EXPERIMENT_RUNLIST.md`(unified re-run)。
>
> **狀態**:experiment 章**整章初稿**,供後續參考 / 修改。結構與敘事為主、數字為佔位;卡在未跑實驗的小節留 scaffold + **[待補]/[待跑]** 標記。
> **設定**:backbone gpt-4o-mini、temperature 0、embedding text-embedding-3-small、chunk 512、top-100;**single deterministic run**(故無 error bar)。FC-SH metric = exact_match(DRQA normalize + ==,**非 LLM judge**);LongMemEval = 官方 LLM judge。
> **數據出處**:`paper_tables_and_figures.md`、`experiment_results.md`、`conflict_type_distribution.md`、`figures_current/`、`analysis/results/phase0/*.json`。§5.4 詳版另見 `experiment_ch_5_4_mechanism_draft.md`。
> **judge 措辭原則**(2026-06-30 釐清):LongMemEval 的 judge 驗證期用 gpt-4o-mini,**是否回官方 gpt-4o 未定(非既定)**;FC-SH 無 judge。系統 backbone 的 model sweep 方向往**更小**(weak-model),非 gpt-4o。

---

## 5.1 實驗設定(Setup)

**Benchmarks.** 我們在兩個 knowledge-update(KU)評測上驗證:
- **MemoryAgentBench FC-SH(ICLR'26)**:general fact 的單跳 fact-consolidation;同一 (S,P) 隨對話被更新,系統須答最新值。四種 conversation-history length(**6k / 32k / 64k / 262k**,跨 40×、最大 18,324 facts),每長度 100 題 = has_pair(衝突題;6k=74、32k=65、64k=66、262k=77)+ no_conflict。
- **LongMemEval KU(ICLR'25)**:personal fact 的 KU;每題 haystack 40 sessions(~115k),**舊值 session 與更新 session 皆在**,系統須答最新。取官方 `longmemeval_s_cleaned.json` 的 `knowledge-update` 子集(**78 題**)。

**Metrics.** FC-SH 用 **exact_match**(DRQA normalize + 字串 ==,`utils/eval_other_utils.py:91-102`),**非 LLM judge** → 確定性、可重現。LongMemEval 用**官方 LLM judge**(`llm_based_eval/evaluate_qa_official.py`,vendor 自 ICLR'25);驗證期 judge=gpt-4o-mini,是否回官方 gpt-4o 未定。主要報 has_pair EM(KU 核心)與 overall EM。

**Models.** backbone gpt-4o-mini(temp 0)、embedding text-embedding-3-small、chunk 512、retrieval top-100。

**Baselines(三層,證明非 trivial、非只在 niche 贏;`experiment_plan.md:23-51`).**
| 層 | 用意 | 對象 |
|---|---|---|
| Same family | 比同類 KU 記憶法 | **mem0**(proactive·coupled,= ours (a) vanilla)、**Zep**(proactive·decoupled,最接近 ours)、LightMem |
| Different family | 證非只在 niche 贏 | **Long-context LLM(LCA,全塞無記憶)**、RAG(BM25/dense)、passive memory(MemGPT/A-Mem) |
| Trivial | 證問題非 trivial | parametric/constant、random-among-retrieved、majority value |

內部 additive ablation 以 (a) native mem0 →(b) 固定 ours 抽取 + mem0 破壞性更新 →(c) ours 隔離兩個貢獻。

**公平規則.** 跨系統各用自身原生抽取 + 原生 inference 模板;**raw-question 檢索 ungated 一致**(剝除 benchmark 的 ~800 字 qa 模板再 embedding,修掉 wrapped-query 檢索 artifact;has_pair 可救率 87%→98%,vanilla 同套用,Zep 本就如此)。fairness audit 唯一 flag = chunk 512 對 Zep 可能不利 →[待補] Zep@4096。

**Reproducibility.** 全鏈從零 clone 已在 Windows(RTX 4050)與 Mac Studio(M2 Ultra)復現定版 6k ours(has_pair 67–69/74、overall 92–94/100,皆在 temp-0 ±2–3 容差內);batch embedding 僅引入 1.22e-4 級非決定性(cosine 0.9999995,排序零影響)。

---

## 5.2 FC-SH 主結果:KU 正確率與 robustness

**Table 1 — FC-SH KU accuracy(has_pair EM % / overall EM %).**
| Method(family) | 6k | 32k | 64k | 262k |
|---|---|---|---|---|
| **Ours**(query-time resolution) | **92 / 92** | **86 / 89** | **91 / 94** | **88 / 91** |
| LCA(no-memory,full-context) | 88 / 88 | 71 / 74 | 55 / 65 | 31 / 42 |
| Zep(proactive·decoupled) | 68 / 76 | 55 / 69 | 67 / 78 | [待補] prohibitive |
| mem0+P1 =(b)(proactive·coupled,destructive) | 46 / 51 | 45 / 61 | 41 / 58 | [待補] M.C.~13hr |
| vanilla mem0 =(a)(stock) | 0 / 16 | 3 / 22 | 3 / 26 | 1 / 17 |

**讀法.** ours 的 has_pair EM **跨 40× context 維持平緩(92/86/91/88%)**;而直接把 full context 餵 LLM 的 LCA 隨長度**單調崩壞(88→71→55→31%)**,Zep 與破壞性 mem0+P1 居中且同樣下滑,native mem0 因 FC 上幾乎抽不到事實而全程 ~0。**ours − LCA 的 gap 隨長度從 +4 拉大到 +57pp**(killer narrative,圖 `F_robust_haspair`、`F_overall`)。這顯示 ours 的 KU 正確率對 history length 具 robustness,而依賴 full-context 或 write-time 更新的方法都隨規模惡化。
> 缺角:mem0+P1 / Zep 的 262k 格因 write-time prohibitive 暫缺(見 §5.7)。

---

## 5.3 LongMemEval 泛化:第二個 benchmark(personal fact)

**主結果(judge=gpt-4o-mini;`experiment_results.md:184-201`).**
| 方法 | KU EM(全 78) | 非-abs(72) | abs(6) |
|---|---|---|---|
| **ours**(保守 + query-time) | **65/78 = 83.3%** | 61/72 = 85% | 4/6 |
| mem0(b) / vanilla / Zep | **[待跑]** baseline full-78 | | |

ours 在 FC-SH(has_pair 86–92%)與 LongMemEval-KU(83.3%)**雙 benchmark 皆強 → KU 主張非 FC-overfit**。baseline full run 尚未完成(smoke 已驗證方法分化:vanilla 0/2 答 stale 舊值),**[待跑]** 是本節硬阻塞。

**conflict-type 跨 benchmark 對比(`conflict_type_distribution.md`)— 解釋「為何同機制能跨 benchmark」.**
| benchmark | FRESHNESS | COMPLEMENTARY | NO_CONFLICT | 意義 |
|---|---:|---:|---:|---|
| FC-SH(general,asymptote) | 85→**98%** | ~1% | ~2% | (S,P)+temporal 即足,結構是 workhorse |
| LongMemEval KU(personal) | 52% | **29%** | 19% | 多值個人事實**需 conflict-type 分類**保留並存值 |

**keep-all 最強論證(Mode B,`experiment_results.md:193-198`).** ours 的 13 個錯題中 ≈7 屬 **Mode B**:題目本身要「歷史/舊值」或「舊 AND 新」雙值(經 oracle evidence 驗證為真設計,非標註錯),被 freshness 解析無條件 collapse 成最新 → 必錯。但**舊值仍在 store(保守寫入沒刪)** → 只有 keep-all 保住了可救的舊版;破壞性 baseline 舊版已刪、再強 resolver 也救不回。修法為 query-aware resolver(偵測 previous/first/both 意圖不 collapse)——**列為未來 case study,暫不實作**。

---

## 5.4 機制分析:為什麼有效(摘要;詳版見 `experiment_ch_5_4_mechanism_draft.md`)

沿確定性因果鏈 **L0(庫狀態)→ L1(檢索)→ L2(解析後)→ EM** 拆解,全程不經 LLM judge:
1. **Write-time 不可逆性(E-L0,`F_bank_recall`)**:ours 記憶庫保有新版 100/98/95/92%,破壞性 mem0+P1 僅 51/49/41%,vanilla 0%。**殺手論證**:破壞性 baseline 的 L0(整庫)== L1(top-100)每長度完全相等 → 損失在 **write-time** 非檢索。
2. **Query-time 解析價值(E-L1→L2,`F_ours_L1L2_pie`)**:L1 both 100/98/95/92% → L2 new_only 70/85/86/79%(破壞性 baseline 結構上做不到,L1 無 both 可解)。
3. **兩道關卡(E-ceiling,`F_em_vs_ceiling`)**:破壞性 EM 緊貼自身 ceiling ~41–51%(瓶頸=ceiling,write-time 封死);ours ceiling 高 87–100% 且 EM 逼近。
4. **最終狀態決定 EM(E4,`F_state_to_em`)**:new_only 287/302=**95%**、both 66%、old_only 2%、neither 6% → 整場遊戲=把 context 收斂成 new_only。
5. **誤差歸因(error-mode)**:三長度「檢索造成答錯」皆 **= 0**;殘餘錯誤 = (S,P) grouping 失敗(`old_not_dropped`)+ answer-LLM,**都不在記憶/檢索層**。winnable has_pair 92/89/92%。

→ KU 的瓶頸已從 write-time 搬到 query-time 下游處理,正是「KU 應是 query-time 問題、非 write-time 不可逆 commitment」的機制證據。

---

## 5.5 Ablation:拆解貢獻

**Additive(FC-SH has_pair %;`F_ablation`、`paper_tables_and_figures.md:23-31`)— [完整可寫].**
| | 6k | 32k | Δ 解讀 |
|---|---|---|---|
| (a) native mem0 | 0 | 3 | 抽取在 FC 失敗 → store 近空 |
| (b) mem0 + P1 抽取(破壞性更新) | 46 | 45 | **+46/+42 = 忠實抽取**(事實進得了 store);破壞性更新仍丟約一半 |
| (c) **ours**(保守 + query-time 解析) | **92** | **86** | **+46/+41 = query-time 解析**把剩下那半救回 |

兩個 delta 各對應一個貢獻;其中 +46/+41pp 純來自「把 KU 延到 query-time」。

**Component-level — [待跑].** structural-only(`ours_struct`:(S,P) group + 確定性 temporal,關掉 LLM grouping + conflict-type)vs full phase2,以驗證「FC-SH 的表現是否主要來自 structural 貢獻」(對照 §5.3 的 FC freshness ~97% → 結構很可能是 workhorse)。腳本已備(`run_fc_sh.sh <L> ours_struct`,重用 ours P1 cache);`analysis/results/` 內**確認尚無結果檔**,為 approved **priority #1**。further:各 component(grouping / conflict-type / temporal)分項貢獻、all-in-one-call vs decomposed pipeline。

---

## 5.6 Weak-Model Regime — [待跑]

驗證 intro 前提:小模型下 ours 是否如預期(**ours 平緩、prior work drop**)。**model sweep 方向 = 比 gpt-4o-mini 更小者優先**(扣 intro narrative),跑 Gemma-3-4B(small)→ mid model;ours / mem0(b) / Zep 對照,看「換難(write-time verdict)為易(query-time resolution)」是否讓弱模型也接近天花板。目前零數據,須有本地算力(RTX 4050 / Mac Studio + vLLM/Ollama)。

---

## 5.7 Cost / Latency 取捨

**Table 3 — Memory Construction(M.C.)總時間(gpt-4o-mini;`experiment_results.md:103-119`).**
| 方法 | 6k | 32k | 64k | 262k |
|---|---|---|---|---|
| **ours** | 476s | 2102s | 4208s | **17041s ≈ 4.7hr**(實測跑完) |
| (a) vanilla(native) | 22s | 124s | 242s | 1058s(⚠ 快=抽≈0條,非真省) |
| (b) mem0+P1(破壞性) | 569s | 4843s(=ours 2.3×) | 8610s(=ours 2.05×) | ≈13hr*(下界,prohibitive) |
| LCA(全塞) | 0 | 0 | 0 | 0(無 M.C.) |
| Zep | send 55s + cloud-proc 慢 | … | ~70–90min* | 數小時*(47min 後 GT 0/15) |

**Q.E.** ours ~27–36s/q(query-time grouping+conflict-type)vs vanilla/mem0(b) ~1.3–2.4s/q、LCA 1–4.7s/q。

**Headline.** 兩個 proactive baseline(mem0 coupled、Zep decoupled)在 **262k write-time 都 prohibitive**(mem0(b) ~13hr、Zep 數小時),而 **ours 262k M.C. 4.7hr 實測跑完** → 「保守寫入」不只更安全(不可逆性),**寫入成本也比破壞性/圖建構更可行**。ours 以較高 Q.E.(~30s/q)換正確性,量化 intro 的「write-time 省成本 ↔ query-time 換正確」取捨(triple 抽取為 M.C. 主成本,lazy-triple 可砍)。

---

## 5.8 Limitations & Future Work

- **Mode B(歷史/雙值題)**:現行 freshness 無條件 collapse → query-aware resolver 未實作(§5.3),列 case study。
- **[待跑] 阻塞清單**:structural-only / component ablation(priority #1)、LongMemEval baselines full、weak-model dose-response、Zep@4096 公平對照、多 seed variance、mem0+P1 / Zep 的 262k 補格、FC-MH 多跳。
- **judge**:目前 gpt-4o-mini;**是否回官方 gpt-4o 為選項、非既定**(FC-SH 無 judge 不受影響)。
- **(S,P) canonicalization**:唯一主要殘餘 lever(predicate 去尾綴 / subject 正規化 / 強化 LLM grouping)。
- 細節 future 見 `conclusion_and_next_step.md`。

---

> **給後續 session**:本初稿 §5.1/5.2/5.4/5.5-additive/5.7 為 committed-data backed,可直接精修;§5.3/5.5-component/5.6 待對應實驗(見 `experiment_chapter_outline_and_gaps.md` 的缺口表)補數字。所有引用的圖在 `figures_current/`、原始數字在 `analysis/results/phase0/` 與本目錄各 `.md`。
