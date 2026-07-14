#!/usr/bin/env python3
"""
stream_worker.py — L0 本地实时观测：流式解析 Claude Code 输出

用法: python3 stream_worker.py <prompt_file> [--max-turns 300] [--max-budget 15]
"""
import json, sys, os, subprocess, time, threading
from datetime import datetime


def stream_claude(prompt: str, max_turns: int = 300, max_budget: float = 15.0, cwd: str = None):
    """流式调用 Claude Code，实时打印进度"""
    cmd = [
        "claude", "--bare", "-p", prompt,
        "--output-format", "stream-json",
        "--verbose",
        "--max-turns", str(max_turns),
        "--max-budget-usd", str(max_budget),
        "--dangerously-skip-permissions",
    ]

    print(f"[stream] 启动 Claude Code (turns={max_turns}, budget=${max_budget})")
    print(f"[stream] {'─' * 50}")

    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, cwd=cwd
    )

    events = []
    turn_count = 0
    tool_calls = []
    start_time = time.time()

    for line in proc.stdout:
        line = line.strip()
        if not line:
            continue

        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue

        events.append(event)
        etype = event.get("type", "")

        # ── 系统事件 ──
        if etype == "system":
            sub = event.get("event", {})
            if sub.get("type") == "api_retry":
                attempt = sub.get("attempt", "?")
                print(f"  ⚠️  API 重试 {attempt}")

        # ── assistant 事件（AI 思考/工具调用） ──
        elif etype == "assistant":
            sub = event.get("event", {})
            msg = sub.get("message", {})
            content = msg.get("content", [])

            for block in content:
                if block.get("type") == "text":
                    text = block.get("text", "")[:100]
                    if text.strip():
                        print(f"  💭 {text}")

                elif block.get("type") == "tool_use":
                    tool_name = block.get("name", "?")
                    tool_input = block.get("input", {})
                    turn_count += 1

                    # 工具调用详情
                    if tool_name == "Read":
                        path = tool_input.get("file_path", "?")
                        fname = os.path.basename(path)
                        print(f"  📖 [{turn_count}] Read: {fname}")

                    elif tool_name == "Write":
                        path = tool_input.get("file_path", "?")
                        fname = os.path.basename(path)
                        print(f"  ✏️ [{turn_count}] Write: {fname}")

                    elif tool_name == "Edit":
                        path = tool_input.get("file_path", "?")
                        fname = os.path.basename(path)
                        print(f"  🔧 [{turn_count}] Edit: {fname}")

                    elif tool_name == "Bash":
                        cmd_str = tool_input.get("command", "?")[:60]
                        print(f"  ⚡ [{turn_count}] Bash: {cmd_str}")

                    else:
                        print(f"  🔧 [{turn_count}] {tool_name}")

                    tool_calls.append({
                        "turn": turn_count,
                        "tool": tool_name,
                        "input_preview": str(tool_input)[:100],
                    })

        # ── 最终结果 ──
        elif etype == "result":
            sub = event.get("event", {})
            result = sub.get("result", "")
            subtype = sub.get("subtype", "?")
            cost = sub.get("total_cost_usd", 0)
            session_id = sub.get("session_id", "")
            num_turns = sub.get("num_turns", turn_count)

            elapsed = time.time() - start_time
            print(f"  {'─' * 50}")
            print(f"  ✅ 完成: {subtype}")
            print(f"  ⏱  耗时: {elapsed:.1f}s")
            print(f"  🔁 turns: {num_turns}")
            print(f"  💰 成本: ${cost:.4f}")
            print(f"  🔧 工具调用: {len(tool_calls)} 次")
            print(f"  📝 结果: {result[:150]}")

            return {
                "subtype": subtype,
                "num_turns": num_turns,
                "total_cost_usd": cost,
                "session_id": session_id,
                "result": result,
                "tool_calls": tool_calls,
                "elapsed": elapsed,
                "raw_events": events,
            }

    # 进程结束但无 result 事件
    proc.wait()
    elapsed = time.time() - start_time
    print(f"  ❌ 进程结束，无 result (exit={proc.returncode}, {elapsed:.1f}s)")

    return {
        "subtype": "error",
        "num_turns": turn_count,
        "total_cost_usd": 0,
        "result": "",
        "tool_calls": tool_calls,
        "elapsed": elapsed,
        "raw_events": events,
    }


if __name__ == "__main__":
    prompt_file = sys.argv[1]
    max_turns = 300
    max_budget = 15.0
    cwd = None

    for i, arg in enumerate(sys.argv[2:], 2):
        if arg == "--max-turns" and i + 1 < len(sys.argv):
            max_turns = int(sys.argv[i + 1])
        elif arg == "--max-budget" and i + 1 < len(sys.argv):
            max_budget = float(sys.argv[i + 1])
        elif arg == "--cwd" and i + 1 < len(sys.argv):
            cwd = sys.argv[i + 1]

    with open(prompt_file) as f:
        prompt = f.read()

    result = stream_claude(prompt, max_turns, max_budget, cwd)

    # 保存原始输出
    output_path = prompt_file.replace("prompt.txt", "claude-raw.json")
    with open(output_path, "w") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n[stream] 原始输出: {output_path}")
