# need_discuss/ — 中途實驗 / appendix candidate / 未定案

> 見 [`../paper_current/README.md`](../paper_current/README.md) 的分流規則。
> 這裡收**尚未確定進 paper body 的內容**:中途 metric 探索、appendix candidate、探索性圖、rollup analysis。
> **判為 body 必需** → 移到 [`../paper_current/`](../paper_current/) 對應子夾;**判為 appendix** → 留這裡直到 paper body 章節穩住。

---

## 分流原則(從 paper_current README 摘要)

進本資料夾的判準是「**尚未定案** OR **不確定進 paper body 哪一節**」。常見狀況:
- 中途 metric 探索(如 M1 bank state 全 baseline 表)— appendix candidate,body 定位不明確
- diagnostic 圖(非 body 主圖的變體)
- 未定案的 baseline(如 Deterministic pointer,還在討論)
- rollup 分析檔(給團隊 review 用,不是給 reviewer 看)

## 判斷是否搬進 `paper_current/`

**兩個條件都要成立**:
1. **對應到 paper body 某章某節某段**(intro / related_work / method / experiments / discussion 有明確位置)
2. **內容已定案**(數字已跑過、caption 寫過、論述邏輯 stable)

只要有一個不成立 → 留在這裡。

---

## 目前收到什麼

*(初始空)*

**未來會放進來的例子**:
- `m1_m2_m3_results.md`(全 bank state / pool state 完整 metric 結果,未來 appendix 用)
- `mem0_dest_write_event_attribution.md`(mem0 M3 write-event 5-bucket 分析,appendix 佐證用)
- 各種 diagnostic 圖(非 body 主圖的變體)
- Matcher precision audit 30×3 樣本結果

**這些目前住在 `docs/handoff/`**,paper body 章節穩住後決定去留:
- `docs/handoff/m1_m2_m3_results.md`
- `docs/handoff/mem0_dest_write_event_attribution.md`
- `docs/handoff/experiment_results_shared.md`(跨機器實驗 log,永久留 handoff/)
- `docs/handoff/reproduction_log_*.md`(每台機器 reproduction 紀錄,永久留 handoff/)
