#!/usr/bin/env python3
"""
intake.py — L0 意图识别辅助脚本
=================================
Hermes 做完分类推理后，用此脚本：
  1. 生成 task_id
  2. 调 state.py init
  3. 写入 input.json
  4. 写入仓库注册表查找

用法:
  intake.py classify <user_request>    # 输出分类建议（供 Hermes 参考）
  intake.py create <task_type> <repo_key> "<goal>" [--gates gate1,gate2] [--worker claude|codex]
  intake.py repos                      # 列出已知仓库
"""

import json, os, sys, textwrap, subprocess
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from validate_contract import validate_file
import paths

# ── 编排偏好路由表 ─────────────────────────────────
PREF_PATH = paths.pref_table()

def resolve_worker(task_type: str, user_override: str = "") -> dict:
    """从编排偏好路由表解析 provider/model。
    用户显式指定时覆盖路由表。"""
    if user_override and user_override != "auto":
        return {"provider": user_override, "model": "auto", "reason": "用户显式指定"}

    try:
        with open(PREF_PATH) as f:
            pref = json.load(f)
    except:
        return {"provider": "claude", "model": "glm-5.2", "reason": "路由表不可用，回退默认"}

    rules = pref.get("rules", [])
    matched = [r for r in rules if r.get("task_type") == task_type]

    if matched:
        r = matched[0]
        return {"provider": r["provider"], "model": r.get("model", "auto"), "reason": r.get("reason", "")}

    default = pref.get("default", {})
    return {"provider": default.get("provider", "claude"),
            "model": default.get("model", "auto"),
            "reason": "无匹配规则，使用默认"}

    return {"provider": "claude", "model": "glm-5.2", "reason": "回退默认"}


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TASKS_DIR = os.path.join(BASE_DIR, ".hermes/tasks")

# 从 repos.json 加载仓库注册表
with open(os.path.join(BASE_DIR, "scripts", "repos.json")) as f:
    REPOS = json.load(f)

RISK_SIGNALS = {
    "high": ["schema", "数据库", "安全", "认证", "生产", "迁移", "删除", "权限", "密码"],
    "medium": ["新增", "修改", "加入", "实现", "重构", "优化"],
    "low": ["日志", "注释", "文案", "格式化", "文档", "readme", "拼写"],
}

TYPE_SIGNALS = {
    "feature": ["加", "新增", "实现", "开发", "创建", "写一个", "添加"],
    "bug": ["修", "bug", "报错", "不管用", "坏", "错误", "崩溃", "异常"],
    "doc": ["文档", "readme", "说明", "注释"],
    "research": ["调研", "看一下", "怎么实现", "分析", "评估"],
    "refactor": ["重构", "整理", "优化结构", "清理"],
}


def classify(request: str) -> dict:
    """简单关键词分类，返回结构化分析。"""
    req = request.lower()

    # task_type
    task_type = "feature"
    for t, keywords in TYPE_SIGNALS.items():
        if any(k in req for k in keywords):
            task_type = t
            break

    # risk
    risk = "medium"
    for r, keywords in RISK_SIGNALS.items():
        if any(k in req for k in keywords):
            risk = r
            break

    # gates
    gate_map = {
        "high": ["方案", "架构", "验证"],
        "medium": ["方案", "验证"],
        "low": ["验证"],
    }
    gates = gate_map.get(risk, ["验证"])

    # decompose
    decompose = any(k in req for k in ["分步", "先", "然后", "多个", "跨模块"])

    # repo（按 triggers 关键词匹配）
    repo_key = None
    for key, repo in REPOS.items():
        for t in repo.get("triggers", [key]):
            if t.lower() in req:
                repo_key = key
                break
        if repo_key:
            break

    return {
        "task_type": task_type,
        "risk": risk,
        "gates": gates,
        "decompose": decompose,
        "cli_mode": "route:claude",
        "repo_key": repo_key,
    }


def cmd_classify(request: str):
    result = classify(request)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    print()
    print("建议 task_type:", result["task_type"])
    print("建议 risk:", result["risk"])
    print("建议 gates:", result["gates"])
    print("命中仓库:", result["repo_key"] or "未匹配，需询问用户")


def cmd_create(task_type: str, repo_key: str, goal: str,
               gates: str = "方案,验证", worker: str = "auto"):
    if repo_key not in REPOS:
        print(f"错误: 未知仓库 '{repo_key}'。已知: {list(REPOS.keys())}")
        sys.exit(1)

    repo = REPOS[repo_key]
    task_id = f"task-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    gates_list = [g.strip() for g in gates.split(",")]

    # 编排偏好路由: auto时查表，否则用用户指定的
    resolved = resolve_worker(task_type, worker)
    provider = resolved["provider"]

    # 调 state.py init（静默）
    import subprocess
    state_py = os.path.join(BASE_DIR, "scripts", "state.py")

    subprocess.run([sys.executable, state_py, "--quiet", "init", task_id, task_type, repo["url"]],
                   check=True)
    subprocess.run([sys.executable, state_py, "--quiet", "set", task_id, "worker", provider], check=True)
    subprocess.run([sys.executable, state_py, "--quiet", "set", task_id, "gates",
                    json.dumps(gates_list)], check=True)

    # 写 input.json
    task_dir = os.path.join(TASKS_DIR, task_id)
    os.makedirs(task_dir, exist_ok=True)

    input_data = {
        "task_id": task_id,
        "task_type": task_type,
        "repo_url": repo["url"],
        "base_branch": repo["default_branch"],
        "goal": goal,
        "acceptance": [],
        "spec": {
            "tasks": []  # OpenSpec 融合: 子任务列表 [{id,title,depends}]
        },
        "constraints": {
            "forbidden": [
                "禁止改 main 分支",
                "禁止 force push",
            ]
        },
        "budget": {"max_iterations": 8, "max_wallclock_minutes": 15},
    }

    input_path = os.path.join(task_dir, "input.json")
    with open(input_path, "w") as f:
        json.dump(input_data, f, indent=2, ensure_ascii=False)

    # 契约强制: input.json 必须通过 input 契约校验，否则任务作废、不流转
    valid, errors, _ = validate_file("input", input_path)
    if not valid:
        print(json.dumps({
            "status": "contract_violation",
            "task_id": task_id,
            "errors": errors,
            "hint": "input.json 违反 input 契约，任务未流转。请修正后重建。",
        }, indent=2, ensure_ascii=False))
        sys.exit(1)

    print(json.dumps({
        "status": "created",
        "task_id": task_id,
        "task_type": task_type,
        "repo": repo_key,
        "gates": gates_list,
        "worker": worker,
        "input_path": input_path,
    }, indent=2, ensure_ascii=False))

    # 流转到 GATE_PENDING
    try:
        subprocess.run([sys.executable, state_py, "--quiet", "trans", task_id, "GATE_PENDING"], check=True)
    except subprocess.CalledProcessError:
        pass


def cmd_repos():
    print(json.dumps(REPOS, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)

    cmd = sys.argv[1]
    args = sys.argv[2:]

    if cmd == "classify":
        cmd_classify(" ".join(args))
    elif cmd == "create":
        # intake.py create <task_type> <repo_key> "<goal>"
        if len(args) < 3:
            print("用法: intake.py create <task_type> <repo_key> '<goal>'")
            sys.exit(1)
        cmd_create(args[0], args[1], args[2])
    elif cmd == "repos":
        cmd_repos()
    else:
        print(f"未知命令: {cmd}")
        sys.exit(1)
