\chapter{Methodology}
\label{ch:methodology}

\section{Overview}
\label{sec:method_overview}
本文方法透過使用者於長期互動中所產生的對話作為輸入，將對話中所抽取的事實建構為外部記憶，並於後續查詢觸發時自記憶中辨識事實的當前版本作為輸出。
方法的目標是讓記憶系統於建構與檢索的過程中正確處理 KU：當同一事實於不同時間點被多次抽取並累積多個版本時，查詢時所回傳的內容應為最新版本，而非過時版本。
整體流程呈現於圖~\ref{fig:method_overview}，包含 write-time 與 query-time 兩個階段。

\figt{0.8\columnwidth}
{figs/method_overview}
{本文方法的整體架構。Write-time 以 append 方式將事實連同寫入時序 $t$ 寫入記憶 $\mathcal{M}$，確保事實的正確版本存在於記憶中。Query-time 以 $(\text{subject}, \text{predicate})$ 配對同一事實並依寫入時序 $t$ 決定當前版本，LLM 僅於 structural matching 無法完成歸群時作為補救。}
{fig:method_overview}
{}

write-time 階段負責將對話中新出現的事實忠實寫入記憶，不對記憶中既有事實做任何跨事實的判斷。
此階段包含兩個 LLM extraction 步驟（其中第二步於 triple 無法映射時另有一次補充呼叫，見 Section~\ref{subsec:triple_extraction}）。
第一步為事實抽取（fact extraction），自使用者發話中將所斷言的內容切分為原子事實，每筆事實對應於單一斷言。
第二步為 triple extraction，將每筆事實映射為 $(\text{subject}, \text{predicate}, \text{object})$ 三元組，其中 subject 為此事實所指涉的實體，predicate 為連結 subject 與 object 的關係表達，object 為當下所斷言的值。
每筆事實於寫入記憶時同時記錄其寫入時序，並保留該事實原文與抽取所得的 triple 作為 metadata。
此階段對記憶不進行任何比對或修改，新事實一律以 append 方式寫入，同一事實於不同時點所斷言的多個版本因此於記憶中並存。

query-time 階段負責於查詢觸發時自記憶中辨識當前版本。
查詢首先觸發 candidate retrieval，以 vector search 自記憶中取回與查詢語意相關的 top-$K$ 候選事實。
取回的候選事實隨後進入 structural matching，以每筆事實 metadata 中的 $(\text{subject}, \text{predicate})$ 作為 key，將指涉同一 $(\text{subject}, \text{predicate})$ 的候選歸為同一群；同群內的候選對應於同一事實的不同版本，以寫入時序最新者（即 $\arg\max_{t} t$）作為當前版本。
此路徑為 deterministic，不涉及 LLM 呼叫，其判斷結果不受 backbone 能力變動的影響。
然而，兩類候選無法由此主路徑完成歸群：其一為於 triple extraction 階段無法映射為明確 $(\text{subject}, \text{predicate}, \text{object})$ 的候選（例如包含多重斷言、指涉不明或屬於主觀敘述），此類候選無 key 可供分群；其二為分群後僅含單一成員的 singleton 群，其中可能存在同一事實因抽取用字差異而未落入同一 key 的孤立版本。
此兩類候選共同構成殘餘 pool，由 LLM Fallback 針對其以語意判斷同一事實的歸屬。
LLM Fallback 的職責僅限於 identity 判斷，不判斷版本新舊，版本判斷仍由寫入時序最新者作為當前版本此一 deterministic 規則完成。
上述兩條路徑所產出的當前版本共同構成 Current Version(s)，作為 answer 階段的輸入。

此架構承載三項核心設計原則。
第一，write-time 不做任何跨筆判斷，所有版本於記憶中並存，錯誤的 KU 判斷不會於寫入階段不可逆地污染記憶。
第二，query-time 的主要 KU 判斷為 deterministic 操作，不涉及 LLM 呼叫，因此其表現不隨 backbone 能力變動而改變，亦不受 knowledge conflict 情境下 LLM 判斷偏好的影響。
第三，LLM 於整體架構中僅參與兩類 extraction 任務（write-time 的 fact extraction 與 triple extraction）以及一類補救任務（query-time 的 LLM Fallback）；其中 extraction 任務為將 unstructured text 映射為 structured representation 的資訊抽取任務，不涉及跨筆事實的取代判斷，LLM Fallback 則僅於 structural matching 無法完成歸群的少數殘餘候選上介入，不修改記憶，不判斷版本。
此三項原則將 LLM 電腦排除於 KU 判斷之外，使 KU 表現由事實的結構所決定，而非由 backbone 的判斷能力所決定。

後續章節依此架構展開。
Section~\ref{sec:notation} 建立本方法所使用的符號、KU 問題的形式化定義，以及方法所倚賴的假設，提供後續章節共用的形式化基礎。
Section~\ref{sec:writetime} 描述 write-time 的兩個 extraction 步驟與記憶寫入細節，並於節首明確劃清 LLM 於本方法中所承擔的 extraction 職責與所排除的 judgment 職責。
Section~\ref{sec:querytime} 描述 query-time 的 candidate retrieval、structural matching 與 LLM Fallback。

\section{Notation and Formal Definitions}
\label{sec:notation}
本節建立後續章節共用的形式化定義以及本方法所倚賴的假設。以下三個 numbered definitions 依序建立事實的表達、同一事實的判準，以及當前版本的判準，並以此形式化 KU 任務。

\begin{definition}[Fact and Memory]
\label{def:fact}
記憶中每筆事實表達為四元組 $(s, p, o, t)$，其中 $s$、$p$、$o$ 分別為此事實的 subject、predicate、object，$t$ 為此事實寫入記憶的時序（ingestion time）。記憶 $\mathcal{M}$ 為所有已寫入事實的集合。
\end{definition}

\begin{definition}[Same Fact]
\label{def:same}
兩筆事實 $(s_1, p_1, o_1, t_1)$ 與 $(s_2, p_2, o_2, t_2)$ 為同一事實，若且唯若 $s_1 = s_2$ 且 $p_1 = p_2$。
\end{definition}

\begin{definition}[Current Version]
\label{def:current}
對於任一 $(\text{subject}, \text{predicate})$ 對 $(s, p)$，以
\[
\mathcal{M}_{s,p} = \{(s', p', o', t') \in \mathcal{M} : s' = s,\ p' = p\}
\]
表示 $\mathcal{M}$ 中所有 subject 為 $s$ 且 predicate 為 $p$ 的事實子集。此 $(\text{subject}, \text{predicate})$ 對應的當前版本為：
\begin{equation}
f^{*}_{s,p} = \arg\max_{(s', p', o', t') \in \mathcal{M}_{s,p}} t'.
\end{equation}
\end{definition}

依上述定義，KU 任務可形式化為：給定記憶 $\mathcal{M}$ 與查詢 $q$，自 $\mathcal{M}$ 中辨識與 $q$ 相關的事實，並於同一事實（依 Definition~\ref{def:same}）存在多個版本的情境下，回傳其當前版本（依 Definition~\ref{def:current}）。
本方法於後續章節將以此形式化語言展開 write-time 與 query-time 的各 component 設計。

本方法建立於一項核心假設：對於同一 $(\text{subject}, \text{predicate})$，於同一時點只有一個當前版本，亦即該屬性（property）為 single-valued。
此假設於 counterfactual 型 KU 情境完全成立，因為此類情境所處理的事實（例如某公司的 CEO 與某國的首都）天然為 single-valued。
於 personal 型 KU 情境，此假設於 single-valued 的個人事實（例如使用者所居住的城市）成立，方法所判斷的 KU 對象亦以此類事實為主；
對於 multi-valued 的個人事實（例如使用者所會的語言與使用者的興趣），同一時點可存在多個值，不構成版本衝突，方法於 LLM Fallback 的 identity 判斷中明確不將此類事實視為同一事實的不同版本。

\section{Write-time Pipeline}
\label{sec:writetime}
Write-time 承擔將對話中新出現的事實忠實寫入記憶的職責，不對記憶中既有事實進行任何跨筆判斷。
此階段的 LLM 使用需與 KU 判斷明確區分。
本方法將 LLM 的使用區分為兩類任務：一類為 LLM 抽取（extraction），任務目標為將 unstructured text 映射為 structured representation，結果僅涉及單筆事實內部的結構化，不涉及跨筆事實的比較或取代；另一類為 LLM 判斷（judgment），任務目標為對候選事實間的取代關係進行決策，結果直接決定記憶狀態或查詢回應。
前者於 knowledge conflict 情境下不受影響，因為任務本身不涉及事實內容與 LLM 既有知識的一致性判斷；後者則直接暴露於 knowledge conflict 之下。
本方法於 write-time 僅使用前者，不使用後者。

\subsection{Fact Extraction}
\label{subsec:fact_extraction}
Fact extraction 自使用者發話中將所斷言的內容切分為原子事實（atomic fact），每筆事實對應於單一斷言，以 LLM 執行。
此步驟為後續 triple extraction 提供 atomic 的輸入單位，其設計本身相對通用，不承載本方法的核心設計。完整 prompt 見附錄。

\subsection{Triple Extraction}
\label{subsec:triple_extraction}
Triple extraction 為本方法於 write-time 的核心設計，將 fact extraction所產出的每筆原子事實映射為 $(s, p, o)$ 三元組。
選用 $(s, p, o)$ 表示的核心理由在於其 partition 性質天然對應 KU 場景：當使用者於長期互動中更新一筆事實時，被更新的通常是 object 這一欄（新值取代舊值），而 $(\text{subject}, \text{predicate})$ 保持不變（同一實體的同一屬性）。
此性質使 $(\text{subject}, \text{predicate})$ 得以作為 fact identity 的 anchor，而 object 承載跨版本的差異部分，直接支撐 Section~\ref{sec:querytime} 中 structural matching 依 $(\text{subject}, \text{predicate})$ 配對同一事實的執行。

為使此 partition 性質於實作中成立，triple extraction 要求 subject 為此事實所指涉的不變實體、object 為當下所斷言的可變值、predicate 為連結兩者的關係表達；於名詞化的關係表達下（例如「the CEO of Acme is Jane Doe」），須將名詞片語分解為 subject 為 Acme、predicate 為 "has CEO"、object 為 Jane Doe，以確保同一實體的同一屬性於不同表述下仍映射至同一 $(\text{subject}, \text{predicate})$。
對於無法乾淨映射為單一 $(s, p, o)$ 的原子事實（主觀敘述、多重斷言、指涉不明），triple 設為 null，並以簡短的補充 LLM 呼叫抽取其主要指涉實體作為 subject fallback，以支援 Section~\ref{sec:querytime} 中 LLM Fallback 的 subject-consistency 判斷。完整 prompt 見附錄。

Triple extraction 所產出的 $(s, p, o)$ 需經過 normalization 以支援 structural matching 於 query-time 的 exact match 執行，目的為讓文字表達上的差異（例如冠詞、copula 的形式變化）不阻礙同一事實的配對。
經過 normalization 後的 $(s, p)$ 稱為 canonical key，是 structural matching 於配對時所使用的實際 key。Normalization 的完整規則見附錄。

每筆事實於寫入記憶時，以 append 方式加入 $\mathcal{M}$，不對記憶中既有事實進行任何比對或修改。
每筆事實的 metadata 包含：事實原文、提取所得的 $(s, p, o)$ 與其 canonical key、以及寫入時序 $t$。
寫入時序 $t$ 於實作中以 per-user 全域的 fact-level 遞增計數器實現，對應於 Definition~\ref{def:fact} 中 $t$ 於同一使用者記憶內為全序的形式化性質，以支援 Definition~\ref{def:current} 中 $\arg\max_{t} t$ 的 deterministic 執行。

\section{Query-time KU Resolution}
\label{sec:querytime}
Query-time 承擔本方法的 KU 判斷職責。
KU 判斷於此階段可分解為兩個子問題：fact identity 為辨識哪幾筆候選記憶對應於同一事實，version decision 為決定同一事實的多個版本中哪一個為當前版本。
本方法對兩個子問題採取的策略分別對應於 Definition~\ref{def:same} 與 Definition~\ref{def:current}：fact identity 主要以 $(s, p)$ 的 structural matching 完成，少數 structural matching 無法歸群的情境以 LLM 補救；version decision 完全以 $\arg\max_{t} t$ 完成，不涉及 LLM。
以下依 candidate retrieval、structural matching、以及 structural matching 之後的 LLM Fallback 依序展開。

\subsection{Candidate Retrieval}
\label{subsec:candidate_retrieval}
給定查詢 $q$，以 vector search 自記憶 $\mathcal{M}$ 中取回與 $q$ 語意相關的 top-$K$ 候選事實，構成候選集 $\mathcal{C}$。
此步驟為標準 dense retrieval，embedding 對象為 Section~\ref{sec:writetime} 寫入時所保留的事實原文。

\subsection{Structural Matching and LLM Fallback}
\label{subsec:structural_matching}
Structural matching 為 query-time KU 判斷的主路徑，以 $(s, p)$ 為 key 將候選集 $\mathcal{C}$ 分群，每群內以 $\arg\max_{t} t$ 決定當前版本。
此路徑於 Definition~\ref{def:same} 下退化為 canonical key 的 exact match，於 Definition~\ref{def:current} 下退化為寫入時序上的 $\arg\max$，兩者皆為 deterministic 操作。
此路徑不涉及 LLM 呼叫，因此其判斷結果不隨 backbone 能力變動而改變，亦不受 knowledge conflict 情境下 LLM 判斷偏好的影響。

Structural matching 的主路徑仰賴候選事實落入可供比對的 $(s, p)$ 群，兩類候選無法滿足此前提。
其一為 Section~\ref{sec:writetime} 所述 triple extraction 中無法乾淨映射為單一 $(s, p, o)$ 的候選（主觀敘述、多重斷言、指涉不明），其 triple 為 null，於 $\mathcal{C}$ 中無 canonical key 可供分群。
其二為依 canonical key 分群後僅含單一成員的 singleton 群；其成員雖具備 key，但若同一事實的另一版本因抽取用字差異而落入不同 key，兩個版本便各自成為 singleton，$\arg\max_{t} t$ 於單一成員的群內無從比對版本。
此兩類候選共同構成殘餘 pool，由 LLM Fallback 補救。

LLM Fallback 的職責僅限於 identity 判斷，即針對殘餘 pool 以語意判斷哪幾筆對應於同一事實，不判斷版本新舊；判斷所得的 identity cluster 內部，仍以 $\arg\max_{t} t$ 決定當前版本，version decision 於此路徑上仍為 deterministic。
LLM Fallback 不修改記憶，亦不對 $\mathcal{M}$ 中既有事實進行任何寫入。

為降低 LLM 於 identity 判斷中錯誤合併不同事實的風險，LLM Fallback 附加一項 subject-consistency 檢查：若 LLM 所建議的 identity cluster 內部存在兩個以上明確且不同的 subject，則拒絕此 cluster。
殘餘 pool 中的兩類候選於此檢查上所依據的訊號來源不同：具備 triple 的 singleton 候選直接以其 triple 中的 subject 作為比對依據，triple-null 候選則因無 triple 可讀，須倚賴 Section~\ref{sec:writetime} 於此情境下所抽取的 subject fallback，該 fallback 為此類候選唯一可供此檢查啟用的訊號。兩者共同使此檢查得以對橫跨不同實體的錯誤合併給出 deterministic 的否決依據。

經過此檢查後所保留 the cluster，連同 structural matching 主路徑所產生的群，一併進入 $\arg\max_{t} t$ 決定當前版本；未被歸入任何 cluster 的殘餘候選（包含被此檢查否決的 cluster 之成員）各自視為獨立的單一成員群。
所有群所產出的當前版本共同構成 Current Version(s)，作為 answer 階段的輸入。完整 prompt 見附錄。

演算法~\ref{alg:query} 以 pseudocode 呈現 query-time 的完整流程，作為上述文字描述的輔助 reference。

\begin{algorithm}[htbp]
\caption{Query-time KU Resolution}
\label{alg:query}
\SetKwInOut{Input}{Input}
\SetKwInOut{Output}{Output}
\Input{Query $q$, memory $\mathcal{M}$}
\Output{Current version(s) $\mathcal{V}$}
$\mathcal{C} \gets \textsc{TopK-VectorSearch}(q, \mathcal{M})$\;
$\mathcal{C}_{\text{struct}}, \mathcal{C}_{\text{null}} \gets$ partition $\mathcal{C}$ by $(s, p)$ canonical key availability\;
$\mathcal{G} \gets$ group $\mathcal{C}_{\text{struct}}$ by canonical key\;
$\mathcal{G}_{\text{multi}} \gets \{g \in \mathcal{G} : |g| \geq 2\}$\;
$\mathcal{R} \gets \mathcal{C}_{\text{null}} \cup \bigcup \{g \in \mathcal{G} : |g| = 1\}$ \tcp*{residual pool: triple-null + singleton}
$\mathcal{G}_{\text{fallback}} \gets \textsc{LLM-Fallback}(\mathcal{R}, q)$ with subject-consistency check\;
\tcp{unclustered members of $\mathcal{R}$ remain as singleton groups in $\mathcal{G}_{\text{fallback}}$}
$\mathcal{V} \gets \emptyset$\;
\ForEach{$g \in \mathcal{G}_{\text{multi}} \cup \mathcal{G}_{\text{fallback}}$}{
    $\mathcal{V} \gets \mathcal{V} \cup \{\arg\max_{f \in g} t_f\}$\;
}
\Return $\mathcal{V}$\;
\end{algorithm}