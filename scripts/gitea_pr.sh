#!/bin/bash
# ============================================================
# gitea_pr.sh — 通过 Gitea API 创建 Pull Request
# ============================================================
# 用法: gitea_pr.sh <task_id> "<title>" <body_file> <head> [base]
# ============================================================
set -euo pipefail

TASK_ID="$1"; TITLE="$2"; BODY_FILE="$3"; HEAD="$4"; BASE="${5:-main}"

GITEA_URL="${GITEA_URL:-}"
GITEA_USER="${GITEA_USER:-}"
GITEA_PASS="${GITEA_PASS:-}"
GITEA_REPO="${GITEA_REPO:-}"
API_URL="${GITEA_URL}/api/v1/repos/${GITEA_REPO}/pulls"

echo "=== gitea_pr: ${TASK_ID} ==="
echo "  head: ${HEAD} → base: ${BASE}"

# 导出为环境变量供 Python 使用
export PR_TITLE="$TITLE"
export PR_TASK_ID="$TASK_ID"
export PR_BODY_FILE="$BODY_FILE"
export PR_HEAD="$HEAD"
export PR_BASE="$BASE"

# 用 Python 一次性完成：读 body + 拼 JSON + 调 API
python3 << PYEOF
import json, sys, os, urllib.request, base64

title = os.environ.get("PR_TITLE", "")
task_id = os.environ.get("PR_TASK_ID", "")
head = os.environ.get("PR_HEAD", "")
base = os.environ.get("PR_BASE", "main")
body_file = os.environ.get("PR_BODY_FILE", "")
gitea_url = os.environ.get("GITEA_URL", "http://192.168.31.7:30000")
gitea_user = os.environ.get("GITEA_USER", "")
gitea_pass = os.environ.get("GITEA_PASS", "")
gitea_repo = os.environ.get("GITEA_REPO", "datavdl/deer-flow")

# 读 body
with open(body_file) as f:
    body = f.read()

payload = json.dumps({
    "title": title,
    "body": body,
    "head": head,
    "base": base,
}).encode()

auth = base64.b64encode(f"{gitea_user}:{gitea_pass}".encode()).decode()
url = f"{gitea_url}/api/v1/repos/{gitea_repo}/pulls"

req = urllib.request.Request(url, data=payload, method="POST")
req.add_header("Content-Type", "application/json")
req.add_header("Authorization", f"Basic {auth}")

try:
    with urllib.request.urlopen(req) as resp:
        d = json.loads(resp.read())
        if "html_url" in d:
            print(f"✅ PR 已创建: {d['html_url']}")
            print(f"   编号: #{d['number']}")
            print(f"   状态: {d['state']}")
            # 输出 JSON 供上游解析
            print(json.dumps({"status":"ok","pr_url":d["html_url"],"number":d["number"]}))
        else:
            print(f"响应: {json.dumps(d, indent=2, ensure_ascii=False)}")
except urllib.error.HTTPError as e:
    err = json.loads(e.read())
    print(f"❌ HTTP {e.code}: {err.get('message', str(e))}")
    sys.exit(1)
PYEOF
