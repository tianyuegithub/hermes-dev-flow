#!/usr/bin/env python3
"""
build_prompt.py — 从 input.json 拼装 Claude Code 提示词
用法: python3 build_prompt.py <task_id> [--output prompt.txt]
也可作为模块导入: from build_prompt import build_prompt
"""
import json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths


def build_prompt(task_id: str, output_path: str = None) -> dict:
    """从 input.json 拼装提示词，返回结果 dict"""
    task_dir = paths.task_dir(task_id)
    input_path = os.path.join(task_dir, "input.json")
    if output_path is None:
        output_path = os.path.join(task_dir, "prompt.txt")

    with open(input_path) as f:
        inp = json.load(f)

    goal = inp["goal"]
    acceptance = "\n".join(f"- {a}" for a in inp.get("acceptance", []))
    forbidden = "\n".join(f"- {f}" for f in inp.get("constraints", {}).get("forbidden", []))

    # ── 子任务拆解（OpenSpec 融合） ──
    spec_tasks = inp.get("spec", {}).get("tasks", [])
    tasks_section = ""
    if spec_tasks:
        tasks_lines = []
        for t in spec_tasks:
            deps = t.get("depends", [])
            dep_str = f" (依赖: {', '.join(deps)})" if deps else ""
            tasks_lines.append(f"- [{t['id']}] {t.get('title', '')}{dep_str}")
        tasks_section = "## 子任务拆解（按顺序执行）\n" + "\n".join(tasks_lines) + "\n\n完成后逐项勾选。\n"

    prompt = f"""你是 dev-flow worker agent。按以下输入契约执行任务。

## 任务目标
{goal}

{tasks_section}
## 验收标准
{acceptance}

## 约束（必须遵守）
{forbidden}

## 证据要求
1. git diff origin/main --stat
2. git add + git commit
3. 如有测试则把输出保存到 .hermes/evidence/test-output.txt

## 逃生舱
遇到无法自决的选择时，写 {task_dir}/escalate.json，然后退出。

## 输出契约
完成后输出 JSON（用 ```json 包裹）:
{{"status":"done|blocked","commits":["<sha>"],"files_changed":["..."],"evidence":{{"diff_stat":"...","test_result":"pass|fail|skipped"}},"self_check":[{{"criterion":"...","met":true|false,"proof":"..."}}]}}
"""

    with open(output_path, "w") as f:
        f.write(prompt)

    return {
        "status": "ok",
        "task_id": task_id,
        "output": output_path,
        "size": len(prompt),
        "goal_preview": goal[:80],
        "acceptance_count": len(inp.get("acceptance", [])),
        "forbidden_count": len(inp.get("constraints", {}).get("forbidden", [])),
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    task_id = sys.argv[1]
    output_path = sys.argv[3] if len(sys.argv) > 3 and sys.argv[2] == "--output" else None
    result = build_prompt(task_id, output_path)
    print(json.dumps(result))
