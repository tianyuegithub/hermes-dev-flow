#!/bin/bash
# ============================================================
# worker-entrypoint.sh — Worker Pod 常驻主循环
# ============================================================
# 设计文档 §5: Pod 跑完 reset，供下个任务复用（热池模式）
# ============================================================
set -uo pipefail   # 去掉 -e，允许个别命令失败

REDIS_HOST="${REDIS_HOST:-redis.infra.svc.cluster.local}"
REDIS_PORT="${REDIS_PORT:-6379}"
POD_NAME="${POD_NAME:-dev-flow-worker-1}"
REPO_URL="${REPO_URL:?必须设置 REPO_URL}"

export PATH="/usr/local/bin:/usr/bin:/bin:$PATH"

# ── 首次 clone ──────────────────────────────────────────────
echo "[worker] 启动: $POD_NAME"

# 配置 SSH
export GIT_SSH_COMMAND="ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i $HOME/.ssh/id_rsa"

if [ -d "/workspace/repo/.git" ]; then
    echo "[worker] repo 已存在，fetch..."
    cd /workspace/repo && git fetch origin || true
else
    echo "[worker] clone repo..."
    for i in 1 2 3; do
        if git clone --depth 1 "$REPO_URL" /workspace/repo; then
            echo "[worker] clone 成功"
            break
        fi
        echo "[worker] clone 失败(尝试 $i/3)，重试..."
        rm -rf /workspace/repo
        sleep 5
    done
    if [ ! -d "/workspace/repo/.git" ]; then
        echo "[worker] ❌ clone 彻底失败，但继续等待任务（可能 SSH key 未就绪）"
    fi
fi

cd /workspace/repo 2>/dev/null || {
    echo "[worker] ⚠️ /workspace/repo 不存在，创建空目录"
    mkdir -p /workspace/repo
    cd /workspace/repo
    git init
}

# ── 标记 IDLE ───────────────────────────────────────────────
redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" SET "pod:$POD_NAME:state" "idle"
echo "[worker] 就绪，等待任务..."

# ── 主循环 ──────────────────────────────────────────────────
while true; do
    # 1. 阻塞等任务
    TASK_ID=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" BLPOP "pod:$POD_NAME:queue" 0 | tail -1)
    export TASK_ID
    echo ""
    echo "=========================================="
    echo "[worker] 收到任务: $TASK_ID"
    echo "=========================================="

    # 2. 标记 BUSY
    redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" SET "pod:$POD_NAME:state" "busy"
    redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" SET "status:$TASK_ID" "running"

    # 3. Fetch spec
    echo "[worker] fetch spec..."
    dev-flow-spec fetch "$TASK_ID" > /tmp/input.json

    # 4. 心跳（后台）
    (
        while true; do
            S=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" GET "status:$TASK_ID" 2>/dev/null || echo "")
            [ "$S" != "running" ] && exit 0
            dev-flow-spec heartbeat "$TASK_ID"
            sleep 30
        done
    ) &
    HB_PID=$!

    # 5. Git prepare（reset 契约的前半段）
    echo "[worker] git prepare..."
    git fetch origin
    git checkout -B "dev-flow/$TASK_ID" origin/main
    git clean -fdx
    mkdir -p .hermes/evidence

    # 6. 从 spec 拼 prompt
    GOAL=$(python3 -c "
import json
d=json.load(open('/tmp/input.json'))
print(d['goal'])
")

    ACCEPTANCE=$(python3 -c "
import json
d=json.load(open('/tmp/input.json'))
print(chr(10).join('- '+a for a in d.get('acceptance',[])))
")

    FORBIDDEN=$(python3 -c "
import json
d=json.load(open('/tmp/input.json'))
print(chr(10).join('- '+f for f in d.get('constraints',{}).get('forbidden',[])))
")

    echo "[worker] goal: ${GOAL:0:80}..."

    # 7. 调 Claude Code
    echo "[worker] starting claude code..."
    claude --bare -p "你是 dev-flow worker agent。

## 任务目标
$GOAL

## 验收标准
$ACCEPTANCE

## 约束（必须遵守）
$FORBIDDEN

## 完成后
1. git diff origin/main --stat
2. git add + git commit -m 'feat: dev-flow task'
3. 输出 JSON（用 \`\`\`json 包裹）:
{\"status\":\"done\",\"commits\":[\"<sha>\"],\"files_changed\":[\"...\"],\"evidence\":{\"diff_stat\":\"...\"},\"self_check\":[{\"criterion\":\"...\",\"met\":true,\"proof\":\"...\"}]}" \
        --output-format json \
        --max-turns 30 \
        --max-budget-usd 1.50 \
        --dangerously-skip-permissions 2>&1 | tee /tmp/claude-raw.json || true

    echo "[worker] claude code 完成，解析输出..."

    # 8. 解析输出（用 os.environ，不用 heredoc 变量）
    python3 << 'PARSEEOF'
import json, subprocess, os

task_id = os.environ["TASK_ID"]

try:
    with open("/tmp/claude-raw.json") as f:
        raw = json.load(f)
except Exception:
    raw = {"subtype": "error", "session_id": "", "total_cost_usd": 0, "num_turns": 0}

# 修改说明：Bug ① 修复 — Claude 提交后工作区干净，需用 ..HEAD 比较提交间差异 | 修改时间：2026-07-03
diff = subprocess.run(
    ["git", "-C", "/workspace/repo", "diff", "origin/main..HEAD", "--stat"],
    capture_output=True, text=True
).stdout.strip()

commit = subprocess.run(
    ["git", "-C", "/workspace/repo", "log", "--oneline", "-1"],
    capture_output=True, text=True
).stdout.strip()

output = {
    "task_id": task_id,
    "status": "done" if diff else "blocked",
    "commits": [commit.split()[0]] if commit else [],
    "evidence": {
        "diff_stat": diff,
        "claude_cost": raw.get("total_cost_usd", 0),
        "claude_turns": raw.get("num_turns", 0),
    },
    "session_id": raw.get("session_id", ""),
}

with open("/tmp/output.json", "w") as f:
    json.dump(output, f, ensure_ascii=False)

print(json.dumps(output, indent=2, ensure_ascii=False))
PARSEEOF

    # 9. Submit output
    echo "[worker] submit output..."
    dev-flow-spec submit "$TASK_ID" /tmp/output.json

    # 10. Push branch
    # 修改说明：Bug ② 修复 — 暴露 push 真实错误 + 远程验证 | 修改时间：2026-07-03
    echo "[worker] push branch..."
    if ! git remote get-url origin >/dev/null 2>&1; then
        echo "[worker] ❌ push 失败: origin remote 不存在，尝试修复..."
        git remote add origin "$REPO_URL" 2>/dev/null || echo "[worker] ❌ 无法修复 origin"
    fi
    PUSH_ERR=$(git push origin "dev-flow/$TASK_ID" 2>&1) && \
        echo "[worker] push 成功 → dev-flow/$TASK_ID" || \
        echo "[worker] ⚠️ push 失败: $(echo "$PUSH_ERR" | tail -1)"

    # 11. 停心跳
    kill $HB_PID 2>/dev/null || true

    # 12. Reset（复用纪律 — 设计文档 §5）
    echo "[worker] reset..."
    redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" SET "pod:$POD_NAME:state" "resetting"
    bash /usr/local/bin/reset.sh
    redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" SET "pod:$POD_NAME:state" "idle"
    echo "[worker] reset 完成，等待下一个任务"
done
