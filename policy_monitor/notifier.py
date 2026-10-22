# -*- coding: utf-8 -*-
"""微信推送：PushPlus / Server酱 / 企业微信机器人；Windows 弹窗提醒。"""
import json
import re
import subprocess
import urllib.request

from .storage import Storage


def _post_json(url, payload, timeout=15):
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={
        "Content-Type": "application/json",
        "User-Agent": "policy-monitor/1.0",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def build_message(result, max_items=30):
    """把一轮检查结果拼成微信消息文本。"""
    lines = []
    for sr in result.results:
        if not sr.ok:
            lines.append("【%s】检查失败：%s" % (sr.name, sr.error))
            continue
        if not (sr.new_items or sr.updated_items or sr.gone_items):
            continue
        lines.append("【%s】" % sr.name)
        for it in sr.new_items:
            d = it.get("pub_date") or ""
            lines.append("  • 新增 %s %s\n    %s" % (d, it["title"], it["url"]))
        for it in sr.updated_items:
            lines.append("  • 更新 %s" % it["title"])
        for it in sr.gone_items:
            lines.append("  • 下架 %s" % it["title"])
    if not lines:
        lines.append("本轮未发现新增或变化的政策。")
    head = "政策监控 %s：新增 %d，更新 %d，下架 %d" % (
        result.run_at[:10], result.total_new, result.total_updated, result.total_gone)
    return head, "\n".join(lines)


def windows_toast(title, text, timeout_ms=10000):
    """Windows 托盘弹窗提醒（用系统自带 PowerShell，无需第三方库）。"""
    safe_t = re.sub(r"[\"'`$]", "", title)[:60]
    safe_x = re.sub(r"[\"'`$]", "", text)[:200]
    ps = (
        "Add-Type -AssemblyName System.Windows.Forms;"
        "$n=New-Object System.Windows.Forms.NotifyIcon;"
        "$n.Icon=[System.Drawing.SystemIcons]::Information;"
        "$n.BalloonTipTitle='%s';$n.BalloonTipText='%s';$n.Visible=$true;"
        "$n.ShowBalloonTip(%d);Start-Sleep -Seconds 8;$n.Dispose()"
        % (safe_t, safe_x, timeout_ms)
    )
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps],
            timeout=30, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return True
    except Exception:
        return False


def push(settings, title, content):
    """按配置推送，返回 (是否发送, 说明)。"""
    p = settings.get("push", {})
    channel = (p.get("channel") or "none").lower()
    try:
        if channel == "pushplus":
            token = p.get("pushplus_token", "").strip()
            if not token:
                return False, "未填写 pushplus_token"
            _post_json("http://www.pushplus.plus/send",
                       {"token": token, "title": title, "content": content,
                        "template": "txt"})
            return True, "已通过 PushPlus 推送"
        if channel == "serverchan":
            key = p.get("serverchan_sendkey", "").strip()
            if not key:
                return False, "未填写 serverchan_sendkey"
            _post_json("https://sct.ftqq.com/%s.send" % key,
                       {"title": title, "desp": content})
            return True, "已通过 Server酱 推送"
        if channel == "wecom":
            hook = p.get("wecom_webhook", "").strip()
            if not hook:
                return False, "未填写 wecom_webhook"
            _post_json(hook, {"msgtype": "markdown",
                              "markdown": {"content": "**%s**\n%s" % (title, content)}})
            return True, "已通过企业微信机器人推送"
    except Exception as e:
        return False, "推送失败：%s" % e
    return False, "未配置推送（channel=none），结果已保存到本地"


def push_result(settings, result, storage: Storage = None):
    title, content = build_message(result)
    ok, msg = push(settings, title, content)
    if storage is not None:
        # 记录到本地日志文件，方便回溯
        try:
            log_dir = storage.conn.execute("PRAGMA database_list").fetchone()
            base = log_dir[2] if log_dir else "."
            path = base.replace("policies.db", "push_history.txt")
            with open(path, "a", encoding="utf-8") as f:
                f.write("==== %s ====\n%s\n%s\n\n" % (title, content, msg))
        except Exception:
            pass
    return ok, msg, title, content
