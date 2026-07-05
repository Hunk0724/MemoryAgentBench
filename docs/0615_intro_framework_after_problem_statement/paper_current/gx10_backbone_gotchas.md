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

**路徑 A(post-hoc,推薦!已有 canonical script)**:

★ **已寫好 script 給你**:[`analysis/rerun_zep_with_ollama_backbone.py`](../../../../analysis/rerun_zep_with_ollama_backbone.py)

### Step-by-step

**Step 1:準備 Ollama 端**
```bash
# 確認 Ollama server 開著 (預設 port 11434)
ollama list

# 若沒 pull 過模型:
ollama pull gemma3:1b
ollama pull gemma3:4b
ollama pull gemma3:12b
ollama pull gemma3:27b
```

**Step 2:確認 Mac 的 Zep 資料在 GX10 端**(git pull 後就有)
```bash
# Mac 已 push 的 Zep per-qid 檔:
ls outputs/rag_retrieved/Structure_rag_zep/k_10/factconsolidation_sh_6k/chunksize_512/query_*.json | wc -l
# 應 = 100
```

**Step 3:smoke 一個 backbone × length**(1-2 min per qid × 5 qids ≈ 5-10 min)
```bash
# 例:gemma3-12b × 6k × 5 qids
python analysis/rerun_zep_with_ollama_backbone.py \
    --length 6k --backbone gemma3:12b --limit 5 --num-ctx 8192
```

驗證:
- log 顯示 `EM = X/5 (Y%)` 且 EM 數字 sensible(非全 0、非 100%)
- 檔案有生成:`ls outputs/gemma3-12b-zep/Conflict_Resolution/`
- 樣本:`ls outputs/rag_retrieved/Structure_rag_gemma3-12b-zep/k_10/.../query_0_context_0.json`

**Step 4:full run 全 4 backbones × 3 lengths(sequential)**
```bash
for BB in gemma3:1b gemma3:4b gemma3:12b gemma3:27b; do
    for L in 6k 32k 64k; do
        # 32k / 64k 需大 num_ctx(gemma 4B/12B 需 confirm 有支援):
        NCTX=8192
        [ "$L" = "32k" ] && NCTX=16384
        [ "$L" = "64k" ] && NCTX=32768
        echo "==== $BB × $L (num_ctx=$NCTX) ===="
        python analysis/rerun_zep_with_ollama_backbone.py \
            --length "$L" --backbone "$BB" --num-ctx "$NCTX"
    done
done
```

**Step 5:rigor audit(記入 gx10_run_log.csv)**
```bash
python analysis/rigor_audit.py --length 6k
# 新的 gemma3-*-zep cells 需加到 rigor_audit.py METHODS(post-hoc 產出的 aggregated 已 canonical format)
```

### 產出結構

每個 backbone × length 一份:
- Per-qid:`outputs/rag_retrieved/Structure_rag_gemma3-{size}-zep/k_10/factconsolidation_sh_{L}/chunksize_512/query_*.json`(fields:edges / nodes / episodes / context_block / response)
- Aggregated:`outputs/gemma3-{size}-zep/Conflict_Resolution/factconsolidation_sh_{L}_unknown_backbone_swap_size256_shots0_max_samplesunknown_k10_chunk512_results.json`(MAB-compat format)

### 為何**不需要 ZEP_API_KEY**

- Zep cloud graph 已由 Mac gpt-4o-mini 建好,per-qid cached edges/nodes/episodes 已 sync
- script 不呼叫 Zep API,只呼叫 Ollama(local)+ 讀 cached JSON
- **完全 offline(除了 Ollama 本地推理)**

### num_ctx 提醒(踩過的雷)

- gemma3-1B / 4B 上限 8192 tokens(Ollama 預設)
- gemma3-12B 可調 16384(視 VRAM)
- gemma3-27B 可調 32768(需大 VRAM)
- **若 32k / 64k Zep context 過大** → 需切 context 或 fallback to edges-only(見 §3.2b)

### §3.2b — 32k / 64k 若 gemma window 不夠

若 Zep context 太長(gemma3-4B 32k 可能爆),兩個 fallback:
1. **truncate**:script 加 `--max-context-tokens 7000` 手動 truncate context 前 7k tokens(丟後面 episodes)
2. **edges-only fallback**:用 `analysis/rerun_zep_edges_only.py` 的方式,只留 edges 不放 nodes+episodes(context 短很多)

我建議先跑 6k(所有 backbone 都 fit),再看 32k 是否需 fallback。

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
