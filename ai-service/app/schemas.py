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


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "0.1.0"
