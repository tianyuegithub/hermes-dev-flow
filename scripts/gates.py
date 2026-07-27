#!/usr/bin/env python3
"""
gates.py — 三道闸门流转引擎（dev → test → PM）

用法: python3 gates.py advance <task_id>       → 推进到下一闸门
      python3 gates.py status <task_id>        → 查看当前闸门
      python3 gates.py verify <task_id> <gate> → 提交闸门验证
"""
import os, sys, json
from datetime import datetime, timezone

TASKS_DIR = os.path.expanduser("~/Codes/ai-dev-flow/.hermes/tasks")

GATE_FLOW = [
    {"id": "dev",   "name": "开发者审查", "role": "dev", "checks": [
        "代码 diff 检查", "Scorecard >= 50", "无合并冲突"
    ]},
    {"id": "test",  "name": "测试验证",   "role": "test", "checks": [
        "功能独立构建通过", "单元测试全部 green", "无回归问题"
    ]},
    {"id": "pm",    "name": "业务验收",   "role": "pm", "checks": [
        "验收标准全部满足", "业务目标达成", "无遗留风险"
    ]},
]

def load_state(task_id: str) -> dict:
    sp = os.path.join(TASKS_DIR, task_id, "state.json")
    with open(sp) as f:
        return json.load(f)

def save_state(task_id: str, state: dict):
    sp = os.path.join(TASKS_DIR, task_id, "state.json")
    with open(sp, "w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)

def get_gate_status(task_id: str) -> dict:
    state = load_state(task_id)
    gates = state.get("gates", [])
    status = state.get("status", "?")

    current_gate = None
    for g in GATE_FLOW:
        if g["id"] not in gates:
            current_gate = g
            break

    return {
        "task_id": task_id,
        "status": status,
        "gates_completed": gates,
        "current_gate": current_gate,
        "gates_remaining": [g for g in GATE_FLOW if g["id"] not in gates],
    }

def advance_gate(task_id: str) -> dict:
    state = load_state(task_id)
    gates = state.get("gates", [])
    status = state.get("status", "?")

    if status != "VERIFY_GATE" and status != "DONE":
        return {"error": f"当前状态 {status} 不允许推进闸门"}

    # 找下一个未完成的闸门
    next_gate = None
    for g in GATE_FLOW:
        if g["id"] not in gates:
            next_gate = g
            break

    if not next_gate:
        state["status"] = "DONE"
        state["updated_at"] = datetime.now(timezone.utc).isoformat()
        save_state(task_id, state)
        return {"task_id": task_id, "status": "DONE", "all_gates_passed": True}

    # 通过当前闸门，进入下一个
    gates.append(next_gate["id"])
    state["gates"] = gates
    state["current_gate"] = next_gate["id"]
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    save_state(task_id, state)

    return {
        "task_id": task_id,
        "gate_passed": next_gate["id"],
        "gate_name": next_gate["name"],
        "role": next_gate["role"],
        "checks": next_gate["checks"],
        "remaining": [g["id"] for g in GATE_FLOW if g["id"] not in gates],
    }

def verify_gate(task_id: str, gate_id: str, verified_by: str = "") -> dict:
    state = load_state(task_id)
    gates = state.get("gates", [])

    if gate_id not in [g["id"] for g in GATE_FLOW]:
        return {"error": f"未知闸门: {gate_id}"}

    if gate_id in gates:
        return {"error": f"闸门 {gate_id} 已通过"}

    gates.append(gate_id)
    state["gates"] = gates
    state["gate_verified_by"] = verified_by or gate_id
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    save_state(task_id, state)

    return advance_gate(task_id)


if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else "help"
    task_id = sys.argv[2] if len(sys.argv) > 2 else ""
    extra = sys.argv[3] if len(sys.argv) > 3 else ""

    if action == "status":
        print(json.dumps(get_gate_status(task_id), indent=2, ensure_ascii=False))
    elif action == "advance":
        print(json.dumps(advance_gate(task_id), indent=2, ensure_ascii=False))
    elif action == "verify":
        print(json.dumps(verify_gate(task_id, extra), indent=2, ensure_ascii=False))
    else:
        print("用法:")
        print("  python3 gates.py status <task_id>")
        print("  python3 gates.py advance <task_id>")
        print("  python3 gates.py verify <task_id> <gate_id>")
