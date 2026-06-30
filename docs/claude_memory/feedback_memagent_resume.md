---
name: MemoryAgentBench 支援 resume,別刪 partial output
description: 跑到一半中斷時,main.py 已內建 resume 機制,不要為了 "重跑" 手動刪 partial 結果檔
type: feedback
originSessionId: 6d64af16-d2ac-474e-967a-04ad47a46836
---
`MemoryAgentBench/main.py` 每跑完一題就 `save_results_to_file`(freq=1),`load_existing_results` 會讀既有 output 當 resume 起點,下次跑同條命令就從 `last_processed_query_id+1` 接續。

**Why:** 2026-04-24 我對 gpt-4o-mini TPM crash 的 3 個 partial 檔案手動 `rm`,等於丟 70 題已完成進度,使用者明確指出 "可以接續跑剩下的就好",我當時不知道 main.py 內建 resume。

**How to apply:** 當 MemoryAgentBench 的 run 中斷(crash / SSH 斷 / rate limit):
- 預設做法:**原 output JSON 保留不動**,直接重跑同樣的 `python main.py --agent_config ... --dataset_config ...`,會自動 skip 已跑題目
- 只有在想徹底重跑(例如改了 prompt、模型行為變)才刪檔;或 pass `--force` 跳過 context-level skip
- 對 OpenAI / Gemini batch,配合 `OpenAI(max_retries=20)` + retry-with-backoff,基本能自動穿過 TPM/RPM 短期限速,不需要手動介入
