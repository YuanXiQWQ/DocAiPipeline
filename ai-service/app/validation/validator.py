"""基于规则的字段校验与规范化。"""

from __future__ import annotations

import re
from datetime import datetime
from typing import List, Set

from loguru import logger

from app.schemas import CustomsField

# 有效币种代码（按需扩展）
VALID_CURRENCIES: Set[str] = {
    "CNY", "USD", "EUR", "GBP", "JPY", "HRK", "KRW", "CAD", "AUD",
    "CHF", "SEK", "NOK", "DKK", "RUB", "INR", "BRL", "MXN", "HKD",
    "RSD",  # Serbian Dinar
}

# 常见币种符号 / 本地名称 → ISO 代码映射
CURRENCY_ALIASES: dict[str, str] = {
    "€": "EUR", "$": "USD", "£": "GBP", "¥": "CNY",
    "元": "CNY", "人民币": "CNY",
    "динар": "RSD", "динара": "RSD", "дин": "RSD", "dinar": "RSD",
    "kuna": "HRK", "kn": "HRK",
}

# 日期规范化尝试的格式
DATE_PATTERNS = [
    (r"\d{4}[-/\.]\d{1,2}[-/\.]\d{1,2}", "%Y-%m-%d"),
    (r"\d{1,2}[-/\.]\d{1,2}[-/\.]\d{4}", "%d-%m-%Y"),
    (r"\d{1,2}[-/\.]\d{1,2}[-/\.]\d{2}", "%d-%m-%y"),
]


class FieldValidator:
    """对抽取的单据字段进行校验和规范化。"""

    def validate(self, fields: List[CustomsField]) -> List[CustomsField]:
        """对字段列表执行所有校验规则，返回更新后的字段。"""
        validated: List[CustomsField] = []
        for field in fields:
            field = self._validate_field(field)
            validated.append(field)
        return validated

    def _validate_field(self, field: CustomsField) -> CustomsField:
        name = field.field_name
        value = field.value

        if not value:
            return field

        # 分发到具体的校验器
        if name == "currency":
            return self._validate_currency(field)
        elif name == "date":
            return self._validate_date(field)
        elif name in ("total_value", "unit_price", "duty_amount", "tax_amount"):
            return self._validate_amount(field)
        elif name in ("quantity", "net_weight", "gross_weight"):
            return self._validate_numeric(field)
        elif name == "tariff_code":
            return self._validate_tariff_code(field)

        return field

    # ------------------------------------------------------------------
    # 具体校验器
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_currency(field: CustomsField) -> CustomsField:
        """将币种与白名单比对，先解析符号/别名。"""
        raw = field.value.strip()
        value_lower = raw.lower()

        # 先尝试别名查找（符号 → 代码，本地名称 → 代码）
        if value_lower in CURRENCY_ALIASES:
            field.value = CURRENCY_ALIASES[value_lower]
            return field

        value_upper = raw.upper()
        if value_upper not in VALID_CURRENCIES:
            field.needs_review = True
            field.review_reason = f"Unknown currency: '{raw}'. Expected one of: {', '.join(sorted(VALID_CURRENCIES))}"
            logger.warning(f"Invalid currency: {raw}")
        else:
            field.value = value_upper
        return field

    @staticmethod
    def _validate_date(field: CustomsField) -> CustomsField:
        """将日期规范化为 YYYY-MM-DD 格式。"""
        raw = field.value.strip()
        # 替换常见分隔符
        normalized = raw.replace("/", "-").replace(".", "-")

        for pattern, fmt in DATE_PATTERNS:
            match = re.search(pattern.replace(r"[-/\.]", "-"), normalized)
            if match:
                try:
                    dt = datetime.strptime(match.group(), fmt.replace("/", "-").replace(".", "-"))
                    field.value = dt.strftime("%Y-%m-%d")
                    return field
                except ValueError:
                    continue

        field.needs_review = True
        field.review_reason = f"Could not parse date: '{raw}'"
        return field

    @staticmethod
    def _validate_amount(field: CustomsField) -> CustomsField:
        """校验金额——检查可疑的小数点。"""
        raw = field.value.strip()
        # 提取数字部分（可能包含币种前缀/后缀）
        numeric_match = re.search(r"[\d,]+\.?\d*", raw)
        if not numeric_match:
            field.needs_review = True
            field.review_reason = f"No numeric value found in amount: '{raw}'"
            return field

        numeric_str = numeric_match.group().replace(",", "")
        try:
            amount = float(numeric_str)
            # 标记可疑的过小或过大金额
            if amount < 0.01:
                field.needs_review = True
                field.review_reason = f"Amount suspiciously small: {amount}"
            elif amount > 100_000_000:
                field.needs_review = True
                field.review_reason = f"Amount suspiciously large: {amount}"
        except ValueError:
            field.needs_review = True
            field.review_reason = f"Cannot parse amount: '{numeric_str}'"

        return field

    @staticmethod
    def _validate_numeric(field: CustomsField) -> CustomsField:
        """数量/重量字段的基本数值校验。"""
        raw = field.value.strip()
        numeric_match = re.search(r"[\d,]+\.?\d*", raw)
        if not numeric_match:
            field.needs_review = True
            field.review_reason = f"No numeric value found: '{raw}'"
            return field

        numeric_str = numeric_match.group().replace(",", "")
        try:
            val = float(numeric_str)
            if val < 0:
                field.needs_review = True
                field.review_reason = f"Negative value: {val}"
        except ValueError:
            field.needs_review = True
            field.review_reason = f"Cannot parse number: '{numeric_str}'"

        return field

    @staticmethod
    def _validate_tariff_code(field: CustomsField) -> CustomsField:
        """HS/税则号通常是 6-10 位数字。支持逗号分隔的多个编码。"""
        raw = field.value.strip()
        # 按逗号/分号拆分多个编码
        parts = re.split(r"[,;]\s*", raw)
        valid_parts: list[str] = []
        for part in parts:
            cleaned = part.strip().replace(".", "").replace(" ", "")
            if re.match(r"^\d{4,10}$", cleaned):
                valid_parts.append(cleaned)

        if not valid_parts:
            field.needs_review = True
            field.review_reason = f"Tariff code format unexpected: '{field.value}'"
        else:
            field.value = ", ".join(valid_parts)
        return field
