"""Phase 2 检尺单 VLM 识别精度测试。

对两份样例 PDF 逐页调用 LogExtractor，输出识别结果并与已知真值比对。
"""

import sys
import io
import json
from pathlib import Path

import fitz
import numpy as np

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from app.extraction.log_extractor import LogExtractor
from app.schemas import LogMeasurementResult

# ------------------------------------------------------------------
# 样例文件
# ------------------------------------------------------------------

SAMPLES_DIR = Path(__file__).resolve().parent.parent / "文档" / "样例"

SAMPLE_FILES = [
    SAMPLES_DIR / "克罗地亚Ad公司原木检尺及入库单-库管填报2.pdf",
    SAMPLES_DIR / "克罗地亚Hrvatske原木对方码单及检尺入库单.pdf",
]

# 已知真值（从图片人工读取）
# Ad公司 P1 左表: 30 行, 右表: 6 行 = 36 根
# Hrvatske P1 打印码单: 33 根, UK.MASA=19.99m³

KNOWN_TRUTH = {
    "Ad_p1": {
        "count": 36,
        "sheet_type": "handwritten",
        "batch_id": "260206-3",
    },
    "Ad_p2": {
        "sheet_type": "confirmation",
        "total_count": 36,
        "total_volume_m3": 23.916,
    },
    "Hr_p1": {
        "count": 33,
        "total_volume_m3": 19.99,
        "sheet_type": "printed_tally",
    },
    "Hr_p2": {
        "sheet_type": "id_list_only",
    },
    "Hr_p3": {
        "sheet_type": "confirmation",
    },
}


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
            import cv2
            img = cv2.cvtColor(img, cv2.COLOR_RGBA2BGR)
        elif pix.n == 3:
            import cv2
            img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
        images.append(img)
    doc.close()
    return images


def main():
    extractor = LogExtractor()
    all_results: list[LogMeasurementResult] = []

    for pdf_path in SAMPLE_FILES:
        if not pdf_path.exists():
            print(f"⚠ 文件不存在: {pdf_path}")
            continue

        print(f"\n{'='*70}")
        print(f"处理: {pdf_path.name}")
        print(f"{'='*70}")

        images = pdf_to_images(pdf_path)
        for i, img in enumerate(images):
            page_num = i + 1
            print(f"\n--- 第 {page_num} 页 ({img.shape[1]}x{img.shape[0]}) ---")

            result = extractor.extract_page(
                image=img,
                filename=pdf_path.name,
                page=page_num,
            )
            all_results.append(result)

            # 输出元数据
            m = result.meta
            print(f"  类型: {m.sheet_type}")
            print(f"  日期: {m.date}")
            print(f"  批次: {m.batch_id}")
            print(f"  车牌: {m.vehicle_plate}")
            print(f"  供应商: {m.supplier}")
            print(f"  声明根数: {m.total_count}")
            print(f"  声明体积: {m.total_volume_m3}")
            print(f"  识别行数: {len(result.entries)}")

            # 输出前5行数据预览
            if result.entries:
                print(f"\n  前 {min(5, len(result.entries))} 行数据:")
                print(f"  {'行':>4} {'编号':>8} {'长度M':>7} {'径级CM':>7} {'体积m³':>8} {'复核':>4}")
                for entry in result.entries[:5]:
                    vol_str = f"{entry.volume_m3:.2f}" if entry.volume_m3 else "-"
                    review = "⚠" if entry.needs_review else "✓"
                    print(f"  {entry.row_number:4d} {entry.log_id:>8} "
                          f"{entry.length_m:7.1f} {entry.diameter_cm:7d} "
                          f"{vol_str:>8} {review:>4}")
                if len(result.entries) > 5:
                    print(f"  ... 还有 {len(result.entries) - 5} 行")

            # 输出警告
            if result.warnings:
                print(f"\n  ⚠ 警告 ({len(result.warnings)}):")
                for w in result.warnings:
                    print(f"    - {w}")

    # ------------------------------------------------------------------
    # 保存完整结果为 JSON
    # ------------------------------------------------------------------
    output_path = Path("output") / "log_extract_results.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(
            [r.model_dump() for r in all_results],
            f,
            ensure_ascii=False,
            indent=2,
        )
    print(f"\n完整结果已保存至: {output_path}")


if __name__ == "__main__":
    main()
