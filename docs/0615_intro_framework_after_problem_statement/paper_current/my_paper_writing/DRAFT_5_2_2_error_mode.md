% ============================================================
% DRAFT — §5.2.2 Error Mode（初步版本，2026-07-19）
% 原則：只放 robust 數字；Mem0 M1/M2 與 Ours-main 殘差走粗方向；Zep 分兩 regime。
% 所有數字出處：results/fc_sh_errormode_dominant_buckets.md（腳本 analysis/errormode_dominant_buckets.py，可複現）。
% 標註：〔ROBUST〕可寫死；〔COARSE〕只講方向。
% ============================================================

\subsection{Per-qid Error Mode: Baselines Fall Back to Prior Knowledge}
\label{subsec:error_mode}

於 FC-SH 的 has\_pair 子集上以 per-qid 逐題分析各 baseline 的失敗案例，揭露一個跨方法一致的簽名：當 KU 失敗時，最終答案回退到與 LLM 既有知識一致的舊值（即 counterfactual scope 下的 gt\_OLD）。此簽名於全部 baseline 上成立，差異僅在於「新版本於 pipeline 的哪一站被弄丟」——write-time 家族於寫入時即物理性抹除新版，query-time 家族則於候選抽取或版本判斷時洩漏對既有知識的偏好。Table~\ref{tab:errormode_buckets} 以各家族對應的診斷指標，並列其主占比失敗機制；本節其餘部分依 pipeline 位置逐一說明。此分析對應 Chapter~\ref{ch:introduction} 的 causal claim：baselines 的錯誤主要來自 LLM 於 counterfactual 情境下對既有知識的偏好。

\begin{table}[!htb]
\centering
\caption{FC-SH has\_pair 各 baseline 的主占比失敗機制（gpt-4o-mini backbone，4 length）。各家族以能隔離其失敗階段的指標量測，全部收束於「回退 gt\_OLD」的同一簽名。數字為該指標於 has\_pair 失敗中的占比；完整逐 length 值與複現腳本見附錄。}
\label{tab:errormode_buckets}
\small
\begin{tabularx}{\linewidth}{llX}
\toprule
Method & KU 判斷時機 & 新版本失落的 pipeline 位置與主占比失敗證據 \\
\midrule
Mem0 + Fact Extraction & Write-time coupled & 寫入時 destructive UPDATE 覆寫舊值；gt\_new 於答題 pool 中已缺席 36--47\%，該桶答題準確率 $\approx 0$（新版於 write-time 不可逆遺失）\\
Zep~\cite{rasmussen2025zep} & Write-time decoupled & 短 context：未產生 invalidation 訊號、舊 edge 續存，此類失敗 100\% 答 gt\_OLD；262k：query-time 未同時取回兩版本 82\%（檢索崩潰，見 Section~\ref{sec:main_results}）\\
Don't Ask~\cite{reddy2026don} & Query-time (upstream) & LLM candidate extraction 僅抽出單一候選且為舊值；6k 失敗 100\%（20/20）\\
Vanilla-RAG & Query-time (downstream) & 兩版本皆於候選集，LLM recency judge 未依序號選新版；失敗 95--100\% 回退 gt\_OLD \\
Ours (Struct-Only) & Query-time (structural) & $(s,p)$ canonicalization 碎裂致兩版本分入不同群；失敗 79--100\% 回退 gt\_OLD \\
\bottomrule
\end{tabularx}
\end{table}

\paragraph{Write-time 家族：新版於寫入時即被抹除。}
Mem0 + Fact Extraction 於單次 LLM 呼叫中判斷取代關係並就地覆寫，被覆寫的 gt\_new 無法於後續查詢中取回。以 answering pool 的狀態量測，其 has\_pair 中有 36--47\% 的 query 於答題時 pool 內已無 gt\_new（僅存舊值或兩版本皆缺），且此桶的答題準確率近乎為零〔ROBUST〕。此為 Chapter~\ref{ch:methodology} 中「write-time 判斷的錯誤不可逆」的直接證據：一旦 write-time 誤判，損害即固化於記憶、query-time 無從還原。Mem0 Vanilla 為此家族的極端，其原生 extraction 於 counterfactual 事實上常抽不出，overall sEM 僅 16--28（Table~\ref{tab:main_fcsh}），失敗更早發生於抽取階段〔COARSE，僅陳述方向〕。

Zep 將 LLM 職責限縮為標記 contradict/duplicate、由系統使舊 edge 失效，屬 write-time decoupled。其失敗於 context 長度上分為兩個 regime。短 context（6k--64k）下 Zep 檢索能同時取回兩版本（未取回兩版本者僅 0--5\%），但於此類「舊 edge 未被 invalidate、兩版本對答題 LLM 同時可見」的失敗案例中，最終答案 100\% 落於 gt\_OLD（32k 17/17、64k 23/23）〔ROBUST；6k 因 Zep 於此長度甚強、失敗僅 2 題，樣本小，僅作機制佐證〕，顯示其失敗來自答題端對既有知識的偏好而非檢索。262k 則轉為另一 regime：query-time 檢索崩潰，has\_pair 有 82\% 未同時取回兩版本〔ROBUST〕，此長度的下滑主因為檢索而非 KU 判斷（見 Section~\ref{sec:main_results} 與附錄）。

\paragraph{Query-time 家族：兩版本皆在，卻於判斷時選錯。}
Don't Ask 的失敗發生於上游：其 LLM candidate extraction 於 6k 的 has\_pair 失敗中 100\%（20/20）僅抽出單一候選，且該候選為與既有知識一致的舊值，counterfactual 的新版雖存在於 top-100 檢索範圍內卻於 extraction 階段被漏掉〔ROBUST；長 context 之數字受 benchmark reversed-serial（D-flag）影響，引用時需標明 raw 或 D-flag 調整後〕。其失敗不在 freshness 選擇本身（$\max(\text{ordinal})$ 於單一候選上必然正確），而在 LLM extraction 洩漏了對既有知識的偏好。Figure~\ref{fig:dontask_case} 以一題 counterfactual 具體呈現此洩漏：新舊版皆於候選集、新版序號較大，Don't Ask 仍僅抽出舊版。

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
\caption{一題 counterfactual 的 per-qid trace（FC-SH 6k, qid 8）。新版（serial 439, Swedish）與舊版（serial 240, Japanese）皆位於 top-100 候選集，且新版序號較大；Don't Ask 的 LLM candidate extraction 之逐字輸出卻僅含舊版一個候選（\texttt{n\_candidates=1}，\texttt{n\_malformed\_dropped=0}——確認新版是被 LLM 拒抽，而非 schema 不合被丟棄），$\max(\text{serial})$ 因此只能回傳舊值，即使答題 prompt 已含序號規則。本方法於同一候選集上以 $(s,p)$ 結構歸群、取 $\arg\max$ 序號，正確選出新版。此為「LLM 於 counterfactual 情境下抗拒更新」的具體實例。}
\label{fig:dontask_case}
\end{figure}

Vanilla-RAG 的失敗發生於下游：兩版本皆存在於候選集、序號規則已明確寫入答題 prompt，LLM 的 recency judge 仍未依序號選新版，而選擇與既有知識一致的舊值——其 has\_pair 失敗 95--100\% 回退 gt\_OLD，於 32k 最嚴重（65 題錯 23 題），對應 Table~\ref{tab:main_fcsh} 中 32k 的 non-monotonic dip〔ROBUST〕。此失敗須排除 retrieval miss 的替代解釋：本方法與 Vanilla-RAG 共用同一 retrieval 設定，面對的候選集完全相同，而本方法於 262k 達 91（代表候選集中至少 91\% 的 query 含 gt\_new），Vanilla-RAG 於同一候選集上僅達 81，其差距因此不可能源於 retrieval miss，而定位於下游的 recency judge。此觀察直接支撐 Chapter~\ref{ch:methodology} 中「version decision 必須為 deterministic 操作」的核心設計決策。

Table~\ref{tab:errormode_twocol} 將三個 query-time baseline 於 4 個 length 的 has\_pair 失敗二分，以定位新版於「決策步驟之前」或「決策步驟本身」失落，三者清楚分工且於 length 上穩定：Vanilla-RAG 的失敗幾乎全落於 Col~B（新版已呈現、判斷仍選舊），Don't Ask 與 Struct-Only 的真實方法失敗則主要落於 Col~A（新版於 extraction 或結構歸群時即失落）。須特別指出，Don't Ask 與 Struct-Only 於短中 length 的 Col~B 全為 benchmark reversed-serial（D-flag，$\text{gt\_seq}<\text{old\_seq}$，$\max(\text{serial})$ 本不可能選中新版），非方法本身的判斷失敗；Vanilla-RAG 的 Col~B 則為真實的判斷失敗。

此二分於 262k 上提供本節最乾淨的一項證據。將 Don't Ask 的 Col~A 進一步拆解，可分為 A1（gt\_new 已被檢索進 top-100 候選集、LLM extraction 卻未將其抽出）與 A2（gt\_new 根本未被檢索取回）。於 262k 上，Don't Ask 的 has\_pair 失敗有 A1 $=10/14$（71\%）、A2 僅 $1/14$（7\%）：即使 context 長達 262k、新版確實存在於候選集之中，其失敗仍主導性地來自 LLM 於 extraction 階段拒絕採納 counterfactual 新版，而非檢索或 scaling 的失效。此與 Zep 於同一 262k 上形成對照——Zep 的下滑主導性地來自 query-time 檢索未取回兩版本（82\%，見 Section~\ref{sec:main_results}），即失敗於 retrieval 階段。兩者於同一 context 長度、失敗於 pipeline 的相反兩端，將「檢索 scaling 的失效」與「LLM 判斷的失效」清楚區隔。事實上，三個 query-time baseline 於 262k 皆無實質的 retrieval miss（Don't Ask A2 $=1$、Vanilla-RAG PP-Missing $=0$、Struct-Only new-miss $=0$），gt\_new 幾乎總是被檢索取回，每一項失敗皆為下游判斷失敗而非檢索失敗，此為 Don't Ask 失敗「與 context 無關」的直接支撐。

\begin{table}[!htb]
\centering
\caption{Query-time baselines 的 has\_pair 失敗二分（gpt-4o-mini, 4 length；格式 A\,/\,B 為失敗題數）。Col~A：gt\_new 於決策步驟之前即失落（未進答題階段）；Col~B：gt\_new 已抵達決策步驟卻仍答錯。A+B 涵蓋 100\% 失敗。$^{\dagger}$ 之 Col~B 全為 D-flag（benchmark reversed-serial，非方法失敗）。Don't Ask 的 Col~A 於 6k/32k/64k 全為 A1（retrieved-but-not-extracted）；262k 為 A1$=10$ $+$ A2$=1$（唯一一題 retrieval miss）。長 length 之 retrieved 判定以 gt\_new 之 fact 文字比對為準（mquake serial 僅於 6k 與 bank ordinal 對齊）。}
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

\paragraph{結構碎裂下本方法亦露出同一簽名。}
本方法關閉 LLM Fallback 的 ablation（Struct-Only）於 has\_pair 失敗中同樣 79--100\% 回退 gt\_OLD〔ROBUST〕，其根本原因單一，為 $(s,p)$ canonicalization miss：new 與 old 因 predicate 的 stem/full-form 差異或 subject 的細微變體被分入不同結構群，$\arg\max_t t$ 於群內無從比對，兩版本因此同時保留於候選集，答題 LLM 於缺乏 recency 指引時回退舊值。此為 LLM Fallback 存在的理由——於 structural matching 無法歸群時補上 identity 判斷。

\paragraph{一致的歸因與其設計意涵。}
上述機制分屬 pipeline 的不同位置（Don't Ask 於上游 candidate extraction、Vanilla-RAG 於下游 recency judge、Struct-Only 於結構碎裂後的答題階段、Mem0 於 write-time 覆寫、Zep 於 invalidation/檢索），但全部收束於同一失敗簽名：回退到與 LLM 既有知識一致的 gt\_OLD。此顯示對既有知識的偏好並非某一階段特有的現象，而是 LLM 只要於 pipeline 中的任一位置接觸 counterfactual 事實即可能洩漏。值得注意的是 Don't Ask 的 pipeline 不含答題階段的 LLM 呼叫（見 Section~\ref{subsec:implementation}），其偏好仍於 candidate extraction 洩漏；此進一步支持——有效的處理方式為將 KU 判斷整段移出 LLM，而非僅將其自答題階段移除。本方法以「忠實寫入所有版本、結構化 identity、以 $\arg\max_t t$ 決定版本、LLM Fallback 補救少數殘餘」的組合逐一迴避各層洩漏。

% ============================================================
% CASE-STUDY CANDIDATES — Don't Ask（三題已驗證，擇一放正文 Figure~\ref{fig:dontask_case}）
% 資料：outputs/maxserial_theircode/6k_gpt-4o-mini_vector100.json
%       + analysis/results/sh_6k_mquake_analysis.json
%       + outputs/rag_retrieved/Structure_rag_...(struct/no_p5)/.../query_{qid}_context_0.json
% 共同性質（三題皆滿足，confounder 全清）：
%   n_candidates=1、抽出=舊版、答錯；gt_seq>old_seq（非 D-flag）；
%   新版 serial 在 retrieved_ords；ours/struct 同題答對 → 新版確在共用 pool 且可辨識。
% ------------------------------------------------------------
% ★ 主選 qid 8：What is the official language of Japan?
%     old  240  Japanese（真實世界值） | new  439  Swedish（序號較大）
%     Don't Ask: retrieved_ords=[240,439,...], n_candidates=1, chosen_serial=240 → "Japanese" ✗（gt=Swedish）
%     ours/struct（同 pool）→ "Swedish" ✓
%     優點：單一 (Japan, 官方語言)、240 與 pool 行 byte 對齊、新舊兩行可並排。
%
% 備選 qid 19：Who is the chief executive officer of Microsoft?
%     old  85  Satya Nadella（現實中真實 CEO） | new  188  Steve Jobs
%     Don't Ask: retrieved_ords=[188,85,...], n_candidates=1, chosen_serial=85 → "Satya Nadella" ✗（gt=Steve Jobs）
%     ours/struct（同 pool）→ "Steve Jobs" ✓
%     優點：LLM 回退到「現實中真實的 CEO」，最能體現 world-prior 抗力；若 narrative 想強化
%           「新值與 LLM 既有知識衝突」這點，qid 19 畫面比 qid 8 更強。
%
% 備選 qid 14：Who is the author of Sidereus Nuncius?
%     old  124  Galileo Galilei（真實作者） | new  401  Samuel Beckett
%     Don't Ask: retrieved_ords=[124,401,...], n_candidates=1, chosen_serial=124 → "Galileo Galilei" ✗（gt=Samuel Beckett）
%     ours/struct（同 pool）→ "Samuel Beckett" ✓
%
% RAW OUTPUT — 已於 2026-07-19 重跑捕捉（rawlog）：
%   rawlog（新檔，未覆蓋 canonical）：
%     outputs/maxserial_theircode/rawlog_6k_gpt-4o-mini_vector100.json
%     outputs/maxserial_theircode/rawlog_32k_gpt-4o-mini_vector100.json
%   重跑腳本：analysis/dontask_rawlog_run.py（包 chat.completions.create 抓 raw；不動 canonical runner/_pipeline.py）
%   一致性：6k 完全一致（overall 80/100, has_pair 54/74）；32k +1 題（87 vs 86，temp-0 server 噪，容許內）。
%   三題 n_malformed_dropped 皆 = 0、cand_extract_status = ok → 新版是被 LLM 拒抽，非 schema 丟棄。
%   逐字 raw_llm_text：
%     qid 8 : {"candidates":[{"serial":240,"fact_text":"The official language of Japan is Japanese.","answer_entity":"Japanese"}]}
%     qid 19: {"candidates":[{"serial":85,"fact_text":"The chief executive officer of Microsoft is Satya Nadella.","answer_entity":"Satya Nadella"}]}
%     qid 14: {"candidates":[{"serial":124,"fact_text":"The author of Sidereus Nuncius is Galileo Galilei.","answer_entity":"Galileo Galilei"}]}
%   → 正文 Figure~\ref{fig:dontask_case} 已改用 qid 8 的逐字 JSON；caveat 解除。
% ------------------------------------------------------------
% 64k/262k 擴充（2026-07-19 重跑）：
%   rawlog：outputs/maxserial_theircode/rawlog_{64k,262k}_gpt-4o-mini_vector100.json
%   一致性：262k 完全一致（overall 86/100, has_pair 63/77）；64k −1（87 vs 88，容許內）。
%   Don't Ask A1/A2/B（has_pair 失敗）：6k 20/0/0、32k 10/0/3、64k 11/0/2、262k 10/1/3。
%     → 262k A1=71%、A2=7% → 純 LLM 拒抽、與 context 無關（vs Zep 262k 敗在 A2 檢索崩 82%）。
%   Vanilla-RAG / Struct-Only 64k+262k 兩欄由 committed 資料補齊（見 tab:errormode_twocol）。
%   ⚠ 方法論：A1/A2 於 32k+ 以 gt_new fact-text 比對判定 retrieved（mquake gt_seq 僅 6k 與
%     bank ordinal 對齊：6k 74/74、32k 3/65）。結論（A1 主導）穩，精確數字引用時註明此判定方式。
%   分析腳本：scratchpad/task2_4length.py（rescore_canonical.official_subem +
%     compute_m1_m2_m3.match_pair + classify_pool_state + maxserial_theircode.load_bank）。
% ============================================================
