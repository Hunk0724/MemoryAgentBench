在長期互動的記憶系統當中，同一事實會隨時間累積多個版本，正確辨識並採用其最新版本的任務被稱為知識更新（knowledge update, KU），此問題已被近期多個 benchmark 視為記憶系統的核心能力。過去方法主要在寫入階段（write-time）做 KU 判斷，但這一類方法共通問題是，只要 LLM 誤判就會將錯誤不可逆寫入記憶；即便近期有研究開始將 KU 判斷設計於查詢階段（query-time），讓正確事實至少都能保留在記憶。然而，這些方法都透過 LLM 的語意判斷來解決 KU，使得兩個層面上存在問題。首先，新事實與 LLM 既有知識衝突時，LLM 傾向以既有知識回答，而無法忠實於輸入資訊做出正確更新；其次，KU 的表現受限於 LLM 的能力是否可靠，於實際部署中，當 backbone 較弱時無法對 KU 做出正確判斷。

本文提出以確定性（deterministic）結構配對為主要 KU 判斷方式，write-time 保留所有版本，並對事實提取結構化資訊；將 KU 判斷延後至 query-time 以 (subject, predicate) 配對以辨識同一事實，並以事實寫入時序決定當前版本，LLM 僅在結構配對失效的情況作為補救機制。

本文於兩個 KU benchmark 上與現有方法比較。本文方法在 counterfactual 型 KU 情境（新事實與 LLM 既有知識衝突）上，答題準確度皆超越 baselines，且分析 baseline 的錯誤，驗證主要來自 LLM 傾向自身知識而抗拒更新 counterfactual 事實。並以不同能力的 backbone 進行實驗，驗證現有方法依賴 LLM 判斷 KU，因此隨 backbone 能力變弱而直接影響判斷表現。

整體而言，本文將 LLM 決策從 KU 判斷中移出，改以 deterministic 結構配對的方式判斷，驗證 KU 表現可由事實結構決定，不再被 backbone 的能力所限制。結果顯示，於 KU 這任務上，讓確定性機制作為核心判斷，LLM 僅作補救，是比既有方法更適合的架構設計。