# Dev-Flow · AI 开发流程编排框架

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

**Hermes 编排 Claude Code / Codex 黑盒执行编码任务。三份契约 + 闸门 + 逃生舱 + Redis 引用传递。**

```
你说: "deer-flow 加一个 /health 接口"
         │
         ▼
    ┌──────────┐    ┌──────────────┐    ┌──────────┐    ┌──────────────┐
    │ intake   │ →  │ worker (黑盒) │ →  │ gate     │ →  │ integrate    │
    │ 分类确认  │    │ Claude -p    │    │ 六项防假绿 │    │ push + PR    │
    └──────────┘    └──────────────┘    └──────────┘    └──────────────┘
```

## 两种模式

| | L0 本地 | L1 Pod 热池 |
|---|---|---|
| 执行方式 | `claude -p` 本地子进程 | K3s Pod + Redis 引用传递 |
| 启动速度 | 秒级 | 分钟级（首次镜像拉取） |
| 适合场景 | 小任务、快速验证 | 大任务、持续运行 |
| 依赖 | Claude Code + git | + Redis + K3s + Harbor |

## 快速安装

```bash
# 1. 安装 Claude Code
npm install -g @anthropic-ai/claude-code

# 2. 安装 Dev-Flow
npx hermes-dev-flow setup
#    → 交互式填写 API key、仓库地址、Redis 等配置

# 3. 检查环境
hermes-dev-flow doctor
#    Claude Code: ✅ v2.1.177
#    Git: ✅
#    Redis: ✅ PONG
```

## 使用（在 Hermes 聊天中）

```
"deer-flow 加一个 /health 接口"           → L0 本地执行
"pod 模式：deer-flow 改一下首页文案"       → L1 Pod 执行
"验证 task-xxx"                          → 闸门核查
"开 PR"                                   → push + 创建 PR
```

## L1 部署（可选）

```bash
# 1. 构建 Worker 镜像
docker build -f docker/Dockerfile.worker -t your-registry/dev-flow/worker:latest .
docker push your-registry/dev-flow/worker:latest

# 2. 部署 K8s
kubectl apply -f k8s/namespace.yaml
kubectl create secret generic dev-flow-secrets -n dev-flow \
  --from-literal=ANTHROPIC_AUTH_TOKEN="<your-api-key>" \
  --from-literal=OPENAI_API_KEY="<your-openai-key>" \
  --from-file=GITEA_SSH_KEY=~/.ssh/id_rsa
kubectl apply -f k8s/worker-deployment.yaml
```

## 配置

`~/.hermes/dev-flow/config.yaml`:

```yaml
claude:
  base_url: "https://api.anthropic.com"  # 或智谱/其他兼容端点
  api_key: "sk-ant-..."

repo:
  url: "ssh://git@github.com/user/repo.git"
  triggers: ["my-project"]  # 自然语言触发词
```

## 架构

见 [docs/architecture-current.html](docs/architecture-current.html)

## License

MIT
