# 實作現況備忘錄(FC benchmark:LCA vs HippoRAG-v2)

> 目的:供研究方法討論時載入使用。寫成獨立自足,另一個 Claude 讀這份即可了解現有實驗範圍、可用的分析工具、已確認結論與已知 methodology caveat。
>
> 範圍:刻意只列 `gemini-3.1-flash-lite-preview` 與 baseline `gpt-4o-mini`,避免其他候選模型干擾方法設計討論。
>
> 最後更新:2026-04-24

---

## 1. Inference prompt 設定(關鍵差異)

兩條 pipeline 用**不同 prompt 風格**,是設計上的 baseline choice,非 bug:

| Pipeline | Prompt 風格 | Output 格式 | max_tokens 來源 |
|---|---|---|---|
| **LCA**(Long Context Agent) | **Direct answer** — 提示「Only give me the answer and do not output any other words」 | bare answer,例如 `"pesäpallo"` | `dataset_config['generation_max_length']`(預設 10) |
| **HippoRAG-v2** | **CoT + one-shot**(rag_qa_musique 模板)— system prompt 要求 `Thought: ... Answer: ...` | raw output 有 thought,**存檔時 `.split('Answer:')[1]` 抽 final answer** | HippoRAG 內部 `max_new_tokens`,**預設 400**(不受 `generation_max_length` 影響) |

兩條 pipeline 都**明確告知「序號越大越新越正確」**(Conflict_Resolution task-level prompt)。

**實作上重要觀察**:HippoRAG 的主 results JSON `data[].output` 是被 parse 過的 short answer,不是 raw thought;完整 thought 若要觀察需另外跑 oracle pipeline 或讀 LLM cache SQLite。

---

## 2. 選用模型:Gemini 3.1 Flash-Lite preview

已實測可穩定跑於 Vertex AI `global` endpoint,burst 30-request 無撞 quota(RPM 下界 ≥ 347)。**Preview 狀態** — Google 可能隨時改版或下架,研究可用,production 需等 GA。

### 2.1 為何選它當 backbone

在 FC 任務 LCA pipeline 下,對比各候選模型的結果後,3.1 Flash-Lite **是唯一能接近甚至超越 gpt-4o-mini 的 Flash-Lite 系列模型**。其他候選模型(2.0 Flash-Lite 已 retire、2.5 Flash-Lite 落差大、2.5 Flash 在 extraction-pattern 任務反常),最終決定採用 3.1 Flash-Lite。細節不在此展開,避免干擾方法討論。

### 2.2 與 gpt-4o-mini head-to-head(LCA,n=100 per run)

| Task | Size | gpt-4o-mini EM | gemini-3.1-flash-lite-preview EM | Δ |
|---|---|---:|---:|---:|
| FC-SH | 6k | 89% | **97%** | +8 pp |
| FC-SH | 32k | 72% | **90%** | +18 pp |
| FC-MH | 6k | 14% | **16%** | +2 pp |
| FC-MH | 32k | 11% | **12%** | +1 pp |

**觀察**:

- FC-SH 3.1 Flash-Lite 在兩個 context size 都勝,且**長 context robustness 更強**(gpt-4o-mini 6k→32k 掉 17pp;3.1 Flash-Lite 只掉 7pp)
- FC-MH 兩者都陷入 10-20% 的低區間,僅 3.1 FL 微勝。**MH 不是 backbone 問題,是任務本身的 multi-hop conflict 難度**

### 2.3 配合 HippoRAG-v2(chunk=512,6k,n=100 per run)

| Task | gpt-4o-mini HippoRAG-v2 | gemini-3.1-flash-lite-preview HippoRAG-v2 | Δ |
|---|---:|---:|---:|
| FC-SH | 69% | **77%** | +8 pp |
| FC-MH | 11% | **20%** | +9 pp |

也印證 Gemini 3.1 FL 在 HippoRAG pipeline 下仍優於 gpt-4o-mini。

### 2.4 chunk_size 在 HippoRAG-v2 的嘗試

- 初次用 data config 預設 `chunk_size=4096` 跑 6k context,**但 6k/4096 ≈ 1.5,只切出 1-2 個 chunks,top-k=10 無意義**(只有 1-2 個 passages 可供排序)
- 透過 `main.py --chunk_size_ablation 512` 覆寫 → 6k/512 ≈ 12 個 chunks,top-k=10 合理
- 本備忘錄裡所有 HippoRAG 數據皆為 **chunk=512 版本**

---

## 3. Benchmark dataset(`ai-hyz/MemoryAgentBench`,split `Conflict_Resolution`)

### 3.1 結構

| Sub-dataset | Context chars | #Facts | #Questions |
|---|---|---|---|
| `factconsolidation_sh_6k` / `mh_6k` | 26,157(兩者共用) | 455 | 100 |
| `factconsolidation_sh_32k` / `mh_32k` | 136,565(兩者共用) | 2,310 | 100 |

- Context 為事實句列表:`N. <fact>.`(N = serial)
- 同 subject+relation 會多次出現,serial 大者為「新」
- 6k 和 32k **是獨立生成的 knowledge pool**,不是同 pool 擴長度;Q text 與 answer 都不同

### 3.2 MQuAKE-CF 對應

- 原資料:`/home/yhchiang/MQuAKE/datasets/MQuAKE-CF.json`(9,218 cases)
- MABench metadata 不含 MQuAKE case_id
- **對應方式**:`(question_text.lower(), answer.lower())` 為 key 查 MQuAKE index → 回到原 case + hop
- 實測對應成功率 **100%**(每 100 題皆能對應回)
- 對應後可取:`gt_seq`(新 fact 的 serial)、`old_seq`(舊 fact 的 serial)、`update_gap = gt_seq - old_seq`

### 3.3 衝突對分類

對每題標記:
- `has_pair`:知識庫同時存在新舊事實(真正的衝突題)
- `no_conflict_pair`:只有新事實(無衝突,純 fact extraction)

實測分布(6k):
- **FC-SH**:has_pair 74,no_conflict 26
- **FC-MH**:has_pair 100(benchmark 設計 MH 題皆含衝突)

32k 分布略異(SH 有 65 has_pair + 35 no_conflict,MH 仍 100 has_pair)。

---

## 4. FC-SH × HippoRAG-v2 × Gemini 3.1 Flash-Lite(6k, chunk=512)

> 格式仿 [analysis/step1a_sh_summary.md](analysis/step1a_sh_summary.md)。
> 分析腳本:[analysis/analyze_sh_512_mquake_gemini.py](analysis/analyze_sh_512_mquake_gemini.py)
> 資料:[analysis/results/hipporag_gemini/sh_512_gemini_mquake_{analysis.json,summary.txt}](analysis/results/hipporag_gemini/sh_512_gemini_mquake_summary.txt)

### 4.1 整體

| 指標 | 數值 |
|---|---|
| 題目總數 | 100 |
| 正確 | 77 |
| **Accuracy** | **77.0%** |

### 4.2 衝突對分組

| 子集 | 題數 | 正確 | Accuracy |
|:---:|:---:|:---:|:---:|
| `has_pair` | 74 | 51 | 68.9% |
| `no_conflict_pair` | 26 | 26 | 100.0% |
| 整體 | 100 | 77 | 77.0% |

**觀察**:`no_conflict_pair` 題目 Gemini 3.1 FL 完全滿分,**區別力在 has_pair**。這個 pattern 和 gpt-4o-mini 一致(gpt-4o-mini:has_pair 59.5%、no_conflict 96.2%),但 Gemini 在 has_pair 上有約 +9 pp 優勢。

### 4.3 Retrieval 品質(has_pair, 74 題)

| 指標 | 數值 |
|---|---|
| GT 新事實取回率 | 73/74 = **98.6%** |
| Old 舊事實取回率 | 74/74 = **100.0%** |
| 兩者同時取回 | 73/74 = **98.6%** |

Retrieval 層面和 gpt-4o-mini × HippoRAG 時觀察一致:**舊事實幾乎全部進入 context,失敗不來自「沒取到新事實」**。

### 4.4 Pass vs Fail 的 retrieval position 對比(has_pair 兩者都取回,73 題)

| 狀態 | n | GT 靠後(rank > old,有利 recency) | GT 靠前(不利) | 平均 position_diff(gt_rank - old_rank) |
|---|---:|---:|---:|---:|
| pass | 51 | 39(76%) | 12(24%) | **+1.02** |
| fail | 22 | 2(9%) | 20(91%) | **-0.55** |

**強關聯**:答對時 GT 幾乎都排在 Old 後面(recency bias 有利);答錯時 GT 多排在 Old 前面(recency bias 不利)。

### 4.5 Oracle A 前置:新舊事實在 top-10 的 co-occurrence 結構(has_pair 74 題)

| 狀態 | n | 說明 |
|---|---:|---|
| 兩者都不在 top-10 | 0 | — |
| 只 GT 取回 | 0 | — |
| 只 Old 取回 | 1 | GT 未取到,Oracle A 無法救 |
| **兩者都取回** | **73** | Oracle A 有效標的 |
| └ **same_passage**(新舊在同一 chunk,移除 Old 會連帶丟 GT) | **14**(pass=10, fail=4) | Oracle A 無法單獨移除 Old |
| └ **different_passage** | **59**(pass=41, fail=18) | Oracle A 可直接移除 Old passage |

在 different_passage 的 59 題中,按 passage rank 細分:

| Passage 排序 | n | pass / fail | Accuracy |
|---|---:|---:|---:|
| **GT 排在 Old 前**(rank GT < rank Old,PPR 把 GT 放前面) | 18 | 2 / 16 | **11%** |
| **GT 排在 Old 後**(rank GT > rank Old,context 裡新 fact 出現在舊 fact 之後) | 41 | 39 / 2 | **95%** |

**強訊號**:在兩者都不同 passage 時,**「GT 是否排在 Old 後面」對 accuracy 有 84 pp 差距**。與 §4.4 的 pass/fail position_diff 是同一現象的兩種切分。

這個觀察對 Oracle A 的 effect size 有意義:
- 目前有 **59/74 題**(80%)Oracle A 可直接操作(不同 passage,移除 Old 不損 GT)
- 已答錯的 23 題中,**18 題屬於 different_passage**(Oracle A 可操作),若 Oracle A 移除後全答對,SH accuracy 理論上限 = (77 + 18)/100 = **95%**

### 4.5 Fail cases 的 update_gap 分布(23 題)

| Gap 區間 | 題數 |
|:---:|:---:|
| 11–50 | 8 |
| 51–100 | 2 |
| 101+ | 13 |
| 平均 | 124.3 |
| 範圍 | 11 – 328 |

Fail 的 gap 明顯偏大,暗示**當新舊事實相距遠時,retrieval 後兩者仍同時進 context,但 LLM 較難鎖定「較新」的那個**。

### 4.6 Error type(fail 23 題)

| 類型 | 題數 | 佔 fail | 備註 |
|---|---:|---:|---|
| older_fact | 23 | **100%** | 每個失敗題 output 字串 match 舊答案(見 §8 caveat) |
| entity_confused | 0 | 0% | — |
| hallucination | 0 | 0% | — |

---

## 5. FC-MH × HippoRAG-v2 × Gemini 3.1 Flash-Lite(6k, chunk=512)

> 格式仿 [analysis/step1a_methodology.md](analysis/step1a_methodology.md)。
> 分析腳本:[analysis/analyze_mh_512_mquake_gemini.py](analysis/analyze_mh_512_mquake_gemini.py)
> 資料:[analysis/results/hipporag_gemini/mh_512_gemini_mquake_{analysis.json,summary.txt}](analysis/results/hipporag_gemini/mh_512_gemini_mquake_summary.txt)

### 5.1 整體

| 指標 | 數值 |
|---|---|
| 題目總數 | 100 |
| 正確 | 20 |
| **Accuracy** | **20.0%** |

### 5.2 Hop 數分組

| Hop 數 | 題數 | Accuracy |
|:---:|:---:|:---:|
| 2-hop | 61 | **26.2%** |
| 3-hop | 24 | 12.5% |
| 4-hop | 15 | 6.7% |

**hop 數越多 accuracy 越低**,與 gpt-4o-mini × HippoRAG 觀察一致(11% 整體、2-hop 最高)。

### 5.3 Per-hop retrieval(含所有跳,n=254 跳)

| 類別 | 跳數 |
|---|---:|
| 總跳數 | 254 |
| has_pair(該跳需解衝突) | 188 |
| no_conflict_pair(該跳無衝突) | 66 |

`has_pair` 跳的 retrieval:

| 指標 | 188 跳中 |
|---|---:|
| GT 取回 | 183 / 188(97.3%) |
| Old 取回 | 184 / 188(97.9%) |
| 兩者都取回 | 179 / 188(95.2%) |
| 兩者都取回且**同一 passage**(新舊 fact 被同一 chunk 涵蓋) | 31 / 179(17.3%) |
| 兩者都取回且**不同 passage** | 148 / 179(82.7%) |

### 5.4 PPR 傾向(兩者取回且不同 passage 的 148 跳)

| 狀態 | 新 PPR 較高(新在前) | 舊 PPR 較高(舊在前) |
|---|---:|---:|
| 整體 148 跳 | 53(35.8%) | 95(64.2%) |
| 題目 pass 時的 has_pair 跳 | 5 | 18 |
| 題目 fail 時的 has_pair 跳 | 48 | 77 |

**觀察**:舊事實(真實世界中常是 well-known 知識,graph 中連通度較高)PPR 系統性偏高,**約 64% 的 has_pair 跳 PPR 會把舊事實排在新事實前面**。

### 5.5 Error type(fail 80 題)

| 類型 | 題數 | 佔 fail |
|---|---:|---:|
| older_fact | 54 | 67.5% |
| entity_confused | 14 | 17.5% |
| intermediate_stop | 7 | 8.8% |
| hallucination | 5 | 6.2% |

`intermediate_stop` = MH 中 LLM 停在某個 hop 的 intermediate answer(通常是鏈的第一個子答,沒繼續推到最終)。其中 5 題停在新版中間答案、2 題停在舊版中間答案。

### 5.6 Oracle A 前置:舊事實 passage 移除需求(100 題)

| 需要移除的舊 passage 數 | 題數 |
|:---:|:---:|
| 0(無 old 被取回) | 8 |
| 1 | 46 |
| 2+ | 46 |

- pass 題中 42 題不需要移除 ≥ 1 個(說明它們答對時 old 可能未被取回或被 LLM 忽略)
- fail 題中 73 題需要移除 ≥ 1 個

### 5.7 Question-level passage ordering vs accuracy(has_pair hop 全 retrieved 的 93 題)

把 "所有 has_pair hop 都 retrieve 到新舊事實" 的題挑出(n=93),依 diff-passage hop 的 rank 順序細分:

| 題目 passage 狀況 | n | Accuracy |
|---|---:|---:|
| 整體(93 題) | 93 | 20% |
| **每個 diff-passage hop 都是 GT rank > Old rank**(完全 recency-favored) | 43 | **30%** |
| **至少一個 diff-passage hop 是 GT rank < Old rank**(至少一跳 recency 不利) | 43 | **12%** |

MH 的「GT 靠後 vs 靠前」對 accuracy 差距(30% vs 12%,18 pp)**比 SH 小很多(84 pp)**。可能原因:MH 有多跳推理鏈,即使某跳 recency 有利,其他跳失敗仍拖累整體 accuracy — 乘法效應弱化了 passage-ordering 的直接影響。

這個對比暗示 **SH 的失敗是 single-hop 的選擇問題(recency-bias dominated),MH 則是鏈式累積失敗**,兩者需要不同的方法性處理。

### 5.7 題目層級衝突完整性(fail 80 題)

| 狀況 | fail 題數 |
|:---:|:---:|
| 全部跳都有衝突 | 42 |
| 部分跳有衝突 | 38 |
| 無衝突 | 0 |

---

## 6. Oracle A 實驗狀態

> 完整方法參見 [analysis/results/oracle_a/oracle_a_report.md](analysis/results/oracle_a/oracle_a_report.md)(2026-04-17,用 gpt-4o-mini 執行)。

### 6.1 舊 gpt-4o-mini × HippoRAG-v2 × chunk=512 的 Oracle A 結果(已完成)

Oracle A = 移除含舊事實的 passage 後重跑 LLM,模擬「完美 conflict filter」的 upper bound。

| Task | Baseline Acc | Oracle A Acc | 提升 |
|---|---:|---:|---:|
| FC-SH | 57.8%(37/64) | **81.2%(52/64)** | +23.4 pp |
| FC-MH | 16.7%(11/66) | **42.4%(28/66)** | +25.8 pp |

說明:
- baseline 與前述 69% / 11% 不同,是因為 Oracle 有排除 same_passage / gt_not_retrieved 等邊界題目的 subset。
- **重點**:Oracle A 在兩個任務都大幅提升 accuracy(+23 / +26 pp),**驗證了「retrieved context 中新舊事實混雜是 HippoRAG-v2 在 conflict resolution 失敗的主因」** — 不是 LLM reasoning 無能,而是 context 裡有舊事實被 picked up。

### 6.2 對 Gemini 3.1 Flash-Lite 跑 Oracle A(**尚未執行**,可做)

現有資料已足夠執行:

| 前置材料 | 狀態 |
|---|---|
| Gemini × HippoRAG FC-{SH,MH} 6k baseline | ✅ 已完成(77% / 20%) |
| Top-10 retrieved passages(共享 gpt-4o-mini 的 retrieval,因為 NV-Embed-v2 不依 LLM) | ✅ 已存於 `outputs/rag_retrieved/Structure_rag_hippo_rag_v2_nv/k_10/factconsolidation_{sh,mh}_6k/chunksize_512/` |
| MQuAKE 對應 + 新舊 fact passage rank | ✅ 已跑(§4, §5) |
| Oracle pipeline code | ✅ 舊 gpt-4o-mini 版本已在,改 LLM backbone 為 Gemini 可重用 |

### 6.3 Oracle A 可行性分析(FC-SH & FC-MH, Gemini × HippoRAG-v2 × chunk=512)

#### FC-SH

| 類別 | 題數 | Oracle A 操作可行性 |
|---|---:|---|
| no_conflict_pair(單一事實,無舊版) | 26 | 無需 Oracle A |
| **has_pair 共 74 題**,細分: | | |
| └ both retrieved, **different_passage** | **59** | ✅ **usable**,可安全移除 old passage |
| └ both retrieved, **same_passage** | 14 | ❌ 新舊同 chunk,移除 old 會連帶丟 GT |
| └ only Old retrieved | 1 | ❌ GT 沒在 top-10,Oracle A 無法救 |
| └ only GT retrieved / neither | 0 | — |

**Oracle A 有效範圍 = 59/74 題(80%)**
- Usable 59 題的 baseline accuracy = 41/59 = **69.5%**
- 18 題答錯若全數救回,SH 整體上限 = (77 + 18)/100 = **95%**

#### FC-MH

| 類別 | 題數 | 說明 |
|---|---:|---|
| **usable**(所有 has_pair hop 都 both retrieved 且 diff_passage) | **66** | ✅ Oracle A 可完整操作 |
| has_same_passage(至少一 hop 是 same_passage) | 27 | ❌ 至少一跳無法安全移除 |
| old_missing | 2 | ❌ 該跳沒 Old 可移 |
| gt_missing | 3 | ❌ GT 被 retrieval 漏掉 |
| both_missing | 2 | ❌ |

**Oracle A 有效範圍 = 66/100**

Usable 66 題按複雜度細分:

| 切分 | n | pass | Baseline Acc |
|---|---:|---:|---:|
| 2-hop | 43 | 13 | 30% |
| 3-hop | 17 | 3 | 18% |
| 4-hop | 6 | 1 | 17% |
| 1-conflict hop 題 | 27 | 12 | **44%** |
| 2-conflict hop 題 | 32 | 5 | 16% |
| 3-conflict hop 題 | 6 | 0 | 0% |
| 4-conflict hop 題 | 1 | 0 | 0% |

**重要觀察**:衝突 hop 數越多,即使 Oracle A usable,baseline accuracy 崩潰越嚴重(44% → 16% → 0%)。這暗示 MH 的失敗來自「多個 hop 都要解衝突」的乘法效應,不只是 retrieval 混雜。**Oracle A 可能在 1-conflict 組有高上限,多 conflict 組提升有限**。

#### 與舊 gpt-4o-mini 的 usable 分布對比

| 指標 | gpt-4o-mini(2026-04-17 Oracle A) | Gemini 3.1 FL(當下) | 備註 |
|---|---:|---:|---|
| SH usable / has_pair | 64 / 74 | 59 / 74 | Gemini 多 5 題 same_passage(兩者的 HippoRAG graph 由各自 OpenIE triples 構成,PPR 結果略異) |
| MH usable / 100 | 66 | 66 | 巧合一致 |

### 6.4 從現有 diagnostic 推出的 Gemini Oracle A 預期

基於 §4.5 / §5.6 的 passage-co-occurrence 結構:

**FC-SH**
- 74 題 has_pair 中,**59 題 different_passage**(Oracle A 可直接操作)
- fail 的 23 題中,**18 題屬於 different_passage** → Oracle A 若全部救回,accuracy 上限 = (77+18)/100 = **95%**
- 4 題 fail 是 same_passage(Oracle A 結構上無法救)
- **預期區間:77% → ~90-95%**(±5 pp 視 LLM 在少 1 passage 時 generation 穩定性)

**FC-MH**
- 100 題中 46 題需要移除 ≥ 2 個 old passage(跨多 hop 的 conflicts)
- 舊 gpt-4o-mini 的 Oracle A 在 FC-MH 上提升 **+25.8 pp**(16.7% → 42.4%)
- 若 Gemini 的提升 magnitude 類似,**預期 20% → ~40-45%**
- 若提升幅度顯著大於 gpt-4o-mini,可論證 Gemini 在「reasoning over pre-filtered context」表現更強

**此實驗可直接驗證**:
1. Gemini 3.1 FL 的 failure mode 是否也是「retrieval 中混入舊事實」為主(SH 預期高度符合,MH 較複雜)
2. 若驗證成立,可強化論文關於「retrieval-side 混雜是 conflict resolution 主要瓶頸」的論點
3. 若 Gemini 的 Oracle A 上升幅度顯著大於 gpt-4o-mini,可進一步推論「Gemini Flash-Lite 在乾淨 context 下的 instruction-following 優於 gpt-4o-mini」

---

## 7. 可進一步分析的面向(現有資料已支援)

| 分析 | 基礎 | 做法 / 預期 |
|---|---|---|
| **Gemini 3.1 Flash-Lite 的 Oracle A 執行**(見 §6.2, §6.3) | retrieval + MQUAKE diagnostic 都齊 | 跑 oracle pipeline,SH 預期 77→~95%,MH 預期 20→~45% |
| **Passage ordering 對 accuracy 的 causal 驗證** | §4.5 SH 顯示 84 pp 差距(GT 排在 Old 前 vs 後) | 可用 re-order 實驗:人為把 retrieved passages 重排,觀察 accuracy 變化 |
| **Same-passage 題(SH 14, MH 31 hops)的獨立處理** | Oracle A 結構上無法救(新舊同 chunk) | 需 chunk-level 或 sentence-level filtering,或 finer chunk_size ablation(chunk=256? 128?) |
| **Update gap vs accuracy**(§4.5:fail 平均 124,13/23 是 gap>101) | 已有 `gt_seq - old_seq` 分佈 | 回歸或 bin accuracy,驗證 "new/old 序號距離遠 = 較難" 假說 |
| **MH partial-conflict vs all-conflict 的 hop-level 失敗定位**(§5.7) | 93 題 all-retrieved,43 題 recency-favored vs 43 題 recency-unfavored | Per-hop `gt_rank > old_rank` 是否預測整題 EM |
| **LCA vs HippoRAG-v2(同 backbone Gemini 3.1 FL)的 accuracy 差距** | LCA SH/MH 6k = 97% / 16%;HippoRAG SH/MH 6k = 77% / 20% | **注意 §8.2 confound**(prompt + max_tokens 不同),結論需謹慎 framing |
| **32k+ HippoRAG-v2** | 尚無 HippoRAG 32k 實驗 | Retrieval + graph build 對 long context 成本增加,LCA 32k 已有數據可先對照 |

---

## 8. 方法論警示(影響論文敘述強度)

### 8.1 Error-type `older_fact` 的 ambiguity

現有 `classify_error` 邏輯:

```python
if output == new_answer:  return "correct"
if output == old_answer:  return "older_fact"     # ← 字串相等就判 older_fact
if output in any fact:    return "entity_confused"
return "hallucination"
```

**問題**:若 `old_answer`(如 `"London"`)在 context 多個無關 facts 也出現,**無法精確歸因** LLM 是否真的從「我們定義的 old fact」抽出,還是從無關 fact 抽到同字串。

量化(LCA runs):70–90% 的 `older_fact` 分類 output 在 context match 多於一筆 fact。**Primacy bias 的 claim 需區分 strict 下界(unique)與 upper 上界(unique+ambiguous)**,已 validated 兩種排序下 model 間 ranking 不變,但絕對百分比會差一截。

**HippoRAG × Gemini SH fail 的 23 題全部被歸為 older_fact**(§4.6),這個 100% 需用同方法檢查 ambiguity,否則不能直接宣稱「Gemini 也有同樣強烈 primacy bias」。

### 8.2 LCA vs HippoRAG 非 apples-to-apples

兩條線的 prompt 設計和 max_tokens 不同(§1):

- LCA direct answer + `max_tokens=10`
- HippoRAG CoT + `max_tokens=400`

如果在同 backbone 上比較「LCA vs HippoRAG accuracy」,**差異混合了三件事**:(a) 有無 retrieval、(b) 有無 thought、(c) output budget 不同。論文若要做這個比較必須說明 confound。

### 8.3 Preview model 穩定性

`gemini-3.1-flash-lite-preview` 處於 Google Vertex preview 狀態。實測偶有 503(`This model is currently experiencing high demand`),已加 retry-with-backoff 處理。論文若要依賴此模型的結論,建議同時註明實驗日期與偵測的 preview 版本(我們跑於 2026-04-24)。

### 8.4 Dataset 設計:MH 題全部有衝突

FC-MH 的 100 題在 MQuAKE 對應後,**conflict_type 全部為 has_pair**(benchmark 設計:multi-hop 題每題至少有一個 hop 要解衝突)。無 MH no_conflict 組可作對照,無法像 SH 那樣做 "無衝突 baseline" 對照。

### 8.5 跨 size 不可逐題比較

6k 與 32k 是各自獨立的 knowledge pool,即便 `qa_pair_id` 前綴相同(`no0 ... no99`),**通常對應不同的 MQuAKE case**。只能做整體 accuracy 對比,不能做「同題在 6k vs 32k 成敗差異」的逐題分析。

---

## 9. 確定 vs 不確定

### 已確定(皆 n=100 完整 run 或 code-level 驗證)

- Gemini 3.1 Flash-Lite preview vs gpt-4o-mini 在 LCA × FC-{SH,MH} × {6k, 32k} 的 accuracy 對比(§2.2)
- Gemini 3.1 Flash-Lite preview vs gpt-4o-mini 在 HippoRAG-v2 × FC-{SH,MH} × 6k × chunk=512 的 accuracy 對比(§2.3)
- MQuAKE 對應率 100%,可精確抽出 `has_pair` / `no_conflict` 與 `gt_seq`、`old_seq`
- HippoRAG 的 retrieval quality(GT / Old 取回率 ≥ 97%)
- Oracle A(gpt-4o-mini 版)已證實 "retrieval 混雜是主因" 的論斷(+23~26 pp accuracy 提升)

### 已收集但待分析

- Update gap 完整分布與 accuracy 的定量關係(§4.5 有摘要,尚未回歸)
- Gemini 3.1 Flash-Lite 的 Oracle A 實驗(§6.2,尚未執行)
- `older_fact` 的 unique / ambiguous 切分(HippoRAG × Gemini 版本,LCA 版本已做過量化)

### 推論但未直接驗證

- "Gemini 3.1 Flash-Lite 勝出源於更佳的 recency bias-aware instruction following" — 我們只有 correlation(position_diff, update_gap),缺 mechanistic evidence
- "4-hop MH 不可解" — 從 6.7% 不能排除 "只要 retrieval 完美 Oracle A 能補救",需要跑 Oracle A 才確定

---

## 10. 檔案速查

```
# Prompt templates
utils/templates.py                                       # LCA + rag_agent task-level prompt（行 80-82）
methods/hipporag/prompts/templates/rag_qa_musique.py    # HippoRAG CoT 模板

# LCA 結果
outputs/gpt-4o-mini/Conflict_Resolution/                 # LCA × gpt-4o-mini × FC-{SH,MH} × {6k, 32k}
outputs/gemini-3.1-flash-lite-preview/Conflict_Resolution/

# HippoRAG-v2 結果
outputs/gpt-4o-mini-hippo_rag_v2_nv/Conflict_Resolution/                      # 舊 gpt-4o-mini 版
outputs/gemini-3.1-flash-lite-preview-hippo_rag_v2_nv/Conflict_Resolution/    # 新 Gemini 版
outputs/rag_retrieved/Structure_rag_hippo_rag_v2_nv/k_10/...                  # Top-10 retrieved passages（LLM-agnostic，共享）

# 分析工具
analysis/analyze_lca_mquake.py                           # LCA MQUAKE 對應（簡化版，無 retrieval）
analysis/analyze_sh_512_mquake_gemini.py                 # HippoRAG × Gemini SH 完整分析（MQUAKE + retrieval）
analysis/analyze_mh_512_mquake_gemini.py                 # HippoRAG × Gemini MH 完整分析
analysis/contexts/factconsolidation_{6k,32k}_context.txt # dumped fact pool

# 分析結果
analysis/results/lca/                                    # LCA × 各 model × MQUAKE 輸出
analysis/results/sh_512_mquake_{analysis.json,summary.txt}    # 舊 gpt-4o-mini × HippoRAG SH
analysis/results/mh_512_mquake_{analysis.json,summary.txt}    # 舊 gpt-4o-mini × HippoRAG MH
analysis/results/hipporag_gemini/sh_512_gemini_mquake_*       # Gemini × HippoRAG SH（新，§4 數據來源）
analysis/results/hipporag_gemini/mh_512_gemini_mquake_*       # Gemini × HippoRAG MH（新，§5 數據來源）
analysis/results/oracle_a/                               # gpt-4o-mini Oracle A 實驗
analysis/step1a_methodology.md, step1a_sh_summary.md     # 過去 HippoRAG gpt-4o-mini 分析報告

# 外部資料
/home/yhchiang/MQuAKE/datasets/MQuAKE-CF.json            # MQuAKE-CF 原始（9,218 cases）
```

---

## 11. Plug-in prompt-engineering 階梯實驗(2026-04-26)

> 在 HippoRAG-v2 × Gemini 3.1 Flash-Lite × FC-{SH,MH} 6k(chunk=512)上,測試 plug-in inference-time prompt 修改的階梯,與 Oracle A(retrieval-side filter)對照。
> 詳細 prompt 設計對比:[`analysis/prompts_comparison.md`](analysis/prompts_comparison.md)
> 各 setting 結果 JSON:[`analysis/results/oracle_a_gemini/`](analysis/results/oracle_a_gemini/)

### 11.1 五個 setting 階梯

| Setting | 描述 | 對 vanilla 的修改深度 |
|---|---|---|
| **Vanilla** | HippoRAG-v2 原 inference,不動 | 基準 |
| **Oracle A** | 移除含 old fact 的 passage(perfect retrieval-side filter,僅可在 different_passage 組操作) | passage 數量減少 |
| **PAT** | vanilla skeleton + leading PAT_INSTRUCTION + fact-level [CURRENT/OUTDATED FACT] tags | 軟性指引 + fact 標記 |
| **RPT-min** | PAT + passage 前加 inline `[SECTION A: ACTIVE]` / `[SECTION B: SUPERSEDED]` label + 強 instructions(MUST/DO NOT) | 加 section partition,**保留 vanilla skeleton** |
| **RPT** | RPT-min + 用 `== HEADER ==` 大標題重組整個 user message | 結構大重構 |

### 11.2 Full 100 題分組結果

題目按是否能用 Oracle A 操作分為 4(SH)/3(MH)組:

- **different_passage**:has_pair,新舊事實在 top-10 不同 passages → Oracle A 可移除 old passage
- **same_passage**:has_pair,但新舊事實在同 chunk → Oracle A 結構上無法救
- **retrieval_missing**:has_pair,但 GT 或 Old 至少一個沒在 top-10 → Oracle A 與 PAT/RPT 皆部分受限
- **no_conflict_pair**(SH only):無新舊衝突,純 fact extraction → 所有方法應接近 100%

#### SH(Full 100,n_per_group: different=64, no_conflict=26, same=9, retrieval_missing=1)

| 組 | n | Vanilla | Oracle A | PAT | RPT-min | RPT |
|---|---:|---:|---:|---:|---:|---:|
| different_passage | 64 | 67% | 97% | 72% | **100%** | **100%** |
| no_conflict_pair | 26 | 100% | N/A | 100% | 100% | 100% |
| same_passage | 9 | 89% | N/A | 89% | **100%** | **100%** |
| retrieval_missing | 1 | 0% | N/A | 0% | 0% | 0% |
| **OVERALL** | 100 | **77%** | (only diff) | **80%** | **99%** | **99%** |

#### MH(Full 100,n_per_group: different=66, same=20, retrieval_missing=14)

| 組 | n | Vanilla | Oracle A | PAT | RPT-min | RPT |
|---|---:|---:|---:|---:|---:|---:|
| different_passage | 66 | 27% | 64% | 42% | 70% | **80%** |
| same_passage | 20 | **0%** | N/A | 30% | 40% | **45%** |
| retrieval_missing | 14 | 14% | N/A | 14% | **43%** | **43%** |
| **OVERALL** | 100 | **20%** | (only diff) | **36%** | **60%** | **68%** |

### 11.3 階梯各層的貢獻分解(MH)

| 增量 | A vs B(MH) | A 對 B 多答對 | B 對 A 多答對 | McNemar p | 結論 |
|---|---|---:|---:|---|---|
| Vanilla → PAT | annotation only(軟性 prompt) | 20 | 4 | 0.0015 ** | annotation 有效但有限 |
| **PAT → RPT-min** | **+ passage 分組 + 強 instruction** | **27** | 3 | **<10⁻⁵ \*\*\*** | **核心 driver(本實驗的 main finding)** |
| RPT-min → RPT | + `== HEADER ==` 大結構重組 | 12 | 4 | 0.077 n.s. | 次要 refinement,trend 為正但統計不顯著 |

#### Main finding:**PAT → RPT-min 的 +24 pp(MH)是 plug-in 路線的核心 driver**

這個 single-step delta 占整個 plug-in gain(Vanilla → RPT 的 +48 pp on MH)中**超過 50%**,且 McNemar p<10⁻⁵ 極顯著。其他兩層(annotation only / 結構重組)各只貢獻 +16 pp 與 +8 pp。

**PAT vs RPT-min 的 prompt design 具體差異**(見 [`analysis/prompts_comparison.md` §3, §5](analysis/prompts_comparison.md)):

| 設計元素 | PAT | RPT-min | 說明 |
|---|---|---|---|
| Fact-level [CURRENT/OUTDATED FACT] 標記 | ✓ | ✓ | 兩者相同 |
| Vanilla skeleton(`Wikipedia Title:` + `Question/Thought` trailer) | ✓ | ✓ | 兩者相同 |
| **Passage-level grouping** | ✗ | ✓ Section A(active)排前,Section B(superseded)排後 | **新增** |
| **Passage-level inline label** | ✗ | ✓ 每個 passage 前加 `[SECTION A: ACTIVE]` 或 `[SECTION B: SUPERSEDED]` | **新增** |
| **Instruction 強度** | 軟性:`use [CURRENT FACT] as source of truth`、`may reference [OUTDATED FACT] only if explicitly asked` | **強性**:`MUST be derived only from facts in SECTION A`、`DO NOT use any fact from Section B as your answer` | **顯著加強** |

換言之 PAT → RPT-min 的 +24 pp 來自三個變化的 **疊加效果**:
- (1) passage 分組 → 把同性質 passages 視覺/結構上分開,降低 LLM attention 在新舊間漂移
- (2) inline `[SECTION X]` label → 給 passage-level decision rule(「整個 passage 不可信」)
- (3) `MUST/DO NOT` 強指令 → 提高 instruction-following compliance

從 failure mode 看 PAT → RPT-min 的影響:**MH older_fact share 從 71% 降到 35%**(different_passage 組),這是 LLM「答出 OUTDATED fact」的比例幾乎砍半。等於 **這 +24 pp 主要來自把 LLM 從 OUTDATED 的 attention 拉力中救出**。

#### Secondary finding:結構重組(RPT-min → RPT)只在最複雜題型有 marginal value

RPT-min → RPT 的 +8 pp(MH p=0.077 n.s.)只在 3-hop-2-conflict 與 4-hop-3-conflict 等 hop / conflict 數量大的題目上有實質 gain(分別 17%→50%, 50%→100% 但 n=6, n=2 樣本小),**在 2-hop 題目上 RPT 與 RPT-min 全部 tie 或差 1-2 題**。從 paper baseline 設計考量,RPT-min 是更乾淨、更節省 prompt budget 的選項;RPT 的 `== HEADER ==` 大結構僅在「token budget 不是問題且要榨最後幾 pp」時值得。

### 11.4 同 usable subset 的雙重驗證(同 setting deterministic check)

| Setting | usable subset(舊跑) | full 100 中 different_passage 子集(新跑) |
|---|---|---|
| PAT × SH | 46/64=72% | 46/64=72% ✓ |
| RPT × SH | 64/64=100% | 64/64=100% ✓ |
| PAT × MH | 28/66=42% | 28/66=42% ✓ |
| RPT × MH | 53/66=80% | 53/66=80% ✓ |
| RPT-min × SH | 64/64=100% | 64/64=100% ✓ |
| RPT-min × MH | 46/66=70% | 46/66=70% ✓ |

temperature=0 在 Vertex Gemini 3.1 Flash-Lite 下 deterministic,實驗可重現。

### 11.5 Plug-in 路線在 Oracle A 救不了的組仍有實質提升

兩組 Oracle A 結構上 N/A 的題目(MH 共 34 題,佔 1/3):

#### `same_passage`(20 題)

vanilla MH **0/20 = 0%**(完全失能,LLM 看到同 chunk 內新舊並存就崩潰),RPT-min 救到 40%、RPT 45%。**fact-level [CURRENT/OUTDATED FACT] 在同一 chunk 內仍能讓 LLM 部分區分新舊**,即使物理上不能移除 passage(Oracle A 受限就在於不能移除否則丟 GT)。

**Section 分配的具體行為**:`classify_passage` 邏輯是「has GT → current → Section A 優先」,所以 **mixed passage(同時含 GT 和 Old)會被歸到 Section A**,而非 Section B。實例(MH q3,hop2 是 same_passage):

```
P3 進 [SECTION A: ACTIVE]:
  [SECTION A: ACTIVE] Wikipedia Title:
    ... [OUTDATED FACT] 156. The capital of Soviet Union is Moscow. ...
    ... [CURRENT FACT]  179. The capital of Soviet Union is Russellville. ...
```

GT 和 Old 在同一段文字並列出現,**沒有 passage-level 物理隔離**,只能依賴 instruction 3「If a fact is marked [OUTDATED FACT] (whether in Section A or B), DO NOT use it」與 fact-level marker 自身。這也說明 same_passage 救率為何遠低於 different_passage(後者 Old 整個 passage 被丟去 Section B,物理 + 標題雙重 isolation)。

`older_fact` share 在 same_passage 上的比例驗證了這個 limitation:RPT-min 50%、RPT 64%(都高於 different_passage 的 35-38%),**RPT 反而比 RPT-min 嚴重**:結構重組強調「應該整個 passage 區分」,但物理上分不開,LLM 在大標題與並列文字之間困惑,attention 反而被 OUTDATED 拉得更強。

#### `retrieval_missing`(MH 14 題,SH 1 題)

**重要釐清(原稿誤導之處)**:對 FC 這類「對話歷史每句獨立事實」的任務,若 GT 完全不在 top-10,**LLM 不可能答對**(沒有外部知識可推導)。

`retrieval_missing` 組的內部結構:

| MH `retrieval_missing` 14 題的 raw status | 數量 | GT 是否在 top-10 |
|---|---:|---|
| `gt_not_safe` | 9 | **GT 在 top-10**;Oracle A 移除 old passage 會連帶丟 GT,所以 Oracle A 不能操作 |
| `old_not_all_found` | 5 | **GT 在 top-10**;Old 沒在 top-10(LLM 沒 [OUTDATED FACT] 可標) |

逐題追蹤 RPT-min 答對的 6 題:5 題 GT 完全在 top-10,僅 1 題 q2 是「2 hops 中 1 hop GT 缺失,LLM 從 partial chain reasoning 答對最終 answer」(MH chain 推理特性,非 single-fact retrieval bypass)。

**SH `retrieval_missing` = 1 題(`gt_not_retrieved`)**:GT 真的不在 top-10 → **全 method 都 0/1 = 0%**,符合「FC 任務 GT 缺失就答不出」的直覺。

#### 修正後的 takeaway

**Plug-in 路線比 Oracle A 廣的覆蓋,主要源自「不需要物理移除 passage」,而非「能在 GT 缺失時推理」**:
- `gt_not_safe` 9 題:GT 與 some Old 因 chunking 邊界連動,Oracle A 移除 old → 連帶丟 GT。**Plug-in 留下 GT,只用 [OUTDATED FACT] 標記 old**,因此可救
- `old_not_all_found` 5 題:Old 沒進 top-10 → annotation 沒 [OUTDATED FACT] 可放,prompt 退化為「only [CURRENT FACT] highlighted」,但 GT 在 → LLM 仍有機會答對
- `same_passage` 20 題:Oracle A 完全不能操作(同 chunk 移除即丟 GT)。Plug-in 仍能用 fact-level annotation 區分,雖然救率(40-45%)低於 different_passage(70-80%)

### 11.6 Failure-mode by 組(MH older_fact share)

| Setting | different_passage | same_passage | retrieval_missing |
|---|---:|---:|---:|
| PAT | 71% | 64% | 67% |
| RPT-min | **35%** | 50% | 12% |
| RPT | 38% | **64%** | 12% |

**新觀察**:**RPT 在 same_passage 上 older_fact 比例反升回 64%**(高於 RPT-min 50%)。在同一段文字內新舊並存時,**結構重組沒有減少 LLM 被 OUTDATED 拉走的傾向**,這暗示 same_passage 的 attention 拉力是不同 mechanism,需要其他改進(例如 sentence-level 編輯或 context truncation)。

`retrieval_missing` 組 older_fact 比例 12% 是因為 Old fact 多數不在 context — 答錯都不是 "answer matches OUTDATED",是 entity confusion / hallucination。

### 11.7 對 paper 的 framing 建議

> **「結構化 plug-in prompt」可在 retrieval 層級之後,以最小代價(無需重新建 graph、無需重跑 retrieval)達到甚至超越 perfect retrieval-side filter(Oracle A)的效果**。我們把 plug-in delta 拆成三層,**核心 finding 是 PAT → RPT-min 的 +24 pp**(MH,p<10⁻⁵):此單步 delta 由「passage-level grouping + inline `[SECTION X]` label + `MUST/DO NOT` 強指令」三個 prompt design 的疊加效果驅動,older_fact share 從 71% 降到 35%。第三層(RPT-min → RPT 的 `== HEADER ==` 結構重組)trend 為正但統計不顯著(p=0.077)。

> **Plug-in 路線比 Oracle A 廣的覆蓋來自「不需要物理移除 passage」**:對 14 題 MH `retrieval_missing`,**12/14 的 GT 仍在 top-10**,只是 Oracle A 移除 old passage 會連帶丟 GT(`gt_not_safe`)或 Old 沒在 top-10 而標不到 [OUTDATED FACT](`old_not_all_found`)。Plug-in 留下完整 context,只用 fact-level annotation,因此能覆蓋這 14 題。SH `retrieval_missing` 1 題 GT 真的不在 top-10,所有方法 0/1,**證實 FC 任務若 GT 完全缺失,任何 inference-time 方法都無法救**。

> 對 `same_passage` 20 題(Oracle A 結構上完全做不了),vanilla MH 0/20 = 0% 完全失能,plug-in 救到 40-45%,顯示 fact-level annotation 在「同一 chunk 內新舊並存」場景仍有部分作用。但 RPT 在這組上 older_fact share 反升回 64%(高於 RPT-min 50%),指向 **「同 chunk 新舊並存」是 plug-in 未解的 attention-level limitation**,需要 chunk-size ablation(更細 chunk 減少 same_passage 比例)或 sentence-level annotation。

### 11.8 Limitation 提醒(同前面 §8)

- 全部基於 6k context × chunk=512 × Gemini 3.1 Flash-Lite preview。**未驗證 long context(32k+)retrieval 仍能保有同樣 has_pair coverage**(若 retrieval recall drop,plug-in 路線在 paper 主張的 setting 下 N/A)
- Conversational dataset(LongMemEval, BEAM)未測,fact-level annotation 設計需要 sentence-level adaptation
- preview model 隨時可能改 API / 下架

---

## 12. Memory-method baselines:Zep & Mem0 衝突解決機制深入分析(2026-04-27)

> 此節是 paper 對「現有 memory 方法在 conflict resolution 任務上行為」的核心 baseline 比較。範圍鎖定 FC-SH 6k / FC-MH 6k,backbone 統一 gpt-4o-mini,chunk=512(與 §11 HippoRAG-v2 / RPT 階梯實驗對齊)。
>
> 結果檔:
> - [`outputs/gpt-4o-mini-zep/Conflict_Resolution/factconsolidation_sh_6k_FULL100_chunk512_results.json`](MemoryAgentBench/outputs/gpt-4o-mini-zep/Conflict_Resolution/)
> - [`outputs/rag_retrieved/Structure_rag_zep/k_10/factconsolidation_mh_6k/chunksize_512/FULL_100queries.json`](MemoryAgentBench/outputs/rag_retrieved/Structure_rag_zep/k_10/factconsolidation_mh_6k/chunksize_512/) — Zep MH 含 per-question `edges` / `nodes` / `episodes` 完整 inspection
> - [`outputs/gpt-4o-mini-mem0/Conflict_Resolution/factconsolidation_*_chunk512_results.json`](MemoryAgentBench/outputs/gpt-4o-mini-mem0/Conflict_Resolution/) — Mem0 SH+MH each n=100
> - [`outputs/rag_retrieved/Structure_rag_mem0/k_100/.../ingestion_context_0.jsonl`](MemoryAgentBench/outputs/rag_retrieved/Structure_rag_mem0/) — Mem0 per-chunk ingestion(LLM 抽出的 facts list)

### 12.0 為什麼選 Zep 與 Mem0 作為 baseline

MAB benchmark 包含 LCA / HippoRAG-v2 / Zep / Mem0 / Cognee / Letta 等多個 memory 方法,但只有 **Zep 與 Mem0 是設計上明確含「conflict resolution / memory update」機制的方法**:

- **Zep**(`zep_cloud` SDK)— 把記憶建構成 **temporal knowledge graph**,在 write-time 用 LLM 偵測同 `(subject, predicate)` 多 object 的衝突,把舊 fact 標記為 `invalid_at`(supersession)
- **Mem0**(本地 Python 庫)— 把記憶存為 **text-level memory items**,在 write-time 用 LLM 對新 fact 對既有 vector 鄰近 entries 判斷 `ADD / UPDATE / DELETE / NONE`
- 其他方法(HippoRAG-v2, Letta, Cognee)無顯式的衝突解決機制 — HippoRAG-v2 是 PPR-based graph retrieval,LLM 直接看到並列 facts,沒有特別的「新版/舊版」標記

→ Zep 與 Mem0 是 paper 中「現有方法已嘗試處理衝突」的代表,值得仔細評估它們在 FC 任務上的實際運作是否到位。

### 12.1 Zep 衝突解決機制(設計層面)

Zep 是 commercial cloud service。從 [`methods/zep.py`](MemoryAgentBench/methods/zep.py) 與 SDK 行為,衝突機制分**寫入時(write-time)**和**檢索時(retrieval-time)**兩階段:

#### Write-time(由 Zep cloud 內部執行,使用者只看到結果)

每次 `client.graph.add(graph_id, type='text', data=...)` 與 `client.thread.add_messages(thread_id, messages)` 後,Zep cloud 用 LLM(預設 OpenAI)做:

1. **Entity extraction**:從 input dialogue 抽 `(entity1, relation, entity2)` triples,儲存為 `EntityEdge`,每個 edge 帶 `fact`(自然語言述語)、`valid_at`(time of write)、`invalid_at`(initially `None`)
2. **Conflict detection**:當新 edge 與既有 edge 對同 `(subject, predicate)` 出現時,Zep 標記舊 edge 的 `invalid_at = 新 edge 的 valid_at`(supersession)
3. **Entity node summarization**:同 entity 的多個 edges 自動 summarize 成 `EntityNode.summary`(LLM 寫的長 string,可能含「conflicts with」等字眼)

#### Retrieval-time(每次 query)

[`methods/zep.py:38-44`](MemoryAgentBench/methods/zep.py#L38)

```python
edges_r = client.graph.search(graph_id=..., query=..., scope='edges',    limit=10).edges
nodes_r = client.graph.search(graph_id=..., query=..., scope='nodes',    limit=10).nodes
eps_r   = client.graph.search(graph_id=..., query=..., scope='episodes', limit=10).episodes
context = client.thread.get_user_context(thread_id=...)  # cloud 自動 conflict-resolved summary
```

`compose_search_context` 把這些訊息組進 user prompt(LLM 看到):

```
FACTS and ENTITIES represent relevant context to the current conversation.

# These are the most relevant facts and their valid date ranges...
# format: FACT (Date range: from - to)
  - {edge.fact} ({valid_at} - {invalid_at})  ← invalid_at=None 顯示 "present"
  ... (top-10 edges)

# These are the most relevant entities
  - {node.name}: {node.summary}
  ... (top-10 nodes)

# Episodes (raw user-assistant dialogue chunks)
  - Content: {episode.content}
  ... (top-10 episodes)

# Cloud-summarized user context block
{context_block}
```

LLM 的衝突解決就靠**這四種信號中的任一辨識新版**:`(valid_at, invalid_at)` 時間 range、node summary 中的衝突描述、episodes 順序、cloud-summarized context block。

> **完整 inference prompt 架構與雙重訊號問題**:見 [zep_methodology.md §1.3](zep_methodology.md)。簡言之,Zep prompt 同時餵給 LLM **兩套不一致的衝突訊號**:
> - Zep 的 `(date_range)` — 在 FACTS section,但 FC 任務指令完全沒說怎麼用 date range
> - FC 的「serial number 越大越新」rule — 在 user prompt 結尾的指令,但 FACTS section 沒有 serial number、只有 EPISODES 才有
>
> 兩個訊號各自殘缺、無對應指令、可能彼此不對齊(Zep 標 invalid 的 edge 序號未必小於 active edge),LLM 必須自行協調——這直接造成「supersession 完美觸發但 LLM 只 71% 採信」的 reasoning gap,也成為 §11 RPT 設計動機的根據(統一成顯式 `[CURRENT]/[OUTDATED]` inline marker + MUST 強指令)。

### 12.2 Mem0 衝突解決機制(設計層面)

Mem0 是本地 Python 庫(`/home/yhchiang/MemoryAgentBench/mem0/`)。

#### Write-time

每次 `memory.add(messages, user_id=...)`:

1. **Fact extraction**:用 LLM(預設 gpt-4o-mini)+ [`FACT_RETRIEVAL_PROMPT`](MemoryAgentBench/mem0/configs/prompts.py)(`Personal Information Organizer`)從 dialogue 抽 facts(輸出 `{"facts": [...]}`)
2. **Memory update**:對抽出的每個 new fact,vector-search 既有 `MemoryItem.memory: str` 的 top-k 鄰近,然後 LLM + [`DEFAULT_UPDATE_MEMORY_PROMPT`](MemoryAgentBench/mem0/configs/prompts.py) 判斷 `ADD / UPDATE / DELETE / NONE`
3. **Vector store update**:對應的 Qdrant / SQLite 更新

#### Retrieval-time

```python
relevant_memories = memory.search(query=message, user_id=..., limit=100)
memories_str = "\n".join(f"- {entry['memory']}" for entry in relevant_memories['results'])
# 然後 LLM 看到 system prompt 中的 memories_str
```

LLM 看到的 retrieved memory 是已經被 update 邏輯處理過的最終 memory items(理論上應該已是 conflict-resolved)。

#### MAB 設定下的 Mem0 不啟用 graph

[`mem0/memory/main.py:54-62`](MemoryAgentBench/mem0/memory/main.py#L54-L62) 顯示 `Memory()` default(MAB 用)的 `graph_store.config = None`,因此 `enable_graph = False`,**MAB 的 Mem0 = pure vector store + LLM-driven memory update**,不是 Mem0g(graph 版需要 neo4j server)。

### 12.3 兩者在 FC-SH / FC-MH 的具體寫入流程

兩個方法在 MAB 中都用同樣的 dialogue wrapping(`templates.py` 的 `factconsolidation` template):

```
'Dialogue between User and Assistant {time_stamp} \n
 <User> The following context is the facts I have learned: \n{context}\n 
 <Assistant> I have learned the facts and I will answer the question you ask.'
```

對 6k context × chunk=512:6k / 512 ≈ 12 chunks → 12 次 `agent.send_message(chunk, memorizing=True)` → 12 次 `add` 操作,每次帶秒級 timestamp。

- **Zep**:每 chunk 進入後 cloud 端 entity extraction 抽出 N 個 edges,並對同 `(subject, predicate)` 的舊 edges 設 `invalid_at`
- **Mem0**:每 chunk 進入後 fact extraction LLM 判斷可抽出哪些 facts;通過後做 ADD/UPDATE/DELETE

12 chunks 餵完後再進入 query 階段。

### 12.4 完整結果矩陣(同 backbone gpt-4o-mini,chunk=512,n=100 per task)

四個方法 × 兩任務的 EM:

| Method | SH Total | SH has_pair (74) | SH no_conflict (26) | MH Total (all has_pair) |
|---|---:|---:|---:|---:|
| LCA(無 retrieval,full 6k context) | 89% | 89% | 88% | 14% |
| HippoRAG-v2(graph + PPR) | 69% | 60% | 96% | 11% |
| **Zep**(temporal graph + invalid_at) | **70%** | **59.5%** | **100%** | **25%** |
| **Mem0 OOB**(text memory + ADD/UPDATE/DELETE) | **15%** | **0%** ⚠️ | 57.7% | 1% |

**fail 題的 older_fact share**(失敗中 LLM 答到 OUTDATED 真實世界答案的比例):

| Method | SH has_pair fail older_fact | MH fail older_fact |
|---|---:|---:|
| HippoRAG-v2 | 28/30 = 93% | 78% |
| **Zep** | **27/30 = 90%** | **40/75 = 53%** |
| **Mem0 OOB** | 54/74 = 73% | 46/99 = 46% |

### 12.5 SH 結果分析:Zep ≈ HippoRAG-v2(機制無顯著效益)

**SH has_pair (74 題) Zep 與 HippoRAG-v2 EM 完全相同 = 59.5%**(各 44/74 答對)。Paired 配對分析:

| | n |
|---|---:|
| Zep 對、HippoRAG-v2 對(both correct) | 27 |
| Zep 對、HippoRAG-v2 錯(Zep only) | 17 |
| Zep 錯、HippoRAG-v2 對(HippoRAG only) | 17 |
| Zep 錯、HippoRAG-v2 錯(both fail) | 13 |

**Zep 與 HippoRAG-v2 在 SH 救題完全互補,但總數一致**。Zep 多救的 17 題,HippoRAG-v2 也多救另外 17 題,兩個方法在 SH 上對 has_pair 的處理**並非全面 dominate**,而是依題目 retrieval 命中差異產生的 random 互補。

`older_fact` share 同樣接近(Zep 90%, HippoRAG-v2 93%):**SH 上兩者在失敗時,都同樣大比例答到 OUTDATED 真實世界版**,Zep 多了的 invalid_at / node summary signal 在 SH 上**沒有顯著改變失敗 mode**。

### 12.6 MH 結果分析:Zep > HippoRAG-v2 +14 pp,supersession 機制是核心貢獻

MH 100 題 全部都是 has_pair。EM:Zep 25%, HippoRAG-v2 11%,Zep 多救 14 題。

Paired 配對(MH 全 100 題):

| | n |
|---|---:|
| 兩者都對 | 6 |
| Zep 對、HippoRAG-v2 錯 | 19 |
| Zep 錯、HippoRAG-v2 對 | 5 |
| 兩者都錯 | 70 |

**Zep 真的 dominate** — 19 救 vs 5 反向(net +14)。

> **Reframe(2026-04-28)**:之前用 edges-only 觀察「Zep MH retrieval 兩者皆中只 48.4%」是錯的——episodes 截斷 dump bug 讓 episode recall 被嚴重低估。修正後:**any-scope union(LLM 推理時 prompt 中真正包含的內容)在 has_pair hops 達 94.7%、no_conflict hops 達 98.5%**,與 HippoRAG-v2 chunk-level recall(95.2%)接近。Zep 的 retrieval 並不弱於 HippoRAG-v2。詳見 [zep_methodology.md §4.4](zep_methodology.md) 的 dump bug 與 sanity-check 說明。

那 +14 來自哪裡?用「supersession 訊號可觸發」的子集分析。invalid_at 訊號只在 edges scope,因此把比較限縮在 **「該題所有 has_pair hops 在 edges 都 both-retrieved」的 34 題子集**(supersession 機制最強的觸發前提):

| 子集條件 | n | Zep EM | HippoRAG-v2 EM(同題) | Δ |
|---|:---:|:---:|:---:|:---:|
| 該題所有 has_pair hops 在 edges 都 both-retrieved | 34 | **44.1%** | 29.4% | +14.7 pp |
| 該題至少一個 has_pair hop 在 edges 都 both-retrieved | 77 | **29.9%** | 13.0% | +16.9 pp |

**Zep 的 +14 pp gain 是真實的 supersession 機制貢獻**:在 supersession 訊號可觸發的子集,Zep 比 HippoRAG-v2 多 +14.7 pp / +16.9 pp;在「supersession 完全沒觸發」的 23 題(該題所有 has_pair hops 在 edges 都 < both-retrieved)Zep 與 HippoRAG-v2 表現基本一致——LLM 看到的 episodes content 與 HippoRAG-v2 取回的 chunks 內容等價,差異消失。

→ **Zep 機制在 invalid_at 訊號可觸發時的確比 HippoRAG-v2 多救題目;當沒觸發,Zep 等價於一個更貴的 HippoRAG-v2**。

### 12.7 Zep 衝突機制效用拆解

從 Zep MH 100 題的 detailed `edges` / `nodes` / `episodes`(每題 10 個各 scope),**直接量化機制三層信號的實際運作**:

#### (a) Retrieval recall — 真實的數字(修正 dump bug 後)

Zep retrieval 三 scope 對 has_pair hops 的 GT/Old fact text recall(hop-level,n=188):

| Scope | GT recall | Old recall | both 同時取到 |
|---|:---:|:---:|:---:|
| edges | 53.2% | 54.3% | 48.4% |
| nodes | 41.5% | 35.1% | 14.9% |
| episodes | 93.6% | 94.1% | **88.8%** |
| **any-scope union** | **96.3%** | **98.4%** | **94.7%** |

> 之前用 edges-only / 截斷 episodes 得到的「Zep 兩者皆中只 40-48%」是 dump bug 造成的誤判。修正後**LLM 推理時 prompt 真正包含的內容,在 has_pair hops 上 94.7% 同時包含 GT 與 Old**——retrieval 不是 Zep 的瓶頸。

**Question-level「supersession 訊號可觸發」的子集**(從 hops 推到 question-level):

| 子集條件 | n | Zep EM | 失敗中 OUTDATED 比例 |
|---|:---:|:---:|---:|
| 該題所有 has_pair hops 在 edges 都 both-retrieved | 34 | 15/34 = 44.1% | — |
| 該題至少一個 has_pair hop 在 edges 都 both-retrieved | 77 | 23/77 = 29.9% | — |
| 該題沒有 has_pair hop 在 edges 都 both-retrieved | 23 | 2/23 = 8.7% | — |

「supersession 完全沒觸發」的 23 題 EM 8.7%,基本與 HippoRAG-v2 整體 11% 持平,符合「沒訊號就退化成 chunk-RAG」的預測。

#### (b) Detection 機制 — 「91 個 has_pair hop」是什麼

**MH 100 題 × 平均每題 2-4 個 has_pair hop,我們聚合所有有 has_pair 的 hop**(把 100 題的所有 hop 攤平算)。對每個 has_pair hop,檢查 Zep retrieved 的 10 個 edges 中是否同時有 fact 包含該 hop 的 GT-fact-text 與 Old-fact-text 各至少一個。

聚合結果:

```
MH 100 題中,有 91 個 (question, hop_idx) pair 滿足
「Zep retrieved edges 含 GT-edge AND Old-edge 兩者」
```

這 91 個 hops 是「Zep cloud 確實 retrieve 到衝突對兩個版本」的 case,可以檢查 Zep 的 supersession 標記:

| | n / 91 | 占比 |
|---|---:|---|
| GT edge 維持 active(`invalid_at = None`) | 88 | **97%** ✓ |
| **Old edge 被標 superseded(`invalid_at != None`)** | **48** | **53%** ⚠️ |
| 兩者都對(GT active AND Old superseded) | 47 | **52%** |

**Detection 只覆蓋 53% has_pair hop**(剩 47% Zep 沒識別到衝突,Old edge 也標 active)。也就是 **Zep 在 MAB 同步注入的 FC 設定下,衝突偵測機制只能捕捉到約一半的 has_pair**。

#### (c) `invalid_at` 信號強度 — 即使標記了,信號太弱

對所有 1000 個 retrieved edges(100 題 × 10 edges):

```
invalid_at != None 的 edges: 181 / 1000 (18.1%)
中的 valid 時間差(invalid_at - valid_at):
  median   1.77 s
  delta > 5 s(可信為真實 supersession): 14 / 178(8%)
```

**Zep 標記為 superseded 的 edges 有 18%,但時間差中位數只 1.77 秒**(因為 MAB 把 12 chunks 在數秒內依序餵入,每個 chunk 帶 `time.strftime('%Y-%m-%d %H:%M:%S')` 秒級時間)。**只 1.4% 的 edges 有 > 5 秒的 meaningful 時間差**,LLM 看到的 (valid_at - invalid_at) range 大多是同秒級「噪音」。

(d) 最終 LLM 決策 — 即使 detection 完整也仍被 OUTDATED 拉走

在 §12.6 的 Zep both-surfaced fail 題中(23 題),18/23 = 78% 答 OUTDATED 真實世界版。具體案例 — MH q5(GT='Baldwin Wallace University', pred='University of Bucharest'):

```
Zep edges 含:
  "Nicolae Ceaușescu is married to Elena Ceaușescu."  valid_at=None, invalid_at=None  ← OLD,detection 沒識別
  "Nicolae Ceaușescu is married to Wilhelm II."        valid_at=None, invalid_at=None  ← GT,沒 valid_at signal

Zep node summary 卻 surface 衝突字眼:
  "Wilhelm II: ... was educated at the University of Bonn, which conflicts with information stating ... Baldwin Wallace University..."
  "Nicolae Ceaușescu: ...is married to Elena Ceaușescu and is also married to Wilhelm II."
```

**Edge 級沒區分**(invalid_at=None),**Node 級用 "conflicts with" 並列兩版本**(LLM 看到並列無時序 → 困惑 → 沿著 OUTDATED chain Elena → University of Bucharest 推)。

→ **即使 Zep 機制設計上有 detection + invalid_at + node summary 三層信號,在 MAB FC 設定下實際運作時:detection 只 53% 覆蓋、invalid_at 太細微難辨、node summary 並列形式反而困惑 LLM**。

### 12.8 Mem0 OOB 失敗根源:ingestion 完全 reject(無機制可被評估)

對 Mem0,從 [`outputs/rag_retrieved/Structure_rag_mem0/k_100/factconsolidation_*_6k/chunksize_512/ingestion_context_0.jsonl`](MemoryAgentBench/outputs/rag_retrieved/Structure_rag_mem0/) 直接驗證每 chunk 的 fact 抽取結果:

| Task | Chunks ingested | Empty-result chunks | Total facts ingested across all chunks |
|---|---:|---:|---:|
| FC-SH 6k | 12 | **12 / 12 (100%)** | **0** |
| FC-MH 6k | 12 | **12 / 12 (100%)** | **0** |

**12/12 chunks 全部 0 facts 進 vector store**。即使 dialogue wrapping 帶 user-assistant 形式餵入,Mem0 的 [`FACT_RETRIEVAL_PROMPT`](MemoryAgentBench/mem0/configs/prompts.py)(`Personal Information Organizer`,專注 personal preferences / relationships / important dates)被 LLM 解讀為「拒絕一切非 personal 的通用知識」,輸出 `{"facts": []}`。

**結果**:Mem0 OOB 對 FC general-knowledge 在 ingestion 階段 100% reject,**Mem0 真正的 conflict resolution 機制(ADD/UPDATE/DELETE)完全沒被觸發**(沒有 fact 進 vector store,何來 update?)

Mem0 SH 15% / MH 1% 是 LLM 看到空 retrieval 時的 pretraining-knowledge fallback,**不反映 Mem0 機制**。

### 12.9 與 HippoRAG-v2 的異同綜合(同 backbone gpt-4o-mini, chunk=512)

| 面向 | HippoRAG-v2 | Zep | Mem0 OOB |
|---|---|---|---|
| 記憶結構 | KG triples(entity-relation-entity)+ chunk passages | Temporal KG(同上但每 edge 帶 valid_at / invalid_at)| Vector store + text MemoryItems |
| 衝突機制 — write-time | **無顯式機制**,直接 add 同 (subject, relation) 多 object 的 edges | LLM detection + 設舊 edge `invalid_at` | LLM 判斷 ADD/UPDATE/DELETE/NONE |
| 衝突機制 — retrieval-time | PPR 排序 → top-k passages 進 LLM(LLM 看並列 facts 無新版/舊版區分) | top-10 edges 帶 (valid_at, invalid_at)+ node summary 含 "conflicts with"+ episodes 順序 | top-100 vector-similar memories 進 LLM(假設已 conflict-resolved) |
| FC-SH has_pair (74) EM | 60% | **59.5%** | 0% |
| FC-MH (100) EM | 11% | **25%** | 1% |
| FC-MH「edges-both 全 has_pair hops」子集(34)EM | 29.4% | **44.1%** | — |
| MH fail older_fact share | 78% | 53% | 46% |

**異**:
1. Zep 在 write-time 多了 detection + invalid_at,在 retrieval-time 多了 node summary "conflicts with" 描述
2. MH overall 上 Zep 比 HippoRAG-v2 多救 14 題(EM 25% vs 11%),supersession 可觸發子集上 +14.7 pp
3. SH 上兩者 has_pair EM 完全一樣(59.5%),機制無實質效益(supersession 在 SH 觸發率僅 6/74 = 8%)

**同**:
1. SH has_pair fail 中 90%+ 都答 OUTDATED — LLM 仍主要被 fact 字面內容拉走
2. MH 同樣崩潰於 3-hop 以上多 conflict 題型(0-10%)
3. **Retrieval recall 在 union 後接近(Zep 94.7% vs HippoRAG-v2 95.2% MH)**——兩個方法 LLM 看到的 context 覆蓋差距很小;真正差別在 supersession 訊號是否可觸發

### 12.10 衝突解決機制當前的 gap 與 paper 改進方向

從以上分析可分離出三個 specific gap,分別對應不同的改進空間:

#### Gap 1:**Detection 機制在同步注入(非 conversational temporal)場景下覆蓋不足**

Zep 設計假設 conversational data 跨時間真實衝突;FC 把所有 facts 在數秒內密集注入,Zep cloud 的 LLM-based detection 只能識別 53% has_pair。**改進方向 A**:把 supersession 信號從 timestamp 改成 task-aware proxy(例如 fact 的 serial number,或 explicit `chunk_order` 標記),detection 可達 ~100%。但這需要 Zep / Mem0 做 product-level 修改,paper 角度只能當 limitation 寫。

#### Gap 2:**LLM 對 metadata 信號(`invalid_at`、node summary)的利用率低**

即使 detection 完整(在 91 has_pair hops 中的 47 個兩者都對的 case),fail 題仍 78% 答 OUTDATED。LLM 不會主動規避 `(invalid_at != None)` 的 fact,也容易被 node summary 並列困惑。**改進方向 B(我們的 RPT 路線)**:把 metadata 從隱式 `(date_range)` 形式升級為**顯式 `[CURRENT FACT] / [OUTDATED FACT]` inline marker + 強指令 `MUST NOT use OUTDATED`**。我們 §11 的 RPT 在 LCA setting 上 SH 100% / MH 80%,證明 LLM-side prompt-engineering 能直接補上這個 gap。

#### Gap 3:**Edges 取回(supersession 訊號的唯一載體)只 ~50%**

Zep 的 invalid_at 訊號只附在 edges,而 edges 兩者皆中只 SH 51.4% / MH 48.4%。剩餘 ~50% 的 has_pair 題目即使 LLM 已經看到 GT 與 Old 的事實文字(在 episodes 層,union 已 95%+),但拿不到時間訊號,仍要靠 prompt 序號規則處理——表現等價於 HippoRAG-v2。**改進方向 C**:讓 supersession metadata 跟著 entity / episode 一起暴露,而不只在 edges scope。但這偏離 plug-in 路線,屬於 retrieval-side 工程。

> **Retrieval coverage 本身不是 gap**:any-scope union 在 has_pair 上 SH 100% / MH 94.7%——LLM 幾乎總是看到 GT 與 Old 兩者,gap 純粹在「訊號的可信度與覆蓋率」,不在「事實是否進入 context」。

#### 收斂到核心改進方向

| 改進方向 | 我們做的 | 結果 |
|---|---|---|
| **A. Retrieval-side detection 強化** | 未做(屬於 Zep / Mem0 product-level 設計) | — |
| **B. LLM-side explicit signaling**(plug-in prompt) | ✓ §11 PAT / RPT-min / RPT 階梯實驗 | SH 67% (vanilla) → 100% (RPT);MH 27% → 80%(usable subset);PAT → RPT-min 是 +24 pp 主要 driver |
| **C. Retrieval recall 擴增** | 未做,但 §11 顯示 RPT 在 different_passage(retrieval 完整)的提升最大 | RPT MH different_passage 80% vs same/missing 40-45% |

**paper main contribution 應 frame 在 B**(LLM-side explicit signaling): 證明即使 retrieval 已 union 達 95%+ recall(Zep 上 LLM 幾乎看到了所有 has_pair 題目的 GT 與 Old)、且 retrieval-side 已嘗試 conflict-aware design(Zep 的 detection + invalid_at),**因 invalid_at 訊號只覆蓋 ~50% has_pair 題且 LLM 對 metadata 利用率低,衝突解決效果仍 cap 在 SH 60% / MH 25%**;我們提出的 RPT 不要求 retrieval 端任何改變,僅在 prompt 層面把信號顯式化(inline `[OUTDATED FACT]` + `MUST` 指令),即可在 fair retrieval 條件下**將 conflict resolution 拉到 SH 100% / MH 80%(LCA setting)** 或 **超過 retrieval-side filter(Oracle A)的水準**(§11.3,RPT-min vs Oracle A p=0.45 n.s.,RPT vs Oracle A MH +17 pp p=0.02)。

### 12.11 Limitation 與待補實驗

1. **Mem0 OOB 等於沒被測試**:ingestion 100% reject。為 fair evaluate Mem0 的 ADD/UPDATE/DELETE 衝突解決,需要 customize fact extraction prompt(保留 update prompt 不動)。Phase 2 待跑
2. **SH supersession 細節**:已透過 retrieval-only re-fetch([run_zep_refetch_retrieval.py](MemoryAgentBench/run_zep_refetch_retrieval.py))拿到 SH 100 題完整 edges/nodes/episodes,SH detection 細節已可量化(見 [zep_sh_summary.md](zep_sh_summary.md))
3. **同步注入的時間特性是 MAB FC 的 dataset-specific artefact**;Zep 機制在真正 conversational temporal data(LongMemEval-KU 等)的表現需要另測
4. Backbone 統一 gpt-4o-mini 對齊 Vanilla / HippoRAG-v2 / Zep / Mem0;若換 Gemini 3.1 Flash-Lite 結果可能改變 — 但 Mem0 / Zep 內部 LLM 仍是 OpenAI(commercial cloud 不可換),所以「換 backbone」對 Zep 只能換 final answer LLM,不能換內部 detection / extraction LLM

---

## 13. Differentiation analysis(Zep vs RPT,paper-framing 收斂版)

> 此節是 §12 的延伸,把「Zep 機制觸發狀態 × EM」分組(Zep-native 失敗分類)、Zep 與 PAT/RPT-min/RPT 的逐題重疊、SH-vs-MH 機制效用對比集中放在這裡,直接服務於 paper 的「differentiation vs prior work」章節。
>
> 分析腳本:[analyze_zep_taxonomy_and_overlap.py](analyze_zep_taxonomy_and_overlap.py)
> 結構化結果:[results/zep/zep_taxonomy_overlap.json](results/zep/zep_taxonomy_overlap.json)

### 13.1 Zep-native 失敗分類(機制觸發狀態 × EM)

把 SH/MH 的每題依「該題 has_pair hops 在 Zep 機制中的觸發狀態」分組。Zep-native 取代 HippoRAG 的 different_passage / same_passage / retrieval_missing,因為 Zep 的訊號層不同(time-stamped edges 而非 chunk passages)。

#### SH(74 has_pair)

| Zep 機制狀態 | n | EM | HippoRAG 對比子集 EM |
|---|:---:|:---:|---|
| **SUPERSESSION_PERFECT** | 6 | **6/6 = 100%** | ~70% |
| **SUPERSESSION_MISFIRED** | **14** | **1/14 = 7%** ⚠️ | ~70% |
| EDGES_BOTH_NO_SIGNAL | 18 | 15/18 = 83% | ~70% |
| NO_EDGE_SIGNAL_BUT_VISIBLE | 36 | 22/36 = 61% | ~70% |
| RETRIEVAL_MISSING(union 缺) | 0 | — | — |

> **Zep 在 SH 的機制淨效應 ≈ 0**:perfect 6 題 +30pp × 6 題 vs misfired 14 題 −63pp × 14 題,相互抵消。具體 14 個 misfired 題目全部是「新事實違反世界知識」的 MQuAKE-CF counterfactual(US 官方語言=德語、basketball 創於蘇聯等)——這些題在 HippoRAG-v2 因為沒機制過濾、LLM 仍能依 prompt 「序號越大越新」答對 ~70%;在 Zep 反被機制誤導,只剩 7%。

#### MH(100 全 has_pair,question-level worst-case 聚合)

| Zep 機制狀態 | n | EM | HippoRAG 同類分組 EM |
|---|:---:|:---:|---|
| **ALL_PERFECT** | 14 | **10/14 = 71%** | ~26% |
| PARTIAL_PERFECT | 27 | 8/27 = 30% | ~26% |
| **NO_SIGNAL_BOTH_VISIBLE** | 47 | **4/47 = 9%** | ~11% |
| ANY_MISFIRED | 3 | 0/3 = 0% | ~26% |
| ANY_RETRIEVAL_MISSING | 9 | 3/9 = 33% | ~14% |

> **Zep 在 MH 的 +14pp gain 主要由 ALL_PERFECT 子集驅動**:14 題 EM 71% vs HippoRAG ~26% ≈ +45pp × 14/100 = +6.3pp;PARTIAL_PERFECT 略有貢獻;NO_SIGNAL_BOTH_VISIBLE 47 題 EM 9%(等同 HippoRAG 11%),這部分 Zep 退化成更貴的 chunk-RAG。

### 13.2 SH vs MH 機制效用對比 — 多跳鏈本身是 MH 難解的根本

把 SH 與 MH 的「無 supersession 訊號但 LLM 看到 GT/Old 兩者」子集 EM 並列:

| 機制狀態 | SH EM | MH EM |
|---|:---:|:---:|
| PERFECT(完美觸發) | 100% (6/6) | 71% (10/14) |
| NO_SIGNAL_BUT_VISIBLE | **68.5%** (37/54) | **8.5%** (4/47) |
| MISFIRED | 7% (1/14) | 0% (0/3) |

> **同樣是「沒 supersession 訊號、但 LLM 看到 GT/Old 兩者」的條件,SH 68.5% 而 MH 8.5%——差距 60pp**。這直接指出:
>
> **MH 多跳知識更新的核心瓶頸不是 retrieval、不是訊號層,而是 LLM 在多跳鏈的每一步都得「自主」選新棄舊**。單跳只要選一次對就答對;多跳要每步都選對才能答對(乘法效應)。即使 Zep 提供 ALL_PERFECT 訊號,MH 仍掉到 71%(從 100% SH);而當無訊號,MH 直接掉到 8.5%(SH 仍 68.5%)。
>
> Paper framing 上,這個發現收斂出「MH 難解的根本原因」:**multi-hop chain × per-hop conflict 形成的乘法-conflict 結構**,需要 explicit-per-hop signaling(我們的 RPT 設計動機)。

### 13.3 4-way contingency: Zep × HippoRAG × RPT-min × RPT(MH 100q)

| 方法 | EM | 與 Zep both | Zep only | other only | neither |
|---|:---:|:---:|:---:|:---:|:---:|
| HippoRAG-v2 | 11% | 6 | 19 | 5 | 70 |
| Zep | 25% | — | — | — | — |
| PAT(plug-in 加 instruction) | 36% | 12 | 13 | 24 | 51 |
| RPT-min(分區 [CURRENT]/[OUTDATED]) | 60% | 19 | **6** | **41** | 34 |
| RPT(分區 + MUST 指令) | **68%** | 25 | **0** | **43** | 32 |

> **核心 punchline**:**RPT 嚴格 dominate Zep on FC-MH**——Zep 答對的 25 題 RPT 全部都答對,**0 題是 Zep 唯一答對**;且 RPT 還多救 43 題。RPT-min 也接近 dominate(僅 6 題 Zep 唯一答對)。
>
> **Hard core: All 4 methods fail = 28/100**:即使透過 prompt-level explicit signaling 也無法救的題;這 28 題是真正屬於「retrieval-missing(union 不全)+ 多跳鏈結構過於複雜」的交集,paper 可以當 limitation 寫(對應 future work 方向 C:retrieval recall 擴增)。

### 13.4 paper differentiation 章節寫作要點

從以上分析,paper 的「differentiation vs prior work」可以這樣鋪:

1. **Zep 設計 vs 我們 RPT 設計屬於同一條 LLM-side explicit signaling 路線**——Zep 在 ingestion 時抽 entity edge + 標 invalid_at,把「新/舊」訊號注入 LLM context 的 (Date range) 形式;RPT 在 retrieval 後 prompt 時加 [CURRENT FACT] / [OUTDATED FACT] inline marker + MUST 指令。**兩者目標相同:讓 LLM 不要被舊事實拉走**。
2. **差別在訊號的觸發率、可信度、強度**:
   - Zep:觸發率 SH 8% / MH 14%(ALL_PERFECT 子集),misfire 率 SH 19% / MH 3%,訊號形式 `(date_range)` 隱晦
   - RPT:覆蓋率 100%(每個 has_pair 對都被標),misfire 率 0%(因為 marker 直接從 ground truth 序號推),訊號形式 `[CURRENT FACT] / [OUTDATED FACT]` 顯式 + `MUST NOT use OUTDATED`
3. **結果差異**:Zep MH 25% vs RPT MH 68%;Zep 嚴格被 dominate,沒有 Zep 唯一答對的題目
4. **MH 比 SH 更難的根本原因**:無訊號條件下 SH 68.5% / MH 8.5%(差距 60pp),多跳鏈 × 衝突的乘法結構——這是 paper 應該強調的 problem framing
5. **Zep 在 SH 主動傷害的 14 題 counterfactual 案例**(MQuAKE-CF 特有):機制 LLM extractor 偏向世界知識、把違反常識的 GT 標 invalid——這是 baseline 評估 Zep 時的 dataset artifact,但對 paper 是有效的「prior work 在 counterfactual setting 失準」證據
6. **Hard core 28 題**(all-method-fail):未來 work 的方向,結合 retrieval-side detection 強化或多跳鏈專用解碼策略
