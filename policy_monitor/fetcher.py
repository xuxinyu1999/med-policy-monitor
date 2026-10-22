# -*- coding: utf-8 -*-
"""网页抓取：温和、带重试、能识别反爬拦截页。"""
import gzip
import re
import time
import urllib.error
import urllib.request

DEFAULT_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

REDIRECT_RE = re.compile(r"window\.location(?:\.href)?\s*=\s*[\"']https?://")

# 政务网站常见 JS 动态加密 WAF 的页面特征（卫健委、药监局等）
WAF_MARKERS = ("$_ts", "$_ts.nsd", "rnmp", "content=\"CYmA1L", "arg1='*'")


class FetchError(Exception):
    pass


class NotFoundError(FetchError):
    """HTTP 404：文章页确实已不存在。"""
    pass


def _decode(raw: bytes, content_type: str) -> str:
    charset = "utf-8"
    if content_type:
        for part in content_type.split(";"):
            part = part.strip().lower()
            if part.startswith("charset="):
                charset = part.split("=", 1)[1].strip() or "utf-8"
    for enc in (charset, "utf-8", "gb18030"):
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="replace")


def _looks_like_waf(html: str) -> bool:
    return any(m in html for m in WAF_MARKERS)


def fetch(url: str, timeout: int = 20, max_retries: int = 2, retry_delay: float = 3.0) -> str:
    """抓取网页文本。失败抛 FetchError，信息里会说明原因。"""
    headers = {
        "User-Agent": DEFAULT_UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Accept-Encoding": "identity",
        "Connection": "keep-alive",
    }
    last_err = ""
    for attempt in range(max_retries + 1):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                ctype = resp.headers.get("Content-Type", "")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise NotFoundError("HTTP 404 页面不存在")
            if e.code in (412, 403):
                raise FetchError(f"被反爬拦截（HTTP {e.code}），该网站需要浏览器环境")
            last_err = f"HTTP {e.code}"
            if 500 <= e.code < 600 and attempt < max_retries:
                time.sleep(retry_delay * (attempt + 1))
                continue
            raise FetchError(f"请求失败 HTTP {e.code}")
        except Exception as e:  # 超时、DNS、连接重置等
            last_err = str(e)
            if attempt < max_retries:
                time.sleep(retry_delay * (attempt + 1))
                continue
            raise FetchError(f"网络错误：{e}")
        if raw[:2] == b"\x1f\x8b":
            try:
                raw = gzip.decompress(raw)
            except Exception:
                pass
        html = _decode(raw, ctype)
        if _looks_like_waf(html):
            raise FetchError("被反爬拦截（页面是 JS 加密验证页），该网站需要浏览器环境")
        # 政务站点被限流时返回跳转壳页面：含 location 跳转赋值且体积不大，或整体过小，视为异常并重试
        is_shell = (REDIRECT_RE.search(html) and len(html) < 20000) or len(html) < 3000
        if is_shell:
            last_err = "页面为跳转壳（%d 字符），疑似被限流" % len(html)
            if attempt < max_retries:
                time.sleep(retry_delay * (attempt + 1))
                continue
            raise FetchError(last_err)
        return html
    raise FetchError(f"抓取失败：{last_err}")
