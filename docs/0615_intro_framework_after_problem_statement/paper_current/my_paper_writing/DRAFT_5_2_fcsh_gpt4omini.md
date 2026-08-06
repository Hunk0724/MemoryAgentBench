% ============================================================
% [2026/07/19 21:48]DRAFT — §5.2 FC-SH on gpt-4o-mini：主結果（5.2.1）+ 錯誤模式（5.2.2）
% 專寫 FC-SH / gpt-4o-mini / 4 length / 全方法。取代舊的 DRAFT_5_2_2_error_mode.md。
% 5.2.2 以「KU 判斷發生在 pipeline 何處」分四類，每類用能隔離該處的指標。
% 所有數字 committed + 可複現；腳本清單見文末 §Provenance。標註〔ROBUST〕可寫死、〔COARSE〕只講方向。
% ============================================================

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

比平均分數更值得注意的是跨 length 的行為。本方法為各 method 中唯一於四個 length 皆維持高分且平穩者（$91\sim94\%$，最大波動 3 pp）。baseline 則各自以不同方式未能同時兼顧高分與穩定：LCA 隨 context 變長單調衰退（$88\to74\to65\to43$），Zep 於 6k$\sim$64k 維持 $76\sim82\%$、卻於 262k 陡降至 29\%，此二者呈明顯的 length 敏感性；Mem0 Vanilla（$16\sim28\%$）與 Mem0 + Fact Extraction（$50\sim65\%$）則於全 length 停在偏低或中段、並非隨長度衰退；Vanilla-RAG 多數 length 達 $81\sim93\%$，惟於 32k 非單調地下探至 77\%。

Don't Ask 為 baseline 中唯一同樣跨 length 平穩者（$80\sim88\%$）。此平穩性與本方法同源：兩者的版本選擇核心皆為確定性操作——本方法以 $(s, p)$ 的 structural matching 加 $\arg\max$ 序號、Don't Ask 以取序號最大者——不需在長 context 下由 LLM 逐一比較候選，判斷結果因此與 context 長度解耦。至於各 baseline 為何未能達到本方法的分數水準（包含 Don't Ask 於平穩之下停在 86\% 左右的上限），其來源於 Section~\ref{subsec:fcsh_errormode} 分析。

\FloatBarrier
\subsection{Error Mode: Where the New Version Is Lost}
\label{subsec:fcsh_errormode}
本方法在 FC-SH 上的領先，對應 counterfactual 型 KU 的核心困難：新事實與 LLM 既有知識衝突時，LLM 傾向以既有知識作答。本節逐方法檢視 counterfactual 新版於 pipeline 何處失落，以及該失落是否可歸因於此偏好。分析聚焦於 has\_pair 子集（ground truth 同時含舊值與 counterfactual 新值；分母 6k/32k/64k/262k $=74/65/66/77$），只有這類 query 才真正觸發 KU 判斷。

\paragraph{以「KU 判斷發生於 pipeline 何處」分四類，各用能隔離該處的指標。}
各 method 的 KU 判斷發生於不同階段，故不能以單一指標比較；本節依判斷位置分四類，每類採用能在該位置隔離「新版是否被採納」的量測：

\begin{itemize}
\item \textbf{類別 1（Vanilla-RAG、LCA）——於 inference 判 KU。} 兩版本皆已提供給答題 LLM（Vanilla-RAG 為 serial-prefixed 檢索 pool、LCA 為 full context），指標為「兩版皆呈現、LLM 仍輸出 gt\_old 的比例」。此可直接歸因為 world-prior：新版就在 LLM 眼前，卻回退世界知識舊值。
\item \textbf{類別 2（Mem0、Zep）——於 write-time 判 KU。} KU 判斷早於 query-time 完成，故量測 query-time 檢索到的記憶狀態所反映的 \emph{KU 成功率}：Mem0 看 top-100 是否 recall 到 gt\_new（recall 到 $=$ 新版存活過寫入 $=$ KU 成功），Zep 看 top-10 中 gt\_old edge 是否被標為 invalid（被標 $=$ KU 成功）。\textbf{此類僅能判斷 KU 成敗，不能將失敗歸因於 world-prior}——write-time 判錯可能源於偏好，亦可能源於機制或能力，bank 狀態無從區分。
\item \textbf{類別 3（Don't Ask）——於 query-time candidate extraction 判 KU。} top-100 通常含兩版，LLM 抽出 candidate list 後以 $\max(\text{serial})$ 選版本；故只要最終答案為 gt\_old，即代表 gt\_new 未被抽出（否則其較大序號會被選中），可歸因為 world-prior。唯一例外為 D-flag（$\text{gt\_seq}<\text{old\_seq}$），需扣除。
\item \textbf{類別 4（本方法）——於 query-time structural matching 判 KU。} 版本辨識為 $(s,p)$ 的確定性配對；將失敗案例列出可見其主要錯誤模式轉移為 $(s,p)$/triple extraction 的品質問題，而非 world-prior。
\end{itemize}

表~\ref{tab:worldprior_matrix} 彙整四類的主要錯誤模式與歸因。統一的背景現象為：幾乎所有 method 失敗時最終答案皆回退 gt\_OLD（world-knowledge 舊值），此為一與 pipeline 階段無關的普遍吸子；四類的差異在於新版失落的位置，以及該回退是否即為失敗的可歸因肇因。

\begin{table}[!htb]
\centering
\caption{FC-SH has\_pair 各 method 的主要錯誤模式與 world-prior 歸因（gpt-4o-mini）。分類依 KU 判斷發生的 pipeline 位置；各類量測見上文與後續各段。}
\label{tab:worldprior_matrix}
\small
\begin{tabularx}{\linewidth}{lllXc}
\toprule
Method & 類別 & KU 判斷處 & 主要錯誤模式（新版失落位置） & world-prior \\
\midrule
Vanilla-RAG & 1 & inference & 下游 recency judge：兩版皆呈現仍選舊 & 是 \\
LCA & 1 & inference & 短：新版在 context 仍拒更新；262k：超窗截斷 & 是（短，最純）\\
Don't Ask & 3 & query-time extract & 上游 extraction 漏抽新版 & 是（扣 D-flag）\\
Mem0 + Fact Extraction & 2 & write-time & destructive 覆寫，新版不在庫 & 只判 KU 成敗 \\
Mem0 Vanilla & 2 & write-time & 原生抽取失敗 $+$ 覆寫 & 只判 KU 成敗 \\
Zep & 2 & write-time & gt\_old 未被 invalidate；262k 檢索缺 & 只判 KU 成敗 \\
Ours (Struct-Only) & 4 & query-time struct & $(s,p)$ canonicalization 碎裂 & 結構問題 \\
\textbf{Ours (main)} & 4 & query-time struct & P3 誤合 $+$ $(s,p)$ 碎裂 $+$ 殘差 & 結構問題 \\
\bottomrule
\end{tabularx}
\end{table}

\paragraph{類別 1：inference 判 KU——LLM 有兩版仍答舊。}
Vanilla-RAG 於下游失敗：兩版本皆呈現於候選集、序號規則已寫入答題 prompt，LLM 的 recency judge 仍回退舊值（has\_pair 失敗中 $95\sim100\%$ 答 gt\_OLD）〔ROBUST〕。須排除 retrieval miss：本方法與 Vanilla-RAG 共用同一 retrieval，本方法於 262k 達 91（候選集至少 91\% 含 gt\_new），Vanilla-RAG 於同一候選集僅 81，差距不可能源於檢索。LCA 為此類中最純之檢驗：其無檢索、無 memory pipeline，完整編號 fact list（新舊兩版皆在）直接進入 prompt。於 context 未超窗的 6k/32k/64k，LCA 失敗中仍有 $67\sim87\%$ 答 gt\_OLD〔ROBUST〕——「新版明明就在 context 內，LLM 仍拒絕採納」的零 pipeline confound 證據。262k 因輸入超出 128k 窗遭截斷（實測 input\_len $\approx$ 124k，新版常被切除），該長度排除於此檢驗之外。

\paragraph{類別 3：query-time extraction 判 KU——輸出舊值即等同拒抽新版。}
Don't Ask 於上游失敗：其 LLM candidate extraction 於 has\_pair 失敗中僅抽出單一舊值候選（6k 20/20），新版雖在 top-100 候選集卻未被抽出。表~\ref{tab:errormode_twocol} 以兩欄拆解 query-time 方法的失落位置：Vanilla-RAG（類別 1）的失敗幾乎全為「新版已呈現、判斷仍選舊」（Col~B），Don't Ask 的真實方法失敗全為「新版未進答題階段」（Col~A）。於 262k，Don't Ask 的 Col~A 進一步拆為 A1（gt\_new 已被檢索、LLM 卻未抽出）$=10/14$（71\%）與 A2（未被檢索）$=1/14$（7\%）：即使 context 長達 262k、新版確在候選集中，其失敗仍主導性地來自 LLM 拒抽反事實新版，而非檢索。此與 Zep 於同一 262k 形成對照——Zep 的下滑主導性地來自 query-time 未取回兩版本（82\%），失敗於 retrieval 階段。三個 query-time method 於 262k 皆無實質 retrieval miss（Don't Ask A2$=1$、Vanilla-RAG PP-Missing$=0$、Struct-Only new-miss$=0$），此為 Don't Ask 失敗「與 context 無關」的直接支撐。Figure~\ref{fig:dontask_case} 以一題呈現逐字 candidate 輸出。

\begin{table}[!htb]
\centering
\caption{query-time method 的 has\_pair 失敗二分（gpt-4o-mini, 4 length；格式 A\,/\,B 為失敗題數）。Col~A：gt\_new 於決策步驟之前即失落；Col~B：gt\_new 已抵達決策步驟卻仍答錯。$^{\dagger}$ 之 Col~B 全為 D-flag（benchmark reversed-serial，非方法失敗）。Don't Ask 之 Col~A 於 6k/32k/64k 全為 A1（retrieved-but-not-extracted）；262k 為 A1$=10$ $+$ A2$=1$。長 length 之 retrieved 判定以 gt\_new fact 文字比對為準（mquake serial 僅 6k 與 bank ordinal 對齊）。}
\label{tab:errormode_twocol}
\small
\begin{tabular}{llcccc}
\toprule
Method & 失落位置 & 6k & 32k & 64k & 262k \\
\midrule
Don't Ask & 上游 extraction & 20 / 0 & 10 / 3$^{\dagger}$ & 11 / 2$^{\dagger}$ & 11 / 3$^{\dagger}$ \\
Vanilla-RAG & 下游 recency judge & 0 / 7 & 0 / 23 & 0 / 15 & 1 / 18 \\
Ours (Struct-Only) & (S,P) 碎裂 & 7 / 0 & 10 / 2$^{\dagger}$ & 8 / 0 & 8 / 6 \\
\bottomrule
\end{tabular}
\end{table}

\begin{figure}[!htb]
\centering
\begin{minipage}{0.95\linewidth}
\begin{verbatim}
Q: What is the official language of Japan?

Retrieved top-100 pool (serial-prefixed; both versions present):
  240  The official language of Japan is Japanese.   [gt_old]
  439  The official language of Japan is Swedish.     [gt_new, newer serial]

Don't Ask -> LLM candidate extraction (verbatim raw output):
  {"candidates":[{"serial":240,"fact_text":"The official language of
   Japan is Japanese.","answer_entity":"Japanese"}]}
  n_candidates=1,  n_malformed_dropped=0   (serial 439 never extracted)
  max(serial)=240  =>  answer: "Japanese"   [wrong; gt="Swedish"]

Ours (same pool): group (Japan, official-language) -> argmax serial=439
                                     =>  answer: "Swedish"   [correct]
\end{verbatim}
\end{minipage}
\caption{一題 counterfactual 的 per-qid trace（FC-SH 6k, qid 8）。新舊版皆位於 top-100 候選集，新版序號較大；Don't Ask 的 candidate extraction 逐字輸出僅含舊版一個候選（\texttt{n\_candidates=1}，\texttt{n\_malformed\_dropped=0}——新版是被 LLM 拒抽、非 schema 丟棄），$\max(\text{serial})$ 因此只能回傳舊值。本方法於同一候選集以 $(s,p)$ 歸群取 $\arg\max$，正確選出新版。}
\label{fig:dontask_case}
\end{figure}

\paragraph{類別 2：write-time 判 KU——量 KU 成敗，不歸因 world-prior。}
Mem0 於單次 LLM 呼叫判斷取代並就地覆寫，被覆寫的 gt\_new 無法於後續查詢取回。以 query-time top-100 的 gt\_new-recall 量測其 KU 成功率（表~\ref{tab:mem0_recall}）：Mem0 + Fact Extraction 僅 $53\sim64\%$ 的 has\_pair 於答題時 pool 內仍含 gt\_new，其餘 $36\sim47\%$ 的新版已於 write-time 被 destructive UPDATE/DELETE 抹除〔ROBUST〕；此桶的答題準確率近乎為零。Mem0 Vanilla 的 answering pool 未持久化於 committed 資料，其 recall 無法計算，僅知其 overall sEM $16\sim28\%$、失敗更早發生於原生抽取階段〔COARSE〕。

\begin{table}[!htb]
\centering
\caption{Mem0 於 query-time top-100 的 gt\_new-recall（$=$ KU 成功率，新版存活過 write-time）。KU-failed $=$ 新版於 write-time 被抹除。}
\label{tab:mem0_recall}
\small
\begin{tabular}{lcccc}
\toprule
& 6k & 32k & 64k & 262k \\
\midrule
Mem0 + Fact Extraction：gt\_new-recall（KU ok） & 53\% & 55\% & 64\% & 53\% \\
\quad↳ KU-failed（新版被抹除） & 47\% & 45\% & 36\% & 47\% \\
Mem0 Vanilla & \multicolumn{4}{c}{COARSE（answering pool 未保存，無法計算）} \\
\bottomrule
\end{tabular}
\end{table}

Zep 將 LLM 職責限縮為標記 contradict/duplicate、由系統使舊 edge 失效，屬 write-time decoupled。以 top-10 中 gt\_old edge 是否帶 invalid 標記量測其 KU 成功率（表~\ref{tab:zep_invalid}）：短 context 下兩版本幾乎皆被 co-retrieved（$95\sim100\%$），但 gt\_old edge 被標為 invalid 的比例僅 $36\%/15\%/21\%$，即多數情況下舊 edge 仍有效、答題 LLM 因此缺乏消歧訊號而回退舊值。262k 則進入 retrieval-miss regime——both-retrieved 崩至 18\%，KU 失敗除「未 invalidate」外另含 gt\_old 根本未檢索取回。此 invalidation 比例因 $(s,p)$ 文字比對的 over-match（約 $26\sim35\%$）而為 gt\_old-present 的\emph{上界}，故上述 KU 成功率應視為約略上界。

\begin{table}[!htb]
\centering
\caption{Zep 於 top-10 的 gt\_old-invalidated（$=$ KU 成功率）。both-retrieved $=$ 兩版本皆檢索取回；invalidation 比例因 $(s,p)$ over-match 為上界。}
\label{tab:zep_invalid}
\small
\begin{tabular}{lcccc}
\toprule
& 6k & 32k & 64k & 262k \\
\midrule
both-retrieved & 100\% & 95\% & 98\% & 18\% \\
gt\_old-invalidated（KU ok，上界） & 36\% & 15\% & 21\% & 14\% \\
KU-failed & 64\% & 85\% & 79\% & 86\% \\
\bottomrule
\end{tabular}
\end{table}

\paragraph{類別 4：本方法——錯誤轉移為 $(s,p)$/triple 品質。}
將本方法的失敗案例列出，其主要錯誤模式並非 world-prior，而是 $(s,p)$ canonicalization miss：new 與 old 因 predicate 的 stem/full-form 差異或 subject 變體被分入不同結構群，$\arg\max_t t$ 於群內無從比對，兩版本同時保留於候選集。關閉 LLM Fallback 的 Struct-Only ablation 之 has\_pair 失敗即 $79\sim100\%$ 落於此結構碎裂〔ROBUST〕；碎裂後答題 LLM 於缺乏 recency 指引時回退舊值（故其 answered\_old 亦高，與類別 1 同機制）。此顯示本方法並非對 world-prior 免疫，而是以 $(s,p)$ structural matching 先將 pool 導向新版、避免落入該吸子，僅於 triple extraction 品質不足所致的結構失敗殘餘上才暴露；full method 以 LLM Fallback 補救此殘餘（見 Section~\ref{sec:ablation}）。

\paragraph{一致的歸因。}
綜合表~\ref{tab:worldprior_matrix}：失敗簽名跨方法統一（回退 gt\_OLD），但 KU 判斷的位置與可歸因性不同。類別 1（Vanilla-RAG、LCA）與類別 3（Don't Ask）為 LLM 手上有新版仍拒絕採納的\emph{直接} world-prior 證據，其中 LCA 為零 pipeline confound 的最純檢驗；類別 2（Mem0、Zep）僅能確認其 write-time KU 成功率偏低（Mem0 $53\sim64\%$、Zep $\le 36\%$），失敗無法乾淨歸因於 world-prior；類別 4（本方法）的錯誤轉移為 $(s,p)$/triple extraction 品質問題。此支撐 Chapter~\ref{ch:introduction} 的 causal claim：以 LLM 承擔 KU 判斷的方法，於 counterfactual 情境下受既有知識偏好影響；而本方法將版本辨識移出 LLM、以 $(s,p)$ 結構配對承擔，僅於結構失敗的殘餘上才暴露於同一偏好。

% ============================================================
% PROVENANCE（可複現，committed，canonical 未動）
% ------------------------------------------------------------
% 主表 tab:fcsh_main：results/fc_sh_main_table_4length.md（= 正文 tab:main_fcsh）。
% 類別 1/3 answered_old：analysis/errormode_worldprior_indicator.py。
% 類別 2 KU 成功率（tab:mem0_recall / tab:zep_invalid）：analysis/class2_ku_success.py
%   （Mem0 gt_new-recall = compute_pool_acc_crosstab.classify_pool_state；Zep gt_old-invalidated = rag_retrieved edges 之 invalid_at）。
% 兩欄 tab:errormode_twocol + A1/A2：analysis/dontask_rawlog_run.py + scratchpad/task2_4length.py。
% case study fig:dontask_case：rawlog_6k qid 8（n_malformed_dropped=0 verified）。
%
% CAVEATS（誠實揭露）：
%  1. LCA 262k 超窗截斷（input_len≈124k < 宣稱 300k），該格排除；6k/32k/64k 為乾淨 world-prior 檢驗。
%  2. 類別 2「不歸因 world-prior」為刻意的嚴謹選擇：write-time 判錯可能為偏好或機制/能力，bank 狀態分不出。
%  3. Zep gt_old-invalidated 因 (s,p) 文字比對 over-match（~26-35%）為上界；hint 的 4/38 未重現，視為約略上界。
%  4. Mem0 Vanilla 之 answering pool 未持久化（retrieved_memories 空）→ recall COARSE、不可算。
%  5. Ours-main 殘差（P3 誤合 7 / (s,p) 碎裂 5 / orthogonal 17）出自 diag 文件、半驗證；如需寫入請重算。
%  6. Don't Ask 長 length retrieved 判定以 fact-text 比對（mquake gt_seq 僅 6k 與 bank ordinal 對齊：6k 74/74、32k 3/65）。
%  7. 資料陷阱：Zep 32k、Mem0+P1 之聚合 output 欄位已知被 "Answer:" placeholder 覆蓋（codebase documented）→ 一律讀 per-qid response/edges，勿讀聚合 output。
%  8. 32k Don't Ask 重跑 +1 題（temp-0 server 噪，容許內）；6k/64k/262k 與 committed 一致。
% ============================================================
