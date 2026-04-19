"""Excel 填充路由：将识别结果写入目标 Excel 模板并返回下载链接。

模板来源：用户上传 > 模板库指定 ID > 模板库默认模板。
"""

from __future__ import annotations

import json
import shutil
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from loguru import logger
from pydantic import BaseModel

from app.config import settings
from app.db import get_conn
from app.export.factory_filler import (
    LogOutputFiller,
    PackingFiller,
    SlicingFiller,
    SoakPoolFiller,
)
from app.export.log_filler import LogFiller

router = APIRouter(prefix="/api", tags=["填充"])


class FillResponse(BaseModel):
    """填充响应：下载链接。"""
    download_url: str
    filename: str
    rows_written: int


class FillCheckItem(BaseModel):
    """填充检查结果的单项（某个 doc_type 的模板匹配情况）。"""
    doc_type: str
    matched_templates: list[dict[str, Any]]
    default_template_id: str | None
    has_match: bool


class FillCheckResponse(BaseModel):
    """填充检查响应：告知前端每种文档类型的模板匹配情况。"""
    items: list[FillCheckItem]
    all_matched: bool


# ------------------------------------------------------------------
# 模板查找（基于模板库 SQLite）
# ------------------------------------------------------------------


def _find_template_from_db(doc_type: str) -> tuple[Path | None, str | None]:
    """从模板库查找适用于 doc_type 的模板。

    优先返回默认模板，否则返回最近使用的匹配模板。
    返回 (file_path, template_id)，找不到则 (None, None)。
    """
    conn = get_conn()
    # 优先查找默认模板
    row = conn.execute(
        """SELECT id, file_path FROM templates
           WHERE types LIKE ? AND default_for LIKE ?
           ORDER BY last_used_at DESC LIMIT 1""",
        (f'%"{doc_type}"%', f'%"{doc_type}"%'),
    ).fetchone()
    if row:
        p = Path(row["file_path"])
        if p.exists():
            return p, row["id"]
    # 回退到任意匹配模板
    row = conn.execute(
        """SELECT id, file_path FROM templates
           WHERE types LIKE ?
           ORDER BY last_used_at DESC LIMIT 1""",
        (f'%"{doc_type}"%',),
    ).fetchone()
    if row:
        p = Path(row["file_path"])
        if p.exists():
            return p, row["id"]
    return None, None


def _get_template_by_id(template_id: str) -> Path:
    """按 ID 获取模板文件路径。"""
    conn = get_conn()
    row = conn.execute(
        "SELECT file_path FROM templates WHERE id = ?", (template_id,)
    ).fetchone()
    if not row:
        raise HTTPException(404, f"模板不存在: {template_id}")
    p = Path(row["file_path"])
    if not p.exists():
        raise HTTPException(404, f"模板文件丢失: {p.name}")
    return p


def _touch_template(template_id: str) -> None:
    """更新模板的最近使用时间。"""
    conn = get_conn()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE templates SET last_used_at = ? WHERE id = ?",
        (now, template_id),
    )
    conn.commit()


@router.post("/fill/check", response_model=FillCheckResponse)
async def fill_check(body: dict):
    """填充前检查：查找每种文档类型对应的可用模板。

    前端在“填充确认”步骤调用，展示模板匹配情况供用户确认/调整。
    body: { "doc_types": ["customs", "log_measurement"] }
    """
    doc_types: list[str] = body.get("doc_types", [])
    if not doc_types:
        raise HTTPException(400, "缺少 doc_types")

    conn = get_conn()
    items: list[FillCheckItem] = []

    for dt in doc_types:
        rows = conn.execute(
            """SELECT id, name, filename, types, default_for, builtin
               FROM templates WHERE types LIKE ?
               ORDER BY
                   CASE WHEN default_for LIKE ? THEN 0 ELSE 1 END,
                   last_used_at DESC""",
            (f'%"{dt}"%', f'%"{dt}"%'),
        ).fetchall()

        matched = []
        default_id = None
        for r in rows:
            tpl = {
                "id": r["id"],
                "name": r["name"],
                "filename": r["filename"],
                "builtin": bool(r["builtin"]),
                "is_default": dt in json.loads(r["default_for"]),
            }
            matched.append(tpl)
            if tpl["is_default"] and default_id is None:
                default_id = r["id"]

        items.append(FillCheckItem(
            doc_type=dt,
            matched_templates=matched,
            default_template_id=default_id,
            has_match=len(matched) > 0,
        ))

    return FillCheckResponse(
        items=items,
        all_matched=all(item.has_match for item in items),
    )


@router.post("/fill", response_model=FillResponse)
async def fill_excel(
        doc_type: str = Form(...),
        results_json: str = Form(...),
        template_id: str = Form(""),
        template: UploadFile | None = File(None),
):
    """将识别结果填入 Excel 模板。

    模板来源优先级：
    1. 用户直接上传的模板文件 (template)
    2. 指定模板库 ID (template_id)
    3. 模板库中该 doc_type 的默认模板
    """
    try:
        results_data = json.loads(results_json)
    except json.JSONDecodeError as e:
        raise HTTPException(400, f"JSON 解析失败: {e}")

    # 确定模板路径
    used_template_id: str | None = None

    if template and template.filename:
        # 1. 用户直接上传
        template_path = Path(settings.upload_dir) / f"tpl_{uuid.uuid4().hex[:6]}_{template.filename}"
        with open(template_path, "wb") as buf:
            buf.write(await template.read())
    elif template_id:
        # 2. 指定模板库 ID
        template_path = _get_template_by_id(template_id)
        used_template_id = template_id
    else:
        # 3. 自动从模板库查找
        template_path, used_template_id = _find_template_from_db(doc_type)
        if template_path is None:
            raise HTTPException(
                404,
                json.dumps({
                    "code": "no_template",
                    "doc_type": doc_type,
                    "message": f"模板库中没有适用于 {doc_type} 的模板，请先上传模板",
                }, ensure_ascii=False),
            )

    # 更新模板使用时间
    if used_template_id:
        _touch_template(used_template_id)

    # 输出路径
    output_dir = Path(settings.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_name = f"filled_{doc_type}_{timestamp}.xlsx"
    output_path = output_dir / output_name

    try:
        rows = _do_fill(doc_type, results_data, template_path, output_path)
    except Exception as e:
        logger.error(f"填充失败: {e}")
        raise HTTPException(500, f"填充失败: {e}")

    # 复制到导出目录
    export_dir = settings.get_export_dir()
    export_path = export_dir / output_name
    try:
        shutil.copy2(str(output_path), str(export_path))
        logger.info(f"已导出到: {export_path}")
    except Exception as e:
        logger.warning(f"复制到导出目录失败: {e}")

    return FillResponse(
        download_url=f"/api/download/{output_name}",
        filename=output_name,
        rows_written=rows,
    )


def _do_fill(doc_type: str, results: list[dict], template: Path, output: Path) -> int:
    """执行填充，返回写入行数。"""
    from app.schemas import (
        CustomsRecord,
        LogMeasurementResult,
        LogOutputResult,
        PackingResult,
        PipelineResult,
        SlicingResult,
        SoakPoolResult,
    )

    if doc_type == "customs":
        from app.export.invoice_filler import InvoiceFiller
        records = [CustomsRecord.model_validate(r) for r in results]
        pr = PipelineResult(
            filename="web_upload",
            total_documents_detected=len(records),
            records=records,
            warnings=[],
        )
        filler_inv = InvoiceFiller(template)
        filler_inv.fill([pr], output)
        return len(records)

    if doc_type == "log_measurement":
        parsed = [LogMeasurementResult.model_validate(r) for r in results]
        filler = LogFiller(template)
        filler.fill(parsed, output)
        return sum(len(r.entries) for r in parsed)

    if doc_type == "log_output":
        parsed_lo = [LogOutputResult.model_validate(r) for r in results]
        filler_lo = LogOutputFiller(template)
        filler_lo.fill(parsed_lo, output)
        return sum(len(r.entries) for r in parsed_lo)

    if doc_type == "soak_pool":
        parsed_sp = [SoakPoolResult.model_validate(r) for r in results]
        filler_sp = SoakPoolFiller(template)
        filler_sp.fill(parsed_sp, output)
        return sum(len(r.entries) for r in parsed_sp)

    if doc_type == "slicing":
        parsed_sl = [SlicingResult.model_validate(r) for r in results]
        filler_sl = SlicingFiller(template)
        filler_sl.fill(parsed_sl, output)
        return sum(len(r.entries) for r in parsed_sl)

    if doc_type == "packing":
        parsed_pk = [PackingResult.model_validate(r) for r in results]
        filler_pk = PackingFiller(template)
        filler_pk.fill(parsed_pk, output)
        return sum(len(r.entries) for r in parsed_pk)

    raise HTTPException(400, f"不支持的填充类型: {doc_type}")


# ------------------------------------------------------------------
# 文件下载
# ------------------------------------------------------------------


@router.get("/download/{filename}")
async def download_file(filename: str):
    """下载填充后的 Excel 文件。"""
    file_path = Path(settings.output_dir) / filename
    if not file_path.exists():
        raise HTTPException(404, f"文件不存在: {filename}")
    return FileResponse(
        path=str(file_path),
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@router.post("/open-file/{filename}")
async def open_file(filename: str):
    """在系统文件管理器中打开文件所在目录并选中文件（桌面端专用）。"""
    import subprocess

    export_dir = settings.get_export_dir()
    file_path = (export_dir / filename).resolve()
    if not file_path.exists():
        # 回退到 output 目录
        file_path = (Path(settings.output_dir) / filename).resolve()
    if not file_path.exists():
        raise HTTPException(404, f"文件不存在: {filename}")

    try:
        if sys.platform == "win32":
            subprocess.Popen(["explorer", "/select,", str(file_path)])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R", str(file_path)])
        else:
            subprocess.Popen(["xdg-open", str(file_path.parent)])
    except Exception as e:
        raise HTTPException(500, f"无法打开目录: {e}")

    return {"message": f"已打开目录: {file_path.parent}"}
