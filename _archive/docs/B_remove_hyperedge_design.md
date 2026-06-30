# B — Remove Phase 1 Hyperedge: Design Doc

**Last updated**: 2026-05-24
**Status**: 待 user 拍板 code change
**對應**: `docs/engineering_todos_v2.0.2.md` E2

---

## §1. 為什麼移除

| 證據 | 數字 |
|---|---|
| W2 Step 1 實測:加 hyperedge 前後 entity-entity 邊數 | 996 → **996**(零增量) |
| 根因 | FC atomic proposition 剛好 2 個 entity → hyperedge 退化成 fact edge → **100% 重複 dict key** |
| 結論 | **不是 bug,是 atomic-prop regime 下的結構必然**;留著只是混淆 method narrative |

→ 撤掉乾淨,paper 不必再解釋一個沒效果的層。

---

## §2. 程式碼現況

**Call site**:`methods/hipporag/HippoRAG.py:336-348`

```python
# ===== W2 I3c (option B): PropRAG-style proposition hyperedges =====
# For each proposition p, add entity-entity edges between every pair of
# entities in p (treating the proposition as an implicit hyperedge).
# No proposition KG node is added (option B, out-of-KG).
# Reference: PropRAG.py:944-995 add_proposition_edges_with_entity_connections
# Spec §B.14 W2 Step 1d.
n_hyperedges = 0
if getattr(self.global_config, 'enable_phase2_chain_detection', False):
    n_hyperedges = self._add_proposition_hyperedges_to_stats()

if num_new_chunks > 0 or n_hyperedges > 0:
    logger.info(...)
    self.add_synonymy_edges()
    self.augment_graph()
    self.save_igraph()
```

**Function definition**:`HippoRAG.py:1289`(`_add_proposition_hyperedges_to_stats`, ~52 行)

**現行 flag**:`enable_phase2_chain_detection`(同時控制 hyperedge **跟** 主 Phase 2 chain enumeration)

---

## §3. 改動方案

### 3.1 改動的具體內容

**(a)** 把 hyperedge call 從 `enable_phase2_chain_detection` flag **解耦** → 加一個專屬 flag `enable_proposition_hyperedge`,**default False**

**(b)** 把 call site 改為:

```python
# ===== W2 I3c (option B): PropRAG-style proposition hyperedges =====
# DEPRECATED 2026-05-24: empirically adds 0 edges on FC corpus (atomic-prop
# regime: 2 entities/prop → hyperedge ≡ fact edge → 100% duplicate).
# Kept for future non-atomic-prop datasets. Default OFF.
n_hyperedges = 0
if getattr(self.global_config, 'enable_proposition_hyperedge', False):
    n_hyperedges = self._add_proposition_hyperedges_to_stats()
```

**(c)** `config_utils.py` 加新 flag:

```python
enable_proposition_hyperedge: bool = field(
    default=False,
    metadata={"help": "W2 I3c: PropRAG-style proposition hyperedges. DEPRECATED on FC "
                      "(atomic-prop regime adds 0 edges, verified 996→996). "
                      "Default OFF. Re-enable only on multi-entity-per-prop datasets."}
)
```

**(d)** **保留** `_add_proposition_hyperedges_to_stats()` 函數本體 + 加 DEPRECATED 註解,供未來實驗用。**不刪 code**,只是不再呼叫。

### 3.2 為何不直接刪函數?

| 理由 | |
|---|---|
| 可逆 | 將來若換非 atomic-prop dataset,可重啟此設計;函數已測試過,留著免重寫 |
| Paper appendix 引用 | 可能需要在 paper 講「我們試過 hyperedge,實證在 FC 無效」,留 code 才方便讀者驗證 |
| `_v2_phase2_pipeline` 內部會走 prop_ppr_mass 邏輯,目前 active_region 算 mass 用「entity PPR 加總」**並未依賴 hyperedge 本身**(hyperedge 是 augment_graph 階段的圖結構改動,跑完 PPR 才用)→ 函數不被呼叫不影響其他 path |

### 3.3 改動範圍精確列

| 檔案 | 行數 | 改什麼 |
|---|---|---|
| `methods/hipporag/HippoRAG.py` | 336-345 | flag 名稱 `enable_phase2_chain_detection` → `enable_proposition_hyperedge`,加 DEPRECATED 註解 |
| `methods/hipporag/HippoRAG.py` | 1289 附近(函數 docstring)| 加 DEPRECATED 標記 + 引述本 doc |
| `methods/hipporag/utils/config_utils.py` | 加 `enable_proposition_hyperedge` flag(default False) | 不刪舊 flag `enable_phase2_chain_detection`(它仍控制主 Phase 2 chain detection)|
| `docs/PROVENANCE.md` | §2.1 補一行「2026-05-24 hyperedge call de-coupled,default OFF」 | 變更紀錄 |

→ **改動 ~10 行,純 Python**,**演算法、prompt、agent.py、config yaml 一個字都不動**。

---

## §4. 預期影響

| 跑哪個 ablation | hyperedge 跑嗎 | 預期 EM | 偏差容忍 |
|---|---|---|---|
| Ablation A(vanilla,所有 flag False) | ❌(本來就 default OFF) | 17%(同前) | 0pp |
| Ablation B(Phase 2 開,`enable_phase2_chain_detection=True`) | **改動前**:跑(零增量) → **改動後**:**不跑** | **31% ± 1pp** | ≤ 1pp 才算 OK(理論上應該完全 0 diff) |
| Ablation C(W3 全開) | 同 B | 31% ± 1pp | ≤ 1pp |
| Ablation D(W3 minimal) | 同 B | 15% ± 1pp | ≤ 1pp |

**Why "理論上 0 diff"**:資料說 hyperedge 加 0 邊,所以圖結構不變,PPR 不變,retrieval 不變,verdict/filter 不變,EM **嚴格相等**。

**Why "± 1pp 容忍"**:LLM call 有隨機性(temp=0.7),即使輸入完全相同,Gemini 偶爾回不同答案 → 跨 run 1-2 題 EM diff 屬正常。

---

## §5. 驗證方案

**最小驗證**:re-run **ablation B 一次**,看 EM 是不是 31% ± 1pp。
- 工程改動 ~10 行,等同零變化
- 跑時間:~1.5 hr GPU
- 通過條件:EM ∈ [30%, 32%]

**理想驗證**:再 re-run A 一次,確認 A 沒受影響(預期 17% ± 1pp)。
- 但 A 本來就不會碰 hyperedge 邏輯(flag 已 False)→ **可省略**

**不建議**:re-run C/D。Phase 3 那層的隨機性高,意義不大。

---

## §6. 風險

| 風險 | 發生條件 | 應對 |
|---|---|---|
| B re-run EM 不是 31% ± 1pp(例如掉到 25 或飆到 35) | 表示 hyperedge 其實有非零影響,或我們上次 B run 有 bug | 不 merge,先 debug |
| 改動破壞其他 Phase 2 邏輯 | flag 改名或拼錯 | smoke test 1-query 先驗 |
| Git 衝突 | 跟未來改 HippoRAG.py 的工作搶 line | 改動小 + git mv 保留 history,衝突可控 |
| 文件不同步 | PROVENANCE / engineering_todos / spec.md 沒更新 | 一個 commit 內全更新 |

---

## §7. 執行步驟

| Step | 內容 | 需要 user OK 嗎? |
|---|---|---|
| 1 | 改 `HippoRAG.py:336-345`(call site flag 解耦)+ `_add_proposition_hyperedges_to_stats` docstring 加 DEPRECATED | ✅ 看到 design 後 OK |
| 2 | 改 `config_utils.py` 加 `enable_proposition_hyperedge` 新 flag(default False) | 同 |
| 3 | smoke test:`python -c "from methods.hipporag import HippoRAG; print('import ok')"` 確認沒 broken | 同 |
| 4 | 更新 `docs/PROVENANCE.md` + `docs/engineering_todos_v2.0.2.md`(E2 mark 進行中) | 同 |
| 5 | git commit: `chore(hipporag): de-couple hyperedge call (data-verified zero increment)` | 同 |
| 6 | **GPU re-run ablation B 100Q** | **要 user 明確說 OK** |
| 7 | 收結果,若 EM ∈ [30%, 32%] → mark E2 DONE,進 C | 視結果 |

---

## §8. 回滾方式

任何 commit 都可 `git revert <hash>`。`enable_proposition_hyperedge=True` 環境變數可即時 re-enable 函數(若有人想跑舊版)。

---

## §9. 相關文件

- `docs/PROVENANCE.md` §2.1 — 演算法層改動清單
- `docs/method_design_v2.0.2_spec.md` §B.14 — W2 Step 1d 原 spec
- `docs/method_v2.0.2_status_brief.md` — 方法現況
- `docs/engineering_todos_v2.0.2.md` E2
