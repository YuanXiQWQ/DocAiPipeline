"""Pydantic models for API request/response and internal data."""

from __future__ import annotations

from typing import Optional
from pydantic import BaseModel


class BoundingBox(BaseModel):
    """Bounding box for a detected document region."""
    x1: float
    y1: float
    x2: float
    y2: float
    confidence: float


class CustomsField(BaseModel):
    """A single extracted field from a customs declaration."""
    field_name: str
    value: str
    confidence: Optional[float] = None
    needs_review: bool = False
    review_reason: Optional[str] = None


class CustomsRecord(BaseModel):
    """Structured record for one customs declaration."""
    record_index: int
    fields: list[CustomsField]
    source_page: int
    bbox: Optional[BoundingBox] = None
    crop_image_path: Optional[str] = None


class PipelineResult(BaseModel):
    """Result of processing a single uploaded file."""
    filename: str
    total_documents_detected: int
    records: list[CustomsRecord]
    warnings: list[str] = []


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "0.1.0"
