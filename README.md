# 政策监控工具（医保 / 卫健 / 药监）

每天自动检索国家级和省级医保局、卫健委、药监局网站的新政策，发现新增或变化时通过
**微信推送 + Windows 弹窗**提醒你，并生成 HTML 日报。

- 纯 Python 标准库实现，**不需要安装任何第三方库**
- 只读取政府网站公开页面，不登录、不留言、不下载附件
- 已内置 5 个实测可用的数据源（共收录 111 条政策），可随时扩充

## 一、安装（3 步）

1. 安装 Python 3.9 或更高版本：https://www.python.org/downloads/
   **安装时务必勾选 "Add Python to PATH"**（默认选项包含本工具需要的 tkinter）。
2. 把本文件夹（policy_monitor）拷贝到任意位置，例如 `D:\policy_monitor`。
3. 双击 `start_monitor.bat` 打开桌面窗口。

## 二、日常使用

| 操作 | 方法 |
|---|---|
| 打开桌面窗口 | 双击 `start_monitor.bat`，或运行 `python run.py gui` |
| 立即检查一次 | 窗口里点「立即检查」，或运行 `python run.py check` |
| 查看 HTML 日报 | 窗口里点「打开HTML日报」，或运行 `python run.py report` |
| 查看数据源列表 | `python run.py sources` |

窗口支持按来源筛选、按关键词搜索（如"集采""目录""价格"），**双击任意一行打开政策原文**。

## 三、设置每天自动检查（二选一）

### 方式 A：Windows 任务计划（推荐，不占内存）

1. Win+S 搜索「任务计划程序」并打开
2. 右侧「创建基本任务」→ 名称"政策监控" → 触发器选「每天」→ 时间设 08:30
3. 操作选「启动程序」：
   - 程序或脚本：`pythonw.exe` 的完整路径（如 `C:\...\Python313\pythonw.exe`）
   - 添加参数：`run.py check`
   - 起始于：本文件夹完整路径（如 `D:\policy_monitor`）
4. 完成。每天 08:30 自动检查，有新政策会弹窗 + 微信推送。

### 方式 B：常驻进程

运行 `python run.py daemon`，保持窗口不关，每天到点自动检查。

## 四、配置微信推送（可选，不配也能用）

编辑 `config/settings.json`，把 `push.channel` 改成以下任一，并填入对应 token：

| 通道 | 申请方式 | 配置项 |
|---|---|---|
| PushPlus（推荐，免费） | 微信搜"PushPlus"公众号 → 绑定 → 复制 token | `pushplus_token` |
| Server酱 Turbo | sct.ftqq.com 微信扫码登录 → 复制 SendKey | `serverchan_sendkey` |
| 企业微信机器人 | 群设置 → 群机器人 → 添加 → 复制 Webhook 地址 | `wecom_webhook` |

配好后运行 `python run.py testpush` 测试，微信能收到即成功。

## 五、数据源说明

当前**启用** 5 个源（`config/sources.json` 中 `enabled: true`）：

| 来源 | 地址 | 模式 |
|---|---|---|
| 国家医保局·通知公告（最重要，医保发文/集采/目录调整都在这） | nhsa.gov.cn/col/col109 | 普通 |
| 国家卫健委·规范性文件 | nhc.gov.cn/wjw/gfxwjj | 浏览器 |
| 国家药监局·政策文件 | nmpa.gov.cn/xxgk/fgwj | 浏览器 |
| 国家药监局·公告通告 | nmpa.gov.cn/xxgk/ggtg | 浏览器 |
| 北京市医保局·政策文件 | ybj.beijing.gov.cn | 普通 |
| 北京市卫健委·通知公告 | wjw.beijing.gov.cn | 普通 |
| 上海市医保局·最新政策 | ybj.sh.gov.cn/zxzc | 普通 |
| 广东省医保局·政策法规 | hsa.gd.gov.cn/zwgk/zcfg | 普通 |
| 广东省药监局·通知公告 | mpa.gd.gov.cn/xwdt/tzgg | 普通 |

> 「浏览器」模式的数据源（卫健委、药监局）需要额外安装 Playwright，见下面第六节；
> 不安装也能用，只是这 3 个源会跳过并提示，其余 6 个源不受影响。

当前**停用** 2 个源（`enabled: false`，原因写在每条 note 里）：

- 国家医保局·政策法规：该栏目已归档，页面只返回跳转壳，现行发文都在「通知公告」
- 江苏省医保局：列表由 JS 动态加载，静态抓取只能得到空壳

### 如何添加新数据源

1. 运行探测命令，看能否解析出政策列表：

   ```
   python run.py discover https://example.gov.cn/policy/ --include "/art/"
   ```

   （`--include` 是可选项：文章链接里都含有的字符，用来过滤导航链接）

2. 能看到「日期 + 标题 + 链接」后，把下面这段加进 `config/sources.json` 的
   `sources` 数组里（注意逗号）：

   ```json
   {
     "id": "xxx",
     "name": "XX省医保局·政策文件",
     "level": "省级",
     "category": "医保",
     "region": "XX",
     "list_url": "https://example.gov.cn/policy/",
     "enabled": true,
     "link_include": "/art/",
     "min_title_len": 8,
     "max_items": 30
   }
   ```

3. 运行 `python run.py check` 验证。

## 六、浏览器模式（覆盖卫健委/药监局必装）

国家卫健委、国家药监局的网站有 JS 动态加密反爬，普通请求会被拦截。
工具用无头 Chromium 执行页面 JS 来读取，需要一次性安装 Playwright（约 170MB）：

```
pip install playwright
python -m playwright install chromium
```

安装后这 3 个国家级源即可正常检查（本工具发布前已实测通过）。
**不安装也能用**——这 3 个源会显示"未安装 Playwright"并跳过，其余源不受影响。

> 提示：浏览器模式每次检查会多花 1-2 分钟（启动浏览器、等页面 JS 执行），属正常现象。
> 检查期间会看到一个 Chromium 窗口一闪而过，不要手动关它。

## 七、常见问题

**Q：某个来源检查失败/提示被限流？**
政府网站对频繁访问会返回限流页。工具已内置温和采集（每次请求间隔 3 秒、失败自动重试）。
每天只查一次基本不会触发；如果失败，当天晚点再跑一次 `python run.py check` 即可，
已抓到的数据不会重复。

**Q：提示"未解析到任何条目"？**
该网站可能改版或加强了反爬。用 `python run.py discover <网址>` 看一下现在能否解析，
再调整 `link_include` 等参数；搞不定就把这个源 `enabled` 改为 `false`，其余源不受影响。

**Q：提示"未安装 Playwright"？**
国家卫健委/药监局 3 个源需要浏览器模式，按上面第六节安装即可；
暂时不想装就把这 3 个源的 `enabled` 改为 `false`，或直接用其余 6 个源。

**Q：双击 start_monitor.bat 没反应/提示没有 tkinter？**
当前 Python 没装 tkinter。从 python.org 重新安装 Python（保持默认选项），
或直接使用 `python run.py report` 查看 HTML 日报，自动检查和微信推送不受影响。

**Q："下架"是怎么判定的？**
政策连续 2 次没出现在列表首页，工具会去访问原文链接确认：原文 404 才判定下架；
只是滚出列表首页（网站只显示最近若干条）不会误报。

**Q：数据存在哪里？**
`data/policies.db`（SQLite 数据库，可备份）；日报在 `data/report.html`；
推送历史在 `data/push_history.txt`。

**Q：想改每天检查时间？**
编辑 `config/settings.json` 里的 `check_time`（方式 B 立即生效，方式 A 需改任务计划）。

## 八、文件结构

```
policy_monitor/
├── start_monitor.bat      双击启动桌面窗口
├── run.py                 命令行入口
├── config/
│   ├── sources.json       数据源配置（增删改都在这里）
│   └── settings.json      检查时间、推送、过滤等设置
├── policy_monitor/
│   ├── engine.py          检查主流程
│   ├── fetcher.py         网页抓取（含反爬/限流识别）
│   ├── browser.py         浏览器模式抓取（Playwright，可选）
│   ├── parser.py          列表页解析
│   ├── storage.py         SQLite 存储与变更检测
│   ├── notifier.py        微信推送 + Windows 弹窗
│   ├── report.py          HTML 日报
│   └── gui.py             桌面窗口
└── data/                  运行生成：数据库、日报、日志
```

## 九、合规提醒

本工具只抓取政府网站公开的政策列表页（标题、日期、链接），不抓取正文、
不绕过任何登录或验证机制。请合理使用（每天一次），不要高频请求。
