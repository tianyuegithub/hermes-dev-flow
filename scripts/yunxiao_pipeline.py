#!/usr/bin/env python3
"""
yunxiao_pipeline.py — Dev-Flow ↔ 云效流水线打通

功能:
  - 任务完成时触发云效流水线运行
  - 从云效拉取待开发任务 → 创建 dev-flow 任务
  - 回写任务状态和制品版本到云效

用法:
  python3 yunxiao_pipeline.py trigger <task_id> [--pipeline-id <id>]
  python3 yunxiao_pipeline.py pull    [--project-id <id>]
  python3 yunxiao_pipeline.py writeback <task_id>
"""
import os, sys, json, subprocess
from datetime import datetime
from urllib.request import Request, urlopen
from urllib.error import URLError

# ── 配置 ─────────────────────────────────────────────
CONFIG_PATH = os.path.expanduser("~/.hermes/dev-flow/config.yaml")
YUNXIAO_BASE = "https://devops.aliyun.com/api"  # 云效 OpenAPI 基础地址


def load_config():
    """加载 dev-flow 配置"""
    config = {}
    try:
        with open(CONFIG_PATH) as f:
            import yaml
            config = yaml.safe_load(f)
    except:
        # 回退: 从环境变量读
        config["yunxiao"] = {
            "org_id": os.environ.get("YUNXIAO_ORG_ID", ""),
            "token": os.environ.get("YUNXIAO_TOKEN", ""),
            "pipeline_id": os.environ.get("YUNXIAO_PIPELINE_ID", ""),
        }
    return config


def trigger_pipeline(task_id: str, pipeline_id: str = None) -> dict:
    """触发云效流水线运行"""
    config = load_config()
    yx = config.get("yunxiao", {})

    org_id = yx.get("org_id", "")
    token = yx.get("token", "")
    pid = pipeline_id or yx.get("pipeline_id", "")

    if not (org_id and pid):
        return {"status": "skipped", "reason": "云效未配置 (缺 org_id/pipeline_id)"}

    # 调用云效 MCP create_pipeline_run
    # 注意: 实际调用走 MCP 工具, 这里是占位——MCP 调用在 Hermes 对话层完成
    return {
        "status": "triggered",
        "org_id": org_id,
        "pipeline_id": pid,
        "task_id": task_id,
        "branch": f"dev-flow/{task_id}",
        "note": "实际的 MCP yunxiao__create_pipeline_run 调用需要在 Hermes 对话中发起",
    }


def pull_workitems(project_id: str = None) -> list:
    """从云效拉取待开发任务"""
    config = load_config()
    yx = config.get("yunxiao", {})

    # 占位: 实际调用 MCP yunxiao__search_workitems
    return [{
        "note": "实际 MCP 调用在 Hermes 对话中发起: mcp__yunxiao__search_workitems",
        "filters": {"category": "Req", "status": "100010", "spaceType": "Project"},
    }]


def writeback(task_id: str) -> dict:
    """回写任务状态和制品到云效"""
    # 读取 dev-flow 任务的 evidence
    task_dir = os.path.expanduser(f"~/Codes/ai-dev-flow/.hermes/tasks/{task_id}")
    evidence = {}
    try:
        with open(os.path.join(task_dir, "state.json")) as f:
            evidence = json.load(f)
    except: pass

    return {
        "status": "pending",
        "task_id": task_id,
        "commit": evidence.get("evidence", {}).get("commits", []),
        "note": "实际 MCP yunxiao__update_work_item 调用在 Hermes 对话中发起",
    }


if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else "help"
    task_id = sys.argv[2] if len(sys.argv) > 2 else ""
    pipeline_id = sys.argv[3].replace("--pipeline-id=", "") if len(sys.argv) > 3 else None

    if action == "trigger":
        result = trigger_pipeline(task_id, pipeline_id)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    elif action == "pull":
        result = pull_workitems()
        print(json.dumps(result, indent=2, ensure_ascii=False))
    elif action == "writeback":
        result = writeback(task_id)
        print(json.dumps(result, indent=2, ensure_ascii=False))
