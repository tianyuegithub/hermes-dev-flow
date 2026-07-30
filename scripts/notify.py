#!/usr/bin/env python3
"""
notify.py — 通知系统（Hermes 消息 + 邮件 + 企微）

用法:
  python3 notify.py task_done <task_id>
  python3 notify.py task_failed <task_id> <reason>
  python3 notify.py escalate <task_id> <message>

配置:
  ~/.hermes/dev-flow/config.yaml → notify 段
"""
import os, sys, json, subprocess, smtplib
from email.mime.text import MIMEText
from datetime import datetime


def load_config():
    config = {}
    config_path = os.path.expanduser("~/.hermes/dev-flow/config.yaml")
    try:
        with open(config_path) as f:
            import yaml
            config = yaml.safe_load(f)
    except:
        pass
    return config.get("notify", {})


def load_task(task_id: str) -> dict:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import paths
    try:
        with open(os.path.join(paths.task_dir(task_id), "state.json")) as f:
            return json.load(f)
    except:
        return {}


def notify_task_done(task_id: str):
    """任务完成 → Hermes 消息 + 邮件"""
    task = load_task(task_id)
    config = load_config()
    evidence = task.get("evidence", {})

    hermes_msg = f"[Dev-Flow] ✅ 任务完成\n  任务: {task_id}\n  commits: {evidence.get('commits', [])}\n  score: {evidence.get('score', '?')}"
    email_subject = f"Dev-Flow: {task_id} 完成"
    email_body = hermes_msg

    _deliver(hermes_msg, email_subject, email_body, config)


def notify_task_failed(task_id: str, reason: str = "未知"):
    task = load_task(task_id)
    config = load_config()

    hermes_msg = f"[Dev-Flow] ❌ 任务失败\n  任务: {task_id}\n  原因: {reason}"
    email_subject = f"Dev-Flow: {task_id} 失败"
    email_body = hermes_msg

    _deliver(hermes_msg, email_subject, email_body, config)


def notify_escalate(task_id: str, message: str):
    config = load_config()

    hermes_msg = f"[Dev-Flow] ⚠️ 需决策\n  任务: {task_id}\n  {message}"
    email_subject = f"Dev-Flow: {task_id} 需决策"
    email_body = hermes_msg

    _deliver(hermes_msg, email_subject, email_body, config)


def _deliver(hermes_msg: str, email_subject: str, email_body: str, config: dict):
    """投递通知：Hermes 消息（写文件）+ 邮件（SMTP）"""

    # 1) Hermes 消息 → 写通知文件（Hermes 技能读到后 clarify）
    notify_dir = os.path.expanduser("~/.hermes/dev-flow/notifications")
    os.makedirs(notify_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    with open(os.path.join(notify_dir, f"notify-{ts}.txt"), "w") as f:
        f.write(hermes_msg)
    print(f"  Hermes: 通知已写入 ~/.hermes/dev-flow/notifications/")

    # 2) 邮件（SMTP，可选）
    smtp_host = config.get("smtp_host")
    if smtp_host:
        try:
            msg = MIMEText(email_body, "plain", "utf-8")
            msg["Subject"] = email_subject
            msg["From"] = config.get("smtp_from", "dev-flow@localhost")
            msg["To"] = config.get("smtp_to", "")

            server = smtplib.SMTP(smtp_host, config.get("smtp_port", 25), timeout=10)
            if config.get("smtp_tls"):
                server.starttls()
            server.login(config.get("smtp_user", ""), config.get("smtp_pass", ""))
            server.send_message(msg)
            server.quit()
            print(f"  Email: 已发送至 {config.get('smtp_to', '(未配置)')}")
        except Exception as e:
            print(f"  Email: 发送失败 ({e})")


if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else "help"
    task_id = sys.argv[2] if len(sys.argv) > 2 else ""
    extra = sys.argv[3] if len(sys.argv) > 3 else ""

    if action == "task_done":
        notify_task_done(task_id)
    elif action == "task_failed":
        notify_task_failed(task_id, extra)
    elif action == "escalate":
        notify_escalate(task_id, extra)
    else:
        print("用法: python3 notify.py <task_done|task_failed|escalate> <task_id> [reason]")
