#!/usr/bin/env python3
"""
progress_push.py — L1 Pod 进度推送器（worker-entrypoint 内调用）

用法（在 entrypoint 里）:
  python3 /usr/local/bin/progress_push.py <task_id> "git prepare done"
  python3 /usr/local/bin/progress_push.py <task_id> "claude code starting"
"""
import sys, subprocess, os

REDIS_HOST = os.environ.get("REDIS_HOST", "redis.infra.svc.cluster.local")
REDIS_PORT = os.environ.get("REDIS_PORT", "6379")

def push(task_id: str, message: str):
    """推送进度到 Redis Pub/Sub"""
    channel = f"task:progress:{task_id}"
    subprocess.run([
        "redis-cli", "-h", REDIS_HOST, "-p", str(REDIS_PORT),
        "PUBLISH", channel, message
    ], capture_output=True)

if __name__ == "__main__":
    task_id = sys.argv[1]
    message = sys.argv[2] if len(sys.argv) > 2 else ""
    push(task_id, message)
