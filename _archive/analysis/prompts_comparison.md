# Inference Prompt Comparison — vanilla / Oracle A / PAT / RPT / RPT-min

> 對比同一題在五個 setting 下,真正送進 Gemini 3.1 Flash-Lite 的 user message 結構。
> 範例題:**MH query 0**(3-hop, 3-conflict),GT = `Belgium`。

---
## 重要前提:Conflict Resolution rule 從哪來、5 setting 都有保留

`main.py` → `conversation_creator.py:187-188` 用 `templates.get_template('factconsolidation', 'query', 'rag_agent')` 抓 [`utils/templates.py:81`](../utils/templates.py#L81) 的 template,`.format(question=<原問題>)` 之後產生 `formatted_query`。**這就是 `data[].query` 存的內容,也是被 HippoRAG 當作 `query_solution.question` 的東西**。

此 task-level wrapper 含「序號越大越新越正確」的 conflict resolution rule:

```text
Pretend you are a knowledge management system. Each fact in the knowledge pool is provided with a serial number at the beginning, and the newer fact has larger serial number. 
 You need to solve the conflicts of facts in the knowledge pool by finding the newest fact with larger serial number. You need to answer a question based on this rule. You should give a very concise answer without saying other words for the question **only** from the knowledge pool you have memorized rather than the real facts in real world. 

For example:

 [Knowledge Pool] 

 Question: Based on the provided Knowledge Pool, what is the name of the current president of Russia? 
Answer: Donald Trump 

 Now Answer the Question: Based on the provided Knowledge Pool, What is the country of citizenship of the spouse of the author of Our Mutual Friend? 
Answer:
```

**所有 5 個 setting 的 user message 都包含整段這個 wrapper**(只是位置/包裝形式不同):

| Setting | wrapper 在哪 |
|---|---|
| Vanilla | 直接放在 `Wikipedia Title: ... ` 之後,`Question: <wrapper>\nThought: ` |
| Oracle A | 同 vanilla,passages 數量減少(去掉含 old 的) |
| PAT | 同 vanilla,passages 內加 fact-level annotation,前面加 PAT_INSTRUCTION |
| RPT | wrapper 被包在 `== QUESTION ==\n<wrapper>\nThought: ` 大標題段 |
| RPT-min | 同 vanilla,passages 前加 INSTRUCTION + inline `[SECTION X]` label |

---
## 0. Common header — 所有 5 個 setting 共用

Inference 是 4-message conversation。前 3 個 messages 完全相同(`rag_qa_musique` template),差別都在最後一個 user message。

**[1/4] system**:
```text
As an advanced reading comprehension assistant, your task is to analyze text passages and corresponding questions meticulously. Your response start after "Thought: ", where you will methodically break down the reasoning process, illustrating how you arrive at conclusions. Conclude with "Answer: " to present a concise, definitive response, devoid of additional elaborations.
```

**[2/4] user — one-shot demo**(只示意,實際是完整 Wikipedia 5 篇 + 1 question):
```text
Wikipedia Title: The Last Horse
The Last Horse (Spanish:El último caballo) is a 1950 Spanish comedy film directed by Edgar Neville starring Fernando Fernán Gómez.
Wikipedia Title: Southampton
The University of Southampton, which was founded in 1862 and received its Royal Charter as a university in 1 ...<truncated>
```

**[3/4] assistant — one-shot answer**:
```text
The employer of Neville A. Stanton is University of Southampton. The University of Southampton was founded in 1862. 
Answer: 1862.
```

---
## 1. Vanilla(原 HippoRAG-v2 baseline)

**修改深度**:無。`HippoRAG.py:rag_qa()` 直接組裝。

**[4/4] user — vanilla 結構**:

```text
Wikipedia Title: <passage 1: ~1900 chars>

Wikipedia Title: <passage 2: ~1900 chars>

...(共 10 個 `Wikipedia Title:` 區塊,順序為 PPR rank 1-10)

Question: Pretend you are a knowledge management system. Each fact in the knowledge pool is provided with a serial number at the beginning, and the newer fact has larger serial number. 
 You need to solve the conflicts of facts in the knowledge pool by finding the newest fact with larger serial number. You need to answer a question based on this rule. You should give a very concise answer without saying other words for the question **only** from the knowledge pool you have memorized rather than the real facts in real world. 

For example:

 [Knowledge Pool] 

 Question: Based on the provided Knowledge Pool, what is the name of the current president of Russia? 
Answer: Donald Trump 

 Now Answer the Question: Based on the provided Knowledge Pool, What is the country of citizenship of the spouse of the author of Our Mutual Friend? 
Answer:
Thought: 
```

**「序號越大越新」rule 位置**:在 `Question:` 之後,`Thought:` 之前(整段 task wrapper)。

---
## 2. Oracle A — 移除含 old fact 的 passages

**修改深度**:本題 keeps = `[2, 3, 4, 5, 8, 9, 10]`,移除 P1, P6, P7。其餘結構與 vanilla 完全一致。

**[4/4] user — Oracle A 結構**:

```text
Wikipedia Title: <passage 2>  # P1 已被移除

Wikipedia Title: <passage 3>

...(共 7 個 passages, P1/P6/P7 被移除)

Question: Pretend you are a knowledge management system. Each fact in the knowledge pool is provided with a serial number at the beginning, and the newer fact has larger serial number. 
 You need to solve the conflicts of facts in the knowledge pool by finding the newest fact with larger serial number. You need to answer a question based on this rule. You should give a very concise answer without saying other words for the question **only** from the knowledge pool you have memorized rather than the real facts in real world. 

For example:

 [Knowledge Pool] 

 Question: Based on the provided Knowledge Pool, what is the name of the current president of Russia? 
Answer: Donald Trump 

 Now Answer the Question: Based on the provided Knowledge Pool, What is the country of citizenship of the spouse of the author of Our Mutual Friend? 
Answer:
Thought: 
```

**「序號越大越新」rule 位置**:同 vanilla — `Question:` 後整段 wrapper。

---
## 3. PAT — fact-level annotation only

**修改深度**:
- (a)前面加 PAT_INSTRUCTION 段;
- (b)passage 內 fact 序號前加 [CURRENT FACT] / [OUTDATED FACT];
- 其餘結構與 vanilla 完全一致。

**PAT_INSTRUCTION** 內容:

```text
Some facts in the context below have been pre-annotated:
- [CURRENT FACT] marks information that is up-to-date.
- [OUTDATED FACT] marks information that has been superseded by a later statement.

When answering, use [CURRENT FACT] as the source of truth. You may reference [OUTDATED FACT] only if the question explicitly asks about historical states.
```

**[4/4] user — PAT 結構**:

```text
<PAT_INSTRUCTION>

Wikipedia Title: <passage 1, 含 `[OUTDATED FACT] 107. The author of Our Mutual Friend is Charles Dickens.`>

Wikipedia Title: <passage 2, 含 `[CURRENT FACT] 146. The author of Our Mutual Friend is Charles Darwin.`>

...(共 10 個 passages,所有 has_pair hop 的 GT/Old 都被相應標記)

Question: Pretend you are a knowledge management system. Each fact in the knowledge pool is provided with a serial number at the beginning, and the newer fact has larger serial number. 
 You need to solve the conflicts of facts in the knowledge pool by finding the newest fact with larger serial number. You need to answer a question based on this rule. You should give a very concise answer without saying other words for the question **only** from the knowledge pool you have memorized rather than the real facts in real world. 

For example:

 [Knowledge Pool] 

 Question: Based on the provided Knowledge Pool, what is the name of the current president of Russia? 
Answer: Donald Trump 

 Now Answer the Question: Based on the provided Knowledge Pool, What is the country of citizenship of the spouse of the author of Our Mutual Friend? 
Answer:
Thought: 
```

**「序號越大越新」rule 位置**:同 vanilla(在 Question 後),PAT_INSTRUCTION 不重複此 rule,只說明 [CURRENT/OUTDATED FACT] 怎麼用。

---
## 4. RPT — full structural reorganization

**修改深度大**:整個 user message 用 `== HEADER ==` 重組。

**[4/4] user — RPT 結構**:

```text
== SECTION A: ACTIVE FACTS (USE THESE FOR YOUR ANSWER) ==
Passages in this section contain current factual statements. ...

Wikipedia Title: <Section A passage 含 [CURRENT FACT] 標記>
...(共 7 個 Section A passages)

== SECTION B: SUPERSEDED HISTORY (DO NOT USE FOR DIRECT ANSWER) ==
Passages in this section contain factual statements that have been replaced ...

Wikipedia Title: <Section B passage 含 [OUTDATED FACT] 標記>
...(共 3 個 Section B passages)

== INSTRUCTIONS ==
1. Your answer MUST be derived only from facts in SECTION A.
2. SECTION B contains outdated information. Do NOT use any fact from Section B...
3. If a fact in SECTION A is marked with [CURRENT FACT], it is the authoritative version...
4. Only reference SECTION B if the question explicitly asks about historical or past states.

== QUESTION ==
Pretend you are a knowledge management system. Each fact in the knowledge pool is provided with a serial number at the beginning, and the newer fact has larger serial number. 
 You need to solve the conflicts of facts in the knowledge pool by finding the newest fact with larger serial number. You need to answer a question based on this rule. You should give a very concise answer without saying other words for the question **only** from the knowledge pool you have memorized rather than the real facts in real world. 

For example:

 [Knowledge Pool] 

 Question: Based on the provided Knowledge Pool, what is the name of the current president of Russia? 
Answer: Donald Trump 

 Now Answer the Question: Based on the provided Knowledge Pool, What is the country of citizenship of the spouse of the author of Our Mutual Friend? 
Answer:
Thought: 
```

**「序號越大越新」rule 位置**:在 `== QUESTION ==` 大段裡(整段 wrapper 被包進去)。同時 INSTRUCTIONS 1-4 又獨立提供 Section A/B rule。**此 setting 同時存在兩套 conflict-resolution signaling**(序號規則 + Section 規則)。

---
## 5. RPT-min — minimum modification + section partition

**修改深度**:
- (a)前面加 RPT_MIN_INSTRUCTION;
- (b)每個 passage 前加 inline `[SECTION A: ACTIVE]` 或 `[SECTION B: SUPERSEDED]`;
- (c)passage 內 fact-level annotation 同 PAT;
- (d)Section A passages 排前,Section B passages 排後;
- **`Wikipedia Title:` 句法保留**,**`Question:/Thought:` trailer 完全一致**。

**RPT_MIN_INSTRUCTION** 內容:

```text
Some retrieved passages contain conflicting facts. They are pre-organized into two groups by recency:
  - Passages prefixed with [SECTION A: ACTIVE] contain current factual statements (some facts highlighted with [CURRENT FACT]). USE these for your answer.
  - Passages prefixed with [SECTION B: SUPERSEDED] contain outdated facts (specific outdated facts marked with [OUTDATED FACT]). DO NOT use any fact from Section B as your answer.
Within Section A, ignore any facts marked [OUTDATED FACT]. Only reference Section B if the question explicitly asks about historical states.
```

**[4/4] user — RPT-min 結構**:

```text
<RPT_MIN_INSTRUCTION>

[SECTION A: ACTIVE] Wikipedia Title: <passage 2, 含 `[CURRENT FACT] 146. ...Charles Darwin.`>

[SECTION A: ACTIVE] Wikipedia Title: <passage 3>

...(共 7 個 [SECTION A] passages,順序為 PPR rank,Section A 排前)

[SECTION B: SUPERSEDED] Wikipedia Title: <passage 1, 含 `[OUTDATED FACT] 107. ...Charles Dickens.`>

[SECTION B: SUPERSEDED] Wikipedia Title: <passage 6>

...(共 3 個 [SECTION B] passages)

Question: Pretend you are a knowledge management system. Each fact in the knowledge pool is provided with a serial number at the beginning, and the newer fact has larger serial number. 
 You need to solve the conflicts of facts in the knowledge pool by finding the newest fact with larger serial number. You need to answer a question based on this rule. You should give a very concise answer without saying other words for the question **only** from the knowledge pool you have memorized rather than the real facts in real world. 

For example:

 [Knowledge Pool] 

 Question: Based on the provided Knowledge Pool, what is the name of the current president of Russia? 
Answer: Donald Trump 

 Now Answer the Question: Based on the provided Knowledge Pool, What is the country of citizenship of the spouse of the author of Our Mutual Friend? 
Answer:
Thought: 
```

**「序號越大越新」rule 位置**:同 vanilla — `Question:` 後整段 wrapper(沒被改寫成 `== QUESTION ==`)。RPT_MIN_INSTRUCTION 同時提供 Section A/B rule。**此 setting 也同時存在兩套 signaling,但 trailer 結構是 vanilla**。

---
## Usable subset 範圍說明

以上五個 setting 全部只跑 Oracle A 篩出的 usable subset(同一份題目集),確保對比 fair。

| 任務 | usable n | 篩選條件 |
|---|---:|---|
| FC-SH | 64 / 100 | (1) has_pair(MQuAKE 確認新舊事實對存在);(2) 新舊事實**都**在 HippoRAG top-10;(3) 新舊事實**不在同一 chunk** |
| FC-MH | 66 / 100 | 同上,但條件須對**所有** has_pair hops 都成立 |

Vanilla 的 baseline accuracy(在這個 subset 上,**並非整個 100 題**)為:
- FC-SH:43 / 64 = 67.2%
- FC-MH:18 / 66 = 27.3%

被排除的題目分布:
- FC-SH 排除 36 題:no_conflict_pair 26 題、same_passage 9 題、only-Old retrieved 1 題
- FC-MH 排除 34 題:has_same_passage 27 題、old/gt missing 7 題

---
## RPT-min 跑出來後可回答的 ablation question

已知:
- **Vanilla** = SH 67.2% / MH 27.3%(usable subset 上)
- **PAT**(vanilla + fact-level annotation + 軟性 prompt)= SH 71.9% / MH 42.4%
- **Oracle A**(passage filter)= SH 96.9% / MH 63.6%
- **RPT**(structure 大重構 + Section + 強 instructions)= SH 100% / MH 80.3%

RPT-min 介於 PAT 與 RPT 之間,設計目的是 **isolate**「Section partition + 強 instruction」的純效果。

| RPT-min 結果 | 解讀 |
|---|---|
| 接近 RPT(SH ~100%, MH ~80%) | Section partition + instruction 是真 driver;`== HEADER ==` 結構重構是 cosmetic,對 LLM attention 無實質影響 |
| 接近 PAT(SH ~72%, MH ~42%) | inline label + leading instruction 不夠強,LLM 需要 `== HEADER ==` 大結構才能對齊 attention;**RPT 強的部分原因是 prompt 結構重構,不是 instruction** |
| 介於 PAT 與 RPT 之間 | 兩個都貢獻;Section partition 是必要,結構重構是加分 |
