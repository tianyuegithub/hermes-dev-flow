#!/usr/bin/env python3
"""
yunxiao_pipeline.py — Dev-Flow ↔ 云效 CI/CD 对接

MCP 工具映射（在 Hermes 对话中调用）:
  trigger  → mcp__yunxiao__create_pipeline_run     (触发流水线)
  pull     → mcp__yunxiao__search_workitems        (拉取待办)
  writeback → mcp__yunxiao__update_work_item       (回写状态)
  get      → mcp__yunxiao__get_pipeline_run         (查看运行状态)

用法: python3 yunxiao_pipeline.py <action> <task_id>
      实际 MCP 调用在 Hermes review 技能中触发
"""
import os, sys, json, subprocess
from datetime import datetime

# ── 配置 ───────────────────────────────
ORG_ID = "67ed37ced6510b763eac705b"          # 云效组织 ID（已配）
PROJECT_ID = "67ee4acd7d8cbc921847ed38"      # 默认项目 ID
PIPELINE_ID = ""                               # 默认流水线 ID（需配）


def load_task(task_id: str) -> dict:
    task_dir = os.path.expanduser(f"~/Codes/ai-dev-flow/.hermes/tasks/{task_id}")
    try:
        with open(os.path.join(task_dir, "state.json")) as f:
            return json.load(f)
    except:
        return {}


# ══════════════════════════════════════════
#  以下函数在 Hermes 技能 review 步骤中调用
# ══════════════════════════════════════════

def trigger_pipeline_params(task_id: str, pipeline_id: str = "") -> dict:
    """生成 create_pipeline_run 的参数"""
    task = load_task(task_id)
    return {
        "mcp_tool": "yunxiao__create_pipeline_run",
        "organizationId": ORG_ID,
        "pipelineId": pipeline_id or PIPELINE_ID,
        "branch": f"dev-flow/{task_id}",
        "comment": f"Dev-Flow 任务 {task_id} - {task.get('task_type', '')}",
    }


def pull_workitems_params(status: str = "100010") -> dict:
    """生成 search_workitems 的参数（100010=开发中）"""
    return {
        "mcp_tool": "yunxiao__search_workitems",
        "organizationId": ORG_ID,
        "category": "Req",
        "spaceType": "Project",
        "spaceId": PROJECT_ID,
        "status": status,
        "page": 1,
        "perPage": 20,
    }


def writeback_params(task_id: str) -> dict:
    """生成 update_work_item 的参数（回写制品信息）"""
    task = load_task(task_id)
    evidence = task.get("evidence", {})
    return {
        "mcp_tool": "yunxiao__update_work_item",
        "organizationId": ORG_ID,
        "workItemId": "",           # 需从 pull 结果关联
        "updateWorkItemFields": {
            "status": "100011",     # 开发完成
            "customFieldValues": {
                "制品版本": evidence.get("commits", [""])[0],
                "代码仓库": "datavdl/deer-flow",
            },
        },
        "description": f"Dev-Flow 自动编码完成\nCommit: {evidence.get('commits', [])}",
        "formatType": "MARKDOWN",
    }


if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else "help"
    task_id = sys.argv[2] if len(sys.argv) > 2 else ""

    if action == "trigger-params":
        print(json.dumps(trigger_pipeline_params(task_id), indent=2, ensure_ascii=False))
    elif action == "pull-params":
        print(json.dumps(pull_workitems_params(), indent=2, ensure_ascii=False))
    elif action == "writeback-params":
        print(json.dumps(writeback_params(task_id), indent=2, ensure_ascii=False))
    else:
        print("用法:")
        print("  python3 yunxiao_pipeline.py trigger-params <task_id>")
        print("  python3 yunxiao_pipeline.py pull-params")
        print("  python3 yunxiao_pipeline.py writeback-params <task_id>")
        print()
        print("  输出 MCP 调用参数，在 Hermes 对话中执行: mcp__<tool>(...params)")
