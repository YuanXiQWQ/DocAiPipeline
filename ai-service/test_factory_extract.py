"""Phase 3 工厂内部单据 VLM 识别测试。

对 4 份样例 PDF 逐页调用 FactoryExtractor，输出识别结果。
"""

import sys
import io
import json
from pathlib import Path

import fitz
import numpy as np
import cv2

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from app.extraction.factory_extractor import FactoryExtractor

SAMPLES_DIR = Path(__file__).resolve().parent.parent / "文档" / "样例"
OUTPUT_DIR = Path(__file__).resolve().parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

# (文件名, 文档类型)
SAMPLE_FILES = [
    ("原木领用出库表.pdf", "log_output"),
    ("刨切木方入池表.pdf", "soak_pool"),
    ("刨切木方上机表.pdf", "slicing"),
    ("表板打包报表.pdf", "packing"),
]


def pdf_to_images(pdf_path: Path) -> list[np.ndarray]:
    """将 PDF 转为 BGR numpy 数组列表。"""
    doc = fitz.open(str(pdf_path))
    images = []
    zoom = 300 / 72.0
    mat = fitz.Matrix(zoom, zoom)
    for page in doc:
        pix = page.get_pixmap(matrix=mat)
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)
        if pix.n == 4:
            img = cv2.cvtColor(img, cv2.COLOR_RGBA2BGR)
        elif pix.n == 3:
            img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
        images.append(img)
    doc.close()
    return images


def main():
    extractor = FactoryExtractor()
    all_results = []

    for fname, doc_type in SAMPLE_FILES:
        pdf_path = SAMPLES_DIR / fname
        if not pdf_path.exists():
            print(f"⚠ 文件不存在: {pdf_path}")
            continue

        print(f"\n{'='*60}")
        print(f"处理: {fname} (type={doc_type})")
        print(f"{'='*60}")

        images = pdf_to_images(pdf_path)
        for i, img in enumerate(images):
            page_num = i + 1
            print(f"\n--- 第 {page_num} 页 ({img.shape[1]}x{img.shape[0]}) ---")

            result = extractor.extract(
                image=img,
                doc_type=doc_type,
                filename=fname,
                page=page_num,
            )

            # 输出元数据
            meta = result.meta  # type: ignore[attr-defined]
            print(f"  Meta: {meta.model_dump()}")

            entries = getattr(result, "entries", [])
            print(f"  识别行数: {len(entries)}")

            # 预览前5行
            if entries:
                print(f"\n  前 {min(5, len(entries))} 行:")
                for entry in entries[:5]:
                    d = entry.model_dump()
                    # 紧凑输出
                    compact = {k: v for k, v in d.items()
                               if v and v != 0 and v != "" and k != "needs_review" and k != "review_reason"}
                    print(f"    {compact}")
                if len(entries) > 5:
                    print(f"    ... 还有 {len(entries) - 5} 行")

            # 输出警告
            warnings = getattr(result, "warnings", [])
            if warnings:
                print(f"\n  ⚠ 警告:")
                for w in warnings:
                    print(f"    - {w}")

            all_results.append(result.model_dump())

    # 保存完整结果
    output_path = OUTPUT_DIR / "factory_extract_results.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n完整结果已保存至: {output_path}")


if __name__ == "__main__":
    main()
