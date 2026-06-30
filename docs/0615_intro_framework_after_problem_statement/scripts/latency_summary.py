"""Table-12-style latency summary (M.C. = Memory Construction, Q.E. = Query
Execution), per MemoryAgentBench (Hu et al.) Table 12. Read straight from each
method's result JSON averaged_metrics (memory_construction_time / query_time_len
are recorded by main.py for EVERY method -> directly comparable). Our cost_logger
gives the within-M.C./Q.E. per-stage breakdown as a bonus (summarize_cost.py).

NOTE on Zep: its main.py memory_construction_time only times the graph.add SEND
(~55s for 64k); the real cost is Zep cloud server-side async processing
(measured separately, ~tens of min). Mark Zep M.C. as send + cloud-processing.
"""
import json, glob, sys

METH = [("ours", "gpt-4o-mini-mem0-chunk512-temp0-openai-unified"),
        ("(a)vanilla", "gpt-4o-mini-mem0-chunk512-temp0-openai-native"),
        ("(b)mem0+P1", "gpt-4o-mini-mem0-chunk512-temp0-openai-unified_dest"),
        ("LCA", "gpt-4o-mini-temp0")]
LENS = sys.argv[1:] or ["6k", "32k", "64k", "262k"]

print(f"{'method':<13}{'len':<6}{'M.C.(s/q)':>10}{'Q.E.(s/q)':>10}{'M.C.tot':>9}{'Q.E.tot':>9}")
for name, d in METH:
    for L in LENS:
        fs = glob.glob(f"outputs/{d}/Conflict_Resolution/*sh_{L}*results*.json")
        if not fs:
            continue
        D = json.load(open(fs[0])); am = D.get("averaged_metrics", {}); n = len(D.get("data", []))
        mc, qe = am.get("memory_construction_time", 0), am.get("query_time_len", 0)
        nm = f"{name}[{n}q]" if n < 100 else name
        print(f"{nm:<13}{L:<6}{mc:>10.2f}{qe:>10.2f}{mc*n:>9.0f}{qe*n:>9.0f}")
