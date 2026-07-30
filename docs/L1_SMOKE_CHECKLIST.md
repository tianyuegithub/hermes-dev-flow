# L1 端到端冒烟检查清单

> **目的**: 验证 2026-07-30 重构后的 L1 链路（Manager → 临时 Pod → 真实 agent → 契约闸门）在真实 K3s 上端到端工作。
> **背景**: 重构修复了 oneshot stub（原不执行 agent）、热池废止、队列统一。这是该链路的首次真实运行。
> **预计耗时**: 30–60 分钟 · **前置**: Mac 可操作 K3s（`NO_PROXY="*"` kubectl）、Redis 可达

每个步骤给出**预期结果**。任何一步不符 → 停止，按文末"故障定位"排查，不要带病继续。

---

## 阶段 0 · 环境准备（5 分钟）

- [ ] **0.1** `python3 -m unittest discover -s tests` → **48/48 OK**
- [ ] **0.2** `NO_PROXY="*" kubectl get nodes` → 节点 Ready
- [ ] **0.3** `redis-cli -h $REDIS_HOST -p $REDIS_PORT PING` → PONG
- [ ] **0.4** 确认 Secret 存在且 key 完整：
  ```bash
  NO_PROXY="*" kubectl -n dev-flow get secret dev-flow-secrets \
    -o jsonpath='{.data}' | python3 -c "import json,sys; d=json.load(sys.stdin); print(sorted(d.keys()))"
  ```
  预期至少含 `ANTHROPIC_AUTH_TOKEN`、`id_rsa`（deploy key）
- [ ] **0.5** ⚠️ **安全检查**: 确认挂载的 SSH key 是**仅仓库范围的 deploy key**，不是你的个人私钥。worker_manager 现在以只读挂载它，但 Pod 内跑的是自主 agent——key 的权限边界就是你给模型的推送权限边界

## 阶段 1 · 构建并推送 Worker 镜像（10 分钟）

- [ ] **1.1** 构建（注意：构建上下文必须是**仓库根目录**，重构后 Dockerfile 引用 `scripts/`）：
  ```bash
  docker build -f docker/Dockerfile.worker -t <registry>/dev-flow/worker:v0.6.0-smoke .
  ```
  预期：成功；`COPY scripts/task_runner.py` 步骤存在（单一来源）
- [ ] **1.2** 验证镜像内容：
  ```bash
  docker run --rm <registry>/dev-flow/worker:v0.6.0-smoke ls /usr/local/bin/
  ```
  预期含 `worker-entrypoint.sh`、`dev-flow-spec`、`task_runner.py`；**不含 `reset.sh`**（已废止）
- [ ] **1.3** `docker push <registry>/dev-flow/worker:v0.6.0-smoke`

## 阶段 2 · 部署 Manager（5 分钟）

- [ ] **2.1** 检查 `k8s/manager-deployment.yaml` 的 env 与重构后默认值一致：
  `WORKER_IMAGE`（指向 1.3 的镜像）、`REDIS_HOST/PORT`、`ANTHROPIC_BASE_URL`、`QUEUE_KEY=dev-flow:queue`
- [ ] **2.2** `NO_PROXY="*" kubectl -n dev-flow apply -f k8s/manager-deployment.yaml`
- [ ] **2.3** 日志出现启动行：
  ```bash
  NO_PROXY="*" kubectl -n dev-flow logs deploy/dev-flow-manager --tail=5
  ```
  预期：`[manager] 启动，监听 dev-flow:queue (image=...)`
  ⚠️ 若镜像是旧的：确认 manager-deployment 没有残留热池时代的配置

## 阶段 3 · L0 快速回归（10 分钟，先验证闸门逻辑本身）

> L1 之前先在本地把契约闸门回路跑一遍，隔离问题域。

- [ ] **3.1** 创建冒烟任务：
  ```bash
  export DEV_FLOW_HOME=$(pwd)
  TASK_ID="task-smoke-$(date +%H%M%S)"
  python3 scripts/state.py init "$TASK_ID" feature "<你的仓库 URL>"
  python3 scripts/state.py trans "$TASK_ID" GATE_PENDING
  python3 scripts/state.py trans "$TASK_ID" EXECUTING
  python3 scripts/state.py trans "$TASK_ID" VERIFY_GATE
  ```
- [ ] **3.2** 伪造一份**违反契约**的 output（缺 task_id）→ `gates.py decide` → 预期 `rejected`，理由是契约违反
- [ ] **3.3** 伪造**契约合规但 test_result=skipped** 的 output → `decide` → 预期 `escalated`，`human dev/test/pm approve` 三连 → `approved`
- [ ] **3.4** `python3 scripts/integrate_hooks.py pr_created "$TASK_ID" "http://test/pr/1"` → 预期**放行**（闸门批准）
- [ ] **3.5** 清理：`rm -rf .hermes/tasks/$TASK_ID`

## 阶段 4 · L1 端到端（20 分钟，核心验证）

- [ ] **4.1** 写入 spec 并入队：
  ```bash
  TASK_ID="task-l1smoke-$(date +%H%M%S)"
  redis-cli -h $REDIS_HOST -p $REDIS_PORT SET "spec:$TASK_ID" '{
    "task_id":"'$TASK_ID'","task_type":"feature",
    "repo_url":"<你的测试仓库>","base_branch":"main",
    "goal":"添加一个 /health 接口，返回 {\"ok\":true}，附带测试",
    "acceptance":["/health 返回 200"],"worker":"claude",
    "constraints":{"forbidden":["禁止改 main 分支"]}
  }'
  redis-cli -h $REDIS_HOST -p $REDIS_PORT RPUSH dev-flow:queue "$TASK_ID"
  ```
- [ ] **4.2** Manager 日志 → 预期依次出现：
  `[manager] 收到任务` → `[manager] Worker Pod: worker-xxx` → **不再有任何热池/reconciler 相关输出**
- [ ] **4.3** Pod 生命周期：
  ```bash
  NO_PROXY="*" kubectl -n dev-flow get pod -l task-id=$TASK_ID -w
  ```
  预期：Pending → Running → **Succeeded**（若 Failed → 看文末故障定位）
- [ ] **4.4** Pod spec 安全基线抽查（重构新增）：
  ```bash
  NO_PROXY="*" kubectl -n dev-flow get pod -l task-id=$TASK_ID \
    -o jsonpath='{.spec.securityContext.runAsNonRoot}{" "}{.spec.activeDeadlineSeconds}'
  ```
  预期：`true 1800`
- [ ] **4.5** 输出契约：
  ```bash
  redis-cli -h $REDIS_HOST -p $REDIS_PORT GET "output:$TASK_ID" | python3 -m json.tool
  ```
  预期：`status=done`、`commits` 非空、`evidence.diff_stat` 非空、`evidence.files_changed` 非空
- [ ] **4.6** 契约校验（L1 产物也必须过闸门 0）：
  ```bash
  redis-cli -h $REDIS_HOST -p $REDIS_PORT GET "output:$TASK_ID" > /tmp/l1-out.json
  python3 scripts/validate_contract.py output /tmp/l1-out.json
  ```
  预期：`"valid": true`
- [ ] **4.7** 远端分支：`git ls-remote <仓库> | grep dev-flow/$TASK_ID` → 分支已 push
- [ ] **4.8** Pod 已自动清理：`get pod -l task-id=$TASK_ID` → NotFound

## 阶段 5 · 故障注入（10 分钟，验证否决项真实生效）

- [ ] **5.1** 故意给一个 `test_result=fail` 的 output 任务走 gates → 预期 `rejected`（外部证据为负一票否决）
- [ ] **5.2** 故意给缺 `task_id` 的 output → 预期 `rejected`（契约违反）
- [ ] **5.3** 两次打回记录都在 `gate_history` 中可查

---

## 故障定位

| 症状 | 最可能原因 | 排查 |
|------|-----------|------|
| Manager 日志无"收到任务" | 队列 key 不一致 | 重构后唯一 key 是 `dev-flow:queue`，检查 RPUSH 目标和 manager env |
| Pod 创建失败，任务直接 failed | kubectl apply 报错（现在会抛出，不再静默） | Manager 日志里的 RuntimeError 即 kubectl stderr |
| Pod ImagePullBackOff | 镜像未推送 / WORKER_IMAGE 指向旧内网 registry | 重构后默认是 ghcr.io，检查 manager env |
| Pod Running 但秒退 Succeeded、无 output | **oneshot stub 旧镜像**——1.1 构建的不是新代码 | 重新构建确认 entrypoint 含"oneshot 唯一模式"注释 |
| output.json valid=false | entrypoint 解析块漏字段 | 对照 contracts/output.schema.json required |
| 任务 Timeout | agent 卡住 / MAX_TURNS 过大 | `kubectl logs` 看 agent 输出；POD_TIMEOUT_SECONDS 可调 |

## 通过后

- [ ] 打 tag `v0.6.0` 触发 GitHub Actions 镜像构建
- [ ] 更新 HANDOFF.md（它仍描述热池时代，需重写或标注 superseded）
- [ ] 录一段端到端 demo（README 用）
