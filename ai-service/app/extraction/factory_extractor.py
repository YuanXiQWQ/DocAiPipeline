"""工厂内部单据 VLM 抽取器：支持出库表、入池表、上机表、打包报表。

统一调用 VLM，根据 doc_type 切换专用 prompt，返回对应的结构化结果。
"""

from __future__ import annotations

import base64
import json
from collections.abc import Callable

import cv2
import numpy as np
from loguru import logger
from openai import OpenAI
from openai.types.chat import (
    ChatCompletionContentPartImageParam,
    ChatCompletionContentPartParam,
    ChatCompletionContentPartTextParam,
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
)
from pydantic import BaseModel

from app.config import settings
from app.schemas import (
    LogOutputEntry, LogOutputMeta, LogOutputResult,
    PackingEntry, PackingMeta, PackingResult,
    SlicingEntry, SlicingMeta, SlicingResult,
    SoakPoolEntry, SoakPoolMeta, SoakPoolResult,
)

# ------------------------------------------------------------------
# 专用 Prompt（英文给模型）
# ------------------------------------------------------------------

PROMPT_LOG_OUTPUT = """You are an expert OCR assistant for timber factory documents.

You will receive a scanned image of a "原木领料表" (Log Output / Withdrawal Table).
This is a handwritten table where logs are withdrawn from inventory for processing.

STRUCTURE:
- Title: "原木领料表" or "TERRA 原木检尺 码单 Log list" (used for output)
- The page may contain TWO side-by-side tables (left and right), each with different batch IDs
- Each table has columns: 编号Br. (log ID) | K/CM (diameter in cm)
- NOTE: there is NO length column — only log_id and diameter
- Bottom has totals: count (根数) and volume (m³)

HEADER FIELDS to extract:
- date, batch_id (批次号), workshop (车间/destination), owner (货物所有人)

For each table (left and right):
- Extract entries with: row, log_id, diameter_cm
- Extract totals: total_count, total_volume_m3

If there are TWO tables, return them as separate objects in a "tables" array.

Return JSON:
{
  "tables": [
    {
      "date": "",
      "batch_id": "",
      "workshop": "",
      "owner": "",
      "total_count": null,
      "total_volume_m3": null,
      "entries": [
        {"row": 1, "log_id": "4026", "diameter_cm": 688}
      ]
    }
  ]
}

CRITICAL: diameter values are typically 3-4 digit numbers (e.g., 688, 749, 725, 741).
These are raw CM measurements, NOT the same as the 2-digit "径级" used elsewhere.
Read handwritten digits carefully: distinguish 0/6, 1/7, 3/5, 4/9.
If uncertain, append [?].

NOISE SUPPRESSION: Ignore dry pen strokes, ink spots, scanner line artifacts, and stains.
Crossed-out values should be replaced with the corrected rewritten value.

Return ONLY valid JSON. No markdown, no extra text.
"""

PROMPT_SOAK_POOL = """You are an expert OCR assistant for timber factory documents.

You will receive a scanned image of a "刨切原木入池记录表" (Soak Pool Entry Table).
This records wood blocks being placed into a soaking pool before slicing.

STRUCTURE:
- Title: "刨切原木入池记录表"
- Header: 工位 (worker name), 入池批次号 (batch ID like 260228-6)
- Table columns: 序号 | 长宽 (e.g. "1810x225x300") | 宽度/直径 | 厚度 | 体积 | 供货商
- The first row may have a full dimension spec "LxWxT" (mm); subsequent rows may only have individual values
- There are typically 6 columns of handwritten 3-digit numbers per row (representing multiple blocks)

Each row represents one wood block with dimensions in mm (typically 200-400 range).
The columns after "长宽" represent: width(宽度), thickness(厚度), volume(体积), and supplier(供货商).

IMPORTANT: Looking at the actual table structure more carefully:
- Column 1: 序号 (row number)  
- Column 2: 长宽 (length description, may include "1810x225x" prefix for row 1)
- Columns 3-6: These appear to be widths/thicknesses of MULTIPLE blocks in that row
- Each cell contains a 3-digit number (200-400 range, mm)
- The table has 24 rows

Return JSON:
{
  "date": "",
  "batch_id": "",
  "pool_number": "",
  "worker": "",
  "owner": "",
  "craft": "",
  "board_thickness": null,
  "material_name": "",
  "total_count": null,
  "total_volume_m3": null,
  "entries": [
    {"row": 1, "length_mm": 1810, "width_mm": 300, "thickness_mm": 300, "volume_m3": null, "supplier": ""}
  ]
}

NOISE SUPPRESSION: Ignore dry pen strokes, ink spots, scanner line artifacts, and stains.
Crossed-out values should be replaced with the corrected rewritten value.

Return ONLY valid JSON. No markdown, no extra text.
"""

PROMPT_SLICING = """You are an expert OCR assistant for timber factory documents.

You will receive a scanned image of a "刨切车间刨切上机产量日报表" (Slicing Machine Daily Report).
This records wood blocks being loaded onto the slicing machine.

IMPORTANT: This table is ROTATED 90° clockwise. The page is in landscape orientation
but the scan may be in portrait. Read the table with this rotation in mind.

STRUCTURE (after rotation):
- Title: "刨切车间刨切上机产量日报表"
- Header: 木种名称 (species), 批号 (batch ID), 机台号 (machine ID), 上机日期 (date)
- Columns (horizontal after rotation): 序号 | 大方规格(spec) | 大方厚度 | 大方宽度 | 刨切厚度 | 木芯序号 | 木芯厚度 | 尾板(tail board)
- Each row = one wood block loaded onto the machine
- Bottom area: 合计产量, 实际产出(m²), 木芯(m²)

The "大方规格" is like "2.5×2.60" or "1.7×2.40" (length×width in some unit).
厚度/宽度 values are typically 3-digit mm numbers (200-500).

Return JSON:
{
  "date": "",
  "batch_id": "",
  "machine_id": "",
  "species": "",
  "owner": "",
  "total_logs": null,
  "total_volume_m3": null,
  "total_output_m2": null,
  "entries": [
    {"row": 1, "log_spec": "2.5×2.60", "thickness_mm": 370, "width_mm": 340, "slice_thickness": 2.0, "core_thickness_mm": 60, "core_count": 1}
  ]
}

NOISE SUPPRESSION: Ignore dry pen strokes, ink spots, scanner line artifacts, and stains.
Crossed-out values should be replaced with the corrected rewritten value.
This table may be rotated — artifacts along the original page edges are scanner noise.

Return ONLY valid JSON. No markdown, no extra text.
"""

PROMPT_PACKING = """You are an expert OCR assistant for timber factory documents.

You will receive a scanned image of a "刨切表板剪切打包记录表" (Veneer Packing Report).
This records finished veneer sheets being cut and packed.

STRUCTURE:
- Title: "刨切表板剪切打包记录表"
- Table columns:
  序号 | 货物所有人 | 包号 | 等级 | 工艺 | 长度 | 宽度 | 厚度 | 计尺长度(MM) | 计尺宽度(MM) | 计尺厚度 | 片数 | 平方数 | 备注

- 货物所有人: e.g. "王总1", "新华公司"
- 包号: e.g. "TW26022504", "TB26022601"
- 等级: e.g. "ABCDE"
- 工艺: e.g. "刨切"
- 长度/宽度: 3-4 digit mm values (540-1740)
- 厚度: decimal like 1.2, 2.0
- 片数: integer (16-1700)
- 平方数: integer or decimal

Some rows only have partial data (length, calc_length, piece_count) — the owner/package_id
carries forward from the previous row that has them.

Return JSON:
{
  "date": "",
  "entries": [
    {
      "row": 1,
      "owner": "王总1",
      "package_id": "TW26022504",
      "grade": "ABCDE",
      "craft": "刨切",
      "length_mm": 1740,
      "width_mm": 205,
      "thickness": 1.2,
      "calc_length_mm": 1700,
      "calc_width_mm": 190,
      "calc_thickness": 0,
      "piece_count": 1350,
      "area_m2": 0
    }
  ]
}

IMPORTANT: Some rows are continuation rows with only length and piece_count filled.
For these rows, set owner/package_id/grade/craft to "" (empty string).
The caller will carry forward from the previous non-empty row.
If uncertain about a value, append [?].

NOISE SUPPRESSION: Ignore dry pen strokes, ink spots, scanner line artifacts, and stains.
Crossed-out values should be replaced with the corrected rewritten value.

Return ONLY valid JSON. No markdown, no extra text.
"""

# prompt 注册表
PROMPTS = {
    "log_output": PROMPT_LOG_OUTPUT,
    "soak_pool": PROMPT_SOAK_POOL,
    "slicing": PROMPT_SLICING,
    "packing": PROMPT_PACKING,
}


class FactoryExtractor:
    """工厂内部单据统一 VLM 抽取器。"""

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key or settings.openai_api_key
        self.model = model or settings.openai_model
        if not self.api_key:
            logger.warning("OpenAI API key not set — FactoryExtractor will fail.")
            self.client = None
        else:
            self.client = OpenAI(
                api_key=self.api_key,
                **({"base_url": settings.openai_base_url} if settings.openai_base_url else {}),
            )

    # ------------------------------------------------------------------
    # 主入口
    # ------------------------------------------------------------------

    def extract(
        self,
        image: np.ndarray,
        doc_type: str,
        filename: str = "",
        page: int = 1,
    ) -> BaseModel:
        """识别工厂单据页面，返回对应的结构化结果。

        参数:
            image: BGR numpy 图像。
            doc_type: 文档类型 ("log_output" | "soak_pool" | "slicing" | "packing")。
            filename: 源文件名。
            page: 页码。
        """
        if self.client is None:
            raise RuntimeError("OpenAI client not initialized. Set OPENAI_API_KEY.")
        if doc_type not in PROMPTS:
            raise ValueError(f"不支持的文档类型: {doc_type}")

        b64_image = self._encode_image(image)
        prompt = PROMPTS[doc_type]

        # 打包表行数多，需要更大的 token 限制
        max_tokens = 8000 if doc_type == "packing" else 4000
        raw_text = self._call_vlm(prompt, b64_image, max_tokens=max_tokens)
        logger.debug(f"FactoryExtractor({doc_type}) raw: {len(raw_text)} chars")

        data = self._parse_json(raw_text)
        if data is None:
            # 返回空结果
            return self._empty_result(doc_type, filename, page, raw_text)

        # 根据类型解析
        parsers: dict[str, Callable[[dict, str, int], BaseModel]] = {
            "log_output": self._parse_log_output,
            "soak_pool": self._parse_soak_pool,
            "slicing": self._parse_slicing,
            "packing": self._parse_packing,
        }
        return parsers[doc_type](data, filename, page)

    # ------------------------------------------------------------------
    # VLM 调用
    # ------------------------------------------------------------------

    def _call_vlm(
        self, system_prompt: str, b64_image: str, *, max_tokens: int = 4000,
    ) -> str:
        """调用 VLM 并返回原始文本。"""
        assert self.client is not None

        sys_msg: ChatCompletionSystemMessageParam = {
            "role": "system",
            "content": system_prompt,
        }
        content_parts: list[ChatCompletionContentPartParam] = [
            ChatCompletionContentPartTextParam(
                type="text",
                text="Extract all data from this factory document. Read every handwritten number carefully.",
            ),
            ChatCompletionContentPartImageParam(
                type="image_url",
                image_url={
                    "url": f"data:image/jpeg;base64,{b64_image}",
                    "detail": "high",
                },
            ),
        ]
        user_msg: ChatCompletionUserMessageParam = {
            "role": "user",
            "content": content_parts,
        }
        messages: list[ChatCompletionMessageParam] = [sys_msg, user_msg]

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=0.1,
        )
        content = response.choices[0].message.content
        assert content is not None, "VLM returned empty content"
        return content.strip()

    # ------------------------------------------------------------------
    # JSON 解析
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_json(raw_text: str) -> dict | None:
        """去除 markdown fence 并解析 JSON。"""
        text = raw_text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:])
            if text.endswith("```"):
                text = text[:-3].strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse failed: {e}\nRaw: {raw_text[:500]}")
            return None

    @staticmethod
    def _safe_int(val: object, default: int = 0) -> int:
        """安全转换为 int，处理 [?] 标记。"""
        s = str(val).replace("[?]", "").replace(",", ".").strip()
        try:
            return int(round(float(s))) if s else default
        except (ValueError, TypeError):
            return default

    @staticmethod
    def _safe_float(val: object, default: float = 0.0) -> float:
        """安全转换为 float，处理 [?] 标记。"""
        s = str(val).replace("[?]", "").replace(",", ".").strip()
        try:
            return float(s) if s else default
        except (ValueError, TypeError):
            return default

    # ------------------------------------------------------------------
    # 各类型解析器
    # ------------------------------------------------------------------

    def _parse_log_output(
        self, data: dict, filename: str, page: int,
    ) -> LogOutputResult:
        """解析出库表。"""
        # 出库表可能有多个 table（左右分区）
        tables = data.get("tables", [data])
        all_entries: list[LogOutputEntry] = []
        meta = LogOutputMeta()

        for table in tables:
            m = LogOutputMeta(
                date=str(table.get("date", "")),
                batch_id=str(table.get("batch_id", "")),
                workshop=str(table.get("workshop", "")),
                owner=str(table.get("owner", "")),
                total_count=table.get("total_count"),
                total_volume_m3=table.get("total_volume_m3"),
            )
            # 用第一个非空 meta
            if not meta.batch_id and m.batch_id:
                meta = m

            for raw in table.get("entries", []):
                has_uncertain = "[?]" in str(raw)
                entry = LogOutputEntry(
                    row_number=self._safe_int(raw.get("row", len(all_entries) + 1)),
                    log_id=str(raw.get("log_id", "")),
                    diameter_cm=self._safe_int(raw.get("diameter_cm", 0)),
                    needs_review=has_uncertain,
                    review_reason="VLM 标记不确定" if has_uncertain else None,
                )
                all_entries.append(entry)

        return LogOutputResult(
            filename=filename, page=page, meta=meta,
            entries=all_entries,
        )

    def _parse_soak_pool(
        self, data: dict, filename: str, page: int,
    ) -> SoakPoolResult:
        """解析入池表。"""
        meta = SoakPoolMeta(
            date=str(data.get("date", "")),
            batch_id=str(data.get("batch_id", "")),
            pool_number=str(data.get("pool_number", "")),
            worker=str(data.get("worker", "")),
            owner=str(data.get("owner", "")),
            craft=str(data.get("craft", "")),
            board_thickness=data.get("board_thickness"),
            material_name=str(data.get("material_name", "")),
            total_count=data.get("total_count"),
            total_volume_m3=data.get("total_volume_m3"),
        )

        entries: list[SoakPoolEntry] = []
        for raw in data.get("entries", []):
            has_uncertain = "[?]" in str(raw)
            entry = SoakPoolEntry(
                row_number=self._safe_int(raw.get("row", len(entries) + 1)),
                length_mm=self._safe_int(raw.get("length_mm", 0)),
                width_mm=self._safe_int(raw.get("width_mm", 0)),
                thickness_mm=self._safe_int(raw.get("thickness_mm", 0)),
                volume_m3=self._safe_float(raw["volume_m3"]) if raw.get("volume_m3") else None,
                supplier=str(raw.get("supplier", "")),
                needs_review=has_uncertain,
                review_reason="VLM 标记不确定" if has_uncertain else None,
            )
            entries.append(entry)

        return SoakPoolResult(
            filename=filename, page=page, meta=meta, entries=entries,
        )

    def _parse_slicing(
        self, data: dict, filename: str, page: int,
    ) -> SlicingResult:
        """解析上机表。"""
        meta = SlicingMeta(
            date=str(data.get("date", "")),
            batch_id=str(data.get("batch_id", "")),
            machine_id=str(data.get("machine_id", "")),
            species=str(data.get("species", "")),
            owner=str(data.get("owner", "")),
            total_logs=data.get("total_logs"),
            total_volume_m3=data.get("total_volume_m3"),
            total_output_m2=data.get("total_output_m2"),
        )

        entries: list[SlicingEntry] = []
        for raw in data.get("entries", []):
            has_uncertain = "[?]" in str(raw)
            entry = SlicingEntry(
                row_number=self._safe_int(raw.get("row", len(entries) + 1)),
                log_spec=str(raw.get("log_spec", "")),
                thickness_mm=self._safe_int(raw.get("thickness_mm", 0)),
                width_mm=self._safe_int(raw.get("width_mm", 0)),
                slice_thickness=self._safe_float(raw.get("slice_thickness", 0)),
                core_thickness_mm=self._safe_int(raw.get("core_thickness_mm", 0)),
                core_count=self._safe_int(raw.get("core_count", 0)),
                needs_review=has_uncertain,
                review_reason="VLM 标记不确定" if has_uncertain else None,
            )
            entries.append(entry)

        return SlicingResult(
            filename=filename, page=page, meta=meta, entries=entries,
        )

    def _parse_packing(
        self, data: dict, filename: str, page: int,
    ) -> PackingResult:
        """解析打包报表。"""
        meta = PackingMeta(date=str(data.get("date", "")))

        entries: list[PackingEntry] = []
        # 继承字段
        last_owner = ""
        last_package_id = ""
        last_grade = ""
        last_craft = ""

        for raw in data.get("entries", []):
            has_uncertain = "[?]" in str(raw)
            owner = str(raw.get("owner", "")).strip()
            pkg_id = str(raw.get("package_id", "")).strip()
            grade = str(raw.get("grade", "")).strip()
            craft = str(raw.get("craft", "")).strip()

            # 继承：如果当前行为空，沿用上一行
            if owner:
                last_owner = owner
            else:
                owner = last_owner
            if pkg_id:
                last_package_id = pkg_id
            else:
                pkg_id = last_package_id
            if grade:
                last_grade = grade
            else:
                grade = last_grade
            if craft:
                last_craft = craft
            else:
                craft = last_craft

            entry = PackingEntry(
                row_number=self._safe_int(raw.get("row", len(entries) + 1)),
                owner=owner,
                package_id=pkg_id,
                grade=grade,
                craft=craft,
                length_mm=self._safe_int(raw.get("length_mm", 0)),
                width_mm=self._safe_int(raw.get("width_mm", 0)),
                thickness=self._safe_float(raw.get("thickness", 0)),
                calc_length_mm=self._safe_int(raw.get("calc_length_mm", 0)),
                calc_width_mm=self._safe_int(raw.get("calc_width_mm", 0)),
                calc_thickness=self._safe_float(raw.get("calc_thickness", 0)),
                piece_count=self._safe_int(raw.get("piece_count", 0)),
                area_m2=self._safe_float(raw.get("area_m2", 0)),
                needs_review=has_uncertain,
                review_reason="VLM 标记不确定" if has_uncertain else None,
            )
            entries.append(entry)

        return PackingResult(
            filename=filename, page=page, meta=meta, entries=entries,
        )

    # ------------------------------------------------------------------
    # 空结果 / 工具方法
    # ------------------------------------------------------------------

    @staticmethod
    def _empty_result(
        doc_type: str, filename: str, page: int, raw_text: str,
    ) -> BaseModel:
        """VLM 返回无效 JSON 时构造空结果。"""
        warn = f"VLM 响应不是有效 JSON: {raw_text[:200]}"
        constructors: dict[str, type[BaseModel]] = {
            "log_output": LogOutputResult,
            "soak_pool": SoakPoolResult,
            "slicing": SlicingResult,
            "packing": PackingResult,
        }
        cls = constructors[doc_type]
        # 所有 Result 类都接受 filename, page, meta, warnings
        meta_map = {
            "log_output": LogOutputMeta(),
            "soak_pool": SoakPoolMeta(),
            "slicing": SlicingMeta(),
            "packing": PackingMeta(),
        }
        return cls(  # type: ignore[call-arg]
            filename=filename, page=page,
            meta=meta_map[doc_type], warnings=[warn],
        )

    @staticmethod
    def _encode_image(image: np.ndarray) -> str:
        """将 BGR numpy 图像编码为 base64 JPEG 字符串。"""
        success, buffer = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 95])
        if not success:
            raise ValueError("Failed to encode image to JPEG")
        return base64.b64encode(buffer).decode("utf-8")
