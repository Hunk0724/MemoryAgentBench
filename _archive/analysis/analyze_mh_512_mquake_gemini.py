"""
analyze_mh_512_mquake.py
========================
FC-MH 6k HippoRAG-v2 (chunk_size=512) 完整分析腳本

對每題每一跳，透過 MQuAKE-CF.json 精確定位：
  - GT 事實句（新版 cloze + answer + '.'）
  - 舊版衝突事實句（requested_rewrite target_true）
  - 各自在 top-10 中的 passage rank 和 PPR score

輸出：
  - analysis/results/hipporag_gemini/mh_512_gemini_mquake_analysis.json   （per-entry 詳細）
  - analysis/results/hipporag_gemini/mh_512_gemini_mquake_summary.txt     （統計摘要）
"""

import json, re, os
from pathlib import Path
from collections import Counter, defaultdict

# ── 路徑 ─────────────────────────────────────────────────────────────────────
BASE          = Path(__file__).parent.parent
MQUAKE_PATH   = Path("/home/yhchiang/MQuAKE/datasets/MQuAKE-CF.json")
CTX_FILE      = Path("/home/yhchiang/MemoryAgentBench/analysis/contexts/factconsolidation_6k_context.txt")
RESULTS_PATH  = BASE / "outputs/gemini-3.1-flash-lite-preview-hippo_rag_v2_nv/Conflict_Resolution/factconsolidation_mh_6k_unknown_in6000_size10_shots0_max_samplesunknown_k10_chunk512_results.json"
RETRIEVED_DIR = BASE / "outputs/rag_retrieved/Structure_rag_hippo_rag_v2_nv/k_10/factconsolidation_mh_6k/chunksize_512"
OUT_JSON      = BASE / "analysis/results/hipporag_gemini/mh_512_gemini_mquake_analysis.json"
OUT_TXT       = BASE / "analysis/results/hipporag_gemini/mh_512_gemini_mquake_summary.txt"

os.makedirs(OUT_JSON.parent, exist_ok=True)

# ── 載入資料 ─────────────────────────────────────────────────────────────────
print("載入 MQuAKE...")
with open(MQUAKE_PATH, encoding="utf-8") as f:
    mquake = json.load(f)

print("載入 context...")
with open(CTX_FILE, encoding="utf-8") as f:
    ctx_text = f.read()

print("載入 MH results...")
with open(RESULTS_PATH, encoding="utf-8") as f:
    results_data = json.load(f)

# ── context 結構 ──────────────────────────────────────────────────────────────
ctx_lines = [
    (int(m.group(1)), m.group(2).strip())
    for m in re.finditer(r'^\s*(\d+)\.\s+(.+)', ctx_text, re.MULTILINE)
]
TOTAL_FACTS  = len(ctx_lines)
ctx_by_lower = {t.lower(): n for n, t in ctx_lines}
ctx_by_seq   = {n: t for n, t in ctx_lines}
print(f"Context 共 {TOTAL_FACTS} 個事實句")

# ── MQuAKE MH 問題索引 ─────────────────────────────────────────────────────
# key: (頂層問句小寫, new_answer小寫) → case
mh_q_index: dict = {}
for c in mquake:
    a_l = c.get("new_answer", "").lower().strip()
    for q in c.get("questions", []):
        key = (q.strip().lower(), a_l)
        if key not in mh_q_index:
            mh_q_index[key] = c
    for alias in c.get("new_answer_alias", []):
        for q in c.get("questions", []):
            key2 = (q.strip().lower(), alias.lower().strip())
            if key2 not in mh_q_index:
                mh_q_index[key2] = c
print(f"MQuAKE MH index 共 {len(mh_q_index)} 個 key")

# ── 輔助函式 ──────────────────────────────────────────────────────────────────

def extract_question(query: str) -> str:
    m = re.search(r'Now Answer the Question:\s*(.+?)(?:\nAnswer:|$)', query, re.DOTALL)
    if not m:
        return ""
    return re.sub(r'Based on the provided Knowledge Pool,\s*', '',
                  m.group(1).strip(), flags=re.IGNORECASE).strip()


def get_hop_gt_seq(hop: dict):
    fact = hop["cloze"] + " " + hop["answer"] + "."
    return ctx_by_lower.get(fact.lower()), fact


def get_hop_old(hop: dict, rws: list, hop_idx: int):
    """回傳 (old_seq, old_fact_text, old_answer, method)"""
    cloze_lower = hop["cloze"].lower().strip()
    gt_n, _     = get_hop_gt_seq(hop)

    if hop_idx < len(rws):
        old_ans = rws[hop_idx].get("target_true", {}).get("str", "")
        if old_ans:
            old_fact = hop["cloze"] + " " + old_ans + "."
            n = ctx_by_lower.get(old_fact.lower())
            if n is not None:
                return n, old_fact, old_ans, "direct"

    candidates = [
        (n, t) for n, t in ctx_lines
        if t.lower().startswith(cloze_lower)
        and t.lower() != (hop["cloze"] + " " + hop["answer"] + ".").lower()
    ]
    if candidates:
        below = [(n, t) for n, t in candidates if gt_n is None or n < gt_n]
        best  = max(below, key=lambda x: x[0]) if below else min(candidates, key=lambda x: x[0])
        cloze_len = len(hop["cloze"]) + 1
        inferred  = best[1][cloze_len:].rstrip(".")
        return best[0], best[1], inferred, "cloze"

    return None, None, "", "none"


def load_passages(query_id: int) -> list[str]:
    fpath = RETRIEVED_DIR / f"query_{query_id}_context_0.json"
    if not fpath.exists():
        return []
    with open(fpath, encoding="utf-8") as f:
        raw = json.load(f)
    parts = re.split(r'Passage \d+:\n', raw)
    return [p.strip() for p in parts if p.strip()]


def find_seq_in_passages(seq_no: int, passages: list[str]):
    """用序號在 passages 中定位，回傳 (rank, offset)，rank 從 1 開始。"""
    prefix = f"{seq_no}. "
    for rank, p in enumerate(passages, 1):
        if prefix in p:
            return rank, p.find(prefix)
    return None, None


def normalize(s: str) -> str:
    return s.strip().rstrip(".,;:!?\"'").strip().lower()


def classify_error_mh(output, new_answer, old_final_answer, new_single_hops, single_hops, exact_match):
    """使用 exact_match 判斷 correct；fail 才細分。"""
    if exact_match:
        return "correct", None, None

    out_n     = normalize(output)
    old_f_n   = normalize(old_final_answer) if old_final_answer else None
    last      = len(new_single_hops) - 1

    # older_fact：整條舊鏈最終答案
    if old_f_n and (out_n == old_f_n or old_f_n in out_n or out_n in old_f_n):
        return "older_fact", None, None

    # intermediate_stop — 新版中間跳
    for k in range(last):
        hop_ans_n = normalize(new_single_hops[k]["answer"])
        if out_n == hop_ans_n or hop_ans_n in out_n or out_n in hop_ans_n:
            return "intermediate_stop", k, "new"

    # intermediate_stop — 舊版中間跳
    for k in range(len(single_hops) - 1):
        hop_ans_n = normalize(single_hops[k]["answer"])
        if out_n == hop_ans_n or hop_ans_n in out_n or out_n in hop_ans_n:
            return "intermediate_stop", k, "old"

    # entity_confused
    if out_n and any(out_n in t.lower() for _, t in ctx_lines):
        return "entity_confused", None, None

    return "hallucination", None, None


# ── 主流程 ────────────────────────────────────────────────────────────────────
print(f"\n分析 {len(results_data['data'])} 題 FC-MH...")

entries    = []
no_match   = []

for entry in results_data["data"]:
    qid       = entry.get("query_id", 0)
    qa_id     = entry.get("qa_pair_id", "")
    query     = entry.get("query", "")
    gt_ans    = entry.get("answer", "")
    output    = entry.get("output", "")
    scores    = entry.get("retrieval_scores", [])
    exact_m   = entry.get("exact_match", False)

    if isinstance(gt_ans, list):
        gt_ans = gt_ans[0] if gt_ans else ""

    question = extract_question(query)
    passages = load_passages(qid)

    # ── MQuAKE 對應 ──────────────────────────────────────────────────────────
    key  = (question.lower().strip(), gt_ans.lower().strip())
    case = mh_q_index.get(key)

    if case is None:
        no_match.append(qa_id)
        entries.append({
            "qa_pair_id": qa_id, "query_id": qid,
            "question": question, "gt_answer": gt_ans,
            "model_output": output, "exact_match": exact_m,
            "error_type": "no_mquake_match",
            "num_hops": None, "hops": [],
            "retrieval_scores": scores,
        })
        continue

    nsh    = case.get("new_single_hops", [])
    sh     = case.get("single_hops", [])
    rws    = case.get("requested_rewrite", [])
    n_hops = len(nsh)

    # ── 各跳詳細資訊 ─────────────────────────────────────────────────────────
    hop_records = []
    for k, hop in enumerate(nsh):
        gt_seq,  gt_fact  = get_hop_gt_seq(hop)
        old_seq, old_fact, old_ans, old_method = get_hop_old(hop, rws, k)

        # 在 passages 中定位
        gt_rank,  gt_off  = find_seq_in_passages(gt_seq,  passages) if gt_seq  is not None else (None, None)
        old_rank, old_off = find_seq_in_passages(old_seq, passages) if old_seq is not None else (None, None)

        gt_ppr  = scores[gt_rank  - 1] if gt_rank  is not None and gt_rank  <= len(scores) else None
        old_ppr = scores[old_rank - 1] if old_rank is not None and old_rank <= len(scores) else None

        conflict_type = "has_pair" if old_seq is not None else "no_conflict_pair"
        same_passage  = (gt_rank is not None and old_rank is not None and gt_rank == old_rank)

        hop_records.append({
            "hop_idx":      k,
            "hop_question": hop.get("question", ""),
            "gt_answer":    hop["answer"],
            "old_answer":   old_ans,
            "conflict_type": conflict_type,

            "gt_seq":       gt_seq,
            "gt_fact_text": gt_fact,
            "gt_retrieved": gt_rank is not None,
            "gt_rank":      gt_rank,
            "gt_ppr":       gt_ppr,

            "old_seq":      old_seq,
            "old_fact_text": old_fact,
            "old_retrieved": old_rank is not None,
            "old_rank":     old_rank,
            "old_ppr":      old_ppr,

            "same_passage": same_passage,
            "update_gap":   (gt_seq - old_seq) if gt_seq is not None and old_seq is not None else None,
        })

    # ── error type ───────────────────────────────────────────────────────────
    old_final = case.get("answer", "")
    error_type, int_hop, int_ver = classify_error_mh(
        output, gt_ans, old_final, nsh, sh, exact_m
    )

    # ── 衝突對總覽（判斷哪些跳有衝突、哪些 passage 是舊事實）────────────────
    has_pair_hops     = [h for h in hop_records if h["conflict_type"] == "has_pair"]
    all_hops_have_gt  = all(h["gt_retrieved"] for h in hop_records)
    any_hop_miss_gt   = any(not h["gt_retrieved"] for h in hop_records)
    old_passages_to_remove = sorted(set(
        h["old_rank"] for h in hop_records
        if h["conflict_type"] == "has_pair" and h["old_retrieved"]
        and (h["old_rank"] != h["gt_rank"])   # 只記錄不同 passage 的舊事實
    ))

    entries.append({
        "qa_pair_id":   qa_id,
        "query_id":     qid,
        "question":     question,
        "gt_answer":    gt_ans,
        "model_output": output,
        "exact_match":  exact_m,
        "case_id":      case["case_id"],
        "num_hops":     n_hops,
        "error_type":   error_type,
        "int_stop_hop": int_hop,
        "int_stop_ver": int_ver,
        "hops":         hop_records,
        "old_final_answer": old_final,
        "old_passages_to_remove": old_passages_to_remove,  # Oracle 實驗用
        "retrieval_scores": scores,
    })

# ── 儲存 JSON ─────────────────────────────────────────────────────────────────
with open(OUT_JSON, "w", encoding="utf-8") as f:
    json.dump(entries, f, ensure_ascii=False, indent=2)
print(f"\n✅ 詳細結果：{OUT_JSON}")

# ── 統計摘要 ──────────────────────────────────────────────────────────────────
valid   = [e for e in entries if e["error_type"] != "no_mquake_match"]
correct = [e for e in valid if e["exact_match"]]
fail    = [e for e in valid if not e["exact_match"]]

lines = []
lines.append("=" * 65)
lines.append("FC-MH 6k HippoRAG-v2 chunk_size=512 分析報告（MQuAKE精確對應）")
lines.append("=" * 65)
lines.append(f"\n總題數: {len(entries)}  有效: {len(valid)}  正確: {len(correct)}  錯誤: {len(fail)}")
lines.append(f"Accuracy: {len(correct)/len(valid)*100:.1f}%")
lines.append(f"No MQuAKE match: {len(no_match)} 題")

# 跳數分佈
lines.append(f"\n{'─'*45}")
lines.append("Hop 數分佈與各跳數 Accuracy")
lines.append(f"{'─'*45}")
hop_cnt = Counter(e["num_hops"] for e in valid)
for nh in sorted(hop_cnt):
    sub = [e for e in valid if e["num_hops"] == nh]
    acc = sum(1 for e in sub if e["exact_match"]) / len(sub) * 100
    lines.append(f"  {nh} 跳: {len(sub):>4} 題  Acc={acc:.1f}%")

# Error type 分佈
lines.append(f"\n{'─'*45}")
lines.append("Error type 分佈（全部有效題）")
lines.append(f"{'─'*45}")
for et, cnt in Counter(e["error_type"] for e in valid).most_common():
    lines.append(f"  {et:<22}: {cnt:>4} 題  ({cnt/len(valid)*100:.1f}%)")

lines.append(f"\n  Fail cases ({len(fail)} 題) error type:")
for et, cnt in Counter(e["error_type"] for e in fail).most_common():
    lines.append(f"    {et:<22}: {cnt:>4} 題  ({cnt/len(fail)*100:.1f}%)")

# intermediate_stop 細節
int_stop = [e for e in fail if e["error_type"] == "intermediate_stop"]
if int_stop:
    lines.append(f"\n  intermediate_stop 詳情（{len(int_stop)} 題）:")
    new_v = sum(1 for e in int_stop if e["int_stop_ver"] == "new")
    old_v = sum(1 for e in int_stop if e["int_stop_ver"] == "old")
    lines.append(f"    停在新版中間答案: {new_v} 題")
    lines.append(f"    停在舊版中間答案: {old_v} 題")
    for e in int_stop:
        lines.append(f"    [{e['int_stop_ver']}] hop{e['int_stop_hop']} | Q: {e['question'][:50]} | out={e['model_output']!r}")

# 各跳的衝突對 retrieval 分析
lines.append(f"\n{'─'*45}")
lines.append("各跳的事實 Retrieval 統計（has_pair 跳）")
lines.append(f"{'─'*45}")
# 蒐集所有跳的記錄
all_hop_records = []
for e in valid:
    for h in e["hops"]:
        h["exact_match"] = e["exact_match"]
        all_hop_records.append(h)

hp_hops = [h for h in all_hop_records if h["conflict_type"] == "has_pair"]
no_pair_hops = [h for h in all_hop_records if h["conflict_type"] == "no_conflict_pair"]
lines.append(f"  總跳次數: {len(all_hop_records)}  has_pair: {len(hp_hops)}  no_conflict_pair: {len(no_pair_hops)}")

gt_ret   = sum(1 for h in hp_hops if h["gt_retrieved"])
old_ret  = sum(1 for h in hp_hops if h["old_retrieved"])
both_ret = sum(1 for h in hp_hops if h["gt_retrieved"] and h["old_retrieved"])
lines.append(f"\n  has_pair 跳的 retrieval 情況:")
lines.append(f"    GT（新事實）取回: {gt_ret}/{len(hp_hops)}")
lines.append(f"    Old（舊事實）取回: {old_ret}/{len(hp_hops)}")
lines.append(f"    兩者都取回: {both_ret}/{len(hp_hops)}")
same_p = sum(1 for h in hp_hops if h["gt_retrieved"] and h["old_retrieved"] and h["same_passage"])
diff_p = sum(1 for h in hp_hops if h["gt_retrieved"] and h["old_retrieved"] and not h["same_passage"])
lines.append(f"    兩者都取回且同一 passage: {same_p}")
lines.append(f"    兩者都取回且不同 passage: {diff_p}")

# PPR 傾向（has_pair，兩者都取回）
both_hp_hops = [h for h in hp_hops if h["gt_retrieved"] and h["old_retrieved"] and not h["same_passage"]]
gt_higher  = sum(1 for h in both_hp_hops if h["gt_ppr"] and h["old_ppr"] and h["gt_ppr"] > h["old_ppr"])
old_higher = sum(1 for h in both_hp_hops if h["gt_ppr"] and h["old_ppr"] and h["old_ppr"] > h["gt_ppr"])
lines.append(f"\n  PPR 傾向（兩者取回且不同 passage，n={len(both_hp_hops)}）:")
lines.append(f"    新事實 PPR 較高（新在前）: {gt_higher}")
lines.append(f"    舊事實 PPR 較高（舊在前）: {old_higher}")

# 按題目 pass/fail 分
for label, em in [("pass(題)", True), ("fail(題)", False)]:
    sub_entries = [e for e in valid if e["exact_match"] == em]
    sub_hops = [h for e in sub_entries for h in e["hops"] if h["conflict_type"] == "has_pair"]
    both_sub = [h for h in sub_hops if h["gt_retrieved"] and h["old_retrieved"]]
    gt_h = sum(1 for h in both_sub if h["gt_ppr"] and h["old_ppr"] and h["gt_ppr"] > h["old_ppr"])
    old_h = sum(1 for h in both_sub if h["gt_ppr"] and h["old_ppr"] and h["old_ppr"] > h["gt_ppr"])
    lines.append(f"    [{label}] 有衝突對跳={len(sub_hops)}, 兩者取回={len(both_sub)}, 新PPR高={gt_h}, 舊PPR高={old_h}")

# Oracle 分析：每題需要移除的舊事實 passage 數量
lines.append(f"\n{'─'*45}")
lines.append("Oracle 實驗準備：舊事實 passage 移除統計")
lines.append(f"{'─'*45}")
for label, subset in [("全部", valid), ("pass", correct), ("fail", fail)]:
    no_old    = sum(1 for e in subset if len(e["old_passages_to_remove"]) == 0)
    has_old1  = sum(1 for e in subset if len(e["old_passages_to_remove"]) == 1)
    has_old2p = sum(1 for e in subset if len(e["old_passages_to_remove"]) >= 2)
    lines.append(f"  [{label}] 無需移除={no_old}, 移除1個={has_old1}, 移除2+個={has_old2p}")

# Hop-by-hop 衝突覆蓋（per question: 每一跳都有衝突 vs 部分有衝突）
lines.append(f"\n{'─'*45}")
lines.append("題目層級：各跳衝突對完整性")
lines.append(f"{'─'*45}")
for label, subset in [("全部", valid), ("pass", correct), ("fail", fail)]:
    all_hops_conflict  = sum(1 for e in subset if all(h["conflict_type"]=="has_pair" for h in e["hops"]))
    partial_conflict   = sum(1 for e in subset if any(h["conflict_type"]=="has_pair" for h in e["hops"])
                              and not all(h["conflict_type"]=="has_pair" for h in e["hops"]))
    no_conflict        = sum(1 for e in subset if all(h["conflict_type"]!="has_pair" for h in e["hops"]))
    lines.append(f"  [{label}] 全跳有衝突={all_hops_conflict}, 部分跳有衝突={partial_conflict}, 無衝突={no_conflict}")

summary_text = "\n".join(lines)
print(summary_text)

with open(OUT_TXT, "w", encoding="utf-8") as f:
    f.write(summary_text)
print(f"\n✅ 統計摘要：{OUT_TXT}")
