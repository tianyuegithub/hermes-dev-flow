#!/usr/bin/env python3
"""
integrate_hooks.py — Dev-Flow integrate 前置/后置钩子（2026-07-30 重构）

闭环收口（docs/THESIS.md）:
  前置: 闸门裁决未通过 → 禁止触发云效流水线与通知，退出码 1
       （此前 scorecard 结果被 capture_output 丢弃，等于没有裁决——已修复）
  后置: 云效流水线触发 + 通知推送

用法（在 dev-integrate 技能中调用）:
  python3 integrate_hooks.py pr_created <task_id> <pr_url>
"""
import os, sys, json, subprocess

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPTS_DIR)


def check_gate_decision(task_id: str) -> dict:
    """闭环收口裁决：批准则放行，未决/打回则阻断。

    先读既有闸门结论（不重跑 Scorecard，避免打断已完成的人工链）；
    仅当从未裁决过时，才跑一次 gates.decide。
    """
    import gates
    approval = gates.approval_state(task_id)

    if approval["decision"] == "pending" and approval["by"] is None:
        # 从未裁决 → 补跑一次自动裁决
        gates.decide(task_id)
        approval = gates.approval_state(task_id)

    if approval["decision"] == "approved":
        print(f"[hooks] 闸门批准（{approval['by']}）→ 放行")
        return approval

    print(f"[hooks] ⛔ 闸门未批准（{approval['decision']} by {approval.get('by') or 'none'}）")
    print(f"[hooks]    {approval.get('feedback') or '人工裁决进行中，见 gates.py status'}")
    print("[hooks]    云效触发与通知已阻断。先完成闸门流程（gates.py human ...）")
    return approval


def on_pr_created(task_id: str, pr_url: str = ""):
    """PR 创建后的钩子链"""
    print(f"[hooks] PR 创建: {pr_url}")

    # 0) 闸门裁决（闭环收口，未批准即阻断）
    decision = check_gate_decision(task_id)
    if decision["decision"] != "approved":
        sys.exit(1)

    # 1) 云效流水线触发
    print("[hooks] → 云效流水线")
    result = subprocess.run([sys.executable,
        os.path.join(SCRIPTS_DIR, "yunxiao_pipeline.py"),
        "trigger-params", task_id],
        capture_output=True, text=True)
    try:
        params = json.loads(result.stdout)
        print(f"    云效 MCP 参数已准备: {params.get('branch', '?')}")
        print(f"    下一步: 在 Hermes 中执行 mcp_{params.get('mcp_tool', '')}(...以上参数)")
    except Exception:
        print("    云效未配置，跳过")

    # 2) 通知
    print("[hooks] → 通知")
    subprocess.run([sys.executable,
        os.path.join(SCRIPTS_DIR, "notify.py"),
        "task_done", task_id], capture_output=True)

    print("[hooks] 全部完成")


if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else ""
    task_id = sys.argv[2] if len(sys.argv) > 2 else ""
    extra = sys.argv[3] if len(sys.argv) > 3 else ""

    if action == "pr_created":
        on_pr_created(task_id, extra)
    else:
        print("用法: python3 integrate_hooks.py pr_created <task_id> [pr_url]")
