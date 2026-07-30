#!/usr/bin/env python3
"""
progress_subscribe.py — L1 进度订阅器（Hermes 端调用）

用法: python3 progress_subscribe.py <task_id> [--timeout 300]
实时打印 worker 执行进度，直到 status 变为 done/blocked/escalate
"""
import sys, subprocess, time, json, os

REDIS_HOST = os.environ.get("REDIS_HOST", "127.0.0.1")
REDIS_PORT = os.environ.get("REDIS_PORT", "6379")

def subscribe(task_id: str, timeout: int = 300):
    """订阅任务进度，实时打印"""
    channel = f"task:progress:{task_id}"
    print(f"[subscribe] 监听 {channel} (timeout={timeout}s)")
    print(f"[subscribe] {'─' * 40}")

    proc = subprocess.Popen(
        ["redis-cli", "-h", REDIS_HOST, "-p", str(REDIS_PORT),
         "SUBSCRIBE", channel],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )

    start = time.time()
    while time.time() - start < timeout:
        line = proc.stdout.readline()
        if not line:
            break

        # redis-cli 输出格式: message\n<channel>\n<content>
        if "message" in line:
            # 下一行是 channel，再下一行是 content
            proc.stdout.readline()  # channel
            content = proc.stdout.readline().strip()
            if content:
                print(f"  {content}")

        # 检查是否完成
        status = subprocess.run(
            ["redis-cli", "-h", REDIS_HOST, "-p", str(REDIS_PORT),
             "GET", f"status:{task_id}"],
            capture_output=True, text=True
        ).stdout.strip()

        if status in ("done", "blocked", "escalate"):
            print(f"  {'─' * 40}")
            print(f"[subscribe] 任务结束: {status}")
            break

    proc.terminate()
    print(f"[subscribe] 完成")

if __name__ == "__main__":
    task_id = sys.argv[1]
    timeout = int(sys.argv[3]) if len(sys.argv) > 3 and sys.argv[2] == "--timeout" else 300
    subscribe(task_id, timeout)
