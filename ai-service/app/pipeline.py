"""Core pipeline orchestrator — ties all stages together.

Flow: PDF → preprocess → detect documents → VLM extract → validate → export
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import cv2
from loguru import logger

from app.config import settings
from app.detection import DocumentDetector
from app.export import Exporter
from app.extraction import VLMExtractor
from app.preprocessing import Preprocessor
from app.schemas import BoundingBox, CustomsRecord, PipelineResult
from app.validation import FieldValidator


class Pipeline:
    """End-to-end document processing pipeline."""

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

    def process(self, pdf_path: str | Path, export: bool = True) -> PipelineResult:
        """Process a PDF file through the full pipeline."""
        pdf_path = Path(pdf_path)
        logger.info(f"=== Processing: {pdf_path.name} ===")

        # 1. PDF → images
        raw_images = self.preprocessor.pdf_to_images(pdf_path)

        all_records: list[CustomsRecord] = []
        warnings: list[str] = []
        record_index = 0

        for page_num, raw_img in enumerate(raw_images):
            logger.info(f"--- Page {page_num + 1}/{len(raw_images)} ---")

            # 2. Preprocess
            processed_img = self.preprocessor.preprocess(raw_img)

            # 3. Detect individual documents
            boxes = self.detector.detect(processed_img)
            crops = self.detector.crop_documents(processed_img, boxes)

            logger.info(f"Page {page_num + 1}: {len(crops)} document(s) detected")

            # 4. Extract fields from each crop
            for i, (crop, box) in enumerate(zip(crops, boxes)):
                logger.info(f"  Extracting page {page_num + 1}, region {i + 1}")

                # Save crop for review
                crop_filename = f"{pdf_path.stem}_p{page_num + 1}_d{i + 1}.jpg"
                crop_path = Path(settings.output_dir) / "crops" / crop_filename
                crop_path.parent.mkdir(parents=True, exist_ok=True)
                cv2.imwrite(str(crop_path), crop)

                try:
                    fields = self.extractor.extract(crop)

                    # Check if VLM flagged this as a continuation/signature page
                    if self._is_continuation_page(fields):
                        logger.info(f"  Page {page_num + 1} is a continuation/signature page — skipping.")
                        warnings.append(
                            f"Page {page_num + 1}: continuation/signature page (skipped)"
                        )
                        continue

                    # Remove the is_continuation_page meta field before validation
                    fields = [f for f in fields if f.field_name != "is_continuation_page"]

                    # 5. Validate
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

        # 6. Export
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
        """Check if the VLM marked this page as a continuation/signature page."""
        for f in fields:
            if f.field_name == "is_continuation_page":
                return f.value.lower().strip() in ("true", "yes", "1")
        return False
