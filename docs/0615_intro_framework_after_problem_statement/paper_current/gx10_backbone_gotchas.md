# GX10 Backbone Swap — Zep / mem0 特殊 gotchas

> **目的**:GX10 跑 gemma3 backbone 於 Zep / mem0(a)/(b) 時**必須先讀**的技術要點。這些 gotcha 是 Mac gpt-4.1-mini 跑不會遇到、gemma 跑才會踩的雷。
> **搭配**:[`gx10_handoff_2026-07-05.md`](gx10_handoff_2026-07-05.md)(rigor SOP)、[`backbone_extension_plan.md`](backbone_extension_plan.md)(72-cell 矩陣 + priority)、[`methods_reproduction.md §7`](methods_reproduction.md)(canonical registry)。
> **核心概念**:「backbone 換掉」不是統一動作 —— 每個方法有**多個 LLM 位置**,換 backbone 影響哪些位置需要**明確 disclose**。

---

## §1 三個 LLM 位置 mapping(對每個 method)

| Method | LLM 位置 1(write / extraction)| LLM 位置 2(write update)| LLM 位置 3(query time)| LLM 位置 4(answer)|
| :--- | :--- | :--- | :--- | :--- |
| **ours(no_p5 / struct / p3_only)** | P1 extraction prompt | (無 destructive UPDATE)| P3 grouping + argmax | Answer LLM |
| **(a) vanilla mem0** | mem0 native FACT_RETRIEVAL_PROMPT | mem0 ADD/UPDATE/DELETE judge | (無 query resolution)| Answer LLM |
| **(b) mem0+P1** | **P1 extraction(=ours' held-fixed)** | mem0 ADD/UPDATE/DELETE judge | (無 query resolution)| Answer LLM |
| **Zep** | Zep cloud graph LLM(**未受 backbone 換掉影響**)| N/A(Zep 不 destructive)| N/A(無 query KU)| Answer LLM |

**全 swap 定義**:所有 backbone-controllable 位置都換成 gemma。**Zep cloud LLM 是 exception**(第 3 節詳談)。

---

## §2 mem0(a)vs(b)於 gemma 的差別**要精確描述**

### 2.1(a)vanilla mem0 於 gemma:**3 個 LLM 位置全 gemma**

- extraction:gemma native prompt(mem0 內建 FACT_RETRIEVAL_PROMPT)
- UPDATE 判定:gemma
- answer:gemma

**已見的 failure mode**(GX10 preliminary observation §3(a)):
- 1B / 4B store 存 **5 個「Name is John」**(**mem0 UPDATE prompt 內建 few-shot 範例**)
- 4B store **完全空(0 筆)**
- **意涵**:weak model 無法遵循 mem0 UPDATE prompt(需輸出 ADD / UPDATE / DELETE / NONE 的 JSON 結構),**照抄 prompt 範例或擺爛**

### 2.2(b)mem0+P1 於 gemma:**extraction = 換的 backbone(P1 prompt),UPDATE / answer 也是 backbone**

**這個 subtle point 要精確描述** —— 現行 run_fc_sh.sh 對(b)設 `MEM0_EXTRACTION_CACHE="$PC/extraction_cache_p1_${L}.json"`,而 `PC` 有 `TAG_SFX`(即 `p1_caches__gemma3-4b/`),所以:
- **(b) at gemma-4B 的 P1 extraction cache = gemma-4B 自己用 P1 prompt 抽出的**(**不是** gpt-4o-mini P1 cache)
- 若要真正「held-fixed extraction at gpt-4o-mini」→ 需手動 copy `p1_caches/extraction_cache_p1_6k.json` 進 `p1_caches__gemma3-4b/`(覆蓋 gemma 自抽的版本)

**paper 意涵**:
- **當前的(b)at gemma = 「同一 backbone 但 extraction prompt 換掉」**(P1 vs mem0 native),隔離 **extraction prompt 效果**
- **若要 isolate「extraction backbone 效果」**(gemma 抽 vs gpt-4o-mini 抽)→ 需要**額外 variant**(b')手動用 gpt-4o-mini cache

**建議 GX10 目前跑法**(現行 flow):
- (b)at gemma = 上述「同 backbone 內比 P1 vs native」
- 若時間充裕可加(b')「gpt-4o-mini P1 cache + gemma UPDATE / answer」→ 論文有更完整 attribution

### 2.3 有問題就馬上停,不要浪費長時間

- 若 (a) at gemma-1B ingest 結束 store 是 empty / 5 個 prompt 範例 → **這是 expected**(記入 aggregated)
- 若 (b) at gemma-1B ingest 完成但 UPDATE 判 100% ADD(沒判 UPDATE)→ **也 expected**(weak model 不判 UPDATE)
- **要 log 的**:mem0 store size 分布 (has_pair related mem0 store 有多少筆);weak model 崩到什麼程度

---

## §3 Zep 於 gemma:**Zep cloud graph LLM 不受 backbone 換掉影響**

### 3.1 Zep architecture 提醒

- **Zep cloud graph**(edge / node / episode 建構) = **Zep 內部 LLM(gemini / GPT)**,**不是 gemma**
- **Answer LLM**(讀 Zep return 的 context 答題) = 可換 gemma(via Ollama)

**paper 描述**:「Zep + gemma3-XB backbone」= **Zep cloud graph(unchanged)+ gemma3-XB answer LLM**。

### 3.2 兩條實作路徑

**路徑 A(post-hoc,較省事)**:
1. 用 **現行 gpt-4o-mini Zep run**(已跑過)保留 per-qid 的 `edges / nodes / episodes / context_block`
2. 寫類似 `analysis/rerun_zep_edges_only.py` 的 script,但 answer LLM 改為 gemma via Ollama
3. **不重跑 Zep cloud graph**(節省 API cost + 360s wait)
4. 產出:`outputs/gemma3-Xb-zep/Conflict_Resolution/factconsolidation_sh_{L}_..._results.json`

**路徑 B(from scratch,重跑 Zep 全流程)**:
1. 修改 `methods/zep.py::OpenAIAgent` 加 Ollama support(current: openai / azure / deepseek only)
2. 修改 `run_zep_fc.sh` 加 `MODEL_TAG` 支援(current: hardcoded gpt-4o-mini path)
3. 從頭跑 Zep(重建 graph,新 user_id / graph_id / thread_id)
4. 每 context 首 query 前 360s wait

**建議**:先跑**路徑 A**,快且不動 Zep code。paper 誠實 disclose「Zep gemma runs = post-hoc answer LLM swap on existing Zep-cloud retrieval」。

### 3.3 methods/zep.py 修改點(若要走路徑 B)

`methods/zep.py::OpenAIAgent` 在 `__init__` 加分支:
```python
elif source == "ollama":
    from openai import OpenAI
    self.client = OpenAI(
        base_url=api_dict.get("base_url", "http://localhost:11434/v1"),
        api_key="ollama",  # dummy, Ollama ignores
    )
```

且 YAML 加 `answer_llm.source: ollama`(現行是 `source: openai`)。

---

## §4 Cache order(所有 method 通用)

**必先跑 ours(full P3+P5)at 某 backbone**,才能跑其他 4 個 mem0 variants:
- ours 首跑 → 建 P1 extraction cache
- ours_no_p5 / ours_struct / ours_p3_only / (b) mem0+P1 → 全 reuse 該 cache

**gemma workflow**(GX10 每個 backbone × length cell):
```
ours (full) → ours_no_p5 → ours_struct → ours_p3_only → (b) mem0+P1
```

**Zep** 走 §3 兩選項之一,獨立於 mem0-based 順序。

**(a) vanilla mem0** 不 reuse P1 cache(它有自己的 native extraction cache path),順序無關 ours。

---

## §5 每 cell 的必存 log 欄位(**追加於 backbone_extension_plan.md §4 CSV schema**)

除了 §4 已列 CSV 欄位,加以下 gemma-specific:

| 欄位 | 目的 |
| :--- | :--- |
| `mem0_store_size` | mem0 UPDATE 崩壞的 signature(1B/4B ~0)|
| `mem0_update_verdicts_count` | ADD / UPDATE / DELETE / NONE 分布(weak model 幾乎全 ADD)|
| `p1_extraction_cache_source` | `own` / `copied_from_gpt-4o-mini`(見 §2.2)|
| `zep_run_type` | `posthoc_swap` / `from_scratch`(見 §3.2)|

---

## §6 pre-run smoke suggestion

**每個 backbone 第一次跑,先 smoke `ours (full) 6k N_ABLATION=2`**:
- 若失敗 → Ollama num_ctx / model_name / server up 有問題,先修
- 若成功 → 全 tier 順序跑

**smoke 必檢查**:
1. `outputs/gemma3-Xb-mem0-.../Conflict_Resolution/*.json` 有 `data` 陣列
2. `outputs/rag_retrieved/Structure_rag_gemma3-Xb-.../k_100/factconsolidation_sh_6k/chunksize_512/query_0_context_0.json` 存在 且有 `response` 欄
3. `python analysis/rigor_audit.py --length 6k` 對該 cell 顯示 OK

---

## §7 完成後回報建議

Tier 完成後回報:
```
Tier X × <backbone> × <length>: complete
- ours (full)    EM=XX/74  wall_time=YYY  vram=ZZ  n_bank=XX
- ours (no_p5)   EM=XX/74  ...
- ours (struct)  ...
- ours (p3_only) ...
- (a) vanilla    EM=XX/74  mem0_store_size=YY(注意 weak model 崩壞 signature)
- (b) mem0+P1    EM=XX/74  ...
- Zep            EM=XX/74  run_type=posthoc/scratch

rigor_audit: all ✅ / ⚠️ <detail>
next Tier: <ready / blocked / question>
```

---

## §8 change log

- **2026-07-05** — 初版,補齊 backbone_extension_plan 沒細講的 Zep / mem0 三 LLM 位置 mapping + gemma-specific gotcha
