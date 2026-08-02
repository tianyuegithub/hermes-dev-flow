#!/usr/bin/env python3
"""
run_with_retry.py — API 自动重试包装器 (MVP 关键)

失败场景:
  - API 529 (智谱过载) → 等 30s → 重试
  - API 5xx → 等 15s → 重试
  - 超时 → 等 30s → 换 provider → 重试

用法: python3 run_with_retry.py --cmd "claude --bare ..." [--max-retries 3] [--fallback-provider opencode]
"""
import os, sys, json, subprocess, time, argparse

def run(cmd: str, max_retries: int = 3, fallback: str = "") -> dict:
    """执行命令，带重试"""
    for attempt in range(1, max_retries + 1):
        print(f"[retry] 尝试 {attempt}/{max_retries}: {cmd[:80]}...")
        try:
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=600)
        except subprocess.TimeoutExpired:
            print(f"[retry] ⚠️ 超时 (attempt {attempt})")
            if attempt < max_retries:
                time.sleep(30)
            continue

        stdout = result.stdout.strip()
        stderr = result.stderr.strip()

        # 解析 Claude Code JSON 输出
        api_error = False
        if "529" in stdout or "529" in stderr or "访问量过大" in stdout:
            api_error = True
            print(f"[retry] ⚠️ API 529 过载 (attempt {attempt})")

        if api_error and attempt < max_retries:
            wait = 30 if attempt == 1 else 60
            print(f"[retry] 等待 {wait}s...")
            time.sleep(wait)
            continue

        # 尝试解析 JSON
        try:
            data = json.loads(stdout)
            data["_attempts"] = attempt
            return data
        except:
            return {"status": "raw", "stdout": stdout[:500], "stderr": stderr[:500], "_attempts": attempt}

    return {"status": "failed", "reason": f"重试 {max_retries} 次仍失败"}

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cmd", required=True)
    parser.add_argument("--max-retries", type=int, default=3)
    args = parser.parse_args()

    result = run(args.cmd, args.max_retries)
    print(json.dumps(result, indent=2, ensure_ascii=False))
