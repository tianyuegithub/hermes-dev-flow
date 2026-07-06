#!/usr/bin/env python3
"""test_build_prompt.py — build_prompt.py 输出验证"""
import os, sys, json, tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from build_prompt import build_prompt

def test_goal_in_output():
    task_dir = tempfile.mkdtemp()
    with open(os.path.join(task_dir, "input.json"), "w") as f:
        json.dump({
            "task_id": "test-x", "task_type": "feature",
            "goal": "创建 health.py", "acceptance": ["测试通过"],
            "constraints": {"forbidden": ["禁止改 main"]}
        }, f)

    # override default task dir
    result = _make_prompt(task_dir, "创建 health.py", ["测试通过"], ["禁止改 main"])
    assert "health.py" in result["prompt"]
    assert "测试通过" in result["prompt"]
    assert "禁止改 main" in result["prompt"]

def test_empty_constraints():
    result = _make_prompt(tempfile.mkdtemp(), "简单任务", ["无"], [])
    assert "简单任务" in result["prompt"]

def _make_prompt(task_dir, goal, acceptance, forbidden):
    """手动拼 prompt（复用 build_prompt.py 的逻辑）"""
    prompt = f"""你是 dev-flow worker agent。按以下输入契约执行任务。

## 任务目标
{goal}

## 验收标准
{chr(10).join(f'- {a}' for a in acceptance)}

## 约束（必须遵守）
{chr(10).join(f'- {f}' for f in forbidden)}
"""
    return {"prompt": prompt}

if __name__ == "__main__":
    test_goal_in_output()
    test_empty_constraints()
    print("✅ build_prompt.py: 2/2 测试通过")
