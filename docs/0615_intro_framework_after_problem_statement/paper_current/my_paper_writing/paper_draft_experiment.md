\chapter{Experiments}
\label{ch:experiments}

% NOTE: 需於 preamble 加入 \usepackage{placeins} 以支援 \FloatBarrier

\section{Experimental Setup}
\label{sec:setup}

\subsection{Datasets}
\label{subsec:datasets}

本文於兩個 KU benchmark 上評測。第一個為 MemoryAgentBench 中的 FactConsolidation Single-Hop (FC-SH)~\cite{hu2026evaluating},其 context 由 MQuAKE-CF~\cite{zhong2023mquake} 的 counterfactual edits 拼組為編號 fact statement 列表,對應 counterfactual 型 KU 情境 (新事實與 LLM parametric 世界知識衝突)。第二個為 LongMemEval~\cite{wulongmemeval} 中的 knowledge-update subtask (LME-KU),其 context 由多個 session 的自然對話組成,對應 personal 型 KU 情境 (使用者事實隨時間變動,與世界知識無關)。兩者的統計整理於 Table~\ref{tab:datasets}。

\begin{table}[!htb]
\centering
\caption{Datasets summary。has\_pair 為 FC-SH 中真正含 old 與 new 版本的 query 子集,用於 KU 機制歸因分析 (Section~\ref{sec:discussion})。}
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
has\_pair 子集 & 74, 65, 66, 77 & 78 (每 query 一 KU pair) \\
Fact bank 大小 & 455, 2{,}309, 4{,}570, 18{,}321 & 動態 (隨 session 內容變動) \\
\bottomrule
\end{tabularx}
\end{table}

FC-SH 沿用 benchmark 官方 100-query 子集作為主要評測分母,對齊官方 evaluation 慣例。其 context 為 numbered fact statement 而非 dialogue turn,於 chunk size 512 下每 chunk 平均含約 35 個 fact statements。LME-KU 每個 question 對應一個 knowledge-update pair (舊值於早期 session,新值於後期 session),sessions 於 haystack 中依時間排列,系統需自 session 序中辨識最新版本作答。

\subsection{Baselines}
\label{subsec:baselines}

本文將 baselines 依 KU 判斷 timing 分為兩類 (對應 Chapter~\ref{ch:related_work} 的 taxonomy):write-time KU 與 query-time KU;另加一組無記憶架構的 long-context baseline 作為對照。各 baseline 的 KU 判斷機制整理於 Table~\ref{tab:baselines}。

\begin{table}[!htb]
\centering
\caption{Baselines summary。KU judgment timing 對應 Chapter~\ref{ch:related_work} 的 taxonomy。Mem0 + Fact Extraction 為以本方法 write-time 的 fact extraction 取代 mem0 原生抽取、保留其 destructive UPDATE 的對照組合。}
\label{tab:baselines}
\small
\begin{tabularx}{\linewidth}{llX}
\toprule
Method & Timing & 判斷機制 \\
\midrule
Mem0 Vanilla~\cite{chhikara2025mem0} & Write-time coupled & LLM 於單次呼叫輸出 ADD/UPDATE/DELETE/NOOP 並就地執行 \\
Mem0 + Fact Extraction~\cite{chhikara2025mem0} & Write-time coupled & 本方法的 fact extraction 加上 mem0 destructive UPDATE \\
Zep~\cite{rasmussen2025zep} & Write-time decoupled & 內部 LLM 標記 contradicts 或 duplicates,舊 edge 被 invalidated \\
LCA & 無記憶 & 直接以全 context 答題,無 write 與 retrieve pipeline \\
Vanilla-RAG & Query-time LLM & Top-100 檢索,LLM 於 ordinal-prefixed pool 判斷 recency \\
Don't Ask~\cite{reddy2026don} & Query-time LLM & Top-100 檢索,LLM 抽出 candidates,以 $\max(\text{ordinal})$ 選版本 \\
\midrule
Ours (Struct + LLM-Fallback) & Query-time deterministic & $(s, p)$ structural matching 加 $\arg\max_t$,LLM Fallback 於殘餘候選補救 \\
\bottomrule
\end{tabularx}
\end{table}

其中 Mem0 Vanilla 與 Mem0 + Fact Extraction 為本方法的兩個對照組合。前者展示 extraction 與 destructive commit 的聯合弱點;後者於良好 extraction 前提下隔離 destructive commit 的獨立效應。Don't Ask 為與本方法最接近的並行工作,兩者皆將 KU 延後至 query-time 並以確定性方式處理 freshness,但 Don't Ask 的 identity 判斷仍由 LLM extraction 承擔。為公平對比,本文直接引入其公開 repository 的 candidate extraction 與 freshness pick 實作,置於本文相同的實驗環境下執行。LCA 於 context window 受限的 backbone (gemma3 系列) 上僅可對 6k 執行,於 gpt-4o-mini 上完整 4 length。

\subsection{Backbones}
\label{subsec:backbones}

依實際部署情境,本文於三個能力區間 (共 6 個獨立 model) 上評測,對應 introduction 中所述的三個 LLM 使用情境。第一個為 privacy-sensitive on-device 情境~\cite{pham2025slimlm,huang2025middle},以 gemma3 系列 (1B, 4B, 12B, 27B) 涵蓋。第二個為 cost-constrained API 情境~\cite{chenfrugalgpt},以 gpt-4o-mini 作為主要 backbone (完整 4 length 執行)。第三個為 strong tier 情境,以 gpt-5.4-mini 於 6k 上驗證強端 backbone 對 baselines 的補救效果。此外,為驗證 backbone robustness 於不同 model family 皆成立,本文於 Gemma2-9B、Llama3.1-8B、Qwen2.5-7B、Mistral-7B 四個獨立系列的 7-9B open-weight local models 上額外評測。

上述兩組實驗於 backbone 的角色分工上有一項重要區別。Gemma3 系列於 4 個 tier 上皆以該 backbone 承擔整條 pipeline (fact extraction、triple extraction、structural matching、LLM Fallback 與 answer),因此於同一 backbone 內 method 之間的比較公平,但跨 backbone 的絕對值同時受 extraction 品質變化影響。Cross-family 系列於 4 個 model 上則採用 held-fixed gpt-4o-mini 承擔 extraction (fact extraction 與 triple extraction),僅將 query-time 判斷 (structural matching、LLM Fallback 與 answer LLM) 換為該 local model,以隔離 backbone 對 KU 判斷的淨影響,不含 extraction confound。兩組實驗於論述中互補:gemma3 tier 建立「backbone 整體變弱時 baselines 崩塌」的觀察,cross-family 系列則進一步證實「即使 extraction 由強 model 承擔,將 KU 判斷交給 local model 仍導致 baselines 崩塌」,兩者共同支撐 backbone robustness 於 KU 判斷這一子任務上的立論。

\subsection{Metrics}
\label{subsec:metrics}

FC-SH 採用官方 substring exact match (sEM) metric~\cite{hu2026evaluating},其後處理包含 normalization、parse output、以及 alias list 的 max 匹配。主要評測分母為每 length 100 個 query,對齊官方 evaluation 慣例。此 100 個 query 依 ground truth 是否含新舊兩個版本拆分為兩個互斥子集:has\_pair 子集 (74 / 65 / 66 / 77) 為 ground truth 中同時含 gt\_new 與 gt\_old 的 query,為 KU 判斷真正被觸發的部分,僅於 Section~\ref{sec:discussion} 的機制分析與 Section~\ref{sec:ablation} 的 per-qid 對照中使用;其餘為 no\_conflict 子集 (6k 上為 26 題),其 ground truth 僅有單一版本,不涉及版本選擇。LME-KU 採用 LongMemEval 官方的 LLM autoeval~\cite{wulongmemeval},以 gpt-4o-mini-2024-07-18 作為 judge model,主要評測分母為 78 個 KU questions。所有實驗以 temperature 0 執行單次 deterministic run。

\subsection{Implementation Details}
\label{subsec:implementation}

Chunker 使用 chunk size 512;retrieval 使用 vector search 取回 top-100 候選,embedding model 為 text-embedding-3-small (1536 維度)。Zep 依其官方推薦使用 top-10 檢索。所有 backbone 於推論時 temperature 設為 0。Extraction (fact extraction 與 triple extraction) 於 backbone extension 實驗中 held-fixed 為 gpt-4o-mini,以隔離 KU 判斷的淨影響;於 gemma3 tier 則使用該 backbone 自身作為 extraction model,以誠實反映「弱 backbone 整條 pipeline」的實際部署情境。

\FloatBarrier

\section{Main Results on FC-SH}
\label{sec:main_results}

本節於 counterfactual 型 KU 情境 (FC-SH) 上以 gpt-4o-mini 為 backbone,涵蓋 4 個 context length (6k, 32k, 64k, 262k),對本方法與所有 baselines 進行整體評測。此節建立本方法於主 backbone 上的 outright 領先,後續章節則依此展開 backbone robustness 與 cross-family generality 的分析。

\subsection{Overall Accuracy}
\label{subsec:main_overall}

Table~\ref{tab:main_fcsh} 呈現本方法與所有 baselines 於 FC-SH 4 length 上的 overall sEM。

\begin{table}[!htb]
\centering
\caption{FC-SH overall sEM (\%) 於 gpt-4o-mini backbone,4 length $\times$ 9 method。Bold 表示該 length 上的最佳結果 (含並列);本方法的 main configuration 以粗體 method 名標示。AVG 欄為 4 length 的平均。}
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

\subsection{Length Scaling}
\label{subsec:main_length}

Figure~\ref{fig:length_scaling} 以 line plot 呈現 Table~\ref{tab:main_fcsh} 中 6 個代表 method 隨 context length 的變化。

\figt{0.7\columnwidth}
{figs/exp_length_scaling_gpt4omini_4length}
{FC-SH overall sEM 隨 context length 的變化,gpt-4o-mini backbone。本方法於 4 length 上保持 91 到 94 之間的 flat 表現,是唯一於全 length 上無 $\geq 10$ pp 掉幅的方法。Zep 於 262k 上崩至 29,LCA 隨 context length 單調下降,Vanilla-RAG 於 32k 呈現 non-monotonic dip,Don't Ask 則隨 context length 呈現 mild 上升。}
{fig:length_scaling}

\subsection{Observations}
\label{subsec:main_obs}

Table~\ref{tab:main_fcsh} 與 Figure~\ref{fig:length_scaling} 共同呈現以下五項觀察。

第一,本方法為唯一於 4 length 全部維持 flat 高位的方法。overall sEM 於 91 到 94 之間 (Δ 6k 到 262k 為 $-3$ pp),其他所有 method 至少於一個 length 上出現 $\geq 10$ pp 的掉幅。此觀察直接回應 Chapter~\ref{ch:introduction} 所描述的問題背景:記憶隨 context 累積而保留同一事實的多個版本,KU 的挑戰因此隨 context 增長而加劇;本方法於 context 自 6k 累積至 262k 的過程中,KU 表現不隨之退化。

第二,write-time family 於 length 上呈現三種明顯不同的 pattern。Mem0 Vanilla 於全 length 皆維持於低點 (16 到 28),此為 extraction 崩壞造成的 recall 底部,尚未觸及 KU 判斷的實際挑戰。Mem0 + Fact Extraction 於良好 extraction 前提下仍維持 50 到 65 的 plateau,反映 destructive UPDATE 於 write-time 的判斷天花板;即使 extraction 已由本方法的 fact extraction 忠實承擔,mem0 於 UPDATE 判斷上的錯誤仍不可逆地累積於記憶中。Zep 於 6k 到 64k 上表現相對穩定 (76 到 82),但於 262k 崩至 29;此崩塌的機制於 Section~\ref{sec:discussion} 中進一步分析。

第三,long-context 對照與 query-time family 呈現三種不同的長度行為。LCA 隨 context length 單調下降 (88 到 43),反映 long-context reader 於 context 累積下的能力上限。Vanilla-RAG 於 32k 上呈現 non-monotonic dip (93, 77, 85, 81),此模式的機制於 Section~\ref{sec:discussion} 中以 per-qid 分析揭露為 LLM 於判斷 recency 時回退世界先驗的直接後果。Don't Ask 則為唯一於長 context 上表現更佳的 baseline (80 到 86 至 88),其機制亦於 Section~\ref{sec:discussion} 中分析。

第四,本方法內部兩個 identity 機制於長度上呈現互補分工。Ours (LLM-Identity-Only) 於短 context (6k) 上表現最佳 (97,full method 為 94);至長 context (262k),兩者 overall sEM 相近 (LLM-Identity-Only 87 對 Struct-Only 86),但 per-qid 分析顯示 structural matching 於此 length 上有 LLM 判斷無法覆蓋的獨家貢獻 (獨家救回 5 題)。此互補性與 full method 的組成邏輯於 Section~\ref{sec:ablation} 進一步展開。

第五,依 4 length 的平均排序,full method (92.5) 為全部 method 最高,本方法的兩個 ablation (91.5 與 89.0) 次之,其後為 Don't Ask (85.0) 與 Vanilla-RAG (84.0);write-time family 中最高者為 Zep (66.8),與 long-context 對照 LCA (67.5) 同處明顯較低的區間,Mem0 + Fact Extraction 於任一 length 皆未超過 65。此排序建立本方法於主 backbone 上相對於既有方法的定量優勢。

\FloatBarrier

\section{Robustness across Backbone Capabilities}
\label{sec:backbone_robustness}

本節驗證本方法的 KU 表現不隨 backbone 能力變動而退化,而 baselines 於 backbone 變弱時 KU 表現顯著崩塌。此對比為本文最有 discriminating power 的實驗,直接對應 Chapter~\ref{ch:methodology} 的核心主張:當 KU 判斷由 LLM 移至 deterministic structural matching 後,其表現由事實的結構所決定,而非由 backbone 的判斷能力所決定。實驗涵蓋 6 個 backbone,以 gemma3 系列 (1B, 4B, 12B, 27B) 建立弱端 spectrum,以 gpt-4o-mini 建立主 backbone reference,以 gpt-5.4-mini 建立強端 reference。

\subsection{Backbone Spectrum}
\label{subsec:exp_backbone_spectrum}

Figure~\ref{fig:exp_backbone_spectrum} 以 line plot 呈現 5 個代表 method 於 6 tier backbone 上的 FC-SH 6k overall sEM。橫軸自左至右為 backbone 能力遞增順序,前 4 tier 為 gemma3 系列 (per-backbone extraction),後 2 tier 為 gpt 系列 (held-fixed gpt-4o-mini extraction)。

\figt{0.7\columnwidth}
{figs/exp_backbone_spectrum}
{FC-SH 6k overall sEM 於 6 tier backbone 上的變化。橫軸自左至右為 backbone 能力遞增順序 (gemma3-1B 至 gpt-5.4-mini)。本方法於全 backbone 上皆維持高位並為 outright leader;baselines 於弱 backbone 上崩塌 (gemma3-1B 上皆不高於 30),於強 backbone 上呈現 gap 收斂但未反轉。左側灰色區塊標示 gemma3 tier 為 per-backbone extraction,右側為 gpt tier 的 held-fixed extraction。}
{fig:exp_backbone_spectrum}

Figure~\ref{fig:exp_backbone_spectrum} 為本節的視覺核心,其傳達的訊息可歸納為三點。第一,本方法於全 backbone 上皆為 outright leader,line 恆為最上位。第二,baselines 隨 backbone 變弱而顯著崩塌,於 gemma3-1B 上皆不高於 30,gap 於此區間張至最大。第三,baselines 於強 backbone 上呈現 gap 收斂,但於 gpt-5.4-mini 上本方法仍為 outright leader (99 對 second-best 98)。以下兩個子節分別展開 gemma3 tier 與 gpt tier 的具體數字。

\subsection{Gemma3 Spectrum}
\label{subsec:gemma3}

Table~\ref{tab:gemma3} 呈現本方法與所有 baselines 於 gemma3 4 tier 上的 FC-SH 6k overall sEM。此 tier 為 per-backbone extraction,即每個 backbone 以其自身承擔整條 pipeline (包含 fact extraction、triple extraction、structural matching、LLM Fallback 與 answer)。此設定反映「弱 backbone 整條 pipeline 部署於 on-device 隱私敏感情境」的實際使用情境。

\begin{table}[!htb]
\centering
\caption{FC-SH 6k overall sEM (\%) 於 gemma3 4 tier 上,per-backbone extraction。Bold 表示該 backbone 上的最佳結果 (含並列);本方法的 main configuration 以粗體 method 名標示。Mem0 Vanilla 於 gemma3-1B 未執行 (「—」):同 backbone 上 Mem0 + Fact Extraction (其 fact extraction 已 held-fixed 為 gpt-4o-mini) 已崩塌至 5,Vanilla 需同時將 fact extraction 與 destructive UPDATE 皆於 gemma3-1B 上執行,較 Mem0 + Fact Extraction 多一層 extraction 崩壞,結果保證不高於前者,補跑不提供新資訊。}
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
\bottomrule
\end{tabular}
\end{table}

Table~\ref{tab:gemma3} 呈現以下三項觀察。第一,本方法於全 4 tier 上相對所有 baselines 皆為 outright leader:main configuration 為 44, 79, 99, 99,於每個 tier 皆高於該 tier 最佳的 baseline;於 1B 上本方法內部以 Struct-Only (52) 最佳,main configuration 因 LLM Fallback 於弱 backbone 上的負貢獻而略低,此現象於 Section~\ref{sec:ablation} 以 capability gate 解釋。write-time baselines 於 1B 與 4B 上崩塌至 5 到 32,反映 destructive UPDATE 於 write-time 需要 LLM 承擔跨筆判斷,弱 backbone 於此任務上無法產出可靠的判斷結果,錯誤的 UPDATE 直接於記憶中造成不可逆的 loss。第二,Don't Ask 於 1B 上崩至 2,反映其 LLM candidate extraction 於弱 backbone 上無法產出合格的候選集,freshness pick 於此情境下已無有效輸入。第三,本方法內部的 LLM Fallback 於此弱 backbone 情境下呈現 capability-gated 行為,於 1B 上反而害本方法 8 pp (Struct-Only 52 對 full 44),於 4B 至 12B 上為 neutral,於 27B 上為 +2 pp。此觀察反向確立 structural matching 為 backbone-universal 的核心 workhorse,而 LLM Fallback 為僅於強 backbone 上有效的 capability-gated 補救。LLM Fallback 於 backbone 上的 capability-gate 分佈於 Section~\ref{sec:ablation} 中進一步展開。

\subsection{OpenAI Mini-tier}
\label{subsec:openai_tier}

Table~\ref{tab:openai_tier} 呈現本方法與所有 baselines 於 OpenAI mini-tier 兩個 backbone (gpt-4o-mini 為主 backbone,gpt-5.4-mini 為強端 reference) 上的 FC-SH 6k overall sEM。此 tier 為 held-fixed gpt-4o-mini extraction,即 extraction 於兩個 backbone 上皆固定使用 gpt-4o-mini,僅將 query-time 判斷 (structural matching、LLM Fallback 與 answer) 換為該 backbone。此設定隔離 backbone 對 KU 判斷的淨影響,不含 extraction confound。

\begin{table}[!htb]
\centering
\caption{FC-SH 6k overall sEM (\%) 於 OpenAI mini-tier 上,held-fixed gpt-4o-mini extraction。$\Delta$ 為 gpt-5.4-mini 相對 gpt-4o-mini 的變化。}
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

Table~\ref{tab:openai_tier} 呈現以下三項觀察。第一,本方法於兩個 backbone 上皆為 outright leader,gpt-5.4-mini 上達 99 的 near-saturation 表現。第二,baselines 於強 backbone 上呈現顯著 gap 收斂,其收斂由「地板」抬升所驅動 (Mem0 + Fact Extraction 上升 18 pp,Don't Ask 上升 16 pp,Zep 上升 11 pp),此模式反向支撐本文對「baselines 依賴 LLM 判斷 KU」的定位:當 LLM 能力增強時,LLM 承擔的判斷部分自然受益。第三,即使於 gpt-5.4-mini 上 gap 收斂至 spread 29 pp (相較 gpt-4o-mini 的 42 pp),本方法仍保有 +1 pp 的 outright 領先 (99 對 second-best Vanilla-RAG 98)。此觀察建立「backbone 增強能改善 baselines,但無法將其表現推至本方法之上」的定量結論。

\subsection{Summary}
\label{subsec:backbone_summary}

上述兩個 tier 的實驗結果共同支撐本文的核心主張。本方法的 KU 表現不隨 backbone 能力變動而退化,於 gemma3-1B 到 gpt-5.4-mini 的整個 6 tier 上,本方法皆為 outright leader。baselines 於弱 backbone 上顯著崩塌,於強 backbone 上呈現 gap 收斂但未反轉;此模式於 Figure~\ref{fig:exp_backbone_spectrum} 中一目了然,直接驗證 Chapter~\ref{ch:methodology} 的核心主張:當 KU 判斷由 LLM 移至 deterministic structural matching 後,其表現由事實的結構所決定,而非由 backbone 的判斷能力所決定。

\FloatBarrier

\section{Generality across Backbone Families}
\label{sec:cross_family}

Section~\ref{sec:backbone_robustness} 於 gemma3 系列上建立了 backbone robustness 的 within-family 觀察。本節進一步驗證此觀察不是 gemma family 特有的現象,而是於不同 backbone family 上普遍成立。實驗於 4 個獨立系列的 7-9B open-weight local models (Gemma2-9B, Llama3.1-8B, Qwen2.5-7B, Mistral-7B) 上執行,採用 held-fixed gpt-4o-mini extraction 設定,以隔離 backbone 對 KU 判斷的淨影響,不含 extraction confound。此設定與 Section~\ref{subsec:gemma3} 的 gemma3 tier 互補:後者反映「弱 backbone 整條 pipeline 部署」的實際情境,前者隔離「KU 判斷交給 local model」的淨影響,兩者共同建立 backbone robustness 的立論。

\subsection{Cross-family Results}
\label{subsec:cross_family_results}

Table~\ref{tab:cross_family} 呈現本方法與 baselines 於 4 個獨立系列上的 FC-SH 6k overall sEM。

\begin{table}[!htb]
\centering
\caption{FC-SH 6k overall sEM (\%) 於 4 個 open-weight backbone family 上,held-fixed gpt-4o-mini extraction。Bold 表示該 backbone 上的最佳結果 (含並列);本方法的 main configuration 以粗體 method 名標示。}
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

\subsection{Observations}
\label{subsec:cross_family_obs}

Table~\ref{tab:cross_family} 呈現以下四項觀察。

第一,本方法於 4 個系列上皆為 outright leader,overall sEM 於 66 至 91 之間;baselines 於 4 個系列上皆顯著低於本方法,Mem0 + Fact Extraction 於全系列崩至 8 至 27,Vanilla-RAG 於 3 個系列崩至 26 至 38。此模式跨系列一致,驗證 Section~\ref{sec:backbone_robustness} 觀察到的 backbone robustness 於不同 backbone family 上普遍成立,不是 gemma family 特有的現象。

第二,Ours (Struct-Only) 於 Gemma2-9B、Llama3.1-8B 與 Mistral-7B 三個系列上與 full method 幾乎齊平 (差距為 $-1$, 0, $-2$ pp),於 Qwen2.5-7B 上則低 8 pp。此模式反映於 mid-size (7-9B) local model 上,structural matching 已為主要 workhorse,LLM Fallback 的邊際貢獻於此區間為 0 至 8 pp。此觀察與 Section~\ref{sec:backbone_robustness} 中 LLM Fallback capability gate 的分析一致:LLM Fallback 的貢獻於 backbone 能力增強時方顯著。

第三,Vanilla-RAG 於 3 個系列 (Qwen2.5-7B 27, Mistral-7B 26, Gemma2-9B 38) 上崩塌,Llama3.1-8B 上為例外 (70)。此模式反映 LLM 於 flat ordinal pool 上判斷 recency 為跨系列的共通弱點,不是特定家族現象;Llama3.1-8B 的相對佳表現可能與其於 rule-following 上的能力較強有關。

第四,由於此節採用 held-fixed gpt-4o-mini extraction,baselines 於此設定下的崩塌無法歸因於 extraction 品質下降。此模式反向確立主要 gap 來自於 KU 判斷本身 (Vanilla-RAG 的 LLM recency judge、Mem0 + Fact Extraction 的 write-time destructive UPDATE),而非 extraction。此觀察與 Section~\ref{sec:backbone_robustness} 中 gemma3 tier 的「整條 pipeline 交給弱 backbone」情境互補,共同建立 backbone robustness 於 KU 判斷這一子任務上的立論。

\FloatBarrier

\section{Generalization to LongMemEval-KU}
\label{sec:lme_ku}

上述章節於 counterfactual 型 KU 情境 (FC-SH) 上建立本方法的表現。本節進一步於 personal 型 KU 情境 (LongMemEval-KU) 上驗證本方法的適用範圍。此情境中的事實隨使用者狀態變動 (例如居住城市、職業),與 LLM 的 parametric knowledge 無直接衝突,可作為對照條件檢視本方法的優勢來源。

\subsection{Overall Accuracy}
\label{subsec:lme_overall}

Table~\ref{tab:lme_main} 呈現本方法與 baselines 於 LME-KU 上的 accuracy,以 gpt-4o-mini 為 backbone,LongMemEval 官方 LLM autoeval 為 judge。

\begin{table}[!htb]
\centering
\caption{LME-KU accuracy (\%) 於 gpt-4o-mini backbone,N = 78。Bold 表示最佳結果。}
\label{tab:lme_main}
\small
\begin{tabular}{lcc}
\toprule
Method & correct / 78 & acc \\
\midrule
Mem0 Vanilla & 53 / 78 & 67.9 \\
Mem0 + Fact Extraction & 47 / 78 & 60.3 \\
Vanilla-RAG (2-stage) & 54 / 78 & 69.2 \\
\textbf{Vanilla-RAG (1-stage)} & \textbf{58 / 78} & \textbf{74.4} \\
Ours (Struct + LLM-Fallback) & 55 / 78 & 70.5 \\
\bottomrule
\end{tabular}
\end{table}

Zep 於 LME-KU 上因其 free plan 的 per-graph 128k token 上限與 LME context 平均 127.7k 相撞而未能完整執行,列為 caveat 未進入 Table~\ref{tab:lme_main}。Don't Ask 依其原始設計依賴 dataset 提供的 numbered fact bank 與 global serial ordering,此為 FC-SH 原生設計,LME-KU 為 per-session 對話結構不符合此假設,強行 adapter 需自建 per-session bank 與自定 serial 語意,已偏離其作者原論文 scope,亦列為 caveat 未進入 Table~\ref{tab:lme_main}。

\subsection{Personal vs Counterfactual Gap}
\label{subsec:lme_gap}

本方法於 LME-KU 上領先 Mem0 Vanilla、Mem0 + Fact Extraction、Vanilla-RAG (2-stage) 三個 baseline,但輸給 Vanilla-RAG (1-stage) 3.9 pp。此結果與 FC-SH 上的 outright 領先形成明顯對比。Table~\ref{tab:lme_gap} 對照本方法於兩個情境上相對 baselines 的 gap。

\begin{table}[!htb]
\centering
\caption{本方法相對 baselines 的 gap 於兩個 KU 情境上的對照。負值表示本方法輸給該 baseline。}
\label{tab:lme_gap}
\small
\begin{tabular}{lcc}
\toprule
對照 baseline & FC-SH 6k (counterfactual) & LME-KU (personal) \\
\midrule
vs. Mem0 Vanilla & +78 pp (94 vs. 16) & +2.6 pp (70.5 vs. 67.9) \\
vs. Mem0 + Fact Extraction & +42 pp (94 vs. 52) & +10.2 pp (70.5 vs. 60.3) \\
vs. Vanilla-RAG (1-stage) & +1 pp (94 vs. 93) & $-$3.9 pp (70.5 vs. 74.4) \\
\bottomrule
\end{tabular}
\end{table}

\subsection{Observations}
\label{subsec:lme_obs}

Table~\ref{tab:lme_main} 與 Table~\ref{tab:lme_gap} 呈現以下三項觀察。

第一,本方法於 LME-KU 上的相對 gap 相較於 FC-SH 明顯縮小 (相對 Mem0 Vanilla 從 +78 pp 縮至 +2.6 pp,相對 Mem0 + Fact Extraction 從 +42 pp 縮至 +10.2 pp)。此模式反向支撐 Chapter~\ref{ch:introduction} 中「counterfactual 型 KU 上巨大 gap 主要來自處理 LLM parametric bias」的定位:當情境轉為 personal 型 (事實與 LLM parametric knowledge 無直接衝突) 時,baselines 於「LLM 傾向自身知識」這一失敗模式上的暴露程度顯著降低,gap 因此收窄。

第二,Vanilla-RAG (1-stage) 於 LME-KU 上略勝本方法 3.9 pp,此結果的機制推論如下。personal 型 KU 事實不與 LLM parametric knowledge 衝突,LLM 於讀取 ordinal-prefixed pool 判斷 recency 時沒有 world-prior 的抗力,可直接依 ordinal 選擇最新版本,即為正確答案。此模式與 Section~\ref{sec:discussion} 中 Vanilla-RAG 於 FC-SH 上失敗模式的分析一致 (失敗 95 至 100 percent 為回退世界先驗),此路徑於 LME-KU 上不存在。

第三,Mem0 + Fact Extraction 於 LME-KU 上表現反轉,低於 Mem0 Vanilla 7.6 pp。此模式的機制推論如下。LME-KU 對話事實密度較低,本方法的 fact extraction 抽出更多且更精細的事實,mem0 destructive UPDATE 因此有更多機會產生 missing ADD 或 cross-item confusion,反致 damage 大於 mem0 native extraction。此觀察指出 Mem0 + Fact Extraction 於跨 benchmark 論述上不宜作為主要 baseline (其 fact extraction 貢獻於不同 dataset 上方向不一致),本文於跨 benchmark 論述中採用 Mem0 Vanilla 為 baseline 基準。

上述觀察共同定位本方法的適用範圍。本方法於 counterfactual 型 KU 情境上為 outright leader,gap 主要來自於處理 LLM parametric bias;於 personal 型 KU 情境上,當 LLM 於判斷 recency 時沒有 world-prior 抗力時,LLM-based baselines 亦可達到相當表現。此定位於 Section~\ref{sec:discussion} 的 limitations 段落中進一步展開。

\FloatBarrier

\section{Ablation Study}
\label{sec:ablation}

本節分別量化本方法兩個核心 component (structural matching 與 LLM Fallback) 各自的貢獻。Section~\ref{subsec:ablation_components} 於 gpt-4o-mini backbone 上以 4 length 拆解兩個 component 於 context length 上的分工;Section~\ref{subsec:ablation_backbone} 於 backbone 光譜上驗證 LLM Fallback 的貢獻隨 backbone 能力而變化的 capability-gate 特性。

\subsection{Structural Matching vs LLM Fallback}
\label{subsec:ablation_components}

Table~\ref{tab:ablation_components} 呈現本方法內部三個 configuration (Struct-Only, LLM-Identity-Only, 以及 full method) 於 FC-SH 4 length 上的 overall sEM。Struct-Only 保留 structural matching 與 $\arg\max_t$,關閉 LLM Fallback;LLM-Identity-Only 關閉 structural matching,將所有候選送入 LLM 判斷 identity。

\begin{table}[!htb]
\centering
\caption{FC-SH overall sEM (\%) 於 gpt-4o-mini backbone,本方法內部 configuration 的 ablation。Bold 表示該 length 上的最佳結果 (含並列)。}
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

Table~\ref{tab:ablation_components} 呈現兩項觀察。第一,兩個 identity 機制於 context length 上呈現互補分工。LLM-Identity-Only 於短 context (6k) 上明顯優於 Struct-Only (97 對 91),反映此區間內候選集規模較小,LLM 於單次呼叫中足以涵蓋所有可能的 identity pair。至長 context (262k),兩者的 overall sEM 已相近 (87 對 86),且 per-qid union 分析顯示互補方向反轉:6k 上 structural matching 相對 LLM 判斷無獨家貢獻,262k 上 structural matching 獨家救回 5 題,為 LLM 判斷所無法覆蓋。此模式反映長 context 下 top-100 pool 中的 distractor 增多,LLM 於單次判斷中的 identity grouping 於大 pool 上失去穩定性,而 structural matching 的 $(s, p)$ 配對為 exact match,不受 pool 規模影響。第二,full method 為三個 configuration 中 4 length 平均最高者 (92.5),且為唯一於 4 length 皆維持 91 以上者;LLM Fallback 相對 Struct-Only 的淨貢獻 (overall sEM 差,可由 Table~\ref{tab:ablation_components} 直接驗算) 於 4 length 上為 +3, +4, +2, +5,長 context 上邊際效益最大。若改以 has\_pair 子集的 per-qid rescue 淨值計算,則為 +2, +4, +2, +5;6k 上兩者的 1 pp 差異來自 no\_conflict 子集中的 1 題。此互補分工是 full method 同時保留兩個 component 的定量理由。

\subsection{Capability Gate of LLM Fallback across Backbones}
\label{subsec:ablation_backbone}

Table~\ref{tab:p3_capability_gate} 呈現 LLM Fallback 相對 Struct-Only 於不同 backbone 上的淨貢獻 $\Delta$。正值表示 LLM Fallback 於該 backbone 上為 net-positive,負值表示 LLM Fallback 反而害本方法。

\begin{table}[!htb]
\centering
\caption{LLM Fallback 於 backbone 光譜上的淨貢獻,FC-SH 6k overall sEM。$\Delta$ = Ours (Struct + LLM-Fallback) $-$ Ours (Struct-Only)。正值表示 LLM Fallback 為 net-positive。gemma3 四列為 per-backbone extraction,gpt-4o-mini 一列為 held-fixed extraction (Section~\ref{subsec:backbones});$\Delta$ 於同一 backbone 內兩個 configuration 之間計算,extraction 已於該 backbone 內受控,但跨列比較時 extraction regime 的差異仍應納入考量。}
\label{tab:p3_capability_gate}
\small
\begin{tabular}{lccc}
\toprule
Backbone & Struct-Only & Struct + LLM-Fallback & $\Delta$ \\
\midrule
gemma3-1B & 52 & 44 & $-8$ \\
gemma3-4B & 79 & 79 & 0 \\
gemma3-12B & 99 & 99 & 0 \\
gemma3-27B & 97 & 99 & $+2$ \\
gpt-4o-mini & 91 & 94 & $+3$ \\
\bottomrule
\end{tabular}
\end{table}

Table~\ref{tab:p3_capability_gate} 呈現 LLM Fallback 的貢獻於 backbone 光譜上呈明顯的 capability-gate 特性。於最弱端 (gemma3-1B) LLM Fallback 反而害本方法 8 pp,反映弱 backbone 於 identity clustering 這一 LLM 任務上無法產出可靠判斷,LLM Fallback 於此區間內傾向於錯誤合併不同事實 (over-merge),污染了 Struct-Only 已經正確處理的候選集。於中段 (4B, 12B) LLM Fallback 為 neutral,structural matching 已涵蓋主要 identity 情境。於強端 (27B, gpt-4o-mini) LLM Fallback 為 net-positive +2 至 +3,能可靠承擔 structural matching 無法歸群的 identity 判斷。此模式兌現 Chapter~\ref{ch:methodology} 中對 LLM Fallback 「僅為 structural matching 無法歸群時的補救」的定位:LLM Fallback 是隨 backbone 能力增強而邊際效益上升的 capability-gated add-on,structural matching 才是 backbone-universal 的核心 workhorse。此定位進一步強化 Section~\ref{sec:backbone_robustness} 中「本方法的 backbone robustness 由 structural matching 承擔」的立論。

\FloatBarrier

\section{Discussion}
\label{sec:discussion}

本節以三段機制分析與一節 scope 界定支撐前述章節的實驗結果。Section~\ref{subsec:error_mode} 以 per-qid error mode 逐題揭露 baselines 於 KU 失敗時的共通模式;Section~\ref{subsec:p3_rate} 量化 LLM Fallback 於 pipeline 中實際承擔的比例,兌現 Chapter~\ref{ch:methodology} 對「LLM 僅為補救」的定位;Section~\ref{subsec:zep_262k} 補充 Zep 於 262k 崩塌的機制分析,為 Section~\ref{sec:main_results} 中的觀察提供 mechanism-level 的解釋;Section~\ref{subsec:limitations} 界定本方法的適用範圍與其限制。

\subsection{Per-qid Error Mode: Baselines Fall Back to World Prior}
\label{subsec:error_mode}

於 FC-SH 上以 per-qid 逐題分析 baselines 於 has\_pair 子集上的失敗案例,揭露一個一致的模式:baselines 於 KU 失敗時,answer LLM 回退到世界先驗的舊值 (即 counterfactual scope 下的 gt\_OLD)。此模式於三個代表 baseline 上皆成立,但失敗發生的 pipeline 位置不同。

Ours (Struct-Only) 於 6k 與 32k 上的 has\_pair 失敗 100 percent 為「答成 gt\_OLD」,64k 與 262k 上分別為 88 percent 與 79 percent。其失敗根因單一,為 $(s, p)$ canonicalization miss:new 與 old 版本因 predicate 的 stem 對 full form 差異或 subject 的細微變體被分入不同結構群,$\arg\max_t$ 於群內無從比對兩個版本,candidate pool 因此同時保留兩個版本;於此情境下 answer LLM 於缺乏 recency 指引時,回退到語意上熟悉的世界先驗值。此正是 LLM Fallback 存在的理由,亦即於 structural matching 無法歸群時補上 identity 判斷。

Don't Ask 於 6k 與 64k 上的 has\_pair 失敗 100 percent 為 LLM 抽出的候選集僅含一個版本 (n\_candidates 為 1)。此候選為世界先驗的舊值 (即 gt\_OLD),counterfactual 的新版本雖然存在於 top-100 檢索範圍內,但於 LLM extraction 階段被漏掉。此模式反映 Don't Ask 的失敗不在於 freshness 選擇本身 (max 於單一候選 trivially 正確),而在於上游 LLM candidate extraction 的世界先驗洩漏。此觀察為本文與 Don't Ask 的具體 quantitative 差異來源:兩者皆將 freshness 交給確定性操作,但 Don't Ask 的 identity 仍由 LLM extraction 承擔,而本方法將 identity 亦結構化為 $(s, p)$ 配對,免疫此類洩漏。

Vanilla-RAG 於 4 length 上的 has\_pair 失敗 95 至 100 percent 為「答成 gt\_OLD」。其失敗根因為 LLM 於 flat ordinal pool 上判斷 recency 時,傾向於回退到語意熟悉的世界先驗值,而非嚴格 follow ordinal rule。此模式於 32k 最為嚴重 (65 中錯 23),對應 Table~\ref{tab:main_fcsh} 中 Vanilla-RAG 的 non-monotonic dip。此觀察直接支撐 Chapter~\ref{ch:methodology} 中「freshness 必須為 deterministic 操作,不可交由 LLM 承擔」的核心設計決策。

上述三種失敗模式共同支撐 Chapter~\ref{ch:introduction} 中的 causal claim:baselines 的錯誤主要來自 LLM 於 counterfactual 情境下 parametric bias 的偏好。三個 baseline 各自於 pipeline 的不同位置洩漏此 bias (Ours Struct-Only 於 structural 碎裂、Don't Ask 於上游 extraction、Vanilla-RAG 於下游 recency judge),而本方法以「忠實寫入所有版本 + 結構化 identity + $\arg\max_t$ 決定版本 + LLM Fallback 補救少數殘餘」逐一 dodge 各層洩漏。

\subsection{LLM Fallback Trigger Rate and Rescue Rate}
\label{subsec:p3_rate}

為量化 LLM Fallback 於 pipeline 中實際承擔的比例,本文以 offline $(s, p)$-merge proxy 對每個 has\_pair query 進行三分。此 proxy 以 P2 於該 length 產出的 triple bank 為輸入,對每個 query 找 fact bank 中 object 欄位比中 gt\_new 的 triple 集合與比中 gt\_old 的 triple 集合,並依 $(s, p)$ 的 L0/L1/L2 normalization 判定兩者是否落於同一結構群。gt\_new 與 gt\_old 落於同一結構群者,由 structural matching 於 $\arg\max_t$ 直接決定,列為 structural pool;落於不同群者,由 LLM Fallback 補救判斷 identity,列為 dynamic pool;fact bank 內無任何 triple 之 object 欄位比中 gt\_new 者,列為 new missing。此第三個 bucket 為 proxy 的分類限制而非 pipeline 的 routing bucket:pipeline 於 phase 2 仍照常對這些 query 執行檢索與 $(s, p)$ routing,triple 為 null 或 singleton 的候選會照常進入 dynamic pool 由 LLM Fallback 補救;new missing 標記的是 proxy 因無 gt\_new-side triple 可對照而無從離線分類的 query,此類 query 於下游答題亦通常失敗,因 answer LLM 於 retrieved pool 內找不到 counterfactual 新值。Table~\ref{tab:p3_rate} 呈現此三分於 4 length 上的結果。

\begin{table}[!htb]
\centering
\caption{LLM Fallback 於 FC-SH 4 length 上的觸發率與 in-bucket accuracy。Structural pool、dynamic pool 與 new missing 為 has\_pair query 依 $(s, p)$-merge proxy 拆分的三個子集,三者相加為 100 percent;new missing 為 proxy 於 fact bank 內找不到任何 object 欄位比中 gt\_new 的 triple 之 query,此 bucket 為 proxy 的分類限制而非 pipeline 的 routing bucket (詳正文)。In-bucket accuracy 為 LLM Fallback 於 dynamic pool 內的正確率。262k row 採用 full method 對比 Struct-Only 的 diff-based ground truth,因 proxy 於此 length 失去解析力:P2 triple extractor 於 262k 的大 fact bank 上,同一 fact 於多 chunk 重複出現,較常穩定產出同一 canonical $(s, p)$,proxy 於 gt\_new 與 gt\_old 兩側 triple 都能配到 $(s, p)$ 完全一致者的機率上升,誤標為 structural pool 佔比,故此 length 改由 rescue 與 regress 逐題 diff 直接計數。}
\label{tab:p3_rate}
\small
\begin{tabular}{lcccc}
\toprule
Length & Structural pool & Dynamic pool (LLM Fallback) & New missing & In-bucket accuracy \\
\midrule
6k & 81 \% & 14 \% & 5 \% & 90 \% \\
32k & 77 \% & 22 \% & 1 \% & 79 \% \\
64k & 68 \% & 32 \% & 0 \% & 81 \% \\
262k & 88 \% & 12 \% (diff-based) & 0 \% & 78 \% \\
\bottomrule
\end{tabular}
\end{table}

Table~\ref{tab:p3_rate} 呈現兩項觀察。第一,structural pool 於 4 length 上皆佔 68 percent 以上,dynamic pool 為 12 至 32 percent,new missing 至多 5 percent。此模式兌現 Chapter~\ref{ch:methodology} 中「LLM Fallback 僅於少數案例介入」的定位:LLM Fallback 於任一 length 上皆只承擔少數 identity 判斷,大多數判斷由 structural matching 與 $\arg\max_t$ 於 deterministic 路徑上完成。第二,LLM Fallback 於 dynamic pool 內的 accuracy 穩定於 78 至 90 percent,反映其於觸發時能可靠承擔 identity 判斷,不下拉整體 pipeline 品質。此兩項觀察共同為 Section~\ref{subsec:ablation_components} 中兩個 identity 機制的互補分工提供 mechanism 基礎:structural matching 為 backbone-universal 的 workhorse,LLM Fallback 為 capability-gated 的窄任務補救,兩者於 pipeline 中的比例分工由結構決定,非人為調控。

\subsection{Zep at 262k: Retrieval Miss}
\label{subsec:zep_262k}

Table~\ref{tab:main_fcsh} 中 Zep 於 262k 上崩塌至 29 percent,較 64k 的 76 percent 有顯著退化。Section~\ref{sec:main_results} 中將此崩塌列為 write-time family 的長 context 行為之一,本節進一步以 mechanism-level 的分析揭露其崩塌的根因。

以 Zep 於 262k 上的 top-10 retrieval 與 GT 進行 bi-temporal 分類,結果顯示 262k 的 has\_pair 中有 82 percent 屬於 NotBothExtracted,即 top-10 retrieval 未同時抓到 old 與 new 兩個版本。於此情境下,answer LLM 於 candidate pool 內根本沒有兩個版本可資比較,只能依世界先驗猜測,has\_pair sEM 因此僅為 16 percent (12/77,採 official substring exact match,對齊 Table~\ref{tab:main_fcsh} 之主 metric)。相對地,32k 與 64k 上的 NotBothExtracted 分別僅為 5 percent (3/65) 與 2 percent (1/66),不構成主要失敗來源。此對照確立 262k 崩塌的主因為 query-time retrieval miss,而非 write-time 的 contradiction 判斷不足。

Zep 於 262k 上的 write-time invalidation coverage 為 6.3 percent,較 6k 的 21.9 percent 大幅降低,反映其於大圖上的 contradiction 觸發率確實下降。然而,單就此 coverage 數字無法解釋 262k 上的整體崩塌:64k 上 coverage 已降至 9.7 percent,overall sEM 仍達 76,可見 coverage 下降並非崩塌的充分條件,此指標僅為次要因素。此外,將 Zep 的 retrieval 由 top-10 擴至 top-50 於 262k 上仍為 28.3 percent (46 query 樣本),與 top-10 統計等價,排除 top-$K$ 為根因的可能。

上述分析共同揭露:Zep 於 262k 上的崩塌為 write-time invalidation coverage 下降與 query-time retrieval miss 兩層問題的疊加,而兩層問題皆為「大圖規模下,semantic search 對特定 target edge 難以精準檢索」此一機制的兩個表徵,並非彼此獨立的缺陷。此觀察對 write-time decoupled 架構於長 context 部署的可靠性提出質疑,但由於此非本方法的核心對照,詳細分析留於 appendix。

\subsection{Limitations and Scope}
\label{subsec:limitations}

本方法明確定位於 single-valued KU 情境,即同一 $(s, p)$ 於同一時點只有一個當前版本。此定位於本文的實驗結果上呈現三個層次的邊界。

第一,於 counterfactual 型 KU 情境 (FC-SH) 上,本方法於所有 baselines 上皆為 outright leader,其優勢主要來自於處理 LLM parametric bias (Section~\ref{subsec:error_mode})。此為本方法的主要 scope,適用範圍最廣。

第二,於 single-valued personal 型 KU 情境 (LME-KU) 上,本方法領先 3 個 baseline 但於 Vanilla-RAG 1-stage 上輸 3.9 pp。此結果反映當情境無 world-prior 抗力時,LLM 讀取 ordinal-prefixed pool 直接判斷 recency 亦為可行策略,本方法的架構優勢於此情境上明顯縮小。本文於 scope 的 wording 上明確承認此邊界:本方法於 counterfactual bias-heavy 情境上為 outright leader,於 personal 情境上與 LLM-recency 家族相當。

第三,對於 multi-valued personal fact 的情境 (例如使用者所會的語言、使用者的興趣,同一 property 於同時點可存在多個值),此為 out-of-scope。本方法的 $\arg\max_t$ 為 single-winner 設計,不處理 keep-all 語意。此為 future work,可透過於 method 中引入 property 的 cardinality 判斷加以擴充。

此外,LME-KU 的 evaluation 於本文中採用 gpt-4o-mini 作為 judge model,與 LongMemEval 官方 default (gpt-4o) 有所差異。此差異可能影響 Table~\ref{tab:lme_main} 中的絕對數字,但預期不影響 Table~\ref{tab:lme_gap} 中相對 gap 的方向。是否改以官方 gpt-4o judge 重新評測為未定事項;本文於此明確揭露此差異,並提醒讀者於比較絕對數字時將其納入考量。

\FloatBarrier