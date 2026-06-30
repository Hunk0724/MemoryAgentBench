# 漂亮 case — ingestion-time 不可逆裁決出錯(intro 直接證據)

> 來源:mem0 gpt-4o-mini FC-SH 6k(L2 凍結 extraction、Vertex embed、temp 0)。log:`logs/sh_6k_gpt4omini_l2/update_decision.jsonl` + vector_results。
> **⚠️ 2026-06-10 更正**:初版誤把 DELETE 的 log text 讀成「刪掉新 fact」。實查證實 **DELETE 只對既有記憶做**(使用者指正正確);用 **final-store 真值(replay vector_results)** 重新歸因。
> final-store 真值(cross-chunk 145 對,排除 same-chunk):**new_only 59 / neither 52 / old_only 27 / both 7**。

## 類型 A ★ neither(該 UPDATE 卻把舊版 DELETE、又沒存新版 → 槽位全空)= 52 例(最多!)

**機制**:新反事實到達、與既有舊版衝突時,update LLM **選擇 DELETE 既有記憶,而非 UPDATE 成新版**,且新版未被 ADD → **新舊兩版全失** → query 檢索無此 slot → 答不出。**不可逆、且把正解徹底摧毀。**

### ★ case Germany(完整 trace,已驗證)
- chunk1:`ADD` id=b309ecdb「Germany in **Europe**」(舊,序號 41)
- chunk11:新「Germany in **Africa**」(正解,序號 435)到達 → update LLM 對既有 id=b309ecdb 輸出 `{"event":"DELETE","text":"...Africa"}` → **刪掉 Europe 記憶、未存 Africa**
- **final-store:Germany slot 全空(neither)** → query「Germany 在哪洲」→ 無資訊
- **應為**:UPDATE Europe→Africa(FC newer wins)。**實際**:DELETE 舊 + 丟新。

→ 這是「該 UPDATE 卻誤刪」最乾淨的例。**52 例同型**(如「Japan 官方語言 Japanese→Swedish」「goaltender ice hockey→pesäpallo」皆 neither)。

## 類型 B — old_only(留舊丟新,LLM 不更新)= 27 例(H2 型)

**機制**:新反事實到達,既有舊世界事實在候選,LLM 卻 **NONE(不 UPDATE)** → 留舊、丟新 → 答舊。
- 例「Australia 在哪洲」:舊=Oceania(chunk1 ADD),新=South America 到達 → mem0 不更新 → final old_only → 答 **Oceania ❌**(正解 South America)。

## 類型 C — both(新舊都 ADD,沒判成衝突)= 7 例(H1 型)
- 候選沒取到舊版 → LLM 把新版當無關直接 ADD → 兩版並存 → context 有衝突。

---

## 論述價值(intro)
**最有力 = 類型 A(neither,52 例)**:mem0 面對衝突時,**不可逆地把正確答案連同舊版一起摧毀**(該 UPDATE 卻 DELETE),query 時徹底救不回。這比「答錯一個值」更震撼——**記憶系統把學到的事實刪光了**。配合類型 B(被 LLM 判斷影響留舊)、類型 C(誤判無關都 ADD),三型都源於「ingestion-time、query-agnostic、不可逆」。

## ready material / 待補
- ✅ trace 三元組可抽(update_prompt=input、parsed_actions=output、final-store=結果)。
- ⬜ 每型抽 1–2 個完整 trace 當 paper figure。
- ⬜ LightMem 的 offline-Delete 同型 case(env 已就緒)。
