# Weak-Model Regime — GX10 Handoff(2026-07-01,revised 2026-07-01 深夜)

## ★ 精簡 minimum-viable scope(最少時間拿到核心 evidence)

**只跑 8 cell 就能拿到 paper 定位的核心 evidence**:

```
SIZES:   27b → 12b        (先強端)
LENGTHS: 6k, 32k          (32k 有 sweet-spot signal)
METHODS: ours_struct, ours_p3_only_no_struct   (apple-to-apple)
= 2 × 2 × 2 = 8 cell
```

**期待觀察 & 決策樹**:

| GX10 27b × 32k | GX10 12b × 32k | 對 claim 的意義 |
| :---: | :---: | :--- |
| p3_only ≈ struct | p3_only ≈ struct | Gemma 12b 還太強,補跑 4b/1b 才會崩 |
| p3_only ≥ struct | **p3_only ≪ struct** ★ | ★ **核心 evidence 拿到**:「強 backbone 對等 → 弱 backbone p3_only 崩」 → **structural anchoring 是 weak-model 的必要設計** |
| p3_only ≪ struct | p3_only ≪ struct | 甚至 27b 就崩 → structural 全域必要,故事更強 |
| p3_only ≥ struct | p3_only ≥ struct | 12b 仍太強,需要 1b/4b 才崩 → 補跑 |

若 12b 已看到明確 p3_only 崩 → **8 cell 就夠**,論文寫作可展開。
若還沒崩 → 追加 4b 或 1b。

**上游 Mac Studio 已有的參照(gpt-4o-mini)**:

| L | struct | p3_only | ours(full) |
| :---: | :---: | :---: | :---: |
| 6k | 93.2 | 91.9 | 91.9 |
| 32k | 78.5 | **87.7** ★ | 86.2 |
| 64k | 86.4 | 89.4 | 90.9 |

→ 強 backbone 上 p3_only 32k **+6 vs struct**。GX10 要驗弱 backbone 上這條會不會翻轉。

---

## (下面是原完整 handoff,對 24-cell 全 matrix 的計畫,若 8-cell 精簡跑完仍想擴展再看)

---



> **目的**:在 ASUS Ascent GX10(NVIDIA GB10 Superchip)上跑 Gemma3 weak-model matrix,驗證**「LLM 元件貢獻隨 backbone 變弱而下降,structural-only 平穩」**。
> **搭配**:[START_HERE.md](START_HERE.md)(總開工)、[RESEARCH_CONTEXT.md](RESEARCH_CONTEXT.md)(主張+定位)、[reproduction_log_mac_studio.md](reproduction_log_mac_studio.md)(Mac Studio 18 cell 已重現,paper baseline 對齊度 ~81%)、`docs/.../paper_draft&materials/32k_case_study.md`(Mac Studio 32k LLM helps/hurts 對位拆解)。

---

## 0. 一句話

跑 `gemma3:{1b,4b,12b,27b}` × `FC-SH {6k,32k,64k}` × `{ours, ours_struct}` = **4 × 3 × 2 = 24 cell**。
每個 model 跑完 6 cell 再切下一個 model,**serial**,中間 `ollama stop` 釋放 RAM。
**順序**:`1b → 12b → 4b → 27b`(1B smoke 通過 → 12B 中等 baseline → 4B → 27B 上界)。

---

## 1. 預期結果(method claim 假設)

| Backbone 強度 | 預期 ours has_pair | 預期 ours_struct has_pair | 預期 (ours - struct) |
| :--- | :---: | :---: | :---: |
| gpt-4o-mini(baseline)| 87.7% @ 32k | 78.5% @ 32k | **+9.2pp** |
| gemma3:27b(強)| 接近 gpt-4o-mini | 同上 | 持平 |
| gemma3:12b(中)| 略低 | 略低 | 持平或略縮 |
| gemma3:4b(弱)| **顯著下降** | 仍維持 ~75% | **明顯縮小或翻負** |
| gemma3:1b(極弱)| **崩**(LLM grouping JSON 不穩 → fallback keep-all → 等於 struct)| 仍維持 ~75% | **~0pp**(LLM 元件失效) |

**最強的 paper narrative**:
- ours_struct 平穩(因為純 deterministic,backbone 影響只在 P1/P2 抽取質量)
- ours 上限隨 backbone 走;**1B 上 ours ≈ ours_struct**(LLM 元件失效歸零,但 structural 仍有效)
- 結論:「**decomposed simple tasks for weak model**」 → structural 在 weak model 上是 robust 解,LLM 元件 = optional bonus(強模型才有 +9pp)

**但要實測才知**:Gemma3:1b 是否會崩在 P1/P2 寫入端(連 ours_struct 都救不到)。

---

## 2. 環境 setup(從零開始,GX10 Linux + CUDA)

### 2.1 Repo + Python env
```bash
git clone -b exp/v2-llm-judge https://github.com/Hunk0724/MemoryAgentBench.git
cd MemoryAgentBench
git pull  # 確認 HEAD 至少包含 "Add weak-model regime infrastructure" commit

# Linux miniforge3
curl -fsSL https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-x86_64.sh -o /tmp/miniforge.sh
bash /tmp/miniforge.sh -b -p $HOME/miniforge3
ln -sf $HOME/miniforge3 $HOME/miniconda3  # 對齊 CONDA_SH 預設

source $HOME/miniconda3/etc/profile.d/conda.sh
conda create -n MABench python=3.10 -y && conda activate MABench
pip install -r requirements-core.txt
pip install ollama  # mem0 + agent.py 走 ollama 用
```

### 2.2 `.env`(自己填,不入 git)
**至少**:`OPENAI_API_KEY_A`(embedding 走 OpenAI;不要洩漏 .env 內容到 transcript)

### 2.3 資料
- FC-SH(由 `datasets` 自動抓 HF `ai-hyz/MemoryAgentBench`),不用手動
- LME 此波**不用**(我們只跑 FC-SH)

### 2.4 Ollama on GX10(Linux + CUDA / Blackwell)
```bash
curl -fsSL https://ollama.com/install.sh | sh  # Linux 原生支援
ollama serve &  # daemon
ollama --version  # 驗證

# 預拉 4 個 model(可選,run_gemma_matrix.sh 會自動 pull)
ollama pull gemma3:1b   # 815 MB
ollama pull gemma3:12b  # 8.1 GB
ollama pull gemma3:4b   # 3.3 GB
ollama pull gemma3:27b  # 17 GB
# 總磁碟 ~30 GB
```

驗證 Ollama 拿到 Blackwell GPU:
```bash
curl -s http://localhost:11434/api/ps  # 看 vram-based default
# 啟動 daemon 後 log 應顯示 library=cuda 或 library=blackwell;total_vram=<...>
```

---

## 3. 跑實驗

### 3.1 Smoke(必跑,~5-10 min in GX10)
```bash
MODEL_TAG=gemma3-1b \
MEM0_TRIPLE_MODEL=gemma3:1b \
MEM0_TRIPLE_OLLAMA_URL=http://localhost:11434 \
OLLAMA_NUM_CTX=8192 \
RUN_OAI_KEY_NAME=OPENAI_API_KEY_A \
bash docs/0615_intro_framework_after_problem_statement/scripts/run_fc_sh.sh 6k ours
```

→ 過了表示 pipeline 全鏈通(env、yaml、Ollama 連線、agent.py 的 ollama 分支、MODEL_TAG 後綴)。

### 3.2 完整 matrix(預估 GX10 serial ~8.5 hr)
```bash
# 預設順序 1b → 12b → 4b → 27b 已寫死;LENGTHS=6k 32k 64k;METHODS=ours ours_struct
bash tools/run_gemma_matrix.sh

# 或自選順序 / subset
SIZES="1b" LENGTHS="6k" bash tools/run_gemma_matrix.sh  # 只 smoke
SIZES="27b" bash tools/run_gemma_matrix.sh              # 只跑 27B
```

每個 cell 跑完 → SUMMARY md 自動更新(matrix log + 每 size 資源 jsonl + 自動 EM 統計)。

---

## 4. 監測

### 4.1 跑時即時
```bash
# 看 matrix 主 log
tail -F docs/0615_intro_framework_after_problem_statement/logs/gemma_matrix_*.log

# 看當前 cell 進度
ls -la outputs/gpt-4o-mini-mem0-chunk512-temp0-openai-unified__gemma3-*/Conflict_Resolution/

# 看 Ollama loaded model
curl -s http://localhost:11434/api/ps
```

### 4.2 跑完後分析
```bash
# 每個 size 的資源 summary(mean / p50 / p95 / peak RAM)
python tools/summarize_resource.py docs/.../logs/gemma_resource/gemma3-1b_*.jsonl
python tools/summarize_resource.py docs/.../logs/gemma_resource/gemma3-12b_*.jsonl
# ... 4 個 size

# 每個 cell 的 EM
python -c "
import json, glob, os
os.chdir(os.path.expanduser('~/MemoryAgentBench'))
for size in ['1b', '12b', '4b', '27b']:
    print(f'=== gemma3-{size} ===')
    for L in ['6k', '32k', '64k']:
        gt = json.load(open(f'analysis/results/sh_{L}_mquake_analysis.json'))
        gt_map = {g['query_id']: g for g in gt if 'query_id' in g}
        hp_ids = [q for q, g in gt_map.items() if g.get('conflict_type') == 'has_pair' and g.get('matched')]
        for m in ['', '_struct']:
            try:
                rf = glob.glob(f'outputs/gpt-4o-mini-mem0-chunk512-temp0-openai-unified{m}__gemma3-{size}/Conflict_Resolution/*sh_{L}*results*.json')[0]
                em = {r['query_id']: bool(r.get('exact_match')) for r in json.load(open(rf))['data']}
                hp = sum(em.get(q, False) for q in hp_ids)
                tot = sum(em.values())
                print(f'  {L} {(\"ours_struct\" if m else \"ours      \")}: has_pair {hp}/{len(hp_ids)} overall {tot}/100')
            except (IndexError, FileNotFoundError):
                print(f'  {L} {m}: missing')
"
```

---

## 5. 已知 caveats(Mac Studio 1B smoke 觀察到的)

1. **Triple confidence 常為 0.0**(Gemma3:1b 對 JSON `confidence` 欄填寫不一致;OpenAI 通常 ~0.95)
   - **不影響功能**:method 已無 confidence gate(`method_pipeline_and_prompts.md` 註明),0 仍進 (S,P) index
   - 較大 model(4B+)應該更穩

2. **`response_format` 強制 JSON 在弱模型上偶失敗**:
   - Ollama 自己會強制 `format=json`(mem0 內建已套)
   - 但內容仍可能不對 schema(如 P3 期待 `{"groups":[...]}` 但 Gemma 給 `{"identity_groups":[...]}`)
   - 已有 fallback:JSON 解析 fail → `complementary` (keep-all),safe-fail

3. **OpenAI embedding 仍走 OpenAI**:每個 cell 都會打 embedding;一個 size 跑 6 cell 約 3000-5000 embed call,**用 OPENAI_API_KEY_A 即可**

4. **num_ctx=8192** 對 P3 grouping 充裕(實測 max 2143 token,留 ~75% buffer)

5. **Mac Studio reproduction log 不要 commit 新 EM**:GX10 跑出的數字也是「本機重現」,不該成 baseline。EM 整理進 reproduction_log_gx10.md(新建)即可。

---

## 6. 完成後該做的事

1. **新增** `docs/handoff/reproduction_log_gx10.md`(對應 reproduction_log_mac_studio.md;紀錄 24 cell × paper 對齊度 + ablation trend × 4 model size)
2. **畫 4-axis figure**:`ours / ours_struct` × `1b/4b/12b/27b/gpt-4o-mini`,每長度一張(或 line chart 兩條線,x=model size)
3. **更新 RESEARCH_CONTEXT.md §2-4**:把「weak-model regime」從 next-step 升級為「已驗」
4. **case study qid 比對**:Mac Studio 32k 已有 8 helps(qid 1,2,3,65,68,81,87,94)— 看 1b/4b 上這 8 題是否仍救得回 = 「LLM 元件失效在哪一級 backbone」精準時刻

---

## 7. 規則(同 START_HERE,在 GX10 上也適用)
- 全程繁體中文
- 執行前先確認設計
- **驗證期用便宜 model**(我們本來就用 gemma3:1b smoke,符合)
- **不要讀 / grep .env**
- 任何啟動本機資源密集步驟(`ollama pull`、長跑、新 daemon)**要 user explicit approve 才動**
