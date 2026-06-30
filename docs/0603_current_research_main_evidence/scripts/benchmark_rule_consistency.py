"""
Benchmark-ONLY check (no MQuAKE): does each FC-SH answer obey the benchmark's
OWN stated rule "answer = newest = largest serial number"?

For each question, locate its gt fact (subject+relation+answer) in the context
via the run GT's gt_fact_text (a unique text locator, independent of MQuAKE
quality), derive the subject-specific cloze, find same-slot siblings, and flag
questions whose answer is NOT the largest serial in that slot.

Result (sh_32k): 65 conflict questions, 63 answer==largest (rule-consistent),
2 (Q8/Q9) answer==smaller serial => benchmark answer-key contradicts its own
rule. These 2 must be excluded from mem0 failure attribution; mem0 (keep largest
serial) is in fact rule-compliant and is penalized by the defective answer key.
"""
import json, re, sys
from datasets import Dataset

ARROW = sys.argv[1] if len(sys.argv) > 1 else \
    ".cache/huggingface/datasets/ai-hyz___memory_agent_bench/default/0.0.0/" \
    "00d1946269e29b41eed74511997afa8171b91e08/memory_agent_bench-Conflict_Resolution.arrow"
ITEM_IDX = int(sys.argv[2]) if len(sys.argv) > 2 else 5  # 5 = factconsolidation_sh_32k
RUN_GT = sys.argv[3] if len(sys.argv) > 3 else "analysis/results/sh_32k_RUN_gt.json"

ctx = Dataset.from_file(ARROW)[ITEM_IDX]["context"]
facts = [(int(m.group(1)), m.group(2).strip().rstrip("."))
         for m in re.finditer(r"^\s*(\d+)\.\s+(.+)", ctx, re.MULTILINE)]
norm = lambda s: s.strip().rstrip(".").lower()

gt = json.load(open(RUN_GT))
covered = multi_slot = collision = 0
coll = []
for q in gt:
    gtt, gs, a = q.get("gt_fact_text"), q.get("gt_seq"), q["gt_answer"]
    if not gtt or gs is None:
        continue
    covered += 1
    ft = gtt.rstrip(".")
    cl = ft[:len(ft) - len(a)].rstrip(" .") if norm(ft).endswith(norm(a)) else ft.rsplit(" ", 1)[0]
    sibs = [(s, t) for s, t in facts if t.lower().startswith(cl.lower())]
    if len(set(norm(t[len(cl):]) for s, t in sibs)) > 1:
        multi_slot += 1
        maxseq = max(s for s, _ in sibs)
        if gs != maxseq:
            collision += 1
            coll.append((q["query_id"], a, gs, maxseq,
                         [(s, t[len(cl):].strip(" .")) for s, t in sorted(sibs)]))

print(f"covered {covered}/{len(gt)}")
print(f"conflict (multi-version) questions: {multi_slot}")
print(f"answer == largest serial (rule-consistent): {multi_slot - collision}")
print(f"answer != largest serial (BENCHMARK DEFECT): {collision}")
for qid, a, gs, mx, sibs in coll:
    print(f"  Q{qid}: ans={a!r}@{gs}  larger same-slot @{mx}  versions={sibs}")
