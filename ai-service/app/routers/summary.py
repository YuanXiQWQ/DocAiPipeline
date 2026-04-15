"""数据汇总路由：从历史记录与明细存储中聚合各环节数据，生成进销存概览。

支持日期范围过滤、卡片明细下钻、行级编辑与历史追溯、单位换算与实时汇率。
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Query
from loguru import logger
from pydantic import BaseModel

from app.config import settings
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


def _aggregate_from_history(*, date_from: str = "", date_to: str = "") -> OverallSummary:
    """从历史记录 JSON 文件中聚合统计数据，支持日期范围过滤。"""
    hdir = Path(settings.output_dir) / "history"
    if not hdir.exists():
        return OverallSummary(
            import_summary=ImportSummary(),
            log_summary=LogSummary(),
            factory_summary=FactorySummary(),
        )

    imp = ImportSummary()
    log = LogSummary()
    fac = FactorySummary()
    total_docs = 0
    total_pages = 0

    for f in hdir.glob("*.json"):
        try:
            data = json.loads(f.read_text("utf-8"))
        except (json.JSONDecodeError, OSError):
            continue

        # 日期过滤：取 timestamp 的日期部分
        ts_str = data.get("timestamp", "")
        if ts_str:
            record_date = ts_str[:10]  # "2026-04-15T..." → "2026-04-15"
            if date_from and record_date < date_from:
                continue
            if date_to and record_date > date_to:
                continue

        doc_type = data.get("doc_type", "")
        results = data.get("results", [])
        total_docs += 1
        total_pages += data.get("pages", 0)

        if doc_type == "customs":
            _agg_customs(imp, results)
        elif doc_type == "log_measurement":
            _agg_log_inbound(log, results)
        elif doc_type == "log_output":
            _agg_log_outbound(log, results)
        elif doc_type == "soak_pool":
            _agg_soak_pool(fac, results)
        elif doc_type == "slicing":
            _agg_slicing(fac, results)
        elif doc_type == "packing":
            _agg_packing(fac, results)

    return OverallSummary(
        import_summary=imp,
        log_summary=log,
        factory_summary=fac,
        total_documents_processed=total_docs,
        total_pages_processed=total_pages,
    )


def _safe_float(val: Any) -> float:
    """安全转换为浮点数。"""
    if val is None:
        return 0.0
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0


def _agg_customs(imp: ImportSummary, results: list[dict]) -> None:
    """聚合进口单据数据。"""
    imp.total_invoices += len(results)
    imp.total_batches += 1
    for r in results:
        fields = {f["field_name"]: f["value"] for f in r.get("fields", [])}
        # 尝试提取金额
        for fname in ("total_amount", "invoice_total", "amount", "ukupno"):
            if fname in fields:
                imp.total_amount_eur += _safe_float(
                    fields[fname].replace(",", ".").replace(" ", "")
                )
                break
        # 尝试提取体积
        for fname in ("volume_m3", "quantity_m3", "masa_neto"):
            if fname in fields:
                imp.total_volume_m3 += _safe_float(
                    fields[fname].replace(",", ".").replace(" ", "")
                )
                break
        # 供应商
        for fname in ("supplier", "sender", "pošiljalac"):
            if fname in fields and fields[fname]:
                name = fields[fname].strip()[:30]
                imp.suppliers[name] = imp.suppliers.get(name, 0) + 1
                break


def _agg_log_inbound(log: LogSummary, results: list[dict]) -> None:
    """聚合原木入库（检尺单）数据。"""
    log.batches += len(results)
    for page in results:
        entries = page.get("entries", [])
        log.total_inbound_logs += len(entries)
        meta = page.get("meta", {})
        vol = _safe_float(meta.get("total_volume_m3"))
        if vol > 0:
            log.total_inbound_m3 += vol
        else:
            # 逐行累加
            for e in entries:
                log.total_inbound_m3 += _safe_float(e.get("volume_m3"))


def _agg_log_outbound(log: LogSummary, results: list[dict]) -> None:
    """聚合原木出库数据。"""
    for page in results:
        entries = page.get("entries", [])
        log.total_outbound_logs += len(entries)
        meta = page.get("meta", {})
        vol = _safe_float(meta.get("total_volume_m3"))
        if vol > 0:
            log.total_outbound_m3 += vol


def _agg_soak_pool(fac: FactorySummary, results: list[dict]) -> None:
    """聚合入池数据。"""
    for page in results:
        entries = page.get("entries", [])
        fac.soak_pool_logs += len(entries)
        for e in entries:
            l_mm = _safe_float(e.get("length_mm"))
            w_mm = _safe_float(e.get("width_mm"))
            t_mm = _safe_float(e.get("thickness_mm"))
            if l_mm > 0 and w_mm > 0 and t_mm > 0:
                fac.soak_pool_m3 += l_mm * w_mm * t_mm / 1e9


def _agg_slicing(fac: FactorySummary, results: list[dict]) -> None:
    """聚合上机数据。"""
    for page in results:
        entries = page.get("entries", [])
        fac.slicing_logs += len(entries)
        meta = page.get("meta", {})
        output = _safe_float(meta.get("total_output_m2"))
        if output > 0:
            fac.slicing_output_m2 += output


def _agg_packing(fac: FactorySummary, results: list[dict]) -> None:
    """聚合打包数据。"""
    package_ids = set()
    for page in results:
        entries = page.get("entries", [])
        for e in entries:
            fac.packing_pieces += max(0, int(_safe_float(e.get("piece_count"))))
            fac.packing_area_m2 += _safe_float(e.get("area_m2"))
            pid = e.get("package_id", "")
            if pid:
                package_ids.add(pid)
    fac.packing_packages += len(package_ids)


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
    return _aggregate_from_history(date_from=date_from, date_to=date_to)


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
