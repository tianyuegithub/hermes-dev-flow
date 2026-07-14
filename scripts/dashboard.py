#!/usr/bin/env python3
"""
dashboard.py — Dev-Flow 仪表盘 + SSE 实时推送
用法: python3 dashboard.py [--port 8080]
"""
import os, json, http.server, sys, subprocess, time, threading
from urllib.parse import urlparse

TASKS_DIR = os.path.expanduser("~/.hermes/dev-flow/tasks")
REDIS_HOST = "192.168.31.173"
REDIS_PORT = 32319

HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><title>Dev-Flow 仪表盘</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root{--bg:#0f1420;--card:#161d2e;--ink:#e6ecf5;--sub:#9fb0c9;
--good:#38d39f;--warn:#ffb454;--bad:#ff6b6b;--accent:#4f9dff;
--mono:"SF Mono",Consolas,monospace}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font-family:-apple-system,"PingFang SC",sans-serif;padding:20px}
h1{font-size:20px}.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}
@media(max-width:800px){.grid{grid-template-columns:1fr}}
.card{background:var(--card);border-radius:12px;padding:16px;border:1px solid #2a3450}
.card h2{font-size:15px;margin:0 0 10px;color:var(--accent)}
.task{display:flex;justify-content:space-between;align-items:center;padding:8px 0;
border-bottom:1px solid#2a3450;font-size:13px}
.status{font-weight:600;font-size:12px;padding:2px 10px;border-radius:12px}
.s-done{background:#123a2b;color:var(--good)}.s-running{background:#33291a;color:var(--warn)}
.s-failed{background:#1f1414;color:var(--bad)}
.pod{padding:10px;border-radius:8px;background:#0c1120;margin:6px 0;font-size:13px}
.refresh{font-size:11px;color:var(--sub)}code{font-family:var(--mono);font-size:11px;color:#cfe0ff}
</style></head>
<body>
<h1>🔧 Dev-Flow 仪表盘</h1>
<div class="grid">
<div class="card" id="tasks"><h2>📋 任务列表</h2><div id="task-list">加载中...</div></div>
<div class="card" id="pods"><h2>🖥 Pod 状态</h2><div id="pod-list">加载中...</div></div>
</div>
<div class="refresh" id="updated">自动刷新 (5s)</div>
<script>
async function load(){try{let r=await fetch('/api/state');let d=await r.json();
let t=d.tasks||[],p=d.pods||[];
document.getElementById('task-list').innerHTML=t.length?t.map(t=>
`<div class="task"><span>${t.id||'?'}</span>
<span class="status s-${(t.status||'').toLowerCase()}">${t.status||'?'}</span></div>`).join(''):'暂无任务';
document.getElementById('pod-list').innerHTML=p.length?p.map(p=>
`<div class="pod">${p.name}<br><code>${p.status}</code></div>`).join(''):'暂无 Pod';
document.getElementById('updated').textContent='更新: '+new Date().toLocaleTimeString()}catch(e){}
}load();setInterval(load,5000);
</script></body></html>"""

class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            self._respond(200, "text/html", HTML)
        elif path == "/api/state":
            state = {"tasks": self._get_tasks(), "pods": self._get_pods()}
            self._respond(200, "application/json", json.dumps(state, ensure_ascii=False))

        elif path == "/api/events":
            self._handle_sse()

        elif path.startswith("/api/log/"):
            task_id = path.split("/")[-1]
            log = self._get_task_log(task_id)
            self._respond(200, "application/json", json.dumps({"log": log}, ensure_ascii=False))
        else:
            self._respond(404, "text/plain", "Not Found")

    def _respond(self, code, content_type, body):
        self.send_response(code)
        self.send_header("Content-Type", content_type + "; charset=utf-8")
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
                              "worker": d.get("worker", "-")})
        return tasks

    def _get_pods(self):
        result = subprocess.run(
            ["kubectl", "get", "pods", "-n", "dev-flow", "-l", "app=dev-flow-worker",
             "-o", "json"], capture_output=True, text=True, timeout=5)
        if result.returncode != 0: return []
        pods = json.loads(result.stdout)
        return [{"name": p["metadata"]["name"], "status": p["status"]["phase"]}
                for p in pods.get("items", [])]

    def _get_task_log(self, task_id):
        log_parts = []
        task_dir = os.path.join(TASKS_DIR, task_id)
        sp = os.path.join(task_dir, "state.json")
        if os.path.exists(sp):
            with open(sp) as f:
                d = json.load(f)
            log_parts.append(f"状态: {d.get('status','?')}  worker: {d.get('worker','-')}")
        return log_parts

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
    port = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[1] == "--port" else 8080
    print(f"Dev-Flow 仪表盘: http://localhost:{port}")
    http.server.HTTPServer(("", port), Handler).serve_forever()
