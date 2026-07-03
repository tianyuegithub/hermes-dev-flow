---
name: dev-run-worker
description: "接缝本体：Hermes 调 CLI agent 黑盒（Claude Code / Codex），拿回带证据的输出契约"
version: 0.1.0
platforms: [macos]
tags: [dev-flow, worker, seam, contract]
---

# dev-run-worker · 接缝本体

这是 Hermes AI 开发流程编排框架的**核心接缝**——Hermes 不写代码，只在这里调 CLI agent 黑盒干活。

## 前置条件

- 已有任务状态（`state.py get <task_id>` 可读）
- 工作副本已准备（`git_prepare.sh` 已执行）
- Claude Code (`claude`) 或 Codex (`codex`) 可用

## 输入契约（Hermes → agent）

文件：`.hermes/tasks/<task_id>/input.json`

```json
{
  "task_id": "task-20260701-001",
  "task_type": "feature",
  "repo_url": "git@192.168.31.7:datavdl/deer-flow.git",
  "base_branch": "main",
  "goal": "自然语言目标（用户原话 + intake 归一）",
  "acceptance": ["验收标准1", "验收标准2"],
  "constraints": {
    "coding_standards": "遵循项目已有代码风格",
    "forbidden": ["禁止改 main 分支", "禁止 force push", "禁止改数据库 schema 不经确认"]
  },
  "budget": {"max_iterations": 8, "max_wallclock_minutes": 15}
}
```

## 输出契约（agent → Hermes）

文件：`.hermes/tasks/<task_id>/output.json`

```json
{
  "task_id": "task-20260701-001",
  "status": "done | blocked | escalate",
  "branch": "dev-flow/task-20260701-001",
  "commits": ["abc123"],
  "evidence": {
    "test_output_path": ".hermes/tasks/task-20260701-001/test-output.txt",
    "diff_stat": "+120 -5",
    "files_changed": ["src/health.go", "src/health_test.go"]
  },
  "self_check": [
    {"criterion": "验收标准1", "met": true, "proof": "测试通过"},
    {"criterion": "验收标准2", "met": true, "proof": "curl /health 返回 200"}
  ]
}
```

## 逃生舱协议（agent 中途升级）

agent 撞到无法自决的岔口 → 写 `.hermes/tasks/<task_id>/escalate.json` 并退出：

```json
{
  "task_id": "task-20260701-001",
  "type": "escalate",
  "question": "这里有两种实现方式，需要人拍板",
  "options": [
    {"id": "A", "desc": "用标准库 net/http", "pros": "零依赖", "cons": "缺少中间件支持"},
    {"id": "B", "desc": "用 gin 框架", "pros": "生态好", "cons": "引入新依赖"}
  ],
  "recommendation": "B",
  "rationale": "项目已有 gin 依赖，保持一致",
  "blast_radius": "仅影响 /health 路由注册方式",
  "wip_branch": "dev-flow/task-20260701-001",
  "session_id": "75e2167f-..."
}
```

Hermes 发现 escalate.json 后 → 转发给你 → 你选 A/B + 补充意见 → Hermes 写
`.hermes/tasks/<task_id>/decision.json`：

```json
{ "chosen": "B", "note": "用 gin，已有的就别再加标准库了" }
```

然后 resume agent：`claude --resume <session_id> -p "按 decision.json 继续"`

---

## 执行流程

### 第一步：确认环境

```bash
# 读取任务状态
python3 ~/Codes/ai-dev-flow/scripts/state.py get <task_id>

# 确认工作副本存在
ls ~/Codes/ai-dev-flow/worktrees/<task_id>/repo/
```

### 第二步：准备 git 工作副本（若未准备）

```bash
bash ~/Codes/ai-dev-flow/scripts/git_prepare.sh \
  <repo_url> <task_id> main
```

### 第三步：拼输入契约

读 `state.py get <task_id>` 获取 task_type、goal 等信息，拼成完整的 input.json，写入：
```
~/Codes/ai-dev-flow/.hermes/tasks/<task_id>/input.json
```

### 第四步：调 CLI agent 黑盒

**选 worker：** 从 state 中 `worker` 字段读取（`claude` 或 `codex`），默认用 `claude`。

#### Claude Code worker（推荐）

```bash
WORK_DIR=~/Codes/ai-dev-flow/worktrees/<task_id>/repo
INPUT=~/Codes/ai-dev-flow/.hermes/tasks/<task_id>/input.json

# 读 input.json 提取 goal
GOAL=$(python3 -c "import json; print(json.load(open('$INPUT'))['goal'])")
ACCEPTANCE=$(python3 -c "import json; print('\n'.join(json.load(open('$INPUT'))['acceptance']))")

# 构造 prompt（注入约束 + 验收标准 + 证据要求）
PROMPT="你是 dev-flow worker agent。完成以下任务，并按要求产出证据。

## 任务目标
$GOAL

## 验收标准
$ACCEPTANCE

## 约束
- 不要改 main 分支，你当前已在工作分支上
- 完成后执行 git add + git commit
- 必须把测试输出保存到 .hermes/evidence/test-output.txt
- 最后用 git diff origin/main --stat 输出变更摘要

## 逃生舱规则（遇到以下情况不要自己决定，写 escalate.json 然后退出）
- 需要在两种互斥的技术方案间选择，且各有利弊
- 修改会影响数据库 schema 或安全策略
- 发现任务描述有歧义，无法确定用户意图
- 修改范围超出原始任务定义

escalate.json 写入 .hermes/tasks/<task_id>/escalate.json，格式：
{
  "task_id": "...", "type": "escalate",
  "question": "...",
  "options": [{"id":"A","desc":"...","pros":"...","cons":"..."}, ...],
  "recommendation": "A",
  "rationale": "...",
  "blast_radius": "...",
  "session_id": "<你的 session ID>",
  "wip_branch": "<当前分支>"
}
写完后 git add + git commit -m "escalate: ..." 然后退出。

## 输出格式
完成后，在最后输出一个 JSON 块（用 \`\`\`json 包裹）：
{
  \"status\": \"done|blocked\",
  \"commits\": [\"<commit-sha>\"],
  \"evidence\": {
    \"test_output_path\": \".hermes/evidence/test-output.txt\",
    \"diff_stat\": \"...\",
    \"files_changed\": [\"...\"]
  },
  \"self_check\": [
    {\"criterion\": \"验收标准1\", \"met\": true|false, \"proof\": \"证据\"}
  ]
}"

claude -p "$PROMPT" \
  --output-format json \
  --max-turns 10 \
  --allowedTools "Read,Write,Edit,Bash" \
  --dangerously-skip-permissions \
  --workdir "$WORK_DIR" 2>&1 | tee ~/Codes/ai-dev-flow/.hermes/tasks/<task_id>/claude-raw.json
```

#### Codex worker（备选）

```bash
WORK_DIR=~/Codes/ai-dev-flow/worktrees/<task_id>/repo
TASK_DIR=~/Codes/ai-dev-flow/.hermes/tasks/<task_id>

# 拼 prompt
GOAL=$(python3 -c "import json; print(json.load(open('$TASK_DIR/input.json'))['goal'])")

cd "$WORK_DIR"
codex exec --full-auto "$GOAL

## 约束
- 不要改 main 分支，你当前已在工作分支 dev-flow/<task_id> 上
- 完成后: git add + git commit
- 必须把测试输出保存到 .hermes/evidence/test-output.txt
- 最后用 git diff origin/main --stat 看变更

## 逃生舱
遇到无法自决的选择时，写 .hermes/tasks/<task_id>/escalate.json（格式同 Claude 版），然后退出。

## 输出
完成后输出一段 JSON（用 \`\`\`json 包裹）：
{\"status\":\"done|blocked\",\"commits\":[\"<sha>\"],\"files_changed\":[\"...\"],\"test_result\":\"pass|fail|skipped\"}" 2>&1 | tee "$TASK_DIR/codex-raw.txt"
```

**Codex vs Claude 差异：**
| | Claude Code | Codex |
|---|---|---|
| 调用方式 | `claude -p "..."` | `codex exec "..."` |
| 自动提交 | 需 prompt 明确要求 | `--full-auto` 自动 commit |
| 输出格式 | `--output-format json` 结构化 | 纯文本，需从 stdout 解析 |
| session_id | `result.session_id` | 不在输出中（L1 补） |
| sandbox | 需 `--dangerously-skip-permissions` | `--full-auto` 自带 |
| PTY | `--bare` 跳过 | 必须 `pty=true` |

### 第五步：解析输出契约

从 Claude Code JSON 输出或 Codex 文本输出中提取：
- `status`：done / blocked
- `commits`：提交 SHA 列表
- `evidence`：测试输出路径、diff 统计、变更文件列表
- `self_check`：逐条验收自检

写入 `output.json`：
```bash
python3 ~/Codes/ai-dev-flow/scripts/state.py set <task_id> evidence '<evidence_json>'
```

### 第六步：更新任务状态

```bash
# 成功
python3 ~/Codes/ai-dev-flow/scripts/state.py trans <task_id> VERIFY_GATE

# 或失败
python3 ~/Codes/ai-dev-flow/scripts/state.py trans <task_id> FAILED

# 或逃生舱（worker 写了 escalate.json）
python3 ~/Codes/ai-dev-flow/scripts/state.py trans <task_id> ESCALATED
```

---

## 防假绿要点（贯穿始终）

1. **声明 ≠ 证据**：agent 说 "done" 只是声明，验证闸门只核 `evidence` 字段
2. **测试产物必须落盘**：要求 agent 把测试输出写入 `.hermes/evidence/test-output.txt`
3. **diff 必须可核查**：要求 agent 输出 `git diff origin/main --stat`
4. **逃生舱保留 WIP**：agent escalate 时必须 commit WIP + 记录 session_id，供 resume

## 陷阱与注意事项

1. **Claude Code `-p` 模式不自动 git commit**——必须在 prompt 里明确要求
2. **Codex `--full-auto` 自动 commit**——注意别让它 push 到 main
3. **工作分支命名一致**——`git_prepare.sh` 创建的分支名 = `dev-flow/<task_id>`，input/output 里的 branch 必须对得上
4. **session_id 是 resume 关键**——Claude Code `--output-format json` 返回的 `session_id` 必须保存到 state
5. **路径一致性**——所有 `.hermes/` 路径是相对于工作副本根目录的

## 测试验证

```bash
# 1. 创建一个测试任务
python3 ~/Codes/ai-dev-flow/scripts/state.py init test-001 feature \
  git@192.168.31.7:datavdl/deer-flow.git

# 2. 设置 worker
python3 ~/Codes/ai-dev-flow/scripts/state.py set test-001 worker claude

# 3. 准备 git
bash ~/Codes/ai-dev-flow/scripts/git_prepare.sh \
  git@192.168.31.7:datavdl/deer-flow.git test-001 main

# 4. 手动拼 input.json 并调 worker
# ...（按第四步执行）

# 5. 检查证据
cat ~/Codes/ai-dev-flow/.hermes/tasks/test-001/output.json
```
