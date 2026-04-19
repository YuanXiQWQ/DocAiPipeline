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
            except (OSError, sqlite3.Error):
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

CREATE TABLE IF NOT EXISTS templates (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL DEFAULT '',
    filename        TEXT NOT NULL DEFAULT '',
    file_path       TEXT NOT NULL DEFAULT '',
    types           TEXT NOT NULL DEFAULT '[]',
    default_for     TEXT NOT NULL DEFAULT '[]',
    sheet_names     TEXT NOT NULL DEFAULT '[]',
    size_bytes      INTEGER NOT NULL DEFAULT 0,
    builtin         INTEGER NOT NULL DEFAULT 0,
    imported_at     TEXT NOT NULL DEFAULT '',
    last_used_at    TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_tpl_builtin ON templates(builtin);
"""


def init_db() -> None:
    """建表 + 自动迁移旧 JSON 数据 + 注册内置模板（幂等）。"""
    conn = get_conn()
    conn.executescript(_SCHEMA_SQL)
    conn.commit()
    logger.info(f"SQLite 数据库已初始化: {db_path()}")
    _migrate_json_data(conn)
    _register_builtin_templates(conn)


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


# ------------------------------------------------------------------
# 内置模板自动注册
# ------------------------------------------------------------------

# 内置模板定义：(文件名, 显示名, 适用类型, 默认类型)
_BUILTIN_TEMPLATES: list[tuple[str, str, list[str], list[str]]] = [
    (
        "数据统计_模板.xlsx",
        "数据统计表",
        ["log_measurement", "log_output", "soak_pool", "slicing", "packing"],
        ["log_measurement", "log_output", "soak_pool", "slicing", "packing"],
    ),
]


def _builtin_models_dir() -> Path:
    """内置模板所在目录（兼容 PyInstaller 打包与开发模式）。"""
    import sys
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    else:
        base = Path(__file__).resolve().parent.parent  # ai-service/
    return base / "models"


def _register_builtin_templates(conn: sqlite3.Connection) -> None:
    """首次启动时将内置模板注册到 templates 表（幂等）。"""
    from datetime import datetime, timezone

    models_dir = _builtin_models_dir()
    now = datetime.now(timezone.utc).isoformat()

    for filename, display_name, types, default_for in _BUILTIN_TEMPLATES:
        filepath = models_dir / filename
        if not filepath.exists():
            logger.warning(f"内置模板文件不存在: {filepath}")
            continue

        # 检查是否已注册（按 builtin=1 且 filename 匹配）
        existing = conn.execute(
            "SELECT id FROM templates WHERE builtin = 1 AND filename = ?",
            (filename,),
        ).fetchone()
        if existing:
            # 更新文件路径（打包后路径可能变化）
            conn.execute(
                "UPDATE templates SET file_path = ? WHERE id = ?",
                (str(filepath), existing["id"]),
            )
            continue

        # 读取工作表名称
        sheet_names: list[str] = []
        try:
            import openpyxl
            wb = openpyxl.load_workbook(str(filepath), read_only=True, data_only=True)
            sheet_names = wb.sheetnames
            wb.close()
        except Exception as e:
            logger.warning(f"读取内置模板工作表失败: {e}")

        tpl_id = f"builtin_{filename}"
        conn.execute(
            """INSERT INTO templates
               (id, name, filename, file_path, types, default_for,
                sheet_names, size_bytes, builtin, imported_at, last_used_at)
               VALUES (?,?,?,?,?,?,?,?,1,?,?)""",
            (
                tpl_id,
                display_name,
                filename,
                str(filepath),
                json.dumps(types, ensure_ascii=False),
                json.dumps(default_for, ensure_ascii=False),
                json.dumps(sheet_names, ensure_ascii=False),
                filepath.stat().st_size,
                now,
                "",
            ),
        )
        logger.info(f"已注册内置模板: {display_name} ({filename})")

    conn.commit()
