"""SQLite 数据库管理：schema 定义、连接管理、JSON 旧数据自动迁移。

数据库文件：output/docai.db
首次启动时自动建表，并导入已有的 JSON 数据。
"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

from loguru import logger

from app.config import settings

# ------------------------------------------------------------------
# 连接管理（线程安全）
# ------------------------------------------------------------------

_local = threading.local()
_all_conns: list[sqlite3.Connection] = []
_all_conns_lock = threading.Lock()


def db_path() -> Path:
    d = Path(settings.output_dir)
    d.mkdir(parents=True, exist_ok=True)
    return d / "docai.db"


def get_conn() -> sqlite3.Connection:
    """获取当前线程的 SQLite 连接（懒加载）。"""
    existing = getattr(_local, "conn", None)
    if existing is not None:
        return existing  # type: ignore[return-value]
    conn = sqlite3.connect(str(db_path()), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    _local.conn = conn
    with _all_conns_lock:
        _all_conns.append(conn)
    return conn


def close_all() -> None:
    """关闭所有线程创建的 SQLite 连接，释放文件锁。"""
    with _all_conns_lock:
        for conn in _all_conns:
            try:
                conn.close()
            except Exception:
                pass
        _all_conns.clear()
    _local.conn = None
    logger.info("所有 SQLite 连接已关闭")


# ------------------------------------------------------------------
# Schema
# ------------------------------------------------------------------

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS summary_entries (
    id              TEXT PRIMARY KEY,
    source          TEXT NOT NULL DEFAULT 'auto',
    history_id      TEXT NOT NULL DEFAULT '',
    filename        TEXT NOT NULL DEFAULT '',
    category        TEXT NOT NULL DEFAULT '',
    metric          TEXT NOT NULL DEFAULT '',
    date            TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL DEFAULT '',
    value           REAL NOT NULL DEFAULT 0.0,
    unit            TEXT NOT NULL DEFAULT '',
    batch_id        TEXT NOT NULL DEFAULT '',
    vehicle_plate   TEXT NOT NULL DEFAULT '',
    detail          TEXT NOT NULL DEFAULT '{}',
    deleted         INTEGER NOT NULL DEFAULT 0,
    deleted_at      TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_se_category ON summary_entries(category);
CREATE INDEX IF NOT EXISTS idx_se_date ON summary_entries(date);
CREATE INDEX IF NOT EXISTS idx_se_batch_id ON summary_entries(batch_id);
CREATE INDEX IF NOT EXISTS idx_se_deleted ON summary_entries(deleted);

CREATE TABLE IF NOT EXISTS entry_revisions (
    revision_id TEXT PRIMARY KEY,
    entry_id    TEXT NOT NULL,
    timestamp   TEXT NOT NULL DEFAULT '',
    author      TEXT NOT NULL DEFAULT 'system',
    changes     TEXT NOT NULL DEFAULT '{}',
    note        TEXT NOT NULL DEFAULT '',
    FOREIGN KEY (entry_id) REFERENCES summary_entries(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_er_entry ON entry_revisions(entry_id);

CREATE TABLE IF NOT EXISTS history_records (
    id              TEXT PRIMARY KEY,
    timestamp       TEXT NOT NULL DEFAULT '',
    doc_type        TEXT NOT NULL DEFAULT '',
    filename        TEXT NOT NULL DEFAULT '',
    pages           INTEGER NOT NULL DEFAULT 0,
    record_count    INTEGER NOT NULL DEFAULT 0,
    warnings        TEXT NOT NULL DEFAULT '[]',
    results         TEXT NOT NULL DEFAULT '[]',
    filled          INTEGER NOT NULL DEFAULT 0,
    fill_filename   TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_hr_doc_type ON history_records(doc_type);
CREATE INDEX IF NOT EXISTS idx_hr_timestamp ON history_records(timestamp);
"""


def init_db() -> None:
    """建表 + 自动迁移旧 JSON 数据（幂等）。"""
    conn = get_conn()
    conn.executescript(_SCHEMA_SQL)
    conn.commit()
    logger.info(f"SQLite 数据库已初始化: {db_path()}")
    _migrate_json_data(conn)


# ------------------------------------------------------------------
# 旧 JSON → SQLite 自动迁移
# ------------------------------------------------------------------


def _migrate_json_data(conn: sqlite3.Connection) -> None:
    """将旧 JSON 文件数据导入 SQLite（仅在表为空时执行）。"""
    _migrate_summary_entries(conn)
    _migrate_history_records(conn)


def _migrate_summary_entries(conn: sqlite3.Connection) -> None:
    """迁移 summary_entries.json → summary_entries + entry_revisions 表。"""
    count = conn.execute("SELECT COUNT(*) FROM summary_entries").fetchone()[0]
    if count > 0:
        return  # 已有数据，跳过

    json_path = Path(settings.output_dir) / "summary_entries.json"
    if not json_path.exists():
        return

    try:
        data = json.loads(json_path.read_text("utf-8"))
        if not isinstance(data, list):
            return
    except (json.JSONDecodeError, OSError):
        return

    inserted = 0
    for item in data:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        try:
            conn.execute(
                """INSERT OR IGNORE INTO summary_entries
                   (id, source, history_id, filename, category, metric,
                    date, created_at, value, unit, batch_id, vehicle_plate,
                    detail, deleted, deleted_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    item["id"],
                    item.get("source", "auto"),
                    item.get("history_id", ""),
                    item.get("filename", ""),
                    item.get("category", ""),
                    item.get("metric", ""),
                    item.get("date", ""),
                    item.get("created_at", ""),
                    float(item.get("value", 0)),
                    item.get("unit", ""),
                    item.get("batch_id", ""),
                    item.get("vehicle_plate", ""),
                    json.dumps(item.get("detail", {}), ensure_ascii=False),
                    1 if item.get("deleted") else 0,
                    item.get("deleted_at", ""),
                ),
            )
            # 迁移修订历史
            for rev in item.get("revisions", []):
                if not isinstance(rev, dict):
                    continue
                conn.execute(
                    """INSERT OR IGNORE INTO entry_revisions
                       (revision_id, entry_id, timestamp, author, changes, note)
                       VALUES (?,?,?,?,?,?)""",
                    (
                        rev.get("revision_id", ""),
                        item["id"],
                        rev.get("timestamp", ""),
                        rev.get("author", "system"),
                        json.dumps(rev.get("changes", {}), ensure_ascii=False),
                        rev.get("note", ""),
                    ),
                )
            inserted += 1
        except Exception as e:
            logger.warning(f"迁移 summary entry 失败: {item.get('id')}: {e}")

    conn.commit()
    if inserted:
        logger.info(f"已从 summary_entries.json 迁移 {inserted} 条记录到 SQLite")


def _migrate_history_records(conn: sqlite3.Connection) -> None:
    """迁移 history/*.json → history_records 表。"""
    count = conn.execute("SELECT COUNT(*) FROM history_records").fetchone()[0]
    if count > 0:
        return

    hdir = Path(settings.output_dir) / "history"
    if not hdir.exists():
        return

    inserted = 0
    for f in hdir.glob("*.json"):
        try:
            data = json.loads(f.read_text("utf-8"))
            if not isinstance(data, dict) or not data.get("id"):
                continue
            conn.execute(
                """INSERT OR IGNORE INTO history_records
                   (id, timestamp, doc_type, filename, pages, record_count,
                    warnings, results, filled, fill_filename)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    data["id"],
                    data.get("timestamp", ""),
                    data.get("doc_type", ""),
                    data.get("filename", ""),
                    int(data.get("pages", 0)),
                    int(data.get("record_count", 0)),
                    json.dumps(data.get("warnings", []), ensure_ascii=False),
                    json.dumps(data.get("results", []), ensure_ascii=False),
                    1 if data.get("filled") else 0,
                    data.get("fill_filename", ""),
                ),
            )
            inserted += 1
        except Exception as e:
            logger.warning(f"迁移 history 失败: {f.name}: {e}")

    conn.commit()
    if inserted:
        logger.info(f"已从 history/*.json 迁移 {inserted} 条记录到 SQLite")
