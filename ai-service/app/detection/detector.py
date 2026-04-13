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
        """Heuristic: find large rectangular contours that likely represent
        individual documents on the scanned page."""
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)

        # Adaptive threshold to handle varying lighting
        thresh = cv2.adaptiveThreshold(
            blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV, 21, 10
        )

        # Morphological close to merge nearby text/lines into blocks
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (50, 50))
        closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)

        contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        img_area = image.shape[0] * image.shape[1]
        min_area = img_area * 0.05   # document must be at least 5% of page
        max_area = img_area * 0.95   # but not the entire page

        boxes: List[BoundingBox] = []
        for contour in contours:
            area = cv2.contourArea(contour)
            if min_area < area < max_area:
                x, y, w, h = cv2.boundingRect(contour)
                aspect = w / h if h > 0 else 0
                # Filter by reasonable aspect ratio for documents
                if 0.3 < aspect < 3.0:
                    boxes.append(BoundingBox(
                        x1=float(x), y1=float(y),
                        x2=float(x + w), y2=float(y + h),
                        confidence=0.8,
                    ))

        # Sort top-to-bottom, then left-to-right
        boxes.sort(key=lambda b: (b.y1, b.x1))

        # If no documents found, treat the whole image as one document
        if not boxes:
            h, w = image.shape[:2]
            boxes = [BoundingBox(x1=0, y1=0, x2=float(w), y2=float(h), confidence=1.0)]
            logger.info("No sub-documents detected — treating entire page as one document.")
        else:
            logger.info(f"Contour fallback detected {len(boxes)} document(s)")

        return boxes
