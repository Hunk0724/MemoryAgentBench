# Phase 0 — FC-SH 6k Evidence (first benchmark-legal result)

> 建立:2026-06-20　範圍:**FC-SH 6k 單一 setting** 的 Phase 0 vs vanilla mem0。
> 方法設計見 [phase0_implementation_guide.md](phase0_implementation_guide.md);本檔只放**證據**。

---

## 0. Headline

| FC-SH 6k (real benchmark, 同 scorer, both fresh 2026-06-20) | EM |
|---|---|
| vanilla mem0(destructive update) | **37.0%** |
| **Phase 0(conservative ADD + (S,P) triple + query-time resolve)** | **87.0%** |
| **Δ** | **+50.0pp** |

唯一差異 = **memory-side**(怎麼存、怎麼把記憶交給 inference)。backbone(gpt-4o-mini)、embedder(text-embedding-3-small)、L2 抽取、top-100 檢索、**FC inference prompt、benchmark scorer 全部逐字相同**。vanilla 以 fresh re-run 重現 37.0%(與 06-12 記錄一致),確認 harness 對齊。

---

## 1. Pipeline 流程圖(實作對照)

```
═════════ WRITE-TIME (ingestion, 每 chunk 一次 memory.add) ═════════
context ──chunk_facts_by_line(512)──▶ chunk           [benchmark loader]
  │ memory.add(chunk) ▶ _add_to_vector_store(infer=True)   [mem0/memory/main.py]
  │
  ├─① L2 extraction  (custom_prompt = make_l2_knowledge_prompt)
  │     frozen MEM0_EXTRACTION_CACHE 命中 ▶ facts[]   (離線, 0 LLM call)
  │
  └─② Phase-0 branch  (env MEM0_ADD_MODE=phase0_structural) ▶ _add_phase0_structural
        ordinal = per-chunk 計數器 (同 chunk 共用)         ← per-chunk, 非 per-fact
        ├─ extract_triples_batch(facts)  [methods/phase0_triple_extractor.py]
        │    gpt-4o-mini, frozen MEM0_TRIPLE_CACHE 命中 ▶ (s,p,o) | null
        ├─ 每 fact: embed(text-embedding-3-small) ▶ _create_memory
        │    qdrant payload = {data, hash, created_at, user_id, ordinal, triple}
        └─ 非 null triple ▶ 寫入 (S,P) inverted index    (無 confidence gate)
        ✗ 無 update-decision LLM call   ✗ 無 overwrite / delete   ▶ 純 ADD

═════════ STORAGE ═════════
 qdrant         : 455 points, payload 帶 triple + ordinal
 (S,P) index    : key=(subject_id, predicate_norm) ▶ [memory_id…] (ordinal DESC)
                  JSON @ MEM0_SP_INDEX_PATH  ← 已建,但本 setting query 時未用(見 §6)

═════════ QUERY-TIME (每題, _handle_mem0_agent 非 memorizing) ═════════
 wrapped FC question                                   [benchmark template, 與 vanilla 同]
  │ memory.search(q, limit=100) ▶ cosine top-100        [mem0]
  │    每筆 result 帶 metadata.triple + metadata.ordinal
  │
  ▼ Phase-0 query  (env MEM0_ADD_MODE) ─ 注入 @ agent.py:931
  │   ├─ group_and_resolve(top-100)   [methods/phase0_query.py]
  │   │    · 按各 item 自身 (subject_id, predicate_norm) 分組
  │   │    · 每組 argmax ordinal, KEEP-ALL-ON-TIE(同 ordinal 不丟)
  │   │    · triple=null ▶ ungrouped, 原樣保留
  │   └─ assemble_context ▶ "- <fact>" 行 (舊版本已被丟)
  │
  ▼ system = "You are a helpful AI…\n{memories_str}\n"   [agent.py:955, 與 vanilla 逐字同]
  ▼ _answer_with_client (gpt-4o-mini) ▶ answer
  ▼ benchmark scorer (drqa exact_match / substring)      [與 vanilla 同一把尺]
```

**4 個 LLM call 位置**:write 的 L2 抽取 + triple 抽取、query 的 (無 analyzer,本 setting)generation。全部 per-item/per-query,**無 cross-item judgment**。

---

## 2. 對齊清單(apples-to-apples)

| 環節 | vanilla | Phase 0 |
|---|---|---|
| backbone / embedder / chunk / top-100 / inference prompt / scorer | — | **完全相同** |
| 抽取 | L2 frozen cache | **同一份 L2 frozen cache** |
| **write 更新** | ADD/UPDATE/DELETE LLM 裁決 + 破壞性 commit | **純 ADD + (s,p,o) triple + (S,P) index** |
| **query** | top-100 原樣進 prompt | top-100 ▶ **(S,P) group + argmax ordinal** ▶ 進 prompt |
| 切換 | — | env `MEM0_ADD_MODE`;關掉 byte-identical |

config:[Structure_rag_gpt-4o-mini-mem0_l2_512_openai_phase0.yaml](../../configs/agent_conf/RAG_Agents/gpt-4o-mini/Structure_rag_gpt-4o-mini-mem0_l2_512_openai_phase0.yaml)(除 store 路徑外與 vanilla 同)。

---

## 3. 抽取品質(6k,frozen triple cache)

| 指標 | 值 |
|---|---|
| F1(triple null 率) | **1.8%**(8/455) |
| F2(衝突對 (S,P) 一致,both-extracted) | **80.6%**(54/67) |
| 結構解析上限(SH has_pair) | **73.0%**(54/74) |
| inverted-pattern(`…\|is`) | 3.1% |

triple extractor 的三條改進**全是 in-scope 通則、零 FC-overfit**(prose 規則,非 FC few-shot):
1. **nominal 分解**:`The R of E is V` ▶ (E, has R, V)(對齊 (s,r,o) KG 慣例)。raw 60.8% ▶ 73.0% ceiling。
2. **faithfulness**:不判真假、照轉錄反事實句(TruthfulRAG 前提)。修掉 18 個反事實 null ▶ F1 4.8% ▶ 1.8%。
3. **batch-aware + local fallback**:gpt-4o-mini batch=50 可靠;弱 local 模型才需 batch=1。

---

## 4. 失敗模式拆解(73% 之外,SH 74 對衝突)

| 結果 | 數量 | 歸屬 |
|---|---|---|
| ✅ 可 group(同 S,P, 跨 chunk) | 54 (73%) | — |
| ❌ (S,P) predicate 同義/截斷 | ~7 | **D3 lightweight normalize(延後)** |
| ❌ (S,P) 結構殘餘(被動/所有格句) | ~3 | 規則延伸 or 延後 |
| ❌ 一側 triple=null | ~10 | F1(已收斂到 1.8%) |
| 同 chunk ordinal 平手 | (部分) | **intra-chunk tie → keep-all-on-tie(設計接受)** |

> EM(87%)> 結構 ceiling(73%):benchmark scorer 含 `substring_exact_match → exact_match`(較寬鬆),且 null/不一致的 fact **仍在 context(semantic 撈得到)**,generation 常仍答對。EM 與 vanilla 同尺,故對照合法。

---

## 5. 破壞性 vs 非破壞(質性證據)

vanilla ingestion log 直接顯示它在 write-time **不可逆刪改**事實:
```
DELETE "Israel is located in the continent of Asia."
DELETE "The capital of Germany is Berlin."
UPDATE "The official language of Japan is Japanese."  (previous: 同)
… (大量 DELETE)
```
Phase 0 全部保留(455 facts 全 ADD),把「選哪版」延到 query-time 用 (S,P)+ordinal 決定。vanilla 一旦刪錯(反事實更新判錯方向 / 刪掉該留的版本)= 不可逆失分;Phase 0 不會。

---

## 6. 已知限制 / 尚未啟用(誠實標註)

- **(S,P) index 本 setting query 時未用**:resolution 直接對 semantic top-100 的 payload (S,P) 分組;sp_index(Path B 結構檢索)是 guide §7.4 的 A3,尚未接。
- **D3 延後**:§4 的 predicate 同義殘餘(~7)留給 lightweight normalize,未做。
- **ordinal = per-chunk**:intra-chunk 衝突 argmax 平手 → keep-all-on-tie(不誤刪,但不解析)。
- **單一 setting**:僅 FC-SH 6k。MH / 32k / A0–A3 ablation 未跑。

---

## 7. 重現

```bash
# 1) 建 6k frozen triple cache(跑一次,之後免費)
python docs/0615_intro_framework_after_problem_statement/scripts/measure_f1_f2.py 6k
# 2) benchmark vs vanilla(real main.py;both fresh)
bash docs/0615_intro_framework_after_problem_statement/scripts/run_phase0_sh_6k.sh
```
結果 JSON:`outputs/gpt-4o-mini-mem0-chunk512-temp0-l2-openai-{phase0,rerun}/Conflict_Resolution/…sh_6k…results.json`。
環境:conda env **MABench**;qdrant 須 `on_disk:true`(否則重開會 rmtree 清空)。
```
