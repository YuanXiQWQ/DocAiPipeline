"""工厂内部单据 Excel 填充器：出库→原木出入库 / 入池+上机→刨切表 / 打包→表板统计。

复用 log_filler.py 中的 monkey-patch 来绕过透视表问题。
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

import openpyxl
from loguru import logger

from app.schemas import (
    LogOutputResult,
    PackingResult,
    SlicingResult,
    SoakPoolResult,
)

# 确保 monkey-patch 已执行
from app.export.log_filler import _patch_openpyxl_pivot_cache
_patch_openpyxl_pivot_cache()


# ------------------------------------------------------------------
# 通用工具
# ------------------------------------------------------------------

def _parse_date(date_str: str) -> datetime | None:
    """解析各种格式的日期字符串。"""
    if not date_str:
        return None
    # "26年2月6日"
    m = re.match(r"(\d{2,4})\u5e74(\d{1,2})\u6708(\d{1,2})\u65e5?", date_str)
    if m:
        y = int(m.group(1))
        if y < 100:
            y += 2000
        return datetime(y, int(m.group(2)), int(m.group(3)))
    # "YYYY-MM-DD"
    try:
        return datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        pass
    # "DD-MM-YYYY"
    try:
        return datetime.strptime(date_str, "%d-%m-%Y")
    except ValueError:
        pass
    # "26-2-2024" (可能是 YY-M-YYYY 误格式)
    m2 = re.match(r"(\d{2})-(\d{1,2})-(\d{4})", date_str)
    if m2:
        return datetime(int(m2.group(3)), int(m2.group(2)), int(m2.group(1)))
    logger.warning(f"无法解析日期: {date_str}")
    return None


def _find_first_empty_row(ws: Any, year_col: int = 1, start_row: int = 3) -> int:
    """找到 sheet 中第一个空行（基于年份列）。"""
    for row in range(start_row, ws.max_row + 2):
        val = ws.cell(row=row, column=year_col).value
        if val is None or val == "":
            return row
        try:
            if int(val) < 2000:
                return row
        except (ValueError, TypeError):
            pass
    return ws.max_row + 1


# ------------------------------------------------------------------
# 1. 出库表 → 原木出入库-3-3.xlsx 数据源表
# ------------------------------------------------------------------

class LogOutputFiller:
    """原木领用出库表 → 原木出入库数据源表（工序=领用出库）。"""

    SHEET_NAME = "数据源表"

    def __init__(self, template_path: Path):
        self.template_path = template_path

    def fill(
        self, results: list[LogOutputResult], output_path: Path,
        *, species: str = "欧橡", owner: str = "新公司",
    ) -> Path:
        wb = openpyxl.load_workbook(self.template_path)
        ws = wb[self.SHEET_NAME]
        start = _find_first_empty_row(ws)
        current = start
        count = 0

        for r in results:
            date_obj = _parse_date(r.meta.date)
            for e in r.entries:
                if e.diameter_cm <= 0:
                    continue
                if date_obj:
                    ws.cell(current, 1, date_obj.year)
                    ws.cell(current, 2, date_obj.month)
                    ws.cell(current, 3, date_obj)
                ws.cell(current, 4, "大锯车间")
                ws.cell(current, 5, "原料")
                ws.cell(current, 6, "领用出库")
                ws.cell(current, 7, species)
                ws.cell(current, 8, "原木")
                ws.cell(current, 9, r.meta.batch_id)
                ws.cell(current, 11, "")  # 车牌号（出库表无）
                ws.cell(current, 12, owner)
                ws.cell(current, 13, e.log_id)
                ws.cell(current, 19, e.diameter_cm)  # 径级
                ws.cell(current, 22, e.diameter_cm)  # 计尺宽
                current += 1
                count += 1

        logger.info(f"出库表写入 {count} 行到 '{self.SHEET_NAME}'")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        wb.save(str(output_path))
        return output_path


# ------------------------------------------------------------------
# 2. 入池表 → 刨切木方入池与上机表3-3.xlsx 原始表
# ------------------------------------------------------------------

class SoakPoolFiller:
    """刨切木方入池表 → 原始表。"""

    SHEET_NAME = "原始表"

    def __init__(self, template_path: Path):
        self.template_path = template_path

    def fill(
        self, results: list[SoakPoolResult], output_path: Path,
        *, owner: str = "新公司",
    ) -> Path:
        wb = openpyxl.load_workbook(self.template_path)
        ws = wb[self.SHEET_NAME]
        start = _find_first_empty_row(ws)
        current = start
        count = 0

        for r in results:
            date_obj = _parse_date(r.meta.date)
            for e in r.entries:
                if date_obj:
                    ws.cell(current, 1, date_obj.year)       # 入池年
                    ws.cell(current, 2, date_obj.month)      # 入池月
                    ws.cell(current, 3, date_obj)             # 入池日期
                ws.cell(current, 4, r.meta.pool_number)       # 池号
                ws.cell(current, 5, r.meta.batch_id)          # 批号
                ws.cell(current, 6, r.meta.owner or owner)    # 货物所有人
                ws.cell(current, 8, r.meta.craft or "刨切")   # 工艺
                ws.cell(current, 9, r.meta.board_thickness)   # 表板厚度
                ws.cell(current, 10, r.meta.material_name or "大方")  # 物料名称
                ws.cell(current, 11, e.length_mm)             # 长
                ws.cell(current, 12, e.width_mm)              # 宽
                ws.cell(current, 13, e.thickness_mm)          # 厚
                # 立方数 = L * W * T / 1e9
                if e.length_mm > 0 and e.width_mm > 0 and e.thickness_mm > 0:
                    vol = e.length_mm * e.width_mm * e.thickness_mm / 1e9
                    ws.cell(current, 14, round(vol, 3))       # 立方数
                ws.cell(current, 15, 1)                        # 根数（每行1根）
                current += 1
                count += 1

        logger.info(f"入池表写入 {count} 行到 '{self.SHEET_NAME}'")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        wb.save(str(output_path))
        return output_path


# ------------------------------------------------------------------
# 3. 上机表 → 刨切木方入池与上机表3-3.xlsx 原始表（上机部分）
# ------------------------------------------------------------------

class SlicingFiller:
    """刨切上机表 → 原始表（更新上机列）。

    注意：上机数据需要与已有的入池行匹配（按批号+序号），
    或追加到新行。当前简化为追加新行。
    """

    SHEET_NAME = "原始表"

    def __init__(self, template_path: Path):
        self.template_path = template_path

    def fill(
        self, results: list[SlicingResult], output_path: Path,
        *, owner: str = "新公司",
    ) -> Path:
        wb = openpyxl.load_workbook(self.template_path)
        ws = wb[self.SHEET_NAME]
        start = _find_first_empty_row(ws)
        current = start
        count = 0

        for r in results:
            date_obj = _parse_date(r.meta.date)
            for e in r.entries:
                # 入池信息留空（上机数据与入池分开填）
                ws.cell(current, 5, r.meta.batch_id)         # 批号
                ws.cell(current, 6, r.meta.owner or owner)   # 货物所有人
                ws.cell(current, 8, "刨切")                  # 工艺
                ws.cell(current, 10, "大方")                  # 物料名称
                ws.cell(current, 12, e.width_mm)              # 宽
                ws.cell(current, 13, e.thickness_mm)          # 厚
                # 上机列
                if date_obj:
                    ws.cell(current, 16, date_obj.year)       # 上机年
                    ws.cell(current, 17, date_obj.month)      # 上机月
                    ws.cell(current, 18, date_obj)             # 上机日期
                ws.cell(current, 19, 1)                        # 上机根数
                if e.core_thickness_mm > 0:
                    ws.cell(current, 20, e.core_thickness_mm) # 尾板厚度
                current += 1
                count += 1

        logger.info(f"上机表写入 {count} 行到 '{self.SHEET_NAME}'")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        wb.save(str(output_path))
        return output_path


# ------------------------------------------------------------------
# 4. 打包报表 → 表板统计-20260304.xlsx 数据源表
# ------------------------------------------------------------------

class PackingFiller:
    """表板打包报表 → 表板统计数据源表。"""

    SHEET_NAME = "数据源表"
    # 表板统计数据源表表头在 R2（R1是行次标签），数据从 R3 开始
    DATA_START_ROW = 3

    def __init__(self, template_path: Path):
        self.template_path = template_path

    def fill(
        self, results: list[PackingResult], output_path: Path,
        *, species: str = "欧橡", workshop: str = "大锯车间",
    ) -> Path:
        wb = openpyxl.load_workbook(self.template_path)
        ws = wb[self.SHEET_NAME]
        start = _find_first_empty_row(ws, year_col=1, start_row=self.DATA_START_ROW)
        current = start
        count = 0

        for r in results:
            date_obj = _parse_date(r.meta.date)
            for e in r.entries:
                if e.piece_count <= 0:
                    continue
                if date_obj:
                    ws.cell(current, 1, date_obj.year)        # 年
                    ws.cell(current, 2, date_obj.month)       # 月
                    ws.cell(current, 3, date_obj)              # 日期
                ws.cell(current, 4, workshop)                  # 车间
                ws.cell(current, 5, "产品")                   # 物料性质
                ws.cell(current, 6, "打包")                   # 工序
                ws.cell(current, 7, species)                   # 木种
                ws.cell(current, 8, "刨切表板")               # 货物名称
                ws.cell(current, 10, "")                       # 送货客户
                ws.cell(current, 12, self._map_owner(e.owner)) # 货物所有人
                ws.cell(current, 13, e.package_id)             # 包号
                ws.cell(current, 14, e.grade)                  # 等级
                ws.cell(current, 15, e.craft)                  # 工艺
                ws.cell(current, 18, e.length_mm)              # 长度
                ws.cell(current, 19, e.width_mm)               # 宽度
                ws.cell(current, 20, e.thickness)              # 厚度
                ws.cell(current, 21, e.calc_length_mm)         # 计尺长
                ws.cell(current, 22, e.calc_width_mm)          # 计尺宽
                ws.cell(current, 23, e.calc_thickness)         # 计尺厚
                ws.cell(current, 24, e.piece_count)            # 片数
                # 平方数：计尺长 * 计尺宽 * 片数 / 1e6
                if e.calc_length_mm > 0 and e.calc_width_mm > 0 and e.piece_count > 0:
                    area = e.calc_length_mm * e.calc_width_mm * e.piece_count / 1e6
                    ws.cell(current, 25, round(area, 3))       # m²
                current += 1
                count += 1

        logger.info(f"打包表写入 {count} 行到 '{self.SHEET_NAME}'")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        wb.save(str(output_path))
        return output_path

    @staticmethod
    def _map_owner(raw: str) -> str:
        """将手写的所有人名称映射为标准名称。"""
        if "王总" in raw or "王" in raw:
            return "王总公司"
        if "新" in raw or "LKV" in raw.upper():
            return "LKVO新公司"
        return raw
