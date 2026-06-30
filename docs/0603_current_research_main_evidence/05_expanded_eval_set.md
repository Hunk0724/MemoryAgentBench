# 擴充評估集(Expanded FC eval set)— 規格與動機

> **動機**:官方 benchmark 每個長度只 query 100 題,但 context 內實際 in-store 的衝突對遠多於此(6k 161 / 32k 837 / 64k 1691 / 262k 7236)。強 backbone 會在 100 題上把記憶方法的衝突解決差異「洗掉」(看起來都接近滿分)。把**每個 in-store 衝突對**都做成可驗證 QA,可在大 N 下真實量測記憶方法的衝突解決能力,也才有足夠鑑別度去比較「**把衝突機制放在記憶系統不同階段**」的設計。

---

## A. 為什麼可行(已驗證)

MQuAKE-CF 每個 `requested_rewrite` 自帶 `question`(single-hop 自然語言問題)、`target_new`(反事實編輯)、`target_true`(世界事實)。每個 context in-store 衝突對 1:1 對應一個 requested_rewrite。

**三項驗證(64k,腳本見 §D)**:
1. **題數**:100% in-store 對都有 `question`(6k 161/161 … 262k 7236/7236,無缺)。
2. **格式一致**:官方 has_pair 問題 = `requested_rewrite.question`,**66/66 逐字相同** → 擴充題與 benchmark 同源同格式。
3. **答案正確**:官方答案 = largest-serial 答案,64/66 一致;唯二不符正是已知 benchmark 答案鍵瑕疵(64k Tom Clancy/Europe;32k London/Rome)。

## B. 答案約定 = LARGEST SERIAL(無瑕疵)

依 benchmark 自宣告規則「newer = 較大序號」。對每個衝突對,答案 = **序號較大那筆 fact 的 object**(直接從 context 算)。
- 與官方答案鍵在所有非瑕疵題一致;
- **自動修正**官方 HF 答案鍵的瑕疵(32k qid8/9、64k qid18/20):這些題官方鍵取了較小序號的世界事實,違反其自宣告規則;largest-serial 取較大序號 → 正確。
- builder 對「官方 100」子集會交叉比對 HF 答案鍵並標 `disagrees_with_official`,**重現上述 4 個瑕疵 → 端到端驗證**。

## C. 輸出 schema(每題)

`analysis/results/expanded/sh_<L>_EXPANDED_gt.json`(list):
```
qa_id            "sh_pair_<old_seq>_<new_seq>"(以 context 序號唯一標識)
question         requested_rewrite.question(與官方同格式)
gt_answer        largest-serial 答案(評分用)
gt_answer_aliases MQuAKE answer_alias(僅取「答案字串實際相符」的 hop,避免把世界事實別名
                  灌到反事實答案上;反事實編輯通常只有自身字串)
gt_seq/gt_fact_text     較大序號 fact
old_answer/old_seq/old_fact_text  較小序號 fact(stale 洩漏偵測用)
conflict_type    "has_pair"
case_id          MQuAKE case
target_new/target_true   原始編輯/世界事實字串
is_official      是否在該長度官方 100 題內(可比官方 vs 擴充)
official_hf_answer / disagrees_with_official  官方子集才有;重現答案鍵瑕疵
```

⚠️ **alias caveat**:反事實答案(target_new)在 MQuAKE 多半無 single-hop 別名 → alias 只含自身字串(保守,不會把 stale 世界事實判對;可能略微低估 recall,不會高估 EM)。

## D. 產生方式(可重現)

```
python docs/0603_current_research_main_evidence/scripts/build_sh_expanded_gt.py \
  --ctx analysis/contexts/factconsolidation_<L>_context.txt \
  --official analysis/results/sh_<L>_RUN_gt.json   # 選用,僅為標記/驗證官方子集 \
  --out analysis/results/expanded/sh_<L>_EXPANDED_gt.json
```

## D2. ★ 優先評估 = vanilla mem0 write-time 沒解決好的衝突對(使用者 2026-06-08 定向)

**動機**:官方 100 題大多落在 resolved,強 backbone 都答對 → 看不出衝突解決弱點。把每個 in-store 對標上 **vanilla mem0 的 write-time 命運**(resolved / H1-miss / H2-refuse / same-chunk,**直接讀既有 ingestion log 算出,不重跑**),挑出**失敗對**當優先題,resolved 當對照。

- 標 fate:`tag_expanded_with_fate.py`(join awt `rows`),產出 `sh_<L>_EXPANDED_tagged.json` + `.priority.json`(僅失敗對)。
- 失敗對數(minimal):6k 18 / 32k 45 / 64k 87(= H1-miss + H2-refuse + same-chunk)。

**QA harness**:`run_expanded_qa.py` 忠實複用 benchmark 的 ingestion / FC query 模板 / 答題 / 計分。
- **忠實度驗證**:對官方 20 題重答,輸出與官方紀錄 **100% 一致**。
- ⚠️ **store 重建必要**:原 run 的 qdrant 在 `/tmp` + `on_disk=False`(mem0 init 會 `rmtree` 清空)→ 沒持久 → 要查新題須重建。harness 補 `on_disk=True` + 持久路徑(`analysis/results/expanded/stores/`),一次 re-ingest 後 `--skip-ingest` 重用(extraction 用 cache 凍結,只重跑 update-LLM;檢索結果與原 run 等價)。

**6k 結果(161 題,按 write-time 命運分組)— 寫時失敗確實傳導到 QA**:
| vanilla mem0 命運 | n | QA EM | stale 洩漏 |
|---|---|---|---|
| ✅ resolved | 143 | **96.5** | 0.7% |
| ❌ same-chunk | 16 | **56.2** | 43.8% |
| ❌ H2-refuse | 1 | **0.0** | 100% |
| ❌ H1-miss | 1 | 100.0 | 0% |

→ resolved 96.5% vs 失敗對(same-chunk 56%、H2-refuse 0%)大幅落差 + 高 stale 洩漏 = **官方 100 題洗掉的衝突解決弱點,在失敗對上現形**。⚠️ 6k 失敗對太少(H1/H2 各 1),統計訊號要看 32k(45)/64k(87)。

## D3. ★ store 重建法(免重 ingest)+ 優先集 QA 結果(2026-06-08)

**store 重建(嚴謹驗證通過)**:原 run 的 qdrant 在 /tmp 被清,但 **vector_results(mem0 實際 add/update/delete 回傳,含 uuid+event+text)有存在 `ingestion_context_0.jsonl`**。replay 這些 → 精確還原最終記憶集,再用 **mem0 同款 embedder(VertexADCEmbedding,text-embedding-004,RETRIEVAL_DOCUMENT/QUERY,cosine top-100)** + 同款答題 → **免重跑 update-LLM**。腳本 `reconstruct_store_qa.py`。
- ⚠️ vector_results 跨 run **append**,須切乾淨單一 run:6k slice `-12`、32k `0:64`(後段是被砍 partial)、64k `36:166`(前 36 是較早 partial)。
- **驗證(6k vs live mem0 QA)**:最終記憶數精確(297,diff 0)、**EM 完全相同(55.6%)**、18 題 17 題逐字一致(唯一差異是「Answer:」前綴,同答案同 EM)→ **重建忠實,可信**。

**final-store 狀態分類器**(`final_store_state.py`):直接用 replay 的最終記憶集判每對是 new_only/old_only/both/neither(QA 真相,非 event-bucket)。

**優先集(event-bucket write-time 失敗對)mem0 QA 結果**:
| | 6k | 32k | 64k |
|---|---|---|---|
| 優先題數(event-bucket 失敗) | 18 | 45 | 87 |
| **mem0 EM(優先集)** | **55.6%** | **82.2%** | **80.5%** |
| ├ final new_only(已自清) | 5 (EM100) | 27 (EM92.6) | 52 (EM100) |
| ├ final both(新舊都在) | 6 (EM83.3) | 13 (EM92.3) | 21 (EM71.4) |
| ├ final old_only(真失敗) | 7 (EM0) | 5 (EM0) | 8 (EM0) |
| └ final neither(都沒了) | 0 | 0 | 6 (EM50) |
| **真未解決(old+both+neither)** | 13 | 18 | 35 |
| **mem0 EM(真未解決)** | **38.5%** | **66.7%** | **51.4%** |

**關鍵發現**:
1. **event-bucket 大幅高估失敗**:22%/60%/60% 的 event-failed 對最終 store 已自清成 new_only(被後續 chunk 把舊版 supersede/A4 污染掉)→ 尺度越大越明顯。
2. **真正 QA 失敗 = old_only(EM 全 0%)**:舊世界事實留在 store、答錯。6k 7 / 32k 5 / 64k 8。
3. **both(新舊都在)= 脆弱成功**:mem0 EM 71–92%(無序號下模型仍偏向挑新),但 **context 不乾淨**——正是 our method「query-time 提供無衝突 context」要補的。
4. **mem0 在真未解決對 EM 僅 38–67%** = our method(query-time 裁決)要證明的 gap。

## D4. ★★ 確立的戰場(final-store 定義,含 A4)+ mem0 baseline(2026-06-08)

**A4 是真失敗模式,但藏在 awt 的 resolved bucket 裡**(64k 全集:71 個 awt-resolved 對最終 store 不乾淨,其中 47 個 neither = winner 也被後續 A4 over-fire 摧毀;抽查 4/4 確認 slot 真的整個消失)。→ **戰場不能用 awt bucket 框,要用「最終 store 狀態」**,自動涵蓋 R1 crowd-out(H1)+ R2 refuse(H2)+ R2 over-fire(A4):
| final store | 機制 | mem0 |
|---|---|---|
| old_only | H2 留舊 / A4 毀 winner | 答舊,EM 0 |
| both | H1 兩版 ADD / H2 沒覆蓋 | 脆弱(靠 prompt nudge) |
| neither | A4 串聯毀新舊 | 無資訊 |
| (new_only) | mem0 自清 | 對照組 |

**戰場 = cross-chunk(排除 same-chunk)+ final-store ∈ {old_only, both, neither}**。腳本 `build_battlefield_gt.py`(+ new_only 50 對照),QA 用重建法 `reconstruct_store_qa.py`,分組 `final_store_state.py`。產物 `analysis/results/expanded/sh_<L>_BATTLEFIELD_gt.json`、`logs/battlefield_{qa,finalstore}_<L>.json`。

**mem0 baseline(reconstruction QA,minimal/temp0/256;同 live 已驗證忠實)**:
| final store | 6k | 32k | 64k |
|---|---|---|---|
| control new_only(no-regression 基準) | 50 / **EM 100** | 50 / **100** | 50 / **100** |
| both(脆弱,prompt 挑新) | 2 / 100 | 22 / 95.5 | 43 / 90.7 |
| **old_only(答舊)** | 2 / **0** | 3 / **0** | 9 / **0** |
| **neither(新舊全毀)** | 2 / **0** | 16 / **12.5** | 47 / **8.5** |
| **戰場真未解決(合計)** | **6 / 33.3** | **41 / 56.1** | **99 / 43.4** |

**對 our method 的意涵**:
- **old_only + neither = mem0 把正確答案 write-time 摧毀(EM ~0–12%)**:6k 4 / 32k 19 / 64k 56 對。our method 非破壞保留 + query-time 時間戳挑新 → 應 ~100%。**最乾淨無歧義的 gap**。
- **both(EM 90–95%)= mem0 靠 benchmark prompt nudge 挑新(脆弱、非確定)**:our method 用明確時間戳確定化、去 prompt 依賴;gemini 上改進小、gpt-4o-mini 上會放大。
- **control new_only EM 100%**:our method 不得讓這些退步(非破壞會把它們變回 both → query 挑新,須驗證仍 100%）。

## D5. ★★★ gpt-4o-mini 跨 backbone 對比 — write-time verdict 是失敗主因(2026-06-08)

**設定**:三層,逐步隔離。extraction 凍結(同 gemini 的 L2 cache,同一批 fact)、embedder 同(text-embedding-004)、檢索同;**唯一變數 = update-verdict + answer LLM**。

| run | extraction | update+answer LLM | FC-SH 6k EM |
|---|---|---|---|
| as-is(benchmark 預設)| mem0 預設 prompt → **抽 0 fact** | gpt-4o-mini | **16%**(extraction 壞掉假象)|
| **clean(隔離)** | **凍結 L2(同 gemini)** | **gpt-4o-mini** | **48%** |
| clean(隔離)| 凍結 L2(同 gemini)| gemini-3.1-flash-lite | **93%** |

→ **同一批 fact、同檢索,只換裁決 LLM:93% → 48%(掉 45pp)**。失敗確定在 **write-time verdict**(+ answer),非 extraction。

**write-time 毀損率(cross-chunk 衝突對 145,final-store ≠ new_only)**:
| | gpt-4o-mini | gemini |
|---|---|---|
| old_only | 27 | 2 |
| **neither(新舊全毀)** | **52** | 2 |
| both | 7 | 2 |
| **毀損合計** | **86 / 145 (59%)** | **6 / 145 (4%)** |
| 最終記憶總數 | 181 | 297 |

→ **頭條統計:write-time verdict 衝突對毀損率 gpt-4o-mini 59% vs gemini 4%**。gpt-4o-mini over-delete(store 縮到 181),52 個衝突把**新舊兩版全刪**。

**論文框架(收斂)**:
- **打的錯誤 = write-time query-agnostic 不可逆 verdict 毀損/錯留 query 所需版本**(old_only/neither/both,機制 H1/H2/A4)。same-chunk 排除(extraction 層)。
- **誠實點**:(a) gpt-4o-mini 毀損 = 推理錯 + 格式錯(hallucinated-id → drop),兩者皆源於「不可逆重生記憶清單」設計,需拆解;(b) 真天花板 = **LCA per backbone**(gemini LCA 99% > mem0 93%,mem0 已損 6pp),非 mem0;(c) our method ingestion 便宜但 store 變大(不 consolidate)→ 需承認 + 可加非破壞 dedup。
- **核心 insight**:write-time verdict 是難題(entity 消歧 + 全 store 衝突偵測 + 無 query)→ 弱 model 崩;query-time resolution 是易題(少數候選 + 明確時序 + 有 query)→ 弱 model 也行。**our method 把難題換易題 → 便宜 model 也接近天花板**。
- **prototype**:非破壞 ingestion(全 ADD + ingestion-order metadata,省 mem0 O(n²) update)+ query-time LLM 語意裁決(時序當訊號,非 rule)。
- **候選 title**:*Resolve When Asked: Query-Time Conflict Resolution for Non-Destructive LLM Memory*。

**待辦**:(1) gpt-4o-mini LCA(per-backbone 天花板);(2) 拆 86 毀損對 = 推理錯 vs 格式錯;(3) OpenAI-embedder 版跑 32k+(Vertex embed 2.8s/call 太慢);(4) prototype。產物:`outputs/gpt-4o-mini-mem0-chunk512-temp0-factaware-l2/`、`logs/sh_6k_gpt4omini_l2/`。

## D6. ★★★ our method 最小 prototype — 強力正面結果(2026-06-09)

**prototype = 非破壞 ingestion(extraction cache 全 455 fact 都留,帶 ingestion-order index)+ query-time resolution(retrieve top-100 → 答題 LLM 用「最大 order=最新」挑)**。零 write-time update LLM。腳本 `prototype_qa.py`。

**FC-SH 6k 官方 100(gpt-4o-mini 答題,對照同 model 的 mem0):**
| 方法 | EM | write-time update LLM |
|---|---|---|
| vanilla mem0(破壞性 verdict) | **48%** | 昂貴 O(n²) + 毀記憶 |
| **our method(非破壞+query-time)** | **96%** | **零** |
| (對照)mem0 gemini | 93% | 昂貴 |
| (對照)LCA gemini = 天花板 | 99% | 全 context |

→ **同 gpt-4o-mini:write-time verdict(難題)48% → query-time resolution(易題)96%(+48pp)**,超過 gemini mem0、逼近 LCA 天花板,且 ingestion 不用 update LLM(更便宜)。

**6k 戰場逐組救回(mem0 毀掉的對 → prototype):**
| mem0 final-store | mem0 EM | prototype EM |
|---|---|---|
| old_only | 0 | **100** |
| neither | 0 | **100** |
| both | 83 | **100** |
| new_only(對照)| 100 | 96(不退步)|

→ **核心 insight 證實**:write-time verdict 是難題(弱 model 崩 48%),query-time resolution 是易題(同弱 model 96%)。non-destructive + 保留時序 + query-time 挑最新 = 最小改動翻盤。

⚠️ **caveat**:6k 單 trial、per-category N 小(old/both/neither 各 2);需 32k/64k 戰場做統計力 + 多 trial。positioning 須界定(vs plain RAG:我們保留時序不破壞;vs LCA:retrieval 低成本可 scale)。次要設計(解耦 LLM 偵測&解決)未做。

**待辦更新**:(1) prototype 上 32k/64k 戰場(統計力);(2) cost 量化(mem0 update tokens vs our 零);(3) gpt-4o-mini LCA per-backbone 天花板;(4) 次要設計;(5) messier-conflict generality。

## E. 現況與待辦

- ✅ **SH 擴充 GT 建好且驗證**:6k 161 / 32k 837 / 64k 1691 / 262k 7236。
- ⬜ **QA 執行**:對既有的 mem0 store(qdrant,免重 ingestion)與 LCA(全 context)逐題回答,算擴充 EM + stale 洩漏率 + 衝突解決率。需 QA harness。
- ⬜ **MH 擴充**:case-level `questions`(3 改寫)+ `new_answer` 可用,但需「多跳鏈在 context 內完整 + 至少一跳為編輯」的可答性檢查(比 SH 複雜),另做。
- ⬜ **用途**:作為比較「衝突機制放在記憶系統不同階段」的鑑別性評估儀。
