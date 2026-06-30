# FC 衝突解決 — 研究主張、證據與方法框架（詳細版草稿）

> **用途**：把本研究線（2026-06-03 起）目前累積、可用於論文論述的部分，整理成一份**精確、自洽、資工系教授可讀**的詳細版。先求講清楚講準確；定稿後再另寫一份「去蕪存菁」的精簡版。
> **建立**：2026-06-06　**狀態**：草稿（含待補/待驗證標記）
> **配套**：分析以 [01](01_mem0_fc_setup_and_results.md)（single source of truth）為準；逐案 trace 見 [02](02_fc_sh_6k_failure_deepdive.md)/[03](03_fc_sh_32k_failure_deepdive.md)/[04](04_fc_sh_64k_failure_deepdive.md)；過程 log 見 [00](00_research_axis_and_setup.md)。

---

## 0. 一句話主張

> 在「LLM 參數知識尚未更新、需靠外部記憶提供最新（甚至反事實）事實」的場景下，**過去在 ingestion-time（write-time）就對知識衝突做不可逆裁決的記憶方法流派**（mem0 為代表），其衝突的**偵測**被迫在資訊寫入當下、僅憑一個用 embedding 相似度取回的局部候選集完成，且裁決一旦寫入即不可逆——因此在高實體重疊、反事實的衝突類型（MemoryAgentBench 的 FactConsolidation, FC）下會產生**隨對話歷史變長而累積、且無法於 query-time 回復**的記憶庫腐蝕。我們提出把衝突裁決**移到 query-time、可逆地**進行，以提供更乾淨且完整的記憶 context，作為最小可貢獻單元。

---

## 1. 問題定義與場景

### 1.1 增量記憶庫中的知識衝突
長期記憶 agent 會把對話歷史**增量**寫入外部記憶庫。隨時序演變，**同一個事實的新版本陸續到來**，使記憶庫中同時存在新舊版本。當 query 進來、檢索同時取回新舊版本時，系統（或下游 LLM）必須判斷**哪一版對當次 query 是正確的**。這就是知識衝突（knowledge conflict）問題。

### 1.2 兩種衝突類型：KU vs FC（本研究的關鍵區分）
| | **KU（Knowledge Update）** | **FC（FactConsolidation，本研究焦點）** |
|---|---|---|
| 內容 | 使用者個人資訊/狀態的自然更新（如「我從 NYC 搬到 LA」）| 世界事實被更新，且**新值與 LLM 參數知識相違背**（反事實）|
| 與 LLM 參數知識的關係 | LLM 本來就沒有 → 只要忠實取用外部記憶即可 | LLM **有**且相反 → 下游必須**抗拒自身參數知識**才能用外部記憶作答 |
| 例 | 「使用者偏好改成素食」 | 「The capital of France is Paris」後又寫入「The capital of France is Harare」；問首都應答 **Harare** |

> **術語澄清**：FC 在精神上接近 knowledge editing，但 knowledge editing 經典定義是**修改模型參數**（ROME/MEMIT 等）。本研究是**透過外部記憶/context 做反事實覆蓋（in-context override）**，不動模型參數。為避免混淆，後文一律用「反事實知識覆蓋」描述。

### 1.3 為什麼 FC 更難、且正是記憶方法該負責的
FC 讓記憶 agent 除了處理「使用者最新狀態」之外，還要處理「**世界事實被更新**」的情況。本研究主張：**記憶方法的職責，是回傳「忠實於外部記憶庫當前狀態」的乾淨 context**；至於下游 LLM 是否願意採信反事實（參數知識 vs context 之爭）是**另一個下游問題**，非本研究主要目標（見 §7 範圍）。

### 1.3.5 ★ 場景 motivation 與文獻錨點（2026-06-06 deep-research，claims 經 3-0 對抗驗證）

**現象（不是 FC 字面場景，而是其背後的真實現象）= 「stale 參數知識 + 演變的外部事實 + 必須 override」**，文獻已有現成詞彙與引用：
- **knowledge cutoff / staleness**：LLM「訓練一次、不再更新」，參數知識隨世界演變而過時。詞彙＝knowledge cutoff / temporal misalignment / dynamic / evolving knowledge。引用：FreshLLMs/FreshQA（Findings ACL 2024, arXiv 2310.03214）、StreamingQA（ICML 2022, 2205.11388）、RealTime QA（NeurIPS 2022 D&B, 2207.13332）、Temporal Misalignment（NAACL 2022, 2111.07408）。
- **fast-changing facts + append 串流**：FreshQA 分 never/slow/**fast-changing**/false-premise；StreamingQA 用 14 年時間戳新聞流 → 直接對應 FC 的累積更新。
- **最強具體 use case＝現任 officeholder（canonical Twitter-CEO 例）**：Zhou et al.（Context-faithful Prompting, EMNLP 2023 Findings, 2303.11315）「text-davinci-003 答 Jack Dorsey 而非 Elon Musk 為 Twitter CEO」。→ 論文 motivation 用這個錨，比自編場景有力（其他可引：prices、regulations、medical/legal guidelines）。
- **衝突命名**：Xu et al. 2024（Knowledge Conflicts for LLMs: A Survey, EMNLP 2024, 2024.emnlp-main.486）＝ **context-memory conflict**（＝我們的 context-vs-parametric）。
- **context 該 override + retrieval 勝 closed-book**：RealTime QA（open-book retrieval 34.6 vs closed-book ~15 EM）。

**直接支撐我們方法設計的文獻（重要）**：
- **支撐「決策改機械時序」(L1)**：LLM 是否採信 context **取決於其參數信心/記憶強度** — ClashEval（NeurIPS 2024 D&B, 2404.10198）：LLM 採信錯誤 context **>60%**；GPT-4 高記憶題即使有反證仍 **~50%** 答參數（Investigating Context-Faithfulness, Findings ACL 2025, 2409.10955）。→ **用 LLM 決定「哪版勝」會繼承此偏誤；改機械時序正好移除它**。（注意：>60% 是 perturbation sweep 的聚合、~50% 是 high-memory NQ 條件，勿當常數引用。）
- **支撐「別逼模型壓自己」**：FaithfulRAG（ACL 2025, 2506.08938）指現有 context-faithful 方法「強制壓制參數知識、反而有害」→ 支撐我們「用外部規則解版本衝突，而非逼模型壓自己」。

**scope nuance（必寫）**：Situated Faithfulness（ICLR 2025, 2410.14675）主張 override 該**有條件**（context 不一定可信）。但**我們假設記憶庫是權威來源**，衝突純粹是「哪版是當前」＝**recency 衝突，非 source-trust 衝突**。要在 scope 寫明，否則會被問。

> **術語精準**：FreshLLMs/RealTime QA 是 **in-context override**（不改參數），描述時用「以 context 刷新/override」勿說「刷新參數知識」，以免與 parameter editing 混淆。

### 1.4 資料與基準
- **MemoryAgentBench / FactConsolidation（FC）**，單跳子集 **FC-SH**（single-hop，排除多跳 retrieval confound）。
- FC 的事實源自 **MQuAKE-CF**（counterfactual 多跳知識編輯資料集）。每筆事實對應一個 (主詞, 關係, 物件)；context 是「附序號的事實清單」，benchmark 規則為「**序號越大＝越新＝正確答案**」（見 §3.4）。
- 對話歷史長度：**6k / 32k / 64k**（262k 規劃中）。每長度 **FC-SH 100 題** QA。

---

## 2. 相關工作：write-time 衝突解決流派

### 2.1 流派定義與「共同負債」
一類長期記憶方法在**資訊寫入時（write-time / ingestion-time）就偵測並處理衝突**，把裁決結果固化進記憶庫。呈現方式可不同：
- **破壞性**（mem0）：直接 UPDATE/DELETE，舊版消失。
- **標籤式**（Zep 類）：對記憶單元加時序/validity metadata，兩版都留但其一標為失效。

> **共同負債**：不論破壞或標籤，**裁決都在 write-time 提前固化、且事後不可逆**。對比之下，read-time/不裁決方法（把全部記憶留到 query 時再解，如 LCA full-context、純 RAG）不在 write-time 承諾。

### 2.2 代表方法
- 我們找到屬於此流派（含顯式衝突機制）的方法：**Zep、mem0、EMG-RAG、LightMem**。
  - **venue/year 線索（2026-06-06 deep-research，⚠️ 未經 claim 驗證，僅 lead）**：mem0→arXiv 2504.19413（2025/04）；Zep→arXiv 2501.13956（2025/01）；**EMG-RAG→ACL Anthology 2024.emnlp-main.281（EMNLP 2024，與原猜一致）**；LightMem→arXiv 2510.18866 + github zjunlp/LightMem +（ICLR 2026 slides，與原猜一致）。**正式引用前須各自開 paper 確認。**
- 本研究以 **mem0（vector 模式）** 為**深析代表**：開源、被廣泛引用、且其 ingestion pipeline 的衝突處理 component 清晰可拆解。**不宣稱 mem0 是唯一**，而是流派的代表性個案。
- **最接近的 related work＝MeLLo**（MQuAKE 附帶方法, EMNLP 2023, arXiv 2305.14795）：memory-based、非 weight editing，把**所有 edit 存外部**、frozen LLM 迭代生成一致答案。**與我們的差異**：MeLLo 存 curated edit set（**非 append-only 多次更新同一事實的串流**），且**不處理 write-vs-query timing 與 detection/decision 分離** → 我們的 delta 在這兩軸。
- ⚠️ **Q4 未驗證**：各系統（mem0/Zep/A-Mem/MemGPT/GraphRAG/HippoRAG/EMG-RAG/LightMem）的衝突處理是 **write-time 還是 query-time**、以及 **Zep/Graphiti 是否在 ingestion 用 LLM 做 bi-temporal edge invalidation 且不可逆** — deep-research **未涵蓋**，須後續直接讀 paper/code 確認（見 §8）。

### 2.3 mem0 的 ingestion pipeline（衝突處理在哪）
一個 chunk = 一次 `memory.add()`，三步：
1. **Extraction**：LLM 從 chunk 抽出 new facts。
2. **Candidate retrieval**：對每個 new fact 取 **cosine top-5** 既有記憶，聯集去重成候選池。
3. **Update decision**：一次 LLM call，輸入（所有 new facts + 候選池），對每個 new fact 判 ADD/NONE、對候選池既有記憶判 UPDATE/DELETE/NONE。**衝突偵測與裁決都壓在這一步、且不可逆寫入。**

---

## 3. 實驗設定（與 benchmark 預設的偏離，全部揭露）

> 原則：所有偏離都是為了讓 pipeline **跑得起來、可分析、可重現**，**非為了在 FC 上佔便宜**；逐項揭露理由。

| 項目 | benchmark 預設 | 我們的設定 | 理由 |
|---|---|---|---|
| Backbone LLM | gpt-4o-mini | **gemini-3.1-flash-lite**（內部+答題同顆，Vertex）| 對齊既定 backbone |
| Embedder | text-embedding-3-small | **Vertex text-embedding-004 (768d)** | 配合 Vertex |
| temperature | 0.7 / 內部 0.1 | **全 0** | 失敗歸因要單 trial 可重現 |
| chunk_size | 4096 | **512** | extraction recall + 逐 chunk 可分析 |
| Chunker | nltk 句切 | **fact-aware（每行一 fact）** | 句切會把序號與內文切散；fact-aware 讓每 fact 落唯一 chunk（+10pp EM，見 00 log）|
| Extraction prompt | `FACT_RETRIEVAL_PROMPT`（個人助理，**對通用知識大量回空**）| **L2 knowledge-extraction + frozen cache** | 預設對 FC 世界知識抽 0 筆；L2 補全並凍結，讓下游可公平比較 |
| 記憶模式 | — | **vector（無 graph）** | 歸因單純 |

### 3.1–3.3 已知 confound（**論述時必須一起講，否則 scale 主張會破**）
- **thinking level**：gemini-3.1-flash-lite 是 thinking model。6k/32k 用 **High thinking**；**64k 因 High 本機 OOM 改用 minimal thinking** → **64k 的 resolved% / H2-refuse 不可與 6k/32k 並列**（minimal 削弱了 H2-refuse，反而推高 resolved%）。
- **答題長度上限**：6k/32k 用 `generation_max_length=10` → 較長答案被**截斷成空輸出**（非失敗，見 §4.5）；64k 用 256（無此問題）。
- **embedder 敏感**：候選 top-5 是 embedder 的函數；凡解讀候選數字的 run 必須同一顆 embedder（已固定）。

### 3.4 序號規則（benchmark 內建，非我們製造）
FC 的 query 模板明寫「newer fact has larger serial number … solve conflicts by finding the newest fact with larger serial number」。**序號是「時序」的文字編碼**，與事實的到達順序冗餘。mem0 的 extraction 會**剝除序號**，改以 **ingestion 順序**承載 recency——這在真實場景是合理的（真實對話也沒有序號），**不構成對 mem0 不公平**。

---

## 4. 證據：write-time 衝突處理的結構性失敗

### 4.1 量化總覽（含 confound 警示）

**FC-SH end-to-end EM（mem0）**：
| | 6k | 32k | 64k |
|---|---|---|---|
| nominal EM | 92% | 90% | 94%⚠️ |
- ⚠️ **64k 不可與 6k/32k 直接比**（minimal thinking + max_len 256 vs High + 10）。修正 artifact 後：32k 真實 EM 天花板 ≈ **93%**（補回 3 個被截斷的正確答案）；64k 真實規則正確率 ≈ **96%**（補回 2 個 benchmark 答案鍵瑕疵題，mem0 其實答對）。

**write-time 衝突解決稽核（query-independent，全 in-store 衝突對）**：
| | 6k（161 對）| 32k（837 對）| 64k（1691 對）⚠️ |
|---|---|---|---|
| resolved | 98.6% | 93.1% | 95.6%⚠️ |
| 候選 crowd-out（H1-miss）| 1 | **29** | **53** |
| 解決拒覆蓋（H2-refuse）| 1 | 28 | 21⚠️ |
| same-chunk（結構盲點）| 16 | 13 | 13 |

> ⚠️ **誠實判定（最重要）**：`resolved%` 在 64k（95.6%）**高於** 32k（93.1%）**不是**「池更大反而更好」，而是 **minimal-thinking 把 H2-refuse 壓低（28→21）所致的 artifact** → resolved% 與 H2-refuse **跨設定不可並列**。
> **目前唯一「跨設定穩健、且純機制」的 scale 證據 = 候選 crowd-out（H1-miss）絕對數 1 → 29 → 53 單調上升**（純 embedding，不受 thinking 影響）。「隨 scale 結構性惡化」目前**只能靠這條**。
> **待辦**：6k/32k 用 minimal thinking 重跑，才能把 resolved% 一條也納入單調性論述。

### 4.2 失敗分解：三個可定位的結構問題（對應後續方法的三個修復）
排除 same-chunk 結構盲點與 extraction 漏抽後，write-time 失敗收斂為三類（內部代號附於括號，供跨 doc 對照）：

1. **取回層 — 候選 crowd-out（H1-miss）**：對 new fact 取 cosine top-5 時，隨記憶庫變大，**真正該被更新的舊版被「同關係不同主詞」的相似事實擠出 top-5** → update LLM 根本沒看到舊版 → 只 ADD → 衝突未解（新舊並存）。
2. **偵測層 — 偵測誤判 over-fire（A4）**：即便 new fact 取到了 top-5，update LLM **把一個「只是共用實體、但不同關係」的無關候選誤判成衝突而 UPDATE 覆蓋** → 正確的無關事實被**不可逆摧毀**。〔實證：32k 全域 16 例 A4，**13/16 被毀的正確版其實就在污染者 top-5（rank 1–3）→ 失敗在偵測判斷，不是取回 miss**。〕
3. **解決層 — 拒絕覆蓋（H2-refuse）**：偵測到了衝突、舊版也在候選池（甚至 rank1 高分），但 update LLM **不願用反事實覆蓋世界事實**（參數知識作梗）→ 保留世界版、丟反事實。

> **根因收斂**：(1)(2) 共享一個取回層根因——**embedding 候選是按「關係模板相似 + 實體重疊」排序，而非「(主詞,關係) 槽位身分」**，所以既會把真舊版擠出（→1），又會把同實體異關係的事實擠入並被誤覆蓋（→2）。(3) 是 update LLM 的裁決品質問題。**三者一旦寫入皆不可逆。**

> ⚠️ **「(主詞,關係) 槽位」只用於診斷解釋，不可寫進方法**（那等於假設每筆 fact 都是乾淨三元組 → 對 benchmark 過擬合，無法泛化）。方法設計改用通用 primitive（見 §5.3）。

### 4.3 破壞不限於「衝突」——強化點（64k 觀察）
64k 的 4 個真 mem0 失敗中，**3 個是「無衝突的單一事實」**被同實體 distractor 毀掉（如 Areopagitica 被摺進 famous-for 槽後被無關作品覆蓋；另有 update LLM 在大候選池下**直接漏輸出 new fact** 的 omission 新子模式 qid76）。→ mem0 的真正負債是「**write-time update 對記憶庫的破壞性維護**」，**比「衝突解決」更廣**：任何 fact 只要候選池混入同實體干擾就可能被毀。

### 4.4 失敗的「不可逆」性質（流派層級的代價）
write-time 一旦解錯（丟反事實 / over-fire 覆蓋 / 漏輸出），**正確版從記憶庫消失，任何 query-time 機制都無法回復**。這正是「破壞性、提前固化」設計選擇的代價，也是 read-time 方法（從不裁決、從不破壞）結構上不會犯的錯。

### 4.5 誠實 caveat（論述時必附）
- **EM 真失敗量很小**：mem0 真正可歸因衝突解決的 query 失敗 = **3/100（32k）、4/100（64k）** → n 太小，**EM 不可當主證據**（見 §6 改用 context 品質為主指標）。
- **空輸出是 artifact 非失敗**：32k 的 3 個空輸出（qid7/33/51）經 controlled re-trial 確認是 `generation_max_length=10` 截斷（同設定確定性空、放大 budget→**三題全答對**），非衝突解決失敗。
- **benchmark 自身有少量答案鍵瑕疵**：32k 的 qid8/9、64k 的 qid18/20——同 (主詞,關係) 在 context 有更大序號的編輯版，答案鍵卻標較小序號的真實事實，**違反 benchmark 自宣告的 largest-serial 規則**；**mem0 保留大序號反而是 rule-compliant**。全 100 題各僅 2 題。此發現同時是「我們改用 rule-faithful 擴充評估集」的依據（§6.2）。

### 4.6 ★ 研究問題（從失敗抽象化 + Xu et al. 2024 grounding；evidence→method 的橋）

**情境定性**：FC = Xu et al. 2024《Knowledge Conflicts for LLMs: A Survey》的 **context-memory conflict**——要採信的 context（反事實最新版）與 LLM 自身參數記憶相反。

**過去 write-time 流派在此情境的兩個結構失敗點**：
- **R1 取回**：候選池**沒撈到衝突對應的另一版** → 根本沒得比（→ 最終 store `both`：兩版都 ADD）。
- **R2 用單一 LLM call 同時做「偵測＋決策」**於該候選池，兩條子因要**分開講**：
  - **H2-refuse = 決策被參數知識毒化**：偵測對了，但 LLM **不願 commit 反事實覆蓋** → **直接是 context-memory conflict**（→ 最終 store `old_only`）。
  - **A4 over-fire = 偵測精度問題**：LLM 在吵雜候選上**誤判同實體異關係為衝突而覆蓋** → 主因是「LLM 對吵雜候選做衝突偵測」不可靠，context-memory 設定**加劇但非唯一成因**（**勿說成純 context-memory conflict**）（→ 最終 store `old_only`/`neither`）。
  - **共同根**：偵測與決策**綁在一次 LLM call**，故一個 call 同時承擔「偵測精度(A4)」與「被參數知識毒化的決策(H2)」；又因 write-time **不可逆**而永久損毀。

**→ method 直接對應（research question 推導出設計）**：
- R1 → **query 錨定取回**（把另一版撈回）。
- R2 → **偵測與決策拆開**：偵測縮小範圍（群內判，對付 A4 精度）；**決策改機械時序，把參數知識徹底移出決策 → H2 消失**。

> **一段話 motivation**：在 context-memory conflict（Xu et al. 2024）下——待存事實為反事實、與 LLM 參數記憶相反——過去 write-time 衝突解決流派失敗於兩處：(R1) 衝突的另一版未被取回候選池；(R2) 以**單一 LLM call 同時做偵測與決策**於該候選池，使**決策被參數知識毒化（拒寫反事實，H2-refuse）**、且**偵測在吵雜候選上失準（誤覆蓋無關事實，A4）**，並因 write-time 不可逆而永久損毀記憶庫。我們將解衝突移到 query-time、可逆地進行，並**把偵測與決策拆開、決策改為機械時序**，以提供對 query 所需槽位無衝突且完整的 context。

---

## 5. 提案：把衝突裁決移到 query-time、可逆地進行

### 5.1 High-level
> mem0 流派做不好的最高層原因 = **在 write-time 不可逆地裁決衝突**。我們改成：**ingestion 只非破壞地存（保留全部 + 時序），把偵測與解決延後到 query-time、依當次 query 的資訊進行、且不破壞記憶庫**。

> 注意：headline 是「不可逆」，但 query-time 這一步實際**一次修了三個不同子因**（避免 reviewer 發現 headline 只 cover 一個）：

### 5.2 三個對應修復（對齊 §4.2 的三類失敗）
| 失敗（§4.2）| 修復 | 為什麼 query-time 結構上更好 |
|---|---|---|
| 1 取回 crowd-out | **query 錨定取回**：用 query 的 entity/意圖把相關記憶盡量取全（over-retrieve + entity 錨定）| 衝突各版本共用同主詞 entity；query 直接給錨點，不靠盲目 cosine 排序 |
| 2 偵測 over-fire | **偵測/解決拆開 + query 錨定分群**：先把「針對 query 所問那件事」的多個版本**精準分群** | query 明說要哪個槽 → 偵測有錨點，不像 write-time 盲猜誰跟誰衝突；且**可逆**（只整理回傳集、不動庫）→ over-fire 不會摧毀資料 |
| 3 解決拒覆蓋 | **解決改機械時序**：群內用 ingestion 順序/時間戳「較新覆蓋較舊」，**不問 LLM 哪個為真** | 把不穩定的「違反自身知識」judgment 從決策中移除 → H2-refuse 消失 |

### 5.3 最小可貢獻單元 + 泛化守則
- **最小貢獻**：對每個 query，回傳「**對 query 所需槽位無衝突、且含最新版**」的乾淨 context（其他無關記憶的衝突先不管）→ 期待消除「同槽舊版洩漏」這條失敗路徑、帶動 EM。
- **泛化守則（避免過擬合 FC 的乾淨三元組）**：所有元件只用**通用 primitive**——NER/entity-linking（free text 可用）、時序/順序、recency 機械規則、query 錨定的 LLM 偵測——**不假設 (主詞,關係,物件) 可乾淨 parse**。
- **記憶單位顆粒度本身是設計旋鈕**：愈原子、自足 → 解衝突愈能退化成「機械時序分群」（避開 H2）；愈粗（一單元混多件事）→ 愈被迫回到 LLM 裁決、H2 風險回來。這是為何 extraction（抽成什麼記憶單位）要納入方法設計，而非單純前處理。

### 5.4 與 Zep 的差異（機制已確認；數字待對齊重驗，2026-06-06）
> 依據：本 repo 既有 Zep 機制分析 [analysis/zep_methodology.md](../../analysis/zep_methodology.md)（描述 benchmark 版 Zep 的程式行為）。
> ⚠️ **既有 Zep 量化數字不可信、需重做**：舊分析是 **gpt-4o-mini + cloud Zep + 只有 6k**，與我們現在（gemini-3.1-flash-lite / temp 0 / 6k-32k-64k）**未對齊**；下方只取「機制」（程式架構事實），**所有 error-rate / recall 數字一律待對齊重跑後才採用**。

**Zep（benchmark 版）的衝突機制（架構事實）**：
- **write-time（ingestion）做衝突決策**：內部 LLM 抽 edge + 標 `valid_at`/`invalid_at`；同 (X,R) 新事實進來時把舊 edge 的 `invalid_at` 填上（supersession）。→ **確認 Zep 屬 write-time 衝突決策流派**。
- **label-based（非破壞）**：舊 edge 保留、只標 invalid；retrieval **不過濾** invalid，把 date-range 一起丟給 inference LLM 自己判讀。
- **write-time 固化**：`invalid_at` 是寫入圖的狀態，標錯就錯在圖裡。
- **訊號傳達弱**：supersession 訊號只在 edges scope；FC prompt 只教序號規則、沒教讀 date-range → 兩套訊號可能打架。（標錯方向率 / edges recall 的**具體數字待重跑**。）

**我們的 delta（grounded 在機制，不靠舊數字）**：
1. **偵測時機/可逆性**：Zep = write-time、不可逆 label；Ours = **query-time、可逆、query 錨定**。
2. **決策**：Zep 把「用哪版」**丟給 inference LLM 讀 date-range（無指令、且與序號訊號衝突）**；Ours = **明確機械時序決策**（移除 LLM judgment）。
3. **訊號傳達**：Zep supersession 訊號只在單一 scope、易流失；Ours **控制分群、回傳乾淨集**。

> **RPT 不是競爭方法，是 oracle 上界**（使用者 2026-06-06 釐清）：RPT 是當初 oracle 實驗的一種**純 prompt engineering**——用 **oracle 給的衝突標記**做 inline `[CURRENT]/[OUTDATED]` + 「MUST NOT use OUTDATED」強指令，證明「**若有完美衝突標記，LLM 就能用新棄舊**」。它**沒有自動偵測/解衝突機制**，不可部署。→ **對我們有利**：RPT 確立了 oracle 上界；**我們的貢獻正是自動達成 RPT 用 oracle 才有的乾淨訊號**（query-time 自動偵測 + 機械時序解）。可把 RPT 當 oracle-ceiling ablation 引用。

### 5.5 ★ 架構實作定案（2026-06-06 討論結論）

**核心洞察：mem0 / RAG-no-res / Ours 是同一套 pipeline，只差「衝突機制那一格放在哪」**——storage 層三者幾乎共用（RAG-no-res 與 Ours 完全共用「全留 + metadata」），形成乾淨的**巢狀 ablation**：

```
              INGESTION                              QUERY
mem0      extract → [衝突機制: write-time]→store      retrieve top-100 → inference
                    (UPDATE/DELETE, 破壞, 剝序號)       (記憶無序號)

RAG-no-res extract → store-all (+原始序號 metadata)    retrieve top-100(原順序)→每筆貼回原始序號 → inference
                    (無衝突機制)                        (LLM 用 benchmark 序號規則自己解)

Ours      extract → store-all (+時序 metadata)         retrieve top-K → [衝突機制: query-time] → inference
                    (無衝突機制)                        (分群 + 機械時序 → 乾淨 context)
```

- **Ours = RAG-no-res + 一格 query-time 衝突機制** → 貢獻可被單獨量出，不被 storage/extraction/retrieval/inference 差異污染。
- pairwise 意義：`mem0 vs RAG-no-res`＝write-time 那格幫忙或幫倒忙；`RAG-no-res vs Ours`＝加一格 query-time 機制有沒有用；`Ours vs mem0`＝同一格從 write-time 搬到 query-time 值不值得。

**修改「衝突機制 component 時機」= 兩個動作：**
1. **拔掉 ingestion 的 Component 3（update decision）** → 退化成 store-all。
   - **實作 = 直接 bypass Component 2+3**（跳過 candidate search + update LLM call），對每筆抽取 fact 直接 `_create_memory`。**不要只把 `DEFAULT_UPDATE_MEMORY_PROMPT` 改成只 ADD**——那仍會跑一次 LLM（多餘、且引入非確定性）。bypass 才是真正「無衝突機制」、deterministic、且最便宜。env flag 控制（baseline-safe）。
2. **在 retrieval 與 inference 之間插入一格 query-time 衝突機制**（分群 → 機械時序解 → 乾淨 context）。**inference prompt 與 retrieval 主體不動** → 改動面鎖在「那一格的時機」。

**metadata 在 ingestion 當下寫入（deterministic，不靠事後 recover）：**
- **RAG-no-res（baseline）**：存每筆 fact 的**原始序號**（ingest 的就是 numbered context，序號當場已知）。retrieval 後**維持 mem0 原本 cosine 順序、不重排**，只貼回原始序號，直接餵 benchmark inference。→ 與 mem0 唯一差別＝「有沒有序號（recency 可不可用）」。**揭露**：貼序號是為了讓 benchmark 自帶的序號規則 inference 能運作的 baseline construction，非宣稱記憶系統有此通用能力（真實場景對應時間戳）。
- **Ours（method）**：存**時序 tag**。
  - **最小原型先用「每筆 fact 的 ingestion 順序」**（在本 benchmark＝序號；同 chunk 內亦有 list 順序）→ **連 same-chunk 也能機械排序**，可先不解 same-chunk 就把 query-time 機制驗證起來。
  - **更真實/更難的版本＝粗顆粒 tag（chunk-level 時間戳，同 chunk 視為同一時刻）**：此時 **same-chunk 的同時衝突無法用時序排序** → 逼出「**在 extraction 階段就先偵測同 chunk 內 new facts 能否分群**」的需求（＝把 same-chunk 衝突在抽取端先解掉）。這是 extraction 作為方法設計軸的具體體現，列為後續 design fork，不擋最小原型。

**extraction 的兩個角色要分開（呼應 §5.3）：**
- **抽「內容」（L2 prompt）＝公平比較 enabler**，三方共用同一份 frozen 抽取，只 disclose、不算 contribution。
- **抽取時「標時序 + 切顆粒度」＝方法設計軸**，要 ablate（原子 vs 粗、有時序 vs 無）。

---

## 6. 評估計畫

### 6.1 主指標：記憶 context 品質（memory-attributable、避開下游 confound）
對每個 query 的所需槽位，量三件事：
- **Completeness**：該槽的**最新版（=context 內最大序號版）**是否在回傳 context 裡。〔mem0 會因 over-fire/破壞而缺；RAG/Ours 恆有〕
- **Cleanliness**：該槽的**舊版**是否已被濾掉。〔RAG-no-resolution 會髒；Ours 乾淨〕
- **EM（輔）**：下游答對否（佐證乾淨 context → 下游也好）。

### 6.2 擴充評估集（解決「EM 真失敗只有 3–4 題」的統計力問題）
- 不只用 benchmark 的 100 題；用 `*_FULLPAIRS_gt`（6k=161 / 32k=837 / 64k=1691 對）**每個 in-store 衝突對各發一個 query**，N 放大一個數量級。
- **便宜**：ingestion 已完成，只是對既有 store 多發 query，無需重抽。
- **★ 命門 rigor**：每個衝突對的 **gold = 「context 內最大序號版」**（`winner_seq = max(old_seq, gt_seq)` 的物件），**不是** MQuAKE 的 per-case answer、也不是 FULLPAIRS 的 `gt_fact_text`。理由：同 (主詞,關係) 會被多個 MQuAKE case 編成不同答案（§4.5 的 qid8/9）→ 用 MQuAKE 答案會把該缺陷以 837× 規模重新引入；改用 largest-serial 則**與 benchmark 規則自洽、且自動修掉那些瑕疵**。
- **報法**：主集＝擴充集（rule-faithful gold）；副集＝原始 100 題（標出瑕疵題）以求可比性與透明。揭露「我們以 benchmark 自宣告規則自建 rule-faithful 評估集，N 100→837/1691」。
- **待辦**：先量 coverage（多少對能對到 MQuAKE 現成問句 / 需 cloze→問句模板 / 對不上而排除）。

#### 6.2.1 ★ 戰場 scoping：cross-chunk + 用「最終 store 狀態」定義失敗（2026-06-06 定案）

**(a) 戰場用「最終 store 狀態」分群，不用 event-bucket**：
- ⚠️ awt 的 H1/H2/A4 是**逐 update 事件**分類；A4 串聯會讓一個事件上標 `resolved` 的對**最終崩壞** → 用 event-bucket 框戰場會漏。**正確 = mem0 跑完後每個衝突對的最終 store 狀態**（mechanism-agnostic、直接對應 QA）：

| 最終 store | 機制來源（event trace 解釋 why）| mem0 QA | 我們指標 |
|---|---|---|---|
| **old_only** | H2-refuse 留舊 / A4 摧毀 winner | 答舊 → EM 0 | **completeness 失敗（不可逆）** |
| **neither** | A4 串聯把新舊都毀 | 無資訊 → 答不出 | **completeness 失敗（不可逆）** |
| **both** | H1-miss 兩版都 ADD / H2 沒覆蓋 | 髒 context → 脆弱(prompt nudge) | **cleanliness 失敗（可逆）** |
| new_only | mem0 自清乾淨 | 答對 | 乾淨（對照）|

- **分工**：最終 store 狀態定義「戰場/QA 失敗」(WHAT)；event-bucket 只拿來解釋「某對為何落該狀態」(WHY)。
- **這就是 completeness/cleanliness**：old_only+neither = 不可逆 completeness 流失（mem0 專屬，Ours 不破壞故結構上避免）；both = 可逆 cleanliness（Ours query-time 清掉）。

**(b) head-to-head 只在 cross-chunk**：每個衝突對標 `same-chunk / cross-chunk`，**主比較（mem0 / RAG-no-res / Ours）只在 cross-chunk 上做**；**same-chunk 當獨立 stratum 另報，不進主比較**。
- **為何排除 same-chunk**：same-chunk 失敗是 **write-time 增量架構 + chunk 批次**的 artifact（同 chunk 舊版當下還沒進 store→不在候選→無法 UPDATE），**與「verdict 品質」(R1 取回 + R2 裁決) 是不同機制**。且 query-time 一進來此 artifact 消失（全留→兩版都在 store），我們方法對 same-chunk 的殘留限制只剩「同時間戳 tie-break」＝extraction 顆粒度軸。放進主比較會 (a) 混兩種機制、(b) 對 Ours 不公平（最小原型若用粗時間戳本就解不了 same-chunk）。
- **與既有稽核一致**：A-WT 本就把 same-chunk 從 detectable 分母剔除（structural blind spot），此 scoping 是同原則延伸。
- **代價小**：same-chunk 占比隨 scale 崩（6k 10% → 32k 1.6% → 64k 0.8%）。
- **誠實**：same-chunk 仍是 mem0 真實缺陷，照常獨立報告，只是不在「write-time vs query-time verdict」這個主張的戰場內；我們方法解 same-chunk 需「細時序 tag」或「extraction 端先分群」＝ design fork。

### 6.3 Baselines
| baseline | 角色 |
|---|---|
| **LCA（full-context）** | read-time、不壓縮的上界參照；測其在長 context 是否也退化 |
| **RAG-no-resolution（存全部、不解，定義見 §5.5）** | ★ 關鍵控制：store-all（bypass Component 2/3）+ 維持 mem0 cosine 順序 + 每筆貼回原始序號 + benchmark inference prompt 不動 → 與 mem0 唯一差別＝「有沒有序號」。隔離「write-time 解衝突幫不幫」。期望 mem0 ≤ RAG-no-res < Ours。**＝ Ours 拿掉 query-time 衝突機制的版本** |
| **mem0（未改 extraction，benchmark 版）** | 對 FC 會大量回空 → 近地板，用來說明為何需 L2 |
| **mem0（改 extraction，= 我們 L2 版）** | 公平的 mem0 主 baseline |
| **Zep（benchmark 程式）** | 流派的標籤式代表 |
| **mem0（最新版）** | 次要 |

> 三方核心比較：**mem0 / RAG-no-resolution / Ours** ×（context 品質為主、EM 為輔）×（6k→262k）。

### 6.4 為什麼這樣比能贏（且誠實）
- 不主張「記憶系統準確率贏過 LCA」（context 塞得下時通常贏不了）；主張的是「**write-time 解衝突流派付出不可逆、隨 scale 累積的腐蝕代價，query-time 可逆解衝突可移除之**」，以 **completeness/cleanliness 曲線 × scale** 證明，EM 佐證。

---

## 7. 範圍外 / 待後續

- **#4 下游 cross-fact inference 混淆**（檢索到正解，但 LLM 拿同實體的另一條 fact 作答，如 qid23/64）：這是 **inference 端**問題，**read-time 方法也會中** → **非此流派專屬**，移出主張，列為 out-of-scope；若我們的乾淨回傳同時降低它，當 bonus，不當主證據。
- **FC-MH（多跳）**：有多跳 retrieval confound（MH 6k→32k EM −25pp），衝突解決主軸先**專注 SH**，MH 待主張站穩後再測。
- **LongMemEval-KU**：用來**證泛化**（非反事實的衝突類型）——回應「只對 FC 有效」的質疑。FC 與 KU 都站穩才完整。

---

## 8. 開放問題與風險（給自己也給審閱者）
1. **scale 單調性目前只有 H1-miss 一條穩**；resolved% 需 6k/32k minimal 重跑才能並列。**這是最大的論述風險**。
2. **EM headroom 小**（3–4/100）→ 必須靠 context-品質擴充集撐統計力；若 RAG-no-resolution 已逼近天花板，代表「write vs query time」空間不大，要趁早 pivot（先跑 RAG-no-res 驗證）。
3. **★ 新穎性未判定 + 與前作 RPT 的關係未釐清（最高優先）**：
   - **Q4 Zep delta — ✅ 機制已解**（§5.4）：Zep = write-time、label-based、不可逆。⚠️ **但舊 Zep 量化分析不可信（gpt-4o-mini+cloud+6k，未對齊）→ 須在對齊設定下重做** 才能引用任何 Zep 數字。
   - **RPT — ✅ 已釐清不威脅新穎性**（使用者：RPT 是 oracle 實驗的純 prompt-engineering，用 oracle 標記，不可部署）→ RPT = **oracle 上界**；我們貢獻 = 自動達成它。可當 ceiling ablation。
   - **Q5 外部新穎性**：有沒有前人做過「query-time、可逆、非破壞 store 上解衝突」或「偵測/決策分離（機械時序 vs LLM judgment）」？deep-research 未涵蓋 → 需一輪聚焦 Q5 的 targeted 搜尋。
   - 其餘系統（mem0 ✅ write-time 破壞；A-Mem/GraphRAG/HippoRAG/EMG-RAG/LightMem 的 timing）可後續補。
   - venue/year 僅有 lead（§2.2），正式引用前逐一確認。
4. **方法的偵測分群必須「非常精準」**：分群誤併不同槽會誤刪，雖可逆但影響回傳品質——這是方法成敗點，需設計實驗單獨驗證分群準確率。
5. **泛化證據**目前只有 FC（乾淨三元組結構）；需 KU 才能反駁過擬合。

---

## 9. 接下來 TODO（依賴序）
1. **跑 RAG-no-resolution baseline** + 建 §6.1 context-品質指標 → 對 mem0 vs RAG-no-res 在 6k/32k/64k 算 completeness/cleanliness，看 gap 是否隨 scale 拉大（最便宜的「gap 真不真」驗證）。
2. **建 §6.2 擴充評估集**（FULLPAIRS → (question, gold=largest-serial)）+ coverage 統計。
3. **6k/32k 用 minimal thinking 重跑** → 補齊 resolved% 的跨設定單調性。
4. **跑 LCA** 6k/32k/64k/262k（同 temp=0/同模型/同 prompt；含「有序號」與「順序/時間戳」兩設定）。
5. **方法最小原型**（細節定案見 §5.5）：ingestion **bypass Component 2/3** 改 store-all + ingestion 當下標 metadata（RAG-no-res 標原始序號、Ours 標時序）；query-time 加「精準分群 → 機械時序解」一格。最小原型先用 per-fact ingestion 順序當時序（連 same-chunk 都可排），same-chunk 粗顆粒版列 design fork。
6. 主張站穩後：FC-MH、LongMemEval-KU。
