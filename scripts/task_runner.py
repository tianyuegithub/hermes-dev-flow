#!/usr/bin/env python3
"""
task_runner.py — 任务 DAG 拆解执行器（OpenSpec 融合）

从 input.json 的 spec.tasks 读取子任务，按依赖顺序串行执行。
每个子任务独立调用 Claude Code，产出独立 evidence。

用法: python3 task_runner.py <task_id> [--dry-run]
"""
import json, os, sys, subprocess, time
from collections import deque

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import paths
    _task_dir = paths.task_dir
    _default_repo = os.path.join(paths.worktrees_dir(), "test-001", "repo")
except ImportError:
    # 容器内单文件运行（docker/task_runner.py 无 paths.py）
    _task_dir = lambda tid: os.path.join(
        os.environ.get("DEV_FLOW_HOME", "."), ".hermes", "tasks", tid)
    _default_repo = os.environ.get("REPO_DIR", ".")


def load_tasks(task_id: str) -> list[dict]:
    """从 input.json 读取子任务"""
    task_dir = _task_dir(task_id)
    with open(os.path.join(task_dir, "input.json")) as f:
        inp = json.load(f)
    return inp.get("spec", {}).get("tasks", [])


def topological_sort(tasks: list[dict]) -> list[list[str]]:
    """拓扑排序：返回 [[batch1], [batch2], ...]，每批可并行"""
    graph: dict[str, set[str]] = {}  # id → {依赖}
    for t in tasks:
        tid = t.get("id", str(t.get("title", ""))[:8])
        graph[tid] = set(t.get("depends", []))

    # Kahn 算法
    in_degree = {k: len(v) for k, v in graph.items()}
    queue = deque([k for k, v in in_degree.items() if v == 0])
    result = []

    while queue:
        batch = list(queue)
        result.append(batch)
        queue.clear()

        for node in batch:
            for other in graph:
                if node in graph[other]:
                    in_degree[other] -= 1
                    if in_degree[other] == 0:
                        queue.append(other)

    if sum(in_degree.values()) > 0:
        raise ValueError(f"循环依赖: {in_degree}")

    return result


def run_subtask(task_id: str, subtask_id: str, goal: str, repo_dir: str) -> dict:
    """调 Claude Code 执行单个子任务"""
    prompt = f"""你是 dev-flow worker agent。执行以下子任务。

## 子任务
{goal}

## 约束
- 只做这个子任务范围内的改动
- 完成后 git add + git commit -m "subtask: {subtask_id}"

## 输出
完成后输出 JSON: {{"status":"done","commits":[],"files_changed":[]}}"""

    result = subprocess.run(
        ["claude", "--bare", "-p", prompt,
         "--output-format", "json", "--max-turns", "15",
         "--dangerously-skip-permissions"],
        capture_output=True, text=True, timeout=180,
        cwd=repo_dir
    )

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"status": "error", "error": result.stderr[:500]}


def run(task_id: str, repo_dir: str, dry_run: bool = False) -> list[dict]:
    """执行所有子任务"""
    tasks = load_tasks(task_id)
    if not tasks:
        print("无子任务，跳过 task_runner")
        return []

    batches = topological_sort(tasks)
    results = []

    for i, batch in enumerate(batches, 1):
        print(f"\n=== Batch {i}/{len(batches)}: {batch} ===")

        for subtask_id in batch:
            task_def = next((t for t in tasks if t.get("id") == subtask_id or t.get("title", "")[:8] == subtask_id), None)
            if not task_def:
                continue

            goal = task_def.get("title", subtask_id)
            print(f"  [{subtask_id}] {goal}")

            if dry_run:
                print("    (dry-run, 跳过)")
                results.append({"id": subtask_id, "status": "dry-run"})
                continue

            result = run_subtask(task_id, subtask_id, goal, repo_dir)

            # 提交子任务结果到 output
            commit_line = subprocess.run(
                ["git", "-C", repo_dir, "log", "--oneline", "-1"],
                capture_output=True, text=True
            ).stdout.strip()

            status = "done" if result.get("subtype") == "success" else "blocked"
            results.append({
                "id": subtask_id,
                "status": status,
                "commit": commit_line.split()[0] if commit_line else "",
                "cost": result.get("total_cost_usd", 0),
                "turns": result.get("num_turns", 0),
            })
            print(f"    → {status} | {commit_line[:50]}")

            # 如果失败则不继续后面步骤
            if status == "blocked":
                print(f"  ❌ 子任务 {subtask_id} 失败，停止后续")
                return results

    return results


if __name__ == "__main__":
    task_id = sys.argv[1]
    repo_dir = sys.argv[2] if len(sys.argv) > 2 else _default_repo
    dry_run = "--dry-run" in sys.argv

    results = run(task_id, repo_dir, dry_run)
    print(json.dumps(results, indent=2, ensure_ascii=False))
