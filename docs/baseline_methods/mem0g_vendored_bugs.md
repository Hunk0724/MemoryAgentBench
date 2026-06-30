# Mem0g 跑 Gemini × Neo4j 時撞到的 Vendored Bug + Fix 紀錄

> 日期:2026-05-29
> 目的:讓未來實驗能穩定跑 mem0g,並讓 paper 能 disclose「我們對 vendored mem0g 做了哪些 minimal 內部 bug fix」
> 性質:**全部屬於 docs/baseline_methods/mem0_setup_deltas_vs_paper.md §20.2 「A. API hygiene」類別** — 純技術 bug fix,不是 prompt mod,不是 method mod,**不需要 ablation**,只需 disclose。

---

## 0. TL;DR

| Bug | 在哪 | 我們的 fix | 穩定性 |
|---|---|---|---|
| 1. `EmbedderFactory.create()` 參數數量不一致 | mem0/memory/main.py vs graph_memory.py | Wrap `.create()` 讓第 3 參數可選 | ✅ 永久穩定 |
| 2. Cypher label 含不合法字元 | mem0/memory/graph_memory.py format string 直接接 LLM 輸出 | Wrap `_add_entities` / `_delete_entities`,先 sanitize | ⚠️ 大致穩定,monitor 新 edge cases |

---

## 1. Bug 1:EmbedderFactory.create() signature 不一致

### 1.1 症狀
跑 mem0g 時:
```
TypeError: EmbedderFactory.create() missing 1 required positional argument: 'vector_config'
```

### 1.2 根本原因
Vendored mem0 v2 fork 內部不一致:

| 檔案 | 行 | 呼叫方式 |
|---|---|---|
| `mem0/memory/main.py` | 43-47 | `EmbedderFactory.create(provider, config, vector_config)` — **3 args(新)** |
| `mem0/memory/graph_memory.py` | 37 | `EmbedderFactory.create(provider, config)` — **2 args(舊)** |
| `mem0/utils/factory.py` | 61 | `def create(cls, provider_name, config, vector_config: Optional[dict])` — **要 3 args** |

Mem0 作者在某次 refactor 加了第 3 個參數(讓 upstash_vector 之類 embed 服務可以共用 vector store config),但**忘了同步更新 graph_memory.py**。標準 vendored API drift bug。

### 1.3 我們的 fix(在 [agent.py](../../agent.py) 的 `_initialize_mem0_agent`)

```python
# Wrap .create so the third arg is genuinely optional
_orig_create = EmbedderFactory.create.__func__
def _patched_create(cls, provider_name, config, vector_config=None):
    return _orig_create(cls, provider_name, config, vector_config)
EmbedderFactory.create = classmethod(_patched_create)
```

### 1.4 為什麼這 fix 是穩定的

- **不依賴模型行為**:跟 LLM 抽什麼無關
- **不依賴資料**:跟 ctx 長短、task 類型無關
- **跟 backbone 無關**:Gemini / GPT / Claude 都 work
- **跟 upstream 不衝突**:就算我們之後 update mem0 vendored,只要他們改 graph_memory.py 用新 signature(很可能會),我們的 monkey-patch 就自動 no-op(`vector_config` 不再 default 為 None 而是真實傳入)

→ **一次寫對,永久 work**。

---

## 2. Bug 2:Cypher label 含不合法字元

### 2.1 症狀
跑 mem0g 時:
```
neo4j.exceptions.CypherSyntaxError: Invalid input '/': expected a parameter, '&', ')', ':', 'WHERE', '{' or '|'
"MERGE (n:country/empire {name: $source_name, user_id: $user_id})"
                  ^
```

### 2.2 根本原因
Neo4j label 規則:`[A-Za-z_][A-Za-z0-9_]*`(英文字母 / 數字 / 底線,**不能數字開頭**)。

Mem0g vendored 在多處直接把 LLM 抽出的 `entity_type` / `relationship` format 進 Cypher:

| Cypher fragment | 在哪 |
|---|---|
| `MERGE (n:{source_type} ...)` | graph_memory.py:341, 361, 396 |
| `MERGE (destination:{destination_type} ...)` | graph_memory.py:399 |
| `MERGE (n)-[r:{relationship}]->(m)` | graph_memory.py:345, 365, 383, 402 |

LLM(Gemini)在 FC 抽出來的 entity_type 例子:
| LLM 回的 entity_type | 含不合法字元 | 結果 |
|---|---|---|
| `country/empire` | `/` | ❌ Neo4j 拒收 |
| `Person (alive)` | 空格、括號 | ❌ |
| `34` | 數字開頭 | ❌ |
| `Person` | 純英文 | ✅ |

Mem0g 開發團隊用 GPT-4o-mini 測試時,GPT 很少回奇怪 entity_type → 沒撞過這 bug → vendored code 沒做 sanitize。Gemini 比較常回奇怪格式 → 我們撞到。

### 2.3 我們的 fix(在 [agent.py](../../agent.py) `_initialize_mem0_agent`)

```python
import re as _re
from mem0.memory import graph_memory as _gm_module

def _sanitize_neo4j_label(s):
    if not s:
        return "Unknown"
    s = _re.sub(r"[^A-Za-z0-9_]", "_", str(s))
    if not s:
        return "Unknown"
    if not (s[0].isalpha() or s[0] == "_"):
        s = "_" + s
    return s

_orig_add_entities = _gm_module.MemoryGraph._add_entities
def _patched_add_entities(self, to_be_added, user_id, entity_type_map):
    sanitized_map = {k: _sanitize_neo4j_label(v) for k, v in entity_type_map.items()}
    sanitized_added = [
        {**item, "relationship": _sanitize_neo4j_label(item.get("relationship", "RELATED"))}
        for item in to_be_added
    ]
    return _orig_add_entities(self, sanitized_added, user_id, sanitized_map)
_gm_module.MemoryGraph._add_entities = _patched_add_entities

# Same for _delete_entities (uses {relationship})
_orig_delete_entities = _gm_module.MemoryGraph._delete_entities
def _patched_delete_entities(self, to_be_deleted, user_id):
    sanitized = [
        {**item, "relationship": _sanitize_neo4j_label(item.get("relationship", "RELATED"))}
        for item in to_be_deleted
    ]
    return _orig_delete_entities(self, sanitized, user_id)
_gm_module.MemoryGraph._delete_entities = _patched_delete_entities
```

### 2.4 已 cover 的情境

| LLM 回 | sanitize 後 | 結果 |
|---|---|---|
| `"country/empire"` | `"country_empire"` | ✅ |
| `"Person (alive)"` | `"Person__alive_"` | ✅ |
| `"34"` | `"_34"` | ✅ |
| `""` 或 `None` | `"Unknown"` | ✅ fallback |
| `"!!!/"` | `"____"` → `"____"` | ✅ valid(雖然語義無意義) |

### 2.5 訊息會不會丟失?

**不會嚴重丟**:
- Entity 的實際 **name**(例如 `"Israel"`)透過 Cypher 參數 `$source_name` 綁定,**完整保留**
- 只有 **label** 名(group 名)會 sanitize,例如 `country/empire` 跟 `country_empire` 會被當成同一 label
- 對 FC 衝突偵測 / 答題:**完全不影響**,因為 mem0g 主要靠 embedding similarity 找衝突,label 只是 group 提示

### 2.6 潛在 edge cases(實務上罕見,但要 monitor)

| Edge case | 處理結果 | 對 FC 任務影響 |
|---|---|---|
| Unicode(中文 / emoji) | 全替換為 `_` | FC 是英文 dataset,不會撞 |
| 超長 label(> 1000 字) | Neo4j 接受但浪費記憶體 | 罕見,可監控 |
| 全部被 sanitize 掉 | `"____"` 仍 valid | 少數 entities 可能混合,但用 embedding 區分 |
| 重複 sanitize 後相同 label | 多個 entity 同 label | 不嚴重,圖仍按 `name` 分節點 |

### 2.7 監控策略

跑後續 ctx sweep 時 monitor:

```bash
grep -c "CypherSyntaxError" logs/mem0g_*_*.log
```

如果有 hit,看具體訊息,擴大 regex / fallback 邏輯。

---

## 3. 為什麼 mem0g 沒人撞過這些 bug?

| 原因 | 解釋 |
|---|---|
| **Mem0g v3 已被 upstream 砍掉** | 詳見 [[../baseline_methods/baseline_methods_paper_vs_impl.md §3]] — mem0 v3 在 2026-04 移除整個圖記憶子系統 |
| **GPT-4o-mini 不會回奇怪 entity_type** | Mem0 原作者用 GPT 測,Gemini 行為不同 |
| **Neo4j 5 比 Neo4j 4 更嚴格** | mem0g 可能在舊 Neo4j 4 上跑過,Neo4j 4 比較寬容 |
| **FC 任務本身罕見** | mem0 主推 dialogue / personal preferences,FC 是 MABench 特定 benchmark,mem0 paper 自己也沒用心測 |

→ 我們是「現代 stack(Neo4j 5 + Gemini + FC)」第一個跑 mem0g 的人。撞 bug 預期合理。

---

## 4. 對 paper disclosure 的影響

### 4.1 屬於哪類改動

[mem0_setup_deltas_vs_paper.md §20.2](mem0_setup_deltas_vs_paper.md) 分類:
- **A. API hygiene**(retry, max_tokens, version compat)— **這兩個 bug fix 都屬於這類** ✅
- B. Cross-method convention selection
- C. Minimal prompt repair
- D. Substantive prompt engineering(危險)

**A 類在頂會通常不需要 ablation**,只需 disclose 是「為了讓 vendored code 能在新環境 work」。

### 4.2 Paper 怎麼寫(草稿)

> "We apply two minimal monkey-patches to vendored mem0g to resolve internal
> API drifts: (1) `EmbedderFactory.create()` signature mismatch between
> `main.py` and `graph_memory.py` (latter calls 2-arg, former 3-arg version);
> (2) Neo4j label sanitization in `_add_entities` / `_delete_entities`, where
> LLM-extracted entity types (e.g., 'country/empire') would otherwise produce
> invalid Cypher. Neither patch modifies mem0g's algorithm or prompts — both
> are pure compatibility fixes between vendored mem0 v2 and the current
> Neo4j 5 + Gemini-3.1-flash-lite stack. See Appendix X for the exact patches."

---

## 5. 對「能否穩定跑下一輪實驗」的答覆

### 5.1 6k(現在跑著)

**穩定機率**:**95%+**
- Sanitizer cover 已知主要情境
- 唯一風險:LLM 回特殊 entity_type 我們沒預料到
- 監控指標:`CypherSyntaxError` 計數

### 5.2 32k

**穩定機率**:**90%+**
- 同 6k 一樣的邏輯,但 entity 數量約 5x → 撞罕見 edge case 機率略增
- 若有新 corner case,擴大 regex 處理

### 5.3 64k

**穩定機率**:**85%+**
- Entity 數量 11x → 統計上更可能撞新 edge case
- Update phase output 也可能撞 max_tokens 上限(獨立風險),需要拉 max_tokens 到 32768

### 5.4 262k

**穩定機率**:**70%+**
- 18000+ facts,LLM 可能回各種怪 entity_type
- max_tokens 大概率不夠 8192,需 65536+(若 Gemini Flash Lite 支援)
- 圖會很大,Neo4j query 可能變慢

### 5.5 對你的建議

| 後續實驗 | 風險 | 對策 |
|---|---|---|
| **mem0g × FC-MH × 6k**(現在跑) | 低 | 等通知 |
| **mem0g × FC-MH × 32k** | 低-中 | 跑時 grep `CypherSyntaxError` |
| **mem0g × FC-MH × 64k** | 中 | max_tokens 拉到 32768 |
| **mem0g × FC-MH × 262k** | 中-高 | max_tokens 65536,且設「撞 Cypher 就跳該 chunk continue」邏輯 |
| **mem0g × FC-SH × ?** | 同上 | SH 通常更短,風險低 |
| **mem0g × 切換 model**(2.5 / 3.5) | 低 | LLM 行為不同,可能撞新邊界,但 monkey-patch 仍有效 |

---

## 6. 監控腳本(放在 bash_files/)

跑後續 mem0g 實驗時,建議加這個 monitor:

```bash
# 跑時 background 啟動 monitor:
tail -F logs/mem0g_*_*.log | grep --line-buffered -E "CypherSyntaxError|empty text — finish_reason=MAX_TOKENS"
```

撞到就 abort + 強化 patch + 重跑。

---

## 7. 相關文件

- 三個 setup deltas 框架:[[mem0_setup_deltas_vs_paper.md]]
- chunk size convention:[[../experiments/chunk_size_convention.md]]
- L1 prompt fix:[[mem0_l1_prompt_fix.md]]
- Neo4j setup:[[../infrastructure/neo4j_setup.md]]
- Mem0g 為何在 mem0 v3 被砍:[[baseline_methods_paper_vs_impl.md]]
