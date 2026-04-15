"""数据汇总路由：从历史记录与明细存储中聚合各环节数据，生成进销存概览。

支持日期范围过滤、卡片明细下钻、行级编辑与历史追溯、单位换算与实时汇率。
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Query
from loguru import logger
from pydantic import BaseModel
from app.summary_store import (
    SummaryEntry,
    EntryRevision,
    query_entries,
    save_entry,
    update_entry,
    soft_delete_entry,
    restore_entry,
    get_entry,
)

router = APIRouter(prefix="/api/summary", tags=["数据汇总"])


# ------------------------------------------------------------------
# 数据模型
# ------------------------------------------------------------------


class ImportSummary(BaseModel):
    """进口采购汇总。"""
    total_batches: int = 0  # 总批次数
    total_invoices: int = 0  # 发票数
    total_amount_eur: float = 0.0  # 总金额（EUR）
    total_volume_m3: float = 0.0  # 总体积（m³）
    suppliers: dict[str, int] = {}  # 供应商 → 批次数


class LogSummary(BaseModel):
    """原木入库/出库汇总。"""
    total_inbound_logs: int = 0  # 入库总根数
    total_inbound_m3: float = 0.0  # 入库总体积
    total_outbound_logs: int = 0  # 出库总根数
    total_outbound_m3: float = 0.0  # 出库总体积
    batches: int = 0  # 批次数


class FactorySummary(BaseModel):
    """工厂加工汇总。"""
    soak_pool_logs: int = 0  # 入池根数
    soak_pool_m3: float = 0.0  # 入池体积
    slicing_logs: int = 0  # 上机根数
    slicing_output_m2: float = 0.0  # 刨切产出 m²
    packing_pieces: int = 0  # 打包片数
    packing_area_m2: float = 0.0  # 打包面积 m²
    packing_packages: int = 0  # 打包包数


class OverallSummary(BaseModel):
    """全局汇总概览。"""
    import_summary: ImportSummary
    log_summary: LogSummary
    factory_summary: FactorySummary
    total_documents_processed: int = 0
    total_pages_processed: int = 0


# ------------------------------------------------------------------
# 聚合逻辑
# ------------------------------------------------------------------


def _aggregate_from_db(*, date_from: str = "", date_to: str = "") -> OverallSummary:
    """从 SQLite summary_entries + history_records 聚合卡片数据。

    与 DetailView 使用同一数据源（summary_entries），确保卡片与详情数字一致。
    """
    from app.db import get_conn

    conn = get_conn()

    # --- 从 summary_entries 聚合（仅未删除的） ---
    entries = query_entries(
        date_from=date_from,
        date_to=date_to,
        include_deleted=False,
    )

    imp = ImportSummary()
    log = LogSummary()
    fac = FactorySummary()

    for e in entries:
        detail = e.detail or {}
        if e.category == "import":
            imp.total_invoices += 1
            imp.total_amount_eur += e.value
            imp.total_volume_m3 += float(detail.get("volume_m3", 0))
            supplier = str(detail.get("importer", "") or detail.get("exporter", "")).strip()[:30]
            if supplier:
                imp.suppliers[supplier] = imp.suppliers.get(supplier, 0) + 1
        elif e.category == "log_inbound":
            log.total_inbound_m3 += e.value
            log.total_inbound_logs += int(detail.get("log_count", 0))
            log.batches += 1
        elif e.category == "log_outbound":
            log.total_outbound_m3 += e.value
            log.total_outbound_logs += int(detail.get("log_count", 0))
        elif e.category == "soak_pool":
            fac.soak_pool_logs += int(e.value)
            fac.soak_pool_m3 += float(detail.get("volume_m3", 0))
        elif e.category == "slicing":
            fac.slicing_logs += int(e.value)
            fac.slicing_output_m2 += float(detail.get("output_m2", 0))
        elif e.category == "packing":
            fac.packing_packages += int(e.value)
            fac.packing_pieces += int(detail.get("pieces", 0))
            fac.packing_area_m2 += float(detail.get("area_m2", 0))

    imp.total_batches = imp.total_invoices  # 每条 entry 对应一票

    # --- 从 history_records 取文档/页数统计 ---
    clauses: list[str] = []
    params: list[Any] = []
    if date_from:
        clauses.append("timestamp>=?")
        params.append(date_from)
    if date_to:
        clauses.append("timestamp<=?")
        params.append(date_to + "T99")  # 包含当天
    where = " AND ".join(clauses) if clauses else "1"

    row = conn.execute(
        f"SELECT COUNT(*) as cnt, COALESCE(SUM(pages),0) as pg FROM history_records WHERE {where}",
        params,
    ).fetchone()
    total_docs = row["cnt"]
    total_pages = row["pg"]

    return OverallSummary(
        import_summary=imp,
        log_summary=log,
        factory_summary=fac,
        total_documents_processed=total_docs,
        total_pages_processed=total_pages,
    )


# ------------------------------------------------------------------
# API 端点
# ------------------------------------------------------------------


def _this_year_range() -> tuple[str, str]:
    """默认日期范围：今年 1月1日 ~ 12月31日。"""
    now = datetime.now()
    return f"{now.year}-01-01", f"{now.year}-12-31"


@router.get("", response_model=OverallSummary)
async def get_summary(
    date_from: str = Query("", description="开始日期 YYYY-MM-DD"),
    date_to: str = Query("", description="结束日期 YYYY-MM-DD"),
):
    """获取全局数据汇总概览（进销存），支持日期范围过滤。"""
    if not date_from and not date_to:
        date_from, date_to = _this_year_range()
    return _aggregate_from_db(date_from=date_from, date_to=date_to)


# ------------------------------------------------------------------
# 明细行 API
# ------------------------------------------------------------------


class EntryListResponse(BaseModel):
    """明细行列表响应。"""
    entries: list[SummaryEntry]
    total: int


@router.get("/entries", response_model=EntryListResponse)
async def list_entries(
    date_from: str = Query(""),
    date_to: str = Query(""),
    category: str = Query(""),
    metric: str = Query(""),
    batch_id: str = Query(""),
    include_deleted: bool = Query(False),
    only_deleted: bool = Query(False),
    source: str = Query(""),
):
    """查询明细行列表。"""
    if not date_from and not date_to:
        date_from, date_to = _this_year_range()
    entries = query_entries(
        date_from=date_from,
        date_to=date_to,
        category=category,
        metric=metric,
        batch_id=batch_id,
        include_deleted=include_deleted,
        only_deleted=only_deleted,
        source=source,
    )
    return EntryListResponse(entries=entries, total=len(entries))


class EntryCreateRequest(BaseModel):
    """手动新增明细行请求。"""
    category: str
    metric: str
    date: str
    value: float
    unit: str = ""
    detail: dict[str, Any] = {}
    note: str = ""


@router.post("/entries", response_model=SummaryEntry)
async def create_entry(req: EntryCreateRequest):
    """手动新增一条明细行。"""
    entry = SummaryEntry(
        source="manual",
        category=req.category,
        metric=req.metric,
        date=req.date,
        value=req.value,
        unit=req.unit,
        detail=req.detail,
    )
    if req.note:
        entry.revisions.append(EntryRevision(author="user", note=req.note))
    return save_entry(entry)


class EntryUpdateRequest(BaseModel):
    """更新明细行请求。"""
    updates: dict[str, Any]  # {field: new_value}
    note: str = ""


@router.put("/entries/{entry_id}", response_model=SummaryEntry)
async def update_entry_api(entry_id: str, req: EntryUpdateRequest):
    """更新一条明细行（自动记录修订历史）。"""
    result = update_entry(entry_id, req.updates, author="user", note=req.note)
    if not result:
        raise HTTPException(404, "明细行不存在")
    return result


@router.delete("/entries/{entry_id}", response_model=SummaryEntry)
async def delete_entry_api(entry_id: str):
    """软删除一条明细行。"""
    result = soft_delete_entry(entry_id)
    if not result:
        raise HTTPException(404, "明细行不存在")
    return result


@router.post("/entries/{entry_id}/restore", response_model=SummaryEntry)
async def restore_entry_api(entry_id: str):
    """恢复一条软删除的明细行。"""
    result = restore_entry(entry_id)
    if not result:
        raise HTTPException(404, "明细行不存在")
    return result


@router.get("/entries/{entry_id}", response_model=SummaryEntry)
async def get_entry_api(entry_id: str):
    """获取单条明细行（含修订历史）。"""
    entry = get_entry(entry_id)
    if not entry:
        raise HTTPException(404, "明细行不存在")
    return entry


# ------------------------------------------------------------------
# 实时汇率（缓存 30 分钟）
# ------------------------------------------------------------------

_rate_cache: dict[str, Any] = {}
_rate_cache_ts: float = 0
_RATE_TTL = 1800  # 30 分钟


async def _fetch_rates(base: str = "EUR") -> dict[str, float]:
    """从公开 API 获取实时汇率，带缓存。"""
    global _rate_cache, _rate_cache_ts
    cache_key = base.lower()
    if cache_key in _rate_cache and time.time() - _rate_cache_ts < _RATE_TTL:
        return _rate_cache[cache_key]

    urls = [
        f"https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies/{base.lower()}.json",
        f"https://latest.currency-api.pages.dev/v1/currencies/{base.lower()}.json",
    ]
    for url in urls:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    rates = data.get(base.lower(), {})
                    if rates:
                        _rate_cache[cache_key] = rates
                        _rate_cache_ts = time.time()
                        return rates
        except Exception as e:
            logger.debug(f"汇率获取失败 ({url}): {e}")
            continue

    return {}


class ExchangeRateResponse(BaseModel):
    """汇率响应。"""
    base: str
    rates: dict[str, float]
    cached: bool = False


@router.get("/exchange-rates", response_model=ExchangeRateResponse)
async def get_exchange_rates(base: str = Query("EUR", description="基准货币")):
    """获取实时汇率（缓存 30 分钟）。"""
    cache_key = base.lower()
    cached = cache_key in _rate_cache and time.time() - _rate_cache_ts < _RATE_TTL
    rates = await _fetch_rates(base.upper())
    if not rates:
        # 返回硬编码后备汇率
        rates = {"eur": 1, "usd": 1.08, "cny": 7.85, "rsd": 117.2}
    return ExchangeRateResponse(base=base.upper(), rates=rates, cached=cached)
