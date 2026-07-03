---
name: dev-intake
description: "意图识别：将用户自然语言请求分类为任务计划（类型/风险/闸门/仓库/CLI 模式），轻确认后创建任务。"
version: 0.1.0
platforms: [macos]
tags: [dev-flow, intake, classification, routing]
---

# dev-intake · 意图识别与路由

系统前门。将用户的一句话需求解析成结构化任务计划，轻确认后建任务。

## 分类逻辑

根据用户请求的特征，判定以下维度：

### 1. task_type（驱动主图裁剪路径）

| 信号 | 类型 | 走哪些阶段 |
|------|------|-----------|
| "加一个"、"实现"、"开发"、"新增功能" | `feature` | 全程：方案→编码→测试→验证→集成 |
| "修"、"bug"、"报错"、"不管用" | `bug` | 定位→修复→测试→验证（跳架构·计划） |
| "文档"、"readme"、"写说明" | `doc` | intake→文档→轻验证 |
| "调研"、"看一下"、"怎么实现" | `research` | 到方案止·不编码 |
| "重构"、"整理"、"优化结构" | `refactor` | 方案→编码→测试→验证 |

### 2. risk（驱动闸门深度）

| 信号 | 风险 | 闸门 |
|------|------|------|
| 改 schema/数据库/安全/认证、触生产 | `high` | 全闸门（方案+架构+计划+验证） |
| 普通功能增改 | `medium` | 方案+验证 |
| 加日志、改文案、注释、格式化 | `low` | 零闸门或仅验证 |

### 3. gates（静态预挂闸门列表）

根据 risk 自动生成，但可被用户覆盖：
- `high` → `["方案", "架构", "验证"]`
- `medium` → `["方案", "验证"]`
- `low` → `["验证"]` 或 `[]`

### 4. decompose（是否需拆分）

信号：跨多个模块 / 超单 agent run 承载 / 明确说"分几步"。

### 5. cli_mode（worker 选择）

| 模式 | 何时用 |
|------|--------|
| `route:claude` | 默认（L0 已验证） |
| `route:codex` | 用户指定 / Codex 更擅长的任务 |
| `single:claude` | 明确指定 Claude |
| `single:codex` | 明确指定 Codex |
| `compare` | v2：高价值任务并跑多个 CLI |

### 6. project（仓库匹配）

从用户话中提取项目名 → 匹配已知仓库：
- `deer-flow` → `ssh://git@192.168.31.7:30022/datavdl/deer-flow.git`
- 默认：询问用户

---

## 执行流程

### 第一步：分析用户请求

读用户原始消息，按上述分类逻辑推理出任务计划：

```
你说："deer-flow 加一个 POST /echo 接口，返回请求体"

我的分析：
  task_type:  feature  （新增功能）
  risk:       medium   （普通接口，不改 schema）
  gates:      ["方案", "验证"]
  decompose:  false    （单文件，不需要拆）
  cli_mode:   route:claude（默认）
  project:    deer-flow
```

### 第二步：轻确认

使用 `clarify` 工具发给用户确认，选项为：
1. "✅ 确认，开始"
2. "🔧 调整参数"

### 第三步：创建任务

用户确认后，调 `state.py init` + 写入 input.json：

```bash
TASK_ID="task-$(date +%Y%m%d-%H%M%S)"
python3 ~/Codes/ai-dev-flow/scripts/state.py init "$TASK_ID" "<task_type>" "<repo_url>"
python3 ~/Codes/ai-dev-flow/scripts/state.py set "$TASK_ID" worker claude
python3 ~/Codes/ai-dev-flow/scripts/state.py set "$TASK_ID" gates '<gates_json>'

# 写入 input.json
cat > ~/Codes/ai-dev-flow/.hermes/tasks/$TASK_ID/input.json << EOF
{
  "task_id": "$TASK_ID",
  "task_type": "<task_type>",
  "repo_url": "<repo_url>",
  "base_branch": "main",
  "goal": "<用户原话>",
  "acceptance": [...],
  "constraints": {...},
  "budget": {"max_iterations": 8, "max_wallclock_minutes": 15}
}
EOF
```

### 第四步：流转状态 → 进入方案闸门（如有）

```bash
python3 ~/Codes/ai-dev-flow/scripts/state.py trans "$TASK_ID" GATE_PENDING
```

然后进入 `dev-gate` 等待方案闸门通过。

---

## 已知仓库注册表

```json
{
  "deer-flow": {
    "repo_url": "ssh://git@192.168.31.7:30022/datavdl/deer-flow.git",
    "gitea_api": "http://192.168.31.7:30000/api/v1/repos/datavdl/deer-flow",
    "default_branch": "main",
    "language": "python",
    "tech_stack": ["fastapi", "langgraph", "uv"]
  }
}
```

新增仓库时更新此表。

## 陷阱

1. **不要直接开始执行**——intake 的职责只是分类和创建任务计划，实际执行由 dev-run-worker 负责
2. **风险判定宁高勿低**——不确定时按 medium 处理，挂方案闸门兜底
3. **验收标准必须从用户话中推导**——如果用户没说清楚，在确认环节追问
