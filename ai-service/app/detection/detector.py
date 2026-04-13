"""基于 YOLO 的单据检测：在可能包含多份单据的扫描页面中定位各个单据。"""

from __future__ import annotations

from pathlib import Path
from typing import List

import numpy as np
from loguru import logger

from app.schemas import BoundingBox


class DocumentDetector:
    """在扫描页面图像中检测单份单据。

    MVP 阶段：若无微调后的 YOLO 模型，则回退到基于轮廓的启发式检测。
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
    # 公开 API
    # ------------------------------------------------------------------

    def detect(self, image: np.ndarray) -> List[BoundingBox]:
        """返回图像中每份检测到的单据的边界框。"""
        if self.model is not None:
            return self._detect_yolo(image)
        return self._detect_contour_fallback(image)

    @staticmethod
    def crop_documents(
        image: np.ndarray, boxes: List[BoundingBox], padding: int = 10
    ) -> List[np.ndarray]:
        """从图像中裁切检测到的区域。"""
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
    # YOLO 检测
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
    # 回退：基于轮廓的检测
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_contour_fallback(image: np.ndarray) -> List[BoundingBox]:
        """回退策略（无 YOLO 模型时使用）。

        在没有微调模型的情况下，基于轮廓的分割不可靠——
        要么裁切过度（丢失页眉页脚信息），要么将单份文档错误分片。

        MVP 策略：**始终发送整页给 VLM**，让视觉模型自行理解文档边界。
        这样可以避免：
        - P4 型分片（单份文档被拆成两条记录）
        - P6 型部分裁切（包含关键信息的页眉被切掉）
        - P2 型签名页裁切（提取了无关区域）

        当 YOLO 微调完成后，_detect_yolo 将接管并提供精确的单据边界框。
        """
        img_h, img_w = image.shape[:2]
        full_page = BoundingBox(x1=0, y1=0, x2=float(img_w), y2=float(img_h), confidence=1.0)
        logger.info("Fallback detector: using full page (YOLO not available).")
        return [full_page]
