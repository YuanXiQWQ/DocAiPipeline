"""FastAPI 应用入口点。"""

from __future__ import annotations

import shutil
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import FileResponse
from loguru import logger

from app.config import settings
from app.pipeline import Pipeline
from app.schemas import HealthResponse, PipelineResult

# 懒加载管线（模型较重）
_pipeline: Pipeline | None = None


def get_pipeline() -> Pipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = Pipeline()
    assert _pipeline is not None
    return _pipeline


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """应用生命周期：启动时初始化目录与日志。"""
    settings.ensure_dirs()
    logger.info("DocAI Pipeline service started")
    logger.info(f"Output dir: {settings.output_dir}")
    logger.info(f"VLM model: {settings.openai_model}")
    yield


app = FastAPI(
    title="DocAI Pipeline",
    description="报关单自动识别与智能归档系统 — AI Service",
    version="0.1.0",
    lifespan=lifespan,
)


# ------------------------------------------------------------------
# 接口
# ------------------------------------------------------------------


@app.get("/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse()


@app.post("/process", response_model=PipelineResult)
async def process_document(file: UploadFile = File(...)):
    """上传 PDF/图像并通过完整管线处理。"""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    suffix = Path(file.filename).suffix.lower()
    if suffix not in (".pdf", ".jpg", ".jpeg", ".png", ".tiff", ".tif"):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {suffix}. Accepted: PDF, JPG, PNG, TIFF",
        )

    # 保存上传文件
    settings.ensure_dirs()
    upload_id = uuid.uuid4().hex[:8]
    save_path = Path(settings.upload_dir) / f"{upload_id}_{file.filename}"
    with open(save_path, "wb") as buf:
        shutil.copyfileobj(file.file, buf)  # type: ignore[arg-type]

    logger.info(f"Received file: {file.filename} → {save_path}")

    try:
        pipeline = get_pipeline()
        result = pipeline.process(save_path)
        return result
    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/download/{filename}")
async def download_file(filename: str):
    """下载导出的文件（Excel/CSV/JSON）。"""
    file_path = Path(settings.output_dir) / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {filename}")
    return FileResponse(path=str(file_path), filename=filename)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=settings.debug)
