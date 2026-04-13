"""使用样例 PDF 的快速端到端测试。"""

import sys
import io
from pathlib import Path
from app.pipeline import Pipeline

# 修复 Windows 终端编码
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

SAMPLE_PDF = Path(__file__).resolve().parent.parent / "文档" / "样例" / "SKEN.36.pdf"


def main():
    assert SAMPLE_PDF.exists(), f"Sample PDF not found: {SAMPLE_PDF}"
    print(f"Testing with: {SAMPLE_PDF}")

    pipeline = Pipeline()
    result = pipeline.process(SAMPLE_PDF)

    print(f"\n{'='*60}")
    print(f"File: {result.filename}")
    print(f"Documents detected: {result.total_documents_detected}")
    print(f"Warnings: {len(result.warnings)}")

    for record in result.records:
        print(f"\n--- Record {record.record_index} (page {record.source_page}) ---")
        for field in record.fields:
            flag = " ⚠️" if field.needs_review else ""
            print(f"  {field.field_name}: {field.value}{flag}")
            if field.review_reason:
                print(f"    → {field.review_reason}")

    if result.warnings:
        print(f"\n⚠️ Warnings:")
        for w in result.warnings:
            print(f"  - {w}")

    print(f"\n{'='*60}")
    print("Done. Check output/ directory for exported files.")

    # 显示导出的 JSON 路径
    output_dir = Path("output")
    for f in output_dir.glob("SKEN.36.*"):
        print(f"  -> {f}")


if __name__ == "__main__":
    main()
