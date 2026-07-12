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

    # 6. 从 spec 读 worker 类型
    # 修改说明：Codex Worker — 双 CLI 支持 | 修改时间：2026-07-03
    WORKER_TYPE=$(python3 -c "
import json,sys
d=json.load(open('/tmp/input.json'))
sys.stdout.write(d.get('worker','claude'))
")
    echo "[worker] 类型: $WORKER_TYPE"

    # 7. 从 spec 拼 prompt（共用）
    GOAL=$(python3 -c "
import json,sys
d=json.load(open('/tmp/input.json'))
sys.stdout.write(d['goal'])
")

    ACCEPTANCE=$(python3 -c "
import json,sys
d=json.load(open('/tmp/input.json'))
sys.stdout.write(chr(10).join('- '+a for a in d.get('acceptance',[])))
")

    FORBIDDEN=$(python3 -c "
import json,sys
d=json.load(open('/tmp/input.json'))
sys.stdout.write(chr(10).join('- '+f for f in d.get('constraints',{}).get('forbidden',[])))
")

    echo "[worker] goal: ${GOAL:0:80}..."

    # ── 多步执行（OpenSpec 融合 P1） ──
    TASK_COUNT=$(python3 -c "
import json
d=json.load(open('/tmp/input.json'))
print(len(d.get('spec',{}).get('tasks',[])))
")

    if [ "$TASK_COUNT" -gt 0 ]; then
        echo "[worker] 检测到 ${TASK_COUNT} 个子任务，使用 task_runner 多步执行..."
        python3 /usr/local/bin/task_runner.py "$TASK_ID" /workspace/repo 2>&1 | tee /tmp/task-runner.log
        echo "[worker] task_runner 完成，汇总结果..."

        # 汇总所有子任务 output
        python3 -c "
import json, subprocess
task_id = '$TASK_ID'
diff = subprocess.run(['git', '-C', '/workspace/repo', 'diff', 'origin/main..HEAD', '--stat'], capture_output=True, text=True).stdout.strip()
commit = subprocess.run(['git', '-C', '/workspace/repo', 'log', '--oneline', '-1'], capture_output=True, text=True).stdout.strip()
output = {'task_id': task_id, 'status': 'done', 'commits': [commit.split()[0]] if commit else [], 'evidence': {'diff_stat': diff, 'multi_step': True}}
with open('/tmp/output.json', 'w') as f:
    json.dump(output, f, ensure_ascii=False)
"
    else
        echo "[worker] 单步执行..."

    # 8. 调用 CLI agent（按类型路由）
    # 修改说明：Codex Worker — 双 CLI 支持 | 修改时间：2026-07-03
    if [ "$WORKER_TYPE" = "codex" ]; then
        echo "[worker] starting codex (--sandbox danger-full-access)..."
        codex exec --full-auto --sandbox danger-full-access "你是 dev-flow worker agent。
    elif [ "$WORKER_TYPE" = "opencode" ]; then
        echo "[worker] starting opencode..."
        opencode --model "${OPENCODE_MODEL:-auto}" --yes "你是 dev-flow worker agent。

## 任务目标
$GOAL

## 验收标准
$ACCEPTANCE

## 约束（必须遵守）
$FORBIDDEN

## 完成后
1. git add -A
2. git commit -m 'feat: dev-flow task'
3. 在最后一行输出: DONE" 2>&1 | tee /tmp/agent-raw.txt || true
        echo "[worker] codex 完成，解析输出..."

        python3 << 'PARSEEOF'
import json, subprocess, os

task_id = os.environ["TASK_ID"]
worker_type = "codex"

# Codex 输出是纯文本，解析 DONE 标记和 git 状态
raw_text = ""
try:
    with open("/tmp/agent-raw.txt") as f:
        raw_text = f.read()
except Exception:
    pass

diff = subprocess.run(
    ["git", "-C", "/workspace/repo", "diff", "origin/main..HEAD", "--stat"],
    capture_output=True, text=True
).stdout.strip()

commit = subprocess.run(
    ["git", "-C", "/workspace/repo", "log", "--oneline", "-1"],
    capture_output=True, text=True
).stdout.strip()

# Codex 没有 turns/cost 统计
output = {
    "task_id": task_id,
    "status": "done" if diff else "blocked",
    "worker": worker_type,
    "commits": [commit.split()[0]] if commit else [],
    "evidence": {
        "diff_stat": diff,
    },
}

with open("/tmp/output.json", "w") as f:
    json.dump(output, f, ensure_ascii=False)

print(json.dumps(output, indent=2, ensure_ascii=False))
PARSEEOF
    else
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
            --dangerously-skip-permissions 2>&1 | tee /tmp/agent-raw.txt || true

        echo "[worker] claude code 完成，解析输出..."

        python3 << 'PARSEEOF'
import json, subprocess, os

task_id = os.environ["TASK_ID"]
worker_type = "claude"

try:
    with open("/tmp/agent-raw.txt") as f:
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
    "worker": worker_type,
    "commits": [commit.split()[0]] if commit else [],
    "evidence": {
        "diff_stat": diff,
        "claude_cost": raw.get("total_cost_usd", 0),
        "claude_turns": raw.get("num_turns", 0),
    },
    "session_id": raw.get("session_id", ""),
}

# 修改说明：L1 逃生舱 — blocked 时写 Redis escalate | 修改时间：2026-07-03
if not diff:
    import subprocess as sp
    sp.run([
        "redis-cli", "-h", os.environ.get("REDIS_HOST", "redis.infra.svc.cluster.local"),
        "-p", os.environ.get("REDIS_PORT", "6379"),
        "SET", f"escalate:{task_id}",
        json.dumps({
            "task_id": task_id,
            "type": "escalate",
            "question": f"Agent ({worker_type}) 未能产生代码变更",
            "options": [
                {"id": "A", "desc": "重试 — 更明确的任务描述"},
                {"id": "B", "desc": "放弃 — 标记失败"},
                {"id": "C", "desc": "人工介入 — 查看 agent 日志"}
            ],
            "recommendation": "A",
            "rationale": f"Agent returned no diff, possible causes: insufficient turns, ambiguous goal, or network error",
            "blast_radius": "任务未执行，无影响",
            "session_id": raw.get("session_id", ""),
            "wip_branch": f"dev-flow/{task_id}",
            "raw_output": raw_text[:2000],
        }, ensure_ascii=False)
    ])

with open("/tmp/output.json", "w") as f:
    json.dump(output, f, ensure_ascii=False)

print(json.dumps(output, indent=2, ensure_ascii=False))
PARSEEOF
    fi

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
