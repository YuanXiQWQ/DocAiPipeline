"""Phase 3 工厂单据 → Excel 填充测试。

使用之前保存的识别结果 JSON 填充，无需再调 VLM。
对于打包表需要重新跑 VLM（因为首次结果被截断了，已修复）。
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
from app.export.factory_filler import (
    LogOutputFiller,
    PackingFiller,
    SlicingFiller,
    SoakPoolFiller,
)
from app.schemas import (
    LogOutputResult,
    PackingResult,
    SlicingResult,
    SoakPoolResult,
)

SAMPLES_DIR = Path(__file__).resolve().parent.parent / "文档" / "样例"
OUTPUT_DIR = Path(__file__).resolve().parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)
RESULTS_JSON = OUTPUT_DIR / "factory_extract_results.json"


def load_results() -> dict[str, list]:
    """从已保存的 JSON 加载结果，按 doc_type 分组。"""
    if not RESULTS_JSON.exists():
        return {}
    with open(RESULTS_JSON, "r", encoding="utf-8") as f:
        raw = json.load(f)

    groups: dict[str, list] = {
        "log_output": [],
        "soak_pool": [],
        "slicing": [],
        "packing": [],
    }

    for item in raw:
        fname = item.get("filename", "")
        if "出库" in fname or "领用" in fname:
            groups["log_output"].append(LogOutputResult.model_validate(item))
        elif "入池" in fname:
            groups["soak_pool"].append(SoakPoolResult.model_validate(item))
        elif "上机" in fname:
            groups["slicing"].append(SlicingResult.model_validate(item))
        elif "打包" in fname:
            groups["packing"].append(PackingResult.model_validate(item))

    return groups


def rerun_packing() -> list[PackingResult]:
    """打包表首次被截断，重新跑 VLM。"""
    pdf_path = SAMPLES_DIR / "表板打包报表.pdf"
    doc = fitz.open(str(pdf_path))
    zoom = 300 / 72.0
    pix = doc[0].get_pixmap(matrix=fitz.Matrix(zoom, zoom))
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)
    img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
    doc.close()

    ext = FactoryExtractor()
    result = ext.extract(img, "packing", "表板打包报表.pdf", 1)
    return [result]  # type: ignore[list-item]


def main():
    print("=== Phase 3 工厂单据 → Excel 填充测试 ===\n")

    groups = load_results()

    # --- 1. 出库表 ---
    log_output = groups.get("log_output", [])
    if log_output:
        print(f"[出库表] {len(log_output)} 页，共 {sum(len(r.entries) for r in log_output)} 行")
        template = SAMPLES_DIR / "原木出入库-3-3.xlsx"
        filler = LogOutputFiller(template)
        out = filler.fill(log_output, OUTPUT_DIR / "原木出入库-出库填充.xlsx")
        print(f"  → {out}\n")

    # --- 2. 入池表 ---
    soak_pool = groups.get("soak_pool", [])
    if soak_pool:
        print(f"[入池表] {len(soak_pool)} 页，共 {sum(len(r.entries) for r in soak_pool)} 行")
        template = SAMPLES_DIR / "刨切木方入池与上机表3-3.xlsx"
        filler2 = SoakPoolFiller(template)
        out = filler2.fill(soak_pool, OUTPUT_DIR / "刨切表-入池填充.xlsx")
        print(f"  → {out}\n")

    # --- 3. 上机表 ---
    slicing = groups.get("slicing", [])
    if slicing:
        print(f"[上机表] {len(slicing)} 页，共 {sum(len(r.entries) for r in slicing)} 行")
        template = SAMPLES_DIR / "刨切木方入池与上机表3-3.xlsx"
        filler3 = SlicingFiller(template)
        out = filler3.fill(slicing, OUTPUT_DIR / "刨切表-上机填充.xlsx")
        print(f"  → {out}\n")

    # --- 4. 打包表 ---
    packing = groups.get("packing", [])
    if not packing or not packing[0].entries:
        print("[打包表] 首次结果被截断，重新调用 VLM...")
        packing = rerun_packing()
    print(f"[打包表] {len(packing)} 页，共 {sum(len(r.entries) for r in packing)} 行")
    template = SAMPLES_DIR / "表板统计  - 20260304.xlsx"
    filler4 = PackingFiller(template)
    out = filler4.fill(packing, OUTPUT_DIR / "表板统计-打包填充.xlsx")
    print(f"  → {out}\n")

    print("✓ 全部完成")


if __name__ == "__main__":
    main()
