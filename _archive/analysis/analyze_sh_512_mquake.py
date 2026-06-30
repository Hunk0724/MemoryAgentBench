"""
analyze_sh_512_mquake.py
========================
FC-SH 6k HippoRAG-v2 (chunk_size=512) 完整分析腳本
使用 MQuAKE-CF.json 精確定位每題的新舊事實句。

分析維度：
  1. Error type 分類：correct / older_fact / entity_confused / hallucination
  2. Conflict pair 存在性：has_pair / no_conflict_pair
  3. 新事實在哪個 Passage（1-10）→ 對應 PPR 排序
  4. 舊事實在哪個 Passage（1-10）→ 對應 PPR 排序
  5. 新舊事實的序號位置（gt_seq, old_seq）→ update_gap
  6. 各 Passage 的 PPR score
  7. Recency bias 分析：新事實 vs 舊事實在 prompt 中的相對位置

輸出：
  - analysis/results/sh_512_mquake_analysis.json  （per-entry 詳細資料）
  - analysis/results/sh_512_mquake_summary.txt    （統計摘要）
"""

import json
import re
import os
from pathlib import Path
from collections import Counter, defaultdict

# ── 路徑設定 ────────────────────────────────────────────────────────────────
BASE = Path(__file__).parent.parent
MQUAKE_PATH = Path("/home/yhchiang/MQuAKE/datasets/MQuAKE-CF.json")
CTX_FILE    = Path("/home/yhchiang/MemoryAgentBench_old/scripts/contexts/factconsolidation_sh_6k_context_0.txt")
RESULTS_PATH = BASE / "outputs/gpt-4o-mini-hippo_rag_v2_nv/Conflict_Resolution/factconsolidation_sh_6k_unknown_in6000_size10_shots0_max_samplesunknown_k10_chunk512_results.json"
RETRIEVED_DIR = BASE / "outputs/rag_retrieved/Structure_rag_hippo_rag_v2_nv/k_10/factconsolidation_sh_6k/chunksize_512"
OUT_JSON = BASE / "analysis/results/sh_512_mquake_analysis.json"
OUT_TXT  = BASE / "analysis/results/sh_512_mquake_summary.txt"

os.makedirs(OUT_JSON.parent, exist_ok=True)

# ── 載入資料 ─────────────────────────────────────────────────────────────────
print("載入 MQuAKE...")
with open(MQUAKE_PATH, encoding="utf-8") as f:
    mquake = json.load(f)

print("載入 context...")
with open(CTX_FILE, encoding="utf-8") as f:
    ctx_text = f.read()

print("載入 results...")
with open(RESULTS_PATH, encoding="utf-8") as f:
    results_data = json.load(f)

# ── 建立 context 查詢結構 ─────────────────────────────────────────────────────
ctx_lines = [
    (int(m.group(1)), m.group(2).strip())
    for m in re.finditer(r'^\s*(\d+)\.\s+(.+)', ctx_text, re.MULTILINE)
]
TOTAL_FACTS = len(ctx_lines)
ctx_by_lower = {t.lower(): n for n, t in ctx_lines}
ctx_by_seq   = {n: t for n, t in ctx_lines}
print(f"Context 共 {TOTAL_FACTS} 個事實句")

# ── 建立 MQuAKE SH hop 索引 ───────────────────────────────────────────────────
# key: (問句小寫, 新版答案小寫) → (case, hop_idx)
sh_hop_index = {}
for c in mquake:
    for i, hop in enumerate(c.get("new_single_hops", [])):
        key = (hop["question"].strip().lower(), hop["answer"].strip().lower())
        if key not in sh_hop_index:
            sh_hop_index[key] = (c, i)

print(f"MQuAKE index 共 {len(sh_hop_index)} 個 SH hop key")

# ── 輔助函式 ─────────────────────────────────────────────────────────────────

def extract_question(query: str) -> str:
    """從完整 query 中提取實際問句。"""
    m = re.search(r'Now Answer the Question:\s*(.+?)(?:\nAnswer:|$)', query, re.DOTALL)
    if not m:
        return ""
    return re.sub(
        r'Based on the provided Knowledge Pool,\s*', '',
        m.group(1).strip(), flags=re.IGNORECASE
    ).strip()


def find_gt_seq(case: dict, hop_idx: int):
    """用 cloze + new_answer + '.' 精確找 GT 事實序號。"""
    hop  = case["new_single_hops"][hop_idx]
    fact = hop["cloze"] + " " + hop["answer"] + "."
    return ctx_by_lower.get(fact.lower()), fact


def find_old_seq(case: dict, hop_idx: int):
    """
    找舊版（衝突對）事實序號與文字。
    優先用 requested_rewrite[hop_idx].target_true.str 精確匹配，
    若找不到再用 cloze 搜尋。
    """
    hop  = case["new_single_hops"][hop_idx]
    rws  = case.get("requested_rewrite", [])
    cloze_lower = hop["cloze"].lower().strip()
    old_answer  = ""

    # 方法一：requested_rewrite 直接查
    if hop_idx < len(rws):
        old_answer = rws[hop_idx].get("target_true", {}).get("str", "")
        if old_answer:
            old_fact = hop["cloze"] + " " + old_answer + "."
            n = ctx_by_lower.get(old_fact.lower())
            if n is not None:
                return n, old_fact, old_answer, "direct"

    # 方法二：context 中搜尋同 cloze、不同答案的句子
    gt_n, _ = find_gt_seq(case, hop_idx)
    candidates = [
        (n, t) for n, t in ctx_lines
        if t.lower().startswith(cloze_lower)
        and t.lower() != (hop["cloze"] + " " + hop["answer"] + ".").lower()
    ]
    if candidates:
        below_gt = [(n, t) for n, t in candidates if gt_n is None or n < gt_n]
        if below_gt:
            best_n, best_t = max(below_gt, key=lambda x: x[0])
        else:
            best_n, best_t = min(candidates, key=lambda x: x[0])
        # 從句子反查舊版答案
        cloze_len = len(hop["cloze"]) + 1
        inferred_old = best_t[cloze_len:].rstrip(".")
        return best_n, best_t, inferred_old, "cloze"

    return None, None, old_answer, "none"


def load_passages(query_id: int) -> list[str]:
    """
    載入 query_id 對應的 retrieved passages。
    回傳 list of str，index 0 = Passage 1 (PPR rank 1, highest score)。
    """
    fpath = RETRIEVED_DIR / f"query_{query_id}_context_0.json"
    if not fpath.exists():
        return []
    with open(fpath, encoding="utf-8") as f:
        raw = json.load(f)
    # raw is a string: "Passage 1:\n...\n\nPassage 2:\n...\n..."
    parts = re.split(r'Passage \d+:\n', raw)
    return [p.strip() for p in parts if p.strip()]


def find_fact_in_passages(fact_text: str, passages: list[str]) -> tuple[int | None, int | None]:
    """
    在 passages 中搜尋包含 fact_text 的 passage。
    回傳 (passage_rank, char_offset_in_passage)，passage_rank 從 1 開始。
    若未找到回傳 (None, None)。
    使用完整 fact_text 做 substring search（忽略大小寫）。
    """
    fact_lower = fact_text.lower().strip()
    for rank, passage in enumerate(passages, start=1):
        if fact_lower in passage.lower():
            offset = passage.lower().find(fact_lower)
            return rank, offset
    return None, None


def find_fact_in_passages_numbered(seq_no: int, passages: list[str]) -> tuple[int | None, int | None]:
    """
    用序號 (e.g. '189. ') 定位事實句在哪個 passage。
    比 substring 更精確，避免誤匹配。
    """
    fact_prefix = f"{seq_no}."
    for rank, passage in enumerate(passages, start=1):
        # 找 "189. some text"
        idx = passage.find(fact_prefix + " ")
        if idx == -1:
            # 也嘗試段落開頭
            idx = passage.find(fact_prefix)
        if idx != -1:
            return rank, idx
    return None, None


def normalize(s: str) -> str:
    """去除首尾空白與標點，轉小寫。"""
    return s.strip().rstrip(".,;:!?\"'").strip().lower()


def classify_error(output: str, new_answer: str, old_answer: str | None, gt_seq: int | None) -> tuple[str, list[int]]:
    """
    分類 error type。
    使用 normalize() 做比較，避免句尾標點造成誤判。
    回傳 (error_type, entity_confused_seqs)
    """
    out_n = normalize(output)
    new_n = normalize(new_answer)
    old_n = normalize(old_answer) if old_answer else None

    if out_n == new_n:
        return "correct", []

    # older_fact：模型輸出 = 舊版答案（exact 或 substring）
    if old_n and (out_n == old_n or old_n in out_n or out_n in old_n):
        return "older_fact", []

    # entity_confused: output 出現在 context 的其他句子中（substring）
    if out_n:
        matched_seqs = [
            n for n, t in ctx_lines
            if out_n in t.lower() and n != gt_seq
        ]
        if matched_seqs:
            return "entity_confused", matched_seqs

    return "hallucination", []


# ── 主流程 ───────────────────────────────────────────────────────────────────
print(f"\n分析 {len(results_data['data'])} 題...")

entries = []
stats = defaultdict(int)
no_mquake_match = []

for entry in results_data["data"]:
    qid      = entry.get("query_id", 0)
    qa_id    = entry.get("qa_pair_id", "")
    query    = entry.get("query", "")
    gt_ans   = entry.get("answer", "")
    output   = entry.get("output", "")
    scores   = entry.get("retrieval_scores", [])  # PPR scores, rank 1~10 in order
    exact_m  = entry.get("exact_match", False)

    if isinstance(gt_ans, list):
        gt_ans = gt_ans[0] if gt_ans else ""

    question = extract_question(query)

    # 載入 retrieved passages
    passages = load_passages(qid)

    # ── MQuAKE 對應 ─────────────────────────────────────────────────────────
    key = (question.lower().strip(), gt_ans.lower().strip())
    match = sh_hop_index.get(key)

    if match is None:
        stats["no_mquake_match"] += 1
        no_mquake_match.append(qa_id)
        entries.append({
            "qa_pair_id": qa_id, "query_id": qid,
            "question": question, "gt_answer": gt_ans,
            "model_output": output, "exact_match": exact_m,
            "conflict_type": "no_mquake_match", "error_type": "no_mquake_match",
        })
        continue

    case, hop_idx = match

    # ── 找 GT 事實 ──────────────────────────────────────────────────────────
    gt_seq, gt_fact_text = find_gt_seq(case, hop_idx)
    gt_relative_pos = round(gt_seq / TOTAL_FACTS, 4) if gt_seq is not None else None

    # ── 找舊版事實 ──────────────────────────────────────────────────────────
    old_seq, old_fact_text, old_answer, old_method = find_old_seq(case, hop_idx)
    conflict_type = "has_pair" if old_seq is not None else "no_conflict_pair"
    update_gap = (gt_seq - old_seq) if (gt_seq is not None and old_seq is not None) else None

    # ── 在 passages 中定位新舊事實 ──────────────────────────────────────────
    # 用序號定位（最精確）
    gt_passage_rank, gt_offset_in_passage = (
        find_fact_in_passages_numbered(gt_seq, passages)
        if gt_seq is not None else (None, None)
    )
    old_passage_rank, old_offset_in_passage = (
        find_fact_in_passages_numbered(old_seq, passages)
        if old_seq is not None else (None, None)
    )

    # 若序號法找不到，退回 substring 法
    if gt_passage_rank is None and gt_fact_text:
        gt_passage_rank, gt_offset_in_passage = find_fact_in_passages(gt_fact_text, passages)
    if old_passage_rank is None and old_fact_text:
        old_passage_rank, old_offset_in_passage = find_fact_in_passages(old_fact_text, passages)

    # ── retrieval 相關衍生資料 ───────────────────────────────────────────────
    gt_ppr_score  = scores[gt_passage_rank - 1]  if gt_passage_rank  is not None and gt_passage_rank  <= len(scores) else None
    old_ppr_score = scores[old_passage_rank - 1] if old_passage_rank is not None and old_passage_rank <= len(scores) else None

    # 新事實是否有在 top-k
    gt_retrieved  = gt_passage_rank  is not None
    old_retrieved = old_passage_rank is not None

    # Recency bias：PPR rank 越高（值越小）= 越前面，LLM recency bias 偏後
    # gt_passage_rank < old_passage_rank → gt 在前（先出現），LLM recency bias 不利新事實
    # gt_passage_rank > old_passage_rank → gt 在後（靠近問題），有 recency bias 優勢
    if gt_passage_rank is not None and old_passage_rank is not None:
        recency_favors_new = (gt_passage_rank > old_passage_rank)  # gt 排後面 → 有優勢
        position_diff = gt_passage_rank - old_passage_rank  # 正 = gt 靠後（有利），負 = gt 靠前（不利）
    else:
        recency_favors_new = None
        position_diff = None

    # ── Error type 分類 ──────────────────────────────────────────────────────
    # 以 results.json 的 exact_match 為準（substring match / alias match）
    # classify_error 只用於 fail cases 判斷失敗原因
    if exact_m:
        error_type, ec_seqs = "correct", []
    else:
        error_type, ec_seqs = classify_error(output, gt_ans, old_answer, gt_seq)
    stats[error_type] += 1

    # ── 建立 record ──────────────────────────────────────────────────────────
    record = {
        "qa_pair_id":       qa_id,
        "query_id":         qid,
        "question":         question,
        "gt_answer":        gt_ans,
        "model_output":     output,
        "exact_match":      exact_m,

        # MQuAKE 資訊
        "case_id":          case["case_id"],
        "hop_idx":          hop_idx,

        # 事實位置
        "gt_seq":           gt_seq,
        "gt_fact_text":     gt_fact_text,
        "gt_relative_pos":  gt_relative_pos,
        "old_seq":          old_seq,
        "old_fact_text":    old_fact_text,
        "old_answer":       old_answer,
        "old_method":       old_method,
        "conflict_type":    conflict_type,
        "update_gap":       update_gap,

        # Retrieval 結果
        "gt_retrieved":          gt_retrieved,
        "gt_passage_rank":       gt_passage_rank,   # 1=PPR最高, 10=PPR最低
        "gt_ppr_score":          gt_ppr_score,
        "old_retrieved":         old_retrieved,
        "old_passage_rank":      old_passage_rank,
        "old_ppr_score":         old_ppr_score,

        # Recency bias
        "recency_favors_new":    recency_favors_new,
        "position_diff":         position_diff,      # gt_rank - old_rank: 正=gt靠後有利

        # Error type
        "error_type":            error_type,
        "entity_confused_seqs":  ec_seqs if ec_seqs else None,

        # PPR scores (all 10)
        "retrieval_scores":      scores,
    }
    entries.append(record)

# ── 儲存 JSON ────────────────────────────────────────────────────────────────
with open(OUT_JSON, "w", encoding="utf-8") as f:
    json.dump(entries, f, ensure_ascii=False, indent=2)
print(f"\n✅ 詳細結果儲存至 {OUT_JSON}")

# ── 統計摘要 ─────────────────────────────────────────────────────────────────
total = len(entries)
valid = [e for e in entries if e.get("conflict_type") != "no_mquake_match"]
correct_entries = [e for e in valid if e["exact_match"]]
fail_entries    = [e for e in valid if not e["exact_match"]]

lines = []
lines.append("=" * 65)
lines.append(f"FC-SH 6k HippoRAG-v2 chunk_size=512 分析報告（MQuAKE精確對應）")
lines.append("=" * 65)
lines.append(f"\n總題數：{total}  |  有效（MQuAKE對應成功）：{len(valid)}")
lines.append(f"正確：{len(correct_entries)}  |  錯誤：{len(fail_entries)}")
acc = len(correct_entries) / len(valid) * 100 if valid else 0
lines.append(f"Accuracy：{acc:.1f}%")

lines.append(f"\n{'─'*40}")
lines.append("Error type 分佈（全部有效題）")
lines.append(f"{'─'*40}")
et_counter = Counter(e["error_type"] for e in valid)
for et, cnt in et_counter.most_common():
    pct = cnt / len(valid) * 100
    lines.append(f"  {et:<22}: {cnt:>3} 題  ({pct:.1f}%)")

lines.append(f"\n{'─'*40}")
lines.append("Conflict type 分佈")
lines.append(f"{'─'*40}")
ct_counter = Counter(e["conflict_type"] for e in valid)
for ct, cnt in ct_counter.most_common():
    lines.append(f"  {ct:<22}: {cnt:>3} 題")

# Fail cases 分析
has_pair_fail = [e for e in fail_entries if e.get("conflict_type") == "has_pair"]
lines.append(f"\n{'─'*40}")
lines.append(f"Fail cases 詳細分析（has_pair {len(has_pair_fail)} 題）")
lines.append(f"{'─'*40}")

lines.append(f"\n[1] Error type 分佈（fail, has_pair）")
fail_et = Counter(e["error_type"] for e in has_pair_fail)
for et, cnt in fail_et.most_common():
    pct = cnt / len(has_pair_fail) * 100 if has_pair_fail else 0
    lines.append(f"  {et:<22}: {cnt:>3} 題  ({pct:.1f}%)")

lines.append(f"\n[2] 新舊事實的 retrieval 情況（fail, has_pair）")
gt_ret_fail  = sum(1 for e in has_pair_fail if e["gt_retrieved"])
old_ret_fail = sum(1 for e in has_pair_fail if e["old_retrieved"])
both_ret_fail = sum(1 for e in has_pair_fail if e["gt_retrieved"] and e["old_retrieved"])
lines.append(f"  GT（新事實）被取回     : {gt_ret_fail}/{len(has_pair_fail)}")
lines.append(f"  Old（舊事實）被取回    : {old_ret_fail}/{len(has_pair_fail)}")
lines.append(f"  兩者都被取回          : {both_ret_fail}/{len(has_pair_fail)}")

# Pass cases 對比
has_pair_pass = [e for e in correct_entries if e.get("conflict_type") == "has_pair"]
lines.append(f"\n[3] 新舊事實的 retrieval 情況（pass, has_pair）對比")
gt_ret_pass  = sum(1 for e in has_pair_pass if e["gt_retrieved"])
old_ret_pass = sum(1 for e in has_pair_pass if e["old_retrieved"])
both_ret_pass = sum(1 for e in has_pair_pass if e["gt_retrieved"] and e["old_retrieved"])
lines.append(f"  GT（新事實）被取回     : {gt_ret_pass}/{len(has_pair_pass)}")
lines.append(f"  Old（舊事實）被取回    : {old_ret_pass}/{len(has_pair_pass)}")
lines.append(f"  兩者都被取回          : {both_ret_pass}/{len(has_pair_pass)}")

lines.append(f"\n[4] Recency bias 分析（has_pair，兩者都被取回）")

def recency_analysis(subset_label, subset):
    both = [e for e in subset if e["gt_retrieved"] and e["old_retrieved"] and e["position_diff"] is not None]
    favors_new  = sum(1 for e in both if e["recency_favors_new"])  # gt rank > old rank（gt靠後有利）
    favors_old  = sum(1 for e in both if not e["recency_favors_new"])
    avg_pos_diff = sum(e["position_diff"] for e in both) / len(both) if both else 0
    return [
        f"  [{subset_label}] 兩者都取回共 {len(both)} 題",
        f"    GT 靠後（有利 recency）: {favors_new} 題  |  GT 靠前（不利）: {favors_old} 題",
        f"    平均 position_diff (gt_rank - old_rank): {avg_pos_diff:.2f}",
    ]

lines.extend(recency_analysis("pass, has_pair", has_pair_pass))
lines.extend(recency_analysis("fail, has_pair", has_pair_fail))

lines.append(f"\n[5] Fail cases 中 GT passage rank 分佈（新事實在第幾個 passage）")
gt_ranks_fail = [e["gt_passage_rank"] for e in has_pair_fail if e["gt_passage_rank"] is not None]
rank_counter_fail = Counter(gt_ranks_fail)
for rank in range(1, 11):
    cnt = rank_counter_fail.get(rank, 0)
    lines.append(f"  Rank {rank:>2}: {cnt:>3} 題")

lines.append(f"\n[6] Pass cases 中 GT passage rank 分佈（新事實在第幾個 passage）")
gt_ranks_pass = [e["gt_passage_rank"] for e in has_pair_pass if e["gt_passage_rank"] is not None]
rank_counter_pass = Counter(gt_ranks_pass)
for rank in range(1, 11):
    cnt = rank_counter_pass.get(rank, 0)
    lines.append(f"  Rank {rank:>2}: {cnt:>3} 題")

lines.append(f"\n[7] Update gap 統計（has_pair fail cases，gt_seq - old_seq）")
gap_vals = [e["update_gap"] for e in has_pair_fail if e["update_gap"] is not None]
if gap_vals:
    lines.append(f"  筆數：{len(gap_vals)}")
    lines.append(f"  平均：{sum(gap_vals)/len(gap_vals):.1f}")
    lines.append(f"  最小：{min(gap_vals)}  最大：{max(gap_vals)}")
    # 分佈
    bins = defaultdict(int)
    for g in gap_vals:
        if g <= 10: bins["1-10"] += 1
        elif g <= 50: bins["11-50"] += 1
        elif g <= 100: bins["51-100"] += 1
        else: bins["101+"] += 1
    for label in ["1-10", "11-50", "51-100", "101+"]:
        lines.append(f"    gap {label:<8}: {bins[label]} 題")

lines.append(f"\n[8-0] PPR score 不均衡分析（old_ppr / gt_ppr 比值）")
lines.append(f"  （比值越高 = 舊事實比新事實有更高的 PPR 分，模型可能更注意舊事實）")
for subset_label, subset in [("pass, has_pair", has_pair_pass), ("fail, has_pair", has_pair_fail)]:
    ratio_vals = []
    for e in subset:
        gt_s  = e.get("gt_ppr_score")
        old_s = e.get("old_ppr_score")
        if gt_s and old_s and gt_s > 0:
            ratio_vals.append(old_s / gt_s)
    if ratio_vals:
        avg_r = sum(ratio_vals) / len(ratio_vals)
        max_r = max(ratio_vals)
        # 比值 > 2 (old score 超過 gt 兩倍)
        dominant = sum(1 for r in ratio_vals if r > 2.0)
        lines.append(f"  [{subset_label}] n={len(ratio_vals)}, avg ratio={avg_r:.2f}, max={max_r:.2f}, ratio>2 count={dominant}")

lines.append(f"\n[8] GT 相對位置（gt_seq / 455）分析")
for label, subset, em in [("pass, has_pair", has_pair_pass, True), ("fail, has_pair", has_pair_fail, False)]:
    pos_vals = [e["gt_relative_pos"] for e in subset if e["gt_relative_pos"] is not None]
    if pos_vals:
        avg = sum(pos_vals) / len(pos_vals)
        lines.append(f"  [{label}] avg relative pos = {avg:.3f}  (n={len(pos_vals)})")

lines.append(f"\n{'─'*40}")
lines.append("No MQuAKE match cases")
lines.append(f"{'─'*40}")
lines.append(f"  共 {len(no_mquake_match)} 題：{no_mquake_match}")

lines.append("")
summary_text = "\n".join(lines)
print(summary_text)

with open(OUT_TXT, "w", encoding="utf-8") as f:
    f.write(summary_text)
print(f"\n✅ 統計摘要儲存至 {OUT_TXT}")
