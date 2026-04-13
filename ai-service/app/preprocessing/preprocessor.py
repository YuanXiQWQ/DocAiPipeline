"""PDF → image conversion and image preprocessing (denoise, deskew, contrast)."""

from __future__ import annotations

from pathlib import Path
from typing import List, Tuple

import cv2
import fitz  # pymupdf
import numpy as np
from loguru import logger


class Preprocessor:
    """Converts PDFs to images and applies preprocessing steps."""

    def __init__(self, dpi: int = 300):
        self.dpi = dpi

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def pdf_to_images(self, pdf_path: str | Path) -> List[np.ndarray]:
        """Convert each page of a PDF to a BGR numpy array."""
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        images: List[np.ndarray] = []
        doc = fitz.open(str(pdf_path))
        zoom = self.dpi / 72.0
        matrix = fitz.Matrix(zoom, zoom)

        for page_num in range(len(doc)):
            page = doc[page_num]
            pix = page.get_pixmap(matrix=matrix)
            img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
                pix.h, pix.w, pix.n
            )
            # Convert RGB → BGR for OpenCV compatibility
            if pix.n == 4:  # RGBA
                img = cv2.cvtColor(img, cv2.COLOR_RGBA2BGR)
            elif pix.n == 3:  # RGB
                img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
            images.append(img)
            logger.debug(f"Page {page_num + 1}: {pix.w}x{pix.h}")

        doc.close()
        logger.info(f"Converted {pdf_path.name}: {len(images)} page(s)")
        return images

    def preprocess(self, image: np.ndarray) -> np.ndarray:
        """Apply full preprocessing pipeline to a single image."""
        img = self._denoise(image)
        img = self._deskew(img)
        img = self._enhance_contrast(img)
        img = self._sharpen(img)
        return img

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _denoise(image: np.ndarray) -> np.ndarray:
        """Remove noise using Non-Local Means Denoising."""
        return cv2.fastNlMeansDenoisingColored(image, None, 10, 10, 7, 21)

    @staticmethod
    def _deskew(image: np.ndarray) -> np.ndarray:
        """Correct slight rotation using Hough line detection."""
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 50, 150, apertureSize=3)
        lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=100,
                                minLineLength=image.shape[1] // 4, maxLineGap=10)
        if lines is None:
            return image

        angles = []
        for line in lines:
            x1, y1, x2, y2 = line[0]
            angle = np.degrees(np.arctan2(y2 - y1, x2 - x1))
            if abs(angle) < 15:  # only consider near-horizontal lines
                angles.append(angle)

        if not angles:
            return image

        median_angle = float(np.median(angles))
        if abs(median_angle) < 0.3:  # skip if nearly straight
            return image

        logger.debug(f"Deskew angle: {median_angle:.2f}°")
        h, w = image.shape[:2]
        center = (w // 2, h // 2)
        rotation_matrix = cv2.getRotationMatrix2D(center, median_angle, 1.0)
        rotated = cv2.warpAffine(image, rotation_matrix, (w, h),
                                 flags=cv2.INTER_CUBIC,
                                 borderMode=cv2.BORDER_REPLICATE)
        return rotated

    @staticmethod
    def _enhance_contrast(image: np.ndarray) -> np.ndarray:
        """Enhance contrast using CLAHE on the L channel of LAB color space."""
        lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
        l_channel, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        l_enhanced = clahe.apply(l_channel)
        enhanced = cv2.merge([l_enhanced, a, b])
        return cv2.cvtColor(enhanced, cv2.COLOR_LAB2BGR)

    @staticmethod
    def _sharpen(image: np.ndarray) -> np.ndarray:
        """Mild sharpening to improve handwritten text clarity for VLM."""
        kernel = np.array([
            [0, -0.5, 0],
            [-0.5, 3, -0.5],
            [0, -0.5, 0],
        ], dtype=np.float32)
        return cv2.filter2D(image, -1, kernel)
