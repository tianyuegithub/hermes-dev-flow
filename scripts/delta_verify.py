#!/usr/bin/env python3
"""
delta_verify.py — OpenSpec Delta 验证器

对照 OpenSpec 的 delta specs（ADDED/MODIFIED/REMOVED），
验证 git diff 中的实际变更是否匹配规范。

用法: python3 delta_verify.py <task_id> [--repo <dir>]
"""
import json, os, sys, subprocess, re
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths


def load_spec(task_id: str) -> dict:
    """从 input.json 读取 delta specs"""
    task_dir = paths.task_dir(task_id)
    with open(os.path.join(task_dir, "input.json")) as f:
        inp = json.load(f)
    return inp.get("spec", {})


def get_changed_files(repo_dir: str) -> list[str]:
    """获取变更文件列表（git diff origin/main..HEAD）"""
    result = subprocess.run(
        ["git", "-C", repo_dir, "diff", "origin/main..HEAD", "--name-only"],
        capture_output=True, text=True
    )
    return [f for f in result.stdout.strip().split("\n") if f]


def verify_delta(task_id: str, repo_dir: str) -> dict:
    """验证 delta specs 与实际变更的匹配度"""
    spec = load_spec(task_id)
    delta_specs = spec.get("delta_specs", {})
    changed_files = get_changed_files(repo_dir)

    if not delta_specs:
        return {
            "status": "skipped",
            "reason": "无 delta specs，跳过验证",
            "matched": 0, "missing": 0, "extra": 0,
        }

    # 解析 delta specs 中的文件路径
    spec_files = set()
    for file_path, operations in delta_specs.items():
        # auth/spec.md → **/auth/**/*.ts 等模糊匹配
        module = file_path.split("/")[0]
        spec_files.add(module)

    changed_modules = set()
    for f in changed_files:
        parts = f.split("/")
        if len(parts) >= 2:
            changed_modules.add(parts[0])

    matched = spec_files & changed_modules
    missing = spec_files - changed_modules
    extra = changed_modules - spec_files

    return {
        "status": "pass" if not missing else "partial",
        "reason": (
            f"匹配: {sorted(matched)}; "
            f"缺漏: {sorted(missing)}; "
            f"额外变更: {sorted(extra)}"
        ) if missing or extra else f"全部匹配: {sorted(matched)}",
        "matched": len(matched),
        "missing": len(missing),
        "extra": len(extra),
        "delta_files": sorted(spec_files),
        "changed_modules": sorted(changed_modules),
    }


if __name__ == "__main__":
    task_id = sys.argv[1]
    repo_dir = sys.argv[2] if len(sys.argv) > 2 else os.path.join(
        paths.worktrees_dir(), "test-001", "repo"
    )

    result = verify_delta(task_id, repo_dir)
    print(json.dumps(result, indent=2, ensure_ascii=False))
