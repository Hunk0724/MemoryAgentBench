# Matcher Specification — pool state classification rigor

> **用途**:paper §4 Metrics / §5 Case study / §6 Rigor 三處都用到 matcher 判定「memory pool 是否含 gt_new / gt_old」。此檔是**唯一 source of truth** 說明各版本演進、當前使用版、限制與 known false-negative rate。
> **paper 誠實 disclose**:matcher 是**演算法判斷**,有 precision limit;正文附錄需附此檔以供 reviewer 檢視。
> **相依 code**:[`analysis/compute_m1_m2_m3.py::match_pair_v4`](../../../../analysis/compute_m1_m2_m3.py) 是 canonical implementation。

---

## §1 Matcher 演進版本

### v1(棄用)— 純 keyword match
- 判 `gt_answer` token 是否在 memory 內
- **問題**:高 false positive(GT answer 出現在無關 fact 也算 match)

### v2(棄用)— SequenceMatcher ratio
- 用 `difflib.SequenceMatcher` 判 memory vs gt_fact 的字串相似度
- Threshold 0.85
- **問題**:false positive(不同 object 的相同 predicate stem 過閾值,如 `goaltender → pesäpallo` vs `goaltender → ice hockey` ratio=0.857 > 0.85)

### v3(2026-06,先前 canonical)— triple-based rigor
- 拆解 `gt_new` / `gt_old` 成 `(shared_stem, new_object, old_object)`
- Rule (i):shared stem 非停詞 token 於 memory ≥60% 命中
- Rule (ii):target object token **全部** present
- Rule (iii):non-target object token **不可全部** present(避免混淆)
- **問題**:Rule (iii) 用 bag-of-words 檢查 → 若 non-target object token 出現在**subject 位置或無關位置**(bag-of-words 無法區分位置),誤判為 ambiguous → false negative

### v4(2026-07-04,當前 canonical)— Layer-0 substring + v3 fallback
- **Layer 0(permissive verbatim check)**:
  - Normalize gt_target_fact 完整字串
  - 若 normalize(gt_target_fact) 是 normalize(memory) 的 substring **AND** normalize(gt_other_fact) 不是 substring → return TRUE
  - Handle verbatim match cleanly, disambiguated
- **Layer 1(v3 fallback)**:若 Layer 0 沒判定 → 用 v3 triple-based
- **精度提升**(64k, all 3 methods):
  - ours PP-OldOnly false-neg:5/5 → 2/2
  - Zep PP-OldOnly false-neg:3/3 → 0/0
  - mem0+P1 PP-OldOnly false-neg:11/17 → 9/15

---

## §2 v4 演算法完整偽碼

```python
def match_pair_v4(memory_text, gt_new_fact, gt_old_fact, target):
    """target ∈ {'new', 'old'}."""
    mem_n = normalize(memory_text)          # lowercase, punct→space, ws collapse
    if not mem_n: return False
    gt_target = gt_new_fact if target == 'new' else gt_old_fact
    gt_other  = gt_old_fact if target == 'new' else gt_new_fact
    gt_target_n = normalize(gt_target)
    gt_other_n  = normalize(gt_other)

    # -------- Layer 0: full-fact substring pre-check --------
    if gt_target_n and gt_target_n in mem_n:
        # only unambiguous if other version's full text NOT also in mem
        if not (gt_other_n and gt_other_n in mem_n):
            return True

    # -------- Layer 1: v3 triple-based fallback --------
    return _match_pair_v3(memory_text, gt_new_fact, gt_old_fact, target)


def _match_pair_v3(memory_text, gt_new, gt_old, target):
    mem_words = set(normalize(memory_text).split())
    stem, new_obj, old_obj = extract_stem_objs(gt_new, gt_old)
    target_obj = new_obj if target == 'new' else old_obj
    other_obj  = old_obj if target == 'new' else new_obj

    stem_salient  = drop_stopwords(stem)
    target_salient = drop_stopwords(target_obj)
    other_salient  = drop_stopwords(other_obj)

    # Short stem (few salient words) → fall back to normalized full-string check
    if len(stem_salient) < 2:
        gt_target = gt_new if target == 'new' else gt_old
        return normalize(gt_target) in normalize(memory_text)

    # Rule (i): ≥60% stem tokens present
    if sum(1 for w in stem_salient if w in mem_words) / len(stem_salient) < 0.6:
        return False
    # Rule (ii): target object all tokens present
    if not target_salient or not all(w in mem_words for w in target_salient):
        return False
    # Rule (iii): non-target object NOT all tokens present (disambiguation)
    if other_salient and all(w in mem_words for w in other_salient):
        return False   # ambiguous → conservative False
    return True
```

**Stem 抽取**(用於 v3 fallback):
```python
def extract_stem_objs(gt_new, gt_old):
    """gt_new='X is Y', gt_old='X is Z' → stem='X is', new_obj='Y', old_obj='Z'"""
    a = gt_new.split(); b = gt_old.split()
    stem_len = 0
    for wa, wb in zip(a, b):
        if wa.lower().rstrip('.,;:!?') != wb.lower().rstrip('.,;:!?'):
            break
        stem_len += 1
    return (
        ' '.join(a[:stem_len]),                    # shared prefix
        ' '.join(a[stem_len:]).rstrip('.,;:!?'),   # new object tail
        ' '.join(b[stem_len:]).rstrip('.,;:!?'),   # old object tail
    )
```

**Normalize**(v3 + v4 共用):
```python
def normalize(s):
    s = (s or '').lower()
    s = re.sub(r'[^\w\s]', ' ', s)
    return re.sub(r'\s+', ' ', s).strip()
```

**Stopword 列表**(drop_stopwords 用):
```
{"the", "a", "an", "of", "is", "was", "are", "were", "be",
 "in", "on", "to", "for", "and", "or", "at"}
```

---

### 3.1 Residual false-negative(64k audit,**2026-07-05 update**)

**2026-07-05 update**:先前表列「ours 2/2、mem0+P1 9/15」為 v3 → v4 遷移期的**保守歷史估計**(基於 aggregated file 而非 canonical per-qid + `extract_pool_texts` 分項比對),已 stale。

**2026-07-05 完整 v4 audit**(gpt-4o-mini × 64k has_pair N=66,方法 = ours main + (b) mem0+P1;掃全部 PP-OldOnly + PP-Missing wrong qids,共 25 題;deep check = 檢查 `subject + new_object` 是否同時出現於同一 pool 條目內):

| Method | PP-OldOnly + PP-Missing wrong qids | Confirmed FN | 備註 |
| :--- | :---: | :---: | :--- |
| ours main | 1(qid=20) | **0** | qid=20 為 D-flag(benchmark 缺陷),非 matcher FN |
| (b) mem0+P1 | 24 | **0** | 22 個為 write-time destructive damage、2 個為 D-flag(qid=18, 20)|
| Zep (k=10) | — | 0 | Zep edges 保留完整原句,v3 期已 0/0 FN |

**結論**:matcher v4 於 gpt-4o-mini × 64k 上**目前 0 個 confirmed false-negative**;歷史 9/15 估計已 verified 為過度悲觀。**Pool state 分析可安全作為 aggregate attribution 使用**。

**⚠ 尚需人工 double-check 的殘餘不確定**:
- 25 題的分類為 script 產出(見 `results/matcher_audit_gpt4omini_64k.md`),paper defence 前建議人工複查 5-10 題確認。
- **未 audit 範圍**:PP-Both wrong 桶(8 題 mem0 + 若干 ours 於 PP-Both 錯)為 answer LLM 側機制(Mode C 或 ambiguity),非 matcher 問題,不影響 matcher precision。
- **未 audit 長度**:6k / 32k 尚未同等 audit;pattern 預期一致(matcher v4 於同 backbone、同 pool_key 上表現一致),但 paper defence 前 recommended 補做。
- **未 audit backbone**:gpt-4.1-mini × 64k、gemma3 12B/27B × 6k 未做同等 audit;weak-backbone(1B/4B)已於 `weak_model_6k_analysis.md §2` 明確標為 pool_state 不可用。

**方向**:v5 目前**無迫切需要**;若 6k / 32k audit 找出 FN 案例再議。

### 3.2 對 weak-model regime 的 shape

Weak model(如 gemma3 1B/4B)抽 triple 可能 truncated 或 malformed → memory text 更難 match gt_fact_text 完整字串 → matcher 精度**必然下降**。

**paper 對策**:
- gpt-4o-mini 主分析:pool_state × Acc 可信,cross-tab 為主 supporting evidence
- weak-model regime:pool_state × Acc **僅供 reference**,paper 主敘事為 **E2E Acc + 錯誤模式 case study**

### 3.3 不能區分「pool 有 fact 但 answer LLM 忽略」vs「pool 缺 fact」的具體 cause

Matcher 只判「pool 有無 gt_new/gt_old」,不判「LLM 為何錯」。**Mode C(world-knowledge override)只能靠 case study 手動歸類**(見 [`results/case_studies_64k.md`](results/case_studies_64k.md))。

---

### 3.4 跨方法 pool_state 不可比性 + Zep 需 bi-temporal mediator（2026-07-07)

**核心 rigor 警告**:文字 pool_state（PP-New/Both/OldOnly/Missing,§2 matcher）量的是「答題 LLM 文字上看到 gt_new/gt_old 沒有」。此變數對三種方法的 **EM 中介地位不同**,不可一律套用:

| 方法 | KU resolution locus | pool 文字對 EM 的中介地位 | 正確 mediator |
| :--- | :--- | :--- | :--- |
| **mem0** | write-time（實刪/覆寫 old） | ✅ 文字 pool 就是機制結果（刪錯 → PP-OldOnly → 答錯） | 文字 pool_state |
| **ours** | query-time（全版本保留,查詢時 group→取 new） | ✅ resolved 後文字 pool 就是輸出（解對 → PP-New） | 文字 pool_state（`memories_str`） |
| **Zep** | **inference-deferred**（保留 + 標 `invalid_at`,呈現 date range 讓 LLM 自判） | ❌ pool 幾乎恆 PP-Both（實測 64k 65/66 ≈98%）,文字無 KU 信號 | **bi-temporal resolution state** |

**為何 Zep 失效**:Zep search 不過濾 invalid edges,兩版恆同時出現 → 文字 classifier 把「Zep 正確解 KU / 沒解 / 解反」三種機制相反情況全壓成 PP-Both,零鑑別力。Zep 的 KU 決定寫在 `valid_at`/`invalid_at`,不在文字。

**Zep 專用分類器**(`analysis/classify_zep_ku_resolution.py`,讀 bi-temporal;Resolved-* 桶**要求 handoff-verify** `loser.invalid_at==winner.valid_at`,避免把「被第三方 fact invalidate」或「matcher 在 generic (S,P) stem 上 over-match 到別 entity」誤記為 resolution)實測(gpt-4o-mini,has_pair):

| length | Resolved-Correct | Resolved-Backward | Additive-NoKU | Other-Ambiguous | overall acc |
| :--- | ---: | ---: | ---: | ---: | ---: |
| 6k | 23%（acc 88%） | 30%（acc 36%） | 39%（acc 69%） | 8% | 62% |
| 32k | 9%（acc 100%） | 3% | 77%（acc 44%） | 6% | 51% |
| 64k | 17%（acc 100%） | 0% | 74%（acc 41%） | 8% | 55% |

- **Additive-NoKU = 長 context 主導,且為保守下界**(over-match 只會把 query 踢出 additive → 真實值 ≥ 報告):32k/64k 77/74%。Zep 越長越測不到衝突。
- **失敗在觸發率不在讀取**:Resolved-Correct 桶 acc 88–100% — Zep 設對時序,LLM 就答對。
- **length interaction**:短 context(6k)Zep 嘗試解但常 **Resolved-Backward**(30%、acc 36%,world-prior 反向失效 counterfactual);長 context 轉為 additive。
- **Other-Ambiguous 6–8%** 為殘差(第三方 invalidate + matcher over-match,multi-edge ~30%);引用信心:Additive > Resolved-Correct > Resolved-Backward 單一數字。完整判讀見 results 檔。

完整表格與判讀:[`results/zep_ku_resolution_bitemporal.md`](results/zep_ku_resolution_bitemporal.md)。

**對 crosstab 使用的結論**:跨方法**只在 E2E Acc 對齊比較**;機制歸因 mem0/ours 用文字 pool_state、Zep 用 bi-temporal resolution state。**勿**把 Zep 的 PP-Both 與 mem0 的 PP-OldOnly 並列(會低估 Zep 的 KU 失敗——PP-Both 看似「兩版都在沒問題」,實際 ~80% 未解)。§3.1 的「Zep 0/0 FN」僅指**文字比對精度**,不涵蓋 bi-temporal 語意。

---

## §4 rigor audit workflow(供 GX10 及 future run reference)

**在 canonical 化任何 crosstab 前,必先跑**:
```bash
python analysis/rigor_audit.py --length 64k --method "ours (no_p5)"
# → 檢查 aggregated ↔ per-qid consistency,列 mismatch qids,
#   report per-bucket false-negative rate (用 gt_answer substring check 為 loose ground truth)
```

**Audit 產出**:
- `docs/0615_.../paper_current/rigor_audit.md` — 全 method × length aggregated-vs-perqid + matcher precision 一頁 summary
- 若某 (method, length) 出現 mismatch → 標記為 **stale / broken** → 不可直接引用

---

## §5 檔案位置速查

| 用途 | 位置 |
| :--- | :--- |
| Canonical matcher code | `analysis/compute_m1_m2_m3.py::match_pair_v4` |
| v3 kept for audit / fallback | `analysis/compute_m1_m2_m3.py::_match_pair_v3` |
| Crosstab (uses matcher_v4 + MAB official EM) | `analysis/compute_pool_acc_crosstab.py` |
| Crosstab output | `results/pool_acc_crosstab.md` |
| Audit script | `analysis/rigor_audit.py` |
| Audit report | `results/rigor_audit.md` |
| **Zep bi-temporal KU classifier** | `analysis/classify_zep_ku_resolution.py`（§3.4） |
| **Zep KU-resolution results** | `results/zep_ku_resolution_bitemporal.md` |
| This spec | `matcher_specification.md`(本檔) |

---

## §6 Change log

- **2026-07-07** — 新增 §3.4 跨方法 pool_state 不可比性 + Zep bi-temporal mediator;新增 `analysis/classify_zep_ku_resolution.py` + `results/zep_ku_resolution_bitemporal.md`。Zep has_pair KU 分類經 review 後改用 **handoff-verify + Other-Ambiguous 殘差桶**(修正初版只看「edge 有無 invalid_at」會把第三方 invalidate / matcher over-match 誤記為 backward):Additive-NoKU 長 context 主導 39→77→74%(保守下界)、Resolved-Correct acc 88–100%、Resolved-Backward 6k 30%(world-prior)。
- **2026-07-04** — matcher_v4 canonical;audit finds ours PP-OldOnly false-neg 100% under v3, drops to 40% under v4;剩餘 FN 記入 §3.1
- 2026-06-XX — matcher_v3(triple-based)取代 v2(SequenceMatcher);見 `analysis/compute_m1_m2_m3.py` docstring
- < 2026-06 — v1/v2 探索期,已 deprecated
