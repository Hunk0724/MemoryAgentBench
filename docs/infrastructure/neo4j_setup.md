# Neo4j 本地化(for mem0g)

> 建立日期:2026-05-24(2026-05-29 補充 lifecycle 慣例)
> 目的:讓任何人 5 分鐘內把 mem0g 需要的 Neo4j 跑起來

mem0g 需要圖資料庫。本 repo 用 Docker 跑 Neo4j 5 community,本地單機。

## ⚠️ Lifecycle 慣例:用完即關

**只在跑 mem0g 實驗時開,跑完關**(釋放記憶體 + ports,資料保留在 `$HOME/neo4j-data/`)。

```bash
bash bash_files/start_neo4j.sh    # 跑 mem0g 前
bash bash_files/stop_neo4j.sh     # 跑完 mem0g 後
```

LCA / mem0(純向量)/ HippoRAG 都不需要 Neo4j。

---

## 1. 啟動指令

```bash
docker run -d --name neo4j-mem0g \
  -p 7474:7474 -p 7687:7687 \
  -v $HOME/neo4j-data:/data \
  -e NEO4J_AUTH=neo4j/mem0gpassword \
  -e NEO4J_PLUGINS='["apoc"]' \
  neo4j:5-community
```

啟動約 30 秒。**驗證**:

```bash
curl -s http://localhost:7474 | head -3       # 應該回 HTML
docker logs neo4j-mem0g 2>&1 | grep "Started" # 應該見到 "Started."
```

連線參數:
- Bolt URI: `neo4j://localhost:7687`
- Username: `neo4j`
- Password: `mem0gpassword`
- Browser UI: http://localhost:7474

對應的 yaml(已寫):
- [Structure_rag_mem0g_gemini-2.5-flash-lite.yaml](../../configs/agent_conf/RAG_Agents/Gemini/Structure_rag_mem0g_gemini-2.5-flash-lite.yaml) 的 `mem0_config.graph_store`

---

## 2. 必要 index(一次性設置)

mem0g 的 Cypher query 都帶 `user_id` filter([mem0/memory/graph_memory.py:107, 297](../../mem0/memory/graph_memory.py#L107))。為了 query 快:

```bash
docker exec -it neo4j-mem0g cypher-shell -u neo4j -p mem0gpassword <<'EOF'
CREATE INDEX entity_user_id IF NOT EXISTS FOR (n:`__Entity__`) ON (n.user_id);
CREATE INDEX entity_name_user_id IF NOT EXISTS FOR (n:`__Entity__`) ON (n.name, n.user_id);
EOF
```

(註:mem0g 用 `__Entity__` 作為 label,需確認實際跑後 schema,可能要調整 label 名)

---

## 3. 資料保留 vs 清空

### 推薦:`user_id` namespace 隔離(不 destructive 清空)

mem0g 跑時用 `user_id = f"context_{context_id}_{sub_dataset}"` (見 [agent.py:583](../../agent.py#L583)),每個子集自動隔離。**所以同一個 Neo4j 容器可以裝下所有實驗的圖**,事後 forensics 直接 query:

```cypher
MATCH (n)-[r]->(m) 
WHERE n.user_id STARTS WITH 'context_0_factconsolidation_mh_6k'
RETURN n.name, type(r), m.name
LIMIT 50;
```

### 何時要清空

只在以下情況:
- 跑性能 benchmark 要保證 query latency 公平(本研究不適用)
- 磁碟壓力大(FC 800 題的圖預估 < 1 GB,通常不必擔心)
- 開新一輪實驗想完全乾淨(可選,但建議保留歷史快照)

清空指令:

```bash
docker exec neo4j-mem0g cypher-shell -u neo4j -p mem0gpassword "MATCH (n) DETACH DELETE n;"
```

---

## 4. 容器管理

```bash
docker stop neo4j-mem0g           # 停止(資料仍在 $HOME/neo4j-data)
docker start neo4j-mem0g          # 重啟
docker rm -f neo4j-mem0g          # 移除(只刪容器,資料留)
rm -rf $HOME/neo4j-data           # 完全清除資料(不可逆)
```

---

## 5. 資源使用預估

| 指標 | 值 |
|---|---|
| 記憶體 | ~1-2 GB(community 預設 heap 512MB + page cache 512MB) |
| 磁碟(完整 pilot 跑完) | < 1 GB(FC 800 題 × 5 model × mem0g) |
| GPU | 0(Neo4j 純 CPU) |
| 啟動時間 | ~30 秒 |

---

## 6. 與其他文件的關係

- 方法論層面對比 mem0g 用 Neo4j vs Graphiti 用 Neo4j 的差異:[[../baseline_methods/baseline_methods_paper_vs_impl.md]]
- pilot 跑法:[[../experiments/pilots/mem0_mem0g_pilot_plan.md]]
- mem0g 的 Cypher 怎麼寫:[mem0/memory/graph_memory.py](../../mem0/memory/graph_memory.py)

---

## 7. Troubleshooting

| 問題 | 處理 |
|---|---|
| `docker: command not found` | 安裝 Docker(`apt install docker.io` 或官方安裝) |
| `port 7687 already in use` | 改用其他 port,並同步改 yaml `graph_store.config.url` |
| `connection refused` 雖然容器在跑 | `docker logs neo4j-mem0g` 看是否還在 startup,等 30-60 秒 |
| mem0g 寫入很慢 | 加 §2 的 index;確認 Docker 沒被資源限制 |
| `auth failed` | 確認 password 跟 yaml 內 `graph_store.config.password` 一致 |
