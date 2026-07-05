# Matcher v4 audit — gpt-4o-mini × 64k(2026-07-05)

> **目的**:paper §Metrics 的 pool state 分析 rigor 佐證。手動核對 matcher v4 於 gpt-4o-mini × 64k 的 PP-OldOnly + PP-Missing wrong qids 是否有 false-negative。
>
> **範圍**:ours main + (b) mem0+P1 於 has_pair N=66 的**全部** wrong-in-PP-OldOnly-or-PP-Missing qids(25 題)。
>
> **⚠ 待人工 double-check**:本檔分類由 audit script 自動 + Claude 手動 review 產出;paper 提交前建議由第二人複查 5-10 題確認。
>
> **產生腳本**:`scratchpad/deep_audit_pp_wrong.py`(scratchpad 版;若定案可 promote 至 `analysis/`)。

---

## §1 Audit protocol

1. **Auto**:用 canonical `compute_pool_acc_crosstab.extract_pool_texts` 取得 per-qid pool text list(ours 用 `memories_str`;(b) 用 `retrieved_memories`)。
2. **Bucket**:用 canonical `compute_pool_acc_crosstab.classify_pool_state`(內部呼叫 `compute_m1_m2_m3.match_pair_v4`)分桶。
3. **Filter**:只保留 PP-OldOnly + PP-Missing 且 E2E EM = wrong 的 qids。
4. **Deep check**:對每題檢查 `subject` + `new_object` 是否**同時出現於任一 pool 條目**(比 matcher v4 更寬鬆的 loose FN 檢驗)。
5. **Classify**:每題手動判定機制 = F(write-time destructive)/ D(D-flag benchmark bug)/ 其他。

---

## §2 分類結果(25 qids)

| Method | qid | matcher 桶 | Deep FN check | 機制 | 說明 |
| :--- | :---: | :--- | :---: | :--- | :--- |
| ours main | 20 | PP-OldOnly | ✅ legit | **D-flag** | Great Britain / Europe;gt_seq < old_seq → argmax 邏輯上不可能對 |
| (b) mem0+P1 | 1 | PP-OldOnly | ✅ | **F** | Hard Times / MLK Jr.(mem0 UPDATE 誤刪新版)|
| (b) mem0+P1 | 2 | PP-OldOnly | ✅ | **F** | David Farragut / Denmark |
| (b) mem0+P1 | 4 | PP-OldOnly | ✅ | **F** | Joseph Mitchell / UK |
| (b) mem0+P1 | 9 | PP-OldOnly | ✅ | **F** | Kermit / Hiroshige |
| (b) mem0+P1 | 11 | PP-Missing | ✅ | **F** | Prince Andrew / Mahidol(兩版都被刪光)|
| (b) mem0+P1 | 18 | PP-Missing | ✅ | **D-flag + F** | Red Storm Rising / Tom Clancy;gt_seq=7 < old_seq=1219 |
| (b) mem0+P1 | 20 | PP-Missing | ✅ | **D-flag + F** | 同 ours qid=20;mem0 兩版都缺(F 疊 D)|
| (b) mem0+P1 | 26 | PP-Missing | ✅ | **F** | Wilma Flintstone / Eric Garcetti(兩版都刪光)|
| (b) mem0+P1 | 29 | PP-OldOnly | ✅ | **F** | PowerBook G4 / Microsoft |
| (b) mem0+P1 | 31 | PP-Missing | ✅ | **F** | Die Gartenlaube / Austrian Empire |
| (b) mem0+P1 | 35 | PP-Missing | ✅ | **F** | Ilir Meta / Montana State University |
| (b) mem0+P1 | 38 | PP-OldOnly | ✅ | **F** | Zürich / Antarctica |
| (b) mem0+P1 | 59 | PP-Missing | ✅ | **F** | bluegrass / Indonesia |
| (b) mem0+P1 | 60 | PP-OldOnly | ✅ | **F** | North East Stars / cricket |
| (b) mem0+P1 | 61 | PP-OldOnly | ✅ | **F** | Tesla CEO / Adam Sandler |
| (b) mem0+P1 | 70 | PP-OldOnly | ✅ | **F** | Aam Aadmi Party / Lamar Alexander |
| (b) mem0+P1 | 71 | PP-OldOnly | ✅ | **F** | Beatles for Sale / Madonna |
| (b) mem0+P1 | 79 | PP-Missing | ⚠ script 誤報(subject regex 抓空)| **F** | George Boole / Spanish;subject "George Boole" 未於任何 pool 條目出現,實際 legit |
| (b) mem0+P1 | 84 | PP-OldOnly | ✅ | **F** | Paul Morley / Ireland |
| (b) mem0+P1 | 85 | PP-OldOnly | ✅ | **F** | Reese Witherspoon child / James Badge Dale |
| (b) mem0+P1 | 90 | PP-OldOnly | ✅ | **F** | Manuel Neuer / linebacker |
| (b) mem0+P1 | 91 | PP-OldOnly | ✅ | **F** | Lonesome Dove / Robert A. Heinlein |
| (b) mem0+P1 | 92 | PP-OldOnly | ✅ | **F** | Allan Pinkerton / Pune |
| (b) mem0+P1 | 95 | PP-Missing | ✅ | **F** | iPad Pro / Google |

## §3 統計摘要

| 機制 | 題數 | 佔 25 audit 樣本 | 佔 mem0 32 全 wrong |
| :--- | :---: | :---: | :---: |
| **F. Write-time destructive damage**(mem0)| **22** | 88% | 69% |
| **D. Benchmark D-flag** | 2(mem0 qid=18, 20)| 8% | 6% |
| **D-flag(ours 也錯)** | 1(ours qid=20)| 4% | — |
| **Matcher confirmed FN** | **0** | **0%** | 0% |

**其他 8 mem0 wrong 於 PP-Both 桶**(pool 兩版都有 → answer LLM 挑錯):非 matcher 精度問題,為 answer LLM 側 Mode C / ambiguity,另分析(§4.4 case study)。

## §4 對 §Matcher_specification.md §3.1 的更新

原歷史估計「mem0+P1 9/15 FN、ours 2/2 FN」**已 verified 為過度悲觀**。實際 v4 於 gpt-4o-mini × 64k 上 **0 confirmed FN**。matcher_specification.md §3.1 已同步更新。

## §5 對 paper §Metrics 的意涵

Pool state × Accuracy attribution 於 gpt-4o-mini × 64k 上**可靠**,無需 residual FN caveat 縮減主張。**(b) mem0+P1 的 write-time destructive damage 於 gpt-4o-mini 佔全部 wrong 的 ~69%**(22/32);另加 D-flag 6%(2/32)= 25/32 pool-side attribution,剩餘 7/32 為 PP-Both bucket 的 answer LLM 側機制。

## §6 尚需複查與擴展的項目

- ☐ **人工 double-check** 5-10 題(paper 提交前)
- ☐ **6k / 32k 同等 audit**(gpt-4o-mini)
- ☐ **gpt-4.1-mini × 64k audit**
- ☐ **gemma3 12B/27B × 6k audit**(1B/4B 已明確標為 pool_state 不可用)
- ☐ **matcher script promotion**:`scratchpad/deep_audit_pp_wrong.py` → `analysis/audit_matcher_v4.py` 若定案為固定工具
