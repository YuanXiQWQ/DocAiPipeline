"""核心管线编排器：串联所有处理阶段。

流程：PDF → 预处理 → 单据检测 → VLM 抽取 → 规则校验 → 导出
"""

from __future__ import annotations

from pathlib import Path

import cv2
from loguru import logger

from app.config import settings
from app.detection import DocumentDetector
from app.export import Exporter
from app.extraction import VLMExtractor
from app.preprocessing import Preprocessor
from app.schemas import CustomsRecord, PipelineResult
from app.validation import FieldValidator


class Pipeline:
    """端到端单据处理管线。"""

    def __init__(self):
        settings.ensure_dirs()
        self.preprocessor = Preprocessor(dpi=300)
        self.detector = DocumentDetector(
            model_path=settings.yolo_model_path,
            confidence=0.5,
        )
        self.extractor = VLMExtractor()
        self.validator = FieldValidator()
        self.exporter = Exporter(output_dir=settings.output_dir)

    def process(self, pdf_path: Path, export: bool = True) -> PipelineResult:
        """将 PDF 文件送入完整管线进行处理。"""
        logger.info(f"=== Processing: {pdf_path.name} ===")

        # 1. PDF → 图像
        raw_images = self.preprocessor.pdf_to_images(pdf_path)

        all_records: list[CustomsRecord] = []
        warnings: list[str] = []
        record_index = 0

        for page_num, raw_img in enumerate(raw_images):
            logger.info(f"--- Page {page_num + 1}/{len(raw_images)} ---")

            # 2. 预处理
            processed_img = self.preprocessor.preprocess(raw_img)

            # 3. 检测单据区域
            boxes = self.detector.detect(processed_img)
            crops = self.detector.crop_documents(processed_img, boxes)

            logger.info(f"Page {page_num + 1}: {len(crops)} document(s) detected")

            # 4. 对每个裁切区域抽取字段
            for i, (crop, box) in enumerate(zip(crops, boxes)):
                logger.info(f"  Extracting page {page_num + 1}, region {i + 1}")

                # 保存裁切图片以便复查
                crop_filename = f"{pdf_path.stem}_p{page_num + 1}_d{i + 1}.jpg"
                crop_path = Path(settings.output_dir) / "crops" / crop_filename
                crop_path.parent.mkdir(parents=True, exist_ok=True)
                _ok, _buf = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, 85])
                if _ok:
                    crop_path.write_bytes(_buf.tobytes())

                try:
                    fields = self.extractor.extract(crop)

                    # 检查 VLM 是否标记此页为续页/签名页
                    if self._is_continuation_page(fields):
                        logger.info(f"  Page {page_num + 1} is a continuation/signature page — skipping.")
                        warnings.append(
                            f"Page {page_num + 1}: continuation/signature page (skipped)"
                        )
                        continue

                    # 在校验前移除 is_continuation_page 元字段
                    fields = [f for f in fields if f.field_name != "is_continuation_page"]

                    # 5. 校验
                    fields = self.validator.validate(fields)

                    record_index += 1
                    review_count = sum(1 for f in fields if f.needs_review)
                    if review_count > 0:
                        warnings.append(
                            f"Record {record_index}: {review_count} field(s) need review"
                        )

                    all_records.append(CustomsRecord(
                        record_index=record_index,
                        fields=fields,
                        source_page=page_num + 1,
                        bbox=box,
                        crop_image_path=str(crop_path),
                    ))

                except Exception as e:
                    logger.error(f"  Failed to extract page {page_num + 1}: {e}")
                    warnings.append(f"Page {page_num + 1}: extraction failed — {e}")

        result = PipelineResult(
            filename=pdf_path.name,
            total_documents_detected=len(all_records),
            records=all_records,
            warnings=warnings,
        )

        # 6. 导出
        if export:
            export_paths = self.exporter.export_all(result)
            logger.info(f"Exported to: {export_paths}")

        logger.info(
            f"=== Done: {pdf_path.name} — {len(all_records)} record(s), "
            f"{len(warnings)} warning(s) ==="
        )
        return result

    @staticmethod
    def _is_continuation_page(fields: list) -> bool:
        """检查 VLM 是否将此页标记为续页/签名页。"""
        for f in fields:
            if f.field_name == "is_continuation_page":
                return f.value.lower().strip() in ("true", "yes", "1")
        return False
