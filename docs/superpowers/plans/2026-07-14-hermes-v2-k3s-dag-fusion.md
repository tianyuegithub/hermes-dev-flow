# Hermes Dev-Flow V2 K3s DAG 与高价值规划融合实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 Hermes Dev-Flow 从脚本原型重建为一个由 Hermes 交互决策、K3s Controller 可靠调度、项目亲和 Pod 热池执行、DAG 契约流转，并仅在高价值规划节点启用多 Agent Fusion 的可验证开源产品。

**Architecture:** Hermes 是本地交互主代理，负责需求澄清、融合判断和人工协作；K3s 内单副本 Controller 是唯一持久状态与调度 owner；Claude Code、Codex、OpenCode 通过项目亲和热池 Pod 执行不可变 Node Attempt。用户可见 TaskGraph 编译为不可变 RunPlan，逻辑 Node 经 Attempt、Lease 临时绑定到 Pod Slot；PlanningFusion 只是 `fanout + join + Hermes decision + approval` 的内置复合模式，普通节点默认只运行一个 Agent。

**Tech Stack:** Python 3.11+、Pydantic 2、FastAPI、Uvicorn、SQLite WAL、PyYAML、Kubernetes Python Client、pytest、Git CLI、K3s、OCI 镜像。

## Global Constraints

- 简体中文用户输出；代码标识符、API 路径和公共 JSON 字段使用英文。
- K3s Pod 执行 Claude Code、Codex、OpenCode 是正式需求，不得删除或降级为远期设想。
- 项目与 Pod Slot 是 `1:N`；一个 Slot 只绑定一个项目，同一时刻最多执行一个 Attempt，任务间可复用。
- Pod 是执行载体，不是 DAG 事实模型：`Node -> Attempt -> PodSlot -> Lease`，绑定只在 Attempt 运行期成立。
- 默认运行镜像包含三种 CLI；调度按 `project_id + runtime_profile + capabilities` 匹配，必要时才拆分专用镜像，避免首版形成三个空闲池。
- Worker、Agent stdout、自报 status 和自报测试结果都不是可信完成证据；Controller 只接受带当前 fencing token 的结果，并独立核对 Git 与验证证据。
- Controller 是任务、RunPlan、Node、Attempt、Lease、Gate、Approval、Publication 的唯一写 owner；Hermes、Dashboard 和 Worker 只通过 Controller API 读写。
- 首版使用单 Controller + SQLite WAL + 独占 PVC；不引入 PostgreSQL、Redis 或消息队列双事实源。
- Worker 通过 Controller HTTP 长轮询领取 Lease，Hermes/Dashboard 通过 REST + SSE 观察；Redis 不参与正确性。
- Hermes/Dashboard 使用 Controller bearer token；每个 Pod Slot 使用独立短期身份。Agent 子进程使用独立低权限 UID 和 env allowlist，不能继承 Controller、Slot 或 Git push 凭证。
- Worker PVC 只是项目 clone 与工具缓存；不可变合同、事件、日志索引和关键产物先持久化到 Controller PVC，Git remote 是代码 checkpoint。
- Claude Code 通过智谱 Anthropic-compatible API 时必须使用 `--bare`。
- PlanningFusion 只用于需求澄清、架构设计、关键决策和高价值计划；普通 DAG Node 默认 `planning_mode=single`。
- Fusion 的每个候选收到同一 canonical `PlanningRequest` 和同一 `request_hash`，独立完成整份方案，不能按前端/后端/测试切片。
- Planning Attempt 默认只读仓库、无 push 权限；候选结束时必须证明 HEAD 和 working tree 未变化。
- 3/3 有效候选正常融合；2/3 允许生成显式 `DEGRADED` 融合并要求 dev approval 确认；少于 2 个有效候选进入 `NEEDS_INPUT`。
- Hermes 负责最终融合裁决，不做投票或平均；最终方案必须记录共识、独有亮点、冲突、采纳/拒绝理由及候选来源。
- 等待人工决策时不长期占用 Pod Lease；Worker 先提交 WIP GitRef/ArtifactRef，释放 Slot，恢复时创建新 Attempt。
- 合同 hash、fencing、Git 仓库完整性、权限边界不可 waiver；可豁免 gate 必须保持 `WAIVED` 而不是伪装为 `PASS`，且发布策略显式允许才可继续。
- L0/L1 共用同一领域模型、状态机、Adapter 和 Gate；L0 是本地 ExecutorBackend，不得形成第二套业务逻辑。
- 旧脚本只在迁移期作为兼容入口，不新增能力、不双写；每个入口一次只选择 legacy 或 v2 owner。
- 不使用 mock、`|| true`、吞异常、硬编码展示值或弱化断言制造端到端通过；单元测试可用 fake adapter，集成与验收必须验证真实 SQLite、Git、subprocess 或 K3s 行为。
- 每个交付批次完成受影响回归后做一次代码评审；零 finding 记录 `review-fix=NOT_TRIGGERED（未触发）`。

---

## 1. 已冻结的架构判断

### 1.1 资深架构师评审

结论：**有条件支持**。

- 主张：保留 K3s 项目亲和热池与 DAG，但用 Controller 单写者、不可变合同、Attempt/Lease/Fencing 重建可靠性；Fusion 只进入高价值规划路径。
- 证据：项目明确要求子 Agent 在 K3s Pod 运行，项目与 Pod 为 1:N 且 Pod 要复用；现有 `BLPOP + 多方写 Redis + || true` 无法可靠回答任务归属、重试和迟到结果。
- 推理桥梁：热池解决真实冷启动与项目缓存问题，但热池本身不提供可靠调度；可靠性必须来自持久状态、独占 Lease、执行纪元和控制面采证。
- 例外/反驳：如果未来要求多 Controller active-active、跨集群或每秒高并发写入，SQLite 单写者会成为限制，届时再迁移 PostgreSQL；当前没有这类证据。
- 结论强度：**强**。

### 1.2 明确保留、重写和删除

| 处理 | 内容 | 原因 |
|---|---|---|
| 保留 | Hermes 作为主交互 Agent | 这是产品入口、融合裁决者和人机协作主体 |
| 保留 | K3s、项目 1:N Pod、项目亲和热池 | 解决远程执行、冷启动和项目 clone/cache 复用 |
| 保留 | Claude/Codex/OpenCode 三种 CLI Adapter | 提供模型与工具多样性 |
| 保留 | L0 本地执行 | 用于开发、诊断和无集群场景，但复用同一核心 |
| 保留 | OpenSpec 作为可选输入适配器 | 它可生成规范输入，但不是运行态 SSOT |
| 重写 | 状态机、DAG runner、Worker 主循环、Gate、Dashboard 写路径 | 现有实现存在多写者、吞失败、伪 DAG 和不可信状态 |
| 重写 | Pod 热池 | 从 Deployment + per-Pod BLPOP 改为 Controller 管理的 Project Slot + PVC + Lease |
| 合并 | input/output/escalate 三份散落契约 | 统一为版本化 contract envelope；`NEEDS_INPUT` 是 Outcome，不是独立子系统 |
| 删除 | `state.json + Redis status` 双写 | 无法定义唯一事实源和崩溃恢复顺序 |
| 删除 | Redis per-Pod queue/BLPOP 正确性依赖 | 领取即丢，缺少 ack/lease/fencing；HTTP claim 直接在 SQLite 事务内完成 |
| 删除 | `compare_outputs.py` 的 diff/成本评分择优 | diff 多少不是质量；PlanningFusion 采用证据化裁决 |
| 删除 | Agent 自行决定 done、直接 push/开 PR | 执行器不应成为验证与发布 owner |

### 1.3 PostgreSQL 与 Redis 决策

首版**不使用 PostgreSQL**。Controller 只部署一个副本，SQLite WAL 放在独占 PVC 上，可以用单事务同时完成 Node READY 选择、Attempt 创建、Lease 分配、事件追加，从而避免 outbox 和队列双写。

首版**不使用 Redis 参与正确性**。Worker 直接长轮询 `POST /v1/leases/claim`，Controller 在 SQLite 事务中领取任务并返回不可变合同。SSE 只传观察事件，断线后按 event ID 从 SQLite 重放。

只有命中任一条件才单独立项迁移 PostgreSQL：

1. 需要两个以上 Controller active-active；
2. 单 SQLite 写事务 p95 连续超过 100ms 并成为吞吐瓶颈；
3. 必须跨集群共享同一事实源；
4. PVC/RWO 的恢复目标无法满足业务 RTO/RPO。

Redis 只允许作为无损可丢的通知/cache adapter；任何时候删除 Redis 都不得改变任务最终状态。

---

## 2. 目标模型与契约

### 2.1 两层图

```text
Requirement
  -> Planning Run（single 或 fusion）
  -> FinalPlan@v1
  -> Dev Approval
  -> GraphCompiler
  -> immutable Implementation RunPlan
  -> Attempts on Pod Slots
  -> Verification / Integration / Test Approval / PM Approval
  -> Publish / PR
```

- `TaskGraph`：用户和 Hermes 理解的逻辑工作图，可包含 `PlanningFusion` 复合节点。
- `RunPlan`：Controller 编译出的不可变执行图，展开 fanout、join、decision、approval、verify、integrate 和 publish。
- 数据边携带命名 port 与 schema；控制边只表达顺序，不假装传数据。
- 确定性节点如 join、approval、terminal、publish 不占 Worker Pod。

### 2.2 执行承载

```text
Logical Node
  -> Attempt #1 (contract_hash=A, base_sha=X)
  -> Lease(fencing_token=7)
  -> Project Pod Slot #2
  -> result accepted/rejected

retry
  -> Attempt #2 (new attempt_id, same or revised contract)
  -> Lease(fencing_token=8)
  -> any eligible Slot in same project/profile
```

- 一个 Node 可以有多个历史 Attempt，但同一时刻最多一个 active Attempt。
- 一个 Slot 同一时刻最多一个 active Lease。
- Lease 到期后 Attempt 变为 `LOST`；重试必须创建新 Attempt，旧 token 的迟到结果返回 HTTP 409。
- Pod/Slot 不与 Node 永久绑定；Slot 完成清理后回到同项目热池。

### 2.3 公共合同

所有合同都包含：

```python
class ContractEnvelope(BaseModel):
    schema_name: str
    schema_version: Literal[1]
    contract_id: UUID
    task_id: UUID
    run_id: UUID
    created_at: datetime
    payload_sha256: str
    payload: dict[str, Any]
    provenance: list[ArtifactRef]
```

核心 payload：

- `TaskRequest@v1`：需求、约束、验收、风险、`planning_mode`。
- `PlanningRequest@v1`：冻结 task、repo/base SHA、事实入口、必答章节和预算。
- `Proposal@v1`：假设、证据、完整方案、DAG、替代项、风险、验证和未决事项。
- `FusionSynthesis@v1`：输入候选 hash、证据审计、共识、独有亮点、冲突裁决、拒绝项、最终方案。
- `NodeContract@v1`：输入 ports、agent、runtime profile、workspace policy、预算、expected outputs。
- `NodeResult@v1`：真实 exit、GitRef、ArtifactRef、原始日志、agent advisory report。
- `DecisionRequest@v1`：问题、选项、影响、推荐、一次性 continuation token。
- `GateResult@v1`：`PASS|FAIL|WAIVED|SKIPPED`、采证者、证据和 policy decision。

ArtifactRef 必须是不可变引用：

```python
class ArtifactRef(BaseModel):
    artifact_id: UUID
    media_type: str
    sha256: str
    size_bytes: int
    storage_key: str
```

### 2.4 PlanningFusion 编译规则

```text
PlanningFusion(task)
  -> planning.claude   [Pod, read-only]
  -> planning.codex    [Pod, read-only]
  -> planning.opencode [Pod, read-only]
  -> planning.collect  [Controller]
  -> planning.fuse     [Hermes decision]
  -> planning.approve  [dev approval]
```

- 三个 proposer 的 canonical payload 字节相同；provider wrapper 只能描述 CLI transport 和输出 schema。
- `collect` 校验候选 schema、request hash、证据引用和 repo 未变证明。
- `fuse` 由 Hermes 提交 `FusionSynthesis`；Controller 校验所有 source candidate ID/hash 存在。
- 2/3 时 synthesis 状态固定为 `DEGRADED`，approval UI 必须显示缺失候选；1/3 不创建假融合。
- 规划审批通过后才编译 Implementation RunPlan；候选 Pod 不保留到实现阶段。

---

## 3. 目标文件结构

```text
pyproject.toml
src/hermes_dev_flow/
  __init__.py
  cli.py
  config.py
  domain/
    models.py
    enums.py
    hashing.py
    state_machine.py
  controller/
    app.py
    api.py
    auth.py
    service.py
    store.py
    migrations/001_initial.sql
    artifacts.py
    events.py
    scheduler.py
    graph_compiler.py
  executors/
    base.py
    local.py
    k3s.py
  agents/
    base.py
    command.py
    claude.py
    codex.py
    opencode.py
  worker/
    main.py
    auth.py
    client.py
    supervisor.py
    workspace.py
    evidence.py
  fusion/
    contracts.py
    compiler.py
    validator.py
  gates/
    evaluator.py
    git_integrity.py
    verification.py
    approval.py
  integrations/
    git_publish.py
    forge.py
    openspec.py
  hermes/
    client.py
k8s/
  controller.yaml
  worker-rbac.yaml
  worker-secrets.example.yaml
  network-policy.yaml
  templates/worker-pod.yaml
  templates/worker-pvc.yaml
docker/
  Dockerfile.controller
  Dockerfile.worker
skills/hermes-dev-flow/SKILL.md
tests/
  unit/
  integration/
  k3s/
```

迁移期保留现有 `scripts/`、`contracts/`、`bin/` 和旧 skills，但不再加功能。v2 通过真实验收并切换入口后，在最后一个批次删除，不创建 `legacy/` 第二事实源。

---

## 4. 实施任务

### Task 1: 建立 Python 产品壳与领域模型

**Files:**
- Create: `pyproject.toml`
- Create: `src/hermes_dev_flow/__init__.py`
- Create: `src/hermes_dev_flow/cli.py`
- Create: `src/hermes_dev_flow/domain/enums.py`
- Create: `src/hermes_dev_flow/domain/models.py`
- Create: `src/hermes_dev_flow/domain/hashing.py`
- Create: `tests/unit/test_models.py`
- Create: `tests/unit/test_hashing.py`

**Interfaces:**
- Produces: `TaskRequest`, `PlanningRequest`, `Proposal`, `FusionSynthesis`, `NodeContract`, `NodeResult`, `ArtifactRef`, `DecisionRequest`, `GateResult`.
- Produces: `canonical_json(model) -> bytes` and `sha256_model(model) -> str`.

- [ ] **Step 1: 写失败测试，固定 canonical hash 和关键枚举**

```python
def test_contract_hash_ignores_input_key_order():
    left = canonical_payload({"goal": "x", "constraints": {"b": 2, "a": 1}})
    right = canonical_payload({"constraints": {"a": 1, "b": 2}, "goal": "x"})
    assert sha256_bytes(left) == sha256_bytes(right)

def test_gate_never_conflates_waived_with_passed():
    assert GateStatus.WAIVED != GateStatus.PASS
```

- [ ] **Step 2: 运行并确认因包不存在失败**

Run: `python3 -m pytest tests/unit/test_models.py tests/unit/test_hashing.py -q`

Expected: FAIL with `ModuleNotFoundError: No module named 'hermes_dev_flow'`.

- [ ] **Step 3: 实现 Pydantic 判别联合和 RFC 8785 风格稳定 JSON**

`TaskRequest.planning_mode` 只允许 `single|fusion`，默认 `single`；`NodeResult.outcome` 只允许 `succeeded|failed|needs_input`。`FusionSynthesis` 强制至少两个 source proposal，且每个 adopted/rejected decision 引用 source IDs。

- [ ] **Step 4: 安装并运行测试**

Run: `python3 -m pip install -e '.[dev]' && python3 -m pytest tests/unit/test_models.py tests/unit/test_hashing.py -q`

Expected: PASS.

- [ ] **Step 5: 提交**

```bash
git add pyproject.toml src/hermes_dev_flow tests/unit/test_models.py tests/unit/test_hashing.py
git commit -m "重构：建立 V2 领域合同与稳定哈希"
```

### Task 2: 建立 SQLite 单一事实源、事件日志和制品库

**Files:**
- Create: `src/hermes_dev_flow/controller/migrations/001_initial.sql`
- Create: `src/hermes_dev_flow/controller/store.py`
- Create: `src/hermes_dev_flow/controller/artifacts.py`
- Create: `src/hermes_dev_flow/controller/events.py`
- Create: `tests/integration/test_store.py`
- Create: `tests/integration/test_artifacts.py`

**Interfaces:**
- Produces: `SqliteStore.transaction()`, `append_event()`, `create_attempt_and_lease()` and `ArtifactStore.put()/open()`.
- Tables: `projects`, `tasks`, `run_plans`, `nodes`, `attempts`, `pod_slots`, `leases`, `contracts`, `artifacts`, `events`, `decisions`, `gates`, `approvals`, `publications`.

- [ ] **Step 1: 写事务与唯一 Lease 失败测试**

```python
def test_slot_cannot_have_two_active_leases(store, ready_node, slot):
    store.create_attempt_and_lease(ready_node, slot, ttl_seconds=60)
    with pytest.raises(LeaseConflict):
        store.create_attempt_and_lease(ready_node, slot, ttl_seconds=60)

def test_event_and_state_commit_atomically(store, task):
    with pytest.raises(RuntimeError):
        with store.transaction() as tx:
            tx.update_task(task.id, phase="RUNNING")
            tx.append_event(task.id, "task.started", {})
            raise RuntimeError("rollback")
    assert store.get_task(task.id).phase == "DRAFT"
    assert store.list_events(task.id) == []
```

- [ ] **Step 2: 建立 WAL、外键和部分唯一索引**

迁移必须执行 `PRAGMA journal_mode=WAL`、`foreign_keys=ON`、`busy_timeout=5000`，并用部分唯一索引保证一个 Node/Slot 最多一个 `ACTIVE` Lease。`events.id` 单调递增，供 SSE `Last-Event-ID` 重放。

- [ ] **Step 3: 实现 content-addressed ArtifactStore**

文件先写同目录临时文件、`fsync`、校验 SHA-256 后 `os.replace` 到 `<artifact_root>/<sha256[:2]>/<sha256>`；重复上传同内容幂等，DB 只保存元数据和 storage key。

- [ ] **Step 4: 验证重启恢复**

Run: `python3 -m pytest tests/integration/test_store.py tests/integration/test_artifacts.py -q`

Expected: PASS；关闭并重开 Store 后 task/event/artifact 仍存在。

- [ ] **Step 5: 提交**

```bash
git add src/hermes_dev_flow/controller tests/integration/test_store.py tests/integration/test_artifacts.py
git commit -m "重构：建立 SQLite 单一事实源与不可变制品库"
```

### Task 3: 实现状态机、TaskGraph 编译器和依赖调度

**Files:**
- Create: `src/hermes_dev_flow/domain/state_machine.py`
- Create: `src/hermes_dev_flow/controller/graph_compiler.py`
- Create: `src/hermes_dev_flow/controller/scheduler.py`
- Create: `tests/unit/test_state_machine.py`
- Create: `tests/unit/test_graph_compiler.py`
- Create: `tests/integration/test_scheduler.py`

**Interfaces:**
- Produces: `GraphCompiler.compile(task_graph) -> RunPlan`.
- Produces: `Scheduler.mark_ready(run_id)` and `Scheduler.claim(slot, now) -> LeaseGrant | None`.

- [ ] **Step 1: 写循环、缺失 port 和 retry 纪元测试**

```python
def test_compile_rejects_cycle(compiler, cyclic_graph):
    with pytest.raises(GraphValidationError, match="cycle"):
        compiler.compile(cyclic_graph)

def test_retry_creates_new_attempt_and_fence(scheduler, failed_attempt):
    retry = scheduler.retry(failed_attempt.node_id)
    assert retry.id != failed_attempt.id
    assert retry.epoch == failed_attempt.epoch + 1
```

- [ ] **Step 2: 定义节点和边**

首版 node type 固定为 `agent|verify|join|decision|approval|integrate|publish|terminal`；data edge 必须指定 `source_port`、`target_port` 和 `schema_name`，control edge 不允许携带 artifact。

- [ ] **Step 3: 实现 READY 推导和失败传播**

Node 只有在全部 required predecessors `SUCCEEDED` 且输入 port 合同完整时变为 `READY`。依赖失败默认将下游标记 `BLOCKED`；只有显式 `failure_policy=continue` 才可继续。

- [ ] **Step 4: 验证 sibling 并行与确定性节点不占 Pod**

Run: `python3 -m pytest tests/unit/test_state_machine.py tests/unit/test_graph_compiler.py tests/integration/test_scheduler.py -q`

Expected: PASS；两个无依赖 agent node 同时 READY，join 等待两者，approval/terminal 从不产生 Lease。

- [ ] **Step 5: 提交**

```bash
git add src/hermes_dev_flow/domain/state_machine.py src/hermes_dev_flow/controller/graph_compiler.py src/hermes_dev_flow/controller/scheduler.py tests/unit/test_state_machine.py tests/unit/test_graph_compiler.py tests/integration/test_scheduler.py
git commit -m "功能：实现不可变 RunPlan 与依赖调度"
```

### Task 4: 建立 Controller REST API、SSE 和幂等命令

**Files:**
- Create: `src/hermes_dev_flow/controller/app.py`
- Create: `src/hermes_dev_flow/controller/api.py`
- Create: `src/hermes_dev_flow/controller/auth.py`
- Create: `src/hermes_dev_flow/controller/service.py`
- Create: `tests/integration/test_controller_api.py`
- Modify: `src/hermes_dev_flow/cli.py`

**Interfaces:**
- Produces: `/v1/projects`, `/v1/tasks`, `/v1/runs`, `/v1/leases/*`, `/v1/decisions/*`, `/v1/approvals/*`, `/v1/publications/*`.
- Produces: `GET /v1/runs/{run_id}/events` as SSE with `Last-Event-ID`.
- Produces: `HermesBearerAuth` and `SlotRequestAuth`；worker 签名覆盖 timestamp、nonce、method、path 和 body SHA-256。

- [ ] **Step 1: 写 idempotency 和 SSE 重放测试**

```python
def test_duplicate_create_task_returns_same_task(client, request):
    a = client.post("/v1/tasks", json=request, headers={"Idempotency-Key": "k1"})
    b = client.post("/v1/tasks", json=request, headers={"Idempotency-Key": "k1"})
    assert a.json()["task_id"] == b.json()["task_id"]

def test_sse_replays_after_last_event_id(client, run):
    events = read_sse(client, run.id, last_event_id=2)
    assert all(event.id > 2 for event in events)

def test_worker_signature_cannot_be_replayed(client, signed_claim):
    assert client.post("/v1/leases/claim", **signed_claim).status_code == 200
    assert client.post("/v1/leases/claim", **signed_claim).status_code == 409
```

- [ ] **Step 2: 实现薄 API 与 Service 单写路径**

API 只做鉴权、schema 校验、idempotency key 和错误映射；所有状态转换进入 `ControllerService`，禁止 endpoint 直接执行 SQL。

- [ ] **Step 3: 固定错误语义**

无效 schema 返回 422；非法状态 409；stale fencing token 409；未知对象 404；内部错误 500 并写事件，但不能把任务改成成功。

Hermes/Dashboard 命令必须带 bearer token；Worker 请求使用 Slot HMAC，nonce 只能消费一次，时间窗口默认 60 秒。Controller 根据数据库 Slot 记录和 K8s Pod UID 核对 project；任何跨 Slot/跨项目身份返回 403。首版明确是单租户可信集群，不宣称抵御拥有节点 root 权限的攻击者。

- [ ] **Step 4: 运行 API 回归**

Run: `python3 -m pytest tests/integration/test_controller_api.py -q`

Expected: PASS；SSE 断线重连不丢历史事件。

- [ ] **Step 5: 提交**

```bash
git add src/hermes_dev_flow/controller src/hermes_dev_flow/cli.py tests/integration/test_controller_api.py
git commit -m "功能：建立 Controller API 与可重放事件流"
```

### Task 5: 统一三种 Agent Adapter 与 L0 Executor

**Files:**
- Create: `src/hermes_dev_flow/agents/base.py`
- Create: `src/hermes_dev_flow/agents/command.py`
- Create: `src/hermes_dev_flow/agents/claude.py`
- Create: `src/hermes_dev_flow/agents/codex.py`
- Create: `src/hermes_dev_flow/agents/opencode.py`
- Create: `src/hermes_dev_flow/executors/base.py`
- Create: `src/hermes_dev_flow/executors/local.py`
- Create: `tests/unit/test_agents.py`
- Create: `tests/integration/test_local_executor.py`

**Interfaces:**
- Produces: `AgentAdapter.build_command(contract, prompt_path) -> CommandSpec`.
- Produces: `ExecutorBackend.execute(attempt, workspace) -> RawExecution`.

- [ ] **Step 1: 写真实退出语义和脱敏测试**

```python
def test_nonzero_exit_never_becomes_success(fake_agent, contract):
    result = fake_agent(exit_code=17, stdout='{"status":"done"}').run(contract)
    assert result.exit_code == 17
    assert result.outcome == "failed"

def test_claude_zhipu_always_uses_bare(claude_adapter, zhipu_profile):
    assert "--bare" in claude_adapter.build_command(zhipu_profile).argv
```

- [ ] **Step 2: 实现共同 CommandRunner**

prompt 通过 stdin 或权限受控文件传递；凭证来自 provider/环境且从 agent 子进程 env allowlist 注入；日志只记录脱敏 argv。timeout、signal、invalid output 都返回红色 RawExecution。

- [ ] **Step 3: 实现三个薄适配器**

Adapter 只负责 CLI 参数和 provider wrapper，不负责状态转换、Git commit、验证或 publish。普通 Node 由合同指定一个 adapter，不自动三跑。

- [ ] **Step 4: 用真实 subprocess 验证 L0**

Run: `python3 -m pytest tests/unit/test_agents.py tests/integration/test_local_executor.py -q`

Expected: PASS；L0 和后续 K3s backend 产生同一种 `RawExecution`。

- [ ] **Step 5: 提交**

```bash
git add src/hermes_dev_flow/agents src/hermes_dev_flow/executors tests/unit/test_agents.py tests/integration/test_local_executor.py
git commit -m "功能：统一三种 Agent 与 L0 执行后端"
```

### Task 6: 实现 Worker Lease 客户端、监督器与项目工作区

**Files:**
- Create: `src/hermes_dev_flow/worker/main.py`
- Create: `src/hermes_dev_flow/worker/auth.py`
- Create: `src/hermes_dev_flow/worker/client.py`
- Create: `src/hermes_dev_flow/worker/supervisor.py`
- Create: `src/hermes_dev_flow/worker/workspace.py`
- Create: `src/hermes_dev_flow/worker/evidence.py`
- Create: `tests/integration/test_worker_protocol.py`
- Create: `tests/integration/test_workspace.py`

**Interfaces:**
- Consumes: `LeaseGrant(attempt_id, contract_id, contract_hash, fencing_token, expires_at)`.
- Produces: heartbeat, raw execution artifact, GitRef and completion request carrying the same fencing token.

- [ ] **Step 1: 写 stale token、超时和仓库身份测试**

```python
def test_late_result_is_rejected(controller, expired_lease):
    response = controller.complete(expired_lease, fencing_token=expired_lease.token)
    assert response.status_code == 409

def test_workspace_rejects_wrong_origin(workspace, project):
    workspace.set_origin("ssh://wrong/repo.git")
    with pytest.raises(WorkspaceIdentityError):
        workspace.prepare(project)
```

- [ ] **Step 2: 实现 claim/heartbeat/complete 协议**

Worker 每次只持有一个 Lease；heartbeat 默认 15 秒，TTL 60 秒。网络中断时不领取新任务；恢复后若 token 已失效，停止提交结果并清理本地 Attempt。

Supervisor 从权限为 `0400` 的 Slot Secret 读取短期身份并签名请求；启动 Agent 前使用 env allowlist 清除 Slot token、Controller token 和 Git push 凭证，以专用非 root UID 运行 CLI。原始凭证不得进入 argv、日志、artifact 或错误响应。

- [ ] **Step 3: 实现项目亲和 workspace reset**

每次任务前验证 origin、fetch、checkout frozen base SHA、创建 `hermes/<task_id>/<node_id>/<attempt_epoch>` 分支并保证 clean。每次任务后先持久化证据，再 reset；reset 失败将 Slot 标记 `DIRTY`，不得重新领取。

- [ ] **Step 4: 实现 NEEDS_INPUT 释放策略**

Worker 创建 WIP commit 或 artifact，提交 `DecisionRequest`，结束当前 Attempt 并释放 Lease；回答后 Controller 创建新 Attempt，不依赖原进程或原 Pod 会话继续存在。

- [ ] **Step 5: 验证并提交**

Run: `python3 -m pytest tests/integration/test_worker_protocol.py tests/integration/test_workspace.py -q`

Expected: PASS；Controller 重启、Worker 重试和迟到结果都不会重复成功。

```bash
git add src/hermes_dev_flow/worker tests/integration/test_worker_protocol.py tests/integration/test_workspace.py
git commit -m "功能：实现 Worker Lease 协议与项目工作区复用"
```

### Task 7: 实现 K3s 项目亲和 Pod 热池

**Files:**
- Create: `src/hermes_dev_flow/executors/k3s.py`
- Create: `k8s/controller.yaml`
- Create: `k8s/worker-rbac.yaml`
- Create: `k8s/worker-secrets.example.yaml`
- Create: `k8s/network-policy.yaml`
- Create: `k8s/templates/worker-pod.yaml`
- Create: `k8s/templates/worker-pvc.yaml`
- Rewrite: `docker/Dockerfile.worker`
- Create: `docker/Dockerfile.controller`
- Create: `tests/unit/test_pool_manager.py`
- Create: `tests/k3s/test_hot_pool.py`

**Interfaces:**
- Produces: `PoolManager.reconcile(project_id)` and stable `PodSlot` records.
- Slot eligibility: exact `project_id`, compatible `runtime_profile`, required agent capability, `state=IDLE`, no active Lease.

- [ ] **Step 1: 写 pool 隔离与缩容安全测试**

```python
def test_never_assigns_cross_project_slot(pool, node_a, slot_b):
    assert pool.is_eligible(node_a, slot_b) is False

def test_busy_or_dirty_slot_is_never_scaled_down(pool, busy_slot, dirty_slot):
    victims = pool.choose_scale_down([busy_slot, dirty_slot])
    assert victims == []
```

- [ ] **Step 2: 实现 Controller 管理的 Pod+PVC Slot**

每个 Slot 有稳定 ID、独立 PVC 和 Pod，标签至少包含 `project-id`、`slot-id`、`runtime-profile`。Controller 创建/重建单独 Pod，不依赖 Deployment 随机身份；PVC 默认保留，Pod 可重建。

PoolManager 为每个 Slot 创建独立 Secret，只挂载到 supervisor 可读路径；Agent CLI 进程不继承该凭证。项目 Git fetch/push credential 也只由 supervisor Git 操作使用，Planning Node 永远没有 push 动作。

- [ ] **Step 3: 实现 min/max 热池策略**

项目配置 `min_hot=1`、`max_hot>=min_hot`。READY 等待超过 `scale_up_after_seconds` 且未达 max 时增加 Slot；只删除连续空闲超过 `scale_down_after_seconds`、无 Lease、clean 且非最后 `min_hot` 的 Slot。

- [ ] **Step 4: 实现真实 K3s 验收**

Run: `NO_PROXY="*" python3 -m pytest -m k3s tests/k3s/test_hot_pool.py -q`

Expected: 创建一个测试项目的两个 Slot；并发领取不同 Slot；Pod 重建后复用原 PVC；跨项目 claim 被拒；busy Slot 不被缩容；测试结束只删除带测试 run label 的资源。

- [ ] **Step 5: 提交**

```bash
git add src/hermes_dev_flow/executors/k3s.py k8s docker tests/unit/test_pool_manager.py tests/k3s/test_hot_pool.py
git commit -m "功能：建立项目亲和 K3s Pod 热池"
```

### Task 8: 重建可信 Gate、Git 集成和发布边界

**Files:**
- Create: `src/hermes_dev_flow/gates/evaluator.py`
- Create: `src/hermes_dev_flow/gates/git_integrity.py`
- Create: `src/hermes_dev_flow/gates/verification.py`
- Create: `src/hermes_dev_flow/gates/approval.py`
- Create: `src/hermes_dev_flow/integrations/git_publish.py`
- Create: `src/hermes_dev_flow/integrations/forge.py`
- Create: `tests/integration/test_gates.py`
- Create: `tests/integration/test_publish.py`

**Interfaces:**
- Produces: deterministic GateResult and `Publisher.publish(task_id) -> Publication`.
- Gate classes: contract integrity、execution、repository integrity、verification、approval policy、publication precondition.

- [ ] **Step 1: 写防假绿测试**

```python
def test_agent_claimed_done_cannot_override_failed_process(gates, execution):
    execution.exit_code = 9
    execution.agent_report = {"status": "done"}
    assert gates.execution(execution).status == GateStatus.FAIL

def test_non_waivable_gate_rejects_waiver(gates, bad_contract):
    with pytest.raises(WaiverForbidden):
        gates.waive(bad_contract, reason="ship it")
```

- [ ] **Step 2: 用结构化 Gate 替代“六步仪式”**

保留六类风险语义，但 Gate 由代码执行并保存证据，不要求每个任务机械打印六段文本。无关 gate 为 `SKIPPED` 且有 policy reason，不等于通过。

- [ ] **Step 3: 收紧 Git 权限**

Agent 只改工作区；Worker supervisor 负责生成确定性 commit。Worker 只允许 push task branch，不能写 main 或创建 PR；Controller 在所有 required Gate 和 approval 满足后调用 Forge adapter 创建 PR。

- [ ] **Step 4: 真实 bare remote 验证**

Run: `python3 -m pytest tests/integration/test_gates.py tests/integration/test_publish.py -q`

Expected: 非零 exit、无 commit、stale base、测试失败、错误 fencing、main push 都保持红色；重复 publish 幂等。

- [ ] **Step 5: 提交**

```bash
git add src/hermes_dev_flow/gates src/hermes_dev_flow/integrations tests/integration/test_gates.py tests/integration/test_publish.py
git commit -m "重构：建立可信 Gate 与发布边界"
```

### Task 9: 实现多节点 DAG、Integrator 与失败恢复

**Files:**
- Modify: `src/hermes_dev_flow/controller/scheduler.py`
- Modify: `src/hermes_dev_flow/controller/graph_compiler.py`
- Create: `src/hermes_dev_flow/controller/integrator.py`
- Create: `tests/integration/test_dag_execution.py`
- Create: `tests/k3s/test_dag_recovery.py`

**Interfaces:**
- Produces: sibling parallel dispatch, retry policy, join, project-scoped Integrator Slot and deterministic run branch.

- [ ] **Step 1: 写并发、阻断和集成冲突测试**

```python
def test_failed_parent_blocks_required_child(run):
    run.fail("backend")
    assert run.node("frontend").status == NodeStatus.BLOCKED

def test_retry_never_overwrites_previous_attempt(run):
    first = run.fail("backend")
    second = run.retry("backend")
    assert first.id != second.id
    assert first.status == AttemptStatus.FAILED
```

- [ ] **Step 2: 实现 Integrator 角色**

每个项目同一时刻最多一个 active integration Lease。Integrator 按 RunPlan 固定顺序 cherry-pick Node commits 到 `hermes/run/<run_id>`，冲突进入 `NEEDS_INPUT`，不得自动丢弃任一候选变更。

- [ ] **Step 3: 实现恢复扫描**

Controller 启动时扫描 expired Lease、RUNNING Attempt 和 READY Node：expired Attempt 变 `LOST`，按 retry policy 创建新 Attempt；已持久化 SUCCEEDED Node 不重复执行。

- [ ] **Step 4: K3s 故障验收**

Run: `NO_PROXY="*" python3 -m pytest -m k3s tests/k3s/test_dag_recovery.py -q`

Expected: sibling 使用不同 Slot；杀死一个 Worker 后只重试对应 Node；Controller 重启后 Run 继续；旧 Worker 迟到提交被拒；最终只产生一个 run branch。

- [ ] **Step 5: 提交**

```bash
git add src/hermes_dev_flow/controller tests/integration/test_dag_execution.py tests/k3s/test_dag_recovery.py
git commit -m "功能：完成 DAG 并发、集成与故障恢复"
```

### Task 10: 实现高价值 PlanningFusion

**Files:**
- Create: `src/hermes_dev_flow/fusion/contracts.py`
- Create: `src/hermes_dev_flow/fusion/compiler.py`
- Create: `src/hermes_dev_flow/fusion/validator.py`
- Create: `src/hermes_dev_flow/hermes/client.py`
- Create: `tests/unit/test_fusion_compiler.py`
- Create: `tests/integration/test_planning_fusion.py`

**Interfaces:**
- Produces: `FusionCompiler.expand(request) -> PlanningRunPlan`.
- Produces: `FusionValidator.validate_proposal()` and `validate_synthesis()`.
- Hermes API: `submit_fusion_synthesis(task_id, synthesis)`.

- [ ] **Step 1: 写同题、隔离与退化测试**

```python
def test_all_proposers_receive_same_request_hash(plan):
    hashes = {node.contract.payload.request_hash for node in plan.proposers}
    assert len(hashes) == 1

@pytest.mark.parametrize("valid,expected", [(3, "READY_TO_FUSE"), (2, "DEGRADED"), (1, "NEEDS_INPUT")])
def test_quorum(valid, expected, fusion_run):
    assert fusion_run.finish_candidates(valid).status == expected
```

- [ ] **Step 2: 编译三 proposer + collect + Hermes decision + approval**

默认 proposer 为 Claude、Codex、OpenCode；配置可改为 3-5 个。每个 proposer 是完整方案，不允许按领域切片；普通 `planning_mode=single` 只创建一个 planning Node。

- [ ] **Step 3: 强制规划只读**

Planning contract 使用只读 Git credential，workspace policy 禁止 commit/push；候选完成前后比较 `HEAD` 与 `git status --porcelain`，任何变更使候选无效并保存证据。

- [ ] **Step 4: 实现证据化融合校验**

Synthesis 必须覆盖 `evidence_audit`、`consensus`、`unique_insights`、`conflicts`、`adopted`、`rejected`、`final_plan`、`validation`、`unresolved`；每个 material decision 至少引用一个 candidate ID，冲突裁决必须写 rationale。

- [ ] **Step 5: 验证并提交**

Run: `python3 -m pytest tests/unit/test_fusion_compiler.py tests/integration/test_planning_fusion.py -q`

Expected: PASS；普通 Node 不三跑；Fusion 3/3、2/3、1/3、timeout、invalid schema、NEEDS_INPUT 和来源追踪全部覆盖。

```bash
git add src/hermes_dev_flow/fusion src/hermes_dev_flow/hermes tests/unit/test_fusion_compiler.py tests/integration/test_planning_fusion.py
git commit -m "功能：实现高价值多 Agent 规划融合"
```

### Task 11: 接入 Hermes、OpenSpec 与只读 Dashboard

**Files:**
- Create: `skills/hermes-dev-flow/SKILL.md`
- Create: `src/hermes_dev_flow/integrations/openspec.py`
- Rewrite: `scripts/dashboard.py`
- Rewrite: `scripts/dashboard.html`
- Create: `tests/unit/test_hermes_skill.py`
- Create: `tests/integration/test_openspec_adapter.py`
- Create: `tests/integration/test_dashboard_api_boundary.py`

**Interfaces:**
- Hermes skill 只调用 Controller CLI/API，不复制状态机和 Gate 规则。
- OpenSpec adapter 只生成 TaskRequest/TaskGraph，不写运行状态。
- Dashboard 只读 Controller API/SSE；stop/resume/approve 也是 Controller command，不写本地 JSON。

- [ ] **Step 1: 写 owner 边界测试**

```python
def test_dashboard_has_no_direct_sqlite_or_kubernetes_access(source_tree):
    dashboard = source_tree.read("scripts/dashboard.py")
    assert "sqlite3" not in dashboard
    assert "kubernetes" not in dashboard
    assert "state.json" not in dashboard
```

- [ ] **Step 2: 重写单一 Hermes skill**

skill 负责创建 task、选择 `planning_mode`、展示 Fusion 候选、提交 Hermes synthesis、请求 approval、查看 DAG 和发布；不出现 Redis key、直接 kubectl 调度或通用 state set。

- [ ] **Step 3: 实现可选 OpenSpec input adapter**

adapter 校验 proposal/spec/design/tasks 引用，将 dependencies 编译为 TaskGraph；OpenSpec archive 只能在 publication 成功后触发，并保存关联 ID。

- [ ] **Step 4: Dashboard 展示真实模型**

必须展示 Node/Attempt/Lease/Slot、合同 hash、Fusion candidate 状态、DEGRADED 标识、Gate 原始状态、approval 和 publication；不得把 RUNNING 计为完成。

- [ ] **Step 5: 验证并提交**

Run: `python3 -m pytest tests/unit/test_hermes_skill.py tests/integration/test_openspec_adapter.py tests/integration/test_dashboard_api_boundary.py -q`

```bash
git add skills/hermes-dev-flow src/hermes_dev_flow/integrations/openspec.py scripts/dashboard.py scripts/dashboard.html tests/unit/test_hermes_skill.py tests/integration/test_openspec_adapter.py tests/integration/test_dashboard_api_boundary.py
git commit -m "功能：接入 Hermes、OpenSpec 与 Controller Dashboard"
```

### Task 12: 迁移旧入口并删除双重 owner

**Files:**
- Modify then delete after cutover: `bin/hermes-dev-flow`
- Delete after cutover: `skills/dev-intake/`, `skills/dev-run-worker/`, `skills/dev-gate/`, `skills/dev-escalation/`, `skills/dev-integrate/`
- Delete after cutover: legacy files under `scripts/` except rewritten dashboard files
- Delete after cutover: `contracts/input.schema.json`, `contracts/output.schema.json`, `contracts/escalate.schema.json`
- Delete after cutover: `docker/dev-flow-spec`, `docker/reset.sh`, `docker/task_runner.py`, `docker/worker-entrypoint.sh`
- Delete after cutover: `k8s/worker-deployment.yaml`
- Delete: `package.json`
- Create: `tests/integration/test_legacy_cutover.py`
- Modify: `README.md`
- Modify: `docs/HANDOFF.md`

**Interfaces:**
- Primary install: `pipx install git+https://github.com/tianyuegithub/hermes-dev-flow.git`.
- CLI: `hermes-dev-flow controller|project|task|run|status|approve|answer|publish|doctor`.

- [ ] **Step 1: 先将旧 CLI 变成 v2 API wrapper**

迁移窗口内旧命令只转换参数并调用新 CLI/API，不读写 `state.json` 或 Redis。通过环境开关选择 legacy/v2 只允许用于一次验收，禁止同时双写。

- [ ] **Step 2: 跑旧用例与 v2 E2E 对照**

Run: `python3 -m pytest tests/test_*.py tests/integration/test_legacy_cutover.py -q`

Expected: 用户可见入口已覆盖；旧脚本不再是任何状态 owner。

- [ ] **Step 3: 删除旧 owner 和 npm 空壳**

删除已被 v2 覆盖的脚本、旧 skills、旧 schema、Redis worker 和 package.json；Git 历史保留原实现，不创建 legacy 目录。

- [ ] **Step 4: 重写 README 和 HANDOFF 真实支持矩阵**

明确区分 `implemented/tested/experimental/planned`；不把单次 smoke 写成 L1 完成。记录 SQLite 单副本边界、K3s 需求、三 Agent 支持度、Fusion 使用范围和故障恢复方式。

- [ ] **Step 5: 验证并提交**

Run: `python3 -m pytest -q && python3 -m build && hermes-dev-flow doctor`

Expected: tests/build PASS；doctor 对未配置能力明确报告 unavailable，不 traceback；仓库不存在第二状态 owner。

```bash
git add bin/hermes-dev-flow skills scripts contracts docker k8s package.json README.md docs/HANDOFF.md tests/integration/test_legacy_cutover.py
git commit -m "重构：切换 V2 主链并移除旧双重状态 owner"
```

### Task 13: CI、真实 K3s 验收与首个版本发布

**Files:**
- Create: `.github/workflows/ci.yml`
- Rewrite: `.github/workflows/docker-publish.yml`
- Create: `tests/k3s/test_end_to_end.py`
- Create: `docs/reports/v2-acceptance-验收报告.md`
- Modify: `README.md`

**Interfaces:**
- CI gate: Python 3.11/3.12/3.13 unit + integration + package build.
- Image gate: controller/worker multi-arch build, SBOM, digest output, tag release.
- K3s release gate: real Controller, real worker Pods, real Git remote, at least two configured CLI agents;没有凭证的第三 Agent 必须报告 unavailable，不能 fake。

- [ ] **Step 1: 建立 CI**

Run in CI:

```bash
python -m pip install -e '.[dev]'
python -m pytest -m 'not k3s' -q
python -m build
git status --porcelain
```

Expected: tests/build PASS，测试后无运行态污染。

- [ ] **Step 2: 建立镜像发布 gate**

只有 CI 成功且 tag 匹配 `v*` 才 push `controller` 与 `worker` 镜像；部署 manifest 引用 digest 或精确版本，不在正式验收使用 `latest`。

- [ ] **Step 3: 运行真实 K3s 验收矩阵**

Run: `NO_PROXY="*" python3 -m pytest -m k3s tests/k3s/test_end_to_end.py -q`

必须覆盖：

1. 一个项目两个 Pod 并发，且各自一次只执行一个 Attempt；
2. 普通 Node 只调用一个 Agent；
3. PlanningFusion 三候选并行、2/3 降级和 1/3 阻断；
4. Worker/Controller 重启、Lease 超时、迟到结果和 PVC 复用；
5. DAG sibling、依赖阻断、Integrator 冲突；
6. Agent 伪造 done、非零退出、测试失败、main push 被阻断；
7. dev/test/PM approval 分阶段记录；
8. publish 后远端真实分支与 PR 存在；
9. SSE 断线重连与 Dashboard 真实状态一致。

- [ ] **Step 4: 记录真实验收报告和容量基线**

报告必须包含镜像 digest、Controller 版本、K3s 版本、项目 ID、run IDs、Git refs、p50/p95 claim 延迟、冷/热启动延迟、失败用例和未覆盖项；不得把缺失 Agent 或未测故障标成通过。

- [ ] **Step 5: 代码评审并决定 review-fix**

评审重点：第二状态 owner、stale token 接受、跨项目调度、planning 写权限、Gate waiver 旁路、错误成功状态、凭证泄漏和测试污染。零 finding 记录 `review-fix=NOT_TRIGGERED（未触发）`。

- [ ] **Step 6: 发布提交**

```bash
git add .github README.md docs/reports tests/k3s
git commit -m "发布：完成 Hermes Dev-Flow V2 真实验收基线"
```

---

## 5. 交付顺序与停止线

| 批次 | Tasks | 可独立验收结果 | 未通过时停止 |
|---|---|---|---|
| A 领域核心 | 1-4 | 合同、SQLite、RunPlan、Controller API | 不进入任何 K3s 改造 |
| B 单节点执行 | 5-8 | L0/L1 同合同、Lease 热池、可信 Gate | 不实现多节点 DAG/Fusion |
| C DAG | 9 | 并发、集成、重试和重启恢复 | 不实现 Fusion |
| D 高价值 Fusion | 10 | 同题独立提案、Hermes 融合、退化语义 | 不开放默认 Fusion |
| E 入口与迁移 | 11-12 | Hermes/OpenSpec/Dashboard 单写路径，旧 owner 删除 | 不发布 V2 |
| F 发布 | 13 | CI、镜像、真实 K3s 验收和报告 | 不打稳定 tag |

每个批次只在前一批次的真实 gate 通过后开始。Task 7 首先完成“一项目、一 Agent、一 Node”的窄闭环，再扩为多 Agent；Task 10 只复用已经稳定的合同、Lease 和热池，不另造执行协议。

## 6. 明确不做

- 不在首版引入 PostgreSQL、Redis Streams、Kafka、Celery、Temporal、Argo Workflows 或 CRD。
- 不实现多 Controller active-active。
- 不把一个逻辑 DAG Node 永久绑定一个 Pod。
- 不为普通 Node 默认运行三种 Agent。
- 不把 PlanningFusion 做成投票器、文本拼接器或 diff 大小评分器。
- 不让 Planning Pod 修改代码或 push。
- 不让 Dashboard、Hermes skill 或 Worker 直接写数据库/K8s 状态。
- 不在人工等待期间无限占用热池 Slot。
- 不把 Worker PVC 当唯一制品库。
- 不以 OpenSpec、Redis 或对话历史作为运行态 SSOT。

## 7. Self-Review Result

- Spec coverage：覆盖 Hermes/Controller 边界、K3s 子 Agent、项目 1:N Pod、热池复用、Node/Attempt/Slot/Lease、DAG、契约流转、Fusion 范围、三 Agent、L0/L1、Gate、人工审批、发布与开源验收。
- Architecture challenge：拒绝当前无证据的 PostgreSQL + Redis 双基础设施，保留迁移触发条件；拒绝永久 Node:Pod 和所有节点三 Agent 竞赛。
- Failure semantics：覆盖 claim、heartbeat、lease expiry、fencing、retry、Controller/Pod 重启、PVC 丢失、迟到结果、NEEDS_INPUT、Fusion quorum 和 publish 幂等。
- Placeholder scan：没有未决占位语句；所有延后项都有明确触发条件或明确不做。
- Type consistency：TaskGraph、RunPlan、Node、Attempt、PodSlot、Lease、ContractEnvelope、ArtifactRef、Proposal、FusionSynthesis、GateResult 在首次出现处定义，并在后续任务保持一致。
- HTML companion：本文件是活跃实施计划，不创建 HTML 伴随版；`docs/architecture-current.html` 继续只表示当前 v0.5.1 原型，不作为 V2 事实源。
