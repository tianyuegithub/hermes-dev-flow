#!/usr/bin/env python3
"""
state.py — L0 任务状态管理（本地 JSON 文件）
=============================================
用法:
  state.py init   <task_id> <task_type> <repo_url>
  state.py get    <task_id>
  state.py set    <task_id> <field> <value>
  state.py trans  <task_id> <new_status>  # 状态转换（校验合法性）
  state.py list                            # 列出所有任务

L0 存储: <DEV_FLOW_HOME>/.hermes/tasks/<task_id>/state.json
（根目录解析见 scripts/paths.py：DEV_FLOW_HOME env > 包安装目录）
L1 迁移: 换 Redis 后端，CLI 接口不变。

状态机（合法转换）:
  CREATED     → PLANNING, CANCELLED
  PLANNING    → GATE_PENDING, CANCELLED
  GATE_PENDING→ EXECUTING, CANCELLED
  EXECUTING   → VERIFY_GATE, ESCALATED, FAILED, CANCELLED
  ESCALATED   → EXECUTING, CANCELLED
  VERIFY_GATE → DONE, EXECUTING, FAILED, CANCELLED
"""

import json, os, sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths

BASE_DIR = paths.tasks_dir()

QUIET = False  # 全局静默标志

VALID_TRANSITIONS = {
    "CREATED":     ["PLANNING", "GATE_PENDING", "CANCELLED"],  # GATE_PENDING 是快捷路径（intake 已做规划）
    "PLANNING":    ["GATE_PENDING", "CANCELLED"],
    "GATE_PENDING":["EXECUTING", "CANCELLED"],
    "EXECUTING":   ["VERIFY_GATE", "ESCALATED", "FAILED", "CANCELLED"],
    "ESCALATED":   ["EXECUTING", "CANCELLED"],
    "VERIFY_GATE": ["DONE", "EXECUTING", "FAILED", "CANCELLED"],
}

def task_dir(task_id: str) -> str:
    return os.path.join(BASE_DIR, task_id)

def load(task_id: str) -> dict:
    path = os.path.join(task_dir(task_id), "state.json")
    if not os.path.exists(path):
        print(json.dumps({"error": f"task not found: {task_id}"}))
        sys.exit(1)
    with open(path) as f:
        return json.load(f)

def save(task_id: str, data: dict):
    d = task_dir(task_id)
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, "state.json")
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    if not QUIET:
        print(json.dumps({"status": "ok", "task_id": task_id}))

def cmd_init(task_id, task_type, repo_url):
    data = {
        "task_id": task_id,
        "task_type": task_type,
        "repo_url": repo_url,
        "status": "CREATED",
        "spec_version": 1,          # 冻结引擎: 打回 → v2
        "branch": f"dev-flow/{task_id}",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "gates": [],
        "gate_history": [],         # 冻结引擎: 每次闸门决策记录
        "worker": None,
        "session_id": None,
        "evidence": {},
        "escalation": None,
    }
    save(task_id, data)

def cmd_get(task_id):
    data = load(task_id)
    print(json.dumps(data, indent=2, ensure_ascii=False))

def cmd_set(task_id, field, value):
    data = load(task_id)
    # 尝试解析 JSON 值
    try:
        value = json.loads(value)
    except (json.JSONDecodeError, ValueError):
        pass
    data[field] = value
    save(task_id, data)

def cmd_trans(task_id, new_status):
    data = load(task_id)
    old = data["status"]
    allowed = VALID_TRANSITIONS.get(old, [])
    if new_status not in allowed:
        print(json.dumps({
            "error": f"非法状态转换: {old} → {new_status}",
            "allowed": allowed
        }))
        sys.exit(1)
    data["status"] = new_status
    save(task_id, data)

def cmd_list():
    if not os.path.exists(BASE_DIR):
        print(json.dumps([], indent=2))
        return
    tasks = []
    for tid in sorted(os.listdir(BASE_DIR)):
        try:
            d = load(tid)
            tasks.append({
                "task_id": d["task_id"],
                "task_type": d["task_type"],
                "status": d["status"],
                "worker": d.get("worker"),
                "updated_at": d.get("updated_at", ""),
            })
        except (SystemExit, Exception):
            pass  # 跳过损坏/空任务目录
    print(json.dumps(tasks, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    # 全局 --quiet 标志
    QUIET = "-q" in sys.argv or "--quiet" in sys.argv
    if QUIET:
        sys.argv = [a for a in sys.argv if a not in ("-q", "--quiet")]

    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)

    cmd = sys.argv[1]
    cmd_args = sys.argv[2:]
    {
        "init":  lambda: cmd_init(*cmd_args),
        "get":   lambda: cmd_get(cmd_args[0]),
        "set":   lambda: cmd_set(cmd_args[0], cmd_args[1], cmd_args[2]),
        "trans": lambda: cmd_trans(cmd_args[0], cmd_args[1]),
        "list":  lambda: cmd_list(),
    }.get(cmd, lambda: print(f"未知命令: {cmd}"))()
