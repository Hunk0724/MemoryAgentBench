# GX10 Report-back — Subject-consistency guard ablation (2026-07-18)

> 回應 [`gx10_handoff_2026-07-18.md`](gx10_handoff_2026-07-18.md)。GX10 端完成 **Task A(cache 檢查)+ Task B(離線 predictor,零 API cost)**;Task C(實跑 ablation)**尚未跑**(pending Mac 決定是否需要實測確認)。

## Task A — grouping cache 檢查(全 8 backbone 都在)

| backbone | grouping_no_p5 | grouping_p3_only | triple | subject |
|:--|:-:|:-:|:-:|:-:|
| gemma3-1b | ✓ | ✓ | ✓ | ✓ |
| gemma3-4b | ✓ | ✓ | ✓ | ✓ |
| gemma3-12b | ✓ | ✓ | ✓ | ✗ |
| gemma3-27b | ✓ | ✓ | ✓ | ✗ |
| gemma2-9b | ✓ | ✗ | ✓ | ✓ |
| llama3.1-8b | ✓ | ✗ | ✓ | ✓ |
| qwen2.5-7b | ✓ | ✗ | ✓ | ✓ |
| mistral-7b | ✓ | ✗ | ✓ | ✓ |

全 8 個都有 `grouping_cache_no_p5_6k.json` + `triple_cache_p1_6k.json`(predictor 最低需求)。gemma3-12b/27b 缺 subject cache,但 predictor 用它當 fallback、主要讀 triple → 不影響。**這批檔案(788K 全部)已隨本 commit push,Mac 端可直接複跑 Task B。**

## Task B — 離線 predictor 結果(全 8 backbone × FC-SH 6k has_pair)

`Predicted Δ_guard-off = HURT(guard 誤傷)− save(guard 有救)`;**負值 = guard 有幫助**。

| backbone | clusters | reject% | save | HURT | **pred_Δ** | 信心 |
|:--|:-:|:-:|:-:|:-:|:-:|:--|
| gemma3-1b | 0 | 0.0% | 0 | 0 | +0 | — (guard no-op, 1B 幾乎不產 P3 cluster) |
| gemma3-4b | 5 | 80.0% | 0 | 2 | +2 | 低(樣本小) |
| gemma3-12b | 1 | 100.0% | 1 | 0 | −1 | 低(樣本小) |
| gemma3-27b | 25 | 88.0% | 4 | 0 | **−4** | 中 |
| gemma2-9b | 27 | 70.4% | 1 | 2 | +1 | 中 |
| llama3.1-8b | 193 | 80.3% | 28 | 26 | **−2** | **高**(高活性) |
| qwen2.5-7b | 33 | 66.7% | 4 | 1 | **−3** | 中 |
| mistral-7b | 140 | 82.9% | 16 | 11 | **−5** | **高**(高活性) |

## 判讀與建議

1. **weak/cross-family 上 guard 大多 net-positive(有幫助)**:gemma3-27b −4、mistral −5、qwen −3、llama −2、gemma3-12b −1。只有 gemma3-4b(+2)、gemma2-9b(+1)偏 guard-off,且都是小樣本/低活性。

2. **高活性 model(最可信)一致說 guard 幫忙**:llama(193 clusters,−2)、mistral(140,−5)。→ 弱 LLM 過度提議亂 cluster,guard 正好擋掉,**弱端反而更需要 guard**(與 strong-tier no-op 的觀察互補)。

3. **決策矩陣 → Option B(keep guard on,ablation 進 appendix)**:有 3 個 cell pred_Δ ≤ −3(mistral −5、gemma3-27b −4、qwen −3),不符合 Option A 的「全部 ≥ −1」。guard 在弱/cross-family 上**不是 no-op、也不是淨害**,而是淨益。

4. **caveat**:predictor magnitude ±3pp(Mac 於 gpt-4o-mini 驗證 direction 3/4、magnitude ±3pp)。若要 confident 定 Option B,可對最負的幾格(mistral / gemma3-27b / qwen)實跑 Task C 確認(GX10 可跑,~$0.30 + ~1hr,待 approve)。

## 狀態

- ✅ Task A + B 完成(零成本);Task B cache 已 commit,Mac 可複跑。
- ⏸ Task C(實跑 guard-off ablation)pending — 待決定是否需要實測確認 predictor。
