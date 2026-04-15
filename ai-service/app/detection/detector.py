"""单据检测：在可能包含多份单据的扫描页面中定位各个单据。

支持两种模式：
1. YOLO 微调模型（精确，需要训练数据）
2. 基于轮廓的启发式检测（回退方案，从合并扫描中分割多个文档矩形区域）
"""

from __future__ import annotations

from pathlib import Path
from typing import List

import cv2
import numpy as np
from loguru import logger

from app.schemas import BoundingBox

# 单据区域占页面面积的最小比例（低于此值视为噪声/空白）
_MIN_AREA_RATIO = 0.03
# 单据区域占页面面积的最大比例（高于此值说明是整页，不算独立区域）
_MAX_AREA_RATIO = 0.95
# 单据区域的最小宽高（像素），过小的矩形通常是表格线或文字块
_MIN_DIMENSION_PX = 200
# 非极大值抑制 IoU 阈值
_NMS_IOU_THRESHOLD = 0.3


class DocumentDetector:
    """在扫描页面图像中检测单份单据。

    优先使用 YOLO 微调模型；无模型时回退到基于轮廓的启发式检测，
    从合并扫描中分割多个文档矩形区域。
    """

    def __init__(self, model_path: str | Path | None = None, confidence: float = 0.5):
        self.confidence = confidence
        self.model = None

        if model_path and Path(model_path).exists():
            try:
                from ultralytics import YOLO
                self.model = YOLO(str(model_path))
                logger.info(f"已加载 YOLO 模型: {model_path}")
            except Exception as e:
                logger.warning(f"加载 YOLO 模型失败: {e}，将使用轮廓检测回退方案")
        else:
            logger.info("未找到 YOLO 模型，将使用基于轮廓的启发式检测")

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
        logger.info(f"YOLO 检测到 {len(boxes)} 个单据区域")
        return boxes

    # ------------------------------------------------------------------
    # 回退：基于轮廓的多单据检测
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_contour_fallback(image: np.ndarray) -> List[BoundingBox]:
        """基于轮廓的启发式检测：从合并扫描中分割多个文档区域。

        处理流程：
        1. 灰度化 → 自适应阈值 → 形态学闭运算（连接近邻元素）
        2. 查找外轮廓 → 取最小外接矩形
        3. 过滤过小/过大的区域
        4. 非极大值抑制去除重叠框
        5. 如果只检测到 0 或 1 个区域，则返回整页（让 VLM 自行判断）

        适用场景：
        - SKEN 合并扫描（一页包含 2-4 张不同单据）
        - 拍照/扫描时多张纸在一个画面中

        已知局限：
        - 当单据之间无明显间隙时可能无法分割
        - YOLO 微调后可提供更精确的分割
        """
        img_h, img_w = image.shape[:2]
        page_area = float(img_h * img_w)

        # 1. 灰度化 + 自适应阈值
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        binary = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV, 51, 10,
        )

        # 2. 形态学闭运算：连接近邻的文字/表格线，形成文档区域块
        kernel_size = max(img_w // 30, 15)
        kernel = cv2.getStructuringElement(
            cv2.MORPH_RECT, (kernel_size, kernel_size)
        )
        closed = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=2)

        # 3. 再膨胀一次，合并相近的区域
        dilate_kernel = cv2.getStructuringElement(
            cv2.MORPH_RECT, (kernel_size // 2, kernel_size // 2)
        )
        dilated = cv2.dilate(closed, dilate_kernel, iterations=1)

        # 4. 查找外轮廓
        contours, _ = cv2.findContours(
            dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        # 5. 提取候选边界框并过滤
        candidates: List[BoundingBox] = []
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            area = float(w * h)
            area_ratio = area / page_area

            # 过滤过小的区域（噪声、单行文字等）
            if area_ratio < _MIN_AREA_RATIO:
                continue
            # 过滤过大的区域（接近整页，无意义）
            if area_ratio > _MAX_AREA_RATIO:
                continue
            # 过滤过窄/过矮的区域
            if w < _MIN_DIMENSION_PX or h < _MIN_DIMENSION_PX:
                continue

            candidates.append(BoundingBox(
                x1=float(x), y1=float(y),
                x2=float(x + w), y2=float(y + h),
                confidence=0.8,
            ))

        # 6. 按面积降序排列 + 非极大值抑制
        candidates.sort(key=lambda b: (b.x2 - b.x1) * (b.y2 - b.y1), reverse=True)
        boxes = _nms(candidates, _NMS_IOU_THRESHOLD)

        # 7. 按从上到下、从左到右排序（阅读顺序）
        boxes.sort(key=lambda b: (b.y1, b.x1))

        if len(boxes) >= 2:
            logger.info(f"轮廓检测: 在合并扫描中发现 {len(boxes)} 个文档区域")
            return boxes

        # 只检测到 0 或 1 个区域 → 返回整页，让 VLM 自行理解
        full_page = BoundingBox(
            x1=0, y1=0, x2=float(img_w), y2=float(img_h), confidence=1.0,
        )
        logger.info(
            f"轮廓检测: 发现 {len(boxes)} 个候选区域，"
            "不足以确认为多单据页面，返回整页"
        )
        return [full_page]


def _iou(a: BoundingBox, b: BoundingBox) -> float:
    """计算两个边界框的 IoU（交并比）。"""
    inter_x1 = max(a.x1, b.x1)
    inter_y1 = max(a.y1, b.y1)
    inter_x2 = min(a.x2, b.x2)
    inter_y2 = min(a.y2, b.y2)
    inter_area = max(0.0, inter_x2 - inter_x1) * max(0.0, inter_y2 - inter_y1)
    area_a = (a.x2 - a.x1) * (a.y2 - a.y1)
    area_b = (b.x2 - b.x1) * (b.y2 - b.y1)
    union = area_a + area_b - inter_area
    return inter_area / union if union > 0 else 0.0


def _nms(boxes: List[BoundingBox], iou_threshold: float) -> List[BoundingBox]:
    """简单的非极大值抑制。"""
    keep: List[BoundingBox] = []
    for box in boxes:
        suppressed = False
        for kept in keep:
            if _iou(box, kept) > iou_threshold:
                suppressed = True
                break
        if not suppressed:
            keep.append(box)
    return keep
