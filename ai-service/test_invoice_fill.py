"""Test: fill 纸质发票记录表 from extracted pipeline results.

Uses a batch of related PDFs (c4/5659 batch):
  - Deklaracija (customs declaration)
  - Racun (broker invoice)
  - SKEN.36 (scanned docs: commercial invoice, EUR.1, inspection cert, CMR, eFaktura)
"""

import sys
import io
import json
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from app.export.invoice_filler import InvoiceFiller
from app.schemas import PipelineResult

TEMPLATE = Path(__file__).resolve().parent.parent / "文档" / "样例" / "纸质发票记录表-20260303.xlsx"
OUTPUT_DIR = Path(__file__).resolve().parent / "output"

# Load pipeline results from JSON
RESULT_FILES = [
    OUTPUT_DIR / "Deklaracija_42072_C4_5659_2026 [JCI00158583].json",
    OUTPUT_DIR / "Racun.json",
    OUTPUT_DIR / "SKEN.36.json",
]


def load_result(path: Path) -> PipelineResult:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return PipelineResult(**data)


def main():
    print("=== Test: Invoice Template Fill ===\n")

    # Check files exist
    assert TEMPLATE.exists(), f"Template not found: {TEMPLATE}"
    for rf in RESULT_FILES:
        assert rf.exists(), f"Result not found: {rf}"

    # Load results
    results = [load_result(rf) for rf in RESULT_FILES]
    total_records = sum(r.total_documents_detected for r in results)
    print(f"Loaded {len(results)} result files with {total_records} total records")

    # Show what documents we have
    for r in results:
        print(f"\n  {r.filename}:")
        for rec in r.records:
            doc_type = ""
            for f in rec.fields:
                if f.field_name == "document_type":
                    doc_type = f.value
                    break
            print(f"    Record {rec.record_index} (page {rec.source_page}): {doc_type}")

    # Fill template
    filler = InvoiceFiller(template_path=TEMPLATE, owner="新A", company="AL")
    output_path = OUTPUT_DIR / "纸质发票记录表-filled.xlsx"
    filler.fill(results, output_path, batch_id="C4-5659")

    # Verify: read back and show new rows
    import openpyxl
    wb = openpyxl.load_workbook(output_path, data_only=False)
    ws = wb["原始汇总"]

    print(f"\n{'='*80}")
    print("FILLED ROWS:")
    print(f"{'='*80}")

    # Find where our data starts (after existing 18 rows)
    headers = ["所属人", "公司名", "供应商名称", "性质", "名称", "日期",
               "发票号", "编号", "FSC", "供应商/备注", "外币金额", "数量"]

    for row_idx in range(3, ws.max_row + 1):
        val_a = ws.cell(row=row_idx, column=1).value
        if val_a is None:
            break

    # Show new rows (from row 21 onward, since template has 18 data rows + 2 header rows)
    new_start = 21  # row 3 + 18 existing = row 21
    for row_idx in range(new_start, ws.max_row + 1):
        val_a = ws.cell(row=row_idx, column=1).value
        if val_a is None:
            break
        print(f"\n  Row {row_idx}:")
        for col_idx, header in enumerate(headers, 1):
            val = ws.cell(row=row_idx, column=col_idx).value
            if val is not None:
                print(f"    {header}: {val}")

    wb.close()
    print(f"\n✓ Output saved to: {output_path}")


if __name__ == "__main__":
    main()
