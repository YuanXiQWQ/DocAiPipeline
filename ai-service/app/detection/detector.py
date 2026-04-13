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
        individual documents on the scanned page.

        Strategy:
        1. Use line detection to find document boundaries (table borders, etc.)
        2. Merge nearby content regions with morphology
        3. If only one large region is found (>60% of page), use the full page
           — this avoids partial crops when a page contains a single document
        4. If multiple distinct regions found, return each as a separate doc
        """
        img_h, img_w = image.shape[:2]
        img_area = img_h * img_w
        full_page = BoundingBox(x1=0, y1=0, x2=float(img_w), y2=float(img_h), confidence=1.0)

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)

        # Binary threshold — try to detect document boundaries
        thresh = cv2.adaptiveThreshold(
            blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV, 21, 10
        )

        # Two-pass morphology: first detect large structural blocks
        # Use a large kernel to merge text lines into document-sized blobs
        kernel_large = cv2.getStructuringElement(cv2.MORPH_RECT, (100, 100))
        closed_large = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel_large)

        contours, _ = cv2.findContours(closed_large, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        # Filter contours by size
        min_doc_area = img_area * 0.08   # at least 8% of page
        single_doc_threshold = img_area * 0.60  # if >60% of page, it's a single-doc page

        candidates: List[BoundingBox] = []
        for contour in contours:
            area = cv2.contourArea(contour)
            if area < min_doc_area:
                continue
            x, y, w, h = cv2.boundingRect(contour)
            aspect = w / h if h > 0 else 0
            if 0.2 < aspect < 5.0:
                candidates.append(BoundingBox(
                    x1=float(x), y1=float(y),
                    x2=float(x + w), y2=float(y + h),
                    confidence=0.8,
                ))

        # Decision logic
        if len(candidates) == 0:
            logger.info("No sub-documents detected — using full page.")
            return [full_page]

        if len(candidates) == 1:
            box = candidates[0]
            box_area = (box.x2 - box.x1) * (box.y2 - box.y1)
            if box_area > single_doc_threshold:
                # Single large region — just use full page to avoid partial crop
                logger.info("Single large region detected — using full page.")
                return [full_page]
            else:
                logger.info("Single sub-document detected.")
                return candidates

        # Multiple candidates — merge overlapping ones, then return
        candidates.sort(key=lambda b: (b.y1, b.x1))
        merged = self._merge_overlapping(candidates)
        logger.info(f"Contour fallback detected {len(merged)} document(s)")
        return merged

    @staticmethod
    def _merge_overlapping(boxes: List[BoundingBox], iou_threshold: float = 0.3) -> List[BoundingBox]:
        """Merge overlapping bounding boxes."""
        if not boxes:
            return boxes

        result: List[BoundingBox] = [boxes[0]]
        for box in boxes[1:]:
            merged = False
            for i, existing in enumerate(result):
                # Check overlap
                x1 = max(box.x1, existing.x1)
                y1 = max(box.y1, existing.y1)
                x2 = min(box.x2, existing.x2)
                y2 = min(box.y2, existing.y2)
                if x1 < x2 and y1 < y2:
                    inter = (x2 - x1) * (y2 - y1)
                    area_box = (box.x2 - box.x1) * (box.y2 - box.y1)
                    area_ex = (existing.x2 - existing.x1) * (existing.y2 - existing.y1)
                    iou = inter / (area_box + area_ex - inter)
                    if iou > iou_threshold:
                        # Merge: expand existing box
                        result[i] = BoundingBox(
                            x1=min(box.x1, existing.x1),
                            y1=min(box.y1, existing.y1),
                            x2=max(box.x2, existing.x2),
                            y2=max(box.y2, existing.y2),
                            confidence=max(box.confidence, existing.confidence),
                        )
                        merged = True
                        break
            if not merged:
                result.append(box)

        return result
