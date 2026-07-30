---
name: dev-escalation
description: "逃生舱：agent 遇岔口升级 → 检测 Redis escalate key → 转人决策 → resume agent"
version: 1.0.0
platforms: [macos]
tags: [dev-flow, escalation, escape-hatch, human-in-the-loop, redis]
---

# dev-escalation · 逃生舱协议 v1.0 (Redis)

> 路径约定：`$DEV_FLOW_HOME` = Dev-Flow 根目录。运行 `hermes-dev-flow home` 可查；未设置时 `export DEV_FLOW_HOME=<包安装目录>`。

agent 撞到无法自决的岔口时，不瞎猜、不卡死，而是写 Redis `escalate:<task_id>`，
Hermes 检测到后转给人拍板。

## 触发条件

1. Worker Pod 执行完成（Claude 或 Codex 返回）
2. 检查 Redis `escalate:<task_id>` 是否存在
3. 存在 → 进入逃生舱流程；不存在 → 正常流程

## 执行流程（严格 v1.0）

### [STEP 1/6] 检测 Redis escalate

```bash
TASK_ID="<task_id>"
ESCALATE=$(redis-cli -h "$REDIS_HOST" -p "${REDIS_PORT:-6379}" GET "escalate:$TASK_ID" 2>/dev/null)

if [ -n "$ESCALATE" ]; then
  echo "🚨 逃生舱激活！$TASK_ID"
  echo "$ESCALATE" | python3 -m json.tool
else
  echo "无逃生舱，继续正常流程"
fi
```

### [STEP 2/6] 更新任务状态

```bash
python3 $DEV_FLOW_HOME/scripts/state.py trans "$TASK_ID" ESCALATED
redis-cli -h "$REDIS_HOST" -p "${REDIS_PORT:-6379}" SET "status:$TASK_ID" "escalated"
```

### [STEP 3/6] 呈现给人

解析 escalate JSON，将结构化选项发给用户（使用 clarify 工具）：

```
🚨 逃生舱 · <task_id>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
问题: <question>

选项 A: <desc>
  👍 <pros>
  👎 <cons>

选项 B: <desc>
  👍 <pros>
  👎 <cons>

🤖 Agent 推荐: <recommendation>
💡 理由: <rationale>

影响面: <blast_radius>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
你的决定？
```

### [STEP 4/6] 写回决策到 Redis

用户决策后写入 Redis：

```bash
redis-cli -h "$REDIS_HOST" -p "${REDIS_PORT:-6379}" SET "escalate:$TASK_ID:decision" '{
  "task_id": "<task_id>",
  "type": "decision",
  "chosen": "B",
  "note": "用户决定的文字说明",
  "decided_at": "<ISO timestamp>"
}'
```

### [STEP 5/6] Resume agent（L0 模式）

**注意**: L1 Pod 热池的 resume 暂不支持（Pod 内 agent 进程已退出）。
当前处理方式：

- **选项 A (重试)**: 修改 spec 的 goal 更明确后，重新 RPUSH 到队列
- **选项 B (放弃)**: 标记 status 为 failed
- **选项 C (人工)**: 保存决策，等人手动介入

```bash
# 重试：修改 spec 后重新入队
POD_NAME=$(redis-cli -h "$REDIS_HOST" -p "${REDIS_PORT:-6379}" KEYS "pod:*:state" | head -1 | sed 's/pod://;s/:state//')
redis-cli -h "$REDIS_HOST" -p "${REDIS_PORT:-6379}" RPUSH "pod:$POD_NAME:queue" "$TASK_ID"
```

### [STEP 6/6] 恢复正常流程

决策执行后，清除 escalate key，继续 gate 流程。

```bash
redis-cli -h "$REDIS_HOST" -p "${REDIS_PORT:-6379}" DEL "escalate:$TASK_ID"
redis-cli -h "$REDIS_HOST" -p "${REDIS_PORT:-6379}" SET "status:$TASK_ID" "running"
```

---

## Worker 端 — 自动写 Redis escalate

worker-entrypoint.sh 在输出解析阶段自动检测：
- 如果 `diff_stat` 为空（agent 无代码产出）
- 自动写 `escalate:<task_id>` 到 Redis
- 包含 worker 类型、session_id、原始输出片段

Hermes 端的技能只需要检测 Redis key 即可。

## 陷阱

1. **Redis key 命名**: `escalate:<task_id>` for escalate, `escalate:<task_id>:decision` for decision
2. **L1 Pod resume 限制**: Pod 热池在任务间执行 reset，无法保留 agent 会话。resume 通过重新入队实现
3. **逃生舱可能循环**: 如果 agent 反复 escalate 同一问题，需要人介入打破循环
4. **清理**: 决策完成后记得 DEL escalate key，避免下次误触发
