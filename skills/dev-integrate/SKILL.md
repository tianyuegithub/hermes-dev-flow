---
name: dev-integrate
description: "集成收口：push 工作分支到远端 + 通过 Gitea API 创建 Pull Request"
version: 0.1.0
platforms: [macos]
tags: [dev-flow, integration, pr, delivery]
---

# dev-integrate · 集成收口

闸门通过后的最后一步：把工作分支 push 到 Gitea，创建 PR。

## 前置条件

- 任务状态为 `DONE`（闸门已通过）
- 工作分支有 commit（`state.py get <task_id>` 中 evidence.commit 非空）
- Gitea 可访问（192.168.31.7:30000/30022）

## 执行流程

### 第一步：确认任务状态

```bash
python3 ~/Codes/ai-dev-flow/scripts/state.py get <task_id>
```

确认：
- `status` = `DONE`
- `evidence.commit` 有值
- `gate_decision.action` = `approved`

### 第二步：Push 工作分支

```bash
REPO_DIR=~/Codes/ai-dev-flow/worktrees/<task_id>/repo
BRANCH="dev-flow/<task_id>"

cd "$REPO_DIR"
git push origin "$BRANCH"
```

Gitea SSH: `ssh://git@192.168.31.7:30022/datavdl/deer-flow.git`

### 第三步：创建 PR

```bash
bash ~/Codes/ai-dev-flow/scripts/gitea_pr.sh \
  <task_id> \
  "<PR 标题>" \
  "<PR 描述>" \
  "dev-flow/<task_id>" \
  "main"
```

脚本内部调 Gitea API：
```
POST http://192.168.31.7:30000/api/v1/repos/datavdl/deer-flow/pulls
Authorization: Basic <base64>
Content-Type: application/json

{
  "title": "...",
  "body": "...",
  "head": "dev-flow/<task_id>",
  "base": "main"
}
```

返回 PR URL。

### 第四步：更新任务状态

```bash
python3 ~/Codes/ai-dev-flow/scripts/state.py set <task_id> pr_url "<pr_url>"
```

---

## PR 描述模板

自动从 task state 和 evidence 生成：

```markdown
## 🤖 AI 开发流程自动生成

**任务**: <task_id>
**类型**: <task_type>
**Worker**: <worker> · cost: $<cost>

### 变更
- <files_changed 列表>
- Diff: <diff_stat>

### 测试
<test_result>

### 验收
<self_check 逐条>

---
*由 Hermes AI 开发流程编排框架自动创建 · 请人工 Review 后合并*
```

## 陷阱

1. **push 前确认分支名**——`git branch --show-current` 必须是 `dev-flow/<task_id>`
2. **Gitea API 需要 Basic Auth**——用户名密码硬编码在 gitea_pr.sh（L1 换 token）
3. **重复 PR**——如果分支已有 PR，Gitea API 会报错，先检查
