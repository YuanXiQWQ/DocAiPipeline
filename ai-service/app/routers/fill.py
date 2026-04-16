"""Excel 填充路由：将识别结果写入目标 Excel 模板并返回下载链接。

所有文档类型均写入同一个数据统计模板的“数据源表”工作表。
模板解析优先级：用户上传 > 按 doc_type 存放的专用模板 > 内置默认模板。
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from loguru import logger
from pydantic import BaseModel

from app.config import settings
from app.export.factory_filler import (
    LogOutputFiller,
    PackingFiller,
    SlicingFiller,
    SoakPoolFiller,
)
from app.export.log_filler import LogFiller

router = APIRouter(prefix="/api", tags=["填充"])

# ------------------------------------------------------------------
# 默认模板路径（可通过 API 覆盖）
# ------------------------------------------------------------------

TEMPLATES_DIR = Path(settings.output_dir) / "templates"


def _builtin_template_path() -> Path:
    """内置数据统计模板路径（兼容 PyInstaller 打包与开发模式）。"""
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    else:
        base = Path(__file__).resolve().parent.parent.parent  # ai-service/
    return base / "models" / "数据统计_模板.xlsx"


class FillRequest(BaseModel):
    """填充请求：识别结果 JSON + 文档类型。"""
    doc_type: str
    results: list[dict]


class FillResponse(BaseModel):
    """填充响应：下载链接。"""
    download_url: str
    filename: str
    rows_written: int


# ------------------------------------------------------------------
# 模板管理端点
# ------------------------------------------------------------------


class TemplateInfo(BaseModel):
    """模板信息。"""
    name: str
    doc_type: str
    size_kb: float


@router.get("/templates", response_model=list[TemplateInfo])
async def list_templates():
    """列出已上传的 Excel 模板。"""
    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    result = []
    for f in TEMPLATES_DIR.glob("*.xlsx"):
        # 按子目录名判断 doc_type
        doc_type = f.parent.name if f.parent != TEMPLATES_DIR else "unknown"
        result.append(TemplateInfo(
            name=f.name,
            doc_type=doc_type,
            size_kb=round(f.stat().st_size / 1024, 1),
        ))
    # 也扫描子目录
    for subdir in TEMPLATES_DIR.iterdir():
        if subdir.is_dir():
            for f in subdir.glob("*.xlsx"):
                result.append(TemplateInfo(
                    name=f.name,
                    doc_type=subdir.name,
                    size_kb=round(f.stat().st_size / 1024, 1),
                ))
    return result


@router.post("/templates/{doc_type}")
async def upload_template(
        doc_type: str,
        file: UploadFile = File(...),
):
    """上传 Excel 模板。按 doc_type 分目录存放。"""
    if not file.filename or not file.filename.endswith(".xlsx"):
        raise HTTPException(400, "请上传 .xlsx 文件")
    target_dir = TEMPLATES_DIR / doc_type
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / file.filename
    with open(target, "wb") as buf:
        content = await file.read()
        buf.write(content)
    logger.info(f"模板上传: {doc_type}/{file.filename} ({len(content) / 1024:.1f}KB)")
    return {"message": f"模板已保存: {target.relative_to(TEMPLATES_DIR)}"}


# ------------------------------------------------------------------
# 填充端点
# ------------------------------------------------------------------


# customs 使用独立的纸质发票记录表模板，不写入数据源表
_NEED_OWN_TEMPLATE = frozenset({"customs"})


def _find_template(doc_type: str) -> Path:
    """查找模板文件。优先级：按 doc_type 存放的专用模板 > 内置默认模板。"""
    # 1. 按 doc_type 查找专用模板
    target_dir = TEMPLATES_DIR / doc_type
    if target_dir.exists():
        templates = list(target_dir.glob("*.xlsx"))
        if templates:
            return templates[0]
    # 2. 需要独立模板的类型不回退到数据统计模板
    if doc_type in _NEED_OWN_TEMPLATE:
        raise HTTPException(
            404,
            f"未找到 {doc_type} 类型的专用模板，请在填充时上传模板或存放到 templates/{doc_type}/",
        )
    # 3. 回退到内置数据统计模板
    builtin = _builtin_template_path()
    if builtin.exists():
        return builtin
    raise HTTPException(404, f"未找到模板文件，请在填充时上传 Excel 模板")


@router.post("/fill", response_model=FillResponse)
async def fill_excel(
        doc_type: str = Form(...),
        results_json: str = Form(...),
        template: UploadFile | None = File(None),
):
    """将识别结果填入 Excel 模板。

    - doc_type: 文档类型
    - results_json: 识别结果的 JSON 字符串
    - template: 可选，直接上传模板文件（不使用已存模板）
    """
    import json

    try:
        results_data = json.loads(results_json)
    except json.JSONDecodeError as e:
        raise HTTPException(400, f"JSON 解析失败: {e}")

    # 确定模板路径
    if template and template.filename:
        # 使用上传的模板
        template_path = Path(settings.upload_dir) / f"tpl_{uuid.uuid4().hex[:6]}_{template.filename}"
        with open(template_path, "wb") as buf:
            buf.write(await template.read())
    else:
        template_path = _find_template(doc_type)

    # 输出路径
    output_dir = Path(settings.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_name = f"filled_{doc_type}_{uuid.uuid4().hex[:6]}.xlsx"
    output_path = output_dir / output_name

    try:
        rows = _do_fill(doc_type, results_data, template_path, output_path)
    except Exception as e:
        logger.error(f"填充失败: {e}")
        raise HTTPException(500, f"填充失败: {e}")

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
