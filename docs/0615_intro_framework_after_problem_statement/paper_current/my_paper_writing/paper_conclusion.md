\chapter{Conclusion}
\label{ch:conclusion}

長期記憶系統中的既有 KU 方法，其差異在於判斷的時機與 LLM 的參與程度，共同機制卻始終未變：辨識同一事實與決定當前版本這兩項判斷皆由 LLM 的語意判斷所承擔。
此依賴使 KU 表現受制於兩項與任務本身無關的因素，即 LLM 於知識衝突（knowledge conflict）下偏好既有知識的傾向，以及 backbone 的判斷能力。

本文指出，KU 的兩個子問題本身即具備可被 deterministic 化的結構。
事實更新時被替換的是 object，而 $(\text{subject}, \text{predicate})$ 恆定，因此其得以作為 fact identity 的 anchor；同一事實於同一時點只有一個當前版本，因此 version decision 可由 ingestion time 的 $\arg\max_{t} t$ 完成。
本文方法即為此洞察的直接實作：write-time 不做任何跨筆判斷，僅保留所有版本並抽取結構；query-time 才以 $(s, p)$ 配對與 $\arg\max_{t} t$ 完成 KU 判斷。

實驗以三項結果支撐此設計。
第一，本方法於 gemma3-1B 至 gpt-5.4-mini 共 6 個 tier 以及 4 個獨立 open-weight family 上皆為 outright leader，baselines 於 gemma3-1B 上皆不高於 30\%，於強 backbone 上 gap 收斂但未反轉，驗證了 KU 表現由事實結構所決定，不再受限於 backbone 的能力。
第二，baselines 於 KU 失敗時有 95\% 至 100\% 回退至世界先驗的舊值，確立了其差距確實來自 LLM 的參數化偏差（parametric bias）。
第三，於不具 world-prior 抗力的 personal 型情境上，本方法相對 Mem0 Vanilla 的 gap 自 $+78$~pp 收窄至 $+2.6$~pp，且與 LLM-recency 家族相當而非領先，此收窄反向印證了上述歸因成立。

本文的結論並非記憶系統應完全排除 LLM，而是 LLM 的職責應限縮於 extraction 以及結構配對失效時的 identity 補救。
此定位有定量資料支撐：structural matching 於各 length 上承擔 68\% 以上的判斷，LLM Fallback 僅承擔 12\% 至 32\%，且其貢獻呈 capability-gated 特性，於弱 backbone 上為負、於強 backbone 上方為正。
因此，於屬性為 single-valued 的假設下，讓 deterministic 機制承擔核心判斷，而 LLM 僅作補救，是比既有以 LLM 判斷為核心的方法，更適合的長期記憶系統 KU 架構設計。