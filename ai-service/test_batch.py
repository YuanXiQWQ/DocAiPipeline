"""批量测试：对所有样例 PDF 运行管线并生成汇总报告。"""

import sys
import io
import json
import time
from pathlib import Path

# 修复 Windows 终端编码
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from app.pipeline import Pipeline

SAMPLE_DIR = Path(__file__).resolve().parent.parent / "文档" / "样例"
REPORT_PATH = Path(__file__).resolve().parent / "output" / "batch_report.json"


def collect_pdfs(sample_dir: Path) -> list[Path]:
    """收集唯一的 PDF（跳过备份文件夹中的副本）。"""
    pdfs = sorted(sample_dir.glob("*.pdf"))
    return pdfs


def count_filled_fields(record) -> tuple[int, int]:
    """返回记录的（已填充, 总数）字段计数。"""
    total = 0
    filled = 0
    for f in record.fields:
        total += 1
        if f.value.strip():
            filled += 1
    return filled, total


def main():
    pdfs = collect_pdfs(SAMPLE_DIR)
    print(f"Found {len(pdfs)} PDF(s) in {SAMPLE_DIR}\n")

    if not pdfs:
        print("No PDFs found. Exiting.")
        return

    # 显示文件列表
    for i, p in enumerate(pdfs, 1):
        print(f"  {i:2d}. {p.name}")

    print(f"\nThis will call the OpenAI API for every page of every PDF.")
    print(f"Estimated cost: ~$0.01-0.03 per page (gpt-4.1-mini with image).")
    print(f"Starting batch processing...\n")

    pipeline = Pipeline()
    results_summary = []
    total_start = time.time()

    for i, pdf_path in enumerate(pdfs, 1):
        print(f"\n{'='*60}")
        print(f"[{i}/{len(pdfs)}] Processing: {pdf_path.name}")
        print(f"{'='*60}")

        start = time.time()
        try:
            result = pipeline.process(pdf_path)
            elapsed = time.time() - start

            # 计算统计数据
            total_fields = 0
            filled_fields = 0
            review_fields = 0
            for record in result.records:
                for f in record.fields:
                    total_fields += 1
                    if f.value.strip():
                        filled_fields += 1
                    if f.needs_review:
                        review_fields += 1

            fill_rate = (filled_fields / total_fields * 100) if total_fields > 0 else 0

            summary = {
                "filename": pdf_path.name,
                "status": "success",
                "records": result.total_documents_detected,
                "total_fields": total_fields,
                "filled_fields": filled_fields,
                "fill_rate_pct": round(fill_rate, 1),
                "review_fields": review_fields,
                "warnings": result.warnings,
                "elapsed_sec": round(elapsed, 1),
            }
            results_summary.append(summary)

            print(f"  ✓ {result.total_documents_detected} record(s), "
                  f"fill rate {fill_rate:.1f}%, "
                  f"{review_fields} need review, "
                  f"{elapsed:.1f}s")

        except Exception as e:
            elapsed = time.time() - start
            summary = {
                "filename": pdf_path.name,
                "status": "error",
                "error": str(e),
                "elapsed_sec": round(elapsed, 1),
            }
            results_summary.append(summary)
            print(f"  ✗ ERROR: {e}")

    total_elapsed = time.time() - total_start

    # 打印汇总表格
    print(f"\n\n{'='*80}")
    print(f"BATCH TEST SUMMARY")
    print(f"{'='*80}")
    print(f"{'Filename':<55} {'Records':>7} {'Fill%':>6} {'Review':>7} {'Time':>6}")
    print(f"{'-'*55} {'-'*7} {'-'*6} {'-'*7} {'-'*6}")

    success_count = 0
    total_records = 0
    total_fill_rates = []

    for s in results_summary:
        if s["status"] == "success":
            success_count += 1
            total_records += s["records"]
            total_fill_rates.append(s["fill_rate_pct"])
            name = s["filename"][:54]
            print(f"{name:<55} {s['records']:>7} {s['fill_rate_pct']:>5.1f}% {s['review_fields']:>7} {s['elapsed_sec']:>5.1f}s")
        else:
            name = s["filename"][:54]
            print(f"{name:<55} {'ERROR':>7} {'':>6} {'':>7} {s['elapsed_sec']:>5.1f}s")

    avg_fill = sum(total_fill_rates) / len(total_fill_rates) if total_fill_rates else 0
    print(f"{'-'*55} {'-'*7} {'-'*6} {'-'*7} {'-'*6}")
    print(f"{'TOTAL':<55} {total_records:>7} {avg_fill:>5.1f}% {'':>7} {total_elapsed:>5.1f}s")
    print(f"\nSuccess: {success_count}/{len(pdfs)}")

    # 保存报告
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump({
            "total_pdfs": len(pdfs),
            "success": success_count,
            "total_records": total_records,
            "avg_fill_rate_pct": round(avg_fill, 1),
            "total_elapsed_sec": round(total_elapsed, 1),
            "details": results_summary,
        }, f, ensure_ascii=False, indent=2)

    print(f"\nDetailed report saved to: {REPORT_PATH}")


if __name__ == "__main__":
    main()
