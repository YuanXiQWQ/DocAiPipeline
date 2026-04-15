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
    row_number: int  # 表格中的行号
    log_id: str = ""  # 编号 / 包号 / 根号
    length_m: float  # 长度（米）
    diameter_cm: int  # 直径（厘米）
    volume_m3: float | None = None  # 体积（m³），打印码单有此值，手写表一般无
    needs_review: bool = False  # 是否需要人工复核
    review_reason: str | None = None  # 复核原因


class LogSheetMeta(BaseModel):
    """检尺单表头元数据。"""
    sheet_type: str = ""  # "handwritten" | "printed_tally" | "confirmation"
    date: str = ""  # 日期
    batch_id: str = ""  # 批次号（如 260206-3）
    vehicle_plate: str = ""  # 车牌号
    supplier: str = ""  # 供应商 / 送货客户
    species: str = ""  # 木种
    total_count: int | None = None  # 合计根数
    total_volume_m3: float | None = None  # 合计体积 m³


class LogMeasurementResult(BaseModel):
    """单页检尺单的识别结果。"""
    filename: str
    page: int
    meta: LogSheetMeta
    entries: list[LogEntry] = []
    warnings: list[str] = []


# ------------------------------------------------------------------
# Phase 3: 工厂内部单据
# ------------------------------------------------------------------


class LogOutputEntry(BaseModel):
    """原木领用出库表的单根数据（只有编号和径级，无长度）。"""
    row_number: int
    log_id: str = ""  # 编号 / 根号
    diameter_cm: int = 0  # 径级（CM）
    needs_review: bool = False
    review_reason: str | None = None


class LogOutputMeta(BaseModel):
    """原木领用出库表元数据。"""
    date: str = ""
    batch_id: str = ""  # 批次号
    workshop: str = ""  # 车间
    owner: str = ""  # 货物所有人
    total_count: int | None = None  # 合计根数
    total_volume_m3: float | None = None  # 合计体积 m³


class LogOutputResult(BaseModel):
    """原木领用出库表识别结果。"""
    filename: str
    page: int
    meta: LogOutputMeta
    entries: list[LogOutputEntry] = []
    warnings: list[str] = []


class SoakPoolEntry(BaseModel):
    """刨切木方入池表的单根数据。"""
    row_number: int
    length_mm: int = 0  # 长（mm）
    width_mm: int = 0  # 宽（mm）
    thickness_mm: int = 0  # 厚（mm）
    volume_m3: float | None = None  # 体积（m³）
    supplier: str = ""  # 供货商
    needs_review: bool = False
    review_reason: str | None = None


class SoakPoolMeta(BaseModel):
    """入池表元数据。"""
    date: str = ""
    batch_id: str = ""  # 入池批次号
    pool_number: str = ""  # 池号
    worker: str = ""  # 工位/操作员
    owner: str = ""  # 货物所有人
    craft: str = ""  # 工艺（刨切/半旋等）
    board_thickness: float | None = None  # 表板厚度（1.2/2.0）
    material_name: str = ""  # 物料名称（大方/半圆方等）
    total_count: int | None = None
    total_volume_m3: float | None = None


class SoakPoolResult(BaseModel):
    """入池表识别结果。"""
    filename: str
    page: int
    meta: SoakPoolMeta
    entries: list[SoakPoolEntry] = []
    warnings: list[str] = []


class SlicingEntry(BaseModel):
    """刨切上机表的单根数据。"""
    row_number: int
    log_spec: str = ""  # 大方规格（如 "2.5×2.60"）
    thickness_mm: int = 0  # 大方厚度（mm）
    width_mm: int = 0  # 大方宽度（mm）
    slice_thickness: float = 0.0  # 刨切厚度（mm）
    core_thickness_mm: int = 0  # 木芯厚度（mm）
    core_count: int = 0  # 木芯序号
    needs_review: bool = False
    review_reason: str | None = None


class SlicingMeta(BaseModel):
    """上机表元数据。"""
    date: str = ""
    batch_id: str = ""  # 批号
    machine_id: str = ""  # 机台号
    species: str = ""  # 木种
    owner: str = ""  # 货物所有人
    total_logs: int | None = None  # 合计上机根数
    total_volume_m3: float | None = None  # 合计立方数
    total_output_m2: float | None = None  # 实际产出 m²


class SlicingResult(BaseModel):
    """上机表识别结果。"""
    filename: str
    page: int
    meta: SlicingMeta
    entries: list[SlicingEntry] = []
    warnings: list[str] = []


class PackingEntry(BaseModel):
    """表板打包报表的单行数据。"""
    row_number: int
    owner: str = ""  # 货物所有人
    package_id: str = ""  # 包号
    grade: str = ""  # 等级
    craft: str = ""  # 工艺
    length_mm: int = 0  # 长度（mm）
    width_mm: int = 0  # 宽度（mm）
    thickness: float = 0.0  # 厚度（mm）
    calc_length_mm: int = 0  # 计尺长度（mm）
    calc_width_mm: int = 0  # 计尺宽度（mm）
    calc_thickness: float = 0.0  # 计尺厚度
    piece_count: int = 0  # 片数
    area_m2: float = 0.0  # 平方数
    needs_review: bool = False
    review_reason: str | None = None


class PackingMeta(BaseModel):
    """打包报表元数据。"""
    date: str = ""


class PackingResult(BaseModel):
    """打包报表识别结果。"""
    filename: str
    page: int
    meta: PackingMeta
    entries: list[PackingEntry] = []
    warnings: list[str] = []


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "0.1.0"
