# A5b — Asymmetric Filter-Driven Cascade (Ablation B)

**校正:filter 真正必要 cascade 是 asymmetric**(只需 chain_old ∈ chain,chain_new 可從 dynamic_lookup 進 pool)。

## Cascade definition

| Stage | Definition |
|---|---|
| S1 | chain_OLD ∈ ∪ candidate chains (chain_old 被選為 focus) |
| S2 | focus=chain_old 的 pool 含 chain_NEW (LLM 可看到對立) |
| S3 | LLM identify chain_new 為 contradicting |
| S4 | Mechanical → verdict 標 chain_old=superseded by chain_new |
| S5 | chain_old chunk ∈ top-20 retrieval (filter scope) |
| S6 | filter 真的 drop chain_old chunk (rescue 沒救) |

## Per-hop cascade rates

| Hop | n | S1 old∈chain | S2 new∈old's pool | S3 LLM ident | S4 verdict supersed | S5 chunk∈top20 | S6 dropped |
|---|---|---|---|---|---|---|---|
| 2-hop | 87 | 73 (83%) | 73 (83%) | 71 (81%) | 71 (81%) | 71 (81%) | 56 (64%) |
| 3-hop | 48 | 28 (58%) | 28 (58%) | 28 (58%) | 28 (58%) | 28 (58%) | 23 (47%) |
| 4-hop | 35 | 13 (37%) | 13 (37%) | 13 (37%) | 12 (34%) | 12 (34%) | 8 (22%) |
| **All** | **170** | 114 (67%) | 114 (67%) | 112 (65%) | 111 (65%) | 111 (65%) | 87 (51%) |
