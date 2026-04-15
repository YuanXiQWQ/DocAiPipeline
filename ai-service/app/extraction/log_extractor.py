"""检尺单 VLM 抽取器：从原木检尺单/码单图像中抽取逐根数据。

支持三种页面类型：
1. 手写检尺单（TERRA 原木检尺 码单 Log list）
2. 打印码单（克罗地亚林业局格式，含编号/长/径/体积）
3. 入库确认表（Specifikacija lista za kupovinu trupaca）
"""

from __future__ import annotations

import base64
import json
import math
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

from app.config import settings
from app.schemas import LogEntry, LogMeasurementResult, LogSheetMeta

# ------------------------------------------------------------------
# 系统提示词：指导 VLM 识别检尺单（英文 prompt 给模型）
# ------------------------------------------------------------------

LOG_SYSTEM_PROMPT = """You are an expert OCR assistant specializing in timber / wood log measurement sheets.

You will receive a scanned image of a page from a log measurement document. It could be one of:

1. **Handwritten log measurement sheet** ("TERRA 原木检尺 码单 Log list")
   - Has a table with columns: 编号Br. | 长度M | 直径CM
   - May have TWO side-by-side tables (left + right) on the same page
   - Header contains: date (日期), batch ID (批次号), vehicle plate (车牌号)
   - Bottom may have totals: 实际检尺数量合计 m³, 根数

2. **Printed tally sheet** (Croatian forestry format)
   - Header: BROJ ŠUM. ŠIF. L D OBUJAM
   - Each row: log_id(6-digit), species_code, sort_code, length(cm), diameter(cm), volume(m³)
   - Bottom has summary: UK. KOM. (total count), UK. MASA (total volume)

3. **Intake confirmation form** ("Specifikacija lista za kupovinu trupaca" / "原木/大方采购验收入库单")
   - A summary table with: batch_id, vehicle plate, total count, confirmed volume, measured volume
   - Often scanned sideways (rotated 90° or 180°)

4. **Handwritten re-check sheet** - only has log IDs (编号) listed, used to cross-reference with the printed tally. Length and diameter columns are empty.

INSTRUCTIONS:
- Determine the sheet_type: "handwritten", "printed_tally", "confirmation", or "id_list_only"
- Extract ALL header/metadata fields you can find
- For types 1 and 2: extract EVERY row from the table(s) as entries
- For handwritten sheets with TWO side-by-side tables, extract BOTH tables. The left table rows come first, then right table rows.
- For confirmation forms: extract only metadata (totals), no individual entries
- For id_list_only: extract log IDs, set length=0 and diameter=0

CRITICAL RULES for handwritten numbers:
1. Length is typically 2.0 - 5.5 meters. Values like "4.5", "3.9", "2.1" are common.
2. Diameter is typically 35 - 65 cm. Values like "42", "47", "56", "61" are common.
3. Carefully distinguish: 1/7, 3/5, 4/9, 6/0 in handwriting.
4. If TWO numbers are written close together with a decimal point, the first part (before dot/comma) is units and the second is tenths: "4.5" means 4.5 meters.
5. If a value is ambiguous, append [?] to it.
6. European decimal format: comma is decimal separator (e.g., "0,48" = 0.48 m³).

NOISE SUPPRESSION rules:
7. DRY PEN STROKES in blank areas (to get ink flowing) are NOT characters — ignore "11111", "/////" artifacts.
8. Ink spots, scanner dirt, or short stray lines are NOT punctuation or digits — ignore them.
9. Suspicious dots between digits: if "2.05" appears but "205" makes more sense in context (e.g. diameter 205mm → 20cm), prefer the value without the dot.
10. Scanner line artifacts at page edges: ignore long vertical/horizontal lines.
11. Crossed-out values: read the CORRECTED (rewritten) value, not the original.

Return a JSON object with this exact structure:
{
  "sheet_type": "handwritten" | "printed_tally" | "confirmation" | "id_list_only",
  "date": "YYYY-MM-DD or original format if unclear",
  "batch_id": "",
  "vehicle_plate": "",
  "supplier": "",
  "species": "",
  "total_count": null or integer,
  "total_volume_m3": null or float,
  "entries": [
    {
      "row": 1,
      "log_id": "",
      "length_m": 4.5,
      "diameter_cm": 42,
      "volume_m3": null or 0.48
    }
  ]
}

For confirmation pages, "entries" should be an empty array [].
Return ONLY valid JSON. No markdown fences, no extra text.
"""


class LogExtractor:
    """从检尺单图像中抽取逐根原木数据。"""

    # 合理性校验阈值
    MIN_LENGTH_M = 1.5
    MAX_LENGTH_M = 7.0
    MIN_DIAMETER_CM = 20
    MAX_DIAMETER_CM = 80

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key or settings.openai_api_key
        self.model = model or settings.openai_model
        if not self.api_key:
            logger.warning("OpenAI API key not set — LogExtractor will fail.")
            self.client = None
        else:
            self.client = OpenAI(
                api_key=self.api_key,
                **({"base_url": settings.openai_base_url} if settings.openai_base_url else {}),
            )

    # ------------------------------------------------------------------
    # 主入口
    # ------------------------------------------------------------------

    def extract_page(
        self,
        image: np.ndarray,
        filename: str = "",
        page: int = 1,
    ) -> LogMeasurementResult:
        """识别单页检尺单图像，返回结构化结果。"""
        if self.client is None:
            raise RuntimeError("OpenAI client not initialized. Set OPENAI_API_KEY.")

        b64_image = self._encode_image(image)

        try:
            sys_msg: ChatCompletionSystemMessageParam = {
                "role": "system",
                "content": LOG_SYSTEM_PROMPT,
            }
            content_parts: list[ChatCompletionContentPartParam] = [
                ChatCompletionContentPartTextParam(
                    type="text",
                    text="Extract all log measurement data from this page. "
                         "Read every handwritten number carefully.",
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
                max_tokens=4000,
                temperature=0.1,
            )

            content = response.choices[0].message.content
            assert content is not None, "VLM returned empty content"
            raw_text = content.strip()
            logger.debug(f"LogExtractor raw response: {len(raw_text)} chars")

            result = self._parse_response(raw_text, filename, page)

            # 校验
            self._validate(result)

            return result

        except Exception as e:
            logger.error(f"LogExtractor failed on {filename} p{page}: {e}")
            raise

    # ------------------------------------------------------------------
    # 解析 VLM 响应
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_response(
        raw_text: str,
        filename: str,
        page: int,
    ) -> LogMeasurementResult:
        """将 VLM JSON 响应解析为 LogMeasurementResult。"""
        text = raw_text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:])
            if text.endswith("```"):
                text = text[:-3].strip()

        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse failed: {e}\nRaw: {raw_text[:500]}")
            return LogMeasurementResult(
                filename=filename,
                page=page,
                meta=LogSheetMeta(),
                warnings=[f"VLM 响应不是有效 JSON: {e}"],
            )

        # 解析元数据
        meta = LogSheetMeta(
            sheet_type=data.get("sheet_type", ""),
            date=str(data.get("date", "")),
            batch_id=str(data.get("batch_id", "")),
            vehicle_plate=str(data.get("vehicle_plate", "")),
            supplier=str(data.get("supplier", "")),
            species=str(data.get("species", "")),
            total_count=data.get("total_count"),
            total_volume_m3=data.get("total_volume_m3"),
        )

        # 解析逐行数据
        entries: list[LogEntry] = []
        for raw_entry in data.get("entries", []):
            try:
                length_raw = raw_entry.get("length_m", 0)
                diameter_raw = raw_entry.get("diameter_cm", 0)

                # 处理可能带 [?] 的值
                needs_review = False
                review_reason = None

                length_str = str(length_raw).replace("[?]", "").strip()
                diameter_str = str(diameter_raw).replace("[?]", "").strip()

                if "[?]" in str(length_raw) or "[?]" in str(diameter_raw):
                    needs_review = True
                    review_reason = "VLM 标记为不确定"

                # 欧洲小数格式：逗号→点
                length_str = length_str.replace(",", ".")
                diameter_str = diameter_str.replace(",", ".")

                length_val = float(length_str) if length_str else 0.0
                diameter_val = int(round(float(diameter_str))) if diameter_str else 0

                volume_raw = raw_entry.get("volume_m3")
                volume_val: float | None = None
                if volume_raw is not None:
                    vol_str = str(volume_raw).replace("[?]", "").replace(",", ".").strip()
                    if vol_str:
                        try:
                            volume_val = float(vol_str)
                        except ValueError:
                            pass

                entry = LogEntry(
                    row_number=int(raw_entry.get("row", len(entries) + 1)),
                    log_id=str(raw_entry.get("log_id", "")),
                    length_m=length_val,
                    diameter_cm=diameter_val,
                    volume_m3=volume_val,
                    needs_review=needs_review,
                    review_reason=review_reason,
                )
                entries.append(entry)
            except (ValueError, TypeError) as e:
                logger.warning(f"跳过无效行: {raw_entry} — {e}")

        return LogMeasurementResult(
            filename=filename,
            page=page,
            meta=meta,
            entries=entries,
        )

    # ------------------------------------------------------------------
    # 校验
    # ------------------------------------------------------------------

    def _validate(self, result: LogMeasurementResult) -> None:
        """对识别结果进行多层校验。"""
        warnings: list[str] = []

        # ① 单根合理性校验
        for entry in result.entries:
            if entry.length_m > 0 and not (
                self.MIN_LENGTH_M <= entry.length_m <= self.MAX_LENGTH_M
            ):
                entry.needs_review = True
                entry.review_reason = (
                    f"长度 {entry.length_m}m 超出合理范围 "
                    f"[{self.MIN_LENGTH_M}-{self.MAX_LENGTH_M}]"
                )
                warnings.append(
                    f"行{entry.row_number}: 长度 {entry.length_m}m 异常"
                )

            if entry.diameter_cm > 0 and not (
                self.MIN_DIAMETER_CM <= entry.diameter_cm <= self.MAX_DIAMETER_CM
            ):
                entry.needs_review = True
                entry.review_reason = (
                    f"径级 {entry.diameter_cm}cm 超出合理范围 "
                    f"[{self.MIN_DIAMETER_CM}-{self.MAX_DIAMETER_CM}]"
                )
                warnings.append(
                    f"行{entry.row_number}: 径级 {entry.diameter_cm}cm 异常"
                )

        # ② 汇总校验：识别根数 vs 元数据声明根数（确认表无逐行数据，跳过）
        if result.meta.sheet_type != "confirmation":
            actual_count = len([e for e in result.entries if e.length_m > 0])
            if result.meta.total_count and actual_count != result.meta.total_count:
                warnings.append(
                    f"根数不一致: 识别 {actual_count} 根, "
                    f"表头声明 {result.meta.total_count} 根"
                )

        # ③ 汇总校验：计算体积 vs 元数据声明体积
        if result.meta.total_volume_m3 and result.entries:
            # 对有体积的行（打印码单），用 VLM 返回的体积求和
            entries_with_vol = [e for e in result.entries if e.volume_m3 is not None]
            if entries_with_vol:
                calc_vol = sum(e.volume_m3 for e in entries_with_vol  # type: ignore[misc]
                               if e.volume_m3 is not None)
            else:
                # 手写表：用 π/4 * D² * L 估算（JAS 圆木材积公式简化）
                calc_vol = sum(
                    math.pi / 4 * (e.diameter_cm / 100) ** 2 * e.length_m
                    for e in result.entries
                    if e.length_m > 0 and e.diameter_cm > 0
                )

            diff_pct = abs(calc_vol - result.meta.total_volume_m3) / result.meta.total_volume_m3 * 100
            if diff_pct > 5:
                warnings.append(
                    f"体积偏差 {diff_pct:.1f}%: 计算 {calc_vol:.2f}m³ vs "
                    f"声明 {result.meta.total_volume_m3:.2f}m³"
                )

        result.warnings.extend(warnings)
        if warnings:
            logger.warning(f"{result.filename} p{result.page}: {len(warnings)} 条校验警告")

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------

    @staticmethod
    def _encode_image(image: np.ndarray) -> str:
        """将 BGR numpy 图像编码为 base64 JPEG 字符串。"""
        success, buffer = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 95])
        if not success:
            raise ValueError("Failed to encode image to JPEG")
        return base64.b64encode(buffer).decode("utf-8")
