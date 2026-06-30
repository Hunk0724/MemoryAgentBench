# C-v2 — Verdict Bidirectional + B2 Chunk-Rebuild Filter

**Last updated**: 2026-05-24
**Status**: code 完成,等 smoke test → commit → GPU B 組 → GPU C 組
**取代**: 已 git rm 的 B3 inline-remove(FC-format-specific,不採用)

---

## §0. 兩個獨立改進,綁一起測

| 改進 | 屬性 | Flag |
|---|---|---|
| **(1) Verdict bidirectional** | DETECTION 層 — 修正 `chain_old_pids` 對稱性漏洞 | `enable_phase2_verdict_bidirectional` |
| **(2) B2 chunk_rebuild filter** | FILTER 層 — 移除 chain_old chunks 內的 old 行,保留 co-located 非 old props | `enable_phase2_filter_chunk_rebuild` |

兩個 flag 各自獨立,可以分別開關 → 跑**兩組** ablation 控變因:

| 組別 | bidir verdict | filter | 量測 |
|---|---|---|---|
| baseline | OFF(legacy)| rescue(現行)| B=31%(已知)|
| **B 組** | **ON** | rescue(現行)| EM 變化 + detection F1 提升 |
| **C 組** | **ON** | **chunk_rebuild** | EM 變化 + detection 累積 + filter 改進 |

---

## §1. 改進 (1):Verdict bidirectional

### Problem(verdict.py:311-333 的對稱性漏洞)

```python
# 現行:
focus_ts = tuple(focus.timestamp)
later = [pid for pid in contradicting_pids if propositions[pid].ts > focus_ts]

if later:
    # focus 比某些 contradicting 還舊 → focus = superseded
    return Verdict(status="superseded", superseder_id=latest_pid, ...)
else:
    # contradicting 都 ≤ focus_ts → focus 標 'current' low conf
    # ❌ 這些 earlier 的 contradicting pool prop 是 older twin,
    #    本來該標 chain_old,但完全沒記錄。
    return Verdict(status="current", confidence="low", ...)
```

### Fix

- **`Verdict.older_contradicting_pool_pids: List[str]`** 新欄位(default `None` → `[]`)
- `_make_verdict_from_contradicting` 額外收集 `earlier = [pid where ts < focus_ts]`,塞進該欄位
- `_v2_phase2_pipeline.chain_old_pids` 聚合改成雙向:
  ```python
  for focus_pid, v in verdicts.items():
      if v.confidence not in ("high", "medium"): continue
      if v.status == "superseded":
          chain_old_pids.add(focus_pid)
      if _verdict_bidir and v.older_contradicting_pool_pids:
          chain_old_pids.update(v.older_contradicting_pool_pids)
  ```

### 不變式

- Flag OFF → 等價現行行為(沒有 bidir 聚合)
- Flag ON 時:`Verdict` schema 多一個欄位,舊讀取者(dump tools)不會壞,但忽略新欄位
- Confidence gate 仍只接受 high/medium(不開放 low confidence 來壓 FP)

---

## §2. 改進 (2):B2 chunk_rebuild filter

### Algorithm(`methods/hipporag/phase2c/chunk_rebuild.py`)

```python
def rebuild_chunk_minus_old(original_chunk_text, pids_in_chunk,
                            chain_old_pid_set, prop_idx) -> str:
    olds = [p for p in pids_in_chunk if p in chain_old_pid_set]
    if not olds:
        return original_chunk_text            # 無 old → 原文不變(passage verbatim)
    remaining = [p for p in pids_in_chunk if p not in chain_old_pid_set]
    if not remaining:
        return ""                              # 全 old → 空 chunk
    remaining.sort(key=lambda p: prop_idx[p].timestamp[1])
    return " ".join(prop_idx[p].text for p in remaining)
```

### 整合點(`HippoRAG.py`)

| 位置 | 作用 |
|---|---|
| `__init__` | 加 `self._v2_chunk_content_override: Dict[query, Dict[chunk_id, text]] = {}` |
| `_v2_phase2_pipeline` | 對 affected chunks call `rebuild_chunk_minus_old`,塞 override |
| `retrieve()` | 組 `top_k_docs` 時,若該 chunk_id 在 override 內 → 用 rebuilt content;否則 → 原文 |

### 為何取代 B3?

| 維度 | B3(inline-remove,FC-format-specific)| **B2 chunk_rebuild(本檔)** |
|---|---|---|
| Drop 粒度 | fact line(regex 解析 chunk 文字) | chunk 但**位置不變**,內容 rebuild |
| 依賴 FC 格式 | ❌ 是(`\d+\.` 切 span) | **✅ 否**(用 proposition_index metadata) |
| 跨方法可比 | 不可 — 看穿了 FC corpus 格式 | **可** — Mem0 / Zep / Mem0g 也能套(只要它們有 prop-to-chunk mapping) |
| 句型 / 序號 | 保留 | 不保留 — chain_old 沒了沒衝突,不需 recency cue |
| 工程複雜度 | 中(regex + tiebreaker) | **小**(純 set 操作)|

### 不變式

- Flag OFF → 等價現行行為(`_v2_chunk_content_override` dict 不被讀)
- Flag ON 時:被 rebuild 的 chunk 位置不變,只是 content 換掉。**LLM context 整體大小可能略縮**(老 props 不見了)
- 與 rescue filter(`enable_phase2_filter_passages`)正交:
  - 兩個都 ON → rescue 先剪 chunks 出 top-K,剩下的 chunk_rebuild 改寫(雙重 filter)
  - C 組測試:rescue OFF + chunk_rebuild ON(乾淨對照)

---

## §3. Expected impact

| 維度 | B 組 | C 組 |
|---|---|---|
| **A1a detection F1**(內部 verdict 命中率)| ↑ 顯著(bidir 補上漏掉的另一向) | 同 B 組 |
| **A1b per-hop detection F1** | ↑ | 同 |
| **chain_old_pids 數量** | ↑(bidir 多收 older pool pids) | 同 |
| **EM** | 持平 ± 2pp 或微降(rescue 機制更多 leak) | **↑**(chunk_rebuild 把 old 真的拿掉,no rescue leak) |
| **filter precision**(被 drop 的 chunk 真含 chain_old 的比例)| 同現行 | 同 B 組 |
| **filter recall**(真 chain_old 被 drop 的比例)| ↑(bidir 偵測到更多)| ↑↑(bidir + no rescue)|

預期:**B 組 EM ≈ 31 ± 2pp**(因為 rescue 仍 leak);**C 組 EM > 31**(rescue 解放)。

---

## §4. 範圍 / Limitation

| | |
|---|---|
| Corpus 假設 | **無**(用 proposition_index 通用 metadata,不依賴 FC numbering)|
| 句型遺失 | 是(prop.text 是 OpenIE canonicalize 後)— 但 chain_old 既然移除,LLM 不需 recency,canonical 句型 OK |
| Detection 對 detection-only(無 filter)的影響 | bidir 只影響聚合;不改 LLM 判定/timestamp 比對 → 對 paper detection F1 來說是純公平改進 |

## §4.5 已知 prompt 端議題(本輪不動,記錄供後續改進)

**verdict_prompt.py 對「無衝突」case 的指引不夠明確**。output schema 寫:
```
{"contradicting_pool_indices": [<int>, ...], "reason": "<...>"}
```
**沒有明示**「焦點為記憶中唯一版本(無衝突) → 應該輸出空 list」。LLM 多半會根據 NOT-CONTRADICTING examples 自行推論 `[]`,但少數 case 可能:
1. 為「填滿」schema 強行 fill 不該 fill 的 pool index → FP
2. 輸出 `null` 或非法 JSON → 被 parser 接到後標 `uncertain low conf` → 被 confidence gate 過濾(safe-side)

**程式碼端是完整處理的**:
- `parse_verdict_response`(verdict_prompt.py:132-148):空 list 正確解析,parse_failed=False
- `_decide_verdict_mechanically`(verdict.py:303-310):empty contradicting → `status="current"`, `confidence="high"`, `older_contradicting_pool_pids=[]` → **chain_old_pids 不收**

**為何本輪不改 prompt**:
- 跟既有 ablation(A=17 / B=31)用同 prompt → 結果直接 cross-comparable
- 改 prompt 雖屬「retrieval-side LLM 的 instruction」(不是 inference wrapper),但仍會引入 prompt 變因

**之後要做的事(記為 future improvement E9-prompt-clarify)**:
1. 跑完 GPU step 8/9 後,從 `verdict_events.jsonl` 分析:
   - 多少比例的 verdict 是 `llm_contradicting_pids=[]`?
   - 那些 cases 對到 labels.json,真的是「無 GT 衝突對」嗎?(計算 FN 跟正確比例)
2. 若 FN 比例 > 預期 → 加 prompt 明示「空 list 是 expected output」,重跑驗證
3. 將「prompt 明示版」放在 paper appendix 跟 ablation,跟「未明示版」對照

---

## §5. 改動清單

| 檔案 | 改動 |
|---|---|
| `methods/hipporag/utils/config_utils.py` | rm `enable_phase2_filter_inline_remove`,新增 `enable_phase2_filter_chunk_rebuild` + `enable_phase2_verdict_bidirectional`(都 default False)|
| `methods/hipporag/phase2b/data_structures.py` | `Verdict` 加 `older_contradicting_pool_pids: list = None` |
| `methods/hipporag/phase2b/verdict.py` | `_make_verdict_from_contradicting`:三處 `return Verdict(...)` 都帶 `older_contradicting_pool_pids=earlier` |
| `methods/hipporag/HippoRAG.py` | 三處改:`__init__` override dict 註解、`_v2_phase2_pipeline` chain_old_pids 雙向聚合 + chunk_rebuild population、`retrieve()` override hook flag 名 |
| `methods/hipporag/phase2c/__init__.py` | re-export `rebuild_chunk_minus_old` |
| `methods/hipporag/phase2c/chunk_rebuild.py` | 新檔(~60 行)|
| **rm**:`docs/C_filter_redesign_design.md`, `phase2c/inline_remove.py`, `smoke_test_inline_remove.py` | B3 完全撤銷 |

---

## §6. Smoke test 計畫

1. **Verdict bidir 行為**:合成 verdicts dict,確認 bidir flag ON 時 chain_old_pids 包含 `superseded` focus + `older_contradicting_pool_pids`
2. **Chunk_rebuild 演算法**:
   - 合成 chunk + props → 移除 1 個 prop → 剩餘按 timestamp 順序組合
   - 邊界:空輸入、全 old → empty、無 old → unchanged
   - 真資料 chunk 0 跑一次:移除第 5 個 prop,確認 Thomas Kyd 在、Pedro 不在
3. **不變式**:flag OFF 時,所有上述新邏輯都不執行

---

## §7. Run plan(GPU steps 8/9,要 user OK)

| Step | 內容 | Flag setting |
|---|---|---|
| **8 (B 組)** | bidir verdict + rescue filter | `bidir=True`, `filter_passages=True`, `chunk_rebuild=False` |
| **9 (C 組)** | bidir verdict + chunk_rebuild | `bidir=True`, `filter_passages=False`, `chunk_rebuild=True` |

兩組各跑 100Q,cache 已熱,~3 分鐘 each。

---

## §8. 相關文件

- `docs/B_remove_hyperedge_design.md` — 前一步(已 verify EM=30/100 ✅)
- `docs/engineering_todos_v2.0.2.md` — 工程 todos
- `docs/PROVENANCE.md` — 需更新加 bidir + chunk_rebuild flag 紀錄
