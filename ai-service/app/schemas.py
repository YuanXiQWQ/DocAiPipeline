"""Pydantic 数据模型：API 请求/响应及内部数据结构。"""

from __future__ import annotations

from typing import Optional
from pydantic import BaseModel


class BoundingBox(BaseModel):
    """检测到的单据区域边界框。"""
    x1: float
    y1: float
    x2: float
    y2: float
    confidence: float


class CustomsField(BaseModel):
    """从单据中抽取的单个字段。"""
    field_name: str
    value: str
    confidence: Optional[float] = None
    needs_review: bool = False
    review_reason: Optional[str] = None


class CustomsRecord(BaseModel):
    """单份单据的结构化记录。"""
    record_index: int
    fields: list[CustomsField]
    source_page: int
    bbox: Optional[BoundingBox] = None
    crop_image_path: Optional[str] = None


class PipelineResult(BaseModel):
    """单个上传文件的处理结果。"""
    filename: str
    total_documents_detected: int
    records: list[CustomsRecord]
    warnings: list[str] = []


# ------------------------------------------------------------------
# Phase 2: 检尺单（原木测量记录）
# ------------------------------------------------------------------


class LogEntry(BaseModel):
    """单根原木的检尺数据。"""
    row_number: int                         # 表格中的行号
    log_id: str = ""                        # 编号 / 包号 / 根号
    length_m: float                         # 长度（米）
    diameter_cm: int                        # 直径（厘米）
    volume_m3: float | None = None          # 体积（m³），打印码单有此值，手写表一般无
    needs_review: bool = False              # 是否需要人工复核
    review_reason: str | None = None        # 复核原因


class LogSheetMeta(BaseModel):
    """检尺单表头元数据。"""
    sheet_type: str = ""                    # "handwritten" | "printed_tally" | "confirmation"
    date: str = ""                          # 日期
    batch_id: str = ""                      # 批次号（如 260206-3）
    vehicle_plate: str = ""                 # 车牌号
    supplier: str = ""                      # 供应商 / 送货客户
    species: str = ""                       # 木种
    total_count: int | None = None          # 合计根数
    total_volume_m3: float | None = None    # 合计体积 m³


class LogMeasurementResult(BaseModel):
    """单页检尺单的识别结果。"""
    filename: str
    page: int
    meta: LogSheetMeta
    entries: list[LogEntry] = []
    warnings: list[str] = []


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "0.1.0"
