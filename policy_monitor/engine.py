# -*- coding: utf-8 -*-
"""配置加载与主检查流程。"""
import json
import os
import time
from dataclasses import dataclass, field

from .fetcher import fetch, FetchError, NotFoundError
from .parser import parse_list_page
from .storage import Storage, now_str

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_DIR = os.path.join(BASE_DIR, "config")
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "policies.db")
REPORT_PATH = os.path.join(DATA_DIR, "report.html")


def load_json(name, default=None):
    path = os.path.join(CONFIG_DIR, name)
    if not os.path.exists(path):
        return default if default is not None else {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_settings():
    return load_json("settings.json", {})


def load_sources(enabled_only=True):
    data = load_json("sources.json", {"sources": []})
    srcs = data.get("sources", [])
    if enabled_only:
        srcs = [s for s in srcs if s.get("enabled")]
    return srcs


@dataclass
class SourceResult:
    source_id: str
    name: str
    ok: bool
    fetched: int = 0
    new_items: list = field(default_factory=list)
    updated_items: list = field(default_factory=list)
    gone_items: list = field(default_factory=list)
    error: str = ""


@dataclass
class CheckResult:
    run_at: str
    results: list = field(default_factory=list)
    total_new: int = 0
    total_updated: int = 0
    total_gone: int = 0
    errors: list = field(default_factory=list)
    new_titles: list = field(default_factory=list)


def check_all(storage: Storage, sources=None, settings=None, progress=None):
    """执行一轮完整检查。progress(msg) 用于 GUI/CLI 进度显示。"""
    settings = settings or load_settings()
    if sources is None:
        sources = load_sources()
    interval = float(settings.get("request_interval_seconds", 3))
    timeout = int(settings.get("request_timeout_seconds", 20))
    retries = int(settings.get("max_retries", 2))
    keyword = (settings.get("keyword_filter") or [None])[0]

    result = CheckResult(run_at=now_str())

    # 浏览器模式（反爬站点）复用同一个浏览器实例
    from .browser import BrowserSession, BrowserFetchError
    session_box = {"s": None}

    def get_html(src):
        if src.get("fetch_mode") == "browser":
            if session_box["s"] is None:
                session_box["s"] = BrowserSession(
                    wait_ms=int(settings.get("browser_wait_ms", 5000)))
                session_box["s"].__enter__()
            return session_box["s"].fetch(src["list_url"])
        return fetch(src["list_url"], timeout=timeout, max_retries=retries)

    try:
        for src in sources:
            name = src.get("name", src["id"])
            if progress:
                progress("正在检查：%s%s" % (name, "（浏览器模式）"
                                            if src.get("fetch_mode") == "browser" else ""))
            try:
                html = get_html(src)
                items = parse_list_page(html, src["list_url"], src)
                if not items:
                    raise FetchError("未解析到任何条目（页面可能被限流，或网站结构已变化）")
            except (FetchError, BrowserFetchError) as e:
                sr = SourceResult(source_id=src["id"], name=name, ok=False, error=str(e))
                result.results.append(sr)
                result.errors.append("%s：%s" % (name, e))
                storage.log_run(src["id"], 0, 0, 0, 0, error=str(e))
                if progress:
                    progress("  × %s（%s）" % (name, e))
                time.sleep(interval)
                continue
            except Exception as e:
                sr = SourceResult(source_id=src["id"], name=name, ok=False, error=str(e))
                result.results.append(sr)
                result.errors.append("%s：%s" % (name, e))
                storage.log_run(src["id"], 0, 0, 0, 0, error=str(e))
                time.sleep(interval)
                continue

            sr = SourceResult(source_id=src["id"], name=name, ok=True, fetched=len(items))
            for it in items:
                if keyword and keyword not in it["title"]:
                    continue
                r = storage.upsert(src, it)
                if r == "new":
                    sr.new_items.append(it)
                    result.new_titles.append((name, it["title"]))
                elif r == "updated":
                    sr.updated_items.append(it)
            storage.mark_misses(src["id"], [i["url"] for i in items])
            # 连续 2 次没出现的条目，先验证原文 URL 再判定下架：
            # 404 = 真下架；仍可访问 = 只是滚出列表首页（复位）；网络异常 = 不确定（复位）
            for cand in storage.gone_candidates(src["id"], threshold=2):
                try:
                    if src.get("fetch_mode") == "browser" and session_box["s"] is not None:
                        session_box["s"].fetch(cand["url"])
                    else:
                        fetch(cand["url"], timeout=15, max_retries=0)
                    storage.reset_miss(cand["id"])
                except NotFoundError:
                    storage.mark_gone(cand["id"])
                    sr.gone_items.append({"title": cand["title"], "url": cand["url"]})
                except Exception:
                    storage.reset_miss(cand["id"])
                time.sleep(interval)
            result.results.append(sr)
            result.total_new += len(sr.new_items)
            result.total_updated += len(sr.updated_items)
            result.total_gone += len(sr.gone_items)
            storage.log_run(src["id"], len(items), len(sr.new_items),
                            len(sr.updated_items), len(sr.gone_items))
            if progress:
                progress("  √ %s：抓取 %d 条，新增 %d，更新 %d，下架 %d"
                         % (name, len(items), len(sr.new_items), len(sr.updated_items),
                            len(sr.gone_items)))
            storage.commit()
            time.sleep(interval)
    finally:
        if session_box["s"] is not None:
            session_box["s"].__exit__()
    # Windows 弹窗提醒
    if settings.get("desktop_toast") and result.total_new > 0:
        try:
            from .notifier import windows_toast
            lines = ["%s %s" % (n, t) for n, t in result.new_titles[:5]]
            if result.total_new > 5:
                lines.append("……等共 %d 条" % result.total_new)
            windows_toast("政策监控：新增 %d 条" % result.total_new,
                          "\n".join(lines))
        except Exception:
            pass
    return result
