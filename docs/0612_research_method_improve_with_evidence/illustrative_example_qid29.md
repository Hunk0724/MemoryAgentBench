# Illustrative Example — qid29「Oscar Wilde 死於哪座城市」(vanilla 失敗 → U5 救回)

> **用途**：vanilla mem0 衝突解決失敗、**而 ours(U5) 救回**的對照式 illustrative example（比單純的 vanilla 失敗更有說服力）。
> 選此題因：(1) 實體有名（Oscar Wilde），(2) entity / 問句**不含**舊答案 "Paris"，wrong answer 可乾淨歸因到記憶庫，(3) U5 是教科書式 **SUPERSEDE** 修復，U5 log 還附人類可讀 reason。
> 落點：vanilla = `old_only / VISIBLE`（主軸戰場）；ours = `new_only` 且答對。對應 [research_narrative §2.2(c)](research_narrative_main_framing&evidence.md#L69) + §4.2/4.3 失敗模式翻轉。

**設定**：FC-SH 6k，backbone gpt-4o-mini，chunk512 / temp0 / l2 / openai embedding（matched re-run）。唯一變量 = update component（vanilla vs U5）。
**資料來源**：
- GT：`analysis/results/sh_6k_RUN_gt.json`
- vanilla：`logs/sh_6k_vanilla_rerun/{candidate_pool,update_decision}.jsonl`、`outputs/.../openai-rerun/...`、`outputs/rag_retrieved/Structure_rag_..._rerun/...`
- ours(U5)：`logs/sh_6k_u5/u5_decision.jsonl`、`outputs/.../openai-u5/...`、`outputs/rag_retrieved/Structure_rag_..._u5/...`

---

## 0. 衝突設定（GT）

| | 內容 | serial |
|---|---|---|
| old fact | `Oscar Wilde died in the city of Paris.` | seq **128** |
| new fact | `Oscar Wilde died in the city of Guangzhou.` | seq **270**（序號較大＝較新，FC 政策上應勝） |
| query | *Which city did Oscar Wilde die in?* | gold = **Guangzhou** |

entity「Oscar Wilde」/ 問句「which city ... die」皆不含舊答案 "Paris" → 答錯只能來自記憶庫，無字面洩漏。

---

## 1. VANILLA：衝突解到「錯的方向」→ old_only → 答舊版 ✗

### Step 1–2｜衝突可見：new 的 top-5 撈到 old（cos 0.7153）

```
cos=0.7153  Oscar Wilde died in the city of Paris.        <== OLD VERSION（衝突可見！）
cos=0.4736  The author of Lady Windermere's Fan is Oscar Wilde.
cos=0.3518  Amy Winehouse died in the city of Camden Town.
cos=0.3487  Andy Warhol died in the city of New York City.
cos=0.3301  Andy Warhol died in the city of Montmélian.
```

### Step 3｜update component 一度收下新版、卻在後續 chunk 親手刪掉它

`update_decision.jsonl` 中 Paris / Guangzhou 的事件序列：

```
chunk 3 : OLD  ADD    id=19   <- Paris 寫入
chunk 4 : OLD  NONE   id=37
chunk 5 : OLD  NONE   id=25
chunk 6 : NEW  ADD    id=73   <- Guangzhou 一度成功寫入！(此刻 store 同時有 Paris+Guangzhou)
chunk 7 : OLD NONE / NEW NONE
chunk 9 : OLD NONE / NEW NONE
chunk10 : OLD  NONE   id=45
chunk11 : OLD  NONE   id=90
chunk11 : NEW  DELETE id=98   <- update 把 Guangzhou 刪掉(真實 id,非幻覺)、卻對 Paris 判 NONE
```

→ **關鍵失敗**：衝突在 chunk 11 攤開（Paris 與 Guangzhou 並存於候選），update component 不但沒把 Paris→Guangzhou UPDATE，反而把**新版 Guangzhou 刪掉、留下舊版 Paris** = 把衝突解到**完全相反的方向**。這是 §3.1 所指「在 query 前就不可逆毀掉正解」的鐵證——而且新版一度已正確進庫，是被 ingestion 階段親手摧毀的。

### Step 4–6｜query

- top-100 檢索：`old_retrieved=True, new_retrieved=False`（Guangzhou 已被刪，撈不到）。
- 模型輸出：`Answer: Paris` → gold = Guangzhou → **EM = False**。

---

## 2. OURS (U5)：同一份候選 + ordinal → 判 SUPERSEDE → new_only → 答對 ✓

`u5_decision.jsonl`（處理 Guangzhou 的那次，chunk_ordinal=6）：

```json
classification = {
  "new_id": "n38", "existing_id": "97", "relation": "SUPERSEDE",
  "reason": "The new fact contradicts the existing death location of Oscar Wilde.",
  "merged_text": "Oscar Wilde died in the city of Guangzhou."
}
mapped_op  = { "action": "SUPERSEDE",
               "superseded_ids": ["40a31ca4-...-c5d138ac8273"],   // 舊 Paris entry
               "added_text": "Oscar Wilde died in the city of Guangzhou" }
```

- U5 把職責**解耦**：LLM 只輸出關係類型 `SUPERSEDE` + reason；**deterministic** 端把它映射成「DELETE 舊 Paris + ADD 新 Guangzhou」。
- **ordinal** 提供時序證據（Guangzhou 的 ingestion ordinal 比 Paris 晚）→ 支撐 SUPERSEDE 判斷，補上 vanilla 缺的「誰新誰舊」。
- 結果 store = `new_only`（只剩 Guangzhou）。

query 階段：

- top-100 檢索：`old_retrieved=False, new_retrieved=True`。
- 模型輸出：`Answer: Guangzhou` → gold = Guangzhou → **EM = True**。

---

## 3. 對照總表（唯一變量 = update component）

| 環節 | vanilla | ours (U5) |
|---|---|---|
| 衝突可見（new top-5 撈到 old）| ✓ cos 0.7153 | ✓（同一份候選）|
| update 對新版的處置 | chunk6 ADD → **chunk11 DELETE（親手毀掉新版）** | **SUPERSEDE**：DELETE 舊 Paris + ADD 新 Guangzhou |
| 時序訊號 | 無（不知 Guangzhou 較新）| **ordinal**（Guangzhou 較晚）作 SUPERSEDE 證據 |
| final store 狀態 | `old_only`（只剩 Paris）| `new_only`（只剩 Guangzhou）|
| query 檢索 | old_ret=True, new_ret=False | old_ret=False, new_ret=True |
| model 答案 | `Paris`（舊）✗ EM=False | `Guangzhou`（新）✓ EM=True |

> **一句話**：vanilla 在 ingestion 把已正確進庫的新版親手刪掉、留舊版（衝突解反方向，不可逆）；U5 用「解耦判斷／執行 + ordinal」在同一份候選上判 SUPERSEDE，讓正解進得了庫、檢索得到、答得對。這正是 §3「先保住資訊、把不可逆毀損降級」的最小可讀示範。

---

## 附：復現指令

```bash
cd /home/yhchiang/MemoryAgentBench/docs/0612_research_method_improve_with_evidence/scripts
python oldonly_visibility.py 6k vanilla     # qid29 在 18 個 VISIBLE old_only 內
# 其餘「vanilla old_only/neither → U5 救回」的同類例子：qid 33(rap rock 起源國), 60(John McVie 曲風)
# —機制相同(U5 SUPERSEDE)，但實體較冷門；qid29(Oscar Wilde)最平易近人。
```
