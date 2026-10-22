# -*- coding: utf-8 -*-
"""SQLite 存储与变更检测。"""
import os
import sqlite3
from datetime import datetime, timedelta

SCHEMA = """
CREATE TABLE IF NOT EXISTS policies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT UNIQUE NOT NULL,
    pub_date TEXT,
    category TEXT,
    level TEXT,
    region TEXT,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    miss_count INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'active',
    is_new INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_policies_source ON policies(source_id);
CREATE INDEX IF NOT EXISTS idx_policies_status ON policies(status);
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_at TEXT NOT NULL,
    source_id TEXT,
    fetched INTEGER DEFAULT 0,
    new_count INTEGER DEFAULT 0,
    updated_count INTEGER DEFAULT 0,
    gone_count INTEGER DEFAULT 0,
    error TEXT
);
"""

NOW_FMT = "%Y-%m-%d %H:%M:%S"


def now_str():
    return datetime.now().strftime(NOW_FMT)


class Storage:
    def __init__(self, db_path):
        d = os.path.dirname(os.path.abspath(db_path))
        if d:
            os.makedirs(d, exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self):
        try:
            self.conn.close()
        except Exception:
            pass

    # ---------- 写入 ----------
    def upsert(self, source, item, now=None):
        """返回 'new' / 'updated' / None。"""
        now = now or now_str()
        row = self.conn.execute(
            "SELECT * FROM policies WHERE url=?", (item["url"],)).fetchone()
        if row is None:
            self.conn.execute(
                "INSERT INTO policies(source_id,title,url,pub_date,category,level,region,"
                "first_seen,last_seen,miss_count,status,is_new) VALUES(?,?,?,?,?,?,?,?,?,0,'active',1)",
                (source["id"], item["title"], item["url"], item.get("pub_date"),
                 source.get("category", ""), source.get("level", ""),
                 source.get("region", ""), now, now))
            return "new"
        changed_title = row["title"] != item["title"]
        pub = item.get("pub_date") or row["pub_date"]
        self.conn.execute(
            "UPDATE policies SET last_seen=?, miss_count=0, status='active', title=?, pub_date=? WHERE url=?",
            (now, item["title"], pub, item["url"]))
        if changed_title and row["status"] == "active":
            return "updated"
        if row["status"] == "gone":
            return "updated"
        return None

    def mark_misses(self, source_id, seen_urls, now=None):
        """本次没出现的条目累计 miss（只累计，不判定下架）。"""
        rows = self.conn.execute(
            "SELECT id, url, miss_count FROM policies WHERE source_id=? AND status='active'",
            (source_id,)).fetchall()
        seen = set(seen_urls)
        for r in rows:
            if r["url"] in seen:
                continue
            self.conn.execute(
                "UPDATE policies SET miss_count=? WHERE id=?",
                (r["miss_count"] + 1, r["id"]))
        return []

    def gone_candidates(self, source_id, threshold=2):
        """连续 miss 达到阈值的在库条目，等待 URL 验证。"""
        return self.conn.execute(
            "SELECT id, url, title FROM policies WHERE source_id=? AND status='active' "
            "AND miss_count>=?", (source_id, threshold)).fetchall()

    def mark_gone(self, policy_id):
        self.conn.execute("UPDATE policies SET status='gone' WHERE id=?", (policy_id,))

    def reset_miss(self, policy_id):
        self.conn.execute("UPDATE policies SET miss_count=0 WHERE id=?", (policy_id,))

    def clear_new_flags(self):
        self.conn.execute("UPDATE policies SET is_new=0 WHERE is_new=1")
        self.conn.commit()

    def log_run(self, source_id, fetched, new_c, upd_c, gone_c, error=None):
        self.conn.execute(
            "INSERT INTO runs(run_at,source_id,fetched,new_count,updated_count,gone_count,error) "
            "VALUES(?,?,?,?,?,?,?)",
            (now_str(), source_id, fetched, new_c, upd_c, gone_c, error))
        self.conn.commit()

    # ---------- 查询 ----------
    def recent(self, days=7, keyword=None, source_id=None, limit=500):
        since = (datetime.now() - timedelta(days=days)).strftime(NOW_FMT)
        sql = ("SELECT * FROM policies WHERE status='active' AND first_seen>=? ")
        args = [since]
        if keyword:
            sql += "AND title LIKE ? "
            args.append("%" + keyword + "%")
        if source_id:
            sql += "AND source_id=? "
            args.append(source_id)
        sql += "ORDER BY first_seen DESC LIMIT ?"
        args.append(limit)
        return self.conn.execute(sql, args).fetchall()

    def last_run_time(self):
        r = self.conn.execute("SELECT MAX(run_at) AS t FROM runs").fetchone()
        return r["t"] if r else None

    def source_names(self):
        return {r["source_id"]: r["name"] for r in
                self.conn.execute("SELECT DISTINCT source_id, '' AS name FROM policies")}

    def stats(self):
        r = self.conn.execute(
            "SELECT COUNT(*) AS total, SUM(CASE WHEN is_new=1 THEN 1 ELSE 0 END) AS new_cnt "
            "FROM policies WHERE status='active'").fetchone()
        return {"total": r["total"] or 0, "new": r["new_cnt"] or 0}

    def commit(self):
        self.conn.commit()
