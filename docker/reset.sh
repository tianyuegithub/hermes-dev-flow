#!/bin/bash
# ============================================================
# reset.sh — Pod 任务完成后强制 reset（设计文档 §5 复用纪律）
# ============================================================
# 修改说明：Bug ② 修复 — 验证 origin remote 存活 | 修改时间：2026-07-03
set -euo pipefail

cd /workspace/repo

git fetch origin
git checkout main
git branch -D $(git branch --list 'dev-flow/*') 2>/dev/null || true
git clean -fdx
git reset --hard origin/main

# 修改说明：Bug ② 修复 — 确保 origin remote 未被意外清除 | 修改时间：2026-07-03
if ! git remote get-url origin >/dev/null 2>&1; then
  echo "RESET WARN: origin remote 丢失"
fi

if [ -z "$(git status --porcelain)" ]; then
  echo "RESET OK"
else
  echo "RESET DIRTY"
  exit 1
fi
