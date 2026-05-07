"""Compare original (bare question) vs aligned (wrapped query) Mem0/Zep × Gemini."""

import json
from pathlib import Path

R = Path('/home/yhchiang/MemoryAgentBench/analysis/experiments/2026-05-02_mem0_zep_gemini_full100/results')

def acc(path):
    if not path.exists(): return None
    d = json.load(open(path))
    ok = sum(1 for r in d if r.get('exact_match'))
    return ok, len(d)

print(f'{"":<32} | {"FC-SH":<14} | {"FC-MH":<14}')
print('-' * 70)
for system in ['mem0', 'zep']:
    bare_sh = acc(R / f'{system}_gemini_sh_results.json')
    bare_mh = acc(R / f'{system}_gemini_mh_results.json')
    aligned_sh = acc(R / f'{system}_gemini_aligned_sh_results.json')
    aligned_mh = acc(R / f'{system}_gemini_aligned_mh_results.json')

    def fmt(a):
        return f'{a[0]}/{a[1]} = {a[0]/a[1]*100:.0f}%' if a else '(not run)'

    print(f'{system+" bare (q[question])":<32} | {fmt(bare_sh):<14} | {fmt(bare_mh):<14}')
    print(f'{system+" aligned (q[query] wrapped)":<32} | {fmt(aligned_sh):<14} | {fmt(aligned_mh):<14}')
    print()
