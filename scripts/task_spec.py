#!/usr/bin/env python3
"""
task_spec.py — 单一任务契约 (替代三份 JSON Schema)

MVP 简化: input.json + output.json + escalate 合并为一个 task.yaml

用法:
  python3 task_spec.py create <task_type> <repo_key> "<goal>" [--worker auto] [--output <dir>]
  python3 task_spec.py show <task_id>
"""
import os, sys, json, subprocess
from datetime import datetime, timezone

TASKS_DIR = os.path.expanduser("~/Codes/ai-dev-flow/.hermes/tasks")
PREF_PATH = os.path.expanduser("~/Codes/ai-dev-flow/config/orchestration-preferences.json")

def resolve_worker(task_type: str, user_override: str = "") -> dict:
    """编排偏好路由表"""
    if user_override and user_override != "auto":
        return {"provider": user_override, "model": "auto", "reason": "用户显式指定"}
    try:
        with open(PREF_PATH) as f:
            pref = json.load(f)
        matched = [r for r in pref.get("rules", []) if r.get("task_type") == task_type]
        if matched:
            r = matched[0]
            return {"provider": r["provider"], "model": r.get("model", "auto"), "reason": r.get("reason", "")}
        default = pref.get("default", {})
        return {"provider": default.get("provider", "claude"), "model": default.get("model", "auto"), "reason": "默认"}
    except:
        return {"provider": "claude", "model": "auto", "reason": "路由表不可用，回退"}

def create_task(task_type: str, repo_key: str, goal: str, worker: str = "auto", output_dir: str = None) -> dict:
    """创建任务（单契约）"""
    # 仓库注册表
    repos_path = os.path.expanduser("~/Codes/ai-dev-flow/scripts/repos.json")
    try:
        with open(repos_path) as f:
            repos = json.load(f)
    except:
        repos = {}
    if repo_key not in repos:
        return {"error": f"未知仓库 '{repo_key}'。已知: {list(repos.keys())}"}

    repo = repos[repo_key]
    task_id = f"task-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    resolved = resolve_worker(task_type, worker)

    task_dir = output_dir or os.path.join(TASKS_DIR, task_id)
    os.makedirs(task_dir, exist_ok=True)

    # ── 单契约 task.yaml ──
    spec = {
        "task_id": task_id,
        "task_type": task_type,
        "repo_url": repo["url"],
        "base_branch": repo.get("default_branch", "main"),
        "goal": goal,
        "provider": resolved["provider"],
        "model": resolved.get("model", "auto"),
        "provider_reason": resolved["reason"],
        "gates": ["dev", "test", "pm"],
        "acceptance": [],
        "constraints": {
            "forbidden": ["禁止改 main 分支", "禁止 force push"]
        },
        "budget": {"max_turns": 300, "max_budget_usd": 15},
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "CREATED",
        "evidence": {},
        "output": {},
    }

    yaml_path = os.path.join(task_dir, "task.yaml")
    with open(yaml_path, "w") as f:
        json.dump(spec, f, indent=2, ensure_ascii=False)

    return {
        "task_id": task_id,
        "task_dir": task_dir,
        "spec_path": yaml_path,
        "provider": resolved["provider"],
        "model": resolved.get("model", "auto"),
        "reason": resolved["reason"],
    }

def show_task(task_id: str) -> dict:
    """查看任务"""
    task_dir = os.path.join(TASKS_DIR, task_id)
    yaml_path = os.path.join(task_dir, "task.yaml")
    if not os.path.exists(yaml_path):
        return {"error": f"任务 {task_id} 不存在 (无 task.yaml)"}
    with open(yaml_path) as f:
        return json.load(f)

if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else "help"
    if action == "create":
        # task_spec.py create <task_type> <repo_key> "<goal>"
        if len(sys.argv) < 5:
            print("用法: task_spec.py create <task_type> <repo_key> '<goal>'")
            sys.exit(1)
        result = create_task(sys.argv[2], sys.argv[3], sys.argv[4])
        print(json.dumps(result, indent=2, ensure_ascii=False))
    elif action == "show":
        if len(sys.argv) < 3:
            print("用法: task_spec.py show <task_id>")
            sys.exit(1)
        print(json.dumps(show_task(sys.argv[2]), indent=2, ensure_ascii=False))
    else:
        print(__doc__)
