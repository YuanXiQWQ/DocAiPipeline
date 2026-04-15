"""处理历史记录持久化：每次文档处理完成后自动保存记录。

存储格式：output/history/ 目录下的 JSON 文件，每条记录一个文件。
文件名格式：{timestamp}_{doc_type}_{filename_hash}.json

提供查询接口：列表（分页/筛选）、单条详情、统计汇总。
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger
from pydantic import BaseModel

from app.config import settings


# ------------------------------------------------------------------
# 数据模型
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
# 存储工具
# ------------------------------------------------------------------


def _history_dir() -> Path:
    """历史记录存储目录。"""
    d = Path(settings.output_dir) / "history"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _make_id(doc_type: str, filename: str) -> str:
    """生成唯一 ID：时间戳 + 文件哈希前6位。"""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    h = hashlib.md5(f"{filename}_{ts}".encode()).hexdigest()[:6]
    return f"{ts}_{doc_type}_{h}"


def save_record(
        doc_type: str,
        filename: str,
        pages: int,
        results: list[dict[str, Any]],
        warnings: list[str] | None = None,
) -> HistoryRecord:
    """保存一条处理历史记录。"""
    record_id = _make_id(doc_type, filename)
    record = HistoryRecord(
        id=record_id,
        timestamp=datetime.now().isoformat(),
        doc_type=doc_type,
        filename=filename,
        pages=pages,
        record_count=len(results),
        warnings=warnings or [],
        results=results,
    )
    path = _history_dir() / f"{record_id}.json"
    path.write_text(
        record.model_dump_json(indent=2),
        encoding="utf-8",
    )
    logger.info(f"历史记录已保存: {record_id} ({doc_type}, {filename})")
    return record


def mark_filled(record_id: str, fill_filename: str) -> bool:
    """标记某条历史记录已填充到 Excel。"""
    path = _history_dir() / f"{record_id}.json"
    if not path.exists():
        return False
    data = json.loads(path.read_text("utf-8"))
    data["filled"] = True
    data["fill_filename"] = fill_filename
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return True


def list_records(
        *,
        doc_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
        keyword: str = "",
) -> tuple[list[HistorySummary], int]:
    """列出历史记录（按时间倒序），返回 (列表, 总数)。"""
    hdir = _history_dir()
    files = sorted(hdir.glob("*.json"), reverse=True)

    # 筛选
    filtered: list[Path] = []
    for f in files:
        if doc_type:
            # 文件名包含 doc_type
            if f"_{doc_type}_" not in f.name:
                continue
        if keyword:
            # 快速检查文件名是否包含关键字
            content = f.read_text("utf-8")
            if keyword.lower() not in content.lower():
                continue
        filtered.append(f)

    total = len(filtered)
    page = filtered[offset: offset + limit]

    summaries: list[HistorySummary] = []
    for f in page:
        try:
            data = json.loads(f.read_text("utf-8"))
            summaries.append(HistorySummary(
                id=data.get("id", f.stem),
                timestamp=data.get("timestamp", ""),
                doc_type=data.get("doc_type", ""),
                filename=data.get("filename", ""),
                pages=data.get("pages", 0),
                record_count=data.get("record_count", 0),
                filled=data.get("filled", False),
                fill_filename=data.get("fill_filename", ""),
            ))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"读取历史记录失败: {f.name}: {e}")

    return summaries, total


def get_record(record_id: str) -> HistoryRecord | None:
    """获取单条历史记录详情。"""
    path = _history_dir() / f"{record_id}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text("utf-8"))
        return HistoryRecord.model_validate(data)
    except (json.JSONDecodeError, OSError, ValueError) as e:
        logger.warning(f"读取历史记录失败: {record_id}: {e}")
        return None


def delete_record(record_id: str) -> bool:
    """删除单条历史记录。"""
    path = _history_dir() / f"{record_id}.json"
    if not path.exists():
        return False
    path.unlink()
    logger.info(f"历史记录已删除: {record_id}")
    return True


def get_stats() -> HistoryStats:
    """获取历史数据统计。"""
    hdir = _history_dir()
    files = list(hdir.glob("*.json"))

    by_type: dict[str, int] = {}
    total_pages = 0
    total_entries = 0
    recent_7 = 0
    cutoff = datetime.now().timestamp() - 7 * 24 * 3600

    for f in files:
        try:
            data = json.loads(f.read_text("utf-8"))
            dt = data.get("doc_type", "unknown")
            by_type[dt] = by_type.get(dt, 0) + 1
            total_pages += data.get("pages", 0)
            total_entries += data.get("record_count", 0)
            # 检查是否在近7天
            ts_str = data.get("timestamp", "")
            if ts_str:
                try:
                    ts = datetime.fromisoformat(ts_str)
                    if ts.timestamp() > cutoff:
                        recent_7 += 1
                except ValueError:
                    pass
        except (json.JSONDecodeError, OSError):
            pass

    return HistoryStats(
        total_records=len(files),
        by_doc_type=by_type,
        total_pages_processed=total_pages,
        total_entries_extracted=total_entries,
        recent_7_days=recent_7,
    )
