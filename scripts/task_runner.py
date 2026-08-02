#!/usr/bin/env python3
"""
task_runner.py — 任务 DAG 拆解执行器（并行版 · Multi-Agent Refactor 模式）

从 input.json 的 spec.tasks 读取子任务，按依赖关系分批执行。
同一批内无依赖的子任务并发执行（每个独立 worktree + 独立 agent）。

用法: python3 task_runner.py <task_id> [--dry-run] [--parallel N] [--repo <dir>]

变更:
- 2026-08-02: 并行化 — 同批子任务并发跑，独立 worktree（Multi-Agent Refactor 启发）
"""
import json, os, sys, subprocess, time, shutil
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import paths
    _task_dir = paths.task_dir
    _default_repo = os.path.join(paths.worktrees_dir(), "test-001", "repo")
except ImportError:
    # 容器内单文件运行
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
    """拓扑排序：返回 [[batch1], [batch2], ...]，每批内可并行"""
    graph: dict[str, set[str]] = {}
    for t in tasks:
        tid = t.get("id", str(t.get("title", ""))[:8])
        graph[tid] = set(t.get("depends", []))

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


def prepare_worktree(base_repo: str, subtask_id: str) -> str:
    """为子任务创建独立 git worktree（并行隔离）"""
    base = os.path.dirname(os.path.abspath(base_repo))
    wt_path = os.path.join(base, f"wt-{subtask_id[:8]}")
    if os.path.exists(wt_path):
        shutil.rmtree(wt_path)

    result = subprocess.run(
        ["git", "-C", base_repo, "worktree", "add", "-b", f"subtask/{subtask_id}",
         wt_path, "origin/main"],
        capture_output=True, text=True, timeout=60
    )
    if result.returncode != 0:
        # 回退: 直接 clone
        repo_url = subprocess.run(
            ["git", "-C", base_repo, "remote", "get-url", "origin"],
            capture_output=True, text=True).stdout.strip()
        subprocess.run(["git", "clone", "--depth", "1", repo_url, wt_path],
                       capture_output=True, text=True, timeout=120)
    return wt_path


def run_subtask(task_id: str, subtask_id: str, goal: str, repo_dir: str,
                provider: str = "claude", max_turns: int = 15) -> dict:
    """在独立 worktree 中调 CLI agent 执行子任务"""
    prompt = f"""你是 dev-flow worker agent。在 {repo_dir} 中执行以下子任务。

## 子任务
{goal}

## 约束
- 只做这个子任务范围内的改动
- 完成后 git add + git commit -m "subtask: {subtask_id}"
- 不要触碰其他模块的文件

## 输出
完成后输出 JSON: {{"status":"done","commits":[],"files_changed":[]}}"""

    if provider == "claude":
        cmd = ["claude", "--bare", "-p", prompt,
               "--output-format", "json", "--max-turns", str(max_turns),
               "--dangerously-skip-permissions"]
    elif provider == "opencode":
        cmd = ["opencode", "--yes", prompt]
    else:
        cmd = ["claude", "--bare", "-p", prompt,
               "--output-format", "json", "--max-turns", str(max_turns),
               "--dangerously-skip-permissions"]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300,
                            cwd=repo_dir)
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"status": "error", "error": result.stderr[:500],
                "stdout": result.stdout[:500]}


def run(task_id: str, repo_dir: str, dry_run: bool = False,
        parallel: int = 4) -> list[dict]:
    """执行所有子任务 — 同批并发"""
    tasks = load_tasks(task_id)
    if not tasks:
        print("无子任务，跳过 task_runner")
        return []

    batches = topological_sort(tasks)
    results: dict[str, dict] = {}
    all_ok = True

    for i, batch in enumerate(batches, 1):
        print(f"\n=== Batch {i}/{len(batches)}: {batch} "
              f"({'并行×' + str(min(len(batch), parallel)) if len(batch) > 1 else '串行'}) ===")

        def execute(subtask_id: str) -> dict:
            task_def = next((t for t in tasks
                             if t.get("id") == subtask_id or t.get("title", "")[:8] == subtask_id), None)
            if not task_def:
                return {"id": subtask_id, "status": "skipped", "reason": "未找到定义"}

            goal = task_def.get("title", subtask_id)
            provider = task_def.get("provider", "claude")
            print(f"  [{subtask_id}] {goal} → {provider}")

            if dry_run:
                return {"id": subtask_id, "status": "dry-run", "goal": goal}

            # 独立 worktree
            wt_dir = prepare_worktree(repo_dir, subtask_id)
            result = run_subtask(task_id, subtask_id, goal, wt_dir, provider)

            commit_line = subprocess.run(
                ["git", "-C", wt_dir, "log", "--oneline", "-1"],
                capture_output=True, text=True).stdout.strip()

            status = "done" if result.get("subtype") == "success" else "blocked"
            entry = {
                "id": subtask_id,
                "status": status,
                "commit": commit_line.split()[0] if commit_line else "",
                "cost": result.get("total_cost_usd", 0),
                "turns": result.get("num_turns", 0),
                "worktree": wt_dir,
            }
            print(f"    → {status} | {commit_line[:50]}")
            return entry

        # 并发执行同批子任务
        with ThreadPoolExecutor(max_workers=min(len(batch), parallel)) as pool:
            futures = {pool.submit(execute, sid): sid for sid in batch}
            for future in as_completed(futures):
                entry = future.result()
                results[entry["id"]] = entry
                if entry["status"] != "done" and entry["status"] != "dry-run":
                    all_ok = False

        # 失败停止后续批次
        if not all_ok:
            print(f"\n❌ Batch {i} 有失败，停止后续批次")
            break

    # 汇总
    return [results[sid] for sid in results]


if __name__ == "__main__":
    task_id = sys.argv[1]
    repo_dir = sys.argv[2] if len(sys.argv) > 2 else _default_repo
    dry_run = "--dry-run" in sys.argv
    parallel = 4
    for i, arg in enumerate(sys.argv):
        if arg == "--parallel" and i + 1 < len(sys.argv):
            parallel = int(sys.argv[i + 1])
        elif arg == "--repo" and i + 1 < len(sys.argv):
            repo_dir = sys.argv[i + 1]

    results = run(task_id, repo_dir, dry_run, parallel)
    print(json.dumps(results, indent=2, ensure_ascii=False))
