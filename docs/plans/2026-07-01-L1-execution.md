# L1 执行计划 · 2026-07-01

> 设计文档：`docs/plans/2026-07-01-L1-design.md`
> 前提：Redis ✅ 已有、Harbor ✅ 已有、Gitea ✅ 已有、K3s ✅ 4 节点

---

## Phase 1: Redis 打通（Hermes ↔ Redis）

| # | 任务 | 命令 | 验证标准 |
|---|------|------|----------|
| 1.1 | Hermes 写 spec 到 Redis | `redis-cli -h 192.168.31.173 -p 32319 SET spec:test '{"a":1}'` | `GET spec:test` 返回 JSON |
| 1.2 | state.py 加 Redis 后端 | 写 `scripts/redis_helper.sh`（封装常用操作） | `redis_helper.sh set spec:X` / `get spec:X` 可用 |
| 1.3 | intake 写 spec 到 Redis | intake 创建任务后 `redis_helper.sh set spec:$TASK_ID` | Redis 里有 spec，本地也有 input.json（双写） |

## Phase 2: Worker 镜像构建

| # | 任务 | 产出 | 验证标准 |
|---|------|------|----------|
| 2.1 | 写 3 个脚本 | `dev-flow-spec`、`reset.sh`、`worker-entrypoint.sh` | 本地 bash -n 语法检查通过 |
| 2.2 | 写 Dockerfile | `Dockerfile.worker` | docker build 成功 |
| 2.3 | SSH 到 PVE 构建 + push Harbor | `ssh pve-server 'docker build && docker push'` | Harbor 上能 pull 镜像 |

## Phase 3: K8s 部署

| # | 任务 | 产出 | 验证标准 |
|---|------|------|----------|
| 3.1 | 创建 namespace + Secret | `kubectl apply -f k8s/namespace.yaml` | `kubectl get ns dev-flow` |
| 3.2 | 创建 Deployment | `kubectl apply -f k8s/worker-deployment.yaml` | Pod Running，日志看到 "等待任务..." |
| 3.3 | 验证 Pod 内 Redis 连通 | `kubectl exec` ping Redis | PONG |
| 3.4 | 验证 Pod 内 Gitea SSH | `kubectl exec` ssh git@gitea | 认证通过 |
| 3.5 | 验证 Pod 内 Claude Code | `kubectl exec` claude --version | 版本号输出 |

## Phase 4: Hermes 技能改造

| # | 任务 | 改动 | 验证标准 |
|---|------|------|----------|
| 4.1 | dev-flow-worker 加 pod 模式 | Step 4 分 local/pod 两条路径 | intake 输出 mode 字段 |
| 4.2 | dev-flow-worker pod 派任务逻辑 | RPUSH 到 pod queue + 轮询 status | Redis queue 有任务 |
| 4.3 | dev-flow-gate 改读 Redis | output 从 Redis 读 | gate 能拿到 evidence |
| 4.4 | dev-flow-escalation 改 Redis | escalate 从 Redis 读 | 逃生舱数据可达 |

## Phase 5: 端到端验证

| # | 任务 | 验证标准 |
|---|------|----------|
| 5.1 | L1 全回路（pod 模式） | intake → Redis → pod 执行 → output → gate → PR |
| 5.2 | L0 兼容（local 模式仍可用） | 同一任务 local 模式跑通 |
| 5.3 | Reset 验证 | pod 跑完 → reset → 再跑一个任务，无状态泄漏 |
| 5.4 | 心跳验证 | pod 执行中 heartbeat key 有值，完成后过期 |

---

## 依赖关系

```
Phase 1 (Redis) ──────┐
                      ├─→ Phase 3 (K8s) ─→ Phase 4 (技能) ─→ Phase 5 (验证)
Phase 2 (镜像) ───────┘
```

Phase 1 和 Phase 2 可并行。
