"""统一文档处理路由：上传 PDF → 自动/手动分类 → VLM 识别 → 返回结构化数据。

支持的文档类型：
- customs: 进口单据（报关单/税款/发票/SKEN）
- log_measurement: 原木检尺单
- log_output: 原木领用出库表
- soak_pool: 刨切木方入池表
- slicing: 刨切木方上机表
- packing: 表板打包报表
- auto: 自动分类（VLM 先判断类型）
"""

from __future__ import annotations

import shutil
import uuid
from enum import Enum
from pathlib import Path
from typing import Any

import cv2
import fitz
import numpy as np
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from loguru import logger
from pydantic import BaseModel

from app.config import settings
from app.extraction import FactoryExtractor, LogExtractor
from app import history
from app.pipeline import Pipeline
from app.preprocessing import Preprocessor

# 共享的预处理器实例
_preprocessor = Preprocessor(dpi=300)

router = APIRouter(prefix="/api", tags=["处理"])

# ------------------------------------------------------------------
# 文档类型枚举
# ------------------------------------------------------------------


class DocType(str, Enum):
    """支持的文档类型。"""
    AUTO = "auto"
    CUSTOMS = "customs"
    LOG_MEASUREMENT = "log_measurement"
    LOG_OUTPUT = "log_output"
    SOAK_POOL = "soak_pool"
    SLICING = "slicing"
    PACKING = "packing"


# ------------------------------------------------------------------
# 响应模型
# ------------------------------------------------------------------


class ProcessResponse(BaseModel):
    """统一处理响应。"""
    doc_type: str
    filename: str
    pages: int
    results: list[Any]
    warnings: list[str] = []


class ClassifyResponse(BaseModel):
    """文档分类响应。"""
    doc_type: str
    confidence: str
    description: str


# ------------------------------------------------------------------
# 工具函数
# ------------------------------------------------------------------

# 懒加载的抽取器实例
_pipeline: Pipeline | None = None
_log_extractor: LogExtractor | None = None
_factory_extractor: FactoryExtractor | None = None


def _get_pipeline() -> Pipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = Pipeline()
    assert _pipeline is not None
    return _pipeline


def _get_log_extractor() -> LogExtractor:
    global _log_extractor
    if _log_extractor is None:
        _log_extractor = LogExtractor()
    assert _log_extractor is not None
    return _log_extractor


def _get_factory_extractor() -> FactoryExtractor:
    global _factory_extractor
    if _factory_extractor is None:
        _factory_extractor = FactoryExtractor()
    assert _factory_extractor is not None
    return _factory_extractor


def _save_upload(file: UploadFile) -> Path:
    """保存上传文件到 uploads/，返回路径。"""
    settings.ensure_dirs()
    upload_id = uuid.uuid4().hex[:8]
    filename = file.filename or "unknown.pdf"
    save_path = Path(settings.upload_dir) / f"{upload_id}_{filename}"
    with open(save_path, "wb") as buf:
        shutil.copyfileobj(file.file, buf)  # type: ignore[arg-type]
    return save_path


def _save_crop(image: np.ndarray, filename: str, page: int) -> str:
    """保存页面截图到 output/crops/，返回相对文件名。"""
    stem = Path(filename).stem
    crop_filename = f"{stem}_p{page}.jpg"
    crop_dir = Path(settings.output_dir) / "crops"
    crop_dir.mkdir(parents=True, exist_ok=True)
    crop_path = crop_dir / crop_filename
    cv2.imwrite(str(crop_path), image, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return crop_filename


def _file_to_images(file_path: Path, dpi: int = 300, preprocess: bool = True) -> list[np.ndarray]:
    """将 PDF 或图片文件转为 BGR numpy 数组列表。

    当 preprocess=True 时，对每张图像执行预处理管线
    （去噪 → 纠偏 → 对比度增强 → 锐化），与提案中的预处理阶段对齐。
    """
    suffix = file_path.suffix.lower()
    raw_images: list[np.ndarray] = []

    # 图片文件直接读取
    if suffix in (".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp", ".webp"):
        img = cv2.imread(str(file_path))
        if img is None:
            return []
        raw_images = [img]
    else:
        # PDF 逐页渲染
        doc = fitz.open(str(file_path))
        zoom = dpi / 72.0
        mat = fitz.Matrix(zoom, zoom)
        for page in doc:
            pix = page.get_pixmap(matrix=mat)
            img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)
            if pix.n == 4:
                img = cv2.cvtColor(img, cv2.COLOR_RGBA2BGR)
            elif pix.n == 3:
                img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
            raw_images.append(img)
        doc.close()

    # 预处理（去噪、纠偏、对比度增强、锐化）
    if preprocess and raw_images:
        processed = []
        for img in raw_images:
            processed.append(_preprocessor.preprocess(img))
        return processed

    return raw_images


# ------------------------------------------------------------------
# VLM 文档分类
# ------------------------------------------------------------------

CLASSIFY_PROMPT = """You are a document classifier for a Serbian timber company (TERRA DRVO d.o.o.).
Look at the document image and classify it into exactly ONE of these types:

1. "customs" — Import documents: CR (tax), Deklaracija (customs declaration), Racun (invoice), SKEN (scanned multi-doc)
2. "log_measurement" — 原木检尺单: Handwritten/printed log measurement tally sheet with columns for log ID, length, diameter
3. "log_output" — 原木领用出库表: Log withdrawal table with log IDs and diameters (no length)
4. "soak_pool" — 刨切木方入池表: Soak pool entry record for timber blocks
5. "slicing" — 刨切木方上机表: Slicing machine daily report (often rotated 90°)
6. "packing" — 表板打包报表: Veneer packing report with package IDs, grades, dimensions

Reply in JSON:
{"doc_type": "<type>", "confidence": "high|medium|low", "description": "<brief reason>"}
"""


def _classify_document(image: np.ndarray) -> ClassifyResponse:
    """用 VLM 分类文档类型。"""
    import base64
    import json

    from typing import cast

    from openai import OpenAI
    from openai.types.chat import ChatCompletionMessageParam

    client = OpenAI(
        api_key=settings.openai_api_key,
        **({"base_url": settings.openai_base_url} if settings.openai_base_url else {}),
    )
    _, buf = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 85])
    b64 = base64.b64encode(buf.tobytes()).decode("utf-8")

    messages = cast(list[ChatCompletionMessageParam], cast(object, [
        {"role": "system", "content": CLASSIFY_PROMPT},
        {"role": "user", "content": [
            {"type": "text", "text": "Classify this document."},
            {"type": "image_url", "image_url": {
                "url": f"data:image/jpeg;base64,{b64}", "detail": "low",
            }},
        ]},
    ]))

    response = client.chat.completions.create(
        model=settings.openai_model,
        messages=messages,
        max_tokens=200,
        temperature=0.0,
    )
    raw = response.choices[0].message.content or "{}"
    # 清理 markdown 围栏
    if "```" in raw:
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    try:
        data = json.loads(raw.strip())
    except json.JSONDecodeError:
        data = {"doc_type": "customs", "confidence": "low", "description": "parse failed"}
    return ClassifyResponse(**data)


# ------------------------------------------------------------------
# 端点
# ------------------------------------------------------------------


@router.post("/classify", response_model=ClassifyResponse)
async def classify_document(file: UploadFile = File(...)):
    """上传 PDF/图片，VLM 自动判断文档类型。"""
    save_path = _save_upload(file)
    images = _file_to_images(save_path)
    if not images:
        raise HTTPException(400, "无法解析文件")
    result = _classify_document(images[0])
    logger.info(f"分类: {file.filename} → {result.doc_type} ({result.confidence})")
    return result


@router.post("/process", response_model=ProcessResponse)
async def process_document(
    file: UploadFile = File(...),
    doc_type: DocType = Form(DocType.AUTO),
):
    """统一文档处理端点。

    - doc_type=auto: 先用 VLM 分类，再路由到对应处理器
    - 其他: 直接使用指定的处理器
    """
    save_path = _save_upload(file)
    filename = file.filename or save_path.name
    images = _file_to_images(save_path)
    if not images:
        raise HTTPException(400, "无法解析文件")

    # 自动分类
    actual_type = doc_type.value
    if actual_type == "auto":
        classify_result = _classify_document(images[0])
        actual_type = classify_result.doc_type
        logger.info(f"自动分类: {filename} → {actual_type} ({classify_result.confidence})")

    warnings: list[str] = []
    results: list[Any] = []

    try:
        if actual_type == "customs":
            # Phase 1: 进口单据（使用原有 Pipeline）
            pipeline = _get_pipeline()
            pipeline_result = pipeline.process(save_path)
            results = [r.model_dump() for r in pipeline_result.records]
            warnings = pipeline_result.warnings

        elif actual_type == "log_measurement":
            # Phase 2: 检尺单
            extractor = _get_log_extractor()
            for i, img in enumerate(images):
                crop_path = _save_crop(img, filename, i + 1)
                r = extractor.extract_page(img, filename=filename, page=i + 1)
                data = r.model_dump()
                data["crop_image_path"] = crop_path
                results.append(data)

        elif actual_type in ("log_output", "soak_pool", "slicing", "packing"):
            # Phase 3: 工厂内部单据
            extractor = _get_factory_extractor()
            for i, img in enumerate(images):
                crop_path = _save_crop(img, filename, i + 1)
                r = extractor.extract(img, doc_type=actual_type, filename=filename, page=i + 1)
                data = r.model_dump()
                data["crop_image_path"] = crop_path
                results.append(data)

        else:
            raise HTTPException(400, f"不支持的文档类型: {actual_type}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"处理失败: {filename} ({actual_type}): {e}")
        raise HTTPException(500, f"处理失败: {e}")

    # 自动保存处理历史
    try:
        history.save_record(
            doc_type=actual_type,
            filename=filename,
            pages=len(images),
            results=results,
            warnings=warnings,
        )
    except Exception as e:
        logger.warning(f"保存历史记录失败: {e}")

    return ProcessResponse(
        doc_type=actual_type,
        filename=filename,
        pages=len(images),
        results=results,
        warnings=warnings,
    )


@router.get("/crop/{filename}")
async def get_crop_image(filename: str):
    """获取裁切/页面截图（供复核界面展示原始文档图像）。"""
    crop_path = Path(settings.output_dir) / "crops" / filename
    if not crop_path.exists():
        raise HTTPException(404, f"裁切图片未找到: {filename}")
    return FileResponse(str(crop_path), media_type="image/jpeg")
