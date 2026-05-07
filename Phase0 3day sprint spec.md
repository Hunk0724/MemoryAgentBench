# Phase 0 三天衝刺實作 Spec

> **目的**：3 天內完成 multi-hop 知識更新瓶頸診斷，產出模式 A/B/C/D 判定，作為後續 method 設計的 evidence base
> **整理日期**：2026-04-30
> **執行週期**：3 天（Day 1-3），第 4 天起進入後續實作
>
> **3 天硬目標**：
> 1. Mem0/Zep 在 FC-SH/MH 的 end-to-end 數字
> 2. Mem0/Zep 的 detection F1（如 entity mapping 太困難可 fallback 為 end-to-end only）
> 3. 對比表（vanilla / Mem0 / Zep / OA1 orig / OA2 oracle）填好
> 4. 模式 A/B/C/D 判定 + 1 頁分析報告
>
> **3 天不做**：LongMemEval-KU setup、v8 report 修訂、Method 實作（瓶頸確認後 W3 再開始）

---

## 整體 3 天排程

| 天 | 主要動作 | Deliverable |
|---|---|---|
| Day 1 上午 | Step 1: Mem0/Zep API audit + entity mapping feasibility | API audit report + mapping 可行性結論 |
| Day 1 下午 | Step 2: OA1 orig prompt 實驗 | OA1 orig 數字 + 跟 OA2 orig 對比 |
| Day 2 全天 | Step 3: Mem0 + Zep setup + entity ID mapping + detection metric pipeline | 兩個系統可跑通 + detection extraction script |
| Day 3 上午 | Step 4: 跑 Mem0/Zep on FC-SH/MH + detection F1 | 對比表填好 |
| Day 3 下午 | Step 5: 結果分析 + 模式 A/B/C/D 判定 | 1 頁分析報告 + paper motivation 修訂方向 |

---

## Step 1: Mem0/Zep API Audit + Entity Mapping Feasibility

### 最終目標

確認以下 4 個技術問題的答案，避免 Day 2 進入 detection metric pipeline 實作後才發現結構性 blockers：

1. Mem0 graph mode 是否暴露 supersession 標記？哪個 attribute？
2. Zep 的 episode/edge invalid_at 是否能從 SDK 直接 access？
3. Mem0/Zep 內部的 entity linking 是否能跟 FC dataset 的 fact_id 對齊？
4. 如果不暴露，需要寫多少 code 才能 extract detection signal？

### 跟整體研究的連結

這是 3 天衝刺最 critical 的 risk gate。如果 detection signal extraction 完全不可行，Day 2-3 計畫必須 fallback 為「只算 end-to-end EM，不算 detection F1」。提早發現比 Day 2 進去後撞牆好。

### 具體執行內容

**1.1 Mem0 audit**（1 小時）

```bash
# Clone & install
cd ~/research_workspace
git clone https://github.com/mem0ai/mem0.git
cd mem0
pip install -e .

# 跑 minimal example with graph mode
python -c "
from mem0 import Memory
config = {'graph_store': {'provider': 'neo4j', ...}}
memory = Memory.from_config(config)
memory.add('User loves pizza', user_id='test')
memory.add('User now hates pizza', user_id='test')  # supersession
result = memory.search('food preference', user_id='test')
print(result)  # 看 result 結構
"
```

檢查項目：
- `result` 是否有 `metadata` field 標 ADD/UPDATE/DELETE/NOOP？
- 內部 resolver output 在哪個 method？grep `UPDATE\|DELETE\|supersede` in source
- Memory inspect API：`memory.get_all()` 是否回傳 entity 跟 supersession 關係？

**1.2 Zep audit**（1 小時）

```bash
git clone https://github.com/getzep/zep.git
# 或 pip install zep-python

python -c "
from zep_python.client import Zep
zep = Zep(api_key='...')
zep.memory.add(session_id='test', messages=[{'role':'user','content':'I live in Tokyo'}])
zep.memory.add(session_id='test', messages=[{'role':'user','content':'I moved to Taipei'}])
edges = zep.graph.search(query='residence', user_id='test')
for e in edges:
    print(e.valid_at, e.invalid_at, e.fact)  # 看 invalid_at 是否被設
"
```

檢查項目：
- `edges` 中 invalid_at 是否被 set 為 supersession 時間？
- Episode 物件是否暴露 superseded_by 關係？

**1.3 Entity ID mapping feasibility**（1 小時）

對 FC dataset 隨機抽 5 筆 instance，比對：

```python
# FC dataset
fc_instance = {
    'fact_id_old': 'X is the capital of A',
    'fact_id_new': 'X is the capital of B',
    'entity': 'X',  # 主體
    ...
}

# Mem0 ingest 完後 inspect
mem0_entities = memory.get_all_entities(user_id='test')
# 問：mem0_entities 中是否有對應 'X'？
# 是用 string match 還是需要 embedding similarity？
```

預期 outcome：
- **Best case**：Mem0/Zep 的 entity linking 用 surface form，FC entity name 直接對得上
- **Middle case**：需要 fuzzy match 但可控
- **Worst case**：完全對不上，需要 embedding-based mapping layer

### Risk + Fallback

| Risk | Mitigation |
|---|---|
| Mem0 API 完全不暴露 supersession 標記 | Fallback 為「inspect retrieved memory diff」：ingest old fact 後 search → ingest new fact 後再 search → 看 old fact 是否消失 |
| Zep 自架需要 Neo4j + LLM API key | Fallback 用 zep cloud free tier（如有），或最小化測試（僅跑 5-10 筆 instance） |
| Entity mapping 嚴重困難 | Day 2 下午切到 fallback：只算 end-to-end EM，detection F1 留 future work |

### Time Budget

3 小時（半天）

### Success Criterion

產出一頁 audit report 包含：
1. Mem0 detection signal extraction 方法（具體 attribute / method）
2. Zep detection signal extraction 方法
3. Entity mapping 可行性結論（best/middle/worst case 哪個）
4. Day 2 工作量重新估計（mapping 困難程度決定 Day 2 是否能完成）

如果產出顯示「mapping 完全不可行」，立刻決定 Day 2-3 plan 切到 end-to-end only fallback。

---

## Step 2: OA1 Orig Prompt 實驗

### 最終目標

驗證老師 0429 evaluation §3.1 提的 paper-level attack vector：「§2.6 NC orig 60% > OA2 orig 55% 暗示 fact-level granularity claim 在 orig prompt 下可能 collapse」。

跑出 OA1 在 orig prompt 下 FC-MH full 100 的 EM，跟 OA2 orig 55% 對比。

### 跟整體研究的連結

這個實驗結果直接決定 paper §2.5 的「fact-level > passage-level by 24pp」結論在 orig prompt 條件下是否成立：

| Outcome | Implication |
|---|---|
| OA1 orig > OA2 orig | Fact-level granularity claim 在 orig prompt 下 collapse → method 設計可能要重新評估 (prompt-conditional granularity) |
| OA1 orig ≈ OA2 orig | Granularity 對 orig prompt 不敏感、對 modified prompt 敏感（有趣 paper finding）|
| OA1 orig < OA2 orig | Claim 全 prompt 條件下都成立，framing 更強 |

### 具體執行內容

```bash
cd /home/yhchiang/MemoryAgentBench

export GOOGLE_GENAI_USE_VERTEXAI=True
export GOOGLE_CLOUD_PROJECT=fc-mh-494213
export GOOGLE_CLOUD_LOCATION=global

# 已有的 OA1 implementation 可能用 modified prompt，需要改為 orig prompt
# 1. 找到 OA1 script
ls analysis/oracle_a*  # 找 passage-level 版本

# 2. 確認 OA1 是否已有 orig prompt 版本
grep -l "orig.*prompt\|original.*prompt" analysis/oracle_a*

# 3a. 如果沒有，從 OA2 orig prompt 版本 copy 並改 granularity 為 passage-level
cp analysis/oracle_a_fact_level_origprompt.py analysis/oracle_a_passage_level_origprompt.py
# 修改：filter granularity 從 sentence-level excision 改為 whole passage removal

# 3b. 跑 full 100
conda run -n hipporag_env python analysis/oracle_a_passage_level_origprompt.py

# 4. 數字產出
# 預期: results/oracle_a_gemini/oa1_origprompt_results.json
```

### Risk + Fallback

| Risk | Mitigation |
|---|---|
| OA1 之前是用 modified prompt 跑，沒有 orig prompt 版本 | 從 OA2 origprompt 改 granularity 即可，工程量小 |
| Resume-safe 機制讓部分 query 重複 | 確認 results 目錄為新名字，避免 conflict |
| Gemini API rate limit | 100 題的 batch 約 10-15 分鐘，可接受 |

### Time Budget

3-4 小時（半天）— 主要時間在 implement passage-level filter 並 verify

### Success Criterion

產出 OA1 orig prompt FC-MH full 100 的 EM 數字。對應 outcome 之一（>/=/<），標記在 v7 §2.6 對應段落作為 W2 evidence 補強。

---

## Step 3: Mem0 + Zep Setup + Entity ID Mapping + Detection Metric Pipeline

### 最終目標

建立可運作的 pipeline：
1. 對 FC-SH/MH 100 題每個 instance，把對話歷史 ingest 進 Mem0/Zep
2. Inspection script 從 Mem0/Zep 內部 extract detection signal（哪個 fact 被標 superseded）
3. 跟 FC ground truth 比對，計算 detection precision/recall/F1

### 跟整體研究的連結

這是 3 天衝刺最 risk-heavy 的一天。Detection F1 數字是 §0.3 模式判定的核心 input。

| 模式 | 需要的 evidence |
|---|---|
| A propagation | Mem0/Zep detection F1 高 + MH end-to-end 低 |
| B detection + propagation | Mem0/Zep F1 低 + MH 低 + Oracle partial 改善 |
| C detection only | Mem0/Zep F1 低 + Oracle 改善大 |
| D reader | Detection 跟 EM 都不能解釋差距 |

### 具體執行內容

**3.1 Mem0 pipeline**（4 小時）

```python
# pipeline_mem0.py
from mem0 import Memory
import json
from tqdm import tqdm

def run_mem0_on_fc(fc_data, output_path):
    """
    對每個 FC instance:
    1. Ingest 對話歷史
    2. Query 並取得 answer
    3. Inspect Mem0 內部，找出哪些 fact_id 被標 superseded
    4. 算 detection F1
    """
    results = []
    for instance in tqdm(fc_data):
        memory = Memory.from_config(...)  # fresh per instance
        
        # Step A: ingest dialogue history
        for turn in instance['dialogue_history']:
            memory.add(turn['content'], user_id='fc_test', 
                       metadata={'fact_id': turn.get('fact_id'), 
                                 'serial': turn.get('serial_num')})
        
        # Step B: query
        answer = memory.search(instance['query'], user_id='fc_test')
        
        # Step C: extract detection signal
        # 方法 1: 看 retrieved memory 跟 ground truth supersession 比對
        # 方法 2: inspect internal _resolver output (如可暴露)
        all_memories = memory.get_all(user_id='fc_test')
        detected_supersessions = extract_supersessions(all_memories, instance)
        
        # Step D: 算 detection metrics
        det_metrics = compute_detection_pr(
            detected=detected_supersessions,
            ground_truth=instance['edit_pairs']
        )
        
        results.append({
            'qid': instance['id'],
            'predicted_answer': answer,
            'em': compute_em(answer, instance['gold_answer']),
            'detection_p': det_metrics['precision'],
            'detection_r': det_metrics['recall'],
            'detection_f1': det_metrics['f1'],
            'detected_pairs': detected_supersessions,
        })
    
    json.dump(results, open(output_path, 'w'))
```

**3.2 Zep pipeline**（3 小時）

```python
# pipeline_zep.py
from zep_python.client import Zep

def run_zep_on_fc(fc_data, output_path):
    zep = Zep(api_key='...', base_url='...')  # cloud or self-host
    
    results = []
    for instance in tqdm(fc_data):
        session_id = f"fc_{instance['id']}"
        
        # Ingest
        for turn in instance['dialogue_history']:
            zep.memory.add(session_id=session_id, messages=[{
                'role': 'user',  # FC 全是 user statements
                'content': turn['content']
            }])
        
        # Query
        memory_response = zep.memory.get(session_id=session_id)
        answer = query_zep_with_context(memory_response, instance['query'])
        
        # Detection signal: invalid_at 欄位
        edges = zep.graph.search(query='*', user_id=session_id)
        detected_supersessions = [e for e in edges if e.invalid_at is not None]
        
        # Detection metrics
        det_metrics = compute_detection_pr(
            detected=detected_supersessions,
            ground_truth=instance['edit_pairs']
        )
        
        results.append({...})  # 同 Mem0
    
    json.dump(results, open(output_path, 'w'))
```

**3.3 Entity ID mapping layer**（2-3 小時）

```python
# entity_mapper.py
def map_fc_to_system_entity(fc_entity, system_entities, method='exact'):
    """
    Given FC fact (e.g., "X is the capital of A"),
    find corresponding entity in Mem0/Zep internal representation
    """
    if method == 'exact':
        # Best case: surface form match
        return next((e for e in system_entities if fc_entity in e.name), None)
    elif method == 'fuzzy':
        # Fuzzy string match
        from rapidfuzz import process
        match, score, _ = process.extractOne(fc_entity, [e.name for e in system_entities])
        return match if score > 80 else None
    elif method == 'embedding':
        # Embedding similarity (last resort)
        ...
```

### Risk + Fallback

| Risk | Mitigation |
|---|---|
| Mem0 內部 supersession 標記不暴露 | Fallback：用 retrieved memory 的「old fact 不在 latest search result」當 detection signal（不完美但可用） |
| Zep self-host 太麻煩 | 用 Zep Cloud free tier，限制每 session 大小 |
| Entity mapping 完全失敗 | 取消 detection F1，只算 end-to-end EM。模式判定退化為「Mem0/Zep MH 跟 oracle MH 對比」 |
| Day 2 結束前沒跑完 setup | 只跑 Mem0 不跑 Zep（因 Zep API 通常較複雜），Day 3 再補 |

### Time Budget

8 小時（全天）— 這是 3 天衝刺最重的一天

### Success Criterion

End of Day 2：
- Mem0 + Zep 都能 ingest 1 個 FC instance 並產出 (a) end-to-end answer (b) detection signal extraction
- Entity mapping 在 5 個 sample instance 上 verify 過
- Pipeline 準備好 Day 3 上午跑 full 100 題

如未達成（最有可能 Zep setup blocked），fallback：只跑 Mem0，Zep 留 W2 後半。

---

## Step 4: 跑 Full FC-SH/MH on Mem0/Zep + Detection F1

### 最終目標

產出 §1.5 對比表的完整數字，填好以下兩列：

| 系統 | FC-SH end2end | FC-MH end2end | Detection F1 | Retrieval Recall | Detection 對但 QA 錯 % |
|---|---|---|---|---|---|
| Mem0ᵍ | ? | ? | ? | ? | ? |
| Zep | ? | ? | ? | ? | ? |

### 跟整體研究的連結

這四欄數字直接 feed Day 3 下午的模式判定。沒有這個 evidence base，模式 A/B/C/D 判定都是猜測。

### 具體執行內容

```bash
# Day 3 上午
python pipeline_mem0.py --benchmark FC-SH --output results/mem0_fc_sh.json
python pipeline_mem0.py --benchmark FC-MH --output results/mem0_fc_mh.json
python pipeline_zep.py --benchmark FC-SH --output results/zep_fc_sh.json
python pipeline_zep.py --benchmark FC-MH --output results/zep_fc_mh.json

# 統計
python compute_summary.py --inputs results/mem0_*.json results/zep_*.json
# 產出 summary table
```

**Detection F1 計算邏輯**：

```python
def compute_detection_pr(detected_pairs, ground_truth_pairs):
    """
    detected_pairs: [(old_fact_id, new_fact_id), ...] from system
    ground_truth_pairs: [(old_fact_id, new_fact_id), ...] from FC dataset
    """
    detected_set = set(detected_pairs)
    gt_set = set(ground_truth_pairs)
    
    tp = len(detected_set & gt_set)
    fp = len(detected_set - gt_set)
    fn = len(gt_set - detected_set)
    
    precision = tp / (tp + fp) if (tp + fp) else 0
    recall = tp / (tp + fn) if (tp + fn) else 0
    f1 = 2 * p * r / (p + r) if (p + r) else 0
    
    return {'precision': precision, 'recall': recall, 'f1': f1, 'tp': tp, 'fp': fp, 'fn': fn}
```

**Detection 對但 QA 錯比例**：

```python
def compute_detection_correct_qa_wrong(results):
    """
    對每個 instance:
    - detection_correct = (detection_f1 == 1.0) i.e. perfect detection on this instance
    - qa_wrong = (em == 0)
    
    比例 = count(detection_correct & qa_wrong) / count(detection_correct)
    """
    detection_correct = [r for r in results if r['detection_f1'] == 1.0]
    if not detection_correct:
        return None
    qa_wrong_count = sum(1 for r in detection_correct if r['em'] == 0)
    return qa_wrong_count / len(detection_correct)
```

這個比例若高，說明 detection 不是 bottleneck（detect 對了還是答錯）→ 模式 A 或 D。

### Risk + Fallback

| Risk | Mitigation |
|---|---|
| API rate limit / cost | Mem0 用 OpenAI API（cost 中等）；Zep cloud 有 free tier 限制，必要時 batch 50 題 instead of 100 |
| 跑到一半失敗 | 確保 resume-safe，每跑完一題就寫入 json |
| Detection F1 因 entity mapping 不準而 noisy | 在 results 中保留 raw detected_pairs，事後可 re-compute |

### Time Budget

3-4 小時（上午）— 跑 FC-SH/MH × 2 系統，每個約 30-60 分鐘

### Success Criterion

對比表四欄數字（end2end SH / end2end MH / detection F1 / detection 對但 QA 錯 %）對 Mem0 + Zep 各自填好。如有缺項，明確標明原因（如 detection F1 因 mapping 困難無法計算）。

---

## Step 5: 結果分析 + 模式 A/B/C/D 判定

### 最終目標

基於 Day 3 上午數字 + W1 已有 oracle 數字，判定 §0.3 模式 A/B/C/D 中哪個最符合 evidence，並產出 1 頁分析報告作為 paper motivation 修訂依據。

### 跟整體研究的連結

這是 3 天衝刺的最終 deliverable。模式判定直接決定：
- Paper 主軸 framing（沿用 v7 mechanism claim 還是需要修正）
- Method 主推方向（detection / propagation / reader / 組合）
- W3 開始的具體實作焦點

### 具體執行內容

**5.1 整理對比表**（30 分鐘）

| 系統 | FC-SH | FC-MH | Detection F1 | Retrieval Recall | Det 對但 QA 錯 % |
|---|---|---|---|---|---|
| HippoRAG-v2 (vanilla) | 77% | 20% | 0 (no detection) | 97%+ | N/A |
| Mem0ᵍ | [Day 3 數字] | [Day 3 數字] | [Day 3 數字] | [estimated] | [Day 3 數字] |
| Zep | [Day 3 數字] | [Day 3 數字] | [Day 3 數字] | [estimated] | [Day 3 數字] |
| OA1 orig (passage filter) | - | [Day 1 數字] | 1.0 (oracle) | - | - |
| OA2 orig (fact filter) | - | 55% | 1.0 (oracle) | - | - |
| OA2 modified (fact filter + trailer) | - | 83% | 1.0 (oracle) | - | - |

**5.2 模式判定 decision tree**（1 小時）

```
Q1: Mem0/Zep detection F1 > 0.7?
├─ YES → 它們檢測得到 conflict
│   Q2: Mem0/Zep MH end-to-end < 30%?
│   ├─ YES → 模式 A (propagation 瓶頸)
│   │   Mem0/Zep 抓到衝突但答錯 → propagation/reasoning 才是核心
│   └─ NO → 它們其實也算工作，瓶頸不那麼明顯
│
└─ NO → 它們檢測 fail
    Q3: OA2 oracle MH 顯著高於 Mem0/Zep MH?
    ├─ YES → Detection 是瓶頸（模式 B 或 C）
    │   Q4: Oracle EM (55-83%) 還遠低於 Sim-OB 98%?
    │   ├─ YES → 即使 detection 對，propagation 仍有空間 → 模式 B
    │   └─ NO → Detection fix 後接近上限 → 模式 C
    │
    └─ NO → Oracle 也救不了 → 模式 D (reader 瓶頸)
```

**5.3 額外 sanity check**（30 分鐘）

- "Detection 對但 QA 錯 %" 高 vs 低
- Retrieval recall 是否在某個 setting 下崩壞
- Hop count 衰減 pattern：Mem0/Zep 在 4-hop 是否更慘

**5.4 1 頁分析報告寫作**（1.5 小時）

報告 structure：

```markdown
# Phase 0 三天衝刺結論：Multi-hop KU 瓶頸診斷

## 1. 數據總覽
[對比表]

## 2. 模式判定
基於 [具體 evidence]，判定為模式 [A/B/C/D]：
- [關鍵 evidence 1]
- [關鍵 evidence 2]

## 3. 對 paper main claim 的 implication
- v7 §1.1 mechanism claim：[需要修正 / 仍然成立 / 需要部分軟化]
- 對應修訂方向：[具體]

## 4. 對 W3 實作的 implication
- 主推方向：[detection / propagation / reader]
- 具體 first action：[具體]

## 5. 給老師對齊的問題
- 基於模式 X，paper 主軸應為 [XX]
- 具體請教：[2-3 題]
```

### Risk + Fallback

| Risk | Mitigation |
|---|---|
| 模式判定 ambiguous（多個模式都部分符合）| 在報告中明確 disclose，列 top 2 候選模式跟各自 implication |
| Mem0/Zep 結果跟 W1 oracle 不可比（如不同 prompt 條件）| 控制變因，對比時標明 prompt 條件，必要時補 OA2 orig 跟 Mem0/Zep 同 prompt 的 vanilla 對照 |
| Detection F1 數字不可靠（因 entity mapping）| 報告中明確標明 detection F1 為 lower bound，主要靠 end-to-end EM 推論 |

### Time Budget

3-4 小時（下午）

### Success Criterion

1 頁報告產出，包含：
- 完整對比表（即使有缺項也清楚標明）
- 模式判定（A/B/C/D 之一，或明確說明 ambiguous + top 2 候選）
- v7 §1.1 mechanism claim 的修訂方向（仍然成立 / 部分軟化 / 需要重寫）
- W3 第一個動作建議
- 給老師的 2-3 個追問問題

---

## 3 天衝刺的整體 Risk Map

| 風險 | 嚴重程度 | 觸發 fallback |
|---|---|---|
| Day 1 上午：Mem0/Zep API 完全不暴露 detection signal | 高 | 切到 end-to-end only mode，detection F1 做 best-effort 估算 |
| Day 1 上午：Entity mapping 嚴重困難 | 高 | 同上 |
| Day 2 中途：Zep self-host 卡住 | 中 | Zep 用 cloud free tier 或只跑 Mem0 |
| Day 3 上午：跑到一半 quota 用完 | 中 | 跑前 50 題，標明 partial result |
| Day 3 下午：模式判定 ambiguous | 中 | 報告中列 top 2 候選 + 各自 implication |

**最壞情況下的 minimum viable deliverable**：
- Mem0 在 FC-SH/MH 的 end-to-end 數字（不要求 detection F1）
- 對比表至少填一半
- 模式判定退化為「不能完全判定，但 evidence 排除模式 X / 傾向模式 Y」

即使最壞情況，3 天結束時仍能 inform W3 方向，不致全廢。

---

## 整體 3 天的 Success Criterion

### 必達（minimum viable）

1. ✅ Mem0 在 FC-SH/MH 的 end-to-end EM
2. ✅ OA1 orig prompt 數字
3. ✅ 模式判定報告（即使 partial）

### 目標（regular success）

1. 上面 3 項
2. ✅ Zep 在 FC-SH/MH 的 end-to-end EM
3. ✅ Mem0/Zep detection F1（至少 lower bound）
4. ✅ 完整對比表
5. ✅ v7 §1.1 修訂方向明確

### Stretch（最佳情況）

1. 上面 5 項
2. ✅ "Detection 對但 QA 錯 %" 拆解到 hop count 維度
3. ✅ LongMemEval-KU setup 的 preliminary check（Day 3 末順手做）

---

## Day 4 起的後續動作（不在 3 天範圍但需提前規劃）

| 動作 | 觸發條件 | 預期 |
|---|---|---|
| LongMemEval-KU setup | 3 天結束後立刻啟動 | W2 後半 |
| W3 method 實作（按模式判定方向）| Day 3 報告產出後 | W3 |
| v8 report 修訂 | Day 3 報告 + LongMemEval preliminary 出來後 | W2 末 / W3 初 |
| 跟老師 sync | 模式判定後，帶報告 + 對比表 | W2 末 |

---

*Spec 整理日期：2026-04-30*
*執行週期：Day 1-3*
*下一個 milestone：Day 3 末模式判定 + 後續 W3 方向確認*
