#!/usr/bin/env python3
"""
openspec_watcher.py — 定时扫描 OpenSpec changes/ 目录，自动创建 dev-flow 任务

用法:
  python3 openspec_watcher.py <repo_dir> [--once]
  cron: */5 * * * * python3 openspec_watcher.py /path/to/repo
"""
import json, os, sys, subprocess, time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths

WATCHED_DIR = "openspec/changes"
STATE_FILE = os.path.join(os.path.expanduser("~/.hermes/dev-flow"), ".openspec_seen.json")


def scan_changes(repo_dir: str) -> list[dict]:
    """扫描 openspec/changes/ 下所有变更提案"""
    changes = []
    changes_dir = os.path.join(repo_dir, WATCHED_DIR)
    if not os.path.exists(changes_dir):
        return changes

    for name in os.listdir(changes_dir):
        path = os.path.join(changes_dir, name)
        proposal = os.path.join(path, "proposal.md")
        tasks = os.path.join(path, "tasks.md")

        if os.path.isdir(path) and os.path.exists(proposal):
            changes.append({
                "name": name,
                "path": path,
                "proposal": proposal,
                "tasks": tasks,
                "has_tasks": os.path.exists(tasks),
            })
    return changes


def load_seen() -> set:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return set(json.load(f))
    return set()


def save_seen(seen: set):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(list(seen), f)


def create_devflow_task(change: dict, repo_url: str) -> str:
    """为 OpenSpec 变更创建 dev-flow 任务"""
    task_id = f"task-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    task_dir = paths.task_dir(task_id)
    os.makedirs(task_dir, exist_ok=True)

    # 读 proposal.md 提取 goal
    goal = change["name"]
    if os.path.exists(change["proposal"]):
        with open(change["proposal"]) as f:
            goal = f.readline().strip("# ").strip() or change["name"]

    # 读 tasks.md 提取子任务
    spec_tasks = []
    if change["has_tasks"]:
        with open(change["tasks"]) as f:
            for line in f:
                line = line.strip()
                if line.startswith("- [ ]") or line.startswith("- "):
                    spec_tasks.append({
                        "id": str(len(spec_tasks) + 1),
                        "title": line.lstrip("- [ ]").lstrip("- ").strip(),
                        "depends": [],
                    })

    input_data = {
        "task_id": task_id,
        "task_type": "feature",
        "repo_url": repo_url,
        "goal": goal,
        "spec": {
            "openspec_change": change["name"],
            "proposal": change["proposal"],
            "tasks": spec_tasks,
        },
        "acceptance": [],
        "constraints": {"forbidden": ["禁止改 main", "禁止 force push"]},
    }

    with open(os.path.join(task_dir, "input.json"), "w") as f:
        json.dump(input_data, f, indent=2, ensure_ascii=False)

    # 初始化 state
    subprocess.run([
        sys.executable, paths.script("state.py"),
        "--quiet", "init", task_id, "feature", repo_url
    ], check=True)
    subprocess.run([
        sys.executable, paths.script("state.py"),
        "--quiet", "trans", task_id, "GATE_PENDING"
    ], check=True)
    subprocess.run([
        sys.executable, paths.script("state.py"),
        "--quiet", "trans", task_id, "EXECUTING"
    ], check=True)

    return task_id


if __name__ == "__main__":
    repo_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        paths.worktrees_dir(), "test-001", "repo"
    )
    repo_url = sys.argv[2] if len(sys.argv) > 2 else os.environ.get("REPO_URL", "")

    changes = scan_changes(repo_dir)
    seen = load_seen()
    new_count = 0

    for change in changes:
        if change["name"] not in seen:
            print(f"  新提案: {change['name']}")
            task_id = create_devflow_task(change, repo_url)
            seen.add(change["name"])
            new_count += 1
            print(f"    → task: {task_id}")

    save_seen(seen)
    print(f"扫描完成: {new_count} 新任务 / {len(changes)} 总提案")
