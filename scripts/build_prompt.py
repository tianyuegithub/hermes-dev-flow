#!/usr/bin/env python3
"""
build_prompt.py — 从 input.json 拼装 Claude Code 提示词
用法: python3 build_prompt.py <task_id> [--output prompt.txt]
"""
import json, os, sys

TASK_ID = sys.argv[1]
TASK_DIR = os.path.expanduser(f"~/Codes/ai-dev-flow/.hermes/tasks/{TASK_ID}")
INPUT_PATH = os.path.join(TASK_DIR, "input.json")
OUTPUT_PATH = sys.argv[3] if len(sys.argv) > 3 and sys.argv[2] == "--output" else os.path.join(TASK_DIR, "prompt.txt")

with open(INPUT_PATH) as f:
    inp = json.load(f)

goal = inp["goal"]
acceptance = "\n".join(f"- {a}" for a in inp.get("acceptance", []))
forbidden = "\n".join(f"- {f}" for f in inp.get("constraints", {}).get("forbidden", []))

prompt = f"""你是 dev-flow worker agent。按以下输入契约执行任务。

## 任务目标
{goal}

## 验收标准
{acceptance}

## 约束（必须遵守）
{forbidden}

## 证据要求
1. git diff origin/main --stat
2. git add + git commit
3. 如有测试则把输出保存到 .hermes/evidence/test-output.txt

## 逃生舱
遇到无法自决的选择时，写 ~/Codes/ai-dev-flow/.hermes/tasks/{TASK_ID}/escalate.json，然后退出。

## 输出契约
完成后输出 JSON（用 ```json 包裹）:
{{"status":"done|blocked","commits":["<sha>"],"files_changed":["..."],"evidence":{{"diff_stat":"...","test_result":"pass|fail|skipped"}},"self_check":[{{"criterion":"...","met":true|false,"proof":"..."}}]}}
"""

with open(OUTPUT_PATH, "w") as f:
    f.write(prompt)

print(json.dumps({
    "status": "ok",
    "task_id": TASK_ID,
    "output": OUTPUT_PATH,
    "size": len(prompt),
    "goal_preview": goal[:80],
    "acceptance_count": len(inp.get("acceptance", [])),
    "forbidden_count": len(inp.get("constraints", {}).get("forbidden", [])),
}))
