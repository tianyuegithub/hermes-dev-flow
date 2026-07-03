#!/bin/bash
# ============================================================
# reset.sh — Pod 任务完成后强制 reset（设计文档 §5 复用纪律）
# ============================================================
set -euo pipefail

cd /workspace/repo

git fetch origin
git checkout main
git branch -D $(git branch --list 'dev-flow/*') 2>/dev/null || true
git clean -fdx
git reset --hard origin/main

if [ -z "$(git status --porcelain)" ]; then
  echo "RESET OK"
else
  echo "RESET DIRTY"
  exit 1
fi
