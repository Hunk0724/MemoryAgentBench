# A5 — Cascade Attrition by Hop (Ablation B)

For each has_pair hop, track how many survive each pipeline stage:

| Hop | n | Active (both in) | Chain (union) | Pool co | Verdict correct | Filter dropped |
|---|---|---|---|---|---|---|
| 2-hop | 87 | 87 (100%) | 70 (80%) | 73 (84%) | 72 (83%) | 59 (68%) |
| 3-hop | 48 | 43 (90%) | 24 (50%) | 29 (60%) | 28 (58%) | 28 (58%) |
| 4-hop | 35 | 29 (83%) | 10 (29%) | 13 (37%) | 12 (34%) | 8 (23%) |
