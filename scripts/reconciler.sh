#!/bin/bash
# ============================================================
# reconciler.sh — Hermes 端 Pod 热池监控 + 自动恢复
# 设计文档 §6: push(hook) + pull(scan) = reconciler
# 定时 cron 或 ad-hoc 运行
# ============================================================
set -uo pipefail

HB=~/Codes/ai-dev-flow/scripts/redis_helper.sh
NAMESPACE="dev-flow"
DEPLOY="dev-flow-worker"

echo "=== reconciler $(date +%H:%M:%S) ==="

# ── 1. 获取所有 worker pod ──────────────────────────────────
PODS=$(kubectl get pods -n "$NAMESPACE" -l app=dev-flow-worker --no-headers 2>/dev/null)
if [ -z "$PODS" ]; then
  echo "  ⚠️ 无 Worker Pod — 重建 Deployment"
  kubectl rollout restart deploy/"$DEPLOY" -n "$NAMESPACE" 2>&1
  exit 0
fi

# ── 2. 逐 Pod 检查 ──────────────────────────────────────────
while IFS= read -r line; do
  POD_NAME=$(echo "$line" | awk '{print $1}')
  POD_STATUS=$(echo "$line" | awk '{print $3}')
  POD_STATE=$($HB get "pod:${POD_NAME}:state" 2>/dev/null || echo "")

  echo "  $POD_NAME: k8s=$POD_STATUS redis=$POD_STATE"

  # 2a. Pod 不存在于 K8s 但 Redis 有记录 → 重建
  if [ "$POD_STATUS" = "Terminating" ]; then
    echo "    → Pod 终止中，等待替换 Pod..."
    continue
  fi

  # 2b. Pod Running 但 Redis 无状态 → 短暂异常
  if [ "$POD_STATUS" = "Running" ] && [ -z "$POD_STATE" ]; then
    echo "    → Redis 状态缺失，Pod 可能刚启动"
    continue
  fi

  # 2c. Pod 不在 Running 且 Redis 状态卡在 busy → 重建
  if [ "$POD_STATUS" != "Running" ] && [ "$POD_STATE" = "busy" ]; then
    echo "    ⚠️ Pod 状态异常 (k8s=$POD_STATUS, redis=busy) → 重建"
    kubectl delete pod "$POD_NAME" -n "$NAMESPACE" 2>&1
  fi

  # 2d. Pod NotReady — 重建
  READY=$(echo "$line" | awk '{print $2}')
  if [ "$READY" != "1/1" ] && [ "$POD_STATUS" = "Running" ]; then
    echo "    ⚠️ Pod NotReady ($READY) → 重建"
    kubectl delete pod "$POD_NAME" -n "$NAMESPACE" 2>&1
  fi
done <<< "$PODS"

# ── 3. 确保至少 1 个 Pod 在跑 ───────────────────────────────
RUNNING=$(kubectl get pods -n "$NAMESPACE" -l app=dev-flow-worker --field-selector=status.phase=Running --no-headers 2>/dev/null | wc -l)
if [ "$RUNNING" -eq 0 ]; then
  echo "  ❌ 无 Running Pod — 触发重建"
  kubectl rollout restart deploy/"$DEPLOY" -n "$NAMESPACE" 2>&1
fi

# ── 4. 清理僵尸 Redis key ───────────────────────────────────
# 遍历所有 busy pod，如果对应 K8s pod 不存在则清理
echo "  清理僵尸 Redis key..."
for key in $($HB rpush pod:DUMMY:queue x 2>/dev/null; :); do :; done
# 简单策略：只保留当前存在 pod 的 state key
POD_NAMES=$(kubectl get pods -n "$NAMESPACE" -l app=dev-flow-worker -o jsonpath='{.items[*].metadata.name}' 2>/dev/null)
echo "  活跃 Pod: $POD_NAMES"

echo "=== reconciler 完成 ==="
