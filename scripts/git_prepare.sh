#!/bin/bash
# ============================================================
# git_prepare.sh — 为任务准备独立工作副本（reset 契约）
# 用法: git_prepare.sh <repo_url> <task_id> [base_branch]
# 输出 JSON: {"work_dir":"...", "branch":"...", "status":"ok|error"}
# ============================================================
set -euo pipefail

REPO_URL="${1:?Usage: git_prepare.sh <repo_url> <task_id> [base_branch]}"
TASK_ID="${2:?Usage: git_prepare.sh <repo_url> <task_id> [base_branch]}"
BASE_BRANCH="${3:-main}"

WORK_DIR="$HOME/Codes/ai-dev-flow/worktrees/${TASK_ID}"
REPO_DIR="${WORK_DIR}/repo"
BRANCH="dev-flow/${TASK_ID}"

log() { echo "[git_prepare] $*" >&2; }
json_out() { python3 -c "import json; print(json.dumps($1))"; }

log "task=${TASK_ID} repo=${REPO_URL} base=${BASE_BRANCH}"

# ── 1. Clone or fetch ──────────────────────────────────────
# 绕过系统 HTTP 代理（内网 Gitea 不走代理，否则 sideband disconnect）
export GIT_SSL_NO_VERIFY=1

if [ -d "${REPO_DIR}/.git" ]; then
    log "[1/4] 已有工作副本，fetch 最新..."
    git -C "${REPO_DIR}" -c http.proxy= -c https.proxy= fetch origin 2>&1 | tail -1 >&2
else
    log "[1/4] 首次 clone（Gitea 内网，走 SSH/直连，不走代理）..."
    mkdir -p "${REPO_DIR}"
    git -c http.proxy= -c https.proxy= clone "${REPO_URL}" "${REPO_DIR}" 2>&1 | tail -2 >&2
fi

# ── 2. 创建/重置工作分支 ───────────────────────────────────
log "[2/4] 创建/重置工作分支: ${BRANCH}"
git -C "${REPO_DIR}" checkout -B "${BRANCH}" "origin/${BASE_BRANCH}" 2>&1 >&2

# ── 3. Clean（reset 契约核心）──────────────────────────────
log "[3/4] git clean -fdx（清理未追踪文件 + 构建产物）"
git -C "${REPO_DIR}" clean -fdx 2>&1 >&2

# ── 4. Hard reset ──────────────────────────────────────────
log "[4/4] git reset --hard HEAD"
git -C "${REPO_DIR}" reset --hard HEAD 2>&1 >&2

# ── 输出 ────────────────────────────────────────────────────
REPO_NAME=$(basename "${REPO_URL}" .git)
log "就绪: ${REPO_DIR} (分支: ${BRANCH})"

json_out '{"status":"ok","work_dir":"'"${REPO_DIR}"'","branch":"'"${BRANCH}"'","repo_name":"'"${REPO_NAME}"'"}'
