#!/bin/bash
# ============================================================
# redis_helper.sh — Hermes 端 Redis 操作封装
# ============================================================
# 用法:
#   redis_helper.sh set    <key> <value>
#   redis_helper.sh get    <key>
#   redis_helper.sh del    <key>
#   redis_helper.sh exists <key>
#   redis_helper.sh rpush  <queue> <value>
#   redis_helper.sh blpop  <queue> <timeout>
#   redis_helper.sh status <task_id>   ← 快捷：读 status:<task_id>
#   redis_helper.sh output <task_id>   ← 快捷：读 output:<task_id>
#   redis_helper.sh spec   <task_id>   ← 快捷：读 spec:<task_id>
#   redis_helper.sh hb     <task_id>   ← 快捷：读 heartbeat:<task_id>
# ============================================================
set -euo pipefail

REDIS_HOST="${REDIS_HOST:-192.168.31.173}"
REDIS_PORT="${REDIS_PORT:-32319}"

CMD="${1:?}"
shift

case "$CMD" in
  set)    redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" SET "$1" "$2" ;;
  get)    redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" GET "$1" ;;
  del)    redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" DEL "$1" ;;
  exists) redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" EXISTS "$1" ;;
  rpush)  redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" RPUSH "$1" "$2" ;;
  blpop)  redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" BLPOP "$1" "${2:-0}" ;;
  status) redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" GET "status:$1" ;;
  output) redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" GET "output:$1" ;;
  spec)   redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" GET "spec:$1" ;;
  hb)     redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" GET "heartbeat:$1" ;;
  *) echo "未知命令: $CMD"; exit 1 ;;
esac
