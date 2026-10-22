# -*- coding: utf-8 -*-
"""浏览器模式抓取（可选能力）。

用于有 JS 动态加密反爬的网站（国家卫健委、国家药监局等），
普通 HTTP 请求会被拦截（412 或返回验证页），用无头 Chromium 执行页面 JS 后即可正常读取。

一次性安装（约 170MB，只需装一次）：
    pip install playwright
    python -m playwright install chromium

未安装时，标记为 browser 模式的数据源会跳过并提示，不影响其他数据源。
"""
import time

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
LAUNCH_ARGS = ["--disable-blink-features=AutomationControlled", "--no-sandbox"]

# 瑞数类 WAF 验证页特征
CHALLENGE_MARKERS = ("$_ts", "$_ts.nsd")


class BrowserFetchError(Exception):
    pass


class BrowserSession:
    """一次检查中复用同一个浏览器实例，避免反复启动。"""

    def __init__(self, wait_ms=5000):
        self.wait_ms = wait_ms
        self._pw = None
        self._browser = None
        self._ctx = None

    def __enter__(self):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise BrowserFetchError(
                "未安装 Playwright。浏览器模式需要先安装："
                "pip install playwright，然后 python -m playwright install chromium")
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=True, args=LAUNCH_ARGS)
        self._ctx = self._browser.new_context(
            user_agent=UA, viewport={"width": 1366, "height": 768}, locale="zh-CN")
        return self

    def __exit__(self, *exc):
        for closer in (lambda: self._ctx and self._ctx.close(),
                       lambda: self._browser and self._browser.close(),
                       lambda: self._pw and self._pw.stop()):
            try:
                closer()
            except Exception:
                pass

    def fetch(self, url, timeout=45000):
        if self._ctx is None:
            raise BrowserFetchError("浏览器会话未初始化")
        page = self._ctx.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=timeout)
            page.wait_for_timeout(self.wait_ms)
            html = page.content()
            # WAF 首访返回 JS 验证页时会自动跳转，多等一轮再取
            if any(m in html for m in CHALLENGE_MARKERS):
                page.wait_for_timeout(8000)
                html = page.content()
                if any(m in html for m in CHALLENGE_MARKERS):
                    raise BrowserFetchError("反爬验证未通过（仍在验证页）")
            return html
        except BrowserFetchError:
            raise
        except Exception as e:
            raise BrowserFetchError("浏览器抓取失败：%s" % str(e)[:120])
        finally:
            try:
                page.close()
            except Exception:
                pass
