# Hermes Dev-Flow · AI 开发流程编排框架 — 完整交接文档

**最后更新**: 2026-07-14  
**当前版本**: v0.5.1  
**仓库**: `github.com/tianyuegithub/hermes-dev-flow`

> **规划状态（2026-07-14）**：当前代码仍是 v0.5.1 原型；已确认的 V2 目标架构与实施顺序见 [`docs/superpowers/plans/2026-07-14-hermes-v2-k3s-dag-fusion.md`](superpowers/plans/2026-07-14-hermes-v2-k3s-dag-fusion.md)。该计划保留 K3s 项目亲和 Pod 热池，旧的“删除 L1/K3s”重建方向已经废止。本文以下内容只描述当前实现，不代表 V2 已完成。

---

## 一、项目定位

AI 驱动的端到端软件开发流水线。Hermes 作为常驻编排智能体，调度 Claude Code / Codex / OpenCode 三种 CLI agent 在黑盒中执行编码任务，通过三份契约（输入/输出/逃生舱）和六项防假绿核查实现质量保障，最终自动 push + 创建 PR。

## 二、系统架构

```
用户 (自然语言触发)
    │
    ▼
┌─────────────────────────────────────────┐
│  Hermes · 常驻编排层 (Mac)               │
│                                          │
│  dev-intake    ← 意图识别, 分类创建任务    │
│  dev-worker    ← 调 CLI agent 黑盒执行    │
│  dev-gate      ← 六项防假绿核查, 人拍板   │
│  dev-escalation← 逃生舱, 遇岔口升级人决策  │
│  dev-integrate ← push + 创建 PR           │
└──────────────────┬──────────────────────┘
                   │
    ┌──────────────┼──────────────┐
    ▼              ▼              ▼
  L0 本地       L1 Pod 热池    Redis 引用传递
  claude -p     K3s Worker      spec → queue → pod
  (当前主力)     (已部署验证)     (已就绪)
```

## 三、用户需求清单

| # | 需求 | 状态 |
|---|------|------|
| 1 | AI 自动编码 (Claude Code) | ✅ |
| 2 | AI 自动编码 (Codex) | ⚠️ 容器沙箱兼容 |
| 3 | AI 自动编码 (OpenCode 多模型) | ✅ Pod 中验证 |
| 4 | 三份契约 (input/output/escalate) | ✅ |
| 5 | 六项防假绿核查 | ✅ |
| 6 | 逃生舱协议 | ✅ |
| 7 | L0 本地执行 | ✅ |
| 8 | L1 K3s Pod 热池执行 | ✅ |
| 9 | Redis 引用传递 (spec/output/heartbeat) | ✅ |
| 10 | Pod 热池 + reset + Reconciler | ✅ |
| 11 | OpenSpec 融合 (spec.tasks + DAG + delta_verify) | ✅ |
| 12 | 多仓库支持 (repos.json) | ✅ |
| 13 | turns=300, budget=$15 默认 | ✅ |
| 14 | 严格流程 (STEP X/Y 打印, 硬闸门) | ✅ |
| 15 | 实时观测 (stream_worker + dashboard SSE) | ✅ |
| 16 | Apple 风格 Web 仪表盘 | ✅ |
| 17 | 仪表盘任务排序(运行中置顶) | ✅ |
| 18 | 仪表盘任务停止/恢复 | ✅ |
| 19 | 仪表盘 DAG 节点查看产物 | ✅ |
| 20 | K3s 未连接禁止创建 Pod 任务 | ✅ |
| 21 | OpenSpec 安装集成 | ✅ |
| 22 | 开源封装 (npx CLI + config 系统) | ✅ |
| 23 | 镜像 CI (GitHub Actions → ghcr.io) | ✅ |
| 24 | 通知 (Hermes 消息 + 邮件) | ⬜ |
| 25 | 多 CLI 择优 | ⬜ |
| 26 | npm publish | ⏸️ GFW 受阻 |
| 27 | Codex 容器沙箱修复 | ⚠️ |
| 28 | Web 面板完整功能 (对话/跟踪/DAG 交互) | ⚠️ 部分完成 |
| 29 | 云效 API 对接 | ⬜ |
| 30 | 三道人工把关 (dev/test/PM) | ⬜ |

## 四、文件结构

```
hermes-dev-flow/
├── bin/
│   └── hermes-dev-flow          ← npx CLI (setup/doctor/config/status)
├── scripts/
│   ├── state.py                  ← 状态机 (CREATED→...→DONE)
│   ├── intake.py                 ← 意图识别 + 创建任务
│   ├── build_prompt.py           ← 从 input.json 拼 Claude prompt
│   ├── git_prepare.sh            ← clone + branch + clean
│   ├── gitea_pr.sh               ← Gitea API 创建 PR
│   ├── redis_helper.sh           ← Redis 读写封装
│   ├── reconciler.sh             ← Pod 热池监控 + 故障恢复
│   ├── dev_flow_config.py        ← 统一配置读取
│   ├── repos.json                ← 仓库注册表
│   ├── compare_outputs.py        ← 多 CLI 择优对比引擎
│   ├── task_runner.py            ← DAG 拓扑排序子任务执行器
│   ├── delta_verify.py           ← Delta Spec 验证器
│   ├── openspec_watcher.py       ← OpenSpec 提案定时拉取
│   ├── stream_worker.py          ← L0 本地 stream-json 实时解析
│   ├── progress_push.py          ← L1 Pod Redis Pub/Sub 推送
│   ├── progress_subscribe.py     ← Hermes 端订阅实时打印
│   ├── dashboard.py              ← Web 仪表盘 HTTP 服务 (端口 28100)
│   └── dashboard.html            ← Apple 风格仪表盘前端
├── skills/                       ← Hermes 技能 (注册到 ~/.hermes/skills/dev-flow/)
│   ├── dev-intake/SKILL.md       ← 意图识别 (v0.2)
│   ├── dev-worker/SKILL.md       ← 黑盒执行 (v0.3)
│   ├── dev-gate/SKILL.md         ← 验证闸门 (v0.2)
│   ├── dev-escalation/SKILL.md   ← 逃生舱 (v0.1)
│   └── dev-integrate/SKILL.md    ← 集成收口 (v0.1)
├── contracts/
│   ├── input.schema.json         ← 输入契约 JSON Schema
│   ├── output.schema.json        ← 输出契约 JSON Schema
│   └── escalate.schema.json      ← 逃生舱 JSON Schema
├── docker/
│   ├── Dockerfile.worker         ← Worker 镜像 (node:20-slim + 3 CLI)
│   ├── worker-entrypoint.sh      ← Pod 主循环 (BLPOP + heartbeat + reset)
│   ├── dev-flow-spec             ← Redis spec 读写 CLI 工具
│   ├── reset.sh                  ← Pod reset 契约
│   └── task_runner.py            ← DAG 子任务执行器 (打入镜像)
├── k8s/
│   ├── secrets-template.yaml     ← K8s Secret 模板 (凭据占位符)
│   └── worker-deployment.yaml    ← Worker Deployment
├── config/
│   └── config.example.yaml       ← 配置模板 (用户填自己的凭据)
├── tests/
│   ├── test_state_machine.py     ← 状态机测试 (5/5)
│   ├── test_build_prompt.py      ← prompt 生成测试 (2/2)
│   └── test_intake.py            ← intake 分类测试 (6/6)
├── docs/
│   ├── plans/                    ← 设计文档
│   │   ├── 2026-07-01-L1-design.md
│   │   ├── 2026-07-03-open-source.md
│   │   ├── 2026-07-09-openspec-fusion.md
│   │   ├── 2026-07-13-observability.md
│   │   └── ...
│   └── architecture-current.html ← 架构 SVG 图
├── README.md                     ← 开源文档
├── package.json                  ← npm 包定义
├── .gitignore                    ← 排除凭据/任务数据
└── .github/workflows/
    └── docker-publish.yml        ← GitHub Actions 自动构建镜像
```

## 五、核心数据流

### L0 本地模式

```
用户说 "deer-flow 加 /health 接口"
  → intake 分类 (feature/low/验证) → 创建 input.json
  → build_prompt.py 生成 prompt → 写 prompt.txt
  → 本地 claude --bare -p (stream-json 实时打印)
  → git diff + commit → output.json
  → gate 六项防假绿 → 人拍板
  → push + gitea_pr.sh → PR
```

### L1 Pod 热池模式

```
Hermes                     Redis                    K3s Worker Pod
  │                          │                         │
  │ SET spec:<id> {input}    │                         │
  ├─────────────────────────►│                         │
  │ RPUSH pod:queue <id>     │                         │
  ├─────────────────────────►│                         │
  │                          │ BLPOP queue              │
  │                          │◄────────────────────────┤
  │                          │ GET spec:<id>            │
  │                          │◄────────────────────────┤
  │                          │ SET heartbeat:<id> TTL60 │
  │                          │◄────────────────────────┤ (每30s)
  │                          │                         │
  │                          │    claude -p 执行        │
  │                          │    git commit + push     │
  │                          │                         │
  │                          │ SET output:<id>          │
  │                          │◄────────────────────────┤
  │ GET output:<id>          │                         │
  ├─────────────────────────►│                         │
  │                          │                         │ reset.sh → idle
```

## 六、部署方式

### 用户安装 (新用户从零开始)

```bash
# 1. 安装 Claude Code
npm install -g @anthropic-ai/claude-code

# 2. 安装 Dev-Flow (从 GitHub 直接装)
npm install -g github:tianyuegithub/hermes-dev-flow

# 3. 交互式配置
hermes-dev-flow setup
#    → Claude API key + base URL
#    → OpenAI API key (Codex, 可选)
#    → OpenCode API key (可选)
#    → Git 仓库 URL + 触发词
#    → Redis (L1, 可选)
#    → K8s (L1, 可选)
#    → Worker 参数 (turns=300, budget=$15)

# 4. 环境检查
hermes-dev-flow doctor

# 5. L1 部署 (可选)
kubectl apply -f k8s/secrets-template.yaml  # 替换占位符
kubectl apply -f k8s/worker-deployment.yaml
```

### 使用方式

```
在 Hermes 聊天中说:
  "deer-flow 加 XX"           → L0 本地执行
  "pod 模式: deer-flow 加 XX"  → L1 Pod 执行
  "验证 task-xxx"              → gate 核查
  "开 PR"                      → push + 创建 PR
```

### 仪表盘访问

```bash
python3 scripts/dashboard.py
# → http://localhost:28100
```

## 七、Redis Key 设计

| Key | 用途 | 写者 | TTL |
|-----|------|------|-----|
| `spec:<task_id>` | 输入契约 | Hermes | 永久 |
| `spec:<task_id>:v<N>` | 版本化 spec | Hermes | 永久 |
| `output:<task_id>` | 输出契约 | Worker Pod | 永久 |
| `heartbeat:<task_id>` | 心跳 | Worker Pod | 60s |
| `status:<task_id>` | 任务运行状态 | Worker Pod | 永久 |
| `escalate:<task_id>` | 逃生舱数据 | Worker Pod | 永久 |
| `pod:<name>:state` | Pod 状态 (idle/busy/resetting) | Pod | 永久 |
| `pod:<name>:queue` | 任务队列 | Hermes | BLPOP |

## 八、配置说明

`~/.hermes/dev-flow/config.yaml` 或 `config/config.example.yaml`:

```yaml
claude:        # Claude Code API (必填)
  base_url: "https://open.bigmodel.cn/api/anthropic"
  api_key: "..."

openai:        # Codex (可选)
  api_key: "sk-..."

opencode:      # OpenCode 多模型 (可选)
  api_key: "..."

repos:         # Git 仓库 (可多个)
  - url: "ssh://git@host/user/repo.git"
    triggers: ["触发词1", "触发词2"]

redis:         # L1 用 (可选)
  host: "192.168.31.173"
  port: 32319

k8s:           # L1 用 (可选)
  namespace: "dev-flow"
  image: "ghcr.io/user/hermes-dev-flow/worker:latest"

worker:
  max_turns: 300
  max_budget_usd: 15
```

## 九、已知问题

| # | 问题 | 影响 | 解决方向 |
|---|------|------|---------|
| 1 | Claude Code 走智谱 API 间歇 529 过载 | 高峰期不可用 | 切 DeepSeek 或 Anthropic 官方 |
| 2 | Codex 容器 sandbox 不兼容 | Pod 中不可用 | `--sandbox danger-full-access` 或等更新 |
| 3 | 非 bare 模式 MCP 初始化阻塞 | Claude Code 非 bare 不可用 | 智谱 API 不支持 MCP |
| 4 | worker_entrypoint heredoc 嵌套引号易出错 | 多次 patch 后语法错误 | 已重写为简洁版本 |
| 5 | GitHub API 被 GFW 墙 | gh CLI 不可用 | 走 SSH 隧道代理 |
| 6 | K3s kubectl 需 NO_PROXY="*" | sing-box 拦截内网流量 | 已记录到记忆和技能 |
| 7 | npm login 不可用 | 无法 npm publish | 改用 GitHub 直装 |
| 8 | Web 仪表盘在 Hermes 内嵌浏览器 onclick 不响应 | 点击事件丢失 | 需在外部浏览器打开 |

## 十、待优化项 (优先级排序)

### P0

- 打标签触发 GitHub Actions 构建公开镜像
- CI 加自动测试

### P1

- 通知系统 (Hermes 消息 + 邮件)
- task_runner/delta_verify/openspec_watcher 补充测试
- 仪表盘会话恢复 (CANCELLED→EXECUTING)

### P2

- 多 CLI 择优打通 (Claude Code + OpenCode 并跑)
- Web 面板实时对话功能
- npm publish (等网络问题解决)

### P3

- 云效 API 对接
- 三道人工把关 (dev/test/PM gate)
- 安全审计

## 十一、关键技术决策

| 决策 | 原因 |
|------|------|
| --bare 模式必用 | 非 bare 在智谱 API 下 MCP 初始化永久阻塞 |
| 300 turns / $15 预算 | turns 给够干活, 预算兜底防烧钱 |
| 工作副本 symlink | 避免每次 clone 74MB (秒级 vs 分钟级) |
| Git 操作绕过代理 (-c http.proxy=) | sing-box 拦截内网 Gitea 传输 |
| Docker 非 root 用户 | Claude Code 禁止 root 下 --dangerously-skip-permissions |
| Redis 引用传递 (非文件共享) | Pod 间只传 task_id, spec 在 Redis 里 |
| Pod 热池 + BLPOP 队列 (非一次性) | 设计文档 §5 原文: 跑完 reset, 供下个任务复用 |
| Gitea SSH 30022 端口 | K3s NodePort 映射, 192.168.31.7:22 是 PVE 宿主机 |
| Secret 和 Deployment 分离 YAML | 避免 kubectl apply 时 placeholder 覆盖真实凭据 |
| NO_PROXY="*" kubectl | sing-box 拦截 192.168.31.x 内网 K3s API 流量 |
