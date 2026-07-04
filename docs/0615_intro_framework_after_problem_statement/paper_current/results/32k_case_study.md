# FC-SH 32k Case Study:LLM grouping/conflict-type 在哪些 long-tail 上有用、哪些救不回

> **問題**:`ours_struct`(只 (S,P) group + 確定性 temporal)vs `ours`(full phase2:P3 LLM grouping + P5 conflict-type)在 32k FC-SH has_pair 上差 6 題(`ours_struct 51/65` vs `ours 57/65`)。
> **目的**:逐題拆解,看 LLM 元件到底救了哪些 long-tail、又有哪些 long-tail 連 LLM 都救不回 → 用來精準描述 method 的能力邊界。
> **資料來源**:Mac Studio 從零重跑(2026-06-30),`outputs/rag_retrieved/.../query_<qid>_context_0.json` + `analysis/results/sh_32k_mquake_analysis.json`。腳本 `/tmp/case_study_32k.py`。
> **搭配**:[reproduction_log_mac_studio.md](../../handoff/reproduction_log_mac_studio.md)(本機重現紀錄)、[method_pipeline_and_prompts.md](method_pipeline_and_prompts.md)(method 元件定義)、[experiment_results.md](experiment_results.md) §1.1(主結果表)。

---

## 0. 一句話結論

**LLM grouping/conflict-type 的真正價值 = 救「同 subject、不同 predicate 寫法」(stem vs full form)的 long-tail(6/65 has_pair = 9.2pp);對 subject alias、關係反轉、triple-null 三種 long-tail 仍救不回**。原報告中「LLM 救回 8 題」有 2 題是 answer-LLM noise(同 final context、不同 answer)— **真實貢獻 = 6 題**。

---

## 1. has_pair 對位拆解(32k,65 題)

| 拆解 | 題數 | qid 列表 |
| :---: | :---: | :--- |
| both right | 49 | (略) |
| **LLM helps**(ours ✓、struct ✗) | **8** | 1, 2, 3, 65, 68, 81, 87, 94 |
| **LLM hurts**(ours ✗、struct ✓) | **2** | 16, 46 |
| **both wrong** | **6** | 8, 9, 21, 27, 32, 51 |

**淨 delta**:struct − ours = −6(has_pair)= −9.2pp。

---

## 2. 失敗模式定義

| Mode | 條件 | 對應 method 失效點 |
| :---: | :--- | :--- |
| **A** | new/old triple 同 subject_id、predicate_norm 字面不同 | P2 predicate canonicalize 失敗(stem vs full form 等) |
| **B** | new/old triple subject_id 字面不同(但實體相同) | P2 subject normalize / alias 失敗 |
| **C** | new 的 subject == old 的 object(或反之),subject↔object 對調 | 關係反轉(逆向 predicate) |
| **D** | new 或 old 的 triple is null | P2 抽取 fail(triple-null) |
| **E** | 同 (S, P)、ordinal 也順,但 EM 仍錯 | 看 final context:若 ctx 對但 EM 錯 → answer-LLM noise;若 new seq < old seq → benchmark 標註錯 |
| F | new 不在 retrieved top-100 | retrieval miss(raw-q 後幾乎無此情況) |
| G | ours phase2 LLM grouping 跨 (S,P) 接到 → struct 看不見 | 上面 A/B/C 救回時的具體機制(統合在 A/B/C 內紀錄) |

---

## 3. LLM helps — 8 題逐題

> **預期**:LLM grouping/conflict-type 在 ours 救回、struct 漏掉 → 看 struct 為什麼漏。
> **發現**:6 題是真正「LLM 救 stem vs full predicate」、**2 題是 answer-LLM noise**(同 ctx 不同 answer)。

### 3.1 真正救回 — A mode(6 題,全是 predicate stem vs full form)

| qid | 問題 | GT new | predicate 變體 |
| :---: | :--- | :--- | :--- |
| 1 | What position does Nick Rimando play? | flanker | `plays position of` vs `plays the position of` |
| 3 | Which religion is Morris Iemma affiliated with? | Methodism | `is affiliated with` vs `is affiliated with the religion of` |
| 65 | Which religion is Bahawalpur State affiliated with? | Catholic Church | 同上 |
| 81 | Which country was pesäpallo created in? | Philippines | `was created in` vs `was created in the country of` |
| 87 | Which religion is Natalie Portman affiliated with? | interdenominational organization | 同 3 |
| 94 | Which sport is shooting guard associated with? | rugby | `is associated with` vs `is associated with the sport of` |

**機制**:P2 LLM 對同一述詞,在不同 chunk 上下文中偶爾抽 stem(`is affiliated with`)、偶爾抽 full form(`is affiliated with the religion of`),兩者 `normalize_predicate` 後仍字面不同 → struct 的 `(S, P)` key 不同 bucket。LLM grouping(P3 in dynamic_pool)能識別兩者同 fact → 群在一起 → P5 判 FRESHNESS → 取最新。

**典型痕跡**(qid 1):
```
new triple: (nick_rimando, plays the position of, flanker)   ord new=...
old triple: (nick_rimando, plays position of, goalkeeper)    ord old=...
struct final ctx: new=Y old=Y    (兩版都被留,無條件 argmax 各群一個,合併後仍有 old)
ours   final ctx: new=Y old=N    (LLM 群在一起 + 判 FRESHNESS + 丟舊)
```

### 3.2 偽救回 — answer-LLM noise(2 題,E mode)

| qid | 問題 | 同 (S,P) | ord new vs old | struct final ctx | ours final ctx |
| :---: | :--- | :---: | :---: | :---: | :---: |
| 2 | Which sport is power forward associated with? | ✓ | 49 vs 33 | new=Y old=N | new=Y old=N |
| 68 | Who is the developer of Internet Explorer 5? | ✓ | 60 vs 57 | new=Y old=N | new=Y old=N |

**關鍵**:**struct 與 ours 的 final context 完全相同**(都正確收斂到 new),但 struct EM=False、ours EM=True。**這不是 LLM grouping 救回,是 answer-LLM 在 gpt-4o-mini server-side bf16 noise 下,同一 ctx 兩次跑出不同答案**。

→ **LLM 元件真正淨貢獻 = 6 題(全 A mode),不是 8 題**。

---

## 4. LLM hurts — 2 題逐題

> ours 有 LLM 元件反而錯,struct 沒有 LLM 反而對。

### 4.1 qid 16 — E mode(answer-LLM noise,反向)
```
Q: Which sport is Jeff Hornacek associated with?
GT new: association football  (old: basketball)
same_S same_P, ord new=58 old=42
struct ctx: new=Y old=N   → EM=True
ours   ctx: new=Y old=N   → EM=False
```

同 §3.2,**ctx 完全相同但 answer 不同**;這次 noise 倒向 struct 對、ours 錯。

### 4.2 qid 46 — C mode(關係反轉)
```
Q: Who is the author of Inuyasha?
GT new: Terrance Dicks         (old: Rumiko Takahashi)
new triple: (inuyasha,           has author,         Terrance Dicks)
old triple: (rumiko_takahashi,   is the author of,  Inuyasha)
                                       ^^^ subject↔object 對調 ^^^
struct ctx: new=Y old=Y   → EM=True
ours   ctx: new=Y old=Y   → EM=False
```

**機制**:struct 的 (S, P) bucket 在 subject `inuyasha` 與 `rumiko_takahashi` 分開,各 bucket 只有 1 筆 → 都當 singleton 留下,answer-LLM 看到「Inuyasha 的作者是 Terrance Dicks」這條直接答對。

ours 的 LLM grouping 在 dynamic_pool 把 `(inuyasha, has author, Terrance Dicks)` 與 `(rumiko_takahashi, is the author of, Inuyasha)` 群在一起(LLM 識別「都是談 Inuyasha 的作者」),P5 判 FRESHNESS 後 ordinal argmax 取最新,但 keep-all-on-tie 仍把舊的留 → final ctx 還有 old,answer-LLM 看到「Inuyasha 的作者是 Rumiko Takahashi」+「Inuyasha 的作者是 Terrance Dicks」混合,answer 偏向 Rumiko Takahashi(常識先驗壓制)→ 錯。

> **這正是 paper 在批的「LLM judge 的不可靠性」反向案例**:LLM grouping 過於敏感反而把不該合的合起來、引入 noise。**ours 不是嚴格優於 struct,而是 high-variance trade**。

---

## 5. both wrong — 6 題(structural + LLM 都救不回)

| qid | mode | 機制 |
| :---: | :---: | :--- |
| **8** | **E (標註錯)** | new seq=707 < old seq=1929 → 違反 FC「較大 serial = 新」規則,**benchmark 自己標錯**(paper §3.4 已知) |
| **9** | **E (標註錯)** | new seq=1291 < old seq=2016,同上 |
| **21** | **A** | `is associated with` stem vs `is associated with the sport of` full;LLM grouping **這題沒接到**(可能 retrieval 給的 candidates 在此題分散,P3 conservative 不群) |
| **27** | **C** | 關係反轉 + S 完全不同:new=`(midfielder, is associated with, sumo)` vs old=`(sport_of_association_football, has association, midfielder)` |
| **32** | **D-old** | old fact 的 triple is null(P2 LLM fail)→ 沒進 (S, P) 索引 |
| **51** | **B** | subject normalize fail:`ireland` vs `current_head_of_state_in_ireland`(同實體不同 surface) |

**真正 method fail = 4 題**(21, 27, 32, 51);**2 題是 benchmark 標註錯**(paper §3.4 完全對應:32k 預期 2 題標註錯,精確命中 qid 8, 9)。

### 5.1 qid 21 — A mode 中 LLM 也沒接到的例子
```
Q: Which sport is flanker associated with?
GT new: rugby     (old: rugby union)
new triple: (flanker, is associated with the sport of, rugby)
old triple: (flanker, is associated with,              rugby union)
struct ctx: new=Y old=Y  → EM=False(answer 受 rugby union 干擾)
ours   ctx: new=Y old=Y  → EM=False(LLM grouping 沒接 → ctx 同 struct)
```

→ 跟 §3.1 是同類 stem vs full,但這題 LLM 沒接到。可能因為 candidate 集裡有更多噪音(flanker 不只 2 個 entry),P3 的「保守不群」策略起作用 → 漏接。

### 5.2 qid 27 — C mode(關係反轉 + S 不同)
```
Q: Which sport is midfielder associated with?
GT new: sumo                                       (old: association football)
new triple: (midfielder,                       is associated with,     sumo)
old triple: (sport_of_association_football,    has association,       midfielder)
```

S 完全不同(`midfielder` vs `sport_of_association_football`)+ predicate 也不對應 → LLM 都接不到。

### 5.3 qid 32 — D-old(P2 抽取 fail)
```
Q: Which religion is Catholic bishop affiliated with?
GT new: Catholicism  (old: Catholic Church)
new triple: 正常
old triple: NULL  ← P2 LLM 抽不出 triple(可能 "Catholic Church" 觸發 LLM 把整句當主觀/複雜)
```

old 沒進 (S, P) 索引 → struct 自然漏;ours phase2 的 dynamic_pool 也包不進去(triple null 仍能進 dynamic_pool,但 LLM grouping 對 triple-null fact 的 identity 判斷較弱)。

### 5.4 qid 51 — B mode(subject alias)
```
Q: What is the name of the current head of state in Ireland?
GT new: Roch Marc Christian Kaboré
new triple: (ireland,                            has current head of state, Roch ...)
old triple: (current_head_of_state_in_ireland,   is,                        Michael D. Higgins)
```

subject 完全不同(`ireland` vs `current_head_of_state_in_ireland`),同實體不同 surface;LLM grouping 也救不到。

---

## 6. 失敗模式統計

| Mode | helps(真實) | helps(噪音 E) | hurts | both wrong | total | LLM 救得到? |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **A** | 6 | — | 0 | 1 | 7 | ✅ 大多可(6/7)|
| **B** | 0 | — | 0 | 1 | 1 | ❌ |
| **C** | 0 | — | 1 | 1 | 2 | ❌(且偶反害)|
| **D** | 0 | — | 0 | 1 | 1 | ❌ |
| **E**(answer-LLM noise) | — | 2 | 1 | — | 3 | n/a(非方法問題)|
| **E**(benchmark 標註錯) | — | — | — | 2 | 2 | n/a(資料問題)|

---

## 7. 對 method framing 的精細含意

**核心修正**(原 32k +9.2pp claim):

| 原 framing | 精修 framing |
| :--- | :--- |
| 「LLM grouping/conflict-type 在 32k 救回 8 題」 | **「LLM 元件真正淨救回 6 題(全 A mode),另 2 題是 answer-LLM noise」** |
| 「LLM 元件貢獻 +9.2pp」 | **「LLM 元件對 'stem vs full predicate' 這類 P2 canonicalize 失敗有效;對 subject alias / 關係反轉 / triple-null 無效」** |

**結構性含意**:

1. **LLM grouping(P3)的能力邊界 = predicate 同 stem-vs-full 級別的細微措辭差**。再大的 surface variation(逆關係、subject alias)需要更強的 reasoning,P3 的「保守 + identity-only」設計刻意不去碰
2. **要進一步壓 32k has_pair**,優先順序應該是:
   - **(a) P2 抽取一致性**:強化 predicate canonicalize / subject canonicalize,讓 A/B mode 在寫入端就解掉 — 這正是 [method_pipeline_and_prompts.md §4.3](method_pipeline_and_prompts.md) lazy-triple 的反向方案
   - **(b) 逆關係知識**:處理 C mode(`A creates B ≡ B is created by A`)需要外部知識或 LLM 對「逆關係」的識別,目前 P3 沒這層
   - **(c) D mode(triple-null)** 的補強:P2b 已寫入 subject_fallback,但**目前 phase0 (struct) 沒讀,phase2 (ours) 也只用作 cross-subject guard**;可以擴展 P3 把 subject_fallback 視為弱 (S, P) 信號
3. **同 ctx 不同 answer 的 noise(E mode 3 題)**告訴我們 answer-LLM 對 32k 級別 ctx(2200 字元 input、含 retrieved memories)仍有 ~3% 不穩定性 → 多 seed 或更穩定 prompt 是潛在補強點

**對「decomposed simple tasks for weak model」claim**:
- LLM grouping 解的是 **(S, P) canonicalize 的 long-tail**,本身就是「小、local、cacheable」任務
- A mode 在 weak model 上是否仍能解?需要 Gemma-3-4B 實測(weak-model regime,next-step #2)
- 推測:A mode(同 subject、措辭微差)Gemma 應仍能識別;C mode(逆關係)強模型也吃力 → weak-model 上差距會在 A 上小、C 上大

---

## 8. 對 paper 寫作的具體建議

1. **§experiment_results 的 ablation 段**改成:「在 32k 上,LLM grouping 從 78.5%(struct)補到 87.7%(ours full),其中 6/8 題的 grouping 救回對應 stem-vs-full predicate canonicalize 失敗;2/8 為 answer-LLM noise」
2. **新增「LLM 元件的能力邊界」一節**(用本文件 §6 統計表),誠實揭露 LLM grouping 對 B/C/D mode 無效
3. **method limitations 加一條**:「P2 LLM 在同述詞上偶爾抽 stem / 偶爾抽 full form,造成 (S, P) canonicalize 失敗 ~7-10%。LLM grouping 接住約 90% 的此類失敗,剩 ~1-2% 仍漏」
4. qid 46(Inuyasha)是極好的「LLM grouping 反害」反例,可寫成附錄 case
5. qid 8/9 標註錯與 paper §3.4 完全對應 — 這台跑出來精確命中 paper 預期,作為「重現性高」的旁證

---

## 9. 附:全 16 題完整資料

詳見 `/tmp/case_study_32k.py` 跑出的逐題 dump(retrieved triple、final ctx、answer 等)。後續若要進論文,可整理成 LaTeX 表格進 appendix。
