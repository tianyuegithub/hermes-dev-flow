# 零脉（PactFlow）· 多智能体契约编排开发框架 — 项目总结报告

> **版本**: v0.6.0-dev  
> **报告日期**: 2026-07-23  
> **仓库**: github.com/tianyuegithub/hermes-dev-flow  
> **许可证**: MIT  
> **完成度**: 27/31（87%）  
> **代码量**: ~5,200 行（Python + Shell + HTML），27 次提交，5 个标签

---

## 一、项目定位

AI 驱动的端到端软件开发流水线。Hermes 作为常驻编排层，调度 Claude Code / Codex / OpenCode 三种 CLI agent 在黑盒中执行编码任务，通过三份契约（输入/输出/逃生舱）和 Scorecard 自动评分实现质量保障，最终自动 push + 创建 PR。

**一句话**: "多智能体契约编排开发框架——你说需求，AI 干活，闸门验收，PR 交付。"

## 二、核心架构

```
用户（自然语言 / Hermes 对话）
    │
    ▼
 编排偏好路由表（task_type → provider/model）
    │
    ├───────────────────┐
    ▼                   ▼
Claude Code         OpenCode
 (强推理)            (高性价比)
    │                   │
    └────────┬──────────┘
             ▼
        Scorecard 自动评分
        (≥70 通过 / 50-70 升级 / <50 打回)
             │
             ▼
   三道闸门: dev → test → PM
             │
             ▼
       PR + 通知 + 云效触发
```

### 两种执行模式

| 模式 | 执行层 | 通信 | 适用 |
|------|--------|------|------|
| L0 本地 | 本机 `claude -p` | 文件系统 | 快速开发 |
| L1 容器 | K3s Pod（Manager→Worker） | Redis 引用传递 | 并发 + 集群 |

## 三、功能清单（27/31 完成）

### 核心回路（6/6 ✅）
- 意图识别 + 分类创建（intake）
- CLI agent 黑盒执行（worker）
- stream-json 实时观测
- Scorecard 自动评分
- 三道闸门流转（dev→test→PM）
- Git push + PR 创建（integrate）

### 智能体编排（6/7，缺 1）
- ✅ 三 CLI Agent 镜像（Claude Code / Codex / OpenCode）
- ✅ 编排偏好路由表（task_type→provider/model）
- ✅ 对比择优引擎（compare_outputs.py）
- ✅ 多步拆解 DAG（task_runner + 拓扑排序）
- ✅ OpenSpec 融合（spec.tasks + delta_verify）
- ✅ 逃生舱协议
- ⏳ 多 CLI 择优真刀打通（API 恢复即测）

### 容器化部署（3/3 ✅）
- ✅ Worker 镜像（Dockerfile 三 CLI）
- ✅ Manager/Node/Worker 三层架构
- ✅ K3s 热池 + Reconciler + Reset

### 观测与运维（4/4 ✅）
- ✅ Web 仪表盘（Apple 风格，端口 28100）
- ✅ 实时流观测（stream_worker + SSE）
- ✅ 云效 CI/CD 对接（trigger/pull/writeback）
- ✅ 通知系统（Hermes 消息 + 邮件）

### 工程化（4/4 ✅）
- ✅ npm CLI + config 系统
- ✅ GitHub Actions CI（tag 触发镜像构建）
- ✅ 单元测试（state/build_prompt/intake 13 项）
- ✅ 开源封装（零凭据泄漏）

### 文档（4/4 ✅）
- ✅ README（安装 + 使用 + 架构）
- ✅ API 接口文档（三份契约 Schema）
- ✅ 架构设计文档（含 SVG）
- ✅ 交接文档 + GPT 提示词

## 四、代码统计

| 语言 | 文件数 | 行数 | 主要模块 |
|------|--------|------|---------|
| Python | 13 | ~3,200 | state/intake/build_prompt/scorecard/gates/worker_manager |
| Shell | 8 | ~1,100 | worker-entrypoint/git_prepare/reconciler |
| HTML | 1 | ~400 | dashboard（Apple Design） |
| YAML | 6 | ~250 | k8s manifests / config |
| JSON | 3 | ~120 | 契约 Schema / 编排偏好表 |
| Markdown | 15 | ~3,500 | 设计文档 / 交接文档 |

## 五、关键技术决策

| 决策 | 原因 |
|------|------|
| `--bare` 模式必用 | 智谱 API 下非 bare 的 MCP 初始化永久阻塞 |
| 300 turns / $15 预算 | turns 给够干活，预算兜底防烧钱 |
| 编排偏好路由表 | 像 Paseo——task_type 自动选 provider，用户可覆盖 |
| Scorecard 替代人工闸门 | 像 HomeRail——6 维度自动打分，≥70 自动通过 |
| Manager/Node/Worker 三层 | 像 HomeRail——临时 Pod 替代持久热池，隔离性更好 |
| Redis 引用传递 | Pod 间只传 task_id，spec 在 Redis |
| Docker 非 root 用户 | Claude Code 禁止 root 下 --dangerously-skip-permissions |
| MIT 许可证 | Paseo 是 AGPL-3.0（商业化受限），HomeRail 是 MIT |

## 六、与对标项目对比

| 维度 | 零脉（PactFlow） | Paseo | HomeRail |
|------|-----------------|-------|----------|
| Stars | — | 11.2k | 659 |
| 编排 | 路由表 + 多步 DAG | 4 模式（Handoff/Loop/Committee/Advisor） | DAG 引擎 + 节点 |
| 质量 | Scorecard 自动评分 + 三道闸门 | Verifier 循环 | Scorecard 打分制 |
| 执行面 | L0 本地 + K3s Pod（Manager→Worker） | 本地 daemon + Worker 子进程 | Docker Worker 容器 |
| 协议 | 无（直接调 CLI） | ACP + MCP | 自研 DAG 合约 |
| 容器化 | ✅ Pod + Manager 调度 | ❌ | ✅ Docker Worker |
| 契约体系 | ✅ 三份 JSON Schema | ❌ | ❌ |
| 人工把关 | ✅ 三级流转 | ❌ | ❌ |
| 许可证 | MIT | AGPL-3.0 ⚠️ | MIT |

## 七、已知问题

| 问题 | 影响 | 状态 |
|------|------|------|
| 智谱 API 间歇 529 过载 | 高峰期不可用 | 待切 DeepSeek |
| Codex 容器沙箱不兼容 | Pod 中不可用 | 等待更新 |
| 非 bare 模式 MCP 阻塞 | 只能 `--bare` | 智谱 API 限制 |
| K3s kubectl 需 NO_PROXY="*" | 操作不便 | 代理配置问题 |
| GitHub 被 GFW 墙 | gh CLI 不可用 | 走 SSH 隧道 |

## 八、下一步计划

1. **P0②**（立即）：多 CLI 择优打通——API 恢复后用 Claude Code + OpenCode 跑一次完整对比
2. **v0.6 发布**：打 tag 触发 GitHub Actions 镜像构建，邀请外部试用
3. **外部评审**：接入 DeepSeek 后找第三方法审查代码质量
