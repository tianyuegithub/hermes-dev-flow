#!/usr/bin/env python3
"""
dashboard.py — Dev-Flow 仪表盘 (Apple Design) + SSE 实时推送
用法: python3 dashboard.py [--port 28100]
"""
import os, json, http.server, sys, subprocess, time, socket
from urllib.parse import urlparse
from datetime import datetime

TASKS_DIR = os.path.expanduser("~/Codes/ai-dev-flow/.hermes/tasks")
REDIS_HOST = "192.168.31.173"
REDIS_PORT = 32319
HTML_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard.html")

def _load_html():
    if os.path.exists(HTML_PATH):
        with open(HTML_PATH) as f:
            return f.read()
    return "<h1>dashboard.html not found</h1>"

class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            self._respond(200, "text/html", _load_html())
        elif path == "/api/state":
            state = {"tasks": self._get_tasks(), "pods": self._get_pods()}
            self._respond(200, "application/json", json.dumps(state, ensure_ascii=False))
        elif path == "/api/events":
            self._handle_sse()
        else:
            self._respond(404, "text/plain", "Not Found")

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/api/create":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
            result = self._create_task(body.get("goal", ""))
            self._respond(200, "application/json", json.dumps(result, ensure_ascii=False))
        else:
            self._respond(404, "text/plain", "Not Found")

    def _respond(self, code, ct, body):
        self.send_response(code)
        self.send_header("Content-Type", ct + "; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body.encode())

    def _get_tasks(self):
        if not os.path.exists(TASKS_DIR): return []
        tasks = []
        for tid in sorted(os.listdir(TASKS_DIR)):
            sp = os.path.join(TASKS_DIR, tid, "state.json")
            if os.path.exists(sp):
                with open(sp) as f:
                    d = json.load(f)
                tasks.append({"id": d.get("task_id", tid), "status": d.get("status", "?"),
                              "worker": d.get("worker", "-"), "task_type": d.get("task_type", "?")})
        return tasks

    def _get_pods(self):
        try:
            result = subprocess.run(
                ["kubectl", "get", "pods", "-n", "dev-flow", "-l", "app=dev-flow-worker",
                 "-o", "json"], capture_output=True, text=True, timeout=5)
            if result.returncode != 0: return []
            pods = json.loads(result.stdout)
            return [{"name": p["metadata"]["name"], "status": p["status"]["phase"]}
                    for p in pods.get("items", [])]
        except Exception:
            return []

    def _create_task(self, goal):
        if not goal:
            return {"error": "goal is required"}
        task_id = f"task-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        task_dir = os.path.join(TASKS_DIR, task_id)
        os.makedirs(task_dir, exist_ok=True)

        input_data = {
            "task_id": task_id, "task_type": "feature",
            "repo_url": "ssh://git@192.168.31.7:30022/datavdl/deer-flow.git",
            "goal": goal, "acceptance": [], "constraints": {"forbidden": ["禁止改 main", "禁止 force push"]},
            "budget": {"max_iterations": 12},
        }
        with open(os.path.join(task_dir, "input.json"), "w") as f:
            json.dump(input_data, f, ensure_ascii=False, indent=2)

        state = {"task_id": task_id, "task_type": "feature", "status": "CREATED",
                 "branch": f"dev-flow/{task_id}",
                 "created_at": datetime.now().isoformat(), "gates": [], "worker": "claude",
                 "session_id": None, "evidence": {}, "escalation": None}
        with open(os.path.join(task_dir, "state.json"), "w") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)

        return {"task_id": task_id, "status": "CREATED"}

    def _handle_sse(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        last = ""
        for _ in range(120):
            tasks = self._get_tasks()
            snap = json.dumps(tasks, ensure_ascii=False)
            if snap != last:
                data = json.dumps({"type": "state", "tasks": tasks}, ensure_ascii=False)
                self.wfile.write(f"data: {data}\n\n".encode())
                self.wfile.flush()
                last = snap
            time.sleep(1)

    def log_message(self, *args): pass

if __name__ == "__main__":
    port = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[1] == "--port" else 28100
    original_port = port
    while True:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.5)
            s.connect(("127.0.0.1", port))
            s.close()
            new_port = port + 1
            print(f"⚠️ 端口 {port} 已被占用，尝试 {new_port}")
            port = new_port
        except (socket.error, ConnectionRefusedError, OSError):
            break
    if port != original_port:
        print(f"📌 端口已切换: {original_port} → {port}")
    print(f"Dev-Flow 仪表盘: http://localhost:{port}")
    http.server.HTTPServer(("", port), Handler).serve_forever()
