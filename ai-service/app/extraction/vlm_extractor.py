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
SYSTEM_PROMPT = """You are an expert document-understanding assistant specializing in customs / trade / logistics paperwork.

You will receive a scanned image of a trade-related document. It may be:
- A customs declaration (报关单 / carinska deklaracija / JCI)
- A movement certificate (EUR.1, ATR, etc.)
- A commercial invoice (račun / faktura / 发票)
- A CMR / transport document
- A phytosanitary / veterinary inspection certificate
- A packing list, specification, or any related trade document

The document may be in ANY language (Croatian, Serbian, Chinese, English, German, etc.).
Read ALL printed and handwritten text carefully.

Extract the following fields. If a field is not present or unreadable, return an empty string "".

Fields to extract:
- document_type: type of document (e.g. "customs declaration", "EUR.1 certificate", "commercial invoice", "CMR", "inspection certificate", etc.)
- declaration_number: document / declaration / certificate number
- date: primary date on the document (normalize to YYYY-MM-DD)
- importer: importer / buyer / consignee name and address
- exporter: exporter / seller / shipper name and address
- country_of_origin: country of origin of goods
- country_of_destination: destination country
- port_of_entry: port / border crossing of entry
- transport_mode: mode of transport (truck, rail, sea, etc.)
- vehicle_registration: vehicle / container registration numbers
- goods_description: description of goods
- quantity: quantity with unit (e.g. "33 komada", "37.93 m³")
- unit_price: unit price with currency
- total_value: total value / amount with currency
- currency: currency code (use ISO: EUR, USD, CNY, RSD, HRK, etc. — convert symbols like € to EUR)
- net_weight: net weight with unit
- gross_weight: gross weight with unit
- tariff_code: HS code / tariff number (e.g. 44039100)
- duty_amount: customs duty amount
- tax_amount: tax / VAT amount
- invoice_number: invoice number (if present, e.g. "Račun br. XXX")
- remarks: any notable remarks, reference numbers, special conditions

IMPORTANT rules:
1. Handwritten text may have corrections, crossed-out text, or cursive — use context to determine the intended value.
2. IGNORE pen strokes used for ink testing, ink spots, scan artifacts, and line noise — do NOT transcribe them.
3. Pay special attention to decimal separators: European documents often use comma as decimal (1.234,56 = one thousand two hundred thirty-four point fifty-six).
4. If you are uncertain about a value, append [?] to it.
5. Extract as much information as possible — even partial values are better than empty strings.

Return ONLY a valid JSON object with the field names above as keys and extracted text as values.
No other text, no markdown fences.
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
