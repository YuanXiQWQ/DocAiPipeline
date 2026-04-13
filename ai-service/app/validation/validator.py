"""Rule-based validation and normalization for extracted fields."""

from __future__ import annotations

import re
from datetime import datetime
from typing import List, Set

from loguru import logger

from app.schemas import CustomsField

# Valid currency codes (extend as needed)
VALID_CURRENCIES: Set[str] = {
    "CNY", "USD", "EUR", "GBP", "JPY", "HRK", "KRW", "CAD", "AUD",
    "CHF", "SEK", "NOK", "DKK", "RUB", "INR", "BRL", "MXN", "HKD",
}

# Date patterns to try for normalization
DATE_PATTERNS = [
    (r"\d{4}[-/\.]\d{1,2}[-/\.]\d{1,2}", "%Y-%m-%d"),
    (r"\d{1,2}[-/\.]\d{1,2}[-/\.]\d{4}", "%d-%m-%Y"),
    (r"\d{1,2}[-/\.]\d{1,2}[-/\.]\d{2}", "%d-%m-%y"),
]


class FieldValidator:
    """Validates and normalizes extracted customs fields."""

    def validate(self, fields: List[CustomsField]) -> List[CustomsField]:
        """Run all validation rules on the field list, returning updated fields."""
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

        # Dispatch to specific validators
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
    # Specific validators
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_currency(field: CustomsField) -> CustomsField:
        """Check currency against whitelist."""
        value_upper = field.value.strip().upper()
        if value_upper not in VALID_CURRENCIES:
            field.needs_review = True
            field.review_reason = f"Unknown currency: '{field.value}'. Expected one of: {', '.join(sorted(VALID_CURRENCIES))}"
            logger.warning(f"Invalid currency: {field.value}")
        else:
            field.value = value_upper  # normalize to uppercase
        return field

    @staticmethod
    def _validate_date(field: CustomsField) -> CustomsField:
        """Normalize date to YYYY-MM-DD format."""
        raw = field.value.strip()
        # Replace common separators
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
        """Validate monetary amounts — check for suspicious decimal points."""
        raw = field.value.strip()
        # Extract numeric part (may include currency prefix/suffix)
        numeric_match = re.search(r"[\d,]+\.?\d*", raw)
        if not numeric_match:
            field.needs_review = True
            field.review_reason = f"No numeric value found in amount: '{raw}'"
            return field

        numeric_str = numeric_match.group().replace(",", "")
        try:
            amount = float(numeric_str)
            # Flag suspiciously small or large amounts
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
        """Basic numeric validation for quantity/weight fields."""
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
        """HS/tariff codes are typically 6-10 digit numbers."""
        raw = field.value.strip().replace(".", "").replace(" ", "")
        if not re.match(r"^\d{4,10}$", raw):
            field.needs_review = True
            field.review_reason = f"Tariff code format unexpected: '{field.value}'"
        return field
