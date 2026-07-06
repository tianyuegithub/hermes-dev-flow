# L2 执行计划 · 2026-07-03

> 依赖顺序: 配置入口 → 镜像 CI → 多仓库 → 通知 → 冻结引擎 → Web 面板 → 多 CLI
> 每个 Phase 完即验证，卡壳跳过继续。

---

## Phase 1: hermes-dev-flow setup 完善（Codex key + 镜像源选择）

**依赖**: 无  
**产出**: setup 交互式向导支持 OpenAI key + 镜像源选择  
**验证**: `npx hermes-dev-flow setup` 填写所有字段 → config.yaml 包含 openai.api_key 和 image.source

### 任务

| # | 任务 | 说明 |
|---|------|------|
| 1.1 | setup 向导加 OpenAI API key 提示 | 已有框架，补充 openai 段 |
| 1.2 | setup 向导加 Worker 镜像源选择 | ghcr.io / docker.io / 自建 Harbor |
| 1.3 | K8s Secret 模板加 OPENAI_API_KEY 字段 | secrets-template.yaml |
| 1.4 | Worker Deployment 确保 OPENAI_API_KEY env 注入 | 已有，验证 |

---

## Phase 2: 镜像 CI（GitHub Actions → ghcr.io）

**依赖**: Phase 1（知道镜像名）  
**产出**: tag push → 自动 docker build + push ghcr.io  
**验证**: `git tag v0.3.0 && git push --tags` → ghcr.io 上出现镜像

### 任务

| # | 任务 | 说明 |
|---|------|------|
| 2.1 | 写 `.github/workflows/docker-publish.yml` | GitHub Actions |
| 2.2 | 测试 CI | push tag → 等待 Actions 完成 → `docker pull ghcr.io/...` |
| 2.3 | README 加 docker pull 命令 | 公开拉取文档 |

---

## Phase 3: 多仓库支持

**依赖**: Phase 1（config.yaml 有完整配置）  
**产出**: repos 数组 + intake 多 trigger 匹配 + worker 理解多仓库  
**验证**: 说 "另一个项目加 XX" 能匹配到正确的仓库

### 任务

| # | 任务 | 说明 |
|---|------|------|
| 3.1 | config.yaml 的 repo 改 repos 数组 | `repos: [{url, triggers, clone_url, ...}]` |
| 3.2 | intake.py 支持多仓库匹配 | classify() 遍历 repos，按 triggers 匹配 |
| 3.3 | Worker entrypoint 从 spec 读 repo_url | spec 里已有 repo_url 字段 |

---

## Phase 4: 通知（Hermes 消息 + 邮件）

**依赖**: Phase 2（Reconciler 已就绪）  
**产出**: 任务完成/逃生舱/Pod 崩溃 → Hermes 消息 + 可选邮件  
**验证**: 投一个任务 → 完成后 Hermes 通知 + 邮件到达

### 任务

| # | 任务 | 说明 |
|---|------|------|
| 4.1 | Reconciler 末尾加通知钩子 | 检测到状态变化 → 触发通知 |
| 4.2 | Hermes 消息通知 | 写文件或调 Redis，Hermes 技能读到后 clarify |
| 4.3 | 邮件通知（可选） | sendmail 或 SMTP |

---

## Phase 5: 冻结引擎（Spec 版本化）

**依赖**: Phase 1（config.yaml 就绪）  
**产出**: 打回 → spec:v2（v1 留痕），版本号递增  
**验证**: 打回一个任务 → spec:v2 存在且内容不同

### 任务

| # | 任务 | 说明 |
|---|------|------|
| 5.1 | Redis key 加版本后缀 | `spec:<id>:v1` / `spec:<id>:v2` |
| 5.2 | gate 打回时创建新版本 | `dev-flow-gate` Step 5 打回分支 |
| 5.3 | worker 读取最新版本 spec | `dev-flow-spec fetch` 自动选最新版本 |

---

## Phase 6: Web 面板（可选）

**依赖**: Phase 4（有通知机制后自然延伸）  
**产出**: 一个简单的 HTML 仪表盘  
**验证**: 浏览器打开 → 看到任务列表 + Pod 状态 + 最近日志

### 任务

| # | 任务 | 说明 |
|---|------|------|
| 6.1 | 仪表盘 HTML 页面 | 纯静态，读 Redis/state.json 渲染 |
| 6.2 | 后端 API（或直接用 Redis 直连） | 最小化：Python HTTP server 调 redis_helper |
| 6.3 | README 加访问说明 | `python3 dashboard.py` → http://localhost:8080 |

---

## Phase 7: 多 CLI 择优（推迟）

**依赖**: Phase 1（Codex key 就绪）  
**状态**: 推迟，等 Codex Pod sandbox 稳定

---

## 执行顺序

```
Phase 1 (setup 完善)
    │
    ▼
Phase 2 (镜像 CI)
    │
    ├──▶ Phase 3 (多仓库)
    │
    ├──▶ Phase 4 (通知)
    │       │
    │       ▼
    │    Phase 6 (Web 面板)
    │
    └──▶ Phase 5 (冻结引擎)
    
Phase 7 (多 CLI) → 推迟
```

Phase 3/4/5 互不依赖，Phase 3+4 可并行。
