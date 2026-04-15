"""处理历史记录持久化：每次文档处理完成后自动保存记录。

存储后端：SQLite（output/docai.db — history_records 表）。

提供查询接口：列表（分页/筛选）、单条详情、统计汇总。
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from loguru import logger
from pydantic import BaseModel

from app.db import get_conn


# ------------------------------------------------------------------
# 数据模型（保持不变）
# ------------------------------------------------------------------


class HistoryRecord(BaseModel):
    """单条处理历史记录。"""
    id: str  # 唯一标识（时间戳+哈希）
    timestamp: str  # ISO 8601 时间戳
    doc_type: str  # 文档类型
    filename: str  # 原始文件名
    pages: int  # 页数
    record_count: int  # 识别出的记录数
    warnings: list[str] = []  # 警告信息
    results: list[dict[str, Any]] = []  # 识别结果（完整 JSON）
    filled: bool = False  # 是否已填充到 Excel
    fill_filename: str = ""  # 填充后的 Excel 文件名


class HistorySummary(BaseModel):
    """历史记录摘要（列表用，不含完整 results）。"""
    id: str
    timestamp: str
    doc_type: str
    filename: str
    pages: int
    record_count: int
    filled: bool
    fill_filename: str


class HistoryStats(BaseModel):
    """历史数据统计。"""
    total_records: int  # 总处理次数
    by_doc_type: dict[str, int]  # 按类型统计
    total_pages_processed: int  # 总页数
    total_entries_extracted: int  # 总抽取记录数
    recent_7_days: int  # 近 7 天处理次数


# ------------------------------------------------------------------
# 内部工具
# ------------------------------------------------------------------


def _make_id(doc_type: str, filename: str) -> str:
    """生成唯一 ID：时间戳 + 文件哈希前6位。"""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    h = hashlib.md5(f"{filename}_{ts}".encode()).hexdigest()[:6]
    return f"{ts}_{doc_type}_{h}"


def _row_to_record(row: Any) -> HistoryRecord:
    """sqlite3.Row → HistoryRecord。"""
    d = dict(row)
    d["warnings"] = json.loads(d.get("warnings") or "[]")
    d["results"] = json.loads(d.get("results") or "[]")
    d["filled"] = bool(d.get("filled"))
    return HistoryRecord.model_validate(d)


def _row_to_summary(row: Any) -> HistorySummary:
    """sqlite3.Row → HistorySummary（不含 results）。"""
    d = dict(row)
    d["filled"] = bool(d.get("filled"))
    return HistorySummary(
        id=d["id"],
        timestamp=d.get("timestamp", ""),
        doc_type=d.get("doc_type", ""),
        filename=d.get("filename", ""),
        pages=d.get("pages", 0),
        record_count=d.get("record_count", 0),
        filled=d["filled"],
        fill_filename=d.get("fill_filename", ""),
    )


# ------------------------------------------------------------------
# 公共 API（签名保持不变）
# ------------------------------------------------------------------


def save_record(
        doc_type: str,
        filename: str,
        pages: int,
        results: list[dict[str, Any]],
        warnings: list[str] | None = None,
) -> HistoryRecord:
    """保存一条处理历史记录。"""
    record_id = _make_id(doc_type, filename)
    now = datetime.now().isoformat()
    record = HistoryRecord(
        id=record_id,
        timestamp=now,
        doc_type=doc_type,
        filename=filename,
        pages=pages,
        record_count=len(results),
        warnings=warnings or [],
        results=results,
    )
    conn = get_conn()
    conn.execute(
        """INSERT INTO history_records
           (id, timestamp, doc_type, filename, pages, record_count,
            warnings, results, filled, fill_filename)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (
            record.id, record.timestamp, record.doc_type, record.filename,
            record.pages, record.record_count,
            json.dumps(record.warnings, ensure_ascii=False),
            json.dumps(record.results, ensure_ascii=False),
            0, "",
        ),
    )
    conn.commit()
    logger.info(f"历史记录已保存: {record_id} ({doc_type}, {filename})")
    return record


def mark_filled(record_id: str, fill_filename: str) -> bool:
    """标记某条历史记录已填充到 Excel。"""
    conn = get_conn()
    cur = conn.execute(
        "UPDATE history_records SET filled=1, fill_filename=? WHERE id=?",
        (fill_filename, record_id),
    )
    conn.commit()
    return cur.rowcount > 0


def list_records(
        *,
        doc_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
        keyword: str = "",
) -> tuple[list[HistorySummary], int]:
    """列出历史记录（按时间倒序），返回 (列表, 总数)。"""
    conn = get_conn()
    clauses: list[str] = []
    params: list[Any] = []

    if doc_type:
        clauses.append("doc_type=?")
        params.append(doc_type)
    if keyword:
        clauses.append("(filename LIKE ? OR results LIKE ?)")
        kw = f"%{keyword}%"
        params.extend([kw, kw])

    where = " AND ".join(clauses) if clauses else "1"

    # 总数
    total = conn.execute(
        f"SELECT COUNT(*) FROM history_records WHERE {where}", params,
    ).fetchone()[0]

    # 分页
    rows = conn.execute(
        f"""SELECT id, timestamp, doc_type, filename, pages, record_count, filled, fill_filename
            FROM history_records WHERE {where}
            ORDER BY timestamp DESC LIMIT ? OFFSET ?""",
        params + [limit, offset],
    ).fetchall()

    summaries = [_row_to_summary(r) for r in rows]
    return summaries, total


def get_record(record_id: str) -> HistoryRecord | None:
    """获取单条历史记录详情。"""
    conn = get_conn()
    row = conn.execute("SELECT * FROM history_records WHERE id=?", (record_id,)).fetchone()
    if row is None:
        return None
    return _row_to_record(row)


def delete_record(record_id: str) -> bool:
    """删除单条历史记录。"""
    conn = get_conn()
    cur = conn.execute("DELETE FROM history_records WHERE id=?", (record_id,))
    conn.commit()
    if cur.rowcount > 0:
        logger.info(f"历史记录已删除: {record_id}")
        return True
    return False


def get_stats() -> HistoryStats:
    """获取历史数据统计。"""
    conn = get_conn()

    total = conn.execute("SELECT COUNT(*) FROM history_records").fetchone()[0]

    # 按类型统计
    by_type: dict[str, int] = {}
    for row in conn.execute("SELECT doc_type, COUNT(*) as cnt FROM history_records GROUP BY doc_type"):
        by_type[row["doc_type"]] = row["cnt"]

    agg = conn.execute(
        "SELECT COALESCE(SUM(pages),0) as tp, COALESCE(SUM(record_count),0) as te FROM history_records"
    ).fetchone()
    total_pages = agg["tp"]
    total_entries = agg["te"]

    # 近 7 天
    cutoff = datetime.now().timestamp() - 7 * 24 * 3600
    cutoff_iso = datetime.fromtimestamp(cutoff).isoformat()
    recent_7 = conn.execute(
        "SELECT COUNT(*) FROM history_records WHERE timestamp>=?", (cutoff_iso,)
    ).fetchone()[0]

    return HistoryStats(
        total_records=total,
        by_doc_type=by_type,
        total_pages_processed=total_pages,
        total_entries_extracted=total_entries,
        recent_7_days=recent_7,
    )
