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

## §3 已知 limitation(paper 需誠實說明)

### 3.1 Residual false-negative(64k audit)

在 v4 之後,仍有 method-dependent 剩餘 false-negative:

| Method | 64k v3 FN | 64k v4 FN | 剩餘原因 |
| :--- | :---: | :---: | :--- |
| ours (no_p5) | 5/5 (100%) | 2/2 | pool text 用 phase2 rephrase 過的縮寫版,gt_fact_text 完整字串不 substring 匹配 |
| mem0+P1 | 11/17 (65%) | 9/15 | mem0 抽取的 fact 可能 truncated / paraphrased,gt_fact_text 不匹配 |
| Zep (k=10) | 3/3 (100%) | 0/0 | Zep edges 保留完整原句,v4 substring 完全捕捉 |

**方向**:v5 可加更寬鬆 Layer-0(如 `gt_answer` 附近 ≤10 token 內 stem 高命中判為 match),但可能引入 false positive。**v4 目前是 rigor / recall 的合理平衡**。

### 3.2 對 weak-model regime 的 shape

Weak model(如 gemma3 1B/4B)抽 triple 可能 truncated 或 malformed → memory text 更難 match gt_fact_text 完整字串 → matcher 精度**必然下降**。

**paper 對策**:
- gpt-4o-mini 主分析:pool_state × Acc 可信,cross-tab 為主 supporting evidence
- weak-model regime:pool_state × Acc **僅供 reference**,paper 主敘事為 **E2E Acc + 錯誤模式 case study**

### 3.3 不能區分「pool 有 fact 但 answer LLM 忽略」vs「pool 缺 fact」的具體 cause

Matcher 只判「pool 有無 gt_new/gt_old」,不判「LLM 為何錯」。**Mode C(world-knowledge override)只能靠 case study 手動歸類**(見 [`results/case_studies_64k.md`](results/case_studies_64k.md))。

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
| This spec | `matcher_specification.md`(本檔) |

---

## §6 Change log

- **2026-07-04** — matcher_v4 canonical;audit finds ours PP-OldOnly false-neg 100% under v3, drops to 40% under v4;剩餘 FN 記入 §3.1
- 2026-06-XX — matcher_v3(triple-based)取代 v2(SequenceMatcher);見 `analysis/compute_m1_m2_m3.py` docstring
- < 2026-06 — v1/v2 探索期,已 deprecated
