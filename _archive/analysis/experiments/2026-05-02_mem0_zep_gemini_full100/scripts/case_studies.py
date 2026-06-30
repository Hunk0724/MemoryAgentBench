"""
Concrete case studies — 對照 Mem0 vs Zep 在具體 FC 衝突 case 上的處理。

For each picked qid, dump:
  - GT (question, gt_answer, has_pair老/新事實)
  - Mem0 history.db UPDATE event(s) for this pair (from before/after of the run)
  - Mem0 retrieved memories (top-5 from saved results)
  - Mem0 answer & EM
  - Zep retrieved context preview & answer & EM

Outputs:
  results/case_studies.md
"""

import json
import sqlite3
from pathlib import Path

BASE = Path("/home/yhchiang/MemoryAgentBench")
RESULTS = BASE / "analysis/experiments/2026-05-02_mem0_zep_gemini_full100/results"
HISTORY_DB = Path("/home/yhchiang/.mem0/history.db")
SH_GT = BASE / "analysis/results/sh_512_mquake_analysis.json"
MH_GT = BASE / "analysis/results/mh_512_mquake_analysis.json"

SINCE = "2026-05-02T07:00:00"


def normalize(s):
    if s is None: return ""
    return str(s).strip().rstrip(".,;:!?\"'").strip().lower()


def text_contains(haystack, needle):
    h = normalize(haystack); n = normalize(needle)
    if not h or not n: return False
    for art in ("the ", "a ", "an "):
        if n.startswith(art): n = n[len(art):]
        if h.startswith(art): h = h[len(art):]
    return n in h or h in n


def load_mem0_events():
    conn = sqlite3.connect(HISTORY_DB)
    cur = conn.cursor()
    rows = cur.execute(
        "SELECT id, memory_id, old_memory, new_memory, event, created_at FROM history "
        "WHERE event IN ('ADD','UPDATE','DELETE') AND created_at >= ?",
        (SINCE,)
    ).fetchall()
    return [{"id": r[0], "mem_id": r[1], "old": r[2], "new": r[3], "event": r[4], "at": r[5]} for r in rows]


def find_relevant_events(events, gt_old, gt_new):
    """Return all events touching either gt_old or gt_new (any direction)."""
    out = []
    for e in events:
        old_str = e["old"] or ""
        new_str = e["new"] or ""
        if (text_contains(old_str, gt_old) or text_contains(new_str, gt_old) or
            text_contains(old_str, gt_new) or text_contains(new_str, gt_new)):
            out.append(e)
    return out


def make_case(qid, task, mem0_results, zep_results, mem0_events, mh_gt=None, sh_gt=None):
    """Pull data for one qid into a case study dict."""
    if task == "MH":
        q_gt = next((q for q in mh_gt if q["query_id"] == qid), None)
    else:
        q_gt = next((q for q in sh_gt if q["query_id"] == qid), None)
    if not q_gt:
        return None

    mem0_r = next((r for r in mem0_results if r["query_id"] == qid), None)
    zep_r = next((r for r in zep_results if r["query_id"] == qid), None)

    case = {
        "qid": qid,
        "task": task,
        "question": q_gt.get("question"),
        "gt_answer": q_gt.get("gt_answer"),
        "num_hops": q_gt.get("num_hops"),
        "chain_pairs": [],
        "mem0_events": [],
        "mem0_retrieved": mem0_r.get("retrieved_memories_preview", []) if mem0_r else [],
        "mem0_answer": mem0_r.get("pred_answer") if mem0_r else None,
        "mem0_em": mem0_r.get("exact_match") if mem0_r else None,
        "zep_retrieved": zep_r.get("retrieved_context_preview") if zep_r else "",
        "zep_n_edges": zep_r.get("n_edges") if zep_r else 0,
        "zep_n_nodes": zep_r.get("n_nodes") if zep_r else 0,
        "zep_n_episodes": zep_r.get("n_episodes") if zep_r else 0,
        "zep_answer": zep_r.get("pred_answer") if zep_r else None,
        "zep_em": zep_r.get("exact_match") if zep_r else None,
    }

    # Collect chain pairs
    if task == "MH":
        for h in q_gt.get("hops", []):
            if h.get("conflict_type") == "has_pair":
                old_t = h.get("old_fact_text", "")
                new_t = h.get("gt_fact_text", "")
                pair = {
                    "hop_idx": h.get("hop_idx"),
                    "old": old_t,
                    "new": new_t,
                    "old_seq": h.get("old_seq"),
                    "new_seq": h.get("gt_seq"),
                }
                case["chain_pairs"].append(pair)
                # Find Mem0 events for this pair
                rel_events = find_relevant_events(mem0_events, old_t, new_t)
                for e in rel_events:
                    e["__for_hop"] = h.get("hop_idx")
                    case["mem0_events"].append(e)
    else:
        if q_gt.get("conflict_type") == "has_pair":
            old_t = q_gt.get("old_fact_text", "")
            new_t = q_gt.get("gt_fact_text", "")
            case["chain_pairs"].append({
                "old": old_t, "new": new_t,
                "old_seq": q_gt.get("old_seq"),
                "new_seq": q_gt.get("gt_seq"),
            })
            case["mem0_events"] = find_relevant_events(mem0_events, old_t, new_t)

    return case


def render_case(case):
    """Render a single case as markdown."""
    md = []
    md.append(f"### {case['task']} qid={case['qid']}")
    md.append(f"\n**Question**: {case['question']}\n")
    md.append(f"**Ground truth answer**: `{case['gt_answer']}`")
    if case.get("num_hops"):
        md.append(f"**num_hops**: {case['num_hops']}")
    md.append("")

    # GT chain pairs
    md.append(f"#### Ground-truth has_pair chain ({len(case['chain_pairs'])} pairs):\n")
    if not case["chain_pairs"]:
        md.append("(no has_pair conflict in this question)\n")
    else:
        for p in case["chain_pairs"]:
            hop_str = f"hop {p['hop_idx']}: " if "hop_idx" in p else ""
            md.append(f"- {hop_str}old (seq {p.get('old_seq')}): `{p['old']}`")
            md.append(f"  → new (seq {p.get('new_seq')}): `{p['new']}`")
        md.append("")

    # Mem0 events
    md.append("#### Mem0 history.db events touching these pairs:\n")
    if not case["mem0_events"]:
        md.append("**(none — Mem0 did NOT fire any UPDATE event for this pair)**\n")
    else:
        for e in case["mem0_events"][:5]:
            hop_tag = f" [hop {e.get('__for_hop')}]" if "__for_hop" in e else ""
            md.append(f"- `{e['event']}`{hop_tag}: ")
            if e["old"]:
                md.append(f"  - old_memory: `{e['old']}`")
            if e["new"]:
                md.append(f"  - new_memory: `{e['new']}`")
        md.append("")

    # Mem0 retrieved + answer
    md.append("#### Mem0 retrieved (top of 100, only top-5 saved per qid) + answer:\n")
    for m in case["mem0_retrieved"]:
        md.append(f"- {m}")
    md.append(f"\n**Mem0 pred answer**: `{(case['mem0_answer'] or '')[:300]}`")
    md.append(f"**Mem0 EM**: {'✅' if case['mem0_em'] else '❌'}")
    md.append("")

    # Zep retrieved + answer
    md.append("#### Zep retrieved context preview + answer:\n")
    md.append(f"- edges={case['zep_n_edges']}, nodes={case['zep_n_nodes']}, episodes={case['zep_n_episodes']}")
    md.append(f"- preview (first 500 chars):\n")
    md.append(f"  ```\n  {(case['zep_retrieved'] or '').replace(chr(10), chr(10)+'  ')[:600]}\n  ```")
    md.append(f"\n**Zep pred answer**: `{(case['zep_answer'] or '')[:300]}`")
    md.append(f"**Zep EM**: {'✅' if case['zep_em'] else '❌'}")
    md.append("\n---\n")
    return "\n".join(md)


def main():
    sh_gt = json.load(open(SH_GT))
    mh_gt = json.load(open(MH_GT))
    mem0_sh = json.load(open(RESULTS / "mem0_gemini_sh_results.json"))
    mem0_mh = json.load(open(RESULTS / "mem0_gemini_mh_results.json"))
    zep_sh = json.load(open(RESULTS / "zep_gemini_sh_results.json"))
    zep_mh = json.load(open(RESULTS / "zep_gemini_mh_results.json"))
    mem0_events = load_mem0_events()

    # Pick 12 representative cases to cover the patterns
    selected = [
        # SH happy paths (Mem0 detected + answered correctly)
        ("SH", 0),
        ("SH", 4),
        # SH where Mem0 missed but Zep got it
        ("SH", 11),
        ("SH", 22),
        # MH where Mem0 fully detected & correct
        ("MH", 0),
        ("MH", 1),
        # MH where Mem0 detected but Zep wrong (the propagation gap)
        ("MH", 5),
        ("MH", 9),
        # MH 4-hop hard cases (both struggle)
        ("MH", 30),
        ("MH", 50),
        # SH counterfactual where Zep×GPT historically went wrong direction
        ("SH", 30),
        ("SH", 50),
    ]

    md = ["# Case Studies — Mem0 vs Zep on FC conflict handling\n"]
    md.append("> Concrete examples of how Mem0 / Zep handle 12 representative FC questions.")
    md.append("> Mem0 events from `~/.mem0/history.db` filtered to this run (`created_at >= 2026-05-02T07:00:00`).")
    md.append("> Mem0 retrieved memories: only top-5 saved per qid in run JSON (full top-100 was sent to LLM).")
    md.append("> Zep retrieved context: only first 500 chars saved per qid in run JSON.\n")
    md.append("---\n")
    md.append("## Quick patterns observed\n")
    md.append("| Pattern | Cases | Implication |")
    md.append("|---|---|---|")
    md.append("| Mem0 detected → Mem0 retrieved CURRENT only → Mem0 answered correctly | SH qid=0, MH qid=0 | Mem0 paradigm = filter at write; LLM sees clean current state |")
    md.append("| Mem0 missed UPDATE → both old+new stored OR only old stored → Mem0 answered with old | MH qid=1 (Olga Kiev→Rodez missed) | Mem0 silent failure mode: no UPDATE event, retrieval returns world-knowledge-aligned old fact |")
    md.append("| Zep edge has `valid_at - present` for OLD fact (no invalid_at set) → LLM sees both with no clear signal → answered with old | SH qid=0, MH qid=0 | Zep detection silent miss; LLM defaults to world knowledge |")
    md.append("| Zep edge has narrow `valid_at - invalid_at` window for NEW fact (wrong direction) | SH qid=22 | counterfactual bias: Zep invalidated the CORRECT fact |")
    md.append("| No has_pair conflict + correct retrieve → both succeed | SH qid=4, qid=11 | baseline competence |")
    md.append("\n---\n")

    for task, qid in selected:
        results_pool = mem0_sh if task == "SH" else mem0_mh
        zep_pool = zep_sh if task == "SH" else zep_mh
        case = make_case(qid, task, results_pool, zep_pool, mem0_events, mh_gt=mh_gt, sh_gt=sh_gt)
        if case:
            md.append(render_case(case))

    out_path = RESULTS / "case_studies.md"
    out_path.write_text("\n".join(md))
    print(f"Written {len(selected)} case studies to: {out_path}")
    # Print a sample of the case_studies length
    print(f"File size: {out_path.stat().st_size} bytes")


if __name__ == "__main__":
    main()
