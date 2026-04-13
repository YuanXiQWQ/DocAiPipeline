"""Phase 2 检尺单 → 原木出入库 Excel 填充测试。

使用之前保存的识别结果 JSON 直接填充，无需再调 VLM。
"""

import sys
import io
import json
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from app.export.log_filler import LogFiller
from app.schemas import LogMeasurementResult

# ------------------------------------------------------------------
# 路径配置
# ------------------------------------------------------------------

SAMPLES_DIR = Path(__file__).resolve().parent.parent / "文档" / "样例"
TEMPLATE = SAMPLES_DIR / "原木出入库-3-3.xlsx"
OUTPUT_DIR = Path(__file__).resolve().parent / "output"
RESULTS_JSON = OUTPUT_DIR / "log_extract_results.json"


def main():
    print("=== 检尺单 → 原木出入库 Excel 填充测试 ===\n")

    # 加载识别结果
    if not RESULTS_JSON.exists():
        print(f"✘ 识别结果不存在: {RESULTS_JSON}")
        print("  请先运行 test_log_extract.py")
        return

    with open(RESULTS_JSON, "r", encoding="utf-8") as f:
        raw = json.load(f)

    results = [LogMeasurementResult.model_validate(r) for r in raw]
    print(f"加载了 {len(results)} 页识别结果")

    # 统计有效数据行
    total_entries = sum(
        len([e for e in r.entries if e.length_m > 0 and e.diameter_cm > 0])
        for r in results
    )
    print(f"有效数据行: {total_entries}")

    # 填充
    filler = LogFiller(template_path=TEMPLATE)
    output_path = OUTPUT_DIR / "原木出入库-测试填充.xlsx"

    filler.fill(
        results=results,
        output_path=output_path,
        grade="厚皮",
        customer="农户",
    )

    # 验证输出
    print(f"\n✓ 输出保存至: {output_path}")

    # 用 pandas 快速检查写入的行
    import pandas as pd
    xls = pd.ExcelFile(output_path, engine="openpyxl")
    df = pd.read_excel(xls, sheet_name="数据源表", header=1)

    print(f"数据源表总行数: {len(df)}")

    # 显示最后几行
    pd.set_option("display.max_columns", 15)
    pd.set_option("display.width", 200)
    pd.set_option("display.max_colwidth", 12)

    # 找批次号为 260206-3 的行
    batch_rows = df[df["序号、批次号\nRedni broj"] == "260206-3"]
    if len(batch_rows) > 0:
        print(f"\n批次 260206-3 的行数: {len(batch_rows)}")
        cols = ["序号、批次号\nRedni broj", "包号/根号broj paketa",
                "长度\nDužina", "宽度/径级Širina", "数量Količina\nm3"]
        available = [c for c in cols if c in batch_rows.columns]
        if available:
            print(batch_rows[available].head(10).to_string())


if __name__ == "__main__":
    main()
