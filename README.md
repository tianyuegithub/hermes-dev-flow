# 零脉（PactFlow）· AI 编码交付物的契约层

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

> **AI 编码的瓶颈，不是模型不够聪明，而是交付物无法被问责。**
>
> PactFlow 不卷编排模式、不做 agent 本身。它只做一件事：让 AI 的每一次代码交付，都以契约开始、以机器强制校验的契约验收、以结构化证据升级给人裁决。模型可替换，供应商可替换，编排可替换——**契约不可协商**。
>
> 📜 项目宪法与决策准则：[docs/THESIS.md](docs/THESIS.md)

**编排 Hermes / Claude Code / Codex / OpenCode 黑盒执行编码任务。三份契约 + 闸门 + 逃生舱 + Redis 引用传递。**

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

| | L0 本地 | L1 临时 Pod |
|---|---|---|
| 执行方式 | `claude -p` 本地子进程 | Manager 调度：一个任务一个 K3s Pod，用完即删 |
| 启动速度 | 秒级 | 分钟级（首次镜像拉取） |
| 适合场景 | 小任务、快速验证 | 大任务、并发、强隔离 |
| 依赖 | Claude Code + git | + Redis + K8s（`k8s/manager-deployment.yaml`） |

## 快速安装

```bash
# 1. 安装 Claude Code
npm install -g @anthropic-ai/claude-code

# 2. 安装 Dev-Flow（从 GitHub 直接安装，无需 npm 账号）
npm install -g github:tianyuegithub/hermes-dev-flow

# 3. 配置
hermes-dev-flow setup

# 4. 检查环境
hermes-dev-flow doctor
```

## 使用（在 Hermes 聊天中）

```
"deer-flow 加一个 /health 接口"           → L0 本地执行
"pod 模式：deer-flow 改一下首页文案"       → L1 Pod 执行
"验证 task-xxx"                          → 闸门核查
"开 PR"                                   → push + 创建 PR
```

## L1 部署（可选）

### 使用公开镜像

```bash
docker pull ghcr.io/<user>/hermes-dev-flow/worker:latest
```

### 自建镜像

```bash
docker build -f docker/Dockerfile.worker -t your-registry/dev-flow/worker:latest .
docker push your-registry/dev-flow/worker:latest
```

# 2. 部署 K8s
kubectl apply -f k8s/namespace.yaml
kubectl create secret generic dev-flow-secrets -n dev-flow \
  --from-literal=ANTHROPIC_AUTH_TOKEN="<your-api-key>" \
  --from-literal=OPENAI_API_KEY="<your-openai-key>" \
  --from-file=GITEA_SSH_KEY=~/.ssh/id_rsa
kubectl apply -f k8s/worker-deployment.yaml
```

## 配置

路径约定：所有脚本经 `scripts/paths.py` 解析根目录——`DEV_FLOW_HOME` 环境变量 > 包安装目录。可用 `hermes-dev-flow home` 查看当前根目录。

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
