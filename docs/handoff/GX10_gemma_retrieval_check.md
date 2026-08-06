# GX10 查核請求 — local-model backbone 的抽取/檢索(bank = per-backbone P1 抽取)

> **機器分工**:GPT 系列(gpt-4o-mini / gpt-4.1-mini / gpt-5.4-mini)與 LME-KU 皆在**主開發機**跑,已在該機驗證;
> **GX10 只負責 local model**:gemma3-1b/4b/12b/27b、gemma2-9b、llama3.1-8b、qwen2.5-7b、mistral-7b。
>
> **已在主開發機確認的事實(重要,修正過往誤解)**:
> - canonical bank **不是 raw-fact bank**,而是 **ours P1 LLM 抽取(凍結 cache)**;store 對 `p1_caches*/extraction_cache_p1_{L}.json` 100% 命中。raw-fact bank(7/12)是中途產物,最終未用於 experiment.tex。
> - 抽取是 **per-backbone**:GPT tier 三個 cache md5 各異(gpt-4o-mini vs gpt-5.4-mini 僅 276/455 逐字相同)。
> - 因此**弱 backbone 的檢索 recall 可能真的較低**(是抽取沒把 gt_new 放進 bank,不是檢索器問題;embedder=text-embedding-3-small 與 backbone 無關)。這是需要 GX10 實測的 confound。
>
> **目標**:量出每個 local backbone 的「gt_new 進得了 answer LLM 的池嗎」,以判斷 backbone sweep 上
> 「表現差異來自 KU 判斷而非抽取/檢索」是否成立(或需在論文揭露抽取 confound)。

## 請在 GX10 上執行並回報(每個 local backbone)

### 1. 各 backbone 的抽取 cache 存在嗎?抽取用哪個 model?
```bash
cd <repo_root>
for bb in gemma3-1b gemma3-4b gemma3-12b gemma3-27b gemma2-9b llama3.1-8b qwen2.5-7b mistral-7b; do
  f="analysis/results/p1_caches__${bb}/extraction_cache_p1_6k.json"
  n=$(python3 -c "import json;c=json.load(open('$f'));print(sum(len(v) for v in c.values() if isinstance(v,list)))" 2>/dev/null)
  echo "$bb: cache_facts=$n (raw_fact_bank 455 為滿分基準)"
done
# 抽取 model:看各 backbone run 的 cost log extract_p1 欄
grep -h extract_p1 docs/0615_intro_framework_after_problem_statement/logs/cost_ours*__gemma3-1b.jsonl 2>/dev/null | head -1
```

### 2. 檢索池是否有 dump?（沒 dump 就無法算 gt_new∈pool，需決定是否重跑）
```bash
find outputs/rag_retrieved -maxdepth 1 -type d | grep -iE "gemma|llama|qwen|mistral" | grep -iE "no_p5|struct"
```

### 3. 若池存在：算各 backbone 的 gt_new∈top-100（6k has_pair）
```bash
conda activate MABench
python3 - <<'PY'
import glob, json, sys
sys.path.insert(0,'.'); sys.path.insert(0,'analysis')
from analysis.rescore_canonical import load_haspair
from analysis.compute_pool_acc_crosstab import classify_pool_state, extract_pool_texts
hp = load_haspair('6k')
for bb in ['gemma3-1b','gemma3-4b','gemma3-12b','gemma3-27b','gemma2-9b','llama3.1-8b','qwen2.5-7b','mistral-7b']:
    dirs = glob.glob(f'outputs/rag_retrieved/*{bb}*unified_no_p5*/k_100/factconsolidation_sh_6k/chunksize_512') \
        or glob.glob(f'outputs/rag_retrieved/*{bb}*unified_struct*/k_100/factconsolidation_sh_6k/chunksize_512')
    if not dirs: print(f'{bb:>12}: NO POOL DUMP'); continue
    d=dirs[0]; n=new=0
    for qid,row in hp.items():
        f=glob.glob(f'{d}/query_{qid}_context_*.json')
        if not f: continue
        pool=extract_pool_texts(json.load(open(f[0])),'retrieved_memories')
        st=classify_pool_state(pool,row.get('gt_fact_text') or '',row.get('old_fact_text') or '')
        n+=1; new+= st in ('PP-New','PP-Both')
    print(f'{bb:>12}: gt_new in top-100 = {new}/{n} = {100*new/max(n,1):.0f}%')
PY
```

### 4. Mem0 Vanilla(native)/ Zep 是否也 per-backbone 跑
```bash
ls -d outputs/*native*__*gemma* outputs/*native*__*llama* outputs/*zep*gemma* 2>/dev/null
```

## 回報格式
貼回 1–4 輸出。關鍵結論一句:
**各 local backbone 的 gt_new∈pool 是否仍 ~100%(→ 差異純判斷),還是弱 backbone 明顯掉(→ 抽取 confound,需論文揭露)?**
- 若池未 dump → 回報,再決定是否重跑 local backbone 並開 pool dump(資源密集,需先批准)。

---
_主開發機 2026-07-22 更新;GPT tier + LME 已於主機驗證,此單僅 local model。_
