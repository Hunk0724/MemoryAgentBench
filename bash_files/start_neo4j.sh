#!/bin/bash
# Start the Neo4j container for mem0g experiments.
# Idempotent: if container exists (stopped), just start it; if not, create.
# Resource discipline: only run during mem0g experiments, stop afterwards.
# See docs/infrastructure/neo4j_setup.md.

set -e

if docker ps --format "{{.Names}}" | grep -q "^neo4j-mem0g$"; then
  echo "[neo4j] already running"
  exit 0
fi

if docker ps -a --format "{{.Names}}" | grep -q "^neo4j-mem0g$"; then
  echo "[neo4j] container exists, starting…"
  docker start neo4j-mem0g
else
  echo "[neo4j] creating container…"
  docker run -d --name neo4j-mem0g \
    -p 7474:7474 -p 7687:7687 \
    -v "$HOME/neo4j-data:/data" \
    -e NEO4J_AUTH=neo4j/mem0gpassword \
    -e NEO4J_PLUGINS='["apoc"]' \
    neo4j:5-community
fi

echo "[neo4j] waiting for ready (timeout 90s)…"
for i in $(seq 1 30); do
  if curl -s http://localhost:7474 > /dev/null 2>&1; then
    echo "[neo4j] ready at http://localhost:7474 (bolt://localhost:7687)"
    exit 0
  fi
  sleep 3
done
echo "[neo4j] timed out waiting for ready, check 'docker logs neo4j-mem0g'"
exit 1
