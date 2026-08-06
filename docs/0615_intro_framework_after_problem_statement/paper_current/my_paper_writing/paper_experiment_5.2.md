\section{Main Results on FC-SH}
\label{sec:main_fcsh}

\subsection{Overall Performance}
\label{subsec:fcsh_overall}
表~\ref{tab:fcsh_main} 為各 method 於 gpt-4o-mini 在四個 context length 上的 sEM，分母為每 length 100 個 query。本方法平均達 92.5\%，在 32k、64k、262k 三個較長 length 上為各 method 最高，在最短的 6k 上與 Vanilla-RAG（93\%）相當。

\begin{table}[!htb]
\centering
\caption{FC-SH 於 gpt-4o-mini 的 sEM (\%)，分母每 length 100 個 query。}
\label{tab:fcsh_main}
\small
\begin{tabular}{lccccc}
\toprule
Method & 6k & 32k & 64k & 262k & AVG \\
\midrule
Mem0 Vanilla & 16 & 22 & 28 & 17 & 20.8 \\
Mem0 + Fact Extraction & 52 & 52 & 65 & 50 & 54.8 \\
Zep & 82 & 80 & 76 & 29 & 66.8 \\
LCA (full context) & 88 & 74 & 65 & 43 & 67.5 \\
Vanilla-RAG & 93 & 77 & 85 & 81 & 84.0 \\
Don't Ask & 80 & 86 & 88 & 86 & 85.0 \\
\midrule
\textbf{Ours} & \textbf{94} & \textbf{91} & \textbf{94} & \textbf{91} & \textbf{92.5} \\
\bottomrule
\end{tabular}
\end{table}

比平均分數更值得注意的是跨 length 的穩定性。本方法在四個 length 上維持於 $91\sim94\%$，最大波動 3 pp；多數 baseline 則隨 context 變長而明顯惡化，Zep 由 6k 的 82\% 降至 262k 的 29\%，LCA 由 88\% 降至 43\%，Vanilla-RAG 雖在 6k 達 93\%，於 32k 亦降至 77\%。

此對比指向本方法與 baseline 的一項結構差異：本方法在 query-time 以 $(s, p)$ 的 structural matching 辨識版本，判斷成本不隨候選數量與 context 長度上升；而以 LLM 在 query-time 逐一判斷版本的做法，需在更長且更多的候選中維持判斷品質，在長 context 下較難維持。

在此之中，Don't Ask 是唯一不隨 length 惡化的 baseline（$80\sim88\%$），與其餘 baseline 的走勢不同。這是因為 Don't Ask 同樣以確定性方式（取序號最大者）決定版本、不在長 context 下逐一比較，因此不受 context 變長影響；其分數的上限另有來源，於 Section~\ref{subsec:fcsh_errormode} 說明。

\FloatBarrier
\subsection{Error Mode: Where the New Version Is Dropped}
\label{subsec:fcsh_errormode}

本方法在 FC-SH 上的領先，對應 counterfactual 型 KU 的核心困難：當新事實與 LLM 既有知識衝突時，LLM 傾向以既有知識作答。本節指出，baselines 在 FC-SH 上的失敗主要來自此偏好，而非檢索或機制問題。分析聚焦於 \texttt{has\_pair} 子集（ground truth 同時含舊值與 counterfactual 新值，分母 $6\text{k}/32\text{k}/64\text{k}/262\text{k} = 74/65/66/77$），只有這類 query 才真正觸發 KU 判斷。

一個跨方法一致的現象是：幾乎所有 method 失敗時，最終答案都回退到 \texttt{gt\_old}（世界知識中的舊值）。此共同的失敗方向即已指向既有知識偏好；各 method 的差異僅在於新版於 pipeline 何處被丟棄。

write-time 方法（Mem0、Zep）的新版在寫入階段即被覆寫或未被標為失效，query-time 檢索時記憶中已無新版可取回，因此無法追蹤新版於決策點的去向，其失敗也就無法乾淨區分為既有知識偏好或機制與能力。本節的偏好判讀因此聚焦於能明確追蹤新版去向的 query-time 方法（Vanilla-RAG、Don't Ask），這類方法的記憶保留了所有版本，新版是否抵達最終決策點、以及抵達後是否被採納，皆可逐題計數。

表~\ref{tab:errormode_twocol} 依 \texttt{gt\_new} 被丟棄的位置，將 query-time 方法在 \texttt{has\_pair} 上的每題失敗分為兩類：「抽取前丟棄」指 \texttt{gt\_new} 在版本決定之前即被丟棄，且未進入答題階段；「答題仍答舊」指 \texttt{gt\_new} 已在候選集內，且LLM 仍輸出舊值。兩類的分布呈現明顯的左右分裂：Don't Ask 的失敗幾乎全落在「抽取前丟棄」，其 candidate extraction 在新版位於 top-100 候選集時仍未將其抽出；Vanilla-RAG 的失敗幾乎全落在「答題仍答舊」，其序號規則已寫入 prompt，recency judge 仍選擇舊值。同一偏好因此在兩個 method 上以 pipeline 不同位置的形式出現，一個在 candidate extraction，一個在答題階段的 recency judge。

\begin{table}[!htb]
\centering
\caption{Query-time 方法在 \texttt{has\_pair} 上的失敗分布（gpt-4o-mini）。每題失敗依 \texttt{gt\_new} 被丟棄的位置分為兩類：\textbf{抽取前丟棄}指 \texttt{gt\_new} 未進入答題階段，\textbf{答題仍答舊}指 \texttt{gt\_new} 已在候選集內、LLM 仍輸出舊值。兩類合計為該 length 的總失敗題數。$^{\dagger}$ 標記的答題失敗中，部分為 benchmark 序號標記相反所致（非方法本身失敗）。}
\label{tab:errormode_twocol}
\small
\begin{tabular}{lcccccccc}
\toprule
& \multicolumn{2}{c}{6k} & \multicolumn{2}{c}{32k} & \multicolumn{2}{c}{64k} & \multicolumn{2}{c}{262k} \\
\cmidrule(lr){2-3}\cmidrule(lr){4-5}\cmidrule(lr){6-7}\cmidrule(lr){8-9}
Method & 抽取前 & 答題 & 抽取前 & 答題 & 抽取前 & 答題 & 抽取前 & 答題 \\
\midrule
Don't Ask & 20 & 0 & 10 & 3$^{\dagger}$ & 11 & 2$^{\dagger}$ & 11 & 3$^{\dagger}$ \\
Vanilla-RAG & 0 & 7 & 0 & 23 & 0 & 15 & 1 & 18 \\
Ours (Struct-Only) & 7 & 0 & 10 & 2$^{\dagger}$ & 8 & 0 & 8 & 6 \\
\bottomrule
\end{tabular}
\end{table}

此偏好最乾淨的證據來自 LCA，它無檢索、無 memory pipeline，完整編號 fact list（新舊兩版皆在）直接進入 prompt，因此不含任何 pipeline confound。於輸入未被截斷的 6k/32k/64k，LCA 失敗中仍有 $67\sim87\%$ 答 \texttt{gt\_old}，即新版就在 context 內、LLM 仍拒絕採納。此結果與表~\ref{tab:errormode_twocol} 的 query-time 觀察一致：三個 query-time 方法於 262k 皆無實質 retrieval miss，說明失敗與 context 長度無關，而是 LLM 在拿到新版時拒絕採納。Listing~\ref{lst:dontask_case} 以一題呈現 Don't Ask 的逐字 candidate 輸出，直接顯示新版位於候選集卻未被抽出。

\begin{lstlisting}[style=tracebox, caption={一題 counterfactual 的 per-qid trace（FC-SH 6k, qid 8）。新舊版皆位於 top-100 候選集，新版序號較大；Don't Ask 的 candidate extraction 逐字輸出僅含舊版一個候選（\texttt{n\_candidates=1}，\texttt{n\_malformed\_dropped=0}，新版是被 LLM 拒抽而非 schema 丟棄），取序號最大者因此只能回傳舊值。本方法於同一候選集以 $(s, p)$ 歸群取最新序號，正確選出新版。}, label={lst:dontask_case}]
Q: What is the official language of Japan?
Retrieved top-100 pool (serial-prefixed; both versions present):
240  The official language of Japan is Japanese.   [gt_old]
439  The official language of Japan is Swedish.     [gt_new, newer serial]
Don't Ask -> LLM candidate extraction (verbatim raw output):
{"candidates":[{"serial":240,"fact_text":"The official language of
Japan is Japanese.","answer_entity":"Japanese"}]}
n_candidates=1,  n_malformed_dropped=0   (serial 439 never extracted)
max(serial)=240  =>  answer: "Japanese"   [wrong; gt="Swedish"]
Ours (same pool): group (Japan, official-language) -> pick newest serial=439
=>  answer: "Swedish"   [correct]
\end{lstlisting}

本方法以 $(s, p)$ 的 structural matching 辨識版本，同一事實的新舊版只要落入相同的 $(s, p)$ 群即一併納入，版本辨識為確定性配對，不經 LLM 對候選的語意抽取，因此依設計不暴露於前述既有知識偏好。表~\ref{tab:errormode_twocol} 中 Ours (Struct-Only) 的失敗集中在「抽取前丟棄」，其來源為 $(s, p)$ 與 triple extraction 的品質，即新舊版因抽取用字差異落入不同的 $(s, p)$ 群而無從比較，而非 LLM 對既有知識的偏好；此殘餘的錯誤模式與 structural matching、LLM Fallback 各自的貢獻於 Section~\ref{sec:ablation} 分析。

此結果支持 Chapter~\ref{ch:introduction} 的論點：於 query-time 或 write-time 以 LLM 判斷版本的方法，在 counterfactual 情境下受既有知識偏好影響；而本方法將版本辨識移出 LLM，以 $(s, p)$ 結構配對負責，依設計不落入同一偏好，僅於結構失敗的殘餘上才需要 LLM 補救。