\chapter{Related Work}

\section{Knowledge Update in Long-Term Memory Systems}

\subsection{Coupled LLM Judgment at Write Time}
最早期的方法將 KU 判斷置於 write-time，對每筆新進事實檢索語意相近的既有記憶，由 LLM 於單次呼叫中直接判斷新舊事實間的取代關係，並輸出對記憶狀態的操作類別。Mem0 \cite{chhikara2025mem0} 其更新機制於單次呼叫中直接輸出 ADD、UPDATE、DELETE、NOOP 四類操作之一，判斷與執行的責任被綁定於同一次 LLM 呼叫，一旦 LLM 將相關但未矛盾的事實之間誤標為衝突，對應的 UPDATE 或 DELETE 便立即以破壞性方式覆蓋既有記憶，且該誤判於後續查詢中無法還原。LightMem \cite{fang2026lightmem} 雖將更新排程延後至離線批次執行，更新判斷的方式與 Mem0 相同，LLM 仍直接輸出操作類別，對記憶的操作也屬於破壞性寫入，批次時機的延後並未改變 LLM 判斷對記憶狀態的直接修改性質。
此類方法的共同設計在於，都設計在 write-time 處理，一旦誤判就會寫入錯誤累積於記憶中，且均由 LLM 語意判斷作為 KU 的決策，判斷結果直接決定系統表現，誤判造成的資訊損失無法還原。

\subsection{Decoupled Judgment and Execution at Write Time}
為降低 LLM 對記憶狀態直接修改的風險，後續研究於 write-time 將 LLM 判斷與執行解耦。Zep \cite{rasmussen2025zep} 將 LLM 的職責限縮為 duplicate 與 contradict 兩種新舊事實之間關係的輸出，對 contradict 標籤由系統在舊事實的時序 metadata 標記為失效， LLM 不再直接改寫記憶。近期研究 Engram \cite{wang2026less} 於此路線上進一步降低 LLM 的參與，透過對事實提取成(s,p,o)，以 deterministic 訊號作為主要判斷：同(s,p)、embedding 相似度，LLM 僅於 deterministic 訊號無法明確判斷的模糊情境才介入。此類方法藉由引入雙時序（Bi-temporal）或失效標記（Invalidation）等非破壞性寫入機制，使事實得以完整保留，避免了早期方法直接覆寫造成的永久性資訊損失。然而，即便降低了 LLM 對記憶執行的直接控制，此類方法的 KU 判斷時機仍然發生在 write-time。一旦系統於寫入時將新舊事實關係誤判為衝突，對應的失效時間戳仍會被錯誤且不可逆地存於記憶中，導致後續query-time 將此錯誤的時序 metadata 一併回傳，進而在最終推論干擾 context 理解與時序推理。

\subsection{Deferred Judgment at Query Time}
近期研究進一步將 KU 判斷延後至 query-time，write-time 保留所有版本，僅於查詢觸發時，對檢索候選進行辨識與版本選擇，由此消除了 write-time 不可逆寫入錯誤的問題。Reddy 與 Challaram \cite{reddy2026don} 於此路線中將 LLM 的職責明確限縮為候選事實和 query 之間的判斷，版本選擇則由 write-time 所保留的事實序號 deterministic 判斷時序最新。此類方法雖將版本判斷交由 deterministic 的方式負責，然而，候選事實之間的辨識仍完全依賴 LLM 於 query-time 的語意判斷。

\subsection{Limitations of Existing Knowledge Update Mechanisms}
上述三類方法雖於 LLM 判斷的依賴程度上逐漸減少，由 LLM 直接輸出操作類別，退為關係類別，再退至候選事實間語意判斷。然而，LLM 的語意判斷仍為 KU 決策的核心。此依賴於 knowledge conflict 情境下 LLM 判斷偏好與對 backbone 能力的敏感性兩個層面上構成限制，使 KU 表現受限於背後 LLM 的判斷可靠性。本文方法屬於 Deferred Judgment at Query Time 一類，並於此類方法的限制上提出，將辨識同一事實的責任，交給 write-time 的 (subject, predicate) 結構資訊提取，並於 query-time 由 deterministic 配對負責同一事實的辨識，LLM 僅於結構配對失效的少數案例作為補救。

\section{Knowledge Conflict in Language Models}

當 context 中提供的資訊與 LLM 內部既有知識不一致時，LLM 於回答時傾向以自身知識而非 context 為準，此現象被稱為 knowledge conflict。Longpre 等人 \cite{longpre2021entity} 於 entity-based 設定下，將 context 中的實體替換為與 LLM 既有知識不符的情況，觀察到 LLM 明顯偏好既有知識。Xu 等人 \cite{xu2024knowledge} 對此類偏好進行系統整理，將知識衝突分為 context-memory、inter-context、intra-memory 三類，並歸納對應的緩解方向。此類研究皆指出，即使 prompt 明確要求以 context 為準，LLM 仍傾向以自身知識覆蓋 context 提供的新資訊。

於 RAG 場景中，近期研究進一步針對衝突的辨識與解決提出對應方法。ASTUTE RAG \cite{wang-etal-2025-astute} 於檢索出的 passage 與 LLM 內部知識之間執行 source-aware 的一致性判斷，並以多輪迭代讓 LLM 對 candidate 進行合併與比對，最終選取跨來源最一致的答案為回應；TruthfulRAG \cite{liu2026truthfulrag} 則將 retrieved content 抽取為 knowledge graph 的 triple 表示，並以 entropy-based 篩選機制辨識引發 LLM 信心波動的 reasoning path，以此定位與 LLM 既有知識不一致的資訊。此類方法所處理的衝突為檢索得到的多份文件之間的可信度取捨，解決依據為跨來源一致性，並無時序的先驗概念。也有相關研究將時序資訊納入 RAG 檢索，以處理跨時間點的資訊混淆。T-GRAG \cite{li2025t} 於索引階段將文件依時間週期切分為多個子圖，查詢時依時間條件過濾出對應子圖執行檢索。然而此類方法所依賴的時序為事實於字面上實際發生的具體時間（valid time），時序的用途為檢索過濾，與 KU 情境所依賴的 ingestion time（事實被寫入記憶的時序）不同。

本文於長期記憶下的 KU 情境，結構上與上述 RAG 場景不同。RAG 場景所處理的衝突對象為檢索得到的多份文件，解決依據為跨來源可信度或 valid time 過濾；KU 情境所處理的衝突對象為記憶中先後寫入的多筆事實，解決依據為 ingestion time。若將 RAG 場景中的處理策略直接遷移至 KU 情境，一個直接可想到的做法為：於寫入時保留 ingestion time 序號，查詢時將所有候選連同序號提供給 LLM，由 LLM 依「序號較大者為新版本」的指示自行判斷。此做法將 KU 判斷交由 LLM 於 query-time 對 ingestion time 的語意判讀負責，結構上與 RAG 場景所依賴的 LLM 語意判斷相同，仍然受到 LLM 對既有知識的偏好影響。本文於後續實驗中將此做法納入為 baseline 之一，以觀察此類 LLM 判讀 ingestion time 的方式於 counterfactual 型 KU 情境下的實際表現，並與本文以 deterministic 結構配對負責 KU 判斷的方法對照。