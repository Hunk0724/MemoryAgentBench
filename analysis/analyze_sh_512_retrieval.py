"""
Offline retrieval analysis for FC-SH chunk_size=512.
Re-runs PPR retrieval for all cases using the existing KG store, then:
  1. Classifies failures:
       Type A - new fact WAS retrieved, LLM chose wrong (reasoning failure)
       Type B - new fact was NOT retrieved (retrieval failure)
  2. Records rank and intra-prompt position (char offset) of new/old facts,
     enabling recency-bias analysis.
"""
import sys, os, json, re
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

os.environ["CUDA_VISIBLE_DEVICES"] = "0"

RESULTS_FILE = "outputs/gpt-4o-mini-hippo_rag_v2_nv/Conflict_Resolution/factconsolidation_sh_6k_unknown_in6000_size10_shots0_max_samplesunknown_k10_chunk512_results.json"
STORE_DIR    = "outputs/rag_retrieved/NV-Embed-v2/factconsolidation_sh_6k/chunksize_512/context_id_0"

# ── Load results ──────────────────────────────────────────────────────────────
with open(RESULTS_FILE) as f:
    data = json.load(f)

results = data['data']
em = data['metrics']['exact_match']

fail_cases = [results[i] for i, v in enumerate(em) if not v]
pass_cases = [results[i] for i, v in enumerate(em) if v]
print(f"Total: {len(results)}  |  Fail: {len(fail_cases)}  |  Pass: {len(pass_cases)}\n")

# ── Load HippoRAG (retrieval only, no re-indexing) ───────────────────────────
from methods.hipporag import HippoRAG
hipporag = HippoRAG(
    save_dir=STORE_DIR,
    llm_model_name="gpt-4o-mini",
    embedding_model_name="nvidia/NV-Embed-v2",
)

# ── Helpers ───────────────────────────────────────────────────────────────────
def answer_in_chunk(answer, chunk_text):
    return answer.strip().lower() in chunk_text.lower()

def find_ranks(answer, chunks):
    """1-based ranks of chunks that contain the answer."""
    ans_list = answer if isinstance(answer, list) else [answer]
    return [i + 1 for i, chunk in enumerate(chunks)
            if any(answer_in_chunk(a, chunk) for a in ans_list)]

def build_prompt_text(top_k_docs):
    """Reconstruct the rag_qa musique-style prompt body (passages only)."""
    return "\n\n".join(f"Wikipedia Title: {doc}" for doc in top_k_docs)

def find_char_offset(answer, prompt_text):
    """Return first char offset (0-based) of answer in prompt, or -1."""
    ans_list = answer if isinstance(answer, list) else [answer]
    for ans in ans_list:
        idx = prompt_text.lower().find(ans.strip().lower())
        if idx != -1:
            return idx
    return -1

def prompt_position_pct(offset, prompt_len):
    """0.0 = beginning, 1.0 = end of prompt."""
    return offset / prompt_len if prompt_len > 0 else -1

# ── Re-run retrieval for all cases ───────────────────────────────────────────
print("Re-running retrieval for all cases...")
type_a, type_b = [], []
pass_entries = []

def process_case(r, label):
    query  = r['query']
    answer = r['answer']
    old_fact = r["output"].strip()
    ans_str  = answer[0] if isinstance(answer, list) else answer

    retrieval_results, top_k_docs = hipporag.retrieve(queries=[query], num_to_retrieve=10)
    scores = retrieval_results[0].doc_scores.tolist()

    new_ranks = find_ranks(answer,   top_k_docs)
    old_ranks = find_ranks(old_fact, top_k_docs)

    # Build the full prompt text to measure positional offsets
    prompt_text = build_prompt_text(top_k_docs)
    prompt_len  = len(prompt_text)

    new_offset = find_char_offset(answer,   prompt_text)
    old_offset = find_char_offset(old_fact, prompt_text)

    new_pos_pct = prompt_position_pct(new_offset, prompt_len) if new_offset >= 0 else None
    old_pos_pct = prompt_position_pct(old_offset, prompt_len) if old_offset >= 0 else None

    # Recency advantage: new fact is LATER in prompt than old fact (recency bias would help)
    recency_advantage = None
    if new_offset >= 0 and old_offset >= 0:
        recency_advantage = new_offset > old_offset  # True → new is closer to end

    return {
        "label":              label,
        "query_id":           r.get("query_id"),
        "expected_answer":    ans_str,
        "model_output":       old_fact,
        "new_fact_retrieved": len(new_ranks) > 0,
        # chunk rank info (1 = first returned by PPR)
        "new_fact_ranks":     new_ranks,
        "old_fact_ranks":     old_ranks,
        "new_fact_scores":    [round(scores[k-1], 5) for k in new_ranks],
        "old_fact_scores":    [round(scores[k-1], 5) for k in old_ranks],
        # intra-prompt position
        "new_fact_char_offset": new_offset,   # -1 = not in prompt
        "old_fact_char_offset": old_offset,
        "new_fact_pos_pct":     new_pos_pct,  # 0.0~1.0, None if not retrieved
        "old_fact_pos_pct":     old_pos_pct,
        "prompt_len_chars":     prompt_len,
        "recency_advantage":    recency_advantage,  # True/False/None
        "retrieved_scores":   [round(s, 5) for s in scores],
        "retrieved_chunks":   top_k_docs,
    }

for r in fail_cases:
    e = process_case(r, "fail")
    if e["new_fact_retrieved"]:
        type_a.append(e)
    else:
        type_b.append(e)

for r in pass_cases:
    e = process_case(r, "pass")
    pass_entries.append(e)

# ── Summary ───────────────────────────────────────────────────────────────────
from collections import Counter
import statistics

print("\n" + "="*60)
print("RETRIEVAL FAILURE ANALYSIS — FC-SH chunk_size=512")
print("="*60)
print(f"\nFail cases ({len(fail_cases)} total):")
print(f"  Type A (new fact retrieved, LLM chose wrong): {len(type_a):3d}  ({len(type_a)/len(fail_cases)*100:.1f}%)")
print(f"  Type B (new fact NOT retrieved):              {len(type_b):3d}  ({len(type_b)/len(fail_cases)*100:.1f}%)")

pass_with_new    = [e for e in pass_entries if e["new_fact_retrieved"]]
pass_without_new = [e for e in pass_entries if not e["new_fact_retrieved"]]
print(f"\nPass cases ({len(pass_cases)} total):")
print(f"  New fact was retrieved:     {len(pass_with_new):3d}  ({len(pass_with_new)/len(pass_cases)*100:.1f}%)")
print(f"  New fact was NOT retrieved: {len(pass_without_new):3d}  ({len(pass_without_new)/len(pass_cases)*100:.1f}%)")

# ── Type A detail ─────────────────────────────────────────────────────────────
print(f"\n--- Type A: new fact in prompt but LLM chose wrong ---")
print(f"  {'expected':22s}  {'got':22s}  new_rank  old_rank  new_pos%  old_pos%  recency_adv")
for e in type_a:
    nr = str(e['new_fact_ranks'])
    or_ = str(e['old_fact_ranks']) if e['old_fact_ranks'] else "—"
    np_ = f"{e['new_fact_pos_pct']*100:.1f}%" if e['new_fact_pos_pct'] is not None else "—"
    op_ = f"{e['old_fact_pos_pct']*100:.1f}%" if e['old_fact_pos_pct'] is not None else "—"
    ra  = str(e['recency_advantage'])
    print(f"  {e['expected_answer']:22s}  {e['model_output']:22s}  {nr:8s}  {or_:8s}  {np_:8s}  {op_:8s}  {ra}")

# ── Type B detail ─────────────────────────────────────────────────────────────
print(f"\n--- Type B: new fact missing from retrieved chunks ---")
print(f"  {'expected':22s}  {'got':22s}  old_rank  old_pos%  top1_score")
for e in type_b:
    or_ = str(e['old_fact_ranks']) if e['old_fact_ranks'] else "—"
    op_ = f"{e['old_fact_pos_pct']*100:.1f}%" if e['old_fact_pos_pct'] is not None else "—"
    print(f"  {e['expected_answer']:22s}  {e['model_output']:22s}  {or_:8s}  {op_:8s}  {e['retrieved_scores'][0]:.4f}")

# ── Recency bias analysis ─────────────────────────────────────────────────────
print(f"\n{'='*60}")
print("RECENCY BIAS ANALYSIS")
print(f"{'='*60}")

def recency_stats(entries, label):
    with_both = [e for e in entries if e['recency_advantage'] is not None]
    adv  = [e for e in with_both if e['recency_advantage']]      # new AFTER old → recency helps
    disadv = [e for e in with_both if not e['recency_advantage']] # new BEFORE old → recency hurts
    print(f"\n{label} ({len(entries)} total, {len(with_both)} with both new+old in prompt):")
    print(f"  new fact AFTER  old (recency helps): {len(adv):3d}")
    print(f"  new fact BEFORE old (recency hurts): {len(disadv):3d}")
    if with_both:
        avg_new = statistics.mean(e['new_fact_pos_pct'] for e in with_both)
        avg_old = statistics.mean(e['old_fact_pos_pct'] for e in with_both)
        print(f"  avg new_fact position in prompt: {avg_new*100:.1f}%")
        print(f"  avg old_fact position in prompt: {avg_old*100:.1f}%")

recency_stats(type_a,       "Type A (fail, both retrieved)")
recency_stats(pass_entries, "Pass cases")

# Among Type A: when new is AFTER old → did LLM still fail?
type_a_adv    = [e for e in type_a if e['recency_advantage'] is True]
type_a_disadv = [e for e in type_a if e['recency_advantage'] is False]
print(f"\nType A breakdown:")
print(f"  recency advantage (new after old) → still failed: {len(type_a_adv)}")
print(f"  recency disadvantage (new before old) → failed:   {len(type_a_disadv)}")

# ── Rank distribution ─────────────────────────────────────────────────────────
print(f"\n--- New fact rank distribution (Type A) ---")
rank_counter = Counter(r for e in type_a for r in e['new_fact_ranks'])
for rank in sorted(rank_counter):
    print(f"  rank #{rank}: {rank_counter[rank]}x")

print(f"\n--- Old fact rank distribution (all fail cases where old retrieved) ---")
old_rank_counter = Counter(r for e in type_a + type_b for r in e['old_fact_ranks'])
for rank in sorted(old_rank_counter):
    print(f"  rank #{rank}: {old_rank_counter[rank]}x")

# ── Save ──────────────────────────────────────────────────────────────────────
os.makedirs("analysis/results", exist_ok=True)
out = {
    "summary": {
        "total_fail": len(fail_cases),
        "type_a_reasoning_failure": len(type_a),
        "type_b_retrieval_failure": len(type_b),
        "pass_with_new_fact_retrieved":    len(pass_with_new),
        "pass_without_new_fact_retrieved": len(pass_without_new),
    },
    "type_a": type_a,
    "type_b": type_b,
    "pass":   pass_entries,
}
out_path = "analysis/results/sh_512_retrieval_analysis.json"
with open(out_path, "w") as f:
    json.dump(out, f, indent=2, ensure_ascii=False)
print(f"\nDetailed results saved to {out_path}")
