# Conflict-type 分佈(freeze 自本機 cache,2026-06-30)

> ⚠️ **PROVISIONAL**:此分佈亦來自本機當前 run 的 cache。freeze 目的是**防止 gitignored cache 隨機器消失而遺失**(供敘事/結構參考);**論文最終數字應從 unified re-run(穩定機器、定版統一設定)的 cache 重算取代**(見 `EXPERIMENT_RUNLIST.md`)。

> **為何單獨存這份**:此分佈的來源 cache(`analysis/results/p1_caches/conflict_cache_p1_*.json`、`p1_caches/lme/conflict_ours_*.json`)是 **gitignored、只在本機**;機器消失需重跑 ingest 才能重生。故在此把已算好的數字 freeze 進 committed 檔,供論文 §5.3/§5.4 與未來 session 直接引用,不必重跑。
>
> **數字驗證**:本表 FC-SH 32k freshness = 1778/1861 = **95.5%**,與既有 committed `experiment_results.md:140`(「FC-SH 32k 95.5% 判 freshness」)完全一致 → cache 與已寫數字吻合。
>
> 三分類定義(per-group, query-aware;Cattan et al. 2025):`{NO_CONFLICT, FRESHNESS, COMPLEMENTARY}`;`phase2_resolve` **只在 FRESHNESS 丟舊版**,其餘全留(precision-safe)。

## FC-SH(general fact)— 各長度 conflict-type 分佈

> 統計單位 = 每個 (S,P) 群的分類判定(n = 該長度全部群數)。

| 長度 | n(群) | FRESHNESS | NO_CONFLICT | COMPLEMENTARY |
|---|---:|---:|---:|---:|
| 6k   | 2022 | 1728 (**85%**) | 251 (12%) | 43 (2%) |
| 32k  | 1861 | 1778 (**96%**) | 63 (3%)   | 20 (1%) |
| 64k  | 1752 | 1700 (**97%**) | 39 (2%)   | 13 (1%) |
| 262k | 1493 | 1460 (**98%**) | 24 (2%)   | 9 (1%)  |

**判讀**:FC-SH 的衝突幾乎全是 **FRESHNESS(85%→98%,隨長度上升)**,COMPLEMENTARY 僅 1–2% → 在 general fact 上,**`(S,P)` 結構分群 + 確定性 temporal 就是 workhorse**,LLM 的 conflict-type 分類在此資料集幾乎不改變結果。這支撐「FC-SH 的表現主要來自 structural 貢獻」的假說(→ 待 `ours_struct` ablation 量化確認)。

## LongMemEval KU(personal fact)— conflict_ours 分佈(4 shards 合併)

| shard | n | FRESHNESS | COMPLEMENTARY | NO_CONFLICT |
|---|---:|---:|---:|---:|
| s0n4 | 127 | 59 | 47 | 21 |
| s1n4 | 135 | 80 | 30 | 25 |
| s2n4 | 128 | 66 | 33 | 29 |
| s3n4 | 147 | 72 | 46 | 29 |
| **合併** | **537** | **277 (52%)** | **156 (29%)** | **104 (19%)** |

**判讀**:LongMemEval 的 **COMPLEMENTARY 高達 29%**(vs FC-SH 1–2%)→ 個人多值事實(同一 (S,P) 可同時成立多個 value:多個喜好、多段並存關係)**真的需要 conflict-type 分類**來避免把「並存值」誤當「過期值」丟掉。這解釋了**為何同一套機制能跨 benchmark**:FRESHNESS 為主時靠 structural+temporal,COMPLEMENTARY 多時靠 conflict-type 保留 → keep-all + query-time 分類是兩個 benchmark 的共同底座。

## 跨 benchmark 對比(論文 killer 對照)

| | FRESHNESS | COMPLEMENTARY | 結論 |
|---|---:|---:|---|
| FC-SH(general,asymptote) | ~97–98% | ~1% | structural+temporal 即足 |
| LongMemEval KU(personal) | 52% | 29% | 需 conflict-type 分類 |

## 重生方式(若 cache 已失)

```bash
# 重跑 ours ingest 會重建 conflict cache(會花 API+時間):
bash docs/0615_intro_framework_after_problem_statement/scripts/run_fc_sh.sh <L> ours   # FC-SH 各長度
# LME: run_lme_ku*.sh (ours)。之後以本檔頂部所述方式對 cache 的 value 計數即可。
```
