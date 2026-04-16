"""将文档处理结果自动转换为 summary entries。

每次文档处理完成后调用 write_entries_from_result()，
将提取的数据分解为可聚合、可追溯的明细行。
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from app.config import settings
from app.summary_store import SummaryEntry, save_entries_batch


def _safe_float(val: Any) -> float:
    """安全转换浮点数。"""
    if val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    try:
        return float(str(val).replace(",", ".").replace(" ", ""))
    except (ValueError, TypeError):
        return 0.0


def _extract_date_from_results(results: list[dict], fallback: str = "") -> str:
    """尝试从识别结果中提取业务日期。"""
    for r in results:
        # customs 格式
        for f in r.get("fields", []):
            if isinstance(f, dict) and f.get("field_name") == "date" and f.get("value"):
                return str(f["value"])[:10]
        # log/factory 格式
        meta = r.get("meta", {})
        if isinstance(meta, dict):
            d = meta.get("date", "")
            if d:
                return str(d)[:10]
        # 直接取 date 字段
        d = r.get("date", "")
        if d:
            return str(d)[:10]
    return fallback


def write_entries_from_result(
    *,
    doc_type: str,
    filename: str,
    history_id: str,
    results: list[dict[str, Any]],
    process_date: str = "",
) -> int:
    """将一次处理结果写入 summary entries，返回写入条数。"""
    entries: list[SummaryEntry] = []
    biz_date = _extract_date_from_results(results, fallback=process_date)

    if doc_type == "customs":
        entries.extend(_customs_entries(results, filename, history_id, biz_date))
    elif doc_type == "log_measurement":
        entries.extend(_log_inbound_entries(results, filename, history_id, biz_date))
    elif doc_type == "log_output":
        entries.extend(_log_outbound_entries(results, filename, history_id, biz_date))
    elif doc_type == "soak_pool":
        entries.extend(_soak_pool_entries(results, filename, history_id, biz_date))
    elif doc_type == "slicing":
        entries.extend(_slicing_entries(results, filename, history_id, biz_date))
    elif doc_type == "packing":
        entries.extend(_packing_entries(results, filename, history_id, biz_date))

    if entries:
        save_entries_batch(entries)
        logger.info(f"已写入 {len(entries)} 条汇总明细 ({doc_type}, {filename})")
    return len(entries)


def _customs_entries(results: list[dict], filename: str, hid: str, date: str) -> list[SummaryEntry]:
    """进口单据 → 每条 record 一行。"""
    out: list[SummaryEntry] = []
    for r in results:
        fields = {f["field_name"]: f["value"] for f in r.get("fields", []) if isinstance(f, dict)}
        amount = 0.0
        for fname in ("total_value", "total_amount", "invoice_total", "amount"):
            if fname in fields and fields[fname]:
                amount = _safe_float(fields[fname])
                if amount > 0:
                    break
        volume = 0.0
        for fname in ("quantity", "volume_m3", "quantity_m3"):
            if fname in fields and fields[fname]:
                v = _safe_float(fields[fname])
                if v > 0:
                    volume = v
                    break
        doc_date = date
        if fields.get("date"):
            doc_date = str(fields["date"])[:10]

        out.append(SummaryEntry(
            source="auto", history_id=hid, filename=filename,
            category="import", metric="customs_record",
            date=doc_date, value=amount,
            unit=str(fields.get("currency", "")).strip().upper() or settings.default_currency,
            batch_id=str(fields.get("declaration_number", "")),
            detail={
                "doc_type_detail": fields.get("document_type", ""),
                "declaration_number": fields.get("declaration_number", ""),
                "importer": fields.get("importer", ""),
                "exporter": fields.get("exporter", ""),
                "volume_m3": volume,
                "goods_description": fields.get("goods_description", ""),
            },
        ))
    return out


def _log_inbound_entries(results: list[dict], filename: str, hid: str, date: str) -> list[SummaryEntry]:
    """原木入库检尺单 → 每页（每批次）一行。"""
    out: list[SummaryEntry] = []
    for page in results:
        meta = page.get("meta", {}) if isinstance(page.get("meta"), dict) else {}
        entries = page.get("entries", [])
        vol = _safe_float(meta.get("total_volume_m3"))
        if vol <= 0:
            for e in entries:
                vol += _safe_float(e.get("volume_m3"))
        pg_date = str(meta.get("date", date))[:10] or date
        out.append(SummaryEntry(
            source="auto", history_id=hid, filename=filename,
            category="log_inbound", metric="inbound_batch",
            date=pg_date, value=vol, unit="m³",
            batch_id=str(meta.get("batch_id", "")),
            vehicle_plate=str(meta.get("vehicle_plate", "")),
            detail={
                "supplier": meta.get("supplier", ""),
                "species": meta.get("species", ""),
                "log_count": len(entries),
            },
        ))
    return out


def _log_outbound_entries(results: list[dict], filename: str, hid: str, date: str) -> list[SummaryEntry]:
    """原木出库 → 每页一行。"""
    out: list[SummaryEntry] = []
    for page in results:
        meta = page.get("meta", {}) if isinstance(page.get("meta"), dict) else {}
        entries = page.get("entries", [])
        vol = _safe_float(meta.get("total_volume_m3"))
        pg_date = str(meta.get("date", date))[:10] or date
        out.append(SummaryEntry(
            source="auto", history_id=hid, filename=filename,
            category="log_outbound", metric="outbound_batch",
            date=pg_date, value=vol, unit="m³",
            batch_id=str(meta.get("batch_id", "")),
            detail={
                "log_count": len(entries),
            },
        ))
    return out


def _soak_pool_entries(results: list[dict], filename: str, hid: str, date: str) -> list[SummaryEntry]:
    """入池 → 每页一行。"""
    out: list[SummaryEntry] = []
    for page in results:
        meta = page.get("meta", {}) if isinstance(page.get("meta"), dict) else {}
        entries = page.get("entries", [])
        vol = 0.0
        for e in entries:
            l_mm = _safe_float(e.get("length_mm"))
            w_mm = _safe_float(e.get("width_mm"))
            t_mm = _safe_float(e.get("thickness_mm"))
            if l_mm > 0 and w_mm > 0 and t_mm > 0:
                vol += l_mm * w_mm * t_mm / 1e9
        pg_date = str(meta.get("date", date))[:10] or date
        out.append(SummaryEntry(
            source="auto", history_id=hid, filename=filename,
            category="soak_pool", metric="soak_pool_batch",
            date=pg_date, value=len(entries), unit="根",
            batch_id=str(meta.get("batch_id", "")),
            detail={
                "pool_number": meta.get("pool_number", ""),
                "volume_m3": round(vol, 4),
            },
        ))
    return out


def _slicing_entries(results: list[dict], filename: str, hid: str, date: str) -> list[SummaryEntry]:
    """上机 → 每页一行。"""
    out: list[SummaryEntry] = []
    for page in results:
        meta = page.get("meta", {}) if isinstance(page.get("meta"), dict) else {}
        entries = page.get("entries", [])
        output_m2 = _safe_float(meta.get("total_output_m2"))
        pg_date = str(meta.get("date", date))[:10] or date
        out.append(SummaryEntry(
            source="auto", history_id=hid, filename=filename,
            category="slicing", metric="slicing_batch",
            date=pg_date, value=len(entries), unit="根",
            batch_id=str(meta.get("batch_id", "")),
            detail={
                "machine_id": meta.get("machine_id", ""),
                "species": meta.get("species", ""),
                "output_m2": output_m2,
            },
        ))
    return out


def _packing_entries(results: list[dict], filename: str, hid: str, date: str) -> list[SummaryEntry]:
    """打包 → 每页一行。"""
    out: list[SummaryEntry] = []
    for page in results:
        meta = page.get("meta", {}) if isinstance(page.get("meta"), dict) else {}
        entries = page.get("entries", [])
        total_pieces = 0
        total_area = 0.0
        pkg_ids = set()
        for e in entries:
            total_pieces += max(0, int(_safe_float(e.get("piece_count"))))
            total_area += _safe_float(e.get("area_m2"))
            pid = e.get("package_id", "")
            if pid:
                pkg_ids.add(pid)
        pg_date = str(meta.get("date", date))[:10] or date
        out.append(SummaryEntry(
            source="auto", history_id=hid, filename=filename,
            category="packing", metric="packing_batch",
            date=pg_date, value=len(pkg_ids), unit="包",
            detail={
                "pieces": total_pieces,
                "area_m2": round(total_area, 4),
                "packages": len(pkg_ids),
            },
        ))
    return out
