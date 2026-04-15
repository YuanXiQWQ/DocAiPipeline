"""数据汇总明细存储：支持编辑、软删除、历史追溯。

每条明细行（SummaryEntry）对应一个可量化的数据点，如一票进口单据、
一批入库原木、一次入池操作等。所有编辑以追加方式记录修订历史，不丢失任何痕迹。

存储后端：SQLite（output/docai.db — summary_entries + entry_revisions 表）。
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

from loguru import logger
from pydantic import BaseModel, Field

from app.db import get_conn


# ------------------------------------------------------------------
# 数据模型（保持不变，供 router / writer 引用）
# ------------------------------------------------------------------


class EntryRevision(BaseModel):
    """一次修订记录。"""
    revision_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:8])
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    author: str = "system"  # "system" 或 "user"
    changes: dict[str, Any] = {}  # {"field": {"old": ..., "new": ...}}
    note: str = ""  # 修订说明


class SummaryEntry(BaseModel):
    """单条汇总明细行。"""
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    # 来源追溯
    source: str = "auto"  # "auto"（系统识别）| "manual"（手动录入）
    history_id: str = ""  # 关联的处理历史记录 ID（auto 来源时）
    filename: str = ""  # 来源文件名
    # 分类
    category: str = ""  # 大类：import / log_inbound / log_outbound / soak_pool / slicing / packing
    metric: str = ""  # 指标 key，如 "total_amount_eur", "inbound_m3" 等
    # 日期
    date: str = ""  # YYYY-MM-DD，业务日期（文档中的日期或手动填写）
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    # 数值
    value: float = 0.0  # 数值
    unit: str = ""  # 单位：EUR / m³ / 根 / 包 / 片 / m²
    # 批次 / 车牌（顶级字段，便于筛选与展示）
    batch_id: str = ""  # 入池批次号 / 检尺批次号 / 上机批号等
    vehicle_plate: str = ""  # 车牌号（检尺单特有）
    # 附加信息（原始数据快照，便于详情展示）
    detail: dict[str, Any] = {}  # 如 {supplier, entries_count, ...}
    # 状态
    deleted: bool = False  # 软删除标记
    deleted_at: str = ""  # 软删除时间
    # 修订历史
    revisions: list[EntryRevision] = []


# ------------------------------------------------------------------
# 内部工具
# ------------------------------------------------------------------


def _row_to_entry(row: Any) -> SummaryEntry:
    """将 sqlite3.Row 转为 SummaryEntry（含修订历史）。"""
    d = dict(row)
    d["detail"] = json.loads(d.get("detail") or "{}")
    d["deleted"] = bool(d.get("deleted"))
    # 加载修订历史
    conn = get_conn()
    revs = conn.execute(
        "SELECT * FROM entry_revisions WHERE entry_id=? ORDER BY timestamp",
        (d["id"],),
    ).fetchall()
    d["revisions"] = [
        {
            "revision_id": r["revision_id"],
            "timestamp": r["timestamp"],
            "author": r["author"],
            "changes": json.loads(r["changes"] or "{}"),
            "note": r["note"],
        }
        for r in revs
    ]
    return SummaryEntry.model_validate(d)


def _insert_entry(conn: Any, entry: SummaryEntry) -> None:
    """INSERT 一条 entry（不含 revisions）。"""
    conn.execute(
        """INSERT INTO summary_entries
           (id, source, history_id, filename, category, metric,
            date, created_at, value, unit, batch_id, vehicle_plate,
            detail, deleted, deleted_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            entry.id, entry.source, entry.history_id, entry.filename,
            entry.category, entry.metric, entry.date, entry.created_at,
            entry.value, entry.unit, entry.batch_id, entry.vehicle_plate,
            json.dumps(entry.detail, ensure_ascii=False),
            1 if entry.deleted else 0, entry.deleted_at,
        ),
    )


# ------------------------------------------------------------------
# 公共 API（签名保持不变）
# ------------------------------------------------------------------


def load_entries() -> list[SummaryEntry]:
    """加载并解析所有明细行。"""
    conn = get_conn()
    rows = conn.execute("SELECT * FROM summary_entries ORDER BY created_at DESC").fetchall()
    return [_row_to_entry(r) for r in rows]


def save_entry(entry: SummaryEntry) -> SummaryEntry:
    """新增一条明细行。"""
    conn = get_conn()
    _insert_entry(conn, entry)
    conn.commit()
    logger.info(f"汇总明细已新增: {entry.id} ({entry.category}/{entry.metric})")
    return entry


def save_entries_batch(new_entries: list[SummaryEntry]) -> int:
    """批量新增明细行。"""
    if not new_entries:
        return 0
    conn = get_conn()
    for e in new_entries:
        _insert_entry(conn, e)
    conn.commit()
    logger.info(f"汇总明细批量新增: {len(new_entries)} 条")
    return len(new_entries)


def update_entry(entry_id: str, updates: dict[str, Any], author: str = "user", note: str = "") -> SummaryEntry | None:
    """更新一条明细行，自动记录修订历史。"""
    conn = get_conn()
    row = conn.execute("SELECT * FROM summary_entries WHERE id=?", (entry_id,)).fetchone()
    if row is None:
        return None

    current = dict(row)
    changes: dict[str, Any] = {}
    set_clauses: list[str] = []
    params: list[Any] = []

    for k, v in updates.items():
        if k in ("id", "revisions", "created_at", "source", "history_id"):
            continue
        # detail 需要 JSON 序列化比较
        if k == "detail":
            old_val = json.loads(current.get("detail") or "{}")
            if old_val != v:
                changes[k] = {"old": old_val, "new": v}
                set_clauses.append("detail=?")
                params.append(json.dumps(v, ensure_ascii=False))
        elif k == "deleted":
            old_val = bool(current.get("deleted"))
            if old_val != v:
                changes[k] = {"old": old_val, "new": v}
                set_clauses.append("deleted=?")
                params.append(1 if v else 0)
        else:
            old_val = current.get(k)
            if old_val != v:
                changes[k] = {"old": old_val, "new": v}
                set_clauses.append(f"{k}=?")
                params.append(v)

    if set_clauses:
        params.append(entry_id)
        conn.execute(
            f"UPDATE summary_entries SET {', '.join(set_clauses)} WHERE id=?",
            params,
        )

    if changes:
        revision = EntryRevision(author=author, changes=changes, note=note)
        conn.execute(
            """INSERT INTO entry_revisions
               (revision_id, entry_id, timestamp, author, changes, note)
               VALUES (?,?,?,?,?,?)""",
            (
                revision.revision_id, entry_id, revision.timestamp,
                revision.author,
                json.dumps(revision.changes, ensure_ascii=False),
                revision.note,
            ),
        )

    conn.commit()
    logger.info(f"汇总明细已更新: {entry_id}, 变更: {list(changes.keys())}")
    return get_entry(entry_id)


def soft_delete_entry(entry_id: str, author: str = "user") -> SummaryEntry | None:
    """软删除一条明细行（保留数据，标记为已删除）。"""
    return update_entry(
        entry_id,
        {"deleted": True, "deleted_at": datetime.now().isoformat()},
        author=author,
        note="软删除",
    )


def restore_entry(entry_id: str, author: str = "user") -> SummaryEntry | None:
    """恢复一条软删除的明细行。"""
    return update_entry(
        entry_id,
        {"deleted": False, "deleted_at": ""},
        author=author,
        note="恢复",
    )


def get_entry(entry_id: str) -> SummaryEntry | None:
    """获取单条明细行。"""
    conn = get_conn()
    row = conn.execute("SELECT * FROM summary_entries WHERE id=?", (entry_id,)).fetchone()
    if row is None:
        return None
    return _row_to_entry(row)


def query_entries(
    *,
    date_from: str = "",
    date_to: str = "",
    category: str = "",
    metric: str = "",
    batch_id: str = "",
    include_deleted: bool = False,
    only_deleted: bool = False,
    source: str = "",
) -> list[SummaryEntry]:
    """按条件查询明细行。"""
    conn = get_conn()
    clauses: list[str] = []
    params: list[Any] = []

    # 删除过滤
    if only_deleted:
        clauses.append("deleted=1")
    elif not include_deleted:
        clauses.append("deleted=0")

    if date_from:
        clauses.append("date>=?")
        params.append(date_from)
    if date_to:
        clauses.append("date<=?")
        params.append(date_to)
    if category:
        clauses.append("category=?")
        params.append(category)
    if metric:
        clauses.append("metric=?")
        params.append(metric)
    if source:
        clauses.append("source=?")
        params.append(source)
    if batch_id:
        clauses.append("batch_id LIKE ?")
        params.append(f"%{batch_id}%")

    where = " AND ".join(clauses) if clauses else "1"
    rows = conn.execute(
        f"SELECT * FROM summary_entries WHERE {where} ORDER BY created_at DESC",
        params,
    ).fetchall()
    return [_row_to_entry(r) for r in rows]
