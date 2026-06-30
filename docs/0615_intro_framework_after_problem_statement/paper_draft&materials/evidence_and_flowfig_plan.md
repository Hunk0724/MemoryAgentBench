# Evidence 圖 + Flow 圖 更新計畫(2026-06-27 反思)

> 設計原則(見 `figures_current/idea_for_*`):figure **self-contained**、caption **三段論(what / observation / implication)**、最佳 bold、軸帶單位、colorblind。
> Observation 要**找 pattern + hypothesis**,Discussion 誠實談 limitation/failure。

---

## Part A — Evidence 圖(「為什麼我們贏」的機制材料,扣 narrative arc)

光「整體表現好」(Table 1 / F_robust)不夠;要把 **intro 的因果鏈逐段量化**。這正是 `evidence_figures/` 那組(F1/F2/F_L1L2/F4)的精神,但要 **(i) 用現役 P1+raw-q 數據重算、(ii) 從「ours vs vanilla」擴成全方法(+mem0(b)/Zep/LCA)**。

因果鏈 = **寫入後 store 狀態 → 檢索回的狀態 → 解析後 context 狀態 → state→Acc**:

| # | Evidence 圖 | 對應舊範本 | 顯示什麼 | 數據狀態 |
|---|---|---|---|---|
| **E1** | **Write-time store 狀態**(各方法寫入後,has_pair 的新/舊版在不在 store) | F1_store_shrinkage | ours **新舊都留**(可逆);mem0(b)/vanilla **破壞性刪除/沒抽到**(不可逆);Zep edges 兩版都在但 invalid_at 少標 | ours✓;**baselines 待抽 store 狀態**(probe 各 store/graph) |
| **E2** | **檢索回的 GT_new/GT_old recall**(has_pair 四態 both/new/old/neither) | F2 / F_L1_retrieved_state | ours both ~98-100%(raw-q);vanilla neither;mem0(b) old_only/neither(新版已刪);Zep 看 edges | ours✓(diag D1);**baselines 待算** |
| **E3** | **ours 解析後 context 狀態**(both→new_only clean) | F_L2_resolved_state | ours 把 both 收斂成 new_only(query-time 解析價值) | ours✓(diag D2b) |
| **E4** | **各方法 final-context 狀態 → Acc**(state→EM) | F4_state_to_em | 答對幾乎全由「最終 context 有沒有新版、有沒有混舊版」決定 | 可從各方法存的檢索/context json + exact_match 算 |
| **E5** | **final-context 純度(ours vs Zep 多顆粒)** | (新) | Zep 整體系統把舊版從 raw episodes 漏回 context → 污染答題;ours context 乾淨 | Zep 檢索 json 分顆粒度資料✓;ours✓ |

**關鍵賦能任務**:寫一支**「各方法 L1/L2/L3 state 抽取器」**——讀每個方法存的 retrieved/context json + GT,輸出 {both/new/old/neither}(L1)、final-context 狀態(L2)、state×EM(L3)。`diag_fc_errormodes.py` 已對 ours 做了,**推廣到 vanilla/mem0(b)/LCA/Zep** 即可。然後仿 `make_figures.py` 用現役數據重繪 E1–E5。

**每圖 caption(三段論)範例(E2)**:
> **Figure (E2).** *FC-SH has_pair 題的檢索態(top-k,raw question),每方法分 {both/new/old/neither}。* ours 在各長度 both≈98-100%,而破壞性 baseline(mem0)隨長度 old_only/neither 升高。*暗示*:ours 把新舊版都留在 store→檢索可救;破壞性寫入在 write-time 即不可逆地丟掉新版。

---

## Part B — Flow 圖更新 spec(以現役 code 為準;PNG 無 source,逐框改動如下)

### B1. `Methodology_ours_Overview.png`(method 章節 overview)— **需明顯修**
現況 → 應改:
1. **【最大缺漏】query-time 缺 conflict-type classifier**:在「Identity grouping」與「Temporal resolution」之間**插入新框**:
   **`Conflict-type classification {NO_CONFLICT / FRESHNESS / COMPLEMENTARY}`**(per-group, query-aware, Cattan'25);**只有 FRESHNESS → Temporal resolution(丟舊)**;NO_CONFLICT / COMPLEMENTARY → **keep all**(不丟)。
2. **「Temporal resolution: timestamp argmax」→ 改「ordinal argmax(ingestion order)」**(現役用 ordinal,非 timestamp)。
3. **「Retrieve: Semantic top-k」→ 註明「raw-question, semantic top-100」**(raw-q 是現役組件)。
4. **Identity grouping 標明 conditional routing**:Structural(同 (S,P) ≥2,確定性、免 LLM)vs LLM-based(其餘 dynamic_pool)= **互斥分流**,非兩道都跑。
5. 誠實點:寫入端的 **(S,P) 倒排索引 JSON 目前 query-time 未用到**(routing 讀 payload 內 triple)→ 圖上若有獨立 index 框可移除或註記。

### B2. `introduction_framework_abstract.png`(intro abstract,高層次)— **微調**
- 大致正確(conservative structural commit + query-time conflict resolution + unified store all-versions)。
- 唯一建議:「Conflict Resolution」內 `Identity grouping → Temporal resolution` **補上 conflict-type 判斷**(至少加一個 `conflict-type?` 菱形,FRESHNESS 才 resolve),以免讀者誤以為「同群就一定丟舊」。其餘不動。

### B3. `Methodoloty_mem0_framework.png`(baseline 對照)— 待核
- 應呈現 mem0 的 **coupled 破壞性更新(`DEFAULT_UPDATE_MEMORY_PROMPT` → ADD/UPDATE/DELETE)**;若已是則不動。可加一句「write-time LLM 判斷 = 唯一且不可逆的錯誤源」對比我方。

> **執行選項**:flow 圖我可 (a) 給此 spec 由你在 drawio/PPT 改;或 (b) 用 matplotlib 重畫(風格未必一致)。建議 (a)。

---

## 建議下一步(優先序)
1. **寫「各方法 L1/L2/L3 state 抽取器」**(推廣 diag)→ 出 E1–E4 數據。← 賦能所有 evidence 圖,最高槓桿。
2. 仿 make_figures 用現役數據重繪 E1–E5(取代過時 evidence_figures)。
3. flow 圖 B1/B2 按 spec 更新(你改 or 我 matplotlib 重畫)。
4. (待跑)能力軸 dose-response、LongMemEval = intro ③ 與 Zep 主戰場的決定性材料。
