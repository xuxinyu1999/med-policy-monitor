# -*- coding: utf-8 -*-
"""tkinter 桌面窗口：浏览、筛选、搜索政策，双击打开原文。

tkinter 是 Python 标准库的一部分，python.org 官方安装包默认包含；
若当前 Python 未安装 tkinter，main() 会给出提示并引导使用 HTML 日报。
"""
import threading
import webbrowser

from .engine import load_sources, load_settings, check_all, REPORT_PATH, DB_PATH
from .notifier import push_result
from .report import write_report
from .storage import Storage


class MonitorApp:
    def __init__(self, root, tk, ttk, messagebox):
        self.tk = tk
        self.ttk = ttk
        self.messagebox = messagebox
        self.root = root
        self.settings = load_settings()
        self.storage = Storage(DB_PATH)
        self.source_names = {s["id"]: s.get("name", s["id"])
                             for s in load_sources(enabled_only=False)}
        self.checking = False

        root.title("政策监控 · 医保/卫健/药监")
        root.geometry("1020x640")
        root.minsize(800, 480)

        top = ttk.Frame(root, padding=10)
        top.pack(fill="x")
        ttk.Label(top, text="来源:").pack(side="left")
        self.src_var = tk.StringVar(value="全部")
        self.src_box = ttk.Combobox(top, textvariable=self.src_var, width=22,
                                    state="readonly")
        self.src_box["values"] = ["全部"] + sorted(self.source_names.values())
        self.src_box.pack(side="left", padx=(4, 12))
        ttk.Label(top, text="搜索:").pack(side="left")
        self.kw_var = tk.StringVar()
        ttk.Entry(top, textvariable=self.kw_var, width=24).pack(side="left", padx=4)
        ttk.Button(top, text="查询", command=self.refresh).pack(side="left")
        ttk.Button(top, text="立即检查", command=self.run_check).pack(side="left",
                                                                      padx=12)
        ttk.Button(top, text="打开HTML日报", command=self.open_report).pack(side="left")

        cols = ("date", "source", "title", "url")
        self.tree = ttk.Treeview(root, columns=cols, show="headings")
        self.tree.heading("date", text="发布日期")
        self.tree.heading("source", text="来源")
        self.tree.heading("title", text="标题")
        self.tree.heading("url", text="链接")
        self.tree.column("date", width=90, anchor="center")
        self.tree.column("source", width=180)
        self.tree.column("title", width=560)
        self.tree.column("url", width=140)
        vsb = ttk.Scrollbar(root, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="top", fill="both", expand=True, padx=10, pady=(6, 0))
        vsb.place(relx=1.0, rely=0.0, relheight=0.9, anchor="ne")
        self.tree.bind("<Double-1>", self.on_open)
        self.tree.tag_configure("new", foreground="#1a7f37")

        self.status = ttk.Label(root, text="就绪", anchor="w", padding=8)
        self.status.pack(fill="x")
        self.refresh()

    # ---------- 数据 ----------
    def refresh(self):
        kw = self.kw_var.get().strip() or None
        src_name = self.src_var.get()
        src_id = None
        if src_name != "全部":
            for sid, name in self.source_names.items():
                if name == src_name:
                    src_id = sid
                    break
        rows = self.storage.recent(days=365, keyword=kw, source_id=src_id, limit=800)
        self.tree.delete(*self.tree.get_children())
        for r in rows:
            tags = ("new",) if r["is_new"] else ()
            self.tree.insert("", "end", values=(
                r["pub_date"] or "—",
                self.source_names.get(r["source_id"], r["source_id"]),
                r["title"], r["url"]), tags=tags)
        stats = self.storage.stats()
        self.status.config(text="在库 %d 条 ｜ 未读 %d 条 ｜ 上次检查：%s"
                           % (stats["total"], stats["new"],
                              self.storage.last_run_time() or "无"))

    def on_open(self, _event):
        sel = self.tree.selection()
        if not sel:
            return
        url = self.tree.item(sel[0], "values")[3]
        if url:
            webbrowser.open(url)

    # ---------- 检查 ----------
    def run_check(self):
        if self.checking:
            return
        self.checking = True
        self.status.config(text="正在检查，请稍候……")
        threading.Thread(target=self._check_thread, daemon=True).start()

    def _check_thread(self):
        try:
            result = check_all(self.storage, settings=self.settings,
                               progress=lambda m: self.root.after(
                                   0, self.status.config, {"text": m}))
            ok, msg, title, content = push_result(self.settings, result,
                                                  self.storage)
            write_report(self.storage, REPORT_PATH,
                         days=int(self.settings.get("report_days", 7)),
                         source_names=self.source_names)
            self.storage.clear_new_flags()
            summary = "检查完成：新增 %d，更新 %d，下架 %d。%s" % (
                result.total_new, result.total_updated, result.total_gone, msg)
            if result.errors:
                summary += "\n部分来源失败：" + "；".join(result.errors)
            self.root.after(0, self._after_check, summary)
        except Exception as e:
            self.root.after(0, self._after_check, "检查出错：%s" % e)

    def _after_check(self, summary):
        self.checking = False
        self.refresh()
        self.status.config(text=summary.split("\n")[0])
        if "新增 0" not in summary or "失败" in summary or "出错" in summary:
            self.messagebox.showinfo("政策监控", summary)

    def open_report(self):
        write_report(self.storage, REPORT_PATH,
                     days=int(self.settings.get("report_days", 7)),
                     source_names=self.source_names)
        webbrowser.open(REPORT_PATH)


def main():
    try:
        import tkinter as tk
        from tkinter import ttk, messagebox
    except ImportError:
        print("当前 Python 未安装 tkinter 模块，无法打开桌面窗口。")
        print("解决办法：从 python.org 重新安装 Python（默认选项包含 tkinter），")
        print("或直接使用 HTML 日报：python run.py report")
        return
    root = tk.Tk()
    MonitorApp(root, tk, ttk, messagebox)
    root.mainloop()


if __name__ == "__main__":
    main()
