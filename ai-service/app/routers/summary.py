"""数据汇总路由：从历史记录中聚合各环节数据，生成进销存概览。

对应规划 6.1 LKV 整体报表汇总。
客户已有 LKV 表板统计表的公式，这里提供 Web 端的数据概览。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from app.config import settings

router = APIRouter(prefix="/api/summary", tags=["数据汇总"])


# ------------------------------------------------------------------
# 数据模型
# ------------------------------------------------------------------


class ImportSummary(BaseModel):
    """进口采购汇总。"""
    total_batches: int = 0              # 总批次数
    total_invoices: int = 0             # 发票数
    total_amount_eur: float = 0.0       # 总金额（EUR）
    total_volume_m3: float = 0.0        # 总体积（m³）
    suppliers: dict[str, int] = {}       # 供应商 → 批次数


class LogSummary(BaseModel):
    """原木入库/出库汇总。"""
    total_inbound_logs: int = 0         # 入库总根数
    total_inbound_m3: float = 0.0       # 入库总体积
    total_outbound_logs: int = 0        # 出库总根数
    total_outbound_m3: float = 0.0      # 出库总体积
    batches: int = 0                    # 批次数


class FactorySummary(BaseModel):
    """工厂加工汇总。"""
    soak_pool_logs: int = 0             # 入池根数
    soak_pool_m3: float = 0.0           # 入池体积
    slicing_logs: int = 0               # 上机根数
    slicing_output_m2: float = 0.0      # 刨切产出 m²
    packing_pieces: int = 0             # 打包片数
    packing_area_m2: float = 0.0        # 打包面积 m²
    packing_packages: int = 0           # 打包包数


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


def _aggregate_from_history() -> OverallSummary:
    """从历史记录 JSON 文件中聚合统计数据。"""
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


@router.get("", response_model=OverallSummary)
async def get_summary():
    """获取全局数据汇总概览（进销存）。"""
    return _aggregate_from_history()
