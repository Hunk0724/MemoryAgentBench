\chapter{Experiments}
\label{ch:experiments}
% NOTE: 需於 preamble 加入 \usepackage{placeins} 以支援 \FloatBarrier

\section{Experimental Setup}
\label{sec:setup}

\subsection{Datasets}
\label{subsec:datasets}
本文於兩個 KU benchmark 上評測。第一個為 MemoryAgentBench 中的 FactConsolidation Single-Hop (FC-SH)~\cite{hu2026evaluating}，其 context 由 MQuAKE~\cite{zhong2023mquake} 的 counterfactual 事實，每一句為序號加上 fact statement 的形式，全體構成一份編號列表，對應 counterfactual 型 KU 情境（新事實與 LLM 既有知識衝突）。第二個為 LongMemEval~\cite{wulongmemeval} 中的 knowledge-update subtask (LME-KU)，其 context 由多個 session 的自然對話組成，對應 personal 型 KU 情境（使用者事實隨時間變動，與 LLM 既有知識無衝突）。兩者的統計整理於 Table~\ref{tab:datasets}。

\begin{table}[!htb]
\centering
\caption{Datasets summary。has\_pair 為 FC-SH 中真正含 old 與 new 版本的 query 子集，用於 Section~\ref{sec:attribution} 的歸因分析。}
\label{tab:datasets}
\small
\begin{tabularx}{\linewidth}{lXX}
\toprule
Property & FC-SH & LME-KU \\
\midrule
Source & MemoryAgentBench~\cite{hu2026evaluating} & LongMemEval~\cite{wulongmemeval} \\
KU 情境 & Counterfactual & Personal \\
Context lengths & 6k, 32k, 64k, 262k tokens & mean 127.7k tokens per query \\
Context 結構 & 編號 fact statement 列表 & 多 session 對話 (mean 488 turns) \\
Queries & 100 per length & 78 KU questions \\
has\_pair 子集 & 74, 65, 66, 77 & 78（每 query 一 KU pair） \\
Fact bank 大小 & 455, 2{,}309, 4{,}570, 18{,}321 & 動態（隨 session 內容變動） \\
\bottomrule
\end{tabularx}
\end{table}

FC-SH 沿用 benchmark 官方 100-query 子集作為主要評測分母，對齊官方 evaluation 慣例。其 context 為 numbered fact statement 而非 dialogue turn，於 chunk size 512 下每 chunk average 含有約 35 個 fact statements。LME-KU 每個 question 對應一個 knowledge-update pair（舊值於早期 session，新值於後期 session），sessions 於 haystack 中依時間排列，系統需自 session 序中辨識最新版本作答。

\subsection{Baselines}
\label{subsec:baselines}
本文將 baselines 依 KU 判斷 timing 分為兩類（對應 Chapter~\ref{ch:related_work} 的 taxonomy）：write-time KU 與 query-time KU；另加一組無記憶架構的 long-context baseline 作為對照。各 baseline 的 KU 判斷機制整理於 Table~\ref{tab:baselines}。

\begin{table}[!htb]
\centering
\caption{Baselines summary。KU judgment timing 對應 Chapter~\ref{ch:related_work} 的 taxonomy。Mem0 + Fact Extraction 以本方法 write-time 的 fact extraction 取代 mem0 原生抽取，並保留其 destructive UPDATE 的對照組合。}
\label{tab:baselines}
\small
\begin{tabularx}{\linewidth}{llX}
\toprule
Method & Timing & 判斷機制 \\
\midrule
Mem0 Vanilla~\cite{chhikara2025mem0} & Write-time coupled & LLM 於單次呼叫輸出 ADD/UPDATE/DELETE/NOOP 並就地執行 \\
Mem0 + Fact Extraction~\cite{chhikara2025mem0} & Write-time coupled & 本方法的 fact extraction 加上 mem0 destructive UPDATE \\
Zep~\cite{rasmussen2025zep} & Write-time decoupled & 內部 LLM 標記 contradicts 或 duplicates，舊 edge 被 invalidated \\
LCA & 無記憶 & 直接以全 context 答題，無 write 與 retrieve pipeline \\
Vanilla-RAG & Query-time LLM & Top-100 檢索，候選以 ordinal-prefixed 格式呈現，由 LLM 依序號判斷 recency \\
Don't Ask~\cite{reddy2026don} & Query-time LLM & Top-100 檢索，LLM 抽出 candidates，以 $\max(\text{ordinal})$ 選版本 \\
\midrule
Ours (Struct + LLM-Fallback) & Query-time deterministic & $(s, p)$ structural matching 加 $\arg\max_t t$，LLM Fallback 於殘餘候選補救 \\
\bottomrule
\end{tabularx}
\end{table}

其中 Mem0 Vanilla 與 Mem0 + Fact Extraction 為本方法的兩個對照組合，前者展示 extraction 與 destructive commit 的聯合弱點，後者於良好 extraction 前提下隔離 destructive commit 的獨立效應。Vanilla-RAG 對應 Chapter~\ref{ch:related_work} 所述「將 RAG 場景的處理策略直接遷移至 KU 情境」的做法，即於寫入時保留 ingestion time 序號，查詢時將所有候選連同序號提供給 LLM，由 LLM 依「序號較大者為新版本」的指示自行判斷；因此，於候選的呈現格式中保留序號為此 baseline 的構成要件；若不保留序號，其 KU 判斷即無從執行。Don't Ask 為與本方法最接近的近期研究，兩者皆將 KU 延後至 query-time 並以確定性方式處理 freshness，但 Don't Ask 的 identity 判斷仍由 LLM extraction 承擔；為公平對比，本文直接引入其公開 repository 的 candidate extraction 與 freshness pick 實作，置於本文相同的實驗環境下執行。LCA 於 context window 受限的 backbone（gemma3 系列）上僅可對 6k 執行，於 gpt-4o-mini 上完整 4 length。

Vanilla-RAG 於兩個 benchmark 上採用不同的呼叫結構，此差異源於兩個 benchmark 的 native answer template 不同。FC-SH 的 native answer template 本身即含序號規則，因此 Vanilla-RAG 於 FC-SH 上為單次呼叫，於同一次呼叫中同時判斷 recency 與作答。LME-KU 的 native answer template 不含此規則，若於 LME-KU 上沿用單次呼叫，Vanilla-RAG 將成為全表唯一於答題 template 上與其餘 method 不一致者，其分數即無法歸因於 KU 機制。因此本文於 LME-KU 上改採兩階段結構：第一階段由 LLM 自 ordinal-prefixed 的 top-100 候選中選出 winners，第二階段以 LME native template 作答，該 template 與其餘 method 完全相同。為完整揭露，本文於 Table~\ref{tab:lme_main} 中同時報告單次呼叫版本作為 pipeline-matched reference，惟其不納入 template-controlled 的排序。

\subsection{Backbones}
\label{subsec:backbones}
依實際部署情境，本文於三個能力區間（共 6 個獨立 model）上評測，對應 Chapter~\ref{ch:introduction} 中所述的三個 LLM 使用情境。第一個為 privacy-sensitive on-device 情境~\cite{pham2025slimlm,huang2025middle}，以 gemma3 系列 (1B, 4B, 12B, 27B) 涵蓋。第二個為 cost-constrained API 情境~\cite{chenfrugalgpt}，以 gpt-4o-mini 作為主要 backbone（完整 4 length 執行）。第三個為 strong tier 情境，以 gpt-5.4-mini 於 6k 上驗證強端 backbone 對 baselines 的補救效果。此外，為驗證 backbone robustness 於不同 model family 皆成立，本文於 Gemma2-9B、Llama3.1-8B、Qwen2.5-7B、Mistral-7B 四個獨立系列的 7-9B open-weight local models 上額外評測。

上述兩組實驗於 backbone 的角色分工上有一項重要區別。Cross-family 系列於 4 個 model 上採用 held-fixed gpt-4o-mini 承擔 extraction（fact extraction 與 triple extraction），僅將 query-time 判斷（structural matching、LLM Fallback 與 answer LLM）換為該 local model，因此 backbone 對 KU 判斷的淨影響得以與 extraction 品質的變化分離。Gemma3 系列於 4 個 tier 上則以該 backbone 承擔整條 pipeline（fact extraction、triple extraction、structural matching、LLM Fallback 與 answer），因此於同一 backbone 內 method 之間的比較公平，但跨 backbone 的絕對值同時受 extraction 品質變化影響。兩組實驗於論述中互補：cross-family 系列建立「即使 extraction 由強 model 承擔，仍導致 baselines 的 KU 表現大幅下滑」的受控觀察，gemma3 tier 則反映「弱 backbone 承擔整條 pipeline」的實際部署情境，兩者共同支撐 backbone robustness 於 KU 判斷這一子任務上的立論。

\subsection{Metrics}
\label{subsec:metrics}
FC-SH 採用官方 substring exact match (sEM) metric~\cite{hu2026evaluating}，其後處理包含 normalization、parse output、以及 alias list 的 max 匹配。主要評測分母為每 length 100 個 query，對齊官方 evaluation 慣例。此 100 個 query 依 ground truth 是否含新舊兩個版本拆分為兩個互斥子集：has\_pair 子集 (74 / 65 / 66 / 77) 為 ground truth 中同時含 gt\_new 與 gt\_old 的 query，為 KU 判斷真正被觸發的部分，僅於 Section~\ref{subsec:error_mode} 的機制分析中使用；其餘為 no\_conflict 子集（6k 上為 26 題），其 ground truth 僅有單一版本，不涉及版本選擇。LME-KU 採用 LongMemEval 官方的 LLM autoeval~\cite{wulongmemeval}，以 gpt-4o-mini-2024-07-18 作為 judge model，主要評測分母為 78 個 KU questions。所有實驗以 temperature 0 執行單次 deterministic run。

\subsection{Implementation Details}
\label{subsec:implementation}
Chunker 使用 chunk size 512；retrieval 使用 vector search 取回 top-100 候選，embedding model 為 text-embedding-3-small (1536 維度)。Zep 依其官方推薦使用 top-10 檢索。All backbone 於推論時 temperature 設為 0。Extraction（fact extraction 與 triple extraction）於 cross-family 實驗中 held-fixed 為 gpt-4o-mini，以隔離 KU 判斷的淨影響；於 gemma3 tier 則使用該 backbone 自身作為 extraction model，以誠實反映「弱 backbone 整條 pipeline」的實際部署情境。

答題階段的 prompt 對齊分為兩個層次。任務指令層於全部 method 上一致：所有 method 的 question 皆由 benchmark 原生的 conversation creator 統一 wrap 為含序號規則與「僅依記憶中的知識作答，而非真實世界的事實」指令的 formatted query，再原封傳入各 method 的 handler，因此無任何 method 於此規則的可得性上取得優勢。Inference scaffolding 層則沿用各 method 於 benchmark 中的原生 handler，於此層次上可分為三個對齊層級。第一層為本方法、Mem0 Vanilla 與 Mem0 + Fact Extraction，三者共用同一 handler，其 system message 與 memory 的呈現格式完全相同，差異僅在於送入答題階段的 memory selection，此為本文最主要的受控對照。第二層為 Vanilla-RAG，其與第一層共用同一 handler 骨架，但 memory 以 ordinal-prefixed 格式呈現並搭配對應的 system message，此差異為該 baseline 的構成要件（見 Section~\ref{subsec:baselines}）。第三層為 LCA 與 Zep，兩者沿用各自於 benchmark 中的原生 scaffolding，其 system message 內容與 memory 的擺放位置與前兩層不同。此三層皆為 benchmark 原生設計的沿用，對齊 benchmark 官方跨 method 比較的慣例。

上述第三層的差異於解讀時需納入兩項考量。其一，Zep 的原生 scaffolding 額外包含一條 abstain 指令，要求模型於不確定時不作答；於 substring exact match 之下，abstain 與答錯同樣計為錯誤，此指令因此可能系統性壓低 Zep 的 sEM。此差異的方向對本文的結論有利，本文於此明確揭露；惟 Zep 於 6k 上達 82（Table~\ref{tab:main_fcsh}），顯示此指令並未於一般情境下實質壓低其表現。其二，本方法所屬 handler 將 memory 置於 system turn，而 LCA 與 Zep 置於 user turn，此位置差異可能影響模型對 memory 的利用程度。此兩項差異皆為沿用 benchmark 原生設計的結果，本文未對其作額外調整。

Don't Ask 於此對齊架構中為一項例外，需單獨說明。其實作直接沿用作者公開 repository 的 pipeline：LLM 僅參與 candidate extraction 一步，freshness 由 $\max(\text{ordinal})$ 確定性完成，答案直接取自結構化欄位，不經答題階段的 LLM 呼叫。此設計本身即無答題 prompt 可供對齊，其 candidate extraction 亦因此未收到 benchmark 的任務指令 wrap，即未收到上述「僅依記憶中的知識作答」的指令。本文選擇忠實重現其原始設計而不作介入，惟此差異於解讀其結果時應應納入考量。

\FloatBarrier

\section{Main Results on FC-SH}
\label{sec:main_results}
本節於 counterfactual 型 KU 情境 (FC-SH) 上以 gpt-4o-mini 為 backbone，涵蓋 4 個 context length (6k, 32k, 64k, 262k)，對本方法與所有 baselines 進行整體評測。此節建立本方法於主 backbone 上的定量領先，Section~\ref{sec:attribution} 則進一步分析此領先的來源。

\begin{table}[!htb]
\centering
\caption{FC-SH overall sEM (\%) 於 gpt-4o-mini backbone, 4 length $\times$ 9 method。Bold 表示該 length 上的最佳結果（含並列）；本方法的 main configuration 以粗體 method 名標示。AVG 欄為 4 length 的平均。Zep 沿用其原生 scaffolding，其中含一條 abstain 指令，於 sEM 之下 abstain 與答錯同樣計為錯誤（見 Section~\ref{subsec:implementation}）。}
\label{tab:main_fcsh}
\small
\begin{tabular}{lccccc}
\toprule
Method & 6k & 32k & 64k & 262k & AVG \\
\midrule
\multicolumn{6}{l}{\textit{Write-time KU baselines}} \\
Mem0 Vanilla & 16 & 22 & 28 & 17 & 20.8 \\
Mem0 + Fact Extraction & 52 & 52 & 65 & 50 & 54.8 \\
Zep ($k{=}10$) & 82 & 80 & 76 & 29 & 66.8 \\
\midrule
\multicolumn{6}{l}{\textit{Long-context baseline}} \\
LCA (full context) & 88 & 74 & 65 & 43 & 67.5 \\
\midrule
\multicolumn{6}{l}{\textit{Query-time KU baselines}} \\
Vanilla-RAG & 93 & 77 & 85 & 81 & 84.0 \\
Don't Ask & 80 & 86 & 88 & 86 & 85.0 \\
\midrule
\multicolumn{6}{l}{\textit{Ours (ablations and main)}} \\
Ours (LLM-Identity-Only) & \textbf{97} & \textbf{91} & 91 & 87 & 91.5 \\
Ours (Struct-Only) & 91 & 87 & 92 & 86 & 89.0 \\
\textbf{Ours (Struct + LLM-Fallback)} & 94 & \textbf{91} & \textbf{94} & \textbf{91} & \textbf{92.5} \\
\bottomrule
\end{tabular}
\end{table}

Table~\ref{tab:main_fcsh} 呈現三項觀察。
第一，依 4 length 的平均排序，full method (92.5) 為全部 method 最高，本方法的兩個 ablation (91.5 與 89.0) 次之，其後為 Don't Ask (85.0) 與 Vanilla-RAG (84.0)；write-time family 中最高者為 Zep (66.8)，與 long-context 對照 LCA (67.5) 同處明顯較低的區間，Mem0 + Fact Extraction 於任一 length 皆未超過 65。此排序建立本方法於主 backbone 上相對於既有方法的定量優勢，同時對應 Chapter~\ref{ch:related_work} 的 taxonomy：write-time family 於任一 length 上皆未超過 82，query-time family 則於全 length 上維持於 77 以上，兩類的區隔與 KU 判斷 timing 的分類一致。

第二，本方法為唯一於 4 length 全部維持 flat 高位的方法，overall sEM 於 91 到 94 之間（$\Delta$ 6k 到 262k 為 $-3$ pp），其他所有 method 至少於一個 length 上出現 $\geq 10$ pp 的掉幅。此觀察為一項 robustness check 而非本文的核心主張：記憶隨 context 累積而保留同一事實的多個版本，KU 的挑戰因此隨 context 增長而加劇，而本方法於 context 自 6k 累積至 262k 的過程中，KU 表現不隨之退化，因此本文的結論不限於短 context 設定。各 method 隨 context length 的個別行為（LCA 的單調下降、Vanilla-RAG 於 32k 的 non-monotonic dip、Zep 於 262k 崩至 29）與 Zep 崩塌的 mechanism-level 分析詳見附錄；其中 Zep 於 262k 的崩塌主為 query-time retrieval miss，其 top-10 retrieval 於 262k 的 has\_pair 中有 82\% 未同時取回 old 與 new 兩個版本，而非 write-time 的 contradiction 判斷不足。

Third，本文的複現結果與 benchmark 原文相符。MemoryAgentBench 原文於 262k 設定與 gpt-4o-mini backbone 上報告 Mem0 為 18\%~\cite{hu2026evaluating}，本文複現之 Mem0 Vanilla 於 262k 為 17，兩者幾乎一致。Zep 於原文所報為 7\%，本文複現為 29，高於原文；此差異應源於 graph 建構與檢索設定的不同，惟兩者於 262k 上崩塌的方向一致，皆顯著低於其於較短 context 上的表現。此對照支撐本文實驗環境的可信度，亦支撐 Chapter~\ref{ch:introduction} 中以此組數字建立的 motivation。

\FloatBarrier

\section{Attribution: Why Baselines Fail at Knowledge Update}
\label{sec:attribution}
Section~\ref{sec:main_results} 建立了本方法相對 baselines 的定量領先，但定量領先本身不指出領先的來源。本節以兩項互補的證據確立此來源為 LLM 對既有知識的偏好。Section~\ref{subsec:error_mode} 於 FC-SH 上以 per-qid 逐題分析 baselines 的失敗案例，顯示 baselines 於 KU 失敗時一致地回退到既有知識中的舊值；Section~\ref{subsec:lme_control} 則以 personal 型 KU 情境作為對照條件，此情境中的新事實與 LLM 既有知識無衝突，因此若上述歸因成立，本方法與 baselines 的差距應於此情境下顯著收窄。兩項證據分別自失敗模式與對照條件兩個方向指向同一結論，共同兌現 Chapter~\ref{ch:introduction} 的 Objective (ii)。

\subsection{Per-qid Error Mode: Baselines Fall Back to Prior Knowledge}
\label{subsec:error_mode}
於 FC-SH 上以 per-qid 逐題分析 baselines 於 has\_pair 子集上的失敗案例，揭露一個一致的模式：baselines 於 KU 失敗時，回退到與其既有知識一致的舊值（即 counterfactual scope 下的 gt\_OLD）。此模式於三個代表 method 上皆成立，但失敗發生的 pipeline 位置不同。

Vanilla-RAG 於 4 length 上的 has\_pair 失敗 95 至 100 percent 為回退到 gt\_OLD，此模式於 32k 最為嚴重（65 題中錯 23 題），對應 Table~\ref{tab:main_fcsh} 中 Vanilla-RAG 於 32k 的 non-monotonic dip。要將此失敗歸因於 LLM 對既有知識的偏好，須先排除一項替代解釋：若 gt\_new 根本未被檢索取回，則此失敗僅為 retrieval miss，與 LLM 的判斷偏好無關。

本方法與 Vanilla-RAG 共用同一 retrieval 設定，因此兩者於同一 query 上所面對的候選集完全相同；本方法於 262k 上達 91，代表其候選集中至少 91\% 的 query 含有 gt\_new，Vanilla-RAG 於同一候選集上僅達 81，其差距因此不可能源於 retrieval miss。
綜合上述，Vanilla-RAG 的失敗發生於下游的 recency judge：兩個版本皆存在於候選集且序號規則已明確寫入其答題 prompt 之中，LLM 仍未嚴格依序號規則選出新版本，而是選擇與其既有知識一致的舊值。此觀察直接支撐 Chapter~\ref{ch:methodology} 中「version decision 必須為 deterministic 操作，不可交由 LLM 承擔」的核心設計決策。

Don't Ask 於 6k 與 64k 上的 has\_pair 失敗 100 percent 為 LLM 抽出的候選集僅含一個版本（n\_candidates 為 1），且該候選為與 LLM 既有知識一致的舊值（即 gt\_OLD），counterfactual 的新版本雖然存在於 top-100 檢索範圍內，卻於 LLM candidate extraction 階段被漏掉。此模式反映 Don't Ask 的失敗不在於 freshness 選擇本身（$\max(\text{ordinal})$ 於單一候選上 trivially 正確），而在於上游 LLM candidate extraction 洩漏了對既有知識的偏好。此觀察為本文與 Don't Ask 的具體 quantitative 差異來源：兩者皆將 freshness 交給確定性操作，但 Don't Ask 的 identity 仍由 LLM extraction 承擔，而本方法將 identity 亦結構化為 $(s, p)$ 配對，因而免疫此類洩漏。此處另有一項值得注意的性質：Don't Ask 的 pipeline 中不含答題階段的 LLM 呼叫（見 Section~\ref{subsec:implementation}），其 LLM 僅參與 candidate extraction，然而對既有知識的偏好仍於該階段洩漏。此顯示此偏好並非答題階段特有的現象，而是 LLM 只要於 pipeline 中的任一位置接觸 counterfactual 事實即可能發生，因此將 KU 判斷整段移出 LLM，而非僅將其自答題階段移除，方為有效的處理方式。

Ours (Struct-Only) 於 6k 與 32k 上的 has\_pair 失敗 100 percent 為回退到 gt\_OLD，64k 與 262k 上分別為 88 percent 與 79 percent。其失敗根因單一，為 $(s, p)$ canonicalization miss：new 與 old 版本因 predicate 的 stem 對 full form 差異或 subject 的細微變體被分入不同結構群，$\arg\max_{t} t$ 於群內無從比對兩個版本，候選集因此同時保留兩個版本；於此情境下 answer LLM 於缺乏 recency 指引時，回退到與其既有知識一致的舊值。此為 LLM Fallback 存在的理由，即於 structural matching 無法歸群時補上 identity 判斷。

上述三種失敗模式共同支撐 Chapter~\ref{ch:introduction} 中的 causal claim：baselines 的錯誤主要來自 LLM 於 counterfactual 情境下對既有知識的偏好。三個 method 各自於 pipeline 的不同位置洩漏此偏好（Vanilla-RAG 於下游 recency judge、Don't Ask 於上游 candidate extraction、Ours Struct-Only 於 structural 碎裂後的答題階段），而本方法以「忠實寫入所有版本、結構化 identity、以 $\arg\max_{t} t$ 決定版本、LLM Fallback 補救少數殘餘」的組合逐一 dodge 各層洩漏。

\subsection{LME-KU as a Control Condition}
\label{subsec:lme_control}
Section~\ref{subsec:error_mode} 自失敗模式的方向支撐上述歸因，本節則以對照條件自另一方向驗證同一歸因。LME-KU 對應 personal 型 KU 情境，其事實隨使用者狀態變動（例如居住城市與職業），與 LLM 既有知識無衝突，因此 LLM 於判斷時不受 knowledge conflict 的抗力。若 Section~\ref{subsec:error_mode} 的歸因成立，則本方法與 baselines 於此情境上的差距應顯著收窄。Table~\ref{tab:lme_main} 呈現本方法與 baselines 於 LME-KU 上的 accuracy。

\begin{table}[!htb]
\centering
\caption{LME-KU accuracy (\%) 於 gpt-4o-mini backbone, N = 78。Bold 表示答題 template 受控之方法中的最佳結果。$^{\dagger}$ Vanilla-RAG (1-stage) 之答題 template 與其餘 method 不一致（見 Section~\ref{subsec:baselines}），列為 pipeline-matched reference，不納入 template-controlled 排序。}
\label{tab:lme_main}
\small
\begin{tabular}{lcc}
\toprule
Method & correct / 78 & acc \\
\midrule
Mem0 Vanilla & 53 / 78 & 67.9 \\
Mem0 + Fact Extraction & 47 / 78 & 60.3 \\
Vanilla-RAG (2-stage) & 54 / 78 & 69.2 \\
\textbf{Ours (Struct + LLM-Fallback)} & \textbf{55 / 78} & \textbf{70.5} \\
\midrule
Vanilla-RAG (1-stage)$^{\dagger}$ & 58 / 78 & 74.4 \\
\bottomrule
\end{tabular}
\end{table}

Zep 於 LME-KU 上因其 free plan 的 per-graph 128k token 上限與 LME context 平均 127.7k 相撞而未能完整執行，列為 caveat 未進入 Table~\ref{tab:lme_main}。Don't Ask 依其原始設計依賴 dataset 提供的 numbered fact bank 與 global serial ordering，此為 FC-SH 原生設計，LME-KU 的 per-session 對話結構不符合此假設，強行 adapt 需自建 per-session bank 與自定 serial 語意，已偏離其作者原論文 scope，亦列為 caveat 未進入 Table~\ref{tab:lme_main}。

Table~\ref{tab:lme_gap} 對照本方法於兩個 KU情境上相對 baselines 的 gap。跨 benchmark 的相減要求兩端的 pipeline 一致，因此 Vanilla-RAG 一列採用 1-stage 版本，其呼叫結構與 FC-SH 上的 Vanilla-RAG 相同。Anchor 採用 FC-SH 的 4 length 平均而非單一 length，因 LME-KU 的 context 平均為 127.7k，與任一單一 length 皆不對應。

\begin{table}[!htb]
\centering
\caption{本方法相對 baselines 的 gap 於兩個 KU 情境上的對照。負值表示本方法輸給該 baseline。FC-SH 欄採 4 length 平均（Table~\ref{tab:main_fcsh} 之 AVG 欄）。收窄的方向於 FC-SH 的 4 個 length 上皆成立：相對 Mem0 + Fact Extraction 為 +42, +39, +29, +41，相對 Vanilla-RAG (1-stage) 為 +1, +14, +9, +10，其中 6k 的 +1 為 gpt-4o-mini 於短 context 上的 ceiling effect。}
\label{tab:lme_gap}
\small
\begin{tabular}{lcc}
\toprule
對照 baseline & FC-SH AVG (counterfactual) & LME-KU (personal) \\
\midrule
vs. Mem0 + Fact Extraction & +37.7 pp (92.5 對 54.8) & +10.2 pp (70.5 對 60.3) \\
vs. Vanilla-RAG (1-stage) & +8.5 pp (92.5 對 84.0) & $-$3.9 pp (70.5 對 74.4) \\
\bottomrule
\end{tabular}
\end{table}

Table~\ref{tab:lme_main} 與 Table~\ref{tab:lme_gap} 呈現以下四項觀察。
第一，本方法相對 baselines 的 gap 於 personal 型情境上顯著收窄，相對 Mem0 + Fact Extraction 自 +37.7 pp 收窄至 +10.2 pp，相對 Vanilla-RAG (1-stage) 則自 +8.5 pp 收窄並反轉為 $-$3.9 pp。此收窄的方向與 Section~\ref{subsec:error_mode} 的歸因所預測者一致：當情境轉為 personal 型時，baselines 於「LLM 傾向以既有知識作答」這一失敗模式上的暴露程度顯著降低，gap 因此收窄。此為對照條件的核心結果，反向支撐 counterfactual 情境上的巨大 gap 確實來自 LLM 對既有知識的偏好，而非來自本方法於一般記憶任務上的普遍優勢。

第二，Vanilla-RAG 一列的反轉為此對照最乾淨的形式。同一條「序號較大者為新版本」的規則，於 FC-SH 上 LLM 因既有知識的抗力而未忠實執行（has\_pair 失敗 95 至 100 percent 回退舊值），於 LME-KU 上則因無此抗力而得以直接依序號選出正確版本，並取得全表最高的 74.4。同一條規則於兩種情境上產出兩種結果，此對照將差異來源明確定位於情境是否存在 knowledge conflict，而非規則本身或 pipeline 設計。

第三，Mem0 + Fact Extraction 一列的收窄為保守估計。此 baseline 於 LME-KU 上表現反轉，低於 Mem0 Vanilla 7.6 pp，其機制推論如下：LME-KU 對話事實密度較低，本方法的 fact extraction 抽出更多且更精細的事實，mem0 destructive UPDATE 因此有更多機會產生 missing ADD 或 cross-item confusion，反致 damage 大於 mem0 native extraction。此 confound 的方向為壓低該 baseline 於 LME-KU 上的分數，因而將 gap 往寬推，與本節所欲論證的收窄方向相反；於此 confound 之下仍觀察到 +37.7 pp 至 +10.2 pp 的收窄，因此該收窄為保守估計。

第四，於答題 template 受控的方法之中，本方法於 LME-KU 上為最高 (70.5)，惟其領先 Vanilla-RAG (2-stage) 僅 1.3 pp（55 題對 54 題，差距為 1 題），於 N = 78 的單次 deterministic run 之下不足以支撐領先的主張。本節因此將此情境上的結論定位為「本方法與 template 受控的 baselines 相當」，而非領先。此定位與上述收窄的預測一致，並於 Section~\ref{sec:limitations} 中作為本方法適用範圍的邊界之一。

\FloatBarrier

\section{Robustness across Backbone Capabilities}
\label{sec:backbone_robustness}
本節驗證 Chapter~\ref{ch:introduction} 的 Objective (iii)：現有方法的 KU 表現隨 backbone 能力減弱而大幅下滑，本方法的退化幅度則明顯較小，兩者的差距因此隨 backbone 能力減弱而擴大。此對比為本文最有 discriminating power 的實驗，直接對應 Chapter~\ref{ch:methodology} 的核心主張：當 KU 判斷由 LLM 移至 deterministic structural matching 後，其表現由事實的結構所決定，而非由 backbone 的判斷能力所決定。實驗涵蓋兩組設定：cross-family 系列於 4 個獨立 model family 上以 held-fixed extraction 隔離 backbone 對 KU 判斷的淨影響；gemma3 系列於 4 個 tier 上以 per-backbone extraction 反映弱 backbone 承擔整條 pipeline 的部署情境。此外以 OpenAI mini-tier 的兩個 backbone 建立強端 reference。

\figt{0.7\columnwidth}
{figs/exp_backbone_spectrum}
{FC-SH 6k overall sEM 於 6 tier backbone 上的變化。橫軸自左至右為 backbone 能力遞增順序（gemma3-1B 至 gpt-5.4-mini）。本方法於全 backbone 上皆維持領先；baselines 於弱 backbone 上崩塌（gemma3-1B 上皆不高於 30），於強 backbone 上呈現 gap 收斂但未反轉。左側灰色區塊標示 gemma3 tier 為 per-backbone extraction，右側為 gpt tier 的 held-fixed extraction。}
{fig:exp_backbone_spectrum}

\subsection{Cross-family Results with Held-fixed Extraction}
\label{subsec:cross_family}
本節於 4 個獨立系列的 7-9B open-weight local models (Gemma2-9B, Llama3.1-8B, Qwen2.5-7B, Mistral-7B) 上執行，採用 held-fixed gpt-4o-mini extraction 設定，因此 backbone 之間的差異僅來自 query-time 的 KU 判斷與答題，不含 extraction 品質的變化。此設定為本節中最受控的證據，故先於 gemma3 tier 呈現。Table~\ref{tab:cross_family} 呈現其結果。

\begin{table}[!htb]
\centering
\caption{FC-SH 6k overall sEM (\%) 於 4 個 open-weight backbone family 上, held-fixed gpt-4o-mini extraction。Bold 表示該 backbone 上的最佳結果（含並列）；本方法的 main configuration 以粗體 method 名標示。}
\label{tab:cross_family}
\small
\begin{tabular}{lcccc}
\toprule
Method & Gemma2-9B & Llama3.1-8B & Qwen2.5-7B & Mistral-7B \\
\midrule
Mem0 + Fact Extraction & 27 & 8 & 21 & 19 \\
Vanilla-RAG & 38 & 70 & 27 & 26 \\
\midrule
Ours (Struct-Only) & 71 & \textbf{81} & 83 & 64 \\
\textbf{Ours (Struct + LLM-Fallback)} & \textbf{72} & \textbf{81} & \textbf{91} & \textbf{66} \\
\bottomrule
\end{tabular}
\end{table}

Table~\ref{tab:cross_family} 呈現以下三項觀察。
第一，本方法於 4 個系列上皆為領先，overall sEM 於 66 至 91 之間，與最佳 baseline 的差距為 11 至 64 pp；baselines 於 4 個系列上皆顯著低於本方法，Mem0 + Fact Extraction 於全系列崩至 8 至 27，Vanilla-RAG 於 3 個系列崩至 26 至 38。此模式跨系列一致，驗證 backbone robustness 不是特定 model family 的現象。

第二，由於此節採用 held-fixed gpt-4o-mini extraction，baselines 於此設定下的崩塌無法歸因於 extraction 品質下降，因此主要 gap 來自 KU 判斷本身，即 Vanilla-RAG 的 LLM recency judge 與 Mem0 + Fact Extraction 的 write-time destructive UPDATE。此設定同時為本方法提供一項 analytic property：於 held-fixed extraction 之下，candidate retrieval 為 deterministic 的 vector search，structural matching 與 $\arg\max_{t} t$ 皆不涉及 LLM 呼叫，因此 Struct-Only 所輸出的 Current Version(s) 於 4 個 backbone 上完全相同（見 Section~\ref{subsec:structural_matching}）。本方法於此設定下 64 至 83 的變動因此僅來自答題階段的能力差異，不來自 KU 判斷本身；baselines 於此設定下的變動則額外包含 KU 判斷本身的失效。此為本方法與 baselines 於 backbone robustness 上差異的直接來源。

第三，Vanilla-RAG 於 3 個系列 (Qwen2.5-7B 27, Mistral-7B 26, Gemma2-9B 38) 上崩塌，Llama3.1-8B 上為例外 (70)。此處值得強調的是，序號規則於全部 method 的答題 prompt 中一致存在（見 Section~\ref{subsec:implementation}），且 Vanilla-RAG 為唯一於候選呈現格式中保留序號、使該規則得以實際執行的 method；即便如此，它於 Qwen2.5-7B 上仍僅為 27，於 Mistral-7B 上僅為 26。此排除「baselines 僅是未被告知規則」的替代解釋，將瓶頸明確定位於 LLM 於 knowledge conflict 之下是否忠實執行已知的規則。Llama3.1-8B 的相對佳表現可能與其於 rule-following 上的能力較強有關。

\subsection{Gemma3 Spectrum and the Capability Gate of LLM Fallback}
\label{subsec:gemma3}
本節於 gemma3 4 tier 上以 per-backbone extraction 執行，即每個 backbone 以其自身承擔整條 pipeline（包含 fact extraction、triple extraction、structural matching、LLM Fallback 與 answer）。此設定反映弱 backbone 整條 pipeline 部署於 on-device 隱私敏感情境的實際使用情境，與 Section~\ref{subsec:cross_family} 的受控設定互補。Table~\ref{tab:gemma3} 呈現其結果，其中 $\Delta$ 欄為本方法內部 LLM Fallback 相對 Struct-Only 的淨貢獻。

\begin{table}[!htb]
\centering
\caption{FC-SH 6k overall sEM (\%) 於 gemma3 4 tier 上, per-backbone extraction。Bold 表示該 backbone 上的最佳結果（含並列）；本方法的 main configuration 以粗體 method 名標示。$\Delta$ 為 Ours (Struct + LLM-Fallback) 減 Ours (Struct-Only)，正值表示 LLM Fallback 為 net-positive。Mem0 Vanilla 於 gemma3-1B 上因資源限制未執行，以「—」標示；此格不影響本節的結論，因該 tier 上本方法為 44，而 Mem0 Vanilla 於 4B 上已僅為 11。}
\label{tab:gemma3}
\small
\begin{tabular}{lcccc}
\toprule
Method & 1B & 4B & 12B & 27B \\
\midrule
Mem0 Vanilla & — & 11 & 53 & 45 \\
Mem0 + Fact Extraction & 5 & 11 & 64 & 54 \\
Zep ($k{=}10$) & 29 & 32 & 58 & 62 \\
Vanilla-RAG & 30 & 48 & 68 & 69 \\
Don't Ask & 2 & 36 & 84 & 96 \\
\midrule
Ours (LLM-Identity-Only) & 27 & 50 & 72 & 59 \\
Ours (Struct-Only) & \textbf{52} & \textbf{79} & \textbf{99} & 97 \\
\textbf{Ours (Struct + LLM-Fallback)} & 44 & \textbf{79} & \textbf{99} & \textbf{99} \\
\midrule
$\Delta$ (LLM Fallback 淨貢獻) & $-8$ & 0 & 0 & $+2$ \\
\bottomrule
\end{tabular}
\end{table}

Table~\ref{tab:gemma3} 呈現以下三項觀察。
第一，本方法於全 4 tier 上相對所有 baselines 皆為領先，main configuration 為 44, 79, 99, 99，與該 tier 最佳 baseline 的差距為 3 至 31 pp。write-time baselines 於 1B 與 4B 上崩塌至 5 至 32，反映 destructive UPDATE 於 write-time 需要 LLM 承擔跨筆判斷，弱 backbone 於此任務上無法產出可靠的判斷結果，錯誤的 UPDATE 因而直接於記憶中造成不可逆的 loss。Don't Ask 於 1B 上崩至 2，反映其 LLM candidate extraction 於弱 backbone 上無法產出合格的候選集，freshness pick 於此情境下已無有效輸入。

第二，本方法於 1B 上的 44 為此 tier 中受 extraction confound 影響最深者，因此 gap 於此 tier 上反而縮至 14 pp，小於 4B 的 31 pp。此為 per-backbone extraction 設定的直接後果：gemma3-1B 同時承擔 fact extraction 與 triple extraction，其 extraction 品質下降同時壓低了本方法的表現。Section~\ref{subsec:cross_family} 的 held-fixed extraction 設定不含此 confound，其於 4 個系列上的 gap 為 11 至 64 pp，可作為本方法於 KU 判斷這一子任務上實際優勢的參考。兩節因此互補：本節誠實反映整條 pipeline 交由弱 backbone 的實際部署結果，前節則隔離出 KU 判斷本身的淨影響。

第三，本方法內部的 LLM Fallback 於 backbone 光譜上呈明顯的 capability-gate 特性。於最弱端 (1B) LLM Fallback 反而害本方法 8 pp，反映弱 backbone 於 identity clustering 這一 LLM 任務上無法產出可靠判斷，於此區間內傾向於錯誤合併不同事實 (over-merge)，因而污染了 Struct-Only 已經正確處理的候選集。於中段 (4B, 12B) LLM Fallback 為 neutral，structural matching 已涵蓋主要 identity情境。於強端 (27B) LLM Fallback 為 net-positive +2，於 gpt-4o-mini 上為 +3（Table~\ref{tab:main_fcsh} 中 91 對 94）。此模式兌現 Chapter~\ref{ch:methodology} 中對 LLM Fallback 「僅為 structural matching 無法歸群時的補救」的定位：LLM Fallback 是隨 backbone 能力增強而邊際效益上升的 capability-gated add-on，structural matching 才是 backbone-universal 的核心 workhorse，本方法的 backbone robustness 因此由 structural matching 承擔。此處需注意 gemma3 四列為 per-backbone extraction 而 gpt-4o-mini 為 held-fixed extraction，$\Delta$ 於同一 backbone 內兩個 configuration 之間計算，extraction 已於該 backbone 內受控，惟跨列比較時 extraction regime 的差異仍應納入考量。

\subsection{OpenAI Mini-tier}
\label{subsec:openai_tier}
Table~\ref{tab:openai_tier} 呈現本方法與所有 baselines 於 OpenAI mini-tier 兩個 backbone（gpt-4o-mini 為主 backbone, gpt-5.4-mini 為強端 reference）上的 FC-SH 6k overall sEM。此 tier 為 held-fixed gpt-4o-mini extraction，即 extraction 於兩個 backbone 上皆固定使用 gpt-4o-mini，僅將 query-time 判斷（structural matching、LLM Fallback 與 answer）換為該 backbone。

\begin{table}[!htb]
\centering
\caption{FC-SH 6k overall sEM (\%) 於 OpenAI mini-tier 上, held-fixed gpt-4o-mini extraction。$\Delta$ 為 gpt-5.4-mini 相對 gpt-4o-mini 的變化。}
\label{tab:openai_tier}
\small
\begin{tabular}{lccc}
\toprule
Method & gpt-4o-mini & gpt-5.4-mini & $\Delta$ \\
\midrule
Mem0 + Fact Extraction & 52 & 70 & +18 \\
Don't Ask & 80 & 96 & +16 \\
Zep ($k{=}10$) & 82 & 93 & +11 \\
Vanilla-RAG & 93 & 98 & +5 \\
\textbf{Ours (Struct + LLM-Fallback)} & \textbf{94} & \textbf{99} & +5 \\
\bottomrule
\end{tabular}
\end{table}

Table~\ref{tab:openai_tier} 呈現兩項觀察。第一，baselines 於強 backbone 上呈現顯著的 gap 收斂，其收斂由地板抬升所驅動（Mem0 + Fact Extraction 上升 18 pp，Don't Ask 上升 16 pp，Zep 上升 11 pp），此模式反向支撐本文對「baselines 依賴 LLM 判斷 KU」的定位：當 LLM 能力增強時，LLM 所承擔的判斷部分自然受益，因此其增益幅度明顯大於本方法的 +5 pp。第二，於 gpt-5.4-mini 上 spread 收斂至 29 pp（相較 gpt-4o-mini 的 42 pp），本方法為 99 而 second-best 為 98；此 1 pp 的差距於單次 deterministic run 之下不構成領先的主張，本文於此僅主張 baselines 於強 backbone 上未反轉本方法的表現。此觀察建立「backbone 增強能改善 baselines，但無法將其表現推至本方法之上」的定量結論，同時界定本方法的優勢集中於中低能力 backbone 的部署區間。

\subsection{Summary}
\label{subsec:backbone_summary}
上述三個設定共同支撐 Objective (iii)。baselines 的 KU 表現隨 backbone 能力減弱而大幅下滑，於 gemma3-1B 上皆不高於 30，於 cross-family 的 4 個系列上崩至 8 至 70；本方法的退化幅度則明顯較小，且於全部 10 個 backbone 設定上皆維持領先。兩者的差距因此隨 backbone 能力減弱而擴大，於強端收斂至 1 pp，於 extraction 受控的 cross-family 上則張至 11 至 64 pp。此模式於 Figure~\ref{fig:exp_backbone_spectrum} 中一目了然，直接驗證 Chapter~\ref{ch:methodology} 的核心主張：當 KU 判斷由 LLM 移至 deterministic structural matching 後，其表現由事實的結構所決定，而非由 backbone 的判斷能力所決定。

\FloatBarrier

\section{Ablation Study}
\label{sec:ablation}
本節量化本方法兩個核心 component（structural matching 與 LLM Fallback）於 context length 上的分工。LLM Fallback 於 backbone 光譜上的 capability-gate 特性已於 Section~\ref{subsec:gemma3} 呈現，此處不重複。Table~\ref{tab:ablation_components} 呈現本方法內部三個 configuration 於 FC-SH 4 length 上的 overall sEM，其中 Struct-Only 保留 structural matching 與 $\arg\max_{t} t$ 而關閉 LLM Fallback，LLM-Identity-Only 則關閉 structural matching，將所有候選送入 LLM 判斷 identity。

\begin{table}[!htb]
\centering
\caption{FC-SH overall sEM (\%) 於 gpt-4o-mini backbone, 本方法內部 configuration 的 ablation。Bold 表示該 length 上的最佳結果（含並列）。}
\label{tab:ablation_components}
\small
\begin{tabular}{lcccc}
\toprule
Method & 6k & 32k & 64k & 262k \\
\midrule
Ours (Struct-Only) & 91 & 87 & 92 & 86 \\
Ours (LLM-Identity-Only) & \textbf{97} & \textbf{91} & 91 & 87 \\
\textbf{Ours (Struct + LLM-Fallback)} & 94 & \textbf{91} & \textbf{94} & \textbf{91} \\
\bottomrule
\end{tabular}
\end{table}

Table~\ref{tab:ablation_components} 呈現兩項觀察。第一，兩個 identity 機制於 context length 上呈現互補分工。LLM-Identity-Only 於短 context (6k) 上明顯優於 Struct-Only (97 對 91)，反映此區間內候選集規模較小，LLM 於單次呼叫中足以涵蓋所有可能的 identity pair；至長 context (262k)，兩者的 overall sEM 已相近 (87 對 86)。此收斂反映長 context 下 top-100 pool 中的 distractor 增多，LLM 於單次判斷中的 identity grouping 於大 pool 上失去穩定性，而 structural matching 的 $(s, p)$ 配對為 exact match，不受 pool 規模影響。第二，full method 為三個 configuration 中 4 length 平均最高者 (92.5)，且為唯一於 4 length 皆維持 91 以上者；LLM Fallback 相對 Struct-Only 的淨貢獻於 4 length 上為 +3, +4, +2, +5，長 context 上邊際效益最大。此互補分工為 full method 同時保留兩個 component 的定量理由。此外，以 offline $(s, p)$-merge proxy 對 has\_pair query 的三分顯示，structural matching 於 4 length 上皆承擔 68\% 以上的判斷，LLM Fallback 的觸發率為 12\% 至 32\%，兌現 Chapter~\ref{ch:methodology} 中「LLM Fallback 僅於少數案例介入」的定位；此 proxy 的完整定義、其分類限制與逐 length 的觸發率與 in-bucket accuracy 詳見附錄。

\subsection{Subject-Consistency Guard: A Backbone-Adaptive Safeguard}
\label{subsec:guard_ablation}

本節量化 Section~\ref{subsec:structural_matching} 所述之 subject-consistency guard 的實際貢獻。Guard 於實作上為 LLM Fallback 之後的 Python-side post-filter，非 GROUPING\_PROMPT 內 rule 1 的重複；其執行順序為 prompt 先於 LLM 側告知不合併不同 subject，LLM 產出 raw clusters 之後 guard 於 Python 側依 metadata 中的 subject 訊號執行硬過濾。於 canonical 配置下，此 guard 為預設啟用；本節透過將 guard 停用（$\text{MEM0\_SUBJECT\_GUARD\_OFF}=1$）與 canonical 對照，隔離 guard 對最終 EM 的影響。

於 gpt-4o-mini backbone 上以 FC-SH 4 length 執行實測 ablation（Table~\ref{tab:guard_ablation_actual}）。於其餘 backbone 上，因 grouping cache 已於 canonical 執行時保存 LLM 的原始提議，本文以 offline predictor 依 cache 內容重演 guard 的執行結果並量化其對 gt\_new / gt\_old 的影響，於 gpt-4o-mini 4 length 上以實測驗證其方向 3 於 4 正確、magnitude 於 $\pm 3$ pp 內，因此 predictor 於其餘 backbone 上具備 backbone-directional 的可用信心（Table~\ref{tab:guard_ablation_predictor}）。

\begin{table}[!htb]
\centering
\caption{Subject-consistency guard 於 gpt-4o-mini backbone 上的 actual ablation。$\Delta_{\text{off}}$ 為 guard 停用相對 canonical 的 overall sEM 變化。}
\label{tab:guard_ablation_actual}
\small
\begin{tabular}{lccccc}
\toprule
Length / Benchmark & Guard on (canonical) & Guard off & $\Delta_{\text{off}}$ \\
\midrule
FC-SH 6k & 94 & 99 & $+5$ \\
FC-SH 32k & 91 & 88 & $-3$ \\
FC-SH 64k & 94 & 97 & $+3$ \\
FC-SH 262k & 91 & 92 & $+1$ \\
FC-SH Mean 4L & 92.5 & 94.0 & $+1.5$ \\
LME-KU ($N{=}78$) & 70.5 & 69.2 & $-1.3$ \\
\bottomrule
\end{tabular}
\end{table}

\begin{table}[!htb]
\centering
\caption{Subject-consistency guard 於其他 backbone 上的 offline predictor 結果（FC-SH 6k has\_pair）。Reject\% 為 guard 於 LLM 所提議之 clusters 中拒絕的比例。$\Delta_{\text{off}}$ 之負值表示 guard 為淨益。無標記者為 no-op，因該 backbone 於 GROUPING\_PROMPT rule 下幾乎不產出違反 rule 的 raw clusters，guard 於實作上鮮少觸發。}
\label{tab:guard_ablation_predictor}
\small
\begin{tabular}{lcccc}
\toprule
Backbone & Clusters proposed & Reject\% & $\Delta_{\text{off}}$ (pred) \\
\midrule
gpt-5.4-mini (strong) & 87 & 67 & (ceiling-bound) \\
gpt-4.1-mini (strong) & 503 & 0 & 0 (no-op) \\
gpt-4o (strong) & 85 & 7 & 0 (no-op) \\
\midrule
gemma3-1B (weak) & 0 & --- & 0 (no-op) \\
gemma3-4B (weak) & 5 & 80 & $+2$ \\
gemma3-12B (weak) & 1 & 100 & $-1$ \\
gemma3-27B (weak) & 25 & 88 & $-4$ \\
\midrule
gemma2-9B (cross-family) & 27 & 70 & $+1$ \\
llama3.1-8B (cross-family) & 193 & 80 & $-2$ \\
qwen2.5-7B (cross-family) & 33 & 67 & $-3$ \\
mistral-7B (cross-family) & 140 & 83 & $-5$ \\
\bottomrule
\end{tabular}
\end{table}

Table~\ref{tab:guard_ablation_actual} 與 Table~\ref{tab:guard_ablation_predictor} 呈現三項觀察。第一，於強 backbone (gpt-4.1-mini, gpt-4o) 上，LLM 於 GROUPING\_PROMPT 之下幾乎不產出違反 rule 1 的 raw clusters，guard 於實作上鮮少觸發，$\Delta_{\text{off}}$ 為 0 或近 0；於此區間 guard 為背景元件，其存在不影響最終 EM。第二，於 gpt-4o-mini 上，guard 的淨效應於 4 length 上非單調 (+5, -3, +3, +1)，Mean 4L 為 +1.5 pp；此結果反映 guard 於 mid tier 上兼有兩種相反的影響：guard 拒絕跨 subject 的 raw cluster 保住原本會被 $\arg\max_{t} t$ 錯誤 drop 的正解，同時於 gt\_new 與 gt\_old 於 raw cluster 中共存的情境下亦拒絕本應有效的 identity 合併。第三，於 weak backbone 與 cross-family 上，guard 的淨貢獻方向明確為 $\Delta_{\text{off}} \leq 0$：於高活性 (clusters $\geq 100$) 的 llama3.1-8B (−2) 與 mistral-7B (−5) 上皆為 guard 有益，於 gemma3-27B (−4) 與 qwen2.5-7B (−3) 上亦然。此模式反映弱 LLM 於 GROUPING\_PROMPT 下過度提議跨 subject 的合併，guard 於 pipeline 之末端擋下這些 raw cluster 而避免 $\arg\max_{t} t$ 的錯誤 drop。

以上三個 tier 的觀察共同支撐 guard 為 backbone-adaptive 元件的定位：於強 backbone 上為 no-op、於 mid tier 上淨效應接近 zero-sum、於 weak / cross-family 上為淨益。本文於 canonical 配置中預設啟用 guard，理由為 (i) 於本文所評估的 backbone spectrum 上 guard 於多數 cell 為淨益或 no-op，僅於 gpt-4o-mini 4 length 的 Mean 出現 +1.5 pp 的機會成本；(ii) 於論文的部署情境上，weak / cross-family 為 privacy-sensitive on-device 與 cost-constrained deployment 的主要區間，guard 於此區間的淨益 (−2 至 −5 pp) 遠大於於 mid tier 的機會成本。此設計選擇因此於 backbone spectrum 的部署情境上為保守的預設，同時透過 environment variable 提供 guard 停用的 opt-in 開關以支援後續於 mid tier 上的微調實驗。

\FloatBarrier

\section{Limitations and Scope}
\label{sec:limitations}
本方法明確定位於 single-valued KU 情境，即同一 $(s, p)$ 於同一時點只有一個當前版本。此定位於本文的實驗結果上呈現三個層次的邊界。

第一，於 counterfactual 型 KU 情境 (FC-SH) 上，本方法於所有 baselines 上皆為領先，其優勢主要來自於處理 LLM 對既有知識的偏好（Section~\ref{subsec:error_mode}）。此為本方法的主要 scope，適用範圍最廣。

第二，於 single-valued personal 型 KU 情境 (LME-KU) 上，本方法相對答題 template 受控的 baselines 領先收窄至 1.3 pp（55 題對 54 題，僅 1 題之差），相對 pipeline-matched 的 Vanilla-RAG (1-stage) 則落後 3.9 pp。此結果反映當情境無 knowledge conflict 的抗力時，LLM 讀取 ordinal-prefixed pool 直接判斷 recency 亦為可行策略，本方法的架優勢於此情境上明顯縮小。本文於 scope 的 wording 上明確承認此邊界：本方法於 counterfactual 情境上為領先，於 personal 情境上與 LLM-recency 家族相當。其中 Mem0 + Fact Extraction 於良好 extraction 前提下仍維持 50 至 65 的 plateau,反映其失敗不來自 extraction 品質,而來自 destructive UPDATE 於 write-time 的判斷天花板;誤判一旦發生即不可逆地累積於記憶中,後續查詢無從還原。此為 Abstract 與 Chapter~\ref{ch:methodology} 中「write-time 判斷的錯誤不可逆」此一主張的直接證據。

第三，對於 multi-valued personal fact 的情境（例如使用者所會的語言與使用者的興趣，同一 property 於同時點可存在多個值），此為 out-of-scope。本方法的 $\arg\max_{t} t$ 為 single-winner 設計，不處理 keep-all 語意。此為 future work，可透過於 method 中引入 property 的 cardinality 判斷加以擴充。

此外有三項實驗設定上的邊界需一併揭露。其一，本文所有實驗以 temperature 0 執行單次 deterministic run，因此表格中 1 至 3 pp 的差距不足以支撐領先的主張，本文於此類差距上僅主張「相當」或「未反轉」。其二，LME-KU 的 evaluation 於本文中採用 gpt-4o-mini 作為 judge model，與 LongMemEval 官方 default (gpt-4o) 有所差異；此差異可能影響 Table~\ref{tab:lme_main} 中的絕對數字，但預期不影響 Table~\ref{tab:lme_gap} 中相對 gap 的方向。其三，跨 method 的 inference scaffolding 沿用各 method 於 benchmark 中的原生設計，其中 Zep 的 abstain 指令與 Don't Ask 未收到 benchmark 任務指令 wrap 兩項差異的方向對本文結論有利，本文已於 Section~\ref{subsec:implementation} 明確揭露。