#!/usr/bin/env python3
"""
gates.py — 统一闸门（2026-07-30 重构，替代旧三道闸门死代码）

单一模型（docs/THESIS.md 推论 3）:
  Scorecard 自动裁决为主，dev/test/PM 不再是独立模块，
  而是 escalate 区间内的三级人工角色，依次裁决。

闭环:
  scorecard auto_pass  → 记录 gate_history → 批准（进入 integrate）
  scorecard auto_reject→ 记录 gate_history → 打回（回 EXECUTING）
  scorecard escalate   → dev → test → pm 依次人工裁决 → 批准或打回

用法:
  gates.py decide <task_id>                      → Scorecard 裁决 + 记录
  gates.py human <task_id> <dev|test|pm> <approve|reject> [feedback]
  gates.py status <task_id>                      → 闸门状态 + 历史

状态字段:
  gate_history[]   每次裁决记录（自动与人工）
  human_gates      {required, approved[], rejected, feedback}
"""
import os, sys, json, subprocess
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths

HOME = paths.home()
TASKS_DIR = paths.tasks_dir()

HUMAN_ROLES = [
    {"id": "dev",  "name": "开发者审查", "checks": ["代码 diff 检查", "无合并冲突", "约束符合"]},
    {"id": "test", "name": "测试验证",   "checks": ["功能独立构建通过", "测试产物可信", "无回归"]},
    {"id": "pm",   "name": "业务验收",   "checks": ["验收标准全部满足", "业务目标达成", "无遗留风险"]},
]
ROLE_IDS = [r["id"] for r in HUMAN_ROLES]


def load_state(task_id: str) -> dict:
    with open(os.path.join(TASKS_DIR, task_id, "state.json")) as f:
        return json.load(f)


def save_state(task_id: str, state: dict):
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    with open(os.path.join(TASKS_DIR, task_id, "state.json"), "w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def _record(state: dict, entry: dict):
    entry["at"] = datetime.now(timezone.utc).isoformat()
    state.setdefault("gate_history", []).append(entry)


def pending_role(state: dict):
    """当前待裁决的人工角色（None = 无需或已全部通过）。"""
    hg = state.get("human_gates")
    if not hg or hg.get("rejected"):
        return None
    for rid in hg.get("required", []):
        if rid not in hg.get("approved", []):
            return rid
    return None


# ── 自动裁决 ──────────────────────────────────────────────────

def decide(task_id: str) -> dict:
    """跑 Scorecard 自动裁决，落入闭环的三条支路之一。"""
    import scorecard
    result = scorecard.evaluate(task_id, auto=True)
    verdict = result["verdict"]

    state = load_state(task_id)
    _record(state, {
        "kind": "auto",
        "verdict": verdict,
        "total": result.get("total"),
        "recommendation": result.get("recommendation"),
    })

    if verdict == "auto_pass":
        state["human_gates"] = {"required": [], "approved": [], "rejected": None}
        save_state(task_id, state)
        return {"decision": "approved", "by": "auto", "next": "dev-integrate",
                "scorecard": result}

    if verdict == "auto_reject":
        state["human_gates"] = {"required": [], "approved": [], "rejected": "auto"}
        save_state(task_id, state)
        return {"decision": "rejected", "by": "auto", "next": "EXECUTING",
                "feedback": result.get("recommendation"), "scorecard": result}

    # escalate → 启动三级人工角色
    state["human_gates"] = {"required": ROLE_IDS.copy(), "approved": [], "rejected": None}
    save_state(task_id, state)
    role = HUMAN_ROLES[0]
    return {"decision": "escalated", "by": "auto", "next": f"human:{role['id']}",
            "pending_role": role, "scorecard": result}


# ── 人工裁决 ──────────────────────────────────────────────────

def human(task_id: str, role: str, action: str, feedback: str = "") -> dict:
    state = load_state(task_id)
    hg = state.get("human_gates") or {}

    if role not in ROLE_IDS:
        return {"error": f"未知角色: {role}，合法: {ROLE_IDS}"}
    if action not in ("approve", "reject"):
        return {"error": "action 必须是 approve 或 reject"}

    current = pending_role(state)
    if current is None:
        return {"error": "当前无待裁决的人工闸门（先跑 gates.py decide）"}
    if role != current:
        return {"error": f"顺序错误：当前待裁决角色是 {current}，不是 {role}"}

    _record(state, {"kind": "human", "role": role, "action": action, "feedback": feedback})

    if action == "reject":
        hg["rejected"] = role
        state["human_gates"] = hg
        save_state(task_id, state)
        return {"decision": "rejected", "by": f"human:{role}", "next": "EXECUTING",
                "feedback": feedback or f"{role} 角色打回"}

    hg.setdefault("approved", []).append(role)
    state["human_gates"] = hg
    nxt = pending_role(state)
    if nxt is None:
        save_state(task_id, state)
        return {"decision": "approved", "by": "human:all", "next": "dev-integrate",
                "approved_by": hg["approved"]}

    save_state(task_id, state)
    role_info = next(r for r in HUMAN_ROLES if r["id"] == nxt)
    return {"decision": "escalated", "by": f"human:{role}", "next": f"human:{nxt}",
            "pending_role": role_info, "approved_so_far": hg["approved"]}


# ── 状态查询 ──────────────────────────────────────────────────

def status(task_id: str) -> dict:
    state = load_state(task_id)
    hg = state.get("human_gates") or {}
    current = pending_role(state)
    return {
        "task_id": task_id,
        "status": state.get("status"),
        "human_gates": hg,
        "pending_role": current,
        "pending_role_info": next((r for r in HUMAN_ROLES if r["id"] == current), None),
        "gate_history": state.get("gate_history", []),
    }


def approval_state(task_id: str) -> dict:
    """只读查询当前闸门结论（不重跑 Scorecard，不打断人工链）。

    approved: 自动 auto_pass，或人工链全部 approve
    rejected: 自动 auto_reject，或任一角色 reject
    pending:  人工链进行中 / 尚未裁决
    """
    state = load_state(task_id)
    hg = state.get("human_gates") or {}
    hist = state.get("gate_history") or []

    if hg.get("rejected"):
        by = hg["rejected"]
        return {"decision": "rejected", "by": f"human:{by}" if by != "auto" else "auto"}

    required = hg.get("required") or []
    if required:
        approved = hg.get("approved") or []
        if all(r in approved for r in required):
            return {"decision": "approved", "by": "human:all", "approved_by": approved}
        return {"decision": "pending", "by": f"human:{pending_role(state)}",
                "approved_so_far": approved}

    if hist:
        last = hist[-1]
        if last.get("verdict") == "auto_pass":
            return {"decision": "approved", "by": "auto"}
        if last.get("verdict") == "auto_reject":
            return {"decision": "rejected", "by": "auto",
                    "feedback": last.get("recommendation")}

    return {"decision": "pending", "by": None}


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(0)

    cmd = args[0]
    if cmd == "decide" and len(args) >= 2:
        print(json.dumps(decide(args[1]), indent=2, ensure_ascii=False))
    elif cmd == "approval" and len(args) >= 2:
        print(json.dumps(approval_state(args[1]), indent=2, ensure_ascii=False))
    elif cmd == "human" and len(args) >= 4:
        print(json.dumps(human(args[1], args[2], args[3],
                               args[4] if len(args) > 4 else ""),
                         indent=2, ensure_ascii=False))
    elif cmd == "status" and len(args) >= 2:
        print(json.dumps(status(args[1]), indent=2, ensure_ascii=False))
    else:
        print(__doc__)
        sys.exit(2)
