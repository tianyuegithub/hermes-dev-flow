#!/bin/bash
# ============================================================
# worker-entrypoint.sh — Worker 入口（oneshot 唯一模式）
#
# 2026-07-30：热池模式（pool）已废止删除。
# 一个任务一个 Pod，Manager 调度（worker_manager.py），用完即删。
# 不再有 reset 契约、不再有热池队列——队列只有一条: dev-flow:queue
# ============================================================
set -uo pipefail

REDIS_HOST="${REDIS_HOST:-redis.infra.svc.cluster.local}"
REDIS_PORT="${REDIS_PORT:-6379}"
REPO_URL="${REPO_URL:?REPO_URL 环境变量必须设置（目标 Git 仓库）}"
TASK_ID="${TASK_ID:?TASK_ID 环境变量必须设置}"
MAX_TURNS="${MAX_TURNS:-300}"
BASE_BRANCH="${BASE_BRANCH:-main}"

export PATH="/usr/local/bin:/usr/bin:/bin:$PATH"
export GIT_SSH_COMMAND="ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i $HOME/.ssh/id_rsa"

echo "[worker] oneshot 启动: $TASK_ID"

# ── 心跳（后台，随 Pod 消亡自动终止） ──
(while true; do
  dev-flow-spec heartbeat "$TASK_ID" 2>/dev/null
  sleep 30
done) &
HB_PID=$!
trap 'kill $HB_PID 2>/dev/null || true' EXIT

redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" SET "status:$TASK_ID" "running"

# ── 取输入契约 ──
dev-flow-spec fetch "$TASK_ID" > /tmp/input.json
if [ ! -s /tmp/input.json ]; then
    echo "[worker] ❌ spec 为空: $TASK_ID"
    redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" SET "status:$TASK_ID" "failed"
    exit 1
fi

# ── 克隆仓库 ──
for i in 1 2 3; do
    git clone --depth 1 "$REPO_URL" /workspace/repo && break
    rm -rf /workspace/repo && sleep 5
done
cd /workspace/repo || { echo "[worker] ❌ clone 失败"; redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" SET "status:$TASK_ID" "failed"; exit 1; }
git checkout -B "dev-flow/$TASK_ID" "origin/$BASE_BRANCH"
mkdir -p .hermes/evidence

# ── 拼 prompt ──
WORKER_TYPE=$(python3 -c "import json; print(json.load(open('/tmp/input.json')).get('worker','claude'))")
echo "[worker] goal($WORKER_TYPE): $(python3 -c "import json; print(json.load(open('/tmp/input.json'))['goal'][:80])")"

python3 -c "
import json
d = json.load(open('/tmp/input.json'))
goal = d['goal']
acc = '\n'.join('- ' + a for a in d.get('acceptance', []))
forb = '\n'.join('- ' + f for f in d.get('constraints', {}).get('forbidden', []))
prompt = f'''你是 dev-flow worker agent。

## 任务目标
{goal}

## 验收标准
{acc}

## 约束（必须遵守）
{forb}

## 证据要求
1. git diff origin/{d.get(\"base_branch\",\"main\")}..HEAD --stat
2. git add + git commit
3. 如有测试则把输出保存到 .hermes/evidence/test-output.txt

## 完成后输出 JSON（用 \`\`\`json 包裹）
{{\"status\":\"done|blocked\",\"commits\":[\"<sha>\"],\"evidence\":{{\"diff_stat\":\"...\",\"test_result\":\"pass|fail|skipped\",\"files_changed\":[\"...\"]}}}}'''
with open('/tmp/prompt.txt', 'w') as f:
    f.write(prompt)
"

# ── 调 CLI agent 黑盒 ──
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
        echo "[worker] claude (max-turns=$MAX_TURNS)..."
        claude --bare -p "$(cat /tmp/prompt.txt)" --output-format json \
            --max-turns "$MAX_TURNS" --dangerously-skip-permissions 2>&1 | tee /tmp/agent-raw.txt || true
        ;;
esac

# ── 解析输出契约 ──
BASE_BRANCH="$BASE_BRANCH" python3 << 'PYEND'
import json, subprocess, os
task_id = os.environ["TASK_ID"]
base = os.environ.get("BASE_BRANCH", "main")
wt = json.load(open("/tmp/input.json")).get("worker", "claude")

raw = {}
try:
    with open("/tmp/agent-raw.txt") as f:
        raw = json.load(f)
except Exception:
    pass

diff = subprocess.run(["git", "-C", "/workspace/repo", "diff", f"origin/{base}..HEAD", "--stat"],
                      capture_output=True, text=True).stdout.strip()
commit = subprocess.run(["git", "-C", "/workspace/repo", "log", "--oneline", "-1"],
                        capture_output=True, text=True).stdout.strip()
files = subprocess.run(["git", "-C", "/workspace/repo", "diff", f"origin/{base}..HEAD", "--name-only"],
                       capture_output=True, text=True).stdout.strip().split("\n")

test_result = "skipped"
if os.path.exists("/workspace/repo/.hermes/evidence/test-output.txt"):
    with open("/workspace/repo/.hermes/evidence/test-output.txt") as f:
        content = f.read()
    test_result = "pass" if ("PASS" in content or "ok" in content.lower()) else "fail"

output = {
    "task_id": task_id,
    "status": "done" if diff else "blocked",
    "branch": f"dev-flow/{task_id}",
    "commits": [commit.split()[0]] if commit else [],
    "evidence": {
        "diff_stat": diff,
        "files_changed": [f for f in files if f],
        "test_result": test_result,
        "claude_turns": raw.get("num_turns", 0),
        "claude_cost": raw.get("total_cost_usd", 0),
    },
    "session_id": raw.get("session_id", ""),
}
with open("/tmp/output.json", "w") as f:
    json.dump(output, f, ensure_ascii=False)
print(json.dumps(output, indent=2, ensure_ascii=False))
PYEND

# ── 提交输出契约 + push ──
dev-flow-spec submit "$TASK_ID" /tmp/output.json
git push origin "dev-flow/$TASK_ID" 2>/dev/null || echo "[worker] ⚠️ push 失败（output 已提交 Redis，不阻塞）"

echo "[worker] oneshot 完成: $TASK_ID"
exit 0
