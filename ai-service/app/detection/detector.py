"""YOLO-based document detection — locates individual customs declarations
in a scanned page that may contain multiple documents."""

from __future__ import annotations

from pathlib import Path
from typing import List, Tuple

import cv2
import numpy as np
from loguru import logger

from app.schemas import BoundingBox


class DocumentDetector:
    """Detects individual customs documents within a scanned page image.

    In MVP phase, if no fine-tuned YOLO model is available, falls back to
    a contour-based heuristic that finds rectangular regions.
    """

    def __init__(self, model_path: str | Path | None = None, confidence: float = 0.5):
        self.confidence = confidence
        self.model = None

        if model_path and Path(model_path).exists():
            try:
                from ultralytics import YOLO
                self.model = YOLO(str(model_path))
                logger.info(f"YOLO model loaded from {model_path}")
            except Exception as e:
                logger.warning(f"Failed to load YOLO model: {e}. Using fallback.")
        else:
            logger.info("No YOLO model found — using contour-based fallback detector.")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def detect(self, image: np.ndarray) -> List[BoundingBox]:
        """Return bounding boxes for each detected document in the image."""
        if self.model is not None:
            return self._detect_yolo(image)
        return self._detect_contour_fallback(image)

    def crop_documents(
        self, image: np.ndarray, boxes: List[BoundingBox], padding: int = 10
    ) -> List[np.ndarray]:
        """Crop detected regions from the image."""
        h, w = image.shape[:2]
        crops: List[np.ndarray] = []
        for box in boxes:
            x1 = max(0, int(box.x1) - padding)
            y1 = max(0, int(box.y1) - padding)
            x2 = min(w, int(box.x2) + padding)
            y2 = min(h, int(box.y2) + padding)
            crops.append(image[y1:y2, x1:x2])
        return crops

    # ------------------------------------------------------------------
    # YOLO detection
    # ------------------------------------------------------------------

    def _detect_yolo(self, image: np.ndarray) -> List[BoundingBox]:
        results = self.model(image, conf=self.confidence, verbose=False)
        boxes: List[BoundingBox] = []
        for result in results:
            for box_data in result.boxes:
                xyxy = box_data.xyxy[0].cpu().numpy()
                conf = float(box_data.conf[0])
                boxes.append(BoundingBox(
                    x1=float(xyxy[0]), y1=float(xyxy[1]),
                    x2=float(xyxy[2]), y2=float(xyxy[3]),
                    confidence=conf,
                ))
        logger.info(f"YOLO detected {len(boxes)} document(s)")
        return boxes

    # ------------------------------------------------------------------
    # Fallback: contour-based detection
    # ------------------------------------------------------------------

    def _detect_contour_fallback(self, image: np.ndarray) -> List[BoundingBox]:
        """Fallback strategy (no YOLO model available).

        Without a fine-tuned model, contour-based splitting is unreliable —
        it either crops too aggressively (losing header/footer info) or
        splits a single document into fragments.

        MVP strategy: **always send the full page to the VLM** and let the
        vision model handle document boundary understanding.  This avoids:
        - P4-style splits (one doc fragmented into two records)
        - P6-style partial crops (header with key info cut off)
        - P2-style signature-only crops (irrelevant region extracted)

        When YOLO is fine-tuned, _detect_yolo will take over and provide
        precise per-document bounding boxes.
        """
        img_h, img_w = image.shape[:2]
        full_page = BoundingBox(x1=0, y1=0, x2=float(img_w), y2=float(img_h), confidence=1.0)
        logger.info("Fallback detector: using full page (YOLO not available).")
        return [full_page]
