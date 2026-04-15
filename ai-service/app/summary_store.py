"""数据汇总明细存储：支持编辑、软删除、历史追溯。

每条明细行（SummaryEntry）对应一个可量化的数据点，如一票进口单据、
一批入库原木、一次入池操作等。所有编辑以追加方式记录修订历史，不丢失任何痕迹。

存储格式：output/summary_entries.json — 单文件 JSON 数组。
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger
from pydantic import BaseModel, Field

from app.config import settings


# ------------------------------------------------------------------
# 数据模型
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
# 存储操作
# ------------------------------------------------------------------


def _store_path() -> Path:
    """汇总明细文件路径。"""
    d = Path(settings.output_dir)
    d.mkdir(parents=True, exist_ok=True)
    return d / "summary_entries.json"


def _load_all() -> list[dict[str, Any]]:
    """加载所有明细行原始 JSON。"""
    p = _store_path()
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text("utf-8"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _save_all(entries: list[dict[str, Any]]) -> None:
    """保存所有明细行。"""
    p = _store_path()
    p.write_text(
        json.dumps(entries, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_entries() -> list[SummaryEntry]:
    """加载并解析所有明细行。"""
    raw = _load_all()
    result = []
    for item in raw:
        try:
            result.append(SummaryEntry.model_validate(item))
        except Exception:
            continue
    return result


def save_entry(entry: SummaryEntry) -> SummaryEntry:
    """新增一条明细行。"""
    entries = _load_all()
    entries.append(entry.model_dump())
    _save_all(entries)
    logger.info(f"汇总明细已新增: {entry.id} ({entry.category}/{entry.metric})")
    return entry


def save_entries_batch(new_entries: list[SummaryEntry]) -> int:
    """批量新增明细行。"""
    if not new_entries:
        return 0
    entries = _load_all()
    for e in new_entries:
        entries.append(e.model_dump())
    _save_all(entries)
    logger.info(f"汇总明细批量新增: {len(new_entries)} 条")
    return len(new_entries)


def update_entry(entry_id: str, updates: dict[str, Any], author: str = "user", note: str = "") -> SummaryEntry | None:
    """更新一条明细行，自动记录修订历史。"""
    entries = _load_all()
    for i, raw in enumerate(entries):
        if raw.get("id") == entry_id:
            # 记录变更
            changes = {}
            for k, v in updates.items():
                if k in ("id", "revisions", "created_at", "source", "history_id"):
                    continue  # 不允许改这些字段
                old_val = raw.get(k)
                if old_val != v:
                    changes[k] = {"old": old_val, "new": v}
                    raw[k] = v
            if changes:
                revision = EntryRevision(
                    author=author,
                    changes=changes,
                    note=note,
                )
                if "revisions" not in raw:
                    raw["revisions"] = []
                raw["revisions"].append(revision.model_dump())
            entries[i] = raw
            _save_all(entries)
            logger.info(f"汇总明细已更新: {entry_id}, 变更: {list(changes.keys())}")
            return SummaryEntry.model_validate(raw)
    return None


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
    for raw in _load_all():
        if raw.get("id") == entry_id:
            try:
                return SummaryEntry.model_validate(raw)
            except Exception:
                return None
    return None


def query_entries(
    *,
    date_from: str = "",
    date_to: str = "",
    category: str = "",
    metric: str = "",
    batch_id: str = "",
    include_deleted: bool = False,
    only_deleted: bool = False,
    source: str = "",  # "auto" / "manual" / ""(全部)
) -> list[SummaryEntry]:
    """按条件查询明细行。"""
    all_entries = load_entries()
    result = []
    for e in all_entries:
        # 删除过滤
        if only_deleted and not e.deleted:
            continue
        if not include_deleted and not only_deleted and e.deleted:
            continue
        # 日期范围
        if date_from and e.date < date_from:
            continue
        if date_to and e.date > date_to:
            continue
        # 分类过滤
        if category and e.category != category:
            continue
        if metric and e.metric != metric:
            continue
        if source and e.source != source:
            continue
        # 批次号模糊匹配
        if batch_id and batch_id.lower() not in e.batch_id.lower():
            continue
        result.append(e)
    return result
