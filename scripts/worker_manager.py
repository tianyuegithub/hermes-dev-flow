#!/usr/bin/env python3
"""
worker_manager.py — Manager 调度器（临时 Pod 唯一模式，2026-07-30 重写）

三层架构:
  Manager (本脚本) → BLPOP dev-flow:queue → 创建一次性 Worker Pod → 监控 → 清理
  Node   (K8s node) → 宿主机
  Worker (临时 Pod) → 一个任务一个 Pod，用完即删（热池已废止）

安全基线:
  runAsNonRoot + 禁特权提升 + drop ALL caps + 资源限额 + activeDeadlineSeconds
  SSH key 只读挂载（应为仅仓库范围的 deploy key，见 README 警告）

用法: python3 worker_manager.py [--once]
环境: REDIS_HOST/REDIS_PORT/NAMESPACE/WORKER_IMAGE/ANTHROPIC_BASE_URL/
      MAX_TURNS/POD_TIMEOUT_SECONDS
"""
import os, sys, json, subprocess, time

REDIS_HOST = os.environ.get("REDIS_HOST", "redis.infra.svc.cluster.local")
REDIS_PORT = os.environ.get("REDIS_PORT", "6379")
NAMESPACE = os.environ.get("NAMESPACE", "dev-flow")
WORKER_IMAGE = os.environ.get("WORKER_IMAGE", "ghcr.io/tianyuegithub/hermes-dev-flow/worker:latest")
ANTHROPIC_BASE_URL = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
MAX_TURNS = os.environ.get("MAX_TURNS", "300")
POD_TIMEOUT = int(os.environ.get("POD_TIMEOUT_SECONDS", "1800"))
QUEUE_KEY = os.environ.get("QUEUE_KEY", "dev-flow:queue")


# ── 纯函数（可测试） ─────────────────────────────────────────

def parse_blpop(raw: str):
    """解析 redis-cli BLPOP 输出 → task_id 或 None。

    兼容 raw 模式（管道）两行输出与交互模式带序号/引号输出。
    """
    lines = [l.strip() for l in raw.strip().split("\n") if l.strip()]
    if not lines:
        return None
    value = lines[-1]
    # 交互模式: '2) "task-xxx"' → 去掉序号和引号
    if ") " in value:
        value = value.split(") ", 1)[1]
    return value.strip('"')


def build_pod_spec(task_id: str, repo_url: str) -> dict:
    """构造一次性 Worker Pod spec（纯函数，可测试）。"""
    pod_name = f"worker-{task_id[-12:]}"
    return {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {
            "name": pod_name,
            "namespace": NAMESPACE,
            "labels": {"app": "dev-flow-worker", "task-id": task_id, "ephemeral": "true"},
        },
        "spec": {
            "restartPolicy": "Never",
            "activeDeadlineSeconds": POD_TIMEOUT,
            "securityContext": {
                "runAsNonRoot": True,
                "runAsUser": 1001,  # 镜像内 worker 用户 uid（node 用户占 1000）
                "fsGroup": 1001,
            },
            "containers": [{
                "name": "worker",
                "image": WORKER_IMAGE,
                "imagePullPolicy": "Always",
                "securityContext": {
                    "allowPrivilegeEscalation": False,
                    "capabilities": {"drop": ["ALL"]},
                },
                "resources": {
                    "requests": {"cpu": "500m", "memory": "1Gi"},
                    "limits": {"cpu": "2", "memory": "4Gi"},
                },
                "env": [
                    {"name": "TASK_ID", "value": task_id},
                    {"name": "REPO_URL", "value": repo_url},
                    {"name": "REDIS_HOST", "value": REDIS_HOST},
                    {"name": "REDIS_PORT", "value": REDIS_PORT},
                    {"name": "MAX_TURNS", "value": MAX_TURNS},
                    {"name": "MODE", "value": "oneshot"},
                    {"name": "ANTHROPIC_BASE_URL", "value": ANTHROPIC_BASE_URL},
                    {"name": "ANTHROPIC_AUTH_TOKEN", "valueFrom": {
                        "secretKeyRef": {"name": "dev-flow-secrets", "key": "ANTHROPIC_AUTH_TOKEN"}}},
                    {"name": "OPENAI_API_KEY", "valueFrom": {
                        "secretKeyRef": {"name": "dev-flow-secrets", "key": "OPENAI_API_KEY",
                                         "optional": True}}},
                ],
                "volumeMounts": [{
                    "name": "ssh-key",
                    "mountPath": "/home/worker/.ssh/id_rsa",
                    "subPath": "id_rsa",
                    "readOnly": True,
                }],
            }],
            "volumes": [{
                "name": "ssh-key",
                "secret": {"secretName": "dev-flow-secrets", "defaultMode": 256},
            }],
        },
    }


# ── 基础设施调用 ──────────────────────────────────────────────

def redis_cmd(*args) -> str:
    result = subprocess.run(
        ["redis-cli", "-h", REDIS_HOST, "-p", str(REDIS_PORT)] + list(args),
        capture_output=True, text=True, timeout=10,
    )
    return result.stdout.strip()


# ── K8s 访问：集群内走 REST（零 kubectl 依赖），本地调试用 kubectl ──

SA_TOKEN_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/token"
SA_CA_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"


def in_cluster() -> bool:
    return os.path.exists(SA_TOKEN_PATH)


def k8s_request(method: str, path: str, body: dict = None) -> dict:
    """集群内直接调 K8s API（ServiceAccount token，无需 kubectl）。"""
    import ssl, urllib.request
    with open(SA_TOKEN_PATH) as f:
        token = f.read().strip()
    ctx = ssl.create_default_context(cafile=SA_CA_PATH)
    req = urllib.request.Request(
        f"https://kubernetes.default.svc{path}",
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, context=ctx, timeout=30) as resp:
        raw = resp.read().decode()
    return json.loads(raw) if raw else {}


def kubectl(*args, check: bool = False) -> subprocess.CompletedProcess:
    result = subprocess.run(["kubectl"] + list(args), capture_output=True, text=True)
    if check and result.returncode != 0:
        raise RuntimeError(f"kubectl {' '.join(args)} 失败: {result.stderr.strip()}")
    return result


def get_repo_url(task_id: str) -> str:
    """从 Redis spec 读 repo_url。"""
    raw = redis_cmd("GET", f"spec:{task_id}")
    try:
        return json.loads(raw).get("repo_url", "")
    except Exception:
        return ""


def create_worker_pod(task_id: str, repo_url: str) -> str:
    spec = build_pod_spec(task_id, repo_url)
    pod_name = spec["metadata"]["name"]
    if in_cluster():
        try:
            k8s_request("POST", f"/api/v1/namespaces/{NAMESPACE}/pods", spec)
        except Exception as e:
            raise RuntimeError(f"创建 Pod 失败: {e}")
    else:
        yaml_path = f"/tmp/{pod_name}.json"
        with open(yaml_path, "w") as f:
            json.dump(spec, f, indent=2)
        kubectl("apply", "-f", yaml_path, check=True)  # 失败即抛，不再静默
    return pod_name


def get_pod_phase(pod_name: str) -> str:
    if in_cluster():
        try:
            pod = k8s_request("GET", f"/api/v1/namespaces/{NAMESPACE}/pods/{pod_name}")
            return pod.get("status", {}).get("phase", "Unknown")
        except Exception:
            return "Unknown"
    result = kubectl("get", "pod", pod_name, "-n", NAMESPACE,
                     "-o", "jsonpath={.status.phase}")
    return result.stdout.strip()


def get_pod_logs(pod_name: str, tail: int = 50) -> str:
    if in_cluster():
        try:
            import ssl, urllib.request
            with open(SA_TOKEN_PATH) as f:
                token = f.read().strip()
            ctx = ssl.create_default_context(cafile=SA_CA_PATH)
            req = urllib.request.Request(
                f"https://kubernetes.default.svc/api/v1/namespaces/{NAMESPACE}"
                f"/pods/{pod_name}/log?tailLines={tail}",
                headers={"Authorization": f"Bearer {token}"},
            )
            with urllib.request.urlopen(req, context=ctx, timeout=30) as resp:
                return resp.read().decode()
        except Exception as e:
            return f"(读取日志失败: {e})"
    result = kubectl("logs", pod_name, "-n", NAMESPACE, f"--tail={tail}")
    return result.stdout


def cleanup_pod(pod_name: str, force: bool = False):
    if in_cluster():
        try:
            body = {"gracePeriodSeconds": 0} if force else None
            k8s_request("DELETE",
                        f"/api/v1/namespaces/{NAMESPACE}/pods/{pod_name}", body)
        except Exception as e:
            print(f"[manager] 清理 Pod 失败（忽略）: {e}")
        return
    args = ["delete", "pod", pod_name, "-n", NAMESPACE, "--ignore-not-found"]
    if force:
        args.append("--force")
    kubectl(*args)


def mark_failed(task_id: str, reason: str):
    redis_cmd("SET", f"status:{task_id}", "failed")
    redis_cmd("SET", f"error:{task_id}", reason)
    print(f"[manager] ❌ {task_id}: {reason}")


def dispatch(task_id: str):
    """单个任务的完整生命周期：建 Pod → 监控 → 清理。"""
    repo_url = get_repo_url(task_id)
    if not repo_url:
        mark_failed(task_id, "spec 中无 repo_url")
        return "failed"

    print(f"[manager] 收到任务: {task_id} → {repo_url}")
    redis_cmd("SET", f"status:{task_id}", "dispatched")

    try:
        pod_name = create_worker_pod(task_id, repo_url)
    except Exception as e:  # 任何基础设施错误都不能让 Manager 崩溃（曾因此 crashloop）
        mark_failed(task_id, str(e))
        return "failed"

    print(f"[manager] Worker Pod: {pod_name} (超时 {POD_TIMEOUT}s)")

    start = time.time()
    phase = "Timeout"
    while time.time() - start < POD_TIMEOUT + 60:
        phase = get_pod_phase(pod_name)
        if phase in ("Succeeded", "Failed"):
            break
        time.sleep(5)
    else:
        phase = "Timeout"

    if phase == "Succeeded":
        print(f"[manager] ✅ {task_id} 完成")
        subprocess.run([sys.executable,
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "notify.py"),
            "task_done", task_id], capture_output=True)
    else:
        mark_failed(task_id, f"Worker Pod {phase}")
        print(get_pod_logs(pod_name, tail=50))

    cleanup_pod(pod_name, force=(phase == "Timeout"))
    return phase


def run_loop():
    print(f"[manager] 启动，监听 {QUEUE_KEY} (image={WORKER_IMAGE})")
    while True:
        raw = redis_cmd("BLPOP", QUEUE_KEY, "5")
        task_id = parse_blpop(raw)
        if task_id:
            dispatch(task_id)


if __name__ == "__main__":
    if "--once" in sys.argv:
        raw = redis_cmd("BLPOP", QUEUE_KEY, "5")
        task_id = parse_blpop(raw)
        if task_id:
            sys.exit(0 if dispatch(task_id) == "Succeeded" else 1)
        print("[manager] 队列空，退出")
    else:
        run_loop()
