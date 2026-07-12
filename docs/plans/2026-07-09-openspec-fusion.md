# OpenSpec × Dev-Flow 融合设计 · 2026-07-09

> OpenSpec 负责"做什么"（规范层），dev-flow 负责"怎么做"（执行层）。
> 上下两层互补，覆盖从需求提案到代码交付的全链路。

## 一、为什么融合

| 维度 | OpenSpec | dev-flow | 融合价值 |
|------|---------|---------|---------|
| 输入 | 自然语言 `/opsx:propose` | 自然语言 "deer-flow 加 XX" | 统一入口 |
| 规划 | proposal + specs + design + tasks | 方案闸门（口头确认） | 结构化方案替代口头确认 |
| 执行 | `/opsx:apply`（单 Agent 对话） | worker 黑盒 + 硬闸门 | 多步拆解 + 质量保障 |
| 质量 | 人类审阅 artifacts | gate 六项防假绿 + 逃生舱 | 双重质量保障 |
| 交付 | `/opsx:archive`（合并规范） | integrate（push + PR） | 归档 + 交付闭环 |
| 运行 | 本地开发机 | L0 本地 + L1 K3s Pod 热池 | 弹性执行面 |

## 二、融合架构

```
用户请求: "增加双因素认证，涉及 auth 和 ui 两个模块"
     │
     ▼
┌──────────────────────────────────────────────────┐
│  OpenSpec 规范层                                   │
│                                                    │
│  /opsx:explore  →  探索代码库，理解现状              │
│  /opsx:propose  →  生成 proposal + specs + design    │
│           ↓                                        │
│    openspec/changes/add-2fa/                        │
│    ├── proposal.md   (Why: 安全合规要求)             │
│    ├── specs/                                        │
│    │   ├── auth/spec.md   (ADDED: TOTP 验证)         │
│    │   └── ui/spec.md     (MODIFIED: 登录流程)        │
│    ├── design.md      (How: TOTP 算法选型)           │
│    └── tasks.md        (Step 1: auth 模块 → Step 2: ui) │
│                       ↓                              │
│                人类审阅 ← 方案闸门                      │
└──────────────────────┬───────────────────────────┘
                       │ spec 注入
                       ▼
┌──────────────────────────────────────────────────┐
│  Dev-Flow 执行层                                   │
│                                                    │
│  intake → spec 冻结为 input.json                    │
│     │                                               │
│     ▼                                               │
│  worker (黑盒)                                       │
│     │  tasks.md 拆为子步骤                           │
│     ├── Step 1: auth 模块 TOTP → Claude Code 执行    │
│     │        ↓ git commit + evidence                 │
│     ├── Step 2: ui 模块登录流程 → Claude Code 执行    │
│     │        ↓ git commit + evidence                 │
│     └── 集成验证 → gate 六项防假绿                    │
│     │                                               │
│     ▼                                               │
│  gate → 通过/打回 → integrate (push + PR)            │
│     │                                               │
│     ▼                                               │
│  OpenSpec archive ←→ dev-flow integrate             │
│    delta → 主规范合并 → archive/ 归档                 │
└──────────────────────────────────────────────────┘
```

## 三、Spec 契约升级

### 当前 input.json（自由格式）
```json
{
  "goal": "增加双因素认证...",
  "acceptance": ["验证码正确登录"],
  "constraints": {"forbidden": ["禁止改 main"]}
}
```

### 融合后的 input.json（结构化，来源 OpenSpec）
```json
{
  "task_id": "task-xxx",
  "task_type": "feature",
  "repo_url": "ssh://git@...",
  "openspec_change": "add-2fa",
  "spec": {
    "proposal": "openspec/changes/add-2fa/proposal.md",
    "delta_specs": {
      "auth/spec.md": ["ADDED: TOTP verification"],
      "ui/spec.md": ["MODIFIED: login flow"]
    },
    "design": "openspec/changes/add-2fa/design.md",
    "tasks": [
      {"id": "1", "title": "auth TOTP implementation", "depends": []},
      {"id": "2", "title": "ui login integration", "depends": ["1"]}
    ]
  },
  "acceptance": [
    "TOTP code validates correctly",
    "Login page shows TOTP input after password"
  ],
  "constraints": {
    "forbidden": ["禁止改 main", "禁止改其他认证方式"],
    "from_design": ["使用 SHA-1 而非 SHA-256", "种子长度 160 bit"]
  }
}
```

## 四、工作流对照

| OpenSpec 命令 | dev-flow 阶段 | 融合行为 |
|-------------|-------------|---------|
| `/opsx:explore` | intake 前 | 探索代码库 → 生成方案建议 → 用户确认 |
| `/opsx:propose <name>` | intake 方案闸门 | 生成 proposal + specs + design + tasks → 人类审阅 |
| `/opsx:apply` | worker 执行 | 按 tasks.md 拆分子步骤 → Claude Code 逐一执行 |
| （无） | gate 验证 | 六项防假绿 + self_check 对照 delta specs |
| `/opsx:archive` | integrate 归档 | Delta 合并到主规范 + push + PR |
| `/opsx:sync` | — | Hermes skills + AI agent 指令同步 |

## 五、云效流水线覆盖

| 云效需求 | 融合覆盖 |
|---------|---------|
| 任务接入 | OpenSpec `/opsx:propose` 拉取需求 + dev-flow intake 对接云效 API |
| AI 研发引擎 | OpenSpec tasks 拆解 + dev-flow worker 多步执行 |
| 多场景覆盖 | feature/bug/doc/refactor 四种 task_type + OpenSpec delta 适配 |
| 三道人工把关 | dev-flow gate(dev) → test gate(独立验证) → PM gate(业务验收) |
| 制品入库 | dev-flow integrate → 构建产物归档 + 回写云效 |
| 私有化部署 | dev-flow Docker 镜像 + K8s manifests（已有） |

## 六、实施路线

| Phase | 内容 | 改动 |
|-------|------|------|
| **融合 P0** | input.json 加 `openspec_change` + `spec.tasks` 字段 | intake.py + build_prompt.py |
| **融合 P1** | worker 支持 tasks 多步拆解执行（串行，有依赖 DAG） | worker-entrypoint + 新建 scripts/task_runner.py |
| **融合 P2** | gate 对照 delta specs 验证（不只看 diff） | dev-gate 技能 |
| **融合 P3** | `/opsx:propose` → dev-flow intake 对接 | 新建 cron job 定时拉取 |
| **融合 P4** | archive → integrate 联动（delta 合并） | integrate 技能 |
