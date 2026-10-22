# -*- coding: utf-8 -*-
"""HTML 日报生成。"""
import html
import os

from .storage import now_str


def _esc(s):
    return html.escape(str(s or ""))


def build_report(storage, days=7, title="政策监控日报", source_names=None):
    """生成 HTML 日报字符串。source_names: {source_id: 显示名}"""
    source_names = source_names or {}
    rows = storage.recent(days=days, limit=1000)
    by_source = {}
    for r in rows:
        by_source.setdefault(r["source_id"], []).append(r)

    stats = storage.stats()
    last_run = storage.last_run_time() or "尚未检查"

    parts = []
    parts.append("""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
body{{font-family:"Microsoft YaHei","PingFang SC",sans-serif;background:#f5f6f8;color:#1f2328;margin:0;padding:24px}}
.wrap{{max-width:960px;margin:0 auto}}
h1{{font-size:20px;font-weight:500}}
.meta{{color:#57606a;font-size:13px;margin:4px 0 20px}}
h2{{font-size:15px;font-weight:500;border-left:4px solid #0969da;padding-left:8px;margin-top:28px}}
table{{width:100%;border-collapse:collapse;background:#fff;border-radius:10px;overflow:hidden;font-size:13px}}
th{{background:#f0f3f6;text-align:left;padding:8px 10px;font-weight:500;color:#57606a}}
td{{padding:8px 10px;border-top:1px solid #eaeef2;vertical-align:top}}
a{{color:#0969da;text-decoration:none}}
a:hover{{text-decoration:underline}}
.badge{{display:inline-block;background:#ddf4e4;color:#1a7f37;border-radius:10px;padding:1px 8px;font-size:12px;margin-right:6px}}
.date{{color:#57606a;white-space:nowrap}}
.empty{{color:#57606a;font-size:13px;background:#fff;border:1px dashed #d8dee4;border-radius:10px;padding:16px}}
</style></head><body><div class="wrap">
<h1>{title}</h1>
<div class="meta">生成时间：{now} ｜ 上次检查：{lastrun} ｜ 近 {days} 天共 {total} 条在库政策，其中 {newcnt} 条未读</div>
""".format(title=_esc(title), now=_esc(now_str()), lastrun=_esc(last_run),
           days=days, total=stats["total"], newcnt=stats["new"]))

    if not rows:
        parts.append('<div class="empty">近 %d 天没有新增政策。可以先运行一次检查，或调大报告天数。</div>' % days)

    for sid, items in by_source.items():
        name = source_names.get(sid, sid)
        parts.append("<h2>%s（%d 条）</h2>" % (_esc(name), len(items)))
        parts.append("<table><tr><th>标题</th><th style=\"width:100px\">发布日期</th>"
                     "<th style=\"width:70px\">级别</th><th style=\"width:90px\">链接</th></tr>")
        for r in items:
            badge = ' <span class="badge">新</span>' if r["is_new"] else ""
            parts.append("<tr><td>%s%s</td><td class=\"date\">%s</td><td>%s</td>"
                         "<td><a href=\"%s\" target=\"_blank\">打开原文</a></td></tr>"
                         % (_esc(r["title"]), badge, _esc(r["pub_date"] or "—"),
                            _esc(r["level"]), _esc(r["url"])))
        parts.append("</table>")

    parts.append("</div></body></html>")
    return "\n".join(parts)


def write_report(storage, path, days=7, title="政策监控日报", source_names=None):
    content = build_report(storage, days=days, title=title, source_names=source_names)
    d = os.path.dirname(os.path.abspath(path))
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path
