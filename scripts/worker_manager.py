#!/usr/bin/env python3
"""
worker_manager.py — Manager 调度器（替代 worker-entrypoint.sh 的 BLPOP）

三层架构:
  Manager (本脚本) → 从 Redis 取任务 → 创建 Worker Pod → 监控 → 清理
  Node   (K8s node)  → 宿主机，运行 Worker 容器
  Worker (临时 Pod)  → 一个任务一个 Pod，用完即删

用法: python3 worker_manager.py [--once]
"""
import os, sys, json, subprocess, time, signal
from datetime import datetime

REDIS_HOST = os.environ.get("REDIS_HOST", "redis.infra.svc.cluster.local")
REDIS_PORT = os.environ.get("REDIS_PORT", "6379")
NAMESPACE = os.environ.get("NAMESPACE", "dev-flow")
WORKER_IMAGE = os.environ.get("WORKER_IMAGE", "192.168.31.200:8080/dev-flow/worker:latest")

def redis_cmd(*args) -> str:
    result = subprocess.run(
        ["redis-cli", "-h", REDIS_HOST, "-p", REDIS_PORT] + list(args),
        capture_output=True, text=True, timeout=10
    )
    return result.stdout.strip()

def create_worker_pod(task_id: str) -> str:
    """通过 kubectl 创建临时 Worker Pod"""
    pod_name = f"worker-{task_id[-12:]}"
    spec = {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {
            "name": pod_name,
            "namespace": NAMESPACE,
            "labels": {"app": "dev-flow-worker", "task-id": task_id, "ephemeral": "true"}
        },
        "spec": {
            "restartPolicy": "Never",
            "containers": [{
                "name": "worker",
                "image": WORKER_IMAGE,
                "env": [
                    {"name": "TASK_ID", "value": task_id},
                    {"name": "REDIS_HOST", "value": REDIS_HOST},
                    {"name": "REDIS_PORT", "value": REDIS_PORT},
                    {"name": "MODE", "value": "oneshot"},  # 一次性模式
                    {"name": "ANTHROPIC_AUTH_TOKEN", "valueFrom": {"secretKeyRef": {"name": "dev-flow-secrets", "key": "ANTHROPIC_AUTH_TOKEN"}}},
                    {"name": "ANTHROPIC_BASE_URL", "value": "https://open.bigmodel.cn/api/anthropic"},
                    {"name": "OPENAI_API_KEY", "valueFrom": {"secretKeyRef": {"name": "dev-flow-secrets", "key": "OPENAI_API_KEY", "optional": True}}},
                ],
                "volumeMounts": [{"name": "ssh-key", "mountPath": "/home/worker/.ssh/id_rsa", "subPath": "id_rsa"}]
            }],
            "volumes": [{"name": "ssh-key", "secret": {"secretName": "dev-flow-secrets", "defaultMode": 256}}]
        }
    }

    # 写临时 YAML 并 apply
    yaml_path = f"/tmp/{pod_name}.yaml"
    with open(yaml_path, "w") as f:
        json.dump(spec, f, indent=2)

    subprocess.run(["kubectl", "apply", "-f", yaml_path], capture_output=True)
    return pod_name

def monitor_worker(pod_name: str, task_id: str, timeout: int = 600):
    """监控 Worker 完成 → 读取 output → 删除 Pod"""
    start = time.time()
    while time.time() - start < timeout:
        result = subprocess.run(
            ["kubectl", "get", "pod", pod_name, "-n", NAMESPACE,
             "-o", "jsonpath={.status.phase}"],
            capture_output=True, text=True
        )
        phase = result.stdout.strip()

        if phase in ("Succeeded", "Failed"):
            # 读取 output
            output = redis_cmd("GET", f"output:{task_id}")
            print(f"[manager] Worker {pod_name}: {phase}")
            print(f"[manager] Output: {output[:200] if output else '(空)'}")

            # 通知
            subprocess.run([sys.executable,
                os.path.expanduser("~/Codes/ai-dev-flow/scripts/notify.py"),
                "task_done", task_id], capture_output=True)

            # 清理
            subprocess.run(["kubectl", "delete", "pod", pod_name, "-n", NAMESPACE],
                         capture_output=True)
            return phase

        time.sleep(5)

    print(f"[manager] 超时，强制删除 {pod_name}")
    subprocess.run(["kubectl", "delete", "pod", pod_name, "-n", NAMESPACE, "--force"],
                 capture_output=True)
    return "timeout"

def run_loop():
    """主循环：从队列取任务 → 创建 Worker → 监控 → 清理"""
    queue_key = "dev-flow:queue"
    print(f"[manager] 启动，监听 {queue_key}")

    while True:
        # BLPOP 获取任务
        result = redis_cmd("BLPOP", queue_key, "5")
        if not result:
            continue

        lines = result.split("\n")
        task_id = lines[1] if len(lines) > 1 else result

        print(f"[manager] 收到任务: {task_id}")
        redis_cmd("SET", f"status:{task_id}", "dispatched")

        pod_name = create_worker_pod(task_id)
        print(f"[manager] Worker Pod: {pod_name}")

        monitor_worker(pod_name, task_id)

if __name__ == "__main__":
    if "--once" in sys.argv:
        # 处理一个任务后退出
        result = redis_cmd("BLPOP", "dev-flow:queue", "5")
        if result:
            task_id = result.split("\n")[1]
            pod_name = create_worker_pod(task_id)
            monitor_worker(pod_name, task_id)
    else:
        run_loop()
