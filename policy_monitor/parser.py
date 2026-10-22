# -*- coding: utf-8 -*-
"""列表页解析：从 HTML 中提取 标题 / 链接 / 发布日期。

策略：
1. 用 html.parser 收集所有 <a> 标签及其后紧跟的文本；
2. 发布日期优先取链接附近文本中的 YYYY-MM-DD，其次从链接 URL 中推断；
3. 每个数据源可用 link_include / link_exclude 过滤链接。
"""
import re
from html.parser import HTMLParser
from urllib.parse import urljoin

DATE_RE = re.compile(r"(20\d{2})[-/年.](\d{1,2})[-/月.](\d{1,2})")
XML_SCRIPT_RE = re.compile(r"<script[^>]*type=['\"]text/xml['\"][^>]*>", re.I)
HREF_DATE_RES = [
    re.compile(r"/art/(20\d{2})/(\d{1,2})/(\d{1,2})/"),   # 国家医保局
    re.compile(r"/(20\d{2})(\d{2})(\d{2})/"),             # 上海 /qtwj/20261012/xxx.html
    re.compile(r"/t(20\d{2})(\d{2})(\d{2})"),             # 北京 t20260730_xxx.html
    re.compile(r"/(20\d{2})-(\d{1,2})-(\d{1,2})/"),       # 路径中带横线日期
]
SKIP_TITLES = ("首页", "更多", "下一页", "上一页", "尾页", "登录", "注册", "搜索",
               "打印", "关闭", "分享", "网站地图", "联系方式", "版权所有", "设为首页",
               "加入收藏", "English", "WAP版")


class _Collector(HTMLParser):
    """把 <a href title>标题</a> 和纯文本按出现顺序收集成 token 流。"""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tokens = []
        self._cur = None

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            d = dict(attrs)
            self._cur = [d.get("href", ""), d.get("title", ""), []]

    def handle_data(self, data):
        if self._cur is not None:
            self._cur[2].append(data)
        self.tokens.append(("t", data))

    def handle_endtag(self, tag):
        if tag == "a" and self._cur is not None:
            href, title_attr, segs = self._cur
            # 有些站点（如北京卫健委）PC/移动端各放一个 span，取最长的那个；
            # 有 title 属性时优先用 title（通常是完整标题）
            text = title_attr.strip() if title_attr else ""
            if not text:
                segs = [s.strip() for s in segs if s.strip()]
                text = max(segs, key=len) if segs else ""
            self.tokens.append(("a", href, text))
            self._cur = None


def _norm_date(y, m, d):
    return "%04d-%02d-%02d" % (int(y), int(m), int(d))


def _date_from_href(href: str):
    for rx in HREF_DATE_RES:
        m = rx.search(href)
        if m:
            try:
                return _norm_date(*m.groups())
            except Exception:
                pass
    return None


def parse_list_page(html: str, base_url: str, source: dict):
    """返回 [{title, url, pub_date}]，pub_date 可能为 None。"""
    # 汉Web 等 CMS 把列表数据放在 <script type="text/xml"> 里，解析器会把它当原始文本吞掉，先剥掉
    html = XML_SCRIPT_RE.sub("", html)
    # 列表还可能包在 <![CDATA[...]]> 里，同样先剥掉
    if "<![CDATA[" in html:
        html = html.replace("<![CDATA[", "").replace("]]>", "")
    c = _Collector()
    try:
        c.feed(html)
        c.close()
    except Exception:
        pass
    include = source.get("link_include")
    exclude = source.get("link_exclude")
    link_re = source.get("link_regex")
    link_re_c = None
    if link_re:
        try:
            link_re_c = re.compile(link_re)
        except re.error:
            link_re_c = None
    min_len = int(source.get("min_title_len", 8))
    max_items = int(source.get("max_items", 40))

    items, seen = [], set()
    for i, tok in enumerate(c.tokens):
        if tok[0] != "a":
            continue
        href, title = tok[1], tok[2]
        if not href or href.startswith(("javascript:", "#", "mailto:", "tel:")):
            continue
        if include and include not in href:
            continue
        if exclude and exclude in href:
            continue
        if link_re_c and not link_re_c.search(href):
            continue
        title = re.sub(r"\s+", " ", title).strip()
        if len(title) < min_len:
            continue
        if any(k in title for k in SKIP_TITLES) and len(title) < 15:
            continue
        url = urljoin(base_url, href)
        if url in seen:
            continue
        pub = None
        for j in range(i + 1, min(i + 8, len(c.tokens))):
            t2 = c.tokens[j]
            if t2[0] == "a":
                break
            m = DATE_RE.search(t2[1])
            if m:
                try:
                    pub = _norm_date(*m.groups())
                    break
                except Exception:
                    pass
        if not pub:
            pub = _date_from_href(href)
        seen.add(url)
        items.append({"title": title, "url": url, "pub_date": pub})
        if len(items) >= max_items:
            break
    return items
