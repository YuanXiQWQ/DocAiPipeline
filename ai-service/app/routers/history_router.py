"""历史记录查询路由：查看处理历史、统计汇总、单条详情。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app import history
from app.history import HistoryRecord, HistoryStats, HistorySummary

router = APIRouter(prefix="/api/history", tags=["历史记录"])


@router.get("", response_model=dict)
async def list_history(
    doc_type: str | None = Query(None, description="按文档类型筛选"),
    keyword: str = Query("", description="搜索关键字（文件名/内容）"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """列出处理历史记录（按时间倒序）。"""
    records, total = history.list_records(
        doc_type=doc_type,
        keyword=keyword,
        limit=limit,
        offset=offset,
    )
    return {
        "records": [r.model_dump() for r in records],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/stats", response_model=HistoryStats)
async def history_stats():
    """获取历史数据统计。"""
    return history.get_stats()


@router.get("/{record_id}", response_model=HistoryRecord)
async def get_history_detail(record_id: str):
    """获取单条历史记录详情（含完整识别结果）。"""
    record = history.get_record(record_id)
    if record is None:
        raise HTTPException(404, f"历史记录未找到: {record_id}")
    return record


@router.delete("/{record_id}")
async def delete_history(record_id: str):
    """删除单条历史记录。"""
    ok = history.delete_record(record_id)
    if not ok:
        raise HTTPException(404, f"历史记录未找到: {record_id}")
    return {"message": f"已删除: {record_id}"}
