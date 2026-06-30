"""
generate_sh_512_report.py
=========================
生成 FC-SH chunk_size=512 的逐題詳細報告（CSV格式）

每題輸出欄位：
  qa_pair_id, question, correct_answer, model_output, exact_match
  conflict_type                     -- has_pair / no_conflict_pair
  new_fact_text, new_fact_seq       -- 新事實（GT）
  new_fact_retrieved, new_fact_rank, new_fact_ppr  -- 是否取到、在top-k的rank、PPR分
  old_fact_text, old_fact_seq       -- 舊事實（衝突對，若有）
  old_fact_retrieved, old_fact_rank, old_fact_ppr
  ppr_favors                        -- "new"(新事實PPR較高) / "old"(舊事實PPR較高) / "same_passage" / "no_pair"
  fail_reason                       -- 僅 fail case 有：older_fact / entity_confused / hallucination / no_conflict_pair_fail
  top_k_passages                    -- 10 個 passage 的摘要（標記哪裡含新/舊事實）
"""

import json
import re
import csv
import os
from pathlib import Path

# ── 路徑 ─────────────────────────────────────────────────────────────────────
BASE         = Path(__file__).parent.parent
ANALYSIS_JSON = BASE / "analysis/results/sh_512_mquake_analysis.json"
RETRIEVED_DIR = BASE / "outputs/rag_retrieved/Structure_rag_hippo_rag_v2_nv/k_10/factconsolidation_sh_6k/chunksize_512"
OUT_CSV      = BASE / "analysis/results/sh_512_detailed_report.csv"
OUT_TXT      = BASE / "analysis/results/sh_512_detailed_report.txt"

# ── 載入分析結果 ─────────────────────────────────────────────────────────────
with open(ANALYSIS_JSON, encoding="utf-8") as f:
    entries = json.load(f)

# ── 輔助：載入 passages ───────────────────────────────────────────────────────
def load_passages(query_id: int) -> list[str]:
    fpath = RETRIEVED_DIR / f"query_{query_id}_context_0.json"
    if not fpath.exists():
        return []
    with open(fpath, encoding="utf-8") as f:
        raw = json.load(f)
    parts = re.split(r'Passage \d+:\n', raw)
    return [p.strip() for p in parts if p.strip()]


def passage_summary(text: str, max_chars: int = 120) -> str:
    """取 passage 前幾個字並壓縮空白。"""
    s = re.sub(r'\s+', ' ', text).strip()
    if len(s) > max_chars:
        return s[:max_chars] + "..."
    return s


def mark_facts_in_passage(text: str, new_seq, old_seq) -> str:
    """
    在 passage 文字中標記新舊事實所在的句子。
    回傳含有 [NEW] / [OLD] 標記的段落摘要（整個文字，非截斷）。
    """
    result = text
    # 用序號精確定位
    if old_seq is not None:
        old_marker = f"{old_seq}."
        result = result.replace(old_marker + " ", f"[OLD]{old_marker} ")
    if new_seq is not None:
        new_marker = f"{new_seq}."
        result = result.replace(new_marker + " ", f"[NEW]{new_marker} ")
    return result


def determine_ppr_favors(e: dict) -> str:
    """判斷 PPR 分高低傾向。"""
    if e.get("conflict_type") != "has_pair":
        return "no_pair"
    gt_r  = e.get("gt_passage_rank")
    old_r = e.get("old_passage_rank")
    if gt_r is None or old_r is None:
        return "partial_retrieval"
    if gt_r == old_r:
        return "same_passage"
    # rank 值越小 = PPR 分越高
    if gt_r < old_r:
        return "new_higher_ppr"   # 新事實 PPR 較高 → 排在前面（不利）
    else:
        return "old_higher_ppr"   # 舊事實 PPR 較高 → 排在前面（對模型有利）


def fail_reason(e: dict) -> str:
    if e["exact_match"]:
        return ""
    et = e.get("error_type", "")
    ct = e.get("conflict_type", "")
    if ct == "no_conflict_pair":
        return "no_conflict_pair_fail"
    return et  # older_fact / entity_confused / hallucination


# ── 生成 CSV ─────────────────────────────────────────────────────────────────
fieldnames = [
    "qa_pair_id", "question", "correct_answer", "model_output", "exact_match",
    "conflict_type",
    "new_fact_seq", "new_fact_text",
    "new_fact_retrieved", "new_fact_rank", "new_fact_ppr",
    "old_fact_seq", "old_fact_text", "old_answer",
    "old_fact_retrieved", "old_fact_rank", "old_fact_ppr",
    "update_gap", "ppr_favors",
    "fail_reason",
    "p1_summary", "p2_summary", "p3_summary", "p4_summary", "p5_summary",
    "p6_summary", "p7_summary", "p8_summary", "p9_summary", "p10_summary",
]

rows = []
for e in entries:
    qid      = e.get("query_id", 0)
    passages = load_passages(qid)
    new_seq  = e.get("gt_seq")
    old_seq  = e.get("old_seq")

    # 為每個 passage 生成摘要（含 [NEW]/[OLD] 標記）
    p_summaries = {}
    for i, p in enumerate(passages, start=1):
        marked = mark_facts_in_passage(p, new_seq, old_seq)
        p_summaries[f"p{i}_summary"] = passage_summary(marked, max_chars=200)
    for i in range(len(passages) + 1, 11):
        p_summaries[f"p{i}_summary"] = ""

    row = {
        "qa_pair_id":      e.get("qa_pair_id", ""),
        "question":        e.get("question", ""),
        "correct_answer":  e.get("gt_answer", ""),
        "model_output":    e.get("model_output", ""),
        "exact_match":     e.get("exact_match", False),
        "conflict_type":   e.get("conflict_type", ""),

        "new_fact_seq":      new_seq if new_seq is not None else "",
        "new_fact_text":     e.get("gt_fact_text", ""),
        "new_fact_retrieved": e.get("gt_retrieved", False),
        "new_fact_rank":     e.get("gt_passage_rank", "") if e.get("gt_passage_rank") else "",
        "new_fact_ppr":      round(e["gt_ppr_score"], 6)  if e.get("gt_ppr_score")  else "",

        "old_fact_seq":      old_seq if old_seq is not None else "",
        "old_fact_text":     e.get("old_fact_text", ""),
        "old_answer":        e.get("old_answer", ""),
        "old_fact_retrieved": e.get("old_retrieved", False),
        "old_fact_rank":     e.get("old_passage_rank", "") if e.get("old_passage_rank") else "",
        "old_fact_ppr":      round(e["old_ppr_score"], 6) if e.get("old_ppr_score") else "",

        "update_gap":   e.get("update_gap", ""),
        "ppr_favors":   determine_ppr_favors(e),
        "fail_reason":  fail_reason(e),
        **p_summaries,
    }
    rows.append(row)

with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
    writer.writeheader()
    writer.writerows(rows)

print(f"✅ CSV 報告：{OUT_CSV}")

# ── 生成可讀文字報告 ──────────────────────────────────────────────────────────
lines = []
lines.append("=" * 70)
lines.append("FC-SH HippoRAG-v2 chunk_size=512 逐題詳細報告")
lines.append("=" * 70)

# 先輸出總覽統計
total = len(entries)
correct_n = sum(1 for e in entries if e["exact_match"])
fail_n    = total - correct_n

has_pair  = [e for e in entries if e.get("conflict_type") == "has_pair"]
no_pair   = [e for e in entries if e.get("conflict_type") == "no_conflict_pair"]

lines.append(f"\n總題數: {total}  正確: {correct_n}  錯誤: {fail_n}  Accuracy: {correct_n/total*100:.1f}%")
lines.append(f"has_pair: {len(has_pair)}  no_conflict_pair: {len(no_pair)}")

# Pass/Fail × has_pair/no_pair
hp_pass = sum(1 for e in has_pair if e["exact_match"])
hp_fail = len(has_pair) - hp_pass
np_pass = sum(1 for e in no_pair if e["exact_match"])
np_fail = len(no_pair) - np_pass
lines.append(f"\n{'子集':<25} {'正確':>6} {'錯誤':>6} {'Acc':>8}")
lines.append(f"{'─'*47}")
lines.append(f"{'has_pair (有衝突對)':<25} {hp_pass:>6} {hp_fail:>6} {hp_pass/len(has_pair)*100:>7.1f}%")
lines.append(f"{'no_conflict_pair (無衝突對)':<25} {np_pass:>6} {np_fail:>6} {np_pass/len(no_pair)*100:>7.1f}%")

# PPR favors 統計（has_pair，兩者都取到）
lines.append(f"\n{'─'*50}")
lines.append("PPR 分高低統計（has_pair，兩者都被取回）")
lines.append(f"{'─'*50}")
both_hp = [e for e in has_pair if e.get("gt_retrieved") and e.get("old_retrieved")]
pf_counter = {}
for e in both_hp:
    k = determine_ppr_favors(e)
    pf_counter[k] = pf_counter.get(k, 0) + 1

lines.append(f"  {'PPR情況':<25} {'全部':>5} {'Pass':>5} {'Fail':>5}")
lines.append(f"  {'─'*45}")
for k in ["new_higher_ppr", "old_higher_ppr", "same_passage"]:
    total_k = pf_counter.get(k, 0)
    pass_k  = sum(1 for e in both_hp if determine_ppr_favors(e) == k and e["exact_match"])
    fail_k  = total_k - pass_k
    label = {
        "new_higher_ppr": "新事實PPR較高（不利）",
        "old_higher_ppr": "舊事實PPR較高（有利）",
        "same_passage":   "同一個Passage"
    }.get(k, k)
    lines.append(f"  {label:<25} {total_k:>5} {pass_k:>5} {fail_k:>5}")

# 新事實 PPR 高但 fail 的具體解釋
new_high_fail = [e for e in both_hp if determine_ppr_favors(e) == "new_higher_ppr" and not e["exact_match"]]
lines.append(f"\n  ※ 新事實PPR較高且 fail 的 {len(new_high_fail)} 題：")
for e in new_high_fail:
    lines.append(f"     Q: {e['question'][:60]}")
    lines.append(f"        新事實rank={e['gt_passage_rank']} PPR={round(e['gt_ppr_score'],4)}")
    lines.append(f"        舊事實rank={e['old_passage_rank']} PPR={round(e['old_ppr_score'],4)}")
    lines.append(f"        model_output: {e['model_output']}  |  error: {e.get('error_type')}")
    lines.append("")

# ── 逐題詳細資料 ─────────────────────────────────────────────────────────────
lines.append("\n" + "=" * 70)
lines.append("逐題詳細資料（依 fail/pass 分組，再依 qa_pair_id 排序）")
lines.append("=" * 70)

def entry_block(e: dict, passages: list[str]) -> list[str]:
    new_seq = e.get("gt_seq")
    old_seq = e.get("old_seq")
    result_marker = "✓ PASS" if e["exact_match"] else "✗ FAIL"
    block = []
    block.append(f"\n{'─'*65}")
    block.append(f"[{result_marker}]  {e.get('qa_pair_id','')}  |  {e.get('conflict_type','')}")
    block.append(f"問題: {e.get('question','')}")
    block.append(f"正確答案: {e.get('gt_answer','')}   模型輸出: {e.get('model_output','')}")

    if not e["exact_match"]:
        block.append(f"★ 失敗原因: {fail_reason(e)}")

    block.append("")
    block.append(f"  【新事實（GT）】seq={new_seq}")
    block.append(f"  文字: {e.get('gt_fact_text','N/A')}")
    if e.get("gt_retrieved"):
        block.append(f"  → 已取回  Rank={e.get('gt_passage_rank')}  PPR={round(e['gt_ppr_score'],6)}")
    else:
        block.append(f"  → ✗ 未取回")

    if e.get("conflict_type") == "has_pair":
        block.append(f"\n  【舊事實（衝突對）】seq={old_seq}  update_gap={e.get('update_gap')}")
        block.append(f"  文字: {e.get('old_fact_text','N/A')}")
        if e.get("old_retrieved"):
            block.append(f"  → 已取回  Rank={e.get('old_passage_rank')}  PPR={round(e['old_ppr_score'],6)}")
        else:
            block.append(f"  → ✗ 未取回")
        block.append(f"\n  PPR 傾向: {determine_ppr_favors(e)}")
    else:
        block.append(f"\n  （無衝突對）")

    block.append("")
    block.append(f"  【Top-10 Retrieved Passages】")
    for i, p in enumerate(passages, start=1):
        marked = mark_facts_in_passage(p, new_seq, old_seq)
        short  = passage_summary(marked, max_chars=250)
        has_new = "[NEW]" in marked
        has_old = "[OLD]" in marked
        tag = ""
        if has_new and has_old: tag = " ← [NEW]+[OLD]"
        elif has_new: tag = " ← [NEW]"
        elif has_old: tag = " ← [OLD]"
        block.append(f"  P{i} (PPR={round(e['retrieval_scores'][i-1],5) if i <= len(e.get('retrieval_scores',[])) else '?'}){tag}:")
        block.append(f"    {short}")
    return block

# 先輸出 fail cases，再輸出 pass cases
for group_label, group_entries in [
    ("FAIL CASES", [e for e in entries if not e["exact_match"]]),
    ("PASS CASES", [e for e in entries if e["exact_match"]]),
]:
    lines.append(f"\n{'#'*70}")
    lines.append(f"## {group_label} ({len(group_entries)} 題)")
    lines.append(f"{'#'*70}")
    for e in sorted(group_entries, key=lambda x: x.get("qa_pair_id", "")):
        passages = load_passages(e.get("query_id", 0))
        lines.extend(entry_block(e, passages))

report_text = "\n".join(lines)
with open(OUT_TXT, "w", encoding="utf-8") as f:
    f.write(report_text)

print(f"✅ 文字報告：{OUT_TXT}")
print(f"\n{'-'*50}")
print(report_text[:3000])  # 預覽前 3000 字
