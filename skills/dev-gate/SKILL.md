---
name: dev-gate
description: "验证闸门：核对 worker 产出的证据，发给人拍板（通过/打回+意见）。防假绿的关键落地点。"
version: 0.1.0
platforms: [macos]
tags: [dev-flow, gate, verification, anti-fake-green]
---

# dev-gate · 验证闸门

> 路径约定：`$DEV_FLOW_HOME` = Dev-Flow 根目录。运行 `hermes-dev-flow home` 可查；未设置时 `export DEV_FLOW_HOME=<包安装目录>`。

这是 Hermes AI 开发流程编排框架的**防假绿落地点**。agent 说 "done" 是声明，闸门只认 evidence。

## 前置条件

- 任务状态为 `VERIFY_GATE`（`state.py get <task_id>`）
- evidence 字段有内容（至少 `files_changed` 和 `commit`）

## 验证流程

### 第零步：契约校验（机器强制，先于一切人工核查）

```bash
python3 $DEV_FLOW_HOME/scripts/validate_contract.py --task <task_id> output
```

- `valid: false` → **直接打回**，无需进入后续核查。output.json 不符合 output 契约的产物不具备被验收的资格，把 errors 原样回注给 worker 修正后重交。
- `valid: true` → 才允许进入第一步。

契约是闸门的入场券，不是加分项。见 `docs/THESIS.md` 推论 1。

### 第一步：统一闸门裁决（2026-07-30 起，单一模型）

```bash
python3 $DEV_FLOW_HOME/scripts/gates.py decide <task_id>
```

三条支路：

| 裁决 | 含义 | 动作 |
|------|------|------|
| `approved` | Scorecard auto_pass（测试 green + 证据可核查） | 直接进入 dev-integrate |
| `rejected` | 契约违反 / 测试失败 / 无证据 | 带 feedback 回 EXECUTING，重新调 dev-run-worker |
| `escalated` | 证据不充分（常见于测试 skipped） | 进入三级人工角色链 |

### 第二步（仅 escalated）：三级人工角色依次裁决

```bash
python3 $DEV_FLOW_HOME/scripts/gates.py human <task_id> dev approve
python3 $DEV_FLOW_HOME/scripts/gates.py human <task_id> test reject "测试产物不可信"
python3 $DEV_FLOW_HOME/scripts/gates.py status <task_id>   # 查当前待裁决角色
```

- 顺序固定 **dev → test → pm**，越序报错；任一角色 reject → 链路终止打回
- 每个角色的核查清单见下方"防假绿检查清单"
- 每次裁决（自动与人工）都记入 `gate_history`，可审计

### 人工核查手册（dev/test/pm 角色的作业清单）

#### 加载任务状态和证据

```bash
python3 $DEV_FLOW_HOME/scripts/state.py get <task_id>
```

从输出中提取：
- `evidence.files_changed` — 变更了哪些文件
- `evidence.diff_stat` — diff 统计
- `evidence.commit` — commit SHA
- `evidence.test_result` — 测试结果（pass/fail/skipped）

#### 核实证据（防假绿核心）

**不能只看 state.json 里的记录！** 必须去工作副本实际核实：

```bash
REPO_DIR=$DEV_FLOW_HOME/worktrees/<task_id>/repo

# 1. 确认 commit 存在
git -C "$REPO_DIR" log --oneline -1

# 2. 确认文件变更属实
git -C "$REPO_DIR" diff origin/main --stat

# 3. 确认测试产物存在（如果有）
ls "$REPO_DIR/.hermes/evidence/test-output.txt" 2>/dev/null && cat "$REPO_DIR/.hermes/evidence/test-output.txt"
```

#### 呈现验证摘要给人

整理成结构化摘要发给用户：

```
📋 验证闸门 · <task_id>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
类型: <task_type>
Worker: <claude|codex>
Commit: <sha> · <commit_message>

📁 变更文件（<N> 个）:
  + backend/app/health.py
  + tests/test_health.py

📊 Diff: <diff_stat>

🧪 测试: <pass|fail|skipped>
  <test output summary>

💰 成本: $<total_cost_usd>

📝 自检清单:
  ✅ /health 返回 200 ok — 测试通过
  ✅ 只新增文件，未改已有文件 — diff 确认

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
等待你的决策：
  A) ✅ 通过 — merge 到 main / 开 PR
  B) ❌ 打回 — 带意见回注 agent，产出 v+1
```

使用 `clarify` 工具发问，选项为 "✅ 通过" 和 "❌ 打回（附意见）"。

#### 执行用户决策

#### 通过（A）

```bash
# 冻结该阶段，标记 DONE
python3 $DEV_FLOW_HOME/scripts/state.py set <task_id> gate_decision "approved"
python3 $DEV_FLOW_HOME/scripts/state.py trans <task_id> DONE
```

然后可进入 `dev-integrate`（push/PR）。

#### 打回（B）

收集用户的打回意见，写入 state：

```bash
python3 $DEV_FLOW_HOME/scripts/state.py set <task_id> gate_decision "{\"action\":\"reject\",\"feedback\":\"<用户原话>\",\"version\":2}"
python3 $DEV_FLOW_HOME/scripts/state.py trans <task_id> EXECUTING
```

然后重新调 `dev-run-worker`，在 prompt 中注入打回意见：

```
上一版被闸门打回，意见如下：
<feedback>

请在此基础上修改，产出 v2。不要重做整个任务，只修复被指出的问题。
```

---

## 防假绿检查清单（每次闸门必核）

| 检查项 | 方法 |
|--------|------|
| ① 声明 vs 证据 | agent 说 done ≠ 真 done，必须核实 evidence 字段 |
| ② commit 存在 | `git log` 确认 SHA 真实存在 |
| ③ 文件变更属实 | `git diff --stat` 确认文件列表匹配 |
| ④ 测试产物可读 | 检查 test-output.txt 文件存在且内容非空 |
| ⑤ 分支隔离 | 确认变更在 dev-flow 分支，未碰 main |
| ⑥ 约束符合 | 对照 input.json 的 constraints.forbidden 逐条检查 |

## 陷阱

1. **不要只看 status 字段** — agent 可能声明 done 但实际没 commit、没测试
2. **test_result=skipped 不代表失败** — 环境缺依赖是正常的（L0 本地没装 pytest），但需标注
3. **diff 为空要警惕** — 可能是 agent 忘了 commit 或搞错了分支
4. **成本异常高要升人** — 单任务超过 $1 或 50 turns 要问是否继续
