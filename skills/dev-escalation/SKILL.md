---
name: dev-escalation
description: "逃生舱：agent 遇岔口升级 → Hermes 检测 → 转人决策 → resume agent"
version: 0.1.0
platforms: [macos]
tags: [dev-flow, escalation, escape-hatch, human-in-the-loop]
---

# dev-escalation · 逃生舱协议

agent 撞到无法自决的岔口时，不瞎猜、不卡死，而是升起动态闸门等人类拍板。

## 触发条件

1. Worker 进程退出（`claude -p` 或 `codex exec` 返回）
2. 检查 `.hermes/tasks/<task_id>/escalate.json` 是否存在
3. 存在 → 进入逃生舱流程；不存在 → 正常流程

## 执行流程

### 第一步：检测 escalate.json

Worker 结束后，检查任务目录：

```bash
TASK_DIR=~/Codes/ai-dev-flow/.hermes/tasks/<task_id>
if [ -f "$TASK_DIR/escalate.json" ]; then
  echo "🚨 逃生舱激活！"
  cat "$TASK_DIR/escalate.json" | python3 -m json.tool
else
  echo "正常完成，继续闸门流程"
fi
```

### 第二步：更新状态

```bash
python3 ~/Codes/ai-dev-flow/scripts/state.py trans <task_id> ESCALATED
python3 ~/Codes/ai-dev-flow/scripts/state.py set <task_id> escalation "$(cat .hermes/tasks/<task_id>/escalate.json)"
```

### 第三步：呈现人选

解析 escalate.json，将结构化选项发给用户：

```
🚨 逃生舱 · <task_id>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
问题: 这里有两种实现方式，需要人拍板

选项 A: 用标准库 net/http
  👍 零依赖
  👎 缺少中间件支持

选项 B: 用 gin 框架
  👍 生态好，项目已有 gin
  👎 引入新依赖

🤖 Agent 推荐: B
💡 理由: 项目已有 gin 依赖，保持一致

影响面: 仅影响路由注册方式
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
你的决定？
  A) 选 A — 用标准库
  B) 选 B — 用 gin（推荐）
  C) 其他意见
```

使用 `clarify` 工具发问。

### 第四步：写回 decision.json

用户决策后，写入：

```json
{
  "task_id": "<task_id>",
  "type": "decision",
  "chosen": "B",
  "note": "用 gin，项目已有的就别再加标准库了",
  "decided_at": "2026-07-01T12:00:00Z"
}
```

```bash
cat > ~/Codes/ai-dev-flow/.hermes/tasks/<task_id>/decision.json << EOF
{...}
EOF
```

### 第五步：Resume agent

用保存的 `session_id` 恢复 Claude Code：

```bash
SESSION_ID=$(python3 -c "import json; print(json.load(open('$TASK_DIR/escalate.json'))['session_id'])")

cd $REPO_DIR
claude --resume "$SESSION_ID" -p \
  "继续任务。上一轮的决策已做出：$(cat $TASK_DIR/decision.json | python3 -c 'import json,sys; d=json.load(sys.stdin); print(f\"选{d[\"chosen\"]}，{d[\"note\"]}\")')" \
  --output-format json \
  --max-turns 8 \
  --dangerously-skip-permissions
```

### 第六步：恢复正常流程

Resume 完成后，检测是否有新的 escalate.json → 如有则循环；如无则进入 dev-gate。

---

## Worker 端（Claude Code）——如何在 prompt 中注入逃生舱指令

在 dev-run-worker 的 prompt 中加入：

```
如果你遇到以下情况，不要自己做决定，而是写 .hermes/tasks/<task_id>/escalate.json 然后退出：
- 需要在两种互斥的技术方案间选择，且各有利弊
- 修改会影响数据库 schema 或安全策略
- 发现任务描述有歧义，无法确定用户意图
- 修改范围超出原始任务定义

escalate.json 格式：
{
  "task_id": "<task_id>",
  "type": "escalate",
  "question": "清晰描述需要决策的问题",
  "options": [{"id":"A","desc":"...","pros":"...","cons":"..."}, ...],
  "recommendation": "推荐选项的 ID",
  "rationale": "推荐理由",
  "blast_radius": "影响面说明",
  "session_id": "<当前 session ID>",
  "wip_branch": "dev-flow/<task_id>"
}

写完后用 exit 0 退出（不要继续编码）。
```

## 陷阱

1. **session_id 必须在 escalate.json 中保存**——没有它就无法 resume
2. **escalate.json 必须在 WIP commit 之前写**——否则 agent 退出后文件消失
3. **resume 的 prompt 必须包含决策上下文**——否则 agent 不知道之前发生了什么
4. **逃生舱可能循环**——如果 agent 反复 escalate 同一问题，需要人介入打破循环
