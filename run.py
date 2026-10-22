# -*- coding: utf-8 -*-
"""命令行入口。

用法：
  python run.py check          立即检查一次（可加 --no-push）
  python run.py daemon         常驻运行，每天按设定时间自动检查
  python run.py gui            打开桌面窗口
  python run.py report         生成 HTML 日报并打开
  python run.py sources        查看数据源列表与状态
  python run.py discover URL   探测一个新网站的政策列表结构
  python run.py testpush       发送一条测试推送
"""
import argparse
import os
import sys
import time
import webbrowser
from datetime import datetime, timedelta

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from policy_monitor.engine import (load_settings, load_sources, check_all,
                                   REPORT_PATH, DB_PATH)
from policy_monitor.notifier import push_result, push, build_message
from policy_monitor.report import write_report
from policy_monitor.storage import Storage


def cmd_check(args):
    settings = load_settings()
    storage = Storage(DB_PATH)
    result = check_all(storage, settings=settings,
                       progress=lambda m: print(m, flush=True))
    ok, msg, title, content = push_result(settings, result, storage)
    print("---- 推送：%s ----" % msg)
    if not args.no_push:
        pass
    if args.push:
        ok, msg, _, _ = push_result(settings, result, storage)
        print("推送结果：%s" % msg)
    names = {s["id"]: s.get("name", s["id"]) for s in load_sources(enabled_only=False)}
    path = write_report(storage, REPORT_PATH,
                        days=int(settings.get("report_days", 7)), source_names=names)
    print("日报已生成：%s" % path)
    if settings.get("open_report_after_check") or args.open:
        webbrowser.open(path)
    storage.close()
    return 0


def cmd_daemon(args):
    settings = load_settings()
    check_time = settings.get("check_time", "08:30")
    hh, mm = [int(x) for x in check_time.split(":")]
    print("守护模式已启动，每天 %02d:%02d 自动检查。按 Ctrl+C 退出。" % (hh, mm))
    while True:
        now = datetime.now()
        target = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        wait = (target - now).total_seconds()
        print("下次检查：%s（%.0f 分钟后）" % (target.strftime("%Y-%m-%d %H:%M"), wait / 60))
        time.sleep(wait)
        try:
            cmd_check(args)
        except Exception as e:
            print("检查失败：%s" % e)


def cmd_gui(args):
    from policy_monitor.gui import main
    main()


def cmd_report(args):
    settings = load_settings()
    storage = Storage(DB_PATH)
    names = {s["id"]: s.get("name", s["id"]) for s in load_sources(enabled_only=False)}
    path = write_report(storage, REPORT_PATH,
                        days=int(settings.get("report_days", 7)), source_names=names)
    print("日报已生成：%s" % path)
    webbrowser.open(path)
    storage.close()


def cmd_sources(args):
    all_src = load_sources(enabled_only=False)
    print("共 %d 个数据源：\n" % len(all_src))
    for s in all_src:
        flag = "启用" if s.get("enabled") else "停用"
        print("[%s] %s" % (flag, s.get("name", s["id"])))
        print("      %s" % s.get("list_url"))
        if s.get("note"):
            print("      备注：%s" % s["note"])
        print()


def cmd_discover(args):
    from policy_monitor.fetcher import fetch, FetchError
    from policy_monitor.parser import parse_list_page
    url = args.url
    print("正在抓取：%s" % url)
    try:
        html = fetch(url, timeout=25)
    except FetchError as e:
        print("抓取失败：%s" % e)
        return 1
    src = {"link_include": args.include, "link_exclude": args.exclude,
           "min_title_len": args.min_len, "max_items": args.max}
    items = parse_list_page(html, url, src)
    print("解析到 %d 条：\n" % len(items))
    for it in items:
        print("%-12s %s\n    %s" % (it["pub_date"] or "无日期", it["title"], it["url"]))
    print("\n把上面结果贴给我，或按 README 的格式把新源加进 config/sources.json。")
    return 0


def cmd_testpush(args):
    settings = load_settings()
    title = "政策监控 · 测试消息"
    content = "这是一条测试推送。如果你在微信里收到了它，说明推送配置正确。"
    ok, msg = push(settings, title, content)
    print(msg)
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description="政策监控工具")
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("check", help="立即检查一次")
    p.add_argument("--push", action="store_true", help="强制推送（默认按配置）")
    p.add_argument("--no-push", action="store_true", help="跳过推送")
    p.add_argument("--open", action="store_true", help="检查后打开日报")

    sub.add_parser("daemon", help="常驻，每天定时检查")
    sub.add_parser("gui", help="桌面窗口")
    sub.add_parser("report", help="生成并打开 HTML 日报")
    sub.add_parser("sources", help="查看数据源")

    p = sub.add_parser("discover", help="探测新网站")
    p.add_argument("url")
    p.add_argument("--include", default=None, help="链接必须包含的字符")
    p.add_argument("--exclude", default=None, help="链接不能包含的字符")
    p.add_argument("--min-len", type=int, default=8)
    p.add_argument("--max", type=int, default=30)

    sub.add_parser("testpush", help="发送测试推送")

    args = ap.parse_args()
    if args.cmd == "check":
        return cmd_check(args)
    if args.cmd == "daemon":
        return cmd_daemon(args)
    if args.cmd == "gui":
        return cmd_gui(args)
    if args.cmd == "report":
        return cmd_report(args)
    if args.cmd == "sources":
        return cmd_sources(args)
    if args.cmd == "discover":
        return cmd_discover(args)
    if args.cmd == "testpush":
        return cmd_testpush(args)
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
