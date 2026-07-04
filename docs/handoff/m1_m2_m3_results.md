# M1 / M2 / M3 Metrics (v2, rigor)

*Protocol*: evaluation_protocol_fc_mquake_v2.md
*Matcher*: 2-layer (string full-sentence + subject+object token overlap)
*Bucket rigor*: M3 mem0 UPDATE_kept_new requires (gt_old NOT in bank) AND (gt_new IN bank) AND (UPDATE event exists)

## Length = 6k

### Zep cumulative-state audit
```
  n_files                                 : 100
  n_edges_observed_union                  : 382
  n_p1_facts                              : 455
  ratio_edges_over_p1                     : 0.8395604395604396
  expired_at_present_in_data              : False
  verdict                                 : N/A (Zep top-10 per query — full graph dump needed for definitive audit)
```

**N_query = 74** (from sh_6k_mquake_analysis.json has_pair)
**N_bank = 124** (from ours P1 triple cache, (S,P) with ≥2 distinct objects)

### M1 (denominator = N_query, n=74)
```
ours (by construction)
  NFPR                                              : 100.0%
  OFPR                                              : 100.0%
  BSPR                                              : 100.0%
  DLR                                               :   0.0%
  (denominator n)                                   : 74
  note: by construction (conservative-ADD, no cross-item LLM judgment)
mem0+P1(b) — write-time destructive commit
  NFPR                                              :  52.7%
  OFPR                                              :  36.5%
  BSPR                                              :  16.2%
  DLR                                               :  47.3%
  (denominator n)                                   : 74
Zep (cloud, top-10 union of per-query edges)
  NFPR                                              :  79.7%
  OFPR                                              :  81.1%
  BSPR                                              :  62.2%
  DLR                                               :  20.3%
  (denominator n)                                   : 74
  note: top-10 union (upper-bound; true bank state may be lower)
```

### M1 (denominator = N_bank, n=124)
```
ours (by construction)
  NFPR                                              : 100.0%
  OFPR                                              : 100.0%
  BSPR                                              : 100.0%
  DLR                                               :   0.0%
  (denominator n)                                   : 124
  note: by construction (conservative-ADD, no cross-item LLM judgment)
mem0+P1(b) — write-time destructive commit
  NFPR                                              :  35.5%
  OFPR                                              :  49.2%
  BSPR                                              :  12.9%
  DLR                                               :  64.5%
  (denominator n)                                   : 124
Zep (cloud, top-10 union of per-query edges)
  NFPR                                              :  66.9%
  OFPR                                              :  63.7%
  BSPR                                              :  48.4%
  DLR                                               :  33.1%
  (denominator n)                                   : 124
  note: top-10 union (upper-bound; true bank state may be lower)
```

### M2 (pool state per query)
```
ours(full)
  PP-New                                            :  71.6%
  PP-Both                                           :  25.7%
  PP-Missing                                        :   1.4%
  PP-OldOnly                                        :   1.4%
  (denominator n)                                   : 74
ours(no_p5)
  PP-New                                            :  70.3%
  PP-Both                                           :  27.0%
  PP-Missing                                        :   1.4%
  PP-OldOnly                                        :   1.4%
  (denominator n)                                   : 74
ours(struct)
  PP-New                                            :  63.5%
  PP-Both                                           :  33.8%
  PP-OldOnly                                        :   2.7%
  (denominator n)                                   : 74
ours(p3_only)
  PP-Both                                           :  32.4%
  PP-New                                            :  64.9%
  PP-Missing                                        :   1.4%
  PP-OldOnly                                        :   1.4%
  (denominator n)                                   : 74
mem0+P1(b) (raw top-100)
  PP-New                                            :  36.5%
  PP-OldOnly                                        :  20.3%
  PP-Both                                           :  16.2%
  PP-Missing                                        :  27.0%
  (denominator n)                                   : 74
Zep (top-10 edges)
  PP-Both                                           :  97.3%
  PP-OldOnly                                        :   2.7%
  (denominator n)                                   : 74
```

### M3 (root-cause attribution)
```
mem0+P1(b) LLM event distribution on gt_new (rigorous bucket rules)
  UPDATE_kept_new                                   :  18.9% (14)
  Ambiguous(ADD|final_new=False,final_old=True)     :  13.5% (10)
  ADD_both_coexist                                  :   8.1% (6)
  DELETE_lost_new                                   :  13.5% (10)
  Ambiguous(ADD|final_new=True,final_old=False)     :  10.8% (8)
  NONE_silent                                       :  10.8% (8)
  Ambiguous(ADD+UPDATE|final_new=False,final_old=True):   4.1% (3)
  Ambiguous(ADD+DELETE|final_new=True,final_old=False):   6.8% (5)
  DELETE_dropped_new                                :   5.4% (4)
  Ambiguous(ADD+DELETE|final_new=True,final_old=True):   5.4% (4)
  Ambiguous(ADD+DELETE+UPDATE|final_new=True,final_old=True):   2.7% (2)
  (denominator n)                                   : 74
Zep (invalid_at, expired_at) on gt_new edge
  valid                                             :  79.7% (59)
  temporal-extraction                               :  17.6% (13)
  missing                                           :   2.7% (2)
  (denominator n)                                   : 74
  note: expired_at MISSING — cloud data pre-patch; contradicted vs temporal-extraction cannot be distinguished
ours(full) pool composition
  both_kept                                         :  97.3% (72)
  gt_new_dropped_gt_old_kept                        :   2.7% (2)
  (denominator n)                                   : 74
ours(no_p5) pool composition
  gt_new_only_kept                                  :  63.5% (47)
  both_kept                                         :  33.8% (25)
  gt_new_dropped_gt_old_kept                        :   2.7% (2)
  (denominator n)                                   : 74
ours(struct) pool composition
  gt_new_only_kept                                  :  63.5% (47)
  both_kept                                         :  33.8% (25)
  gt_new_dropped_gt_old_kept                        :   2.7% (2)
  (denominator n)                                   : 74
ours(p3_only) pool composition
  both_kept                                         :  97.3% (72)
  gt_new_dropped_gt_old_kept                        :   2.7% (2)
  (denominator n)                                   : 74
```

## Length = 32k

### Zep cumulative-state audit
```
  n_files                                 : 100
  n_edges_observed_union                  : 689
  n_p1_facts                              : 2309
  ratio_edges_over_p1                     : 0.29839757470766565
  expired_at_present_in_data              : False
  verdict                                 : N/A (Zep top-10 per query — full graph dump needed for definitive audit)
```

**N_query = 65** (from sh_32k_mquake_analysis.json has_pair)
**N_bank = 638** (from ours P1 triple cache, (S,P) with ≥2 distinct objects)

### M1 (denominator = N_query, n=65)
```
ours (by construction)
  NFPR                                              : 100.0%
  OFPR                                              : 100.0%
  BSPR                                              : 100.0%
  DLR                                               :   0.0%
  (denominator n)                                   : 65
  note: by construction (conservative-ADD, no cross-item LLM judgment)
mem0+P1(b) — write-time destructive commit
  NFPR                                              :  55.4%
  OFPR                                              :  38.5%
  BSPR                                              :  21.5%
  DLR                                               :  44.6%
  (denominator n)                                   : 65
Zep (cloud, top-10 union of per-query edges)
  NFPR                                              :  90.8%
  OFPR                                              :  87.7%
  BSPR                                              :  80.0%
  DLR                                               :   9.2%
  (denominator n)                                   : 65
  note: top-10 union (upper-bound; true bank state may be lower)
```

### M1 (denominator = N_bank, n=638)
```
ours (by construction)
  NFPR                                              : 100.0%
  OFPR                                              : 100.0%
  BSPR                                              : 100.0%
  DLR                                               :   0.0%
  (denominator n)                                   : 638
  note: by construction (conservative-ADD, no cross-item LLM judgment)
mem0+P1(b) — write-time destructive commit
  NFPR                                              :  38.2%
  OFPR                                              :  50.8%
  BSPR                                              :  16.6%
  DLR                                               :  61.8%
  (denominator n)                                   : 638
Zep (cloud, top-10 union of per-query edges)
  NFPR                                              :  29.8%
  OFPR                                              :  31.0%
  BSPR                                              :  20.4%
  DLR                                               :  70.2%
  (denominator n)                                   : 638
  note: top-10 union (upper-bound; true bank state may be lower)
```

### M2 (pool state per query)
```
ours(full)
  PP-New                                            :  61.5%
  PP-Both                                           :  32.3%
  PP-OldOnly                                        :   4.6%
  PP-Missing                                        :   1.5%
  (denominator n)                                   : 65
ours(no_p5)
  PP-New                                            :  61.5%
  PP-Both                                           :  32.3%
  PP-OldOnly                                        :   4.6%
  PP-Missing                                        :   1.5%
  (denominator n)                                   : 65
ours(struct)
  PP-New                                            :  49.2%
  PP-Both                                           :  44.6%
  PP-OldOnly                                        :   4.6%
  PP-Missing                                        :   1.5%
  (denominator n)                                   : 65
ours(p3_only)
  PP-New                                            :  60.0%
  PP-Both                                           :  33.8%
  PP-OldOnly                                        :   4.6%
  PP-Missing                                        :   1.5%
  (denominator n)                                   : 65
mem0+P1(b) (raw top-100)
  PP-New                                            :  33.8%
  PP-OldOnly                                        :  16.9%
  PP-Both                                           :  21.5%
  PP-Missing                                        :  27.7%
  (denominator n)                                   : 65
Zep (top-10 edges)
  PP-Both                                           :  95.4%
  PP-Missing                                        :   1.5%
  PP-New                                            :   1.5%
  PP-OldOnly                                        :   1.5%
  (denominator n)                                   : 65
```

### M3 (root-cause attribution)
```
mem0+P1(b) LLM event distribution on gt_new (rigorous bucket rules)
  Ambiguous(ADD|final_new=True,final_old=False)     :   9.2% (6)
  Ambiguous(ADD+UPDATE|final_new=False,final_old=True):   7.7% (5)
  Ambiguous(ADD+DELETE+UPDATE|final_new=True,final_old=True):  12.3% (8)
  DELETE_dropped_new                                :   7.7% (5)
  Ambiguous(ADD|final_new=False,final_old=True)     :   4.6% (3)
  Ambiguous(ADD+DELETE|final_new=True,final_old=False):   9.2% (6)
  Ambiguous(ADD|final_new=False,final_old=False)    :   3.1% (2)
  UPDATE_kept_new                                   :  15.4% (10)
  Ambiguous(ADD+DELETE+UPDATE|final_new=False,final_old=True):   3.1% (2)
  ADD_both_coexist                                  :   4.6% (3)
  DELETE_lost_new                                   :   9.2% (6)
  Ambiguous(ADD+UPDATE|final_new=False,final_old=False):   1.5% (1)
  NONE_silent                                       :   6.2% (4)
  Ambiguous(ADD+UPDATE|final_new=True,final_old=True):   4.6% (3)
  Ambiguous(ADD+DELETE|final_new=False,final_old=True):   1.5% (1)
  (denominator n)                                   : 65
Zep (invalid_at, expired_at) on gt_new edge
  valid                                             :  90.8% (59)
  missing                                           :   3.1% (2)
  temporal-extraction                               :   6.2% (4)
  (denominator n)                                   : 65
  note: expired_at MISSING — cloud data pre-patch; contradicted vs temporal-extraction cannot be distinguished
ours(full) pool composition
  both_kept                                         :  96.9% (63)
  gt_new_dropped_gt_old_kept                        :   3.1% (2)
  (denominator n)                                   : 65
ours(no_p5) pool composition
  gt_new_only_kept                                  :  49.2% (32)
  both_kept                                         :  44.6% (29)
  gt_new_dropped_gt_old_kept                        :   4.6% (3)
  neither_in_pool                                   :   1.5% (1)
  (denominator n)                                   : 65
ours(struct) pool composition
  gt_new_only_kept                                  :  49.2% (32)
  both_kept                                         :  44.6% (29)
  gt_new_dropped_gt_old_kept                        :   4.6% (3)
  neither_in_pool                                   :   1.5% (1)
  (denominator n)                                   : 65
ours(p3_only) pool composition
  both_kept                                         :  96.9% (63)
  gt_new_dropped_gt_old_kept                        :   3.1% (2)
  (denominator n)                                   : 65
```

## Length = 64k

### Zep cumulative-state audit
```
  n_files                                 : 100
  n_edges_observed_union                  : 794
  n_p1_facts                              : 4570
  ratio_edges_over_p1                     : 0.1737417943107221
  expired_at_present_in_data              : False
  verdict                                 : N/A (Zep top-10 per query — full graph dump needed for definitive audit)
```

**N_query = 66** (from sh_64k_mquake_analysis.json has_pair)
**N_bank = 1299** (from ours P1 triple cache, (S,P) with ≥2 distinct objects)

### M1 (denominator = N_query, n=66)
```
ours (by construction)
  NFPR                                              : 100.0%
  OFPR                                              : 100.0%
  BSPR                                              : 100.0%
  DLR                                               :   0.0%
  (denominator n)                                   : 66
  note: by construction (conservative-ADD, no cross-item LLM judgment)
mem0+P1(b) — write-time destructive commit
  NFPR                                              :  60.6%
  OFPR                                              :  48.5%
  BSPR                                              :  22.7%
  DLR                                               :  39.4%
  (denominator n)                                   : 66
Zep (cloud, top-10 union of per-query edges)
  NFPR                                              :  93.9%
  OFPR                                              :  87.9%
  BSPR                                              :  81.8%
  DLR                                               :   6.1%
  (denominator n)                                   : 66
  note: top-10 union (upper-bound; true bank state may be lower)
```

### M1 (denominator = N_bank, n=1299)
```
ours (by construction)
  NFPR                                              : 100.0%
  OFPR                                              : 100.0%
  BSPR                                              : 100.0%
  DLR                                               :   0.0%
  (denominator n)                                   : 1299
  note: by construction (conservative-ADD, no cross-item LLM judgment)
mem0+P1(b) — write-time destructive commit
  NFPR                                              :  48.3%
  OFPR                                              :  51.7%
  BSPR                                              :  20.1%
  DLR                                               :  51.7%
  (denominator n)                                   : 1299
Zep (cloud, top-10 union of per-query edges)
  NFPR                                              :  21.0%
  OFPR                                              :  21.2%
  BSPR                                              :  12.0%
  DLR                                               :  79.0%
  (denominator n)                                   : 1299
  note: top-10 union (upper-bound; true bank state may be lower)
```

### M2 (pool state per query)
```
ours(full)
  PP-New                                            :  57.6%
  PP-Both                                           :  34.8%
  PP-OldOnly                                        :   7.6%
  (denominator n)                                   : 66
ours(no_p5)
  PP-New                                            :  57.6%
  PP-Both                                           :  34.8%
  PP-OldOnly                                        :   7.6%
  (denominator n)                                   : 66
ours(struct)
  PP-Both                                           :  50.0%
  PP-New                                            :  45.5%
  PP-OldOnly                                        :   4.5%
  (denominator n)                                   : 66
ours(p3_only)
  PP-New                                            :  54.5%
  PP-Both                                           :  37.9%
  PP-OldOnly                                        :   7.6%
  (denominator n)                                   : 66
mem0+P1(b) (raw top-100)
  PP-New                                            :  37.9%
  PP-OldOnly                                        :  25.8%
  PP-Both                                           :  22.7%
  PP-Missing                                        :  13.6%
  (denominator n)                                   : 66
Zep (top-10 edges)
  PP-Both                                           :  93.9%
  PP-New                                            :   1.5%
  PP-OldOnly                                        :   4.5%
  (denominator n)                                   : 66
```

### M3 (root-cause attribution)
```
mem0+P1(b) LLM event distribution on gt_new (rigorous bucket rules)
  UPDATE_kept_new                                   :  15.2% (10)
  Ambiguous(ADD+UPDATE|final_new=False,final_old=True):   9.1% (6)
  DELETE_dropped_new                                :  10.6% (7)
  Ambiguous(ADD|final_new=False,final_old=True)     :   9.1% (6)
  Ambiguous(ADD+UPDATE|final_new=True,final_old=True):   7.6% (5)
  Ambiguous(ADD|final_new=True,final_old=False)     :  21.2% (14)
  Ambiguous(ADD+DELETE+UPDATE|final_new=True,final_old=True):  13.6% (9)
  Ambiguous(ADD+DELETE|final_new=True,final_old=False):   1.5% (1)
  DELETE_lost_new                                   :   6.1% (4)
  Ambiguous(ADD|final_new=False,final_old=False)    :   1.5% (1)
  ADD_both_coexist                                  :   1.5% (1)
  Ambiguous(ADD+DELETE+UPDATE|final_new=False,final_old=True):   1.5% (1)
  NONE_silent                                       :   1.5% (1)
  (denominator n)                                   : 66
Zep (invalid_at, expired_at) on gt_new edge
  valid                                             :  93.9% (62)
  temporal-extraction                               :   1.5% (1)
  missing                                           :   4.5% (3)
  (denominator n)                                   : 66
  note: expired_at MISSING — cloud data pre-patch; contradicted vs temporal-extraction cannot be distinguished
ours(full) pool composition
  both_kept                                         :  95.5% (63)
  gt_new_dropped_gt_old_kept                        :   4.5% (3)
  (denominator n)                                   : 66
ours(no_p5) pool composition
  both_kept                                         :  50.0% (33)
  gt_new_only_kept                                  :  45.5% (30)
  gt_new_dropped_gt_old_kept                        :   4.5% (3)
  (denominator n)                                   : 66
ours(struct) pool composition
  both_kept                                         :  50.0% (33)
  gt_new_only_kept                                  :  45.5% (30)
  gt_new_dropped_gt_old_kept                        :   4.5% (3)
  (denominator n)                                   : 66
ours(p3_only) pool composition
  both_kept                                         :  95.5% (63)
  gt_new_dropped_gt_old_kept                        :   4.5% (3)
  (denominator n)                                   : 66
```
