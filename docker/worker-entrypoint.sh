#!/bin/bash
# worker-entrypoint.sh — Worker Pod 热池主循环
# 设计文档 §5: Pod 跑完 reset，供下个任务复用
set -uo pipefail

REDIS_HOST="${REDIS_HOST:-redis.infra.svc.cluster.local}"
REDIS_PORT="${REDIS_PORT:-6379}"
POD_NAME="${POD_NAME:-dev-flow-worker-1}"
REPO_URL="${REPO_URL:?}"
export PATH="/usr/local/bin:/usr/bin:/bin:$PATH"
export GIT_SSH_COMMAND="ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i $HOME/.ssh/id_rsa"

# ── 首次 clone ──
echo "[worker] 启动: $POD_NAME"
if [ -d "/workspace/repo/.git" ]; then
    cd /workspace/repo && git fetch origin || true
else
    for i in 1 2 3; do
        git clone --depth 1 "$REPO_URL" /workspace/repo && break
        rm -rf /workspace/repo && sleep 5
    done
fi
cd /workspace/repo 2>/dev/null || { mkdir -p /workspace/repo && cd /workspace/repo && git init; }

redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" SET "pod:$POD_NAME:state" "idle"
echo "[worker] 就绪，等待任务..."

# ── 主循环 ──
while true; do
    TASK_ID=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" BLPOP "pod:$POD_NAME:queue" 0 | tail -1)
    export TASK_ID
    echo "=========================================="
    echo "[worker] 收到任务: $TASK_ID"

    redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" SET "pod:$POD_NAME:state" "busy"
    redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" SET "status:$TASK_ID" "running"

    # Fetch spec
    dev-flow-spec fetch "$TASK_ID" > /tmp/input.json

    # 心跳
    (while true; do
        S=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" GET "status:$TASK_ID" 2>/dev/null || echo "")
        [ "$S" != "running" ] && exit 0
        dev-flow-spec heartbeat "$TASK_ID"
        sleep 30
    done) &
    HB_PID=$!

    # Git prepare
    git fetch origin
    git checkout -B "dev-flow/$TASK_ID" origin/main
    git clean -fdx
    mkdir -p .hermes/evidence

    # Read spec
    GOAL=$(python3 -c "import json; d=json.load(open('/tmp/input.json')); print(d['goal'])")
    WORKER_TYPE=$(python3 -c "import json; d=json.load(open('/tmp/input.json')); print(d.get('worker','claude'))")
    echo "[worker] goal($WORKER_TYPE): ${GOAL:0:80}..."

    # Build prompt file
    python3 /usr/local/bin/build_prompt.sh 2>/dev/null || python3 -c "
import json
d=json.load(open('/tmp/input.json'))
goal=d['goal']
acc='\n'.join('- '+a for a in d.get('acceptance',[]))
forb='\n'.join('- '+f for f in d.get('constraints',{}).get('forbidden',[]))
prompt = f'''你是 dev-flow worker agent。

## 任务目标\n{goal}

## 验收标准\n{acc}

## 约束\n{forb}

## 完成后\n1. git diff origin/main..HEAD --stat\n2. git add + git commit\n3. 输出 JSON'''
with open('/tmp/prompt.txt','w') as f: f.write(prompt)
"

    # Run agent
    case "$WORKER_TYPE" in
        codex)
            echo "[worker] codex..."
            codex exec --full-auto --sandbox danger-full-access "$(cat /tmp/prompt.txt)" 2>&1 | tee /tmp/agent-raw.txt || true
            ;;
        opencode)
            echo "[worker] opencode..."
            opencode --model "${OPENCODE_MODEL:-auto}" --yes "$(cat /tmp/prompt.txt)" 2>&1 | tee /tmp/agent-raw.txt || true
            ;;
        *)
            echo "[worker] claude..."
            cat /tmp/prompt.txt | claude --bare -p "$(cat)" --output-format json \
                --max-turns 300 --dangerously-skip-permissions 2>&1 | tee /tmp/agent-raw.txt || true
            ;;
    esac

    # Parse output  
    python3 << 'PYEND'
import json, subprocess, os
task_id = os.environ["TASK_ID"]
wt = json.load(open("/tmp/input.json")).get("worker", "claude")

# Try Claude JSON format first
raw = {"subtype": "error", "session_id": "", "total_cost_usd": 0, "num_turns": 0}
try:
    with open("/tmp/agent-raw.txt") as f:
        raw = json.load(f)
except: pass

diff = subprocess.run(["git", "-C", "/workspace/repo", "diff", "origin/main..HEAD", "--stat"],
                      capture_output=True, text=True).stdout.strip()
commit = subprocess.run(["git", "-C", "/workspace/repo", "log", "--oneline", "-1"],
                        capture_output=True, text=True).stdout.strip()

output = {
    "task_id": task_id, "worker": wt,
    "status": "done" if diff else "blocked",
    "commits": [commit.split()[0]] if commit else [],
    "evidence": {
        "diff_stat": diff,
        "claude_turns": raw.get("num_turns", 0),
        "claude_cost": raw.get("total_cost_usd", 0),
    },
    "session_id": raw.get("session_id", ""),
}
with open("/tmp/output.json", "w") as f:
    json.dump(output, f, ensure_ascii=False)
print(json.dumps(output, indent=2, ensure_ascii=False))
PYEND

    # Submit + push + reset
    dev-flow-spec submit "$TASK_ID" /tmp/output.json
    git push origin "dev-flow/$TASK_ID" 2>/dev/null || echo "[worker] push skipped"
    kill $HB_PID 2>/dev/null || true

    redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" SET "pod:$POD_NAME:state" "resetting"
    bash /usr/local/bin/reset.sh
    redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" SET "pod:$POD_NAME:state" "idle"
    echo "[worker] reset 完成"
done
