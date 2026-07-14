# 实时观测能力设计 · 2026-07-13

> 目标：让用户在 Hermes 对话窗口实时看到 worker 执行进度，不再"投任务→黑盒→等通知"。

## 三层观测

```
┌─────────────────────────────────────────────────────┐
│  L0 本地：Claude Code stream-json → Hermes 终端实时打印 │
│  L1 Pod：Redis Pub/Sub → Hermes 订阅 → 实时推送        │
│  L2 面板：dashboard.py SSE 推送 → 浏览器实时刷新        │
└─────────────────────────────────────────────────────┘
```

## L0 本地实时（最快见效）

Claude Code 支持 `--output-format stream-json`，每一步工具调用都输出事件：

```bash
claude --bare -p "..." --output-format stream-json --verbose
```

每个事件是一行 JSON，包含：
- `system` — 系统消息（API 调用/重试）
- `assistant` — AI 思考和工具调用
- `result` — 最终结果

改造 build_prompt + worker 调用，加 `--output-format stream-json` + 实时过滤解析器。

## L1 Pod 实时（Redis Pub/Sub）

Worker entrypoint 加日志推送：

```bash
# 每个 step 后推送到 Redis
redis-cli PUBLISH "task:progress:$TASK_ID" "[worker] git prepare done"
redis-cli PUBLISH "task:progress:$TASK_ID" "[worker] claude code starting..."
```

Hermes 端订阅：

```bash
redis-cli SUBSCRIBE "task:progress:$TASK_ID"
```

## L2 面板实时（dashboard SSE）

dashboard.py 加 `/api/events` SSE 端点：

```python
# 浏览器 EventSource 连接
GET /api/events → data: {"task_id":"...","event":"worker_start","msg":"..."}
```
