#!/usr/bin/env python3
"""
integrate_hooks.py — Dev-Flow integrate 后置钩子

当前钩子:
  1. 云效流水线触发  →  PR 创建后自动跑云效流水线
  2. 通知推送        →  任务完成/失败推送 Hermes 消息
  3. Scorecard 评分  →  自动评分替代人工闸门

用法（在 dev-integrate 技能中调用）:
  python3 integrate_hooks.py pr_created <task_id> <pr_url>
"""
import os, sys, json, subprocess


def on_pr_created(task_id: str, pr_url: str = ""):
    """PR 创建后的钩子链"""
    print(f"[hooks] PR 创建: {pr_url}")

    # 1) Scorecard 评分
    print("[hooks] → Scorecard")
    subprocess.run([sys.executable,
        os.path.expanduser("~/Codes/ai-dev-flow/scripts/scorecard.py"),
        task_id, "--auto"], capture_output=True)

    # 2) 云效流水线触发
    print("[hooks] → 云效流水线")
    result = subprocess.run([sys.executable,
        os.path.expanduser("~/Codes/ai-dev-flow/scripts/yunxiao_pipeline.py"),
        "trigger-params", task_id],
        capture_output=True, text=True)
    try:
        params = json.loads(result.stdout)
        print(f"    云效 MCP 参数已准备: {params.get('branch', '?')}")
        print(f"    下一步: 在 Hermes 中执行 mcp_{params.get('mcp_tool', '')}(...以上参数)")
    except:
        print(f"    云效未配置，跳过")

    # 3) 通知
    print("[hooks] → 通知")
    subprocess.run([sys.executable,
        os.path.expanduser("~/Codes/ai-dev-flow/scripts/notify.py"),
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
