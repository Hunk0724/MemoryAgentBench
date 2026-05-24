"""Dump the real qa() prompt to verify top-K and content structure.

Inline driver: does NOT modify HippoRAG.py source.
- Loads existing vectorstore
- Runs retrieve() on 1 query
- Mirrors qa() prompt assembly logic (HippoRAG.py:579-592)
- Prints actual prompt_user content + length
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

BASE = Path("/home/yhchiang/MemoryAgentBench")

# Setup env (vanilla A 設定)
os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "True")
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "fc-mh-494213")
os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "global")
os.environ.setdefault("HF_HOME", str(BASE / ".cache/huggingface"))
os.environ["HIPPORAG_ENABLE_PHASE2_CHAIN_DETECTION"] = "0"   # vanilla
os.environ["HIPPORAG_ENABLE_PHASE3_V2_ENRICHED"] = "0"
os.environ["HIPPORAG_ENABLE_PHASE2_FILTER_PASSAGES"] = "0"
os.environ.setdefault("HIPPORAG_EMBED_FP16", "1")
os.environ.setdefault("HIPPORAG_EMBED_BATCH_SIZE", "8")
os.environ.setdefault("HIPPORAG_ENABLE_SUPERSESSION", "0")
os.environ.setdefault("HIPPORAG_ENABLE_PHASE2_FILTER", "0")
os.environ.setdefault("HIPPORAG_ENABLE_PHASE3_SCAFFOLD", "0")
os.environ.setdefault("HIPPORAG_ENABLE_V2_DETECT", "0")

sys.path.insert(0, str(BASE))

save_dir = BASE / "outputs/rag_retrieved/NV-Embed-v2/factconsolidation_mh_6k/chunksize_512/context_id_0"

print("[dump] init HippoRAG…")
from methods.hipporag import HippoRAG

hipporag = HippoRAG(
    save_dir=str(save_dir),
    llm_model_name="gemini-3.1-flash-lite-preview",
    embedding_model_name="nvidia/NV-Embed-v2",
)
hipporag.index(docs=[])

# Show config
print(f"\n=== Config ===")
print(f"qa_top_k:              {hipporag.global_config.qa_top_k}")
print(f"retrieval_top_k:       {hipporag.global_config.retrieval_top_k}")

# Use a real FC-MH query (same as case no0 from prompts_comparison.md example)
# Include the FC task-level wrapper that conversation_creator.py adds
fc_wrapper_template = """Pretend you are a knowledge management system. Each fact in the knowledge pool is provided with a serial number at the beginning, and the newer fact has larger serial number.
 You need to solve the conflicts of facts in the knowledge pool by finding the newest fact with larger serial number. You need to answer a question based on this rule. You should give a very concise answer without saying other words for the question **only** from the knowledge pool you have memorized rather than the real facts in real world.

For example:

 [Knowledge Pool]

 Question: Based on the provided Knowledge Pool, what is the name of the current president of Russia?
Answer: Donald Trump

 Now Answer the Question: Based on the provided Knowledge Pool, {question}
Answer:"""

# question 0: OMF spouse citizenship
question = "What is the country of citizenship of the spouse of the author of Our Mutual Friend?"
formatted_query = fc_wrapper_template.format(question=question)

print(f"\n[dump] retrieving for query…")
retrieval_results, top_k_docs = hipporag.retrieve(queries=[formatted_query], num_to_retrieve=10)
qs = retrieval_results[0]

print(f"\n=== Retrieve result ===")
print(f"len(query_solution.docs): {len(qs.docs)}  (= retrieve num_to_retrieve)")
print(f"doc_scores top 3: {qs.doc_scores[:3].tolist() if hasattr(qs.doc_scores, 'tolist') else qs.doc_scores[:3]}")

# Mirror qa() prompt assembly (HippoRAG.py:579-592)
qa_top_k = hipporag.global_config.qa_top_k
retrieved_passages = qs.docs[:qa_top_k]
print(f"\n=== qa() cut ===")
print(f"qa_top_k cut: {qa_top_k}")
print(f"retrieved_passages selected: {len(retrieved_passages)}")

prompt_user = ''
for passage in retrieved_passages:
    prompt_user += f'Wikipedia Title: {passage}\n\n'
prompt_user += 'Question: ' + qs.question + '\nThought: '

print(f"\n=== Final prompt_user ===")
print(f"Total chars: {len(prompt_user)}")
# Approximate tokens
import re
words = len(re.findall(r'\S+', prompt_user))
print(f"Approx word count: {words}")
print(f"Approx tokens (~1.3 per word): {int(words * 1.3)}")

# Count "Wikipedia Title:" markers
n_wiki = prompt_user.count("Wikipedia Title:")
print(f"# 'Wikipedia Title:' blocks: {n_wiki}")

# Confirm wrapper presence
has_serial_rule = "newer fact has larger serial number" in prompt_user
has_solve_conflicts = "solve the conflicts" in prompt_user
print(f"\n=== Wrapper check ===")
print(f"R1 'newer fact has larger serial number': {has_serial_rule}")
print(f"R2 'solve the conflicts':                 {has_solve_conflicts}")

# Dump full prompt
out_path = BASE / "analysis/results/full100_eval/real_qa_prompt_sample.txt"
out_path.parent.mkdir(parents=True, exist_ok=True)
with open(out_path, "w") as f:
    f.write(f"=== Config ===\nqa_top_k={qa_top_k}\nlen(docs)={len(qs.docs)}\n\n")
    f.write(f"=== prompt_user (full) ===\n")
    f.write(prompt_user)
print(f"\n[wrote] full prompt to {out_path}")

# Show beginning + end
print(f"\n=== prompt_user (first 1500 chars) ===")
print(prompt_user[:1500])
print(f"\n=== prompt_user (last 1500 chars) ===")
print(prompt_user[-1500:])
