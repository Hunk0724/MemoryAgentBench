#!/bin/bash
# Stop the Neo4j container (data persists in $HOME/neo4j-data/).
# Run after mem0g experiments finish to release memory + ports.

set -e

if docker ps --format "{{.Names}}" | grep -q "^neo4j-mem0g$"; then
  docker stop neo4j-mem0g
  echo "[neo4j] stopped (data persisted in \$HOME/neo4j-data/)"
else
  echo "[neo4j] not running"
fi
