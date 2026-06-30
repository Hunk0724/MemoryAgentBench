# 研究脈絡交接(換機後 Claude Code 先讀這份)

> 目的:讓新機器的 Claude Code 接上本研究的**脈絡 + 目前成果 + 下一步 + 最關鍵的定位難題**,以便直接續談「實作 / 寫作」而非從零開始。
> 搭配閱讀:[EXPERIMENT_RUNLIST.md](EXPERIMENT_RUNLIST.md)(實驗執行優先序)、[competitive_landscape_agentic_memory.md](competitive_landscape_agentic_memory.md)(對手生態與正交性判讀)、根目錄 `CLAUDE.md`(規則+環境+復現步驟)。

---

## 1. 一句話與主張

碩論:在 **mem0** 上的 **Knowledge Update (KU) 記憶框架**。核心主張——
**KU 是 query-time 問題,不是 write-time 的 commitment。**

過去記憶系統在 **write-time 就 commit KU**(LLM 一判斷哪個是「新版」就把舊版**不可逆刪掉**),一旦誤判即永久損失正解。我們把 KU **延後到 query-time** 解,三個 commitment:

1. **Faithful / conservative write**:忠實抽取所有 fact、**保留全版本**、write 時**不做跨筆 LLM 判斷**。
2. **Query-time KU resolution**:衝突只在 query 時、且 query-aware 地解。
3. **Decomposed, simple LLM tasks(for weak model)**:把難任務拆成小步——raw-question retrieval → identity grouping((S,P) 結構 + LLM)→ 3-way conflict-type → 確定性 temporal(僅 FRESHNESS 取最新)。

評測:**MemoryAgentBench(ICLR'26)FC-SH**(general fact)+ **LongMemEval(ICLR'25)KU**(personal fact)。

---

## 2. 目前成果快照(2026-06-30)

- **FC-SH 機制+結果已立穩**:ours has_pair EM **86–92% flat(6k→262k)**,贏 mem0 / Zep / long-context。
  - 機制證據:① write-time 不可逆性(L0 庫缺新版、且 **L0==L1** → 不是檢索問題,是寫入時就丟了);② recall-ceiling vs EM 兩道關卡;③ both→new_only 的 resolution;④ additive ablation。
  - **核心現象**:FC-SH conflict-type **97% freshness** → **structural (S,P)+temporal 是 workhorse**;conflict-type 主要是給 LongMemEval 多值個人事實(complementary 29%)用的。
- **LongMemEval**:ours KU **83.3%**(gpt-4o-mini judge),泛化已驗證;**baselines(mem0 / vanilla / Zep)full run 尚未完成**(smoke 過、可 resume)。Mode B(問歷史值/新舊雙值)強化 keep-all 主張,列 future work,不實作 resolver。
- **公平性 audit 已做**:metric / query template / GT / baseline prompt 全未動;唯一 flag = chunk_size 512 對 Zep 可能不利 → 建議補 **Zep@4096**。

> 證據鏈分層術語:**L0**(memory-bank 狀態)→ **L1**(retrieved top-100)→ **L2**(resolved final context)→ **L3**(EM)。

---

## 3. ★ 最關鍵的待解:研究「定位」難題

**這是目前最缺、最該一起想清楚的部分(不是缺實驗,是缺 framing)。**

困境:
- 一堆人在做**大題目**(general / long-term memory 平台:cognee、supermemory、mempalace…見 landscape 文件);我們做的是**窄而深的 Knowledge Update**。
- 我們很容易被歸到兩個大筐而失焦:(a)「memory systems 一般工程」、(b)「memory / knowledge **conflict** 的大問題」。
- 目前**比較對象太少**(只有 mem0 / Zep / long-context),**沒有對到很多論文** → 審稿人會問「你跟誰比、你的 novelty 邊界在哪」。
- 隨手一抓就一堆套件 → 看起來擁擠,但**多數與我們正交**(見下)。

定位要明確切出的三件事:
1. **Problem scoping**:KU ⊂ memory,但要**排除正交層**——retrieval/向量(C 類)、context/KV-cache 壓縮(B 類)、codebase memory(D 類)都不是我們要解的;我們解的是「同一 store 內,事實**隨時間被更新**時,怎麼在不破壞舊版的前提下答對」。
2. **與「conflict resolution 大問題」的切割**:我們不是要解所有衝突,而是主張**衝突解決的時機(write→query)與方式(non-destructive + decomposed)**。差異化賣點:**可逆性(non-destructive)**、**weak-model 友善的拆解式 pipeline**、**query-time / query-aware resolution**。
3. **對的 baseline & related work**:baseline = 會在 write-time 做 destructive update 的系統(mem0 native、Zep 的 invalidation);related work 要找「KU / temporal fact / memory update」這條線的**方法論論文**,而不是平台型 repo。

> KU 分類(已定錨,見 `docs/.../ku_taxonomy_and_scope*.md`):A=明確更正(出界)/ B=newer-wins(我們主場,FC 為主 + LongMemEval/BEAM 泛化)。keep-all 是必要設計(同 store 也要能答 temporal/歷史題)。

**新機器的 Claude 要能幫的事**:協助把上述定位寫成 intro / related work 的 framing,並從 landscape + 文獻中挑出**真正可比 / 該引用**的對象(區分「正交平台」與「同題方法」)。

---

## 4. 下一步(優先序)

1. **驗證論文核心主張:表現是否主要來自 structural 貢獻**
   - 先做 **ablation(structural-only)**:`(S,P)` group + 確定性 temporal,關掉 LLM grouping + conflict-type,對照 full phase2。腳本已備:`run_fc_sh.sh <L> ours_struct` vs `run_fc_sh.sh <L> ours`。**結果出來才決定怎麼 claim**(對照:FC-SH conflict-type 97% freshness → structural 很可能就是 workhorse)。
2. **驗證 weak-model regime 前提**:小模型下 ours 是否如預期(**ours 平緩、prior work drop**)。跑不同 model size:**Gemma-3-4B(small)→ mid model(Gemma 中型,之後可用 Google AI Studio API)**。先確認本地 RTX 4050 / Mac Studio 能否跑 local model。
3. **找 prior work 結構性失敗模式**:手動分析 mem0 / Zep 的失敗 case(**qid29** 是起點:mem0 write-time 把新版刪掉留舊版)。
4. **強化 narrative:完整 ablation**:量化每個 component(identity grouping / conflict-type / temporal)的貢獻。
5. **決定寫作方向**:依上述結果定 framing;**同步補 narrative 所需文獻**(與第 3 節定位連動)。

> 之後穿插:LongMemEval baselines full、gpt-4o judge paper-final、Zep@4096、多 seed variance、FC-MH 多跳。
