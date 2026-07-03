#!/usr/bin/env python3
"""
reconciler.py — Redis 孤儿任务清理器
=====================================
设计文档 §5.3: Pod 崩溃后自动清理残留的 running 状态，
防止任务永久卡死。

用法:
  reconciler.py [--dry-run] [--max-age-minutes 30]

逻辑:
  1. 扫描所有 status:* key，找到 status=running 的任务
  2. 检查对应 heartbeat 是否存活（TTL 未过期）
  3. 若无心跳，标记为 FAILED，清理 pod queue 中的残留
  4. --dry-run 模式只报告不修改

# 修改说明：Reconciler — Pod 崩溃恢复 | 修改时间：2026-07-03
"""

import json, os, sys, time
from datetime import datetime, timezone

# Redis 连接配置（优先环境变量，其次默认值）
REDIS_HOST = os.environ.get("REDIS_HOST", "192.168.31.173")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "32319"))

try:
    import redis
    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    r.ping()
except ImportError:
    print("需要 redis-py: pip install redis")
    sys.exit(1)
except Exception as e:
    print(f"Redis 连接失败: {e}")
    sys.exit(1)

DRY_RUN = "--dry-run" in sys.argv
MAX_AGE_MINUTES = 30

# 解析 --max-age-minutes
for i, arg in enumerate(sys.argv):
    if arg == "--max-age-minutes" and i + 1 < len(sys.argv):
        MAX_AGE_MINUTES = int(sys.argv[i + 1])


def scan_orphans():
    """扫描孤儿任务"""
    orphans = []
    now = time.time()

    # 1. 扫描所有 status:* key
    for key in r.scan_iter("status:*"):
        task_id = key.replace("status:", "")
        status = r.get(key)
        if status != "running":
            continue

        # 2. 检查心跳
        hb_key = f"heartbeat:{task_id}"
        hb_ttl = r.ttl(hb_key)
        has_heartbeat = hb_ttl > 0

        # 3. 检查是否有 pod 正在处理
        spec_key = f"spec:{task_id}"
        spec_data = r.get(spec_key)

        # 判断是否孤儿
        is_orphan = not has_heartbeat  # 心跳停了 = 无 pod 在工作

        if is_orphan:
            # 获取 spec 中的额外信息
            try:
                spec = json.loads(spec_data) if spec_data else {}
            except json.JSONDecodeError:
                spec = {}

            orphans.append({
                "task_id": task_id,
                "status": status,
                "heartbeat_ttl": hb_ttl,
                "worker": spec.get("worker", "unknown"),
                "goal": (spec.get("goal", "") or "")[:80],
                "has_spec": bool(spec_data),
            })

    return orphans


def report(orphans):
    """打印报告"""
    print(f"\n{'[DRY-RUN] ' if DRY_RUN else ''}Reconciler 扫描完成")
    print(f"  发现孤儿任务: {len(orphans)}")
    print()

    if not orphans:
        print("  ✅ 无孤儿任务，一切正常")
        return 0

    for o in orphans:
        print(f"  🔴 {o['task_id']}")
        print(f"     worker={o['worker']}, heartbeat_ttl={o['heartbeat_ttl']}")
        print(f"     goal: {o['goal'][:60]}...")
        print()

    return len(orphans)


def cleanup(orphans):
    """清理孤儿任务"""
    cleaned = 0
    for o in orphans:
        tid = o["task_id"]
        if DRY_RUN:
            print(f"  [DRY-RUN] 将标记 {tid} 为 FAILED")
            continue

        # 标记失败
        r.set(f"status:{tid}", "failed")

        # 清理队列中的残留（扫描所有 pod queue）
        for qkey in r.scan_iter("pod:*:queue"):
            r.lrem(qkey, 0, tid)

        # 写入清理原因到 output
        r.set(f"output:{tid}", json.dumps({
            "task_id": tid,
            "status": "failed",
            "reason": "reconciled: pod crash or heartbeat lost",
            "reconciled_at": datetime.now(timezone.utc).isoformat(),
        }, ensure_ascii=False))

        print(f"  ✅ 已清理: {tid}")
        cleaned += 1

    return cleaned


def main():
    orphans = scan_orphans()
    count = report(orphans)

    if count > 0 and not DRY_RUN:
        cleaned = cleanup(orphans)
        print(f"\n  清理完成: {cleaned}/{count}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
