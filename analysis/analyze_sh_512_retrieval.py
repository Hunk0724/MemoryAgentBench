"""
Offline retrieval analysis for FC-SH chunk_size=512.

Key fixes vs naive substring matching:
  - New fact = fact sentence with highest serial# containing answer AND key entity
  - Old fact = fact sentence with key entity but WITHOUT answer (conflicting value),
               highest serial# before the new fact
  - Model output may not equal the old fact (could be unrelated entity value)

Classifies failures as:
  Type A  - new fact sentence WAS in retrieved chunks (reasoning/attention failure)
  Type B  - new fact sentence was NOT retrieved (retrieval failure)

Also records intra-prompt positions for recency bias analysis.
"""
import sys, os, json, re
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

os.environ["CUDA_VISIBLE_DEVICES"] = "0"
if not os.environ.get("OPENAI_API_KEY"):
    os.environ["OPENAI_API_KEY"] = "retrieval-only-no-llm-calls"

RESULTS_FILE = "outputs/gpt-4o-mini-hippo_rag_v2_nv/Conflict_Resolution/factconsolidation_sh_6k_unknown_in6000_size10_shots0_max_samplesunknown_k10_chunk512_results.json"
STORE_DIR    = "outputs/rag_retrieved/NV-Embed-v2/factconsolidation_sh_6k/chunksize_512/context_id_0"
ARROW_FILE   = ".cache/huggingface/datasets/ai-hyz___memory_agent_bench/default/0.0.0/00d1946269e29b41eed74511997afa8171b91e08/memory_agent_bench-Conflict_Resolution.arrow"

# ── Load FC dataset context ───────────────────────────────────────────────────
import pyarrow as pa
table = pa.ipc.open_stream(ARROW_FILE).read_all()
fc_row = next(r for r in table.to_pylist() if 'factconsolidation_sh' in str(r['metadata']))

raw_context = fc_row['context']

# Parse all numbered facts: {serial: fact_text}
fact_pattern = re.compile(r'(\d+)\. (.+?)(?=\n\d+\. |\Z)', re.DOTALL)
all_facts = [(int(n), t.strip()) for n, t in fact_pattern.findall(raw_context)]
print(f"Loaded {len(all_facts)} facts from FC-SH context")

# ── Load results ──────────────────────────────────────────────────────────────
with open(RESULTS_FILE) as f:
    data = json.load(f)

results = data['data']
em = data['metrics']['exact_match']

fail_cases = [results[i] for i, v in enumerate(em) if not v]
pass_cases = [results[i] for i, v in enumerate(em) if v]
print(f"Total: {len(results)}  Fail: {len(fail_cases)}  Pass: {len(pass_cases)}\n")

# ── Load HippoRAG ─────────────────────────────────────────────────────────────
from methods.hipporag import HippoRAG
hipporag = HippoRAG(save_dir=STORE_DIR, llm_model_name="gpt-4o-mini",
                    embedding_model_name="nvidia/NV-Embed-v2")
hipporag.index(docs=[])

# ── Helpers ───────────────────────────────────────────────────────────────────
def extract_key_entities_from_query(query_text):
    """
    Extract the question part from the FC query template and return
    candidate key entities (nouns/phrases before the question verb).
    Simple heuristic: return all tokens of length >= 4 from the actual question sentence.
    """
    # FC template: "...Now Answer the Question: Based on the provided Knowledge Pool, {question}\nAnswer:"
    match = re.search(r'Now Answer the Question:.*?Knowledge Pool,\s*(.+?)\n', query_text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return query_text[-200:]

def find_specific_fact(answer_text, question_str, all_facts):
    """
    Find the new fact: the fact with the HIGHEST serial number whose text contains
    the answer AND a key entity from the question.
    Falls back to highest-serial fact containing the answer if no entity match.
    """
    ans_lower = answer_text.strip().lower()
    # Find candidate facts containing the answer
    answer_facts = [(n, t) for n, t in all_facts if ans_lower in t.lower()]
    if not answer_facts:
        return None, None

    # Extract question sentence (the actual question, not the template)
    q_sent = extract_key_entities_from_query(question_str)
    # Tokenize: words >= 4 chars as candidate entities
    q_tokens = set(w.lower() for w in re.findall(r'\b\w{4,}\b', q_sent))

    # Prefer facts that share tokens with the question
    entity_matches = [(n, t) for n, t in answer_facts
                      if any(tok in t.lower() for tok in q_tokens)]
    candidates = entity_matches if entity_matches else answer_facts
    # Pick the one with highest serial number
    best = max(candidates, key=lambda x: x[0])
    return best  # (serial_number, fact_text)

def find_old_fact(new_serial, new_fact_text, all_facts):
    """
    Find the old fact: highest-serial fact that shares key entity tokens with
    the new fact but has a DIFFERENT predicate object (different ending).
    Heuristic: same first half of sentence structure, different ending.
    """
    # Extract subject/predicate prefix from new fact (everything before the answer value)
    # E.g. "goaltender is associated with the sport of pesäpallo"
    #   → try to find facts with "goaltender is associated with the sport of" but different object
    words = new_fact_text.split()
    if len(words) < 4:
        return None, None

    # Use first 60% of words as the "subject+predicate" prefix
    prefix_len = max(3, int(len(words) * 0.5))
    prefix_tokens = set(w.lower() for w in words[:prefix_len] if len(w) >= 4)

    candidates = []
    for n, t in all_facts:
        if n >= new_serial:
            continue  # must be older (lower serial)
        t_lower = t.lower()
        # Must share prefix tokens with new fact
        overlap = sum(1 for tok in prefix_tokens if tok in t_lower)
        if overlap >= min(2, len(prefix_tokens)):
            # Must NOT be identical to new fact
            if t.lower().strip() != new_fact_text.lower().strip():
                candidates.append((n, t, overlap))

    if not candidates:
        return None, None
    # Pick highest serial (most recent old fact)
    best = max(candidates, key=lambda x: (x[2], x[0]))
    return best[0], best[1]

def fact_in_chunks(fact_text, chunks):
    """Check if the specific fact sentence appears in any chunk (partial match, >=80% of words)."""
    if fact_text is None:
        return []
    words = set(w.lower() for w in fact_text.split() if len(w) >= 3)
    if not words:
        return []
    threshold = 0.75
    ranks = []
    for i, chunk in enumerate(chunks):
        chunk_lower = chunk.lower()
        overlap = sum(1 for w in words if w in chunk_lower)
        if overlap / len(words) >= threshold:
            ranks.append(i + 1)
    return ranks

def find_fact_char_offset(fact_text, prompt_text):
    """Find char offset of a fact sentence in prompt using fuzzy word match."""
    if fact_text is None:
        return -1
    # Try exact substring first
    idx = prompt_text.lower().find(fact_text.lower()[:40])
    return idx

def build_prompt_text(top_k_docs):
    return "\n\n".join(f"Wikipedia Title: {doc}" for doc in top_k_docs)

# ── Process all cases ─────────────────────────────────────────────────────────
print("Re-running retrieval and locating specific fact sentences...")
type_a, type_b = [], []
pass_entries = []

def process_case(r, label):
    query   = r['query']
    answer  = r['answer']
    ans_str = answer[0] if isinstance(answer, list) else answer
    model_out = r["output"].strip()

    # Find specific new and old fact sentences in the original context
    new_serial, new_fact_text = find_specific_fact(ans_str, query, all_facts)
    if new_serial is not None:
        old_serial, old_fact_text = find_old_fact(new_serial, new_fact_text, all_facts)
    else:
        old_serial, old_fact_text = None, None
    # has_conflict_pair: False means this fact has no conflicting counterpart
    has_conflict_pair = (old_serial is not None)

    # Re-run retrieval
    retrieval_results, top_k_docs = hipporag.retrieve(queries=[query], num_to_retrieve=10)
    scores = retrieval_results[0].doc_scores.tolist()

    # Check which ranks contain the specific new/old fact sentences
    new_ranks = fact_in_chunks(new_fact_text, top_k_docs)
    old_ranks = fact_in_chunks(old_fact_text, top_k_docs)

    # Intra-prompt position (char offset in assembled prompt)
    prompt_text = build_prompt_text(top_k_docs)
    prompt_len  = len(prompt_text)
    new_offset  = find_fact_char_offset(new_fact_text, prompt_text) if new_fact_text else -1
    old_offset  = find_fact_char_offset(old_fact_text, prompt_text) if old_fact_text else -1

    new_pos_pct = new_offset / prompt_len if new_offset >= 0 and prompt_len > 0 else None
    old_pos_pct = old_offset / prompt_len if old_offset >= 0 and prompt_len > 0 else None

    recency_advantage = None
    if new_offset >= 0 and old_offset >= 0:
        recency_advantage = new_offset > old_offset  # True → new is closer to end

    # Check if model output matches true old fact
    model_matches_old = (old_fact_text is not None and
                         model_out.lower().strip().rstrip('.') in old_fact_text.lower())

    return {
        "label":               label,
        "query_id":            r.get("query_id"),
        "expected_answer":     ans_str,
        "model_output":        model_out,
        # Specific fact sentences from original context
        "new_fact_serial":     new_serial,
        "new_fact_text":       new_fact_text,
        "old_fact_serial":     old_serial,
        "old_fact_text":       old_fact_text,
        "model_matches_old_fact": model_matches_old,
        "has_conflict_pair":   has_conflict_pair,  # False = 此事實在 context 中無衝突對
        # Retrieval positions
        "new_fact_retrieved":  len(new_ranks) > 0,
        "new_fact_ranks":      new_ranks,
        "old_fact_ranks":      old_ranks,
        "new_fact_scores":     [round(scores[k-1], 5) for k in new_ranks],
        "old_fact_scores":     [round(scores[k-1], 5) for k in old_ranks],
        # Intra-prompt position
        "new_fact_pos_pct":    new_pos_pct,
        "old_fact_pos_pct":    old_pos_pct,
        "recency_advantage":   recency_advantage,
        "retrieved_scores":    [round(s, 5) for s in scores],
        "retrieved_chunks":    top_k_docs,
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
print(f"\nFail ({len(fail_cases)} total):")
print(f"  Type A (new fact sentence retrieved, LLM wrong): {len(type_a):3d}  ({len(type_a)/len(fail_cases)*100:.1f}%)")
print(f"  Type B (new fact sentence NOT retrieved):         {len(type_b):3d}  ({len(type_b)/len(fail_cases)*100:.1f}%)")

pass_with    = [e for e in pass_entries if e["new_fact_retrieved"]]
pass_without = [e for e in pass_entries if not e["new_fact_retrieved"]]
print(f"\nPass ({len(pass_cases)} total):")
print(f"  新事實句有被檢索到:     {len(pass_with):3d}  ({len(pass_with)/len(pass_cases)*100:.1f}%)")
print(f"  新事實句未被檢索到:     {len(pass_without):3d}  ({len(pass_without)/len(pass_cases)*100:.1f}%)")

# 衝突對存在與否的統計
all_entries = type_a + type_b + pass_entries
no_conflict = [e for e in all_entries if not e["has_conflict_pair"]]
has_conflict = [e for e in all_entries if e["has_conflict_pair"]]
print(f"\n--- 衝突對存在性（context 中有無對應的舊事實句）---")
print(f"  有衝突對:   {len(has_conflict):3d} / {len(all_entries)}")
print(f"  無衝突對:   {len(no_conflict):3d} / {len(all_entries)}")
fail_no_conflict = [e for e in type_a + type_b if not e["has_conflict_pair"]]
print(f"  Fail 中無衝突對: {len(fail_no_conflict)}")

# Model output vs true old fact
all_fail_entries = type_a + type_b
model_eq_old = [e for e in all_fail_entries if e["model_matches_old_fact"]]
print(f"\n--- 模型輸出與真正的舊事實是否相符 ---")
print(f"  模型輸出 = 真正的舊事實: {len(model_eq_old)}/{len(all_fail_entries)}")
print(f"  模型輸出 = 其他無關值:   {len(all_fail_entries)-len(model_eq_old)}/{len(all_fail_entries)}")

# ── Type A detail ─────────────────────────────────────────────────────────────
print(f"\n--- Type A: new fact in prompt but LLM chose wrong ---")
header = f"  {'expected':20s}  {'model_out':20s}  {'new_serial':>10}  {'old_serial':>10}  new_rank  old_rank  new_pos%  old_pos%  recency_adv  model=old?"
print(header)
for e in type_a:
    nr   = str(e['new_fact_ranks'])
    or_  = str(e['old_fact_ranks']) if e['old_fact_ranks'] else "—"
    np_  = f"{e['new_fact_pos_pct']*100:.1f}%" if e['new_fact_pos_pct'] is not None else "—"
    op_  = f"{e['old_fact_pos_pct']*100:.1f}%" if e['old_fact_pos_pct'] is not None else "—"
    ns   = str(e['new_fact_serial']) if e['new_fact_serial'] is not None else "?"
    os_  = str(e['old_fact_serial']) if e['old_fact_serial'] is not None else "?"
    ra   = str(e['recency_advantage'])
    mo   = str(e['model_matches_old_fact'])
    print(f"  {e['expected_answer']:20s}  {e['model_output']:20s}  {ns:>10}  {os_:>10}  {nr:8s}  {or_:8s}  {np_:8s}  {op_:8s}  {ra:11s}  {mo}")

# ── Type B detail ─────────────────────────────────────────────────────────────
if type_b:
    print(f"\n--- Type B: new fact sentence missing ---")
    for e in type_b:
        print(f"  {e['expected_answer']:20s}  new_serial={e['new_fact_serial']}  new_text={e['new_fact_text']}")

# ── Recency bias ──────────────────────────────────────────────────────────────
print(f"\n{'='*60}")
print("RECENCY BIAS (based on specific fact sentence positions)")
print(f"{'='*60}")

def recency_stats(entries, label):
    with_both = [e for e in entries if e['recency_advantage'] is not None]
    adv    = [e for e in with_both if e['recency_advantage']]
    disadv = [e for e in with_both if not e['recency_advantage']]
    print(f"\n{label} ({len(entries)} cases, {len(with_both)} with both facts in prompt):")
    print(f"  new fact AFTER  old (recency helps): {len(adv):3d}")
    print(f"  new fact BEFORE old (recency hurts): {len(disadv):3d}")
    if with_both:
        avg_new = statistics.mean(e['new_fact_pos_pct'] for e in with_both)
        avg_old = statistics.mean(e['old_fact_pos_pct'] for e in with_both)
        print(f"  avg new_fact prompt position: {avg_new*100:.1f}%")
        print(f"  avg old_fact prompt position: {avg_old*100:.1f}%")

recency_stats(type_a,       "Type A (fail)")
recency_stats(pass_entries, "Pass")

# Serial number gap: new vs old
print(f"\n--- Serial number gap (new - old) ---")
a_gaps = [e['new_fact_serial'] - e['old_fact_serial'] for e in type_a
          if e['new_fact_serial'] and e['old_fact_serial']]
p_gaps = [e['new_fact_serial'] - e['old_fact_serial'] for e in pass_entries
          if e['new_fact_serial'] and e['old_fact_serial']]
if a_gaps:
    print(f"  Type A fail: mean gap={statistics.mean(a_gaps):.1f}  median={statistics.median(a_gaps):.1f}")
if p_gaps:
    print(f"  Pass:        mean gap={statistics.mean(p_gaps):.1f}  median={statistics.median(p_gaps):.1f}")

# ── Save ──────────────────────────────────────────────────────────────────────
os.makedirs("analysis/results", exist_ok=True)
out = {
    "summary": {
        "total_fail": len(fail_cases),
        "type_a": len(type_a),
        "type_b": len(type_b),
        "pass_with_new": len(pass_with),
        "pass_without_new": len(pass_without),
        "fail_model_output_eq_old_fact": len(model_eq_old),
    },
    "type_a": type_a,
    "type_b": type_b,
    "pass":   pass_entries,
}
out_path = "analysis/results/sh_512_retrieval_analysis.json"
with open(out_path, "w") as f:
    json.dump(out, f, indent=2, ensure_ascii=False)
print(f"\nSaved to {out_path}")
