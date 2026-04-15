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

import asyncio
import json
import shutil
import uuid
from enum import Enum
from pathlib import Path
from typing import Any, AsyncGenerator, Callable

import cv2
import fitz
import numpy as np
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from loguru import logger
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from app.config import settings
from app.extraction import FactoryExtractor, LogExtractor
from app import history
from app.pipeline import Pipeline
from app.preprocessing import Preprocessor
from app.summary_writer import write_entries_from_result

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

    if suffix in (".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp", ".webp"):
        img = cv2.imread(str(file_path))
        if img is None:
            return []
        raw_images = [img]
    else:
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

    if preprocess and raw_images:
        processed = []
        for img in raw_images:
            processed.append(_preprocessor.preprocess(img))
        return processed

    return raw_images


# 进度回调类型：(percent: int, stage: str) -> None
ProgressCallback = Callable[[int, str], None]


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

Reply in JSON (description 用中文):
{"doc_type": "<type>", "confidence": "high|medium|low", "description": "<用中文简述分类理由>"}
"""


def _classify_document(image: np.ndarray) -> ClassifyResponse:
    """用 VLM 分类文档类型。"""
    import base64
    import json

    from typing import cast

    from openai import OpenAI
    from openai.types.chat import ChatCompletionMessageParam

    logger.info("VLM 文档分类中…")
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
    if "```" in raw:
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    try:
        data = json.loads(raw.strip())
    except json.JSONDecodeError:
        data = {"doc_type": "customs", "confidence": "low", "description": "解析失败"}
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
    logger.info(f"文档分类: {file.filename} → {result.doc_type} (置信度: {result.confidence})")
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
            # 为每页保存 crop 图片
            for i, img in enumerate(images):
                crop_path = _save_crop(img, filename, i + 1)
                if i < len(results):
                    results[i]["crop_image_path"] = crop_path

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


def _process_single_file(
    save_path: Path,
    filename: str,
    doc_type_str: str,
    images: list[np.ndarray],
    progress_cb: ProgressCallback | None = None,
) -> ProcessResponse:
    """处理单个文件的核心逻辑（同步），通过 progress_cb 报告进度百分比。"""
    def _report(pct: int, stage: str) -> None:
        if progress_cb:
            progress_cb(pct, stage)

    total_pages = len(images)
    actual_type = doc_type_str

    # 阶段 1：分类（0-20%）
    if actual_type == "auto":
        _report(5, "分类中")
        classify_result = _classify_document(images[0])
        actual_type = classify_result.doc_type
        logger.info(f"自动分类: {filename} → {actual_type} (置信度: {classify_result.confidence})")
    _report(20, "分类完成")

    warnings: list[str] = []
    results: list[Any] = []

    # 阶段 2：逐页识别（20-90%）
    extract_start, extract_end = 20, 90
    extract_range = extract_end - extract_start

    if actual_type == "customs":
        _report(extract_start, f"识别进口单据 (共 {total_pages} 页)")
        pipeline = _get_pipeline()
        pipeline_result = pipeline.process(save_path)
        results = [r.model_dump() for r in pipeline_result.records]
        warnings = pipeline_result.warnings
        for i, img in enumerate(images):
            crop_path = _save_crop(img, filename, i + 1)
            if i < len(results):
                results[i]["crop_image_path"] = crop_path
            pct = extract_start + int(extract_range * (i + 1) / total_pages)
            _report(pct, f"识别进口单据 第 {i + 1}/{total_pages} 页")

    elif actual_type == "log_measurement":
        extractor = _get_log_extractor()
        for i, img in enumerate(images):
            _report(extract_start + int(extract_range * i / total_pages),
                    f"识别检尺单 第 {i + 1}/{total_pages} 页")
            crop_path = _save_crop(img, filename, i + 1)
            r = extractor.extract_page(img, filename=filename, page=i + 1)
            data = r.model_dump()
            data["crop_image_path"] = crop_path
            results.append(data)
            logger.info(f"检尺单识别: {filename} 第 {i + 1}/{total_pages} 页完成")

    elif actual_type in ("log_output", "soak_pool", "slicing", "packing"):
        type_names = {
            "log_output": "出库表", "soak_pool": "入池表",
            "slicing": "上机表", "packing": "打包表",
        }
        type_name = type_names.get(actual_type, actual_type)
        extractor = _get_factory_extractor()
        for i, img in enumerate(images):
            _report(extract_start + int(extract_range * i / total_pages),
                    f"识别{type_name} 第 {i + 1}/{total_pages} 页")
            crop_path = _save_crop(img, filename, i + 1)
            r = extractor.extract(img, doc_type=actual_type, filename=filename, page=i + 1)
            data = r.model_dump()
            data["crop_image_path"] = crop_path
            results.append(data)
            logger.info(f"{type_name}识别: {filename} 第 {i + 1}/{total_pages} 页完成")

    else:
        raise ValueError(f"不支持的文档类型: {actual_type}")

    # 阶段 3：保存结果（90-100%）
    _report(90, "保存结果")
    history_id = ""
    try:
        rec = history.save_record(
            doc_type=actual_type,
            filename=filename,
            pages=len(images),
            results=results,
            warnings=warnings,
        )
        history_id = rec.id
    except Exception as e:
        logger.warning(f"保存历史记录失败: {e}")

    # 写入汇总明细行
    try:
        from datetime import datetime
        write_entries_from_result(
            doc_type=actual_type,
            filename=filename,
            history_id=history_id,
            results=results,
            process_date=datetime.now().strftime("%Y-%m-%d"),
        )
    except Exception as e:
        logger.warning(f"写入汇总明细失败: {e}")

    _report(100, "完成")
    return ProcessResponse(
        doc_type=actual_type,
        filename=filename,
        pages=len(images),
        results=results,
        warnings=warnings,
    )


# ------------------------------------------------------------------
# 批量处理 + SSE 进度推送
# ------------------------------------------------------------------


@router.post("/process-batch")
async def process_batch(
    request: Request,
    files: list[UploadFile] = File(...),
    doc_type: DocType = Form(DocType.AUTO),
):
    """批量处理多个文件，通过 SSE 推送每个文件的处理进度。

    SSE 事件类型：
    - progress: {"index": 0, "total": 3, "filename": "a.pdf", "percent": 30, "stage": "识别中第1/3页"}
    - result:   {"index": 0, "filename": "a.pdf", "data": {...ProcessResponse}}
    - error:    {"index": 0, "filename": "a.pdf", "error": "..."}
    - done:     {"total": 3, "success": 2, "failed": 1}
    """
    saved_files: list[tuple[Path, str]] = []
    for f in files:
        path = _save_upload(f)
        saved_files.append((path, f.filename or path.name))

    total = len(saved_files)
    doc_type_str = doc_type.value

    async def event_generator() -> AsyncGenerator[dict, None]:
        success_count = 0
        for idx, (save_path, filename) in enumerate(saved_files):
            if await request.is_disconnected():
                return

            logger.info(f"开始处理: {filename} ({idx + 1}/{total})")

            # 线程安全的进度队列
            progress_queue: asyncio.Queue[tuple[int, str]] = asyncio.Queue()

            def on_progress(pct: int, stage: str) -> None:
                progress_queue.put_nowait((pct, stage))

            yield {
                "event": "progress",
                "data": json.dumps({
                    "index": idx,
                    "total": total,
                    "filename": filename,
                    "percent": 0,
                    "stage": "开始处理",
                }),
            }

            try:
                images = _file_to_images(save_path)
                if not images:
                    raise ValueError("无法解析文件")

                loop = asyncio.get_event_loop()

                # 异步执行处理，同时轮询进度队列
                import concurrent.futures
                future = loop.run_in_executor(
                    None,
                    _process_single_file,
                    save_path, filename, doc_type_str, images, on_progress,
                )

                # 轮询进度直到处理完成
                while not future.done():
                    try:
                        pct, stage = await asyncio.wait_for(
                            progress_queue.get(), timeout=0.5
                        )
                        yield {
                            "event": "progress",
                            "data": json.dumps({
                                "index": idx,
                                "total": total,
                                "filename": filename,
                                "percent": pct,
                                "stage": stage,
                            }),
                        }
                    except asyncio.TimeoutError:
                        pass

                # 读取剩余进度消息
                while not progress_queue.empty():
                    pct, stage = progress_queue.get_nowait()
                    yield {
                        "event": "progress",
                        "data": json.dumps({
                            "index": idx,
                            "total": total,
                            "filename": filename,
                            "percent": pct,
                            "stage": stage,
                        }),
                    }

                resp = future.result()
                logger.info(f"处理完成: {filename} → {resp.doc_type}, "
                            f"{len(resp.results)} 条记录, {len(resp.warnings)} 条警告")

                yield {
                    "event": "result",
                    "data": json.dumps({
                        "index": idx,
                        "filename": filename,
                        "data": resp.model_dump(),
                    }),
                }
                success_count += 1

            except Exception as e:
                logger.error(f"处理失败: {filename}: {e}")
                yield {
                    "event": "error",
                    "data": json.dumps({
                        "index": idx,
                        "filename": filename,
                        "error": str(e),
                    }),
                }

        yield {
            "event": "done",
            "data": json.dumps({
                "total": total,
                "success": success_count,
                "failed": total - success_count,
            }),
        }
        logger.info(f"批量处理完成: 共 {total} 个文件, 成功 {success_count}, 失败 {total - success_count}")

    return EventSourceResponse(event_generator())


@router.get("/crop/{filename}")
async def get_crop_image(filename: str):
    """获取裁切/页面截图（供复核界面展示原始文档图像）。"""
    crop_path = Path(settings.output_dir) / "crops" / filename
    if not crop_path.exists():
        raise HTTPException(404, f"裁切图片未找到: {filename}")
    return FileResponse(str(crop_path), media_type="image/jpeg")
