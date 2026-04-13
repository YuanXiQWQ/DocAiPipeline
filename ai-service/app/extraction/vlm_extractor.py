"""基于 VLM 的单据图像端到端字段抽取。

使用 OpenAI 视觉模型读取印刷体和手写文字，理解文档结构，并以结构化 JSON 格式抽取字段。
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

# 系统提示词：指导 VLM 抽取哪些字段以及如何抽取（保持英文，因为是给 AI 模型的指令）。
SYSTEM_PROMPT = """You are an expert document-understanding assistant specializing in customs / trade / logistics paperwork.

You will receive a scanned image of a full page that may contain a trade-related document. It may be:
- A customs declaration (报关单 / carinska deklaracija / JCI)
- A movement certificate (EUR.1, ATR, etc.)
- A commercial invoice (račun / faktura / 发票)
- A CMR / transport document (MEĐUNARODNI TOVARNI LIST)
- A phytosanitary / veterinary inspection certificate (РЕШЕЊЕ)
- An electronic invoice (eFaktura)
- A packing list, specification, or any related trade document
- A continuation/signature page of a previous document

The document may be in ANY language (Croatian, Serbian, Chinese, English, German, etc.).

FIRST, determine if this page contains a substantive document or is just a
continuation/signature page with no new data fields. Set the "is_continuation_page"
field accordingly.

Extract the following fields. If a field is not present or unreadable, return "".

Fields to extract:
- is_continuation_page: "true" if this page is ONLY signatures, stamps, or boilerplate text with no substantive data fields; "false" otherwise
- document_type: e.g. "customs declaration", "EUR.1 certificate", "commercial invoice", "CMR", "inspection certificate", "eFaktura", etc.
- declaration_number: document / declaration / certificate number (NOT internal product codes)
- date: primary document date (normalize to YYYY-MM-DD). Look for "Datum", "Дата", "日期", "Date"
- importer: importer / buyer / consignee — full name AND address. Look for "Primatelj", "Primalac", "Купац", "收货人"
- exporter: exporter / seller / shipper — full name AND address. Include parent company name (e.g. "HRVATSKE ŠUME d.o.o."). Look for "Izvoznik", "Pošiljalac", "Продавац", "发货人"
- country_of_origin: country of origin of goods
- country_of_destination: destination country
- port_of_entry: port / border crossing. Look for "Гранични прелаз", "口岸"
- transport_mode: mode of transport (truck/kamion/камион, rail, sea, etc.)
- vehicle_registration: ALL vehicle/trailer plate numbers found. Look for "Reg. broj vozila", "превозном средству број". Common Balkan plates look like "ŠI-047-MB" — note that Š/Ž look like S/Z but are DIFFERENT letters
- goods_description: FULL description of goods, including grade/quality if present
- quantity: quantity with unit. Note: on CMR docs, "Zapremina m³" is volume, "Broj koleta" is package count, "Bruto težina kg" is weight — extract volume/package count here, NOT weight
- unit_price: unit price with currency
- total_value: total value / final payable amount with currency. Look for "SVEUKUPNO", "Iznos za plaćanje", "Укупно"
- currency: ISO currency code. Convert: € → EUR, $ → USD, £ → GBP, ¥ → CNY, "Valuta fakture: RSD" → RSD, динар/динара → RSD, kuna/kn → HRK
- net_weight: net weight with unit
- gross_weight: gross weight with unit (kg or other)
- tariff_code: HS code / tariff number ONLY (6-10 digit numeric codes like 44039100). Do NOT put legal article references (e.g. "ЗРАТ") here
- duty_amount: customs duty amount with currency
- tax_amount: tax / VAT amount with currency
- invoice_number: the INVOICE number specifically (e.g. "Račun br. 603/0400/0402", "Broj fakture: 44/2026"). Do NOT confuse with CMR number or declaration number
- remarks: other notable info — reference numbers, IBAN, payment terms, legal notes, specification numbers

CRITICAL rules for HANDWRITTEN text (especially on CMR documents):
1. Balkan handwriting: "Š" and "Ž" with háček are COMMON — do not read "ŠI" as "51" or "SI". Context: Croatian/Serbian vehicle plates use letters like ŠI, ZG, PŽ.
2. Company names: if you see handwritten "TERA" or "TEER" near a known company context, the correct name is likely "TERA DRVO" (a wood trading company).
3. City names: "LJUKOVO" and "VUKOVAR" are different cities. Check the address context — if the document says "22321" the city is LJUKOVO (near Inđija, Serbia).
4. Numbers: carefully distinguish 5/S, 6/G, 9/g, 0/O in handwriting. Cross-reference with printed text on the same page.
5. Specification numbers: read digits very carefully — "16959" vs "16979" matters.
6. If handwritten text is ambiguous, prefer the reading that is consistent with other information on the same page or other pages.

OTHER rules:
7. SCAN the ENTIRE page including headers, footers, stamps, and fine print. Key fields like "Valuta fakture" or "Datum izdavanja" may be in small text.
8. European decimal convention: comma = decimal separator, dot = thousands separator (e.g. 103.700,00 = one hundred three thousand seven hundred).
9. If uncertain about a value, append [?].
10. Extract as much as possible — partial values are better than empty strings.

Return ONLY a valid JSON object with the field names above as keys.
No other text, no markdown fences, no code blocks.
"""


class VLMExtractor:
    """使用 VLM 从单据图像中抽取结构化字段。"""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or settings.openai_api_key
        self.model = model or settings.openai_model
        if not self.api_key:
            logger.warning("OpenAI API key not set — VLM extraction will fail.")
            self.client = None
        else:
            self.client = OpenAI(api_key=self.api_key)

    def extract(self, image: np.ndarray) -> List[CustomsField]:
        """从单份单据裁切图像中抽取字段。"""
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
                                "text": "Extract all fields from this trade document. Read every detail carefully.",
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
                max_tokens=3000,
                temperature=0.1,
            )

            raw_text = response.choices[0].message.content.strip()
            logger.debug(f"VLM raw response length: {len(raw_text)} chars")
            return self._parse_response(raw_text)

        except Exception as e:
            logger.error(f"VLM extraction failed: {e}")
            raise

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------

    @staticmethod
    def _encode_image(image: np.ndarray) -> str:
        """将 BGR numpy 图像编码为 base64 JPEG 字符串。"""
        success, buffer = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 95])
        if not success:
            raise ValueError("Failed to encode image to JPEG")
        return base64.b64encode(buffer).decode("utf-8")

    @staticmethod
    def _parse_response(raw_text: str) -> List[CustomsField]:
        """解析 VLM 的 JSON 响应为 CustomsField 列表。"""
        # 去除可能存在的 Markdown 代码围栏
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
