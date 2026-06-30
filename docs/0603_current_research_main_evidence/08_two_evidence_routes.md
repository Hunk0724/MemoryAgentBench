# 兩條證據路線 — gpt-4o-mini vs gemini(決策用,2026-06-10)

> **用途**:把「用 gpt-4o-mini」與「用 gemini-3.1-flash-lite」兩條 backbone 路線,各自的三層分析(整體 EM / write-time 後 vectorDB 對衝突對的解決狀況 / 失敗題根因)並排,讓我們看清各支持什麼 claim、如何結合。
> **設定**:mem0 chunk 512、L2 凍結 extraction、temp 0。⚠️ **embedder 各自原生**:gpt-4o-mini = OpenAI text-embedding-3-small(benchmark 預設);gemini = Vertex text-embedding-004(我們的設定)。LCA = 全 context、size256、temp 0。
> **分析法**:final-store = replay vector_results 的真實 ADD/UPDATE/DELETE → 最終記憶集;衝突對狀態用**精確全文比對**(mem0 ADD 逐字保留,99% 驗證過)。

---

## 表1 — FC-SH 官方 100 整體 EM
| 方法 | 6k | 32k | 64k | 262k |
|---|---|---|---|---|
| **LCA gemini**(全 context,非破壞,天花板) | **99** | **96** | **94** | **74** |
| **LCA gpt-4o-mini** | **86** | **75** | **62** | (>128k 不適用) |
| mem0 gemini(write-time consolidate) | 93 | 94 | 94 | ⬜ |
| **mem0 gpt-4o-mini** | **37** | **61** | **45** | ⬜(暫停) |

**consolidation 的代價(LCA 天花板 − mem0)= write-time 修改弄壞了多少**:
| backbone | 6k | 32k | 64k |
|---|---|---|---|
| **gpt-4o-mini**(LCA−mem0) | 86−37 = **−49pp** | 75−61 = **−14pp** | 62−45 = **−17pp** |
| **gemini**(LCA−mem0) | 99−93 = **−6pp** | 96−94 = **−2pp** | 94−94 = **0pp** |

→ **弱 model(gpt-4o-mini)做 write-time consolidation 代價巨大(−14~49pp,主因 omission);強 model(gemini)代價小(0~6pp,結構性 verdict)。** 這把兩路線用「成本×表現」釘死:**不做 write-time consolidation(LCA/我們的 query-time)就能省下這個代價。**

---

## 表2 — write-time 後 vectorDB 對「所有衝突對」的解決狀況(final-store vs GT)
| backbone | new_only(✓解決) | old_only | **neither** | both | same-chunk | 總對 |
|---|---|---|---|---|---|---|
| gpt4o 6k | 20% | 16% | **47%** | 7% | 10% | 161 |
| gpt4o 32k | 41% | 23% | 23% | 11% | 2% | 837 |
| gpt4o 64k | 38% | 28% | 26% | 8% | 1% | 1691 |
| **gemini 6k** | **88%** | 1% | 1%(2) | 0% | 10% | 161 |
| gemini 32k | **95%** | 0% | 2%(17) | 1% | 2% | 837 |
| gemini 64k | **95%** | 1% | 3%(48) | 1% | 1% | 1691 |

→ **gpt-4o-mini 只解決 20–41%、毀掉/汙染多數;gemini 解決 88–95%。** gemini 的 neither 雖佔比小,但**絕對數隨 scale 成長:2 → 17 → 48**。

---

## 表3 — FC-SH 官方 100 失敗題的根本原因
| backbone | 總錯(6k/32k/64k) | A 寫時汙染 | B/C 檢索/答題 | no_pair 非衝突 |
|---|---|---|---|---|
| gpt-4o-mini | 63/38/55 | 84%/82%/64% | 1/3/7 | 9/4/13 |
| gemini | **7/6/6** | 71%/83%/50% | 1/1/0 | 1/0/3 |

**A 寫時汙染的具體機制(精確比對)**:
- **gpt-4o-mini**:**omission 主導(75–85%)**——新/正解版根本沒被 ADD(連存都漏);其次 both-ADD(沒判衝突,11–20%);破壞型 DELETE/UPDATE 僅 ~2–4%。
- **gemini**:少數失敗是**乾淨的 conflict verdict 錯**(A4 over-fire 摧毀正解、H2 拒覆蓋),**無 omission**。

---

## 兩條路線各自支持的 claim

### 路線 A — gpt-4o-mini(broad,公平/戲劇/cost)
- 整體差(37/61/45),vectorDB 只解決 20–41%,失敗 64–84% 是寫時汙染,**機制以 omission 為主**。
- **claim**:「**成本可負擔的 model,write-time update component(廣義改記憶庫)不可靠——連存都漏(omission)+ 衝突誤判 → 記憶庫被不可逆汙染 → 表現崩。改在 query-time 對檢索到的少數記憶處理。**」
- **insight**:write-time update = 難任務(全部 fact/無 query/不可逆)→ 弱 model 失敗;query-time = 易任務 → 同 model 成功。
- ✅ 公平(benchmark model)、戲劇(48→96)、cost 對齊。⚠️ 機制不純(主要能力/omission),易被「換好 model」打 → 用 gemini + cost 反駁。

### 路線 B — gemini(narrow,乾淨機制/結構性)
- 整體好(93/94/94),vectorDB 解決 88–95%,但 neither 絕對數 2→17→48(A4 結構性摧毀)。
- **claim**:「**即使強 model 也解決 95%,仍有結構性的少數(隨 scale 成長)被 query-agnostic 不可逆 verdict(A4)摧毀,query-time 救不回。**」
- ✅ 機制乾淨、結構性、擋「換好 model」。⚠️ magnitude 小(須擴充集放大)。

### 一句話對照
> **同樣「毀掉正解(neither)」:gpt-4o-mini 很大(76/191/444)但主要是 omission(能力);gemini 小但純(2/17/48)且是 A4 結構性摧毀。** 兩個 model 的「為什麼」完全不同。

---

## 建議的結合(初步)
- **主故事 = 路線 A(gpt-4o-mini broad + cost)**:公平、戲劇、benchmark 標準。
- **gemini 當支撐**:(a)「連強 model 在 verdict 上都還會錯(A4,結構性)」擋反駁;(b) 昂貴強 model 的 baseline 當 cost 對照。
- **LCA = 天花板對照**:非破壞 + query-time(靠 prompt)就贏 mem0;但 262k 崩(74)→ 需 retrieval(our method)。

## 待補
- ⬜ LCA gpt-4o-mini(size256)— 跑中,補表1 + consolidation 代價。
- ⬜ gemini same-model our-method 對照(93→?)。
- ⬜ mem0 262k(暫停);LCA gemini 262k=74 已有。
