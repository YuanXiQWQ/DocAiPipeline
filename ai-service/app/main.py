"""FastAPI application entry point."""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import FileResponse
from loguru import logger

from app.config import settings
from app.pipeline import Pipeline
from app.schemas import HealthResponse, PipelineResult

app = FastAPI(
    title="DocAI Pipeline",
    description="报关单自动识别与智能归档系统 — AI Service",
    version="0.1.0",
)

# Lazily initialized pipeline (heavy model loading)
_pipeline: Pipeline | None = None


def get_pipeline() -> Pipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = Pipeline()
    return _pipeline


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------


@app.get("/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse()


@app.post("/process", response_model=PipelineResult)
async def process_document(file: UploadFile = File(...)):
    """Upload a PDF/image and process through the full pipeline."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    suffix = Path(file.filename).suffix.lower()
    if suffix not in (".pdf", ".jpg", ".jpeg", ".png", ".tiff", ".tif"):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {suffix}. Accepted: PDF, JPG, PNG, TIFF",
        )

    # Save uploaded file
    settings.ensure_dirs()
    upload_id = uuid.uuid4().hex[:8]
    save_path = Path(settings.upload_dir) / f"{upload_id}_{file.filename}"
    with open(save_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

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
    """Download an exported file (Excel/CSV/JSON)."""
    file_path = Path(settings.output_dir) / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {filename}")
    return FileResponse(path=str(file_path), filename=filename)


# ------------------------------------------------------------------
# Startup / Shutdown
# ------------------------------------------------------------------


@app.on_event("startup")
async def startup():
    settings.ensure_dirs()
    logger.info("DocAI Pipeline service started")
    logger.info(f"Output dir: {settings.output_dir}")
    logger.info(f"VLM model: {settings.openai_model}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=settings.debug)
