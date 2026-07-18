\chapter{Introduction}
\label{ch:introduction}
\section{Background}

近年基於大型語言模型（Large Language Models, LLMs）的智慧代理已被廣泛應用於需要跨越多個對話與使用者長期互動的場景。然而 LLM 本身為無狀態（stateless），僅能在有限的 context window 內運作。為在跨對話的長期互動中維持連貫性，需引入外部記憶（external memory）持續保存並檢索對話中累積的資訊。

隨著記憶持續累積對話中提供的資訊，同一事實會於不同時點寫入不同版本，記憶中因此保留同一事實的多個版本。當後續查詢觸發檢索時，新舊版本會被一併取回並作為 context 提供給 LLM，回答可能因此取自過時版本而非當前版本。
辨識同一事實在記憶中的多個版本，並採用其最新版本，此問題被稱為知識更新（Knowledge Update, KU）。近期多個長期記憶 benchmark 將 KU 明確列為記憶系統的核心能力之一\cite{wulongmemeval}\hspace{-0.05em}\cite{hu2026evaluating}\hspace{-0.05em}\cite{tavakoli2026beyond}。

另一方面，KU 情境根據新事實的特性可再分為兩類。一類是 counterfactual 型 KU，新事實明顯與世界事實不符，但要求記憶系統以新事實為準，例如 MemoryAgentBench 的 FactConsolidation 任務即以 MQUAKE 中的 counterfactual 事實所建構\cite{hu2026evaluating}\hspace{-0.05em}\cite{zhong2023mquake}。另一類是 personal 型 KU，新事實為使用者個人資訊隨時間的變動，例如 LongMemEval 的 knowledge-update 任務以自然對話中使用者事實所建構\cite{wulongmemeval}。兩類情境於後續章節分別稱為 counterfactual 型與 personal 型 KU 情境，用以區分本文的實驗設計與觀察。

\section{Motivation}

一個通用的記憶系統依資訊被處理的時機，可分為寫入階段（write-time）與查詢階段（query-time）。write-time 負責將新資訊建構到記憶中，並決定新資訊與既有記憶的關係；query-time 則依當前查詢從記憶中檢索相關內容作為 context 提供 LLM 推論使用。

現有方法可依 KU 判斷於記憶系統中的時機，分為三種處理策略。早期方法主要將 KU 判斷設計在 write-time，由 LLM 於單次呼叫中同時判斷記憶要如何被操作（如 ADD / UPDATE / DELETE）並執行寫入\cite{chhikara2025mem0}\hspace{-0.05em}\cite{fang2026lightmem}。此類方法的判斷與執行設計於同一次LLM呼叫，一旦誤判就直接將錯誤寫入記憶。為降低此風險，後續研究於 write-time 將 LLM 判斷與執行解耦，讓 LLM 僅負責輸出新舊事實間的關係類別（如 contradict、duplicate），實際的操作則交由 deterministic 系統執行\cite{rasmussen2025zep}。此類方法雖降低了 LLM 對執行的直接參與，KU 判斷時機仍然於 write-time 完成，錯誤仍會不可逆寫入記憶。近期研究則進一步將 KU 判斷延後至 query-time，記憶始終保留所有版本，只有在 query-time 對檢索出的候選事實進行判斷\cite{reddy2026don}。整體而言，三種策略演變的目標都是為了讓 KU 所需的正確版本存在於記憶中，且判斷過程中減少對 LLM 的依賴程度。

然而，這三種策略仍有一個共同的前提：無論 KU 判斷設計在 write-time 或 query-time，辨識哪些候選記憶對應到同一事實，以及決定哪個為當前版本，皆由 LLM 的語意判斷負責。此設計於兩個層面上存在問題：LLM 在知識衝突下的判斷偏好、KU 表現依賴於 backbone 的能力。

LLM 於知識衝突（knowledge conflict）情境下的判斷偏好，直接影響 KU 判斷的可靠性。近期研究指出，當 context 中提供的新資訊與 LLM 內部的既有知識不一致時，即便 prompt 已明確要求以提供的資訊為準，LLM 仍傾向以自身知識回答\cite{longpre2021entity}\hspace{-0.05em}\cite{xu2024knowledge}。以 MemoryAgentBench 的 FactConsolidation 任務為例，將每則事實依標上序號，並告知 agent 序號較大者為較新的新事實；同時告知 agent「僅根據記憶中的知識，而非真實世界的事實」做回答\cite{hu2026evaluating}。即便在此規範下，在 gpt-4o-mini 上，主要以 write-time 判斷 KU 的現有方法在回答 single-hop (FC-SH) 的準確率中，Mem0 僅達 18\%、Zep 僅達 7\%\cite{hu2026evaluating}。

既然現有方法的 KU 判斷由 LLM 執行，其表現也隨著 backbone 的能力不同而變動。這直接影響實際部署情境：隱私敏感的情境下，將推論置於裝置端可避免私有資料外洩，而裝置端的資源限制使可用模型侷限於小型語言模型\cite{pham2025slimlm}；成本受限的情境下，部署則傾向在能力與價格之間權衡，而採用成本較低的模型\cite{chenfrugalgpt}。因此，只要 KU 判斷仍由 LLM 執行，方法的表現便會直接與 LLM 的判斷能力相關。

\section{Research Objective}

基於上述觀察，只要 KU 判斷仍由 LLM 執行，KU 的表現便直接受 LLM 的判斷能力與判斷偏好所影響。本文核心問題是：將 KU 判斷從 LLM 執行改為以 deterministic 機制執行，是否能使 KU 的表現不再依賴 LLM 的判斷能力，且不再受 LLM 判斷偏好的影響？

要以 deterministic 機制取代 LLM 判斷，須先確認 KU 是否能不靠語意判斷就能解決。KU 判斷隱含兩個子問題：辨識哪些候選記憶對應同一事實（fact identity），以及決定其中哪一個為當前版本（version decision）。就辨識同一事實而言，KU 發生於 fact-level 的記憶粒度，而事實可表示為 $(\text{subject}, \text{predicate}, \text{object})$ 的三元組（triple）形式~\cite{zhong2023comprehensive}，其中 $(\text{subject}, \text{predicate})$ 指此事實的實體與屬性，object 為該屬性的值。在同一屬性於同一時點僅取單一值的前提下，同一 $(\text{subject}, \text{predicate})$ 即對應同一事實，辨識同一事實能夠透過 $(\text{subject}, \text{predicate})$ 的結構配對負責。就決定當前版本而言，KU 情境下同一事實於同一時間點僅有一個當前版本，寫入時序較新者即為當前版本，版本決定能夠透過寫入時序上的比較負責。兩個子問題皆能由事實的結構與寫入時序負責，不需 LLM 的語意判斷，此為 deterministic 機制執行 KU 判斷的可行性基礎。

因此，本文提出以 deterministic 結構配對為主要 KU 判斷方式：write-time 只保留所有版本，並對事實抽取結構化資訊，不進行任何 KU 判斷；query-time 才進行 KU 判斷，並以 $(\text{subject}, \text{predicate})$ 配對辨識同一事實，透過事實寫入時序決定當前版本。LLM 於此設計中僅於結構配對失效的情況作為補救介入，不參與主要判斷，也不修改記憶。本文的研究目標包含以下三點：

\begin{itemize}
\item 本文提出以 deterministic 結構配對為主要 KU 判斷方式的記憶系統機制。此機制將 KU 判斷從 LLM 執行改為由確定性操作執行，使 KU 判斷不再依賴 LLM 的語意判斷。
\item 本文於 counterfactual 型 KU 情境上與現有方法比較，觀察到本方法於各設定上相對既有方法呈現較高的 KU 準確率[從experiment寫完後回來補更精確的用詞與論述寫法]，並透過對 baseline 錯誤模式的逐題分析，驗證此差距確實來自 LLM 傾向以既有知識作答，因此抗拒更新 counterfactual 的新事實[從experiment寫完後回來補更精確的用詞與論述寫法]。為進一步確立此歸因，本文另以 personal 型 KU 情境作為對照條件[從experiment寫完後回來補更精確的用詞與論述寫法]。此情境中的新事實與 LLM 既有知識無衝突，LLM 於判斷時不受既有知識偏好的抗力，因此若上述歸因成立，本方法與既有方法的差距應於此情境下明顯縮小。
\item 本文透過以不同能力的 backbone 進行對照實驗，驗證現有方法的 KU 表現隨 backbone 能力減弱而大幅下滑，而本方法的退化幅度明顯較小，兩者的差距因此隨 backbone 能力減弱而擴大。[從experiment寫完後回來補更精確的用詞與論述寫法]
\end{itemize}