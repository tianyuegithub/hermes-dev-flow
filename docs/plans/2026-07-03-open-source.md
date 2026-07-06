# Dev-Flow 开源架构 · 2026-07-03

> 原则：任何人不依赖你的 Mac/集群凭据就能装起来用。
> 安装 = npx + 填配置 + 跑起来。

## 架构

```
┌─────────────────────────────────────────────────────────┐
│  npx hermes-dev-flow setup                              │
│    ├── 提示 Claude Code API 配置 (base_url + api_key)     │
│    ├── 提示 OpenAI API key (可选，Codex 用)               │
│    ├── 提示 Git 仓库配置 (repo_url + host + user)         │
│    ├── 提示 Redis 配置 (host + port，L1 用)               │
│    ├── 提示 K8s 配置 (可选，L1 用)                        │
│    └── 生成 ~/.hermes/dev-flow/config.yaml               │
└─────────────────────────────────────────────────────────┘
         │
         ├── L0: 本地模式 (零依赖，只需 Claude Code + git)
         │      hermes → claude -p → 本地执行
         │
         └── L1: K8s 模式 (需要 Redis + K8s + Harbor)
                hermes → Redis → K3s Pod → 远程执行
```

## 文件结构

```
hermes-dev-flow/                    ← GitHub 仓库
├── package.json                    ← npx 入口
├── README.md                       ← 中文优先
├── bin/
│   └── hermes-dev-flow             ← CLI 入口 (setup/config/status)
├── skills/                         ← Hermes 技能（安装到 ~/.hermes/skills/）
│   ├── dev-flow-intake/
│   ├── dev-flow-worker/
│   ├── dev-flow-gate/
│   ├── dev-flow-escalation/
│   └── dev-flow-integrate/
├── scripts/                        ← 辅助脚本
│   ├── state.py
│   ├── intake.py
│   ├── build_prompt.py
│   ├── git_prepare.sh
│   ├── gitea_pr.sh
│   ├── redis_helper.sh
│   └── reconciler.sh
├── contracts/                      ← 三份契约 schema
│   ├── input.schema.json
│   ├── output.schema.json
│   └── escalate.schema.json
├── docker/                         ← Worker 镜像（给 L1 用）
│   ├── Dockerfile.worker
│   ├── worker-entrypoint.sh
│   ├── dev-flow-spec
│   └── reset.sh
├── k8s/                            ← K8s 部署模板（变量化，不含真实凭据）
│   ├── namespace.yaml
│   ├── secrets-template.yaml       ← 模板，用户填自己的 key
│   └── worker-deployment.yaml
├── config/
│   └── config.example.yaml         ← 配置模板（被 .gitignore 忽略真实值）
└── docs/
    ├── QUICKSTART.md
    ├── L0-GUIDE.md
    └── L1-GUIDE.md
```

## 安装流程

```bash
# 1. 安装
npx hermes-dev-flow setup

# 交互式问答:
#   ? Claude Code API base URL [https://open.bigmodel.cn/api/anthropic]:
#   ? Claude Code API key: ********
#   ? OpenAI API key (可选，按回车跳过):
#   ? Git 仓库 URL [ssh://git@your-host.com/user/repo.git]:
#   ? Git 托管平台 [gitea]:
#   ? Redis host [192.168.31.173]:
#   ? Redis port [32319]:
#   ? K8s namespace (可选，L1 用):
#
#   配置已写入 ~/.hermes/dev-flow/config.yaml
#   技能已安装到 ~/.hermes/skills/dev-flow/
#   脚本已安装到 ~/.hermes/dev-flow/scripts/

# 2. 验证
hermes-dev-flow doctor
#    Claude Code: ✅ v2.1.177
#    Git: ✅ git@your-host.com/user/repo.git
#    Redis: ✅ PONG (可选)
#    K8s: ✅ (可选)

# 3. 使用（Hermes 聊天里自然语言触发）
#    "deer-flow 加一个 /health 接口"
#    "pod 模式：deer-flow 改一下首页文案"
```

## 凭据管理——零硬编码

| 凭据 | 存储 | 注入方式 |
|------|------|---------|
| Claude Code API key | `~/.hermes/dev-flow/config.yaml` | 技能 Step 4 运行时读 `config.yaml` |
| OpenAI API key | 同上 | 同上 |
| Git SSH key | 用户自己的 `~/.ssh/` | 镜像里通过 K8s Secret mount |
| Redis 地址 | 同上 | 脚本读 `config.yaml` |
| Gitea/Harbor 密码 | 同上 | 脚本读 `config.yaml` |

## 和当前实现的关系

```
当前 ai-dev-flow/ 仓库          →   开源 hermes-dev-flow 仓库
─────────────────────────────────────────────────────
scripts/ (硬编码 host/key)      →   scripts/ (读 config.yaml)
k8s/ (含真实凭据)               →   k8s/ (模板，凭据由 setup 生成)
skills/ (引用路径写死)           →   skills/ (统一从 config.yaml 读)
docker/ (镜像已推 Harbor)       →   docker/ (用户自己 build 或 pull)
docs/plans/ (内部设计)          →   docs/ (用户文档)
```

## L0 vs L1 安装差异

| | L0 (最小) | L1 (完整) |
|---|-----------|----------|
| 依赖 | Claude Code + git | + Redis + K8s + Harbor |
| 安装 | npx setup → 只填 Claude 和 git 配置 | 填全部 |
| 使用 | "deer-flow 加 XX" → 本地 claude -p | "pod 模式：deer-flow 加 XX" |
| 镜像 | 不需要 | docker build + push |
| K8s | 不需要 | kubectl apply -f k8s/ |
