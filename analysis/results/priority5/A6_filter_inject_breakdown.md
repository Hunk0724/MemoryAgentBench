# A6 — Chain_old Chunk Classification: Filter + Inject Potential

For each ground-truth `chain_old` prop's source_chunk, classify whether the chunk also contains GT `chain_new` props:

## Categories

| Category | Means | Filter strategy |
|---|---|---|
| **A SAFE_DROP** | chunk 不含任何 GT chain_new | 直接 drop 安全 |
| **B SAME_HOP_NEW** | chunk 內含**同 hop 對應的** chain_new | drop 會殺到答案 → **必須 inject** chain_new 回 context |
| **C CROSS_HOP_UNIQUE** | chunk 含**其他 hop 的** chain_new + 該 chain_new **只在這 chunk** | drop 會漏失另一 hop → **應 inject** |
| **D CROSS_HOP_REDUNDANT** | chunk 含其他 hop 的 chain_new + 該 chain_new **也在其他 chunk** | drop 無損失(redundancy) |

## Overall distribution

| Category | Count | % |
|---|---|---|
| A_SAFE_DROP | 146 | 83% |
| B_SAME_HOP_NEW | 20 | 11% |
| C_CROSS_HOP_UNIQUE | 9 | 5% |
| D_CROSS_HOP_REDUNDANT | 0 | 0% |

## By hop depth

| Hop | n | A SAFE_DROP | B SAME_HOP_NEW | C CROSS_UNIQUE | D CROSS_REDUNDANT |
|---|---|---|---|---|---|
| 2-hop | 89 | 76 (85%) | 10 (11%) | 3 (3%) | 0 (0%) |
| 3-hop | 51 | 44 (86%) | 4 (7%) | 3 (5%) | 0 (0%) |
| 4-hop | 35 | 26 (74%) | 6 (17%) | 3 (8%) | 0 (0%) |

## Filter + Inject design implication

**A+D 可以放心 drop**: 146/175 = 83%

**B+C 必須 inject 該 chunk 內 chain_new 才能 safely drop**: 29/175 = 17%

→ 若不 inject,B+C 這 29 個 hops 的 filter 會誤殺 chain_new 答案.
