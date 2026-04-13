"""VLM-based end-to-end field extraction from customs declaration images.

Uses OpenAI's vision-capable models to read both printed and handwritten
text, understand document structure, and extract fields as structured JSON.
"""

from __future__ import annotations

import base64
import json
from typing import List, Optional

import cv2
import numpy as np
from loguru import logger
from openai import OpenAI

from app.config import settings
from app.schemas import CustomsField

# The system prompt instructs the VLM on what to extract and how.
SYSTEM_PROMPT = """你是一个专业的报关单识别助手。你将收到一张报关单（海关申报单）的图片。
请仔细阅读图片中的所有内容（包括手写和印刷文字），并抽取以下字段。
如果某个字段无法识别或图片中不存在，返回空字符串。

需要抽取的字段：
- declaration_number: 报关单号/申报编号
- date: 日期（格式化为 YYYY-MM-DD）
- importer: 进口商/收货人名称
- exporter: 出口商/发货人名称
- country_of_origin: 原产国
- port_of_entry: 进口口岸
- transport_mode: 运输方式
- goods_description: 货物名称/描述
- quantity: 数量（含单位）
- unit_price: 单价（含币种）
- total_value: 总金额（含币种）
- currency: 币种（如 CNY, USD, EUR, HRK 等）
- net_weight: 净重（含单位）
- gross_weight: 毛重（含单位）
- tariff_code: 税则号/HS编码
- duty_amount: 关税金额
- tax_amount: 税额
- remarks: 备注

特别注意：
1. 手写内容可能存在涂改、连笔，请结合上下文判断正确值
2. 忽略干笔划线、墨点等噪声，不要将其识别为有效文字
3. 数字中的小数点要特别注意，区分真正的小数点和噪声/遮挡造成的假象
4. 如果某个值你不确定，在对应字段后加 [?] 标记

请以严格的 JSON 格式返回，键为上述英文字段名，值为识别到的文本。
仅返回 JSON，不要有其他文字。
"""


class VLMExtractor:
    """Extract structured fields from customs declaration images using VLM."""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or settings.openai_api_key
        self.model = model or settings.openai_model
        if not self.api_key:
            logger.warning("OpenAI API key not set — VLM extraction will fail.")
            self.client = None
        else:
            self.client = OpenAI(api_key=self.api_key)

    def extract(self, image: np.ndarray) -> List[CustomsField]:
        """Extract fields from a single document crop image."""
        if self.client is None:
            raise RuntimeError("OpenAI client not initialized. Set OPENAI_API_KEY.")

        b64_image = self._encode_image(image)

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "请识别这张报关单中的所有字段信息。",
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{b64_image}",
                                    "detail": "high",
                                },
                            },
                        ],
                    },
                ],
                max_tokens=2000,
                temperature=0.1,
            )

            raw_text = response.choices[0].message.content.strip()
            logger.debug(f"VLM raw response length: {len(raw_text)} chars")
            return self._parse_response(raw_text)

        except Exception as e:
            logger.error(f"VLM extraction failed: {e}")
            raise

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _encode_image(image: np.ndarray) -> str:
        """Encode a BGR numpy image as base64 JPEG string."""
        success, buffer = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 95])
        if not success:
            raise ValueError("Failed to encode image to JPEG")
        return base64.b64encode(buffer).decode("utf-8")

    @staticmethod
    def _parse_response(raw_text: str) -> List[CustomsField]:
        """Parse VLM JSON response into a list of CustomsField."""
        # Strip markdown code fences if present
        text = raw_text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:])
            if text.endswith("```"):
                text = text[:-3].strip()

        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse VLM JSON: {e}\nRaw: {raw_text[:500]}")
            return [CustomsField(
                field_name="raw_response",
                value=raw_text,
                needs_review=True,
                review_reason="VLM response was not valid JSON",
            )]

        fields: List[CustomsField] = []
        for key, value in data.items():
            value_str = str(value).strip() if value else ""
            needs_review = value_str.endswith("[?]")
            if needs_review:
                value_str = value_str.replace("[?]", "").strip()

            fields.append(CustomsField(
                field_name=key,
                value=value_str,
                needs_review=needs_review,
                review_reason="Low confidence — marked by VLM" if needs_review else None,
            ))

        return fields
