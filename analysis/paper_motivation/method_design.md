# Method Design — Abstract Functional Requirements + Instances

> **目的**: 不被特定實作綁住,先列**抽象 functional requirements** (要做到什麼),再列**多種具體 instance** (怎麼做到),最後記錄每個 experiment 在 design space 中的位置。
>
> 建立日期: 2026-05-05
> 對應: motivation_narrative.md (claim 與 evidence 出處)

---

## §1 兩 phase 對應兩 claim

| Phase | 對應 motivation claim | 抽象目標 |
|---|---|---|
| **Phase 1** | **Claim 1** — query-related chain_old 在 retrieval 中是主要失敗源 | **減少 LLM context 中 query-related 的 stale fact**(不論用什麼機制) |
| **Phase 2** | **Claim 2** — LLM 在乾淨 context 上仍需結構化引導 | **給 LLM 結構化 signal 讓多跳 reasoning 穩定**(不論用什麼形式) |

剩餘 17pp gap (PureChain 97%) 屬 retrieval coverage / parametric leakage,不在範圍。

---

## §2 Phase 1 — Functional Requirements (抽象層)

### §2.1 Functional 目標
**對於 incoming new fact,系統要能識別「既有 KG 中哪些 fact 與此 new fact 衝突」,並讓這些 stale fact 在後續 query 不影響 LLM。**

可拆成兩個子功能:

#### F1.1 衝突偵測 (detection)
> 判斷 new fact 跟既有 KG 中哪些 fact 矛盾。

| 抽象 signal source | 可能 instance |
|---|---|
| **時序 (temporal)** | ingestion order / timestamp / version number |
| **結構 (structural)** | KG edge constraint: 同 (S, R) 不同 O |
| **語義 (semantic)** | LLM judge: new vs top-K existing → contradiction? |
| **混合 (hybrid)** | 結構 + 語義 fallback / 結構 + 時序 hybrid |

#### F1.2 衝突訊號的儲存方式 (signal representation)
> 偵測到衝突後,把訊號存哪裡讓 query 階段能用。

| 抽象選項 | 可能 instance |
|---|---|
| **直接刪除舊 fact** | Mem0 UPDATE (覆寫) / Mem0 DELETE |
| **加 metadata 標記** | Zep `invalid_at` timestamp / superseded_by edge |
| **建立版本化記憶結構** | versioned KG (active edges + archived edges 分開索引) |
| **分層記憶** | 多層 store: hot (current) / warm (recent) / cold (archived) |

### §2.2 Phase 1 已測 / 待測 instances

| Instance | F1.1 機制 | F1.2 儲存 | Paradigm | 狀態 |
|---|---|---|---|---|
| **V0** (done) | 結構: 同 (S, R) 不同 O cross-chunk + 時序: 後 chunk 勝 | 不修 KG, 純 read-time excise | A 純結構 | ✅ EM 44% |
| V1a | V0 + entity/relation alias normalization | 同上 | A 純結構 | ⏳ |
| V1b | V0 + same-chunk conflict (用 chunk 內順序) | 同上 | A 純結構 | ⏳ |
| V2a | LLM judge 仿 Mem0 UPDATE_MEMORY_PROMPT | 直接刪舊 fact | B 純語義 | ⏳ |
| V2b | LLM judge 仿 Zep dedupe_edges | 加 invalid_at metadata | B 純語義 | ⏳ |
| V3 | V1 高信心 + V2 fallback for ambiguous | 混合 metadata + 刪除 | C hybrid | ⏳ |
| V4 | versioned KG (active vs archived edges) | 結構化分層 | 全新架構 | ⏳ |

---

## §3 Phase 2 — Functional Requirements (抽象層)

### §3.1 Functional 目標
**給 LLM 一個結構化 signal,讓它在多跳推理中穩定地: (a) 從 retrieved context 抓對 fact, (b) 不在中途 regress 到 OLD, (c) 每 hop 都有 verification anchor。**

可拆成兩個子功能:

#### F2.1 給 LLM 的 signal 形式 (scaffold type)

| 抽象 signal | 可能 instance | 已知 evidence |
|---|---|---|
| **格式約束** (force LLM 寫某格式) | trailer "Intermediate answers: [a, b, c]" | OA2 +28pp ✅ |
| **引用要求** (force LLM cite 來源) | V2 cite-source: "X (from fact 146)" | OA2 +30pp ✅ |
| **拆解要求** (先列 sub-question) | V3 decompose: "Sub-questions: 1...2..." | OA2 +31pp ✅ |
| **子圖注入** (inject query-relevant KG subgraph) | KG: 從 query entities 出發抽 N-hop 子圖,放 prompt | ⏳ 未測 |
| **預計算 chain** (pre-execute multi-hop, present chain) | sequential per-hop retrieval → 把 chain 給 LLM | ⏳ 未測 |
| **逐跳迭代** (iterative retrieval per hop) | 每 hop 各自 retrieve, ground hop 結果, 餵下 hop | ⏳ 未測 |

#### F2.2 信號注入時機 (where in pipeline)

| 抽象 | 可能 instance |
|---|---|
| Inference prompt 加文字 | trailer / cite / decompose 都屬此 |
| Context 重組 | RPT-style sections (active/superseded) |
| Multi-step pipeline | sequential decomposition |

### §3.2 Phase 2 已測 / 待測 instances

| Instance | F2.1 scaffold | F2.2 注入 | 已知 evidence |
|---|---|---|---|
| **trailer (V1)** ✅ | 格式約束 | inference prompt | OA2 55→83 = +28pp |
| **cite-source (V2)** ✅ | 引用要求 | inference prompt | OA2 55→85 = +30pp |
| **decompose (V3)** ✅ | 拆解要求 | inference prompt | OA2 55→86 = +31pp |
| **subgraph-injection (V4)** ⏳ | 子圖注入 | inference prompt | 預期效益: high (KG-native) |
| **sequential per-hop retrieval (V5)** ⏳ | 預計算 chain / 逐跳迭代 | multi-step pipeline | 預期效益: very high (避開 satellite leak) |
| **RPT-style sections (V6)** ⏳ | context 重組 | context structure | 已有 RPT 數據 (orig 68%) |

### §3.3 為什麼 V4 (subgraph-injection) / V5 (sequential retrieval) 重要

你提的點很對 — V4/V5 比 trailer/cite/decompose **更 generalize**:
- 不依賴特定 prompt 文字
- 利用 KG 結構本身的 query-aware reasoning
- 對非 FC 任務 (LongMemEval / MemBench / BEAM) 也適用,因為任何 KG 記憶都能抽 subgraph
- 實際上是在 retrieve 階段就做 chain-aware,等於同時補 §1.5 提的 "retrieval coverage" 弱點 (HippoRAG PPR 是 entity-level random walk,不是 hop-by-hop)

---

## §4 Design Space 視覺化

```
                       Phase 1 (filter)              Phase 2 (reasoning guide)
                     ┌──────────────────┐         ┌─────────────────────────┐
        F1.1 detect: │ A 結構 (V0/V1)   │   F2.1: │ 格式 (trailer)         │
                     │ B 語義 (V2)      │         │ 引用 (cite)            │
                     │ C hybrid (V3)    │         │ 拆解 (decompose)       │
                     └──────────────────┘         │ 子圖注入 (V4)          │
        F1.2 store:  ┌──────────────────┐         │ 預計算 chain (V5)      │
                     │ 刪除              │         │ 逐跳迭代 (V5)          │
                     │ metadata          │         │ context 重組 (V6)      │
                     │ versioned KG      │         └─────────────────────────┘
                     │ 分層              │
                     └──────────────────┘

最終 method = (F1.1 × F1.2) × (F2.1 × F2.2) 的某個組合
```

V0 = (F1.1=結構, F1.2=不修 KG/read-time excise) × (F2.1=無, F2.2=無) → 44%
V0+trailer = V0 + (F2.1=格式, F2.2=prompt) → 預期 60-70%

---

## §5 Experiment Log (附在 design space 下)

### Experiment 1 — V0: Pure Deterministic Edge Constraint

**Design space 位置**: F1.1=結構 + F1.2=read-time excise (不修 KG) | F2 無

**對應 claim**: Claim 1 (filter chain_old)

**狀態**: ✅ Done (2026-05-05)

**實際結果**:
- EM 44% (rule-clean 96, +23pp from vanilla 22%)
- Detection: 41% recall, 99% precision
- 拿到 OA2 oracle gain 67%
- by hops: 2-hop 52%, 3-hop 33%, 4-hop 18%

**Code**: `analysis/phase1_v0_auto_supersession.py`
**Result**: `analysis/results/diagnostic/phase1_v0_auto_supersession_mh_results.json`

**結論**:
- Paradigm A 結構偵測可行
- recall 41% 已能拿 67% gain → 偵測到的就是核心 conflict
- alias / 同 chunk 衝突沒處理 → V1 改進空間

---

### (Planned) Experiment List

#### Phase 1 改進路線

| ID | Design space | 主要改的 functional axis |
|---|---|---|
| V1a | F1.1: 結構 + alias norm | 推 detection recall |
| V1b | F1.1: 結構 + same-chunk handling | 推 detection recall |
| V2 | F1.1: LLM judge | 對比 paradigm B |
| V3 | F1.1: hybrid A+B | push to ceiling |
| V4-store | F1.2: versioned KG | 改 storage architecture |

#### Phase 2 改進路線

| ID | Design space | 預期 evidence value |
|---|---|---|
| V0+trailer | F2.1=格式 | 確認 Phase 1+2 組合 (~60-70%?) |
| V0+cite | F2.1=引用 | 跟 trailer 對照 |
| V0+decompose | F2.1=拆解 | 跟 trailer 對照 |
| V0+subgraph | F2.1=子圖注入 | **generalization 關鍵** — 不依賴 prompt 文字,KG 結構直接給 chain |
| V0+sequential | F2.1=逐跳迭代 | **避開 satellite leak**, 補 retrieval coverage |
| V0+RPT-sections | F2.1=context 重組 | 既有 RPT 數據可對照 |

---

## §6 待釐清研究問題 (影響實驗優先順序)

1. **V0 推到多少才算「夠好」?**
   - 對比 OA2 oracle 55%,我們要超過? 還是 close enough?

2. **F2.1 哪些 scaffold 最有效?**
   - trailer / cite / decompose 已知 +28-31pp on clean context
   - 但這些**不容易 generalize** (依賴 prompt 文字)
   - 子圖注入 / 逐跳迭代 **更 generalize**,但實作更複雜
   - 哪個值得優先做?

3. **F1.1 paradigm A vs B 的優劣**
   - 結構 (deterministic) precision 高 recall 限
   - 語義 (LLM judge) recall 高但 noisy
   - **是否應該 PaperAble pivot 為「結構為主, 語義 fallback」這條 hybrid 主張**?

4. **超出 FC scope 的 generalization 怎麼測?**
   - 需 LongMemEval-KU / MemBench / BEAM survey
   - 我們的 Phase 1 對隱式衝突 (semantic) 沒救 — 必須 Paradigm B
   - 我們的 Phase 2 對 KG-based memory 都通用

5. **同 chunk 衝突在 FC 多嚴重?**
   - 若 chunk_size=512 下 old/new 大多跨 chunk → V1b 優先順序低
   - 數據驗證: 我們 OpenIE 88 個 conflict (S, R) 中有多少是同 chunk?

---

## §7 Contribution candidates (對 paper)

```
Layer 1 contribution (機制創新):
  (a) 在 HippoRAG-v2 KG 上,deterministic edge constraint 是有效衝突偵測機制 (V0)
  (b) 結構偵測 + LLM judge fallback 的 hybrid 設計 (V3)
  (c) versioned KG + active/archived 雙層 store (V4-store)

Layer 2 contribution (整合):
  (d) Phase 1 + Phase 2 整合 method 推進到 OA2 oracle ceiling
  (e) 子圖注入 / 逐跳迭代的 chain-aware Phase 2 — generalize 到非 FC 任務

Layer 3 contribution (taxonomy / framing):
  (f) 在 explicit triple conflict scope 上,結構偵測已逼近 LLM judge ceiling
      (paradigm 建議: 不必為 FC 投資 LLM judge)
  (g) 分離 retrieval-side (Claim 1) vs inference-side (Claim 2) 失敗源
      → 對 future memory benchmark 設計有指導意義
```

最終 paper 不會全做,但這份清單讓我們選 contribution 時知道**哪幾個是 trade-off**。

---

## §8 短期決策建議

不急著動具體 V1/V2/V3,先決定**研究主軸**:

- **Path X (HippoRAG 內 incremental)**: V0 → V1 → V0+trailer → 推到 OA2 ceiling
  - 對 paper 主賣點: "deterministic edge constraint 在 HippoRAG-v2 上的有效性"
  - 缺點: 不容易 generalize 到非 FC

- **Path Y (chain-aware retrieval, KG-native)**: V0 → V0+subgraph → V0+sequential
  - 對 paper 主賣點: "KG 結構支持的 chain-aware reasoning 補 retrieval coverage 跟 reasoning stability"
  - 優點: 自然 generalize 到任何 KG 記憶

- **Path Z (paradigm comparison)**: V0 → V2 → V3 hybrid
  - 對 paper 主賣點: "在 explicit conflict scope, 結構足夠;其他 scope 需要 hybrid"
  - 適合 LongMemEval / MemBench survey 後做

選 path 之前,先決定**paper 的主賣點**是什麼,那會 pin down 下一個實驗。

---

## §9 Design Constraint: Scaffold 必須適應底層記憶系統的 retrieval format + 衝突處理哲學

> 來源: motivation_narrative.md §4.4 — 三系統不對稱反應源自兩個獨立 axis:
>   (a) retrieval format 是否含序號 (Mem0 不含,Zep 含 via episodes,HippoRAG-v2 含 via chunks)
>   (b) chain_old 處理時機 (Mem0 ingestion-time 物理刪除 vs Zep inference-time 標記 vs HippoRAG-v2 不處理)
>
> 加入日期: 2026-05-07
> 修訂日期: 2026-05-07 (修正前一輪「Zep 沒序號靠時間戳類推」的錯誤判斷,確認 Zep episodes 含原始序號)

### §9.1 觀察 — 兩條 axis 解釋三系統 EM 排序

| 系統 | retrieval 是否含序號 | chain_old 處理 | aligned MH EM |
|---|:---:|---|:---:|
| HippoRAG-v2 | ✓ (chunks) | 不處理 (vanilla) | 22% |
| **Mem0** | ✗ (paraphrased fact list) | ingestion-time 物理刪除 (UPDATE/DELETE) | **44%** |
| **Zep** | ✓ (episodes) | inference-time 標記 (`invalid_at`,不刪除) | **28%** |

→ **EM 排序 (Mem0 > Zep > HippoRAG-v2) 不能單用「序號可用性」解釋** — 否則 Mem0 (無序號) 應該最低。實際排序由 axis (b) 主導:**ingestion-time 物理刪除最有效**,因為它直接把 chain_old 從 retrieval 中移除,LLM 端負擔最低。

### §9.2 對 Phase 2 (inference-time scaffold) 設計的影響

我們 V1/V2/V3 在 OracleClean (chunks 含序號) 上的 +28-31pp gain 是**「retrieval format = chunks 含序號 + chain_old 同時可見」這個特定條件下的 evidence**。要外推到 production memory systems 須對應到目標系統的 retrieval format:

- 對 Mem0 (paraphrased + chain_old 已被 filter 大量移除): scaffold 不能依賴序號,且 retrieval 中 chain_old 可能不存在,scaffold 著力點變成「multi-hop chain 銜接的穩定性」
- 對 Zep (3-scope + chain_old 仍在): scaffold 可依賴 episodes 序號,但 LLM 還必須對 edges 時間戳 + nodes summary 做 cross-reference

### §9.3 Functional 子要求 — 跨 retrieval format 可移植性

**F2.X 跨 retrieval format portability**:
> Inference-time scaffold 必須在以下三種 retrieval format 都給出顯著 +Δ:
>   - format-A: chunks 直接 retrieve (HippoRAG-v2 風格,含序號,chain_old 並列)
>   - format-B: paraphrased fact list (Mem0 風格,無序號,chain_old 多被移除)
>   - format-C: 多 scope 並列 (Zep 風格,episodes 含序號 + edges 含時間戳,chain_old 仍在)

### §9.4 Scaffold instance 評估清單 (修正版)

對既有 V1/V2/V3 重新檢視 (基於 [pat_modified_prompt.py](../pat_modified_prompt.py), [oa2_v2_cite_source.py](../oa2_v2_cite_source.py), [oa2_v3_decompose.py](../oa2_v3_decompose.py) 真實 prompt 內容):

| Instance | 真實 prompt 行為 | 依賴序號? | format-A (chunks 含序號) | format-B (Mem0 無序號) | format-C (Zep episodes 含序號) |
|---|---|:---:|:---:|:---:|:---:|
| V1 trailer | `Intermediate answers: [a, b, c]` — 要求 LLM 顯式列每跳中間實體 | ✗ | ✓ | ✓ | ✓ |
| V2 cite-source | `cite the specific fact number ... (e.g., 'X is Y (from fact 146)')` | ✓ | ✓ | **✗** (無 fact number 可 cite) | ✓ (可 cite episodes 序號) |
| V3 decompose | `first list each reasoning hop ... as a numbered sub-question` | ✗ | ✓ | ✓ | ✓ |
| V_NEW: contradiction-aware | 引導 LLM 識別 retrieved facts 間矛盾對 + entity-level 判新舊 | ✗ | ✓ | ✓ | ✓ |

**設計 take-away**:
- **V2 cite-source** 是唯一明顯依賴序號的 instance,在 Mem0 上預期失效,因為 Mem0 retrieval 是 LLM-paraphrased fact list 無 ID 可 cite
- **V1 trailer / V3 decompose** 不依賴序號,**預期三系統都可移植但需實驗驗證** — 不是因為它們不依賴 chain-discriminative 內容,而是它們以「格式約束 / 拆解約束」操作 LLM 的 reasoning 過程,跟 retrieval format 正交
- **V_NEW** (新候選): portability-first 設計,完全不依賴 ordering metadata。在 Mem0 上仍可發揮 (引導 LLM 注意 retrieved fact 中的矛盾 entity bindings);在 Zep 上仍可作為 metadata cross-reference 之外的補強
- **重要警示**: 上述「V1/V3 三系統都 ✓」純粹是 prompt 設計推論;**實際在 Mem0/Zep retrieval 上跑 V1/V3 之前不可宣稱 portable**。V1 在 Mem0 上仍可能因 retrieval 缺 chain-discriminative 內容 (chain_old 已被 filter 刪掉) 而沒有可施力的對象,需實驗

### §9.5 對未來實驗的指引

跑任何 Phase 2 instance 時,**至少在 format-A (OA2 chunks) + format-B (Mem0 retrieval) + format-C (Zep 3-scope retrieval) 三種 format 各跑一次**,記錄 EM × format 矩陣。format 之間 EM 差距代表該 scaffold 對 retrieval format 的依賴強度,對 paper 的 generalizability 主張至關重要。同時記錄三系統的 chain_old 處理狀態(物理刪除 / 標記 / 無處理),確保 scaffold 在三種「衝突處理哲學」下都被驗證。
