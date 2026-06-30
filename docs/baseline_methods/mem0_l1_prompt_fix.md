# Mem0 L1 Prompt Fix — Minimal modification for FC task compatibility

> 日期:2026-05-29(Phase 0 已先驗證,2026-05-29 第二次驗證)
> 目的:讓 mem0 在 FC(Fact Consolidation)任務上能 work,前提是用嚴守 prompt 的 LLM(如 Gemini 3.1-flash-lite)

---

## 0. 問題

Mem0 預設 `FACT_RETRIEVAL_PROMPT`([mem0/configs/prompts.py:14](../../mem0/configs/prompts.py#L14))內含兩個 rejection few-shot 範例:

```
Input: Hi.
Output: {"facts" : []}

Input: There are branches in trees.
Output: {"facts" : []}
```

`"There are branches in trees"` 跟 FC 給的「客觀世界事實」(`"Thomas Kyd was born in London"`)是**完全同類別**的句子。Strict prompt-following LLM(如 gemini-3.1-flash-lite)看到這兩個 example 後,**對所有 FC 輸入回 `{"facts": []}`**。

結果:
- Mem0 在 FC 上 ingest **0 facts**
- Retrieve 拿不到任何 memory
- EM = **0.0%**

---

## 1. 證據(2026-05-29 驗證)

```
[mem0 debug] memory_messages[1].content len=17623 chars     ← input 正常,完整 6k context
[mem0 debug] memory_messages[1].content head: '...Here is a list of facts:
                                                  0. Thomas Kyd was born in London. ...'

[mem0 internal] fact extraction response (len=13): '{"facts": []}'  ← Gemini 抽不出任何 fact
[mem0 internal] new_retrieved_facts count = 0
```

LLM call 成功,但 LLM 嚴守 prompt 拒絕 FC 輸入。

---

## 2. Fix(L1 minimal modification)

只移除那 2 個 rejection few-shots,其他 prompt 結構完全不動:

| Prompt 元素 | OOB | L1 fix |
|---|---|---|
| Persona ("Personal Information Organizer") | ✅ | ✅ 不動 |
| 7 Types of info to remember(preferences, plans, ...) | ✅ | ✅ 不動 |
| `Input: Hi. → {facts: []}` | ✅ | ❌ **移除** |
| `Input: There are branches → {facts: []}` | ✅ | ❌ **移除** |
| `Input: Restaurant in San Francisco → ...` | ✅ | ✅ 不動 |
| `Input: Meeting with John ...` | ✅ | ✅ 不動 |
| `Input: My name is John ...` | ✅ | ✅ 不動 |
| `Input: Favorite movies ...` | ✅ | ✅ 不動 |
| Extraction guidelines(JSON format, language detection, etc.) | ✅ | ✅ 不動 |

**改動量化**:OOB prompt = 3173 chars,L1 = 3078 chars(**移除 95 chars**,佔總長 3.0%)。

---

## 3. 實作

### 3.1 程式碼位置
- L1 prompt 邏輯:[methods/mem0_fc_prompt_fix.py](../../methods/mem0_fc_prompt_fix.py)
- agent.py 注入點:[agent.py:_initialize_mem0_agent](../../agent.py) 讀 yaml flag `mem0_config.use_l1_fc_prompt: true`
- **不改 vendored `mem0/configs/prompts.py`**(透過 `MemoryConfig(custom_fact_extraction_prompt=...)` 注入,vendored 保持乾淨)

### 3.2 yaml 開關
```yaml
mem0_config:
  llm: {...}
  embedder: {...}
  vector_store: {...}
  use_l1_fc_prompt: true   # ← 加這行就自動套用 L1 fix
```

---

## 4. Paper 論述(待寫到 paper appendix)

```text
We minimally modify mem0's fact-extraction prompt by removing two few-shot
examples ("Hi." and "There are branches in trees." → {facts: []}) that
explicitly instruct the LLM to reject input modalities resembling our
FC benchmark (declarative factual statements). All other elements of the
prompt (Personal Information Organizer framing, 7 types of information,
extraction guidelines, JSON format, language preservation) remain unchanged.
This is a 95-character removal out of 3173 (3.0%).

Without this fix, gemini-3.1-flash-lite strictly follows the prompt and
rejects all FC inputs (0% EM). With the fix, mem0 produces fact lists
comparable in volume to what GPT-4o-mini extracts under the OOB prompt
(see ablation in Section X).

We adopt this fix because (1) the two removed examples directly contradict
the input modality of FC, not the design intent of mem0; (2) GPT-4o-mini
under OOB prompt also exhibits this limitation but partially escapes it
through looser prompt-following behavior (EM 1-15%); (3) we unify all
baselines on a single LLM backbone for fair cross-method comparison.
```

---

## 5. Chunk size 對 Gemini 的二次影響(2026-05-29 補充)

L1 fix 套用後,**chunk_size 對 Gemini 在 FC 上的 mem0 行為仍有重大影響**:

| chunk_size | Phase 0 (chunk=512) | 本次驗證 (chunk=4096) |
|---|---|---|
| Chunks 數 | 12 chunks(6k context) | 2 chunks(6k context) |
| Facts ingested | **448 facts**(逐條抽取) | **1 meta-summary**(`"Learned the provided list of 308 facts"`) |
| EM 預期 | 可分析(phase 0 跑過) | 0%(沒抽到具體 facts) |

**現象解釋**:
- chunk=4096:每 chunk 含 ~250 個 facts → LLM 看到「一大段 list」→ **meta-summarize 而非逐條抽取**
- chunk=512:每 chunk 含 ~38 個 facts → LLM 看到「小段 list」→ **逐條抽取**(跟 prompt few-shot 範例「Meeting with John at 3pm → 萃取單條事實」對齊)

**對 paper convention 的影響**:
- Mem0 paper 規定統一 chunk=4096(memory feedback 記錄的 [chunk_size_convention.md](../experiments/chunk_size_convention.md))
- 但在 Gemini 嚴守 prompt 的情況下,chunk=4096 + mem0 預設 prompt 在 FC 上**失效**
- 必須改用 **chunk=512**(對齊 Phase 0 已驗證的 setup)才有有意義結果

**Paper 內論述**(待寫):
```
While mem0's paper convention sets chunk_size=4096 across all datasets,
this assumes a GPT-style LLM that loosely interprets the fact-extraction
prompt. Under strict prompt-following LLMs (gemini-3.1-flash-lite), chunk
=4096 causes mem0 to produce a single meta-summary per chunk rather than
extracting individual facts (verified: 1 "Learned 308 facts" entry vs 448
extracted facts under chunk=512). We therefore set chunk_size=512 for mem0
under the Gemini backbone, matching the Phase 0 validated configuration.
```

---

## 6. Ablation 規劃(paper §X)

| Variant | Prompt | chunk | Expected EM | 用途 |
|---|---|---|---|---|
| Mem0 OOB(原 prompt)| 預設 | 4096 | ~0% | 證明 prompt fix 必要 |
| Mem0 OOB(原 prompt)| 預設 | 512 | ~0% | 證明 chunk 切小也救不了原 prompt |
| Mem0 L1 + chunk=4096 | L1 移除 | 4096 | **0%(已驗證)** | 證明 chunk size 對 Gemini 有影響 |
| **Mem0 L1 + chunk=512(主結果)** | L1 移除 | **512** | ~? %(跑中) | 對齊 Phase 0 / paper main result |
| Mem0 OOB + GPT-4o-mini | 預設 | 512 | EM 15% / 1%(歷史) | 對齊 mem0 paper 既有數字 |

---

## 6. 風險評估

| 風險 | 解釋 | 緩解 |
|---|---|---|
| reviewer 質疑「prompt engineering」 | 怕變成 craft prompt 讓 mem0 變強 | 答辯:OOB → L1 是「修復 input modality mismatch」,不是讓 mem0 變更強(對比 GPT-4o-mini OOB 跑出 1-15% 同水平) |
| reviewer 質疑「為什麼不用 GPT」 | mem0 paper 用 GPT-4o-mini | 答辯:統一 backbone 才公平比較 LCA/HippoRAG/Ours 等所有方法 |
| reviewer 質疑「fix only for FC」 | 是否其他 task 也 cherry-pick prompt | Disclose:L1 是因 FC 特有的「declarative facts」輸入模態,其他 task 用 mem0 OOB(若有跑) |

---

## 7. 歷史脈絡

- **Phase 0**([analysis/experiments/2026-04-30_mem0_zep_baseline_setup/README.md](../../analysis/experiments/2026-04-30_mem0_zep_baseline_setup/README.md)):首次發現 + 驗證 L1 fix
- **2026-05-29 二次驗證**(本文件):用 vertexai 全 ADC + chunk=4096 + gemini-3.1-flash-lite,正式整合進 agent.py / yaml

---

## 8. 相關文件

- 跑法總計畫:[[../experiments/pilots/mem0_mem0g_pilot_plan.md]]
- mem0 預設 prompt 原文:[mem0/configs/prompts.py:14](../../mem0/configs/prompts.py#L14)
- Phase 0 README:[analysis/experiments/2026-04-30_mem0_zep_baseline_setup/README.md](../../analysis/experiments/2026-04-30_mem0_zep_baseline_setup/README.md)
