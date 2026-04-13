"""Fill the '纸质发票记录表' Excel template with extracted pipeline data.

Target template: 纸质发票记录表-20260303.xlsx
Sheet: 原始汇总
Columns to fill (A-L):
  A: 所属人         — from config (fixed)
  B: 公司名         — from config (fixed)
  C: 供应商名称     — from exporter field
  D: 性质           — '进口' for import docs
  E: 名称           — derived from document_type / goods_description
  F: 日期           — from date field
  G: 发票号         — from invoice_number or declaration_number
  H: 编号           — auto-generated internal reference
  I: FSC            — '是' or '非' (from EUR.1 cert or default)
  J: 供应商/备注    — formula =C{row} (auto)
  K: 外币金额       — from total_value (numeric)
  L: 数量           — from quantity (numeric, m³)
"""

from __future__ import annotations

import re
from copy import copy
from datetime import datetime
from pathlib import Path
from typing import Optional

import openpyxl
from loguru import logger

from app.schemas import PipelineResult, CustomsRecord


# ---------------------------------------------------------------------------
# Config: default values for fixed columns
# ---------------------------------------------------------------------------

DEFAULT_OWNER = "新A"          # 所属人 — column A
DEFAULT_COMPANY = "AL"         # 公司名 — column B
DEFAULT_NATURE = "进口"         # 性质  — column D
DEFAULT_FSC = "非"             # FSC   — column I


class InvoiceFiller:
    """Fills the 纸质发票记录表 Excel template from pipeline results."""

    def __init__(
        self,
        template_path: str | Path,
        sheet_name: str = "原始汇总",
        owner: str = DEFAULT_OWNER,
        company: str = DEFAULT_COMPANY,
    ):
        self.template_path = Path(template_path)
        self.sheet_name = sheet_name
        self.owner = owner
        self.company = company

        if not self.template_path.exists():
            raise FileNotFoundError(f"Template not found: {self.template_path}")

    def fill(
        self,
        results: list[PipelineResult],
        output_path: str | Path,
        batch_id: Optional[str] = None,
    ) -> Path:
        """Fill the template with data from one or more pipeline results.

        Args:
            results: List of PipelineResult from processing PDF files.
            output_path: Where to save the filled Excel.
            batch_id: Optional batch identifier prefix for internal ref numbers.

        Returns:
            Path to the saved file.
        """
        output_path = Path(output_path)

        wb = openpyxl.load_workbook(self.template_path)
        ws = wb[self.sheet_name]

        # Find the first empty row (header is row 2, data starts at row 3)
        start_row = self._find_first_empty_row(ws)
        logger.info(f"Template has data up to row {start_row - 1}. Appending from row {start_row}.")

        ref_counter = 0
        has_fsc = False  # Track if any EUR.1 cert found in batch

        # First pass: check for EUR.1 certificates
        for result in results:
            for record in result.records:
                doc_type = self._get_field(record, "document_type").lower()
                if "eur.1" in doc_type or "eur1" in doc_type or "movement certificate" in doc_type:
                    has_fsc = True
                    break

        # Second pass: fill rows for relevant documents
        current_row = start_row
        for result in results:
            source_file = result.filename
            for record in result.records:
                doc_type = self._get_field(record, "document_type").lower()

                # Skip non-invoice documents (continuation pages, certificates used only for FSC)
                if self._should_skip(doc_type):
                    logger.debug(f"Skipping {doc_type} from {source_file} (not billable)")
                    continue

                ref_counter += 1
                ref_num = self._generate_ref(batch_id, record, ref_counter)

                row_data = self._map_record_to_row(record, source_file, ref_num, has_fsc)
                self._write_row(ws, current_row, row_data)
                current_row += 1

        records_added = current_row - start_row
        logger.info(f"Added {records_added} row(s) to '{self.sheet_name}'")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        wb.save(str(output_path))
        wb.close()
        logger.info(f"Saved filled template to: {output_path}")
        return output_path

    # ------------------------------------------------------------------
    # Mapping logic
    # ------------------------------------------------------------------

    def _map_record_to_row(
        self, record: CustomsRecord, source_file: str, ref_num: str, has_fsc: bool
    ) -> dict:
        """Map a CustomsRecord to a dict of column values."""
        doc_type = self._get_field(record, "document_type").lower()
        exporter = self._get_field(record, "exporter")
        date_str = self._get_field(record, "date")
        invoice_num = self._get_field(record, "invoice_number")
        decl_num = self._get_field(record, "declaration_number")
        total_value = self._get_field(record, "total_value")
        quantity = self._get_field(record, "quantity")
        currency = self._get_field(record, "currency")
        goods_desc = self._get_field(record, "goods_description")

        # Determine 名称 (column E)
        item_name = self._derive_item_name(doc_type, goods_desc)

        # Determine 发票号 (column G) — prefer invoice_number, fallback to declaration_number
        bill_number = invoice_num if invoice_num else decl_num

        # Determine FSC
        fsc = "是" if has_fsc else DEFAULT_FSC

        # Parse numeric values
        amount = self._parse_european_number(total_value)
        qty = self._parse_european_number(quantity)

        # Parse date
        date_val = self._parse_date(date_str)

        # Extract short supplier name
        supplier = self._extract_supplier_name(exporter)

        return {
            "A": self.owner,           # 所属人
            "B": self.company,         # 公司名
            "C": supplier,             # 供应商名称
            "D": DEFAULT_NATURE,       # 性质
            "E": item_name,            # 名称
            "F": date_val,             # 日期
            "G": bill_number,          # 发票号
            "H": ref_num,              # 编号
            "I": fsc,                  # FSC
            # J is formula =C{row}, handled in _write_row
            "K": amount,               # 外币金额
            "L": qty,                  # 数量
        }

    @staticmethod
    def _should_skip(doc_type: str) -> bool:
        """Determine if a document type should be skipped (not a billable item)."""
        skip_types = [
            "eur.1", "eur1", "movement certificate",
            "inspection certificate", "phytosanitary",
            "cmr", "transport document",
        ]
        return any(t in doc_type for t in skip_types)

    @staticmethod
    def _derive_item_name(doc_type: str, goods_desc: str) -> str:
        """Derive the 名称 column value from document type and goods description."""
        goods_lower = goods_desc.lower()

        # Transport / freight
        if any(w in doc_type for w in ["transport", "efaktura"]):
            return "运费"
        if any(w in goods_lower for w in ["prevoz", "transport", "运费", "运输"]):
            return "运费"

        # Broker / customs service invoice
        if any(w in goods_lower for w in ["špedicij", "spedicij", "usluga", "报关费", "obracun", "pdv za jci"]):
            return "报关费"

        # Customs declaration → timber
        if "customs" in doc_type or "declaration" in doc_type:
            return "原木"

        # Wood / timber
        if any(w in goods_lower for w in ["trup", "drvo", "原木", "wood", "oak", "hrast", "furnir"]):
            return "原木"

        return "原木"  # default

    @staticmethod
    def _extract_supplier_name(exporter: str) -> str:
        """Extract a short supplier name from the full exporter string."""
        if not exporter:
            return ""

        name = exporter.strip()

        # Known supplier mappings (long name → short)
        supplier_map = {
            "HRVATSKE ŠUME": "HRVATSKE ŠUME",
            "PREMIUM": "PREMIUM",
            "UŠP": "HRVATSKE ŠUME",
        }
        name_upper = name.upper()
        for key, short in supplier_map.items():
            if key.upper() in name_upper:
                return short

        # For transport companies, take first part before "PR "
        if " PR " in name:
            # e.g. "MILENKO JANJATOVIĆ PR AUTOPREVOZ..." → "WOOD TRANS" if found
            if "WOOD TRANS" in name.upper():
                return "WOOD TRANS MOROVIĆ"
            name = name[:name.index(" PR ")]

        # Cut at address indicators
        for sep in [", Nikol", ", NIKOL", ", Milke", ", MILKE", ", Morović",
                    ", Zagreb", ", ZAGREB", ", Požega", ", POŽEGA",
                    ", USP", ", UŠP", ", UŠĆE", ", Jarački"]:
            if sep in name:
                name = name[:name.index(sep)]
                break

        return name.strip().rstrip(",").strip()

    @staticmethod
    def _parse_european_number(text: str) -> Optional[float]:
        """Parse a European-format number (1.234,56) to float."""
        if not text:
            return None

        # Remove currency codes and units
        cleaned = re.sub(r"[A-Za-z³²%]+", "", text).strip()
        # Remove spaces
        cleaned = cleaned.replace(" ", "")

        if not cleaned:
            return None

        # European format: 103.700,00 → 103700.00
        if "," in cleaned and "." in cleaned:
            # Determine which is decimal separator
            last_comma = cleaned.rfind(",")
            last_dot = cleaned.rfind(".")
            if last_comma > last_dot:
                # Comma is decimal: 1.234,56
                cleaned = cleaned.replace(".", "").replace(",", ".")
            else:
                # Dot is decimal: 1,234.56
                cleaned = cleaned.replace(",", "")
        elif "," in cleaned:
            # Only comma: could be decimal (3,61) or thousands (1,000)
            parts = cleaned.split(",")
            if len(parts) == 2 and len(parts[1]) <= 2:
                cleaned = cleaned.replace(",", ".")
            else:
                cleaned = cleaned.replace(",", "")
        # else: only dots or no separator — standard format

        try:
            return float(cleaned)
        except ValueError:
            return None

    @staticmethod
    def _parse_date(date_str: str) -> Optional[datetime]:
        """Parse a date string to datetime."""
        if not date_str:
            return None

        for fmt in ["%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%Y-%m-%d %H:%M:%S"]:
            try:
                return datetime.strptime(date_str.strip(), fmt)
            except ValueError:
                continue
        return date_str  # fallback: return as string

    @staticmethod
    def _generate_ref(batch_id: Optional[str], record: CustomsRecord, counter: int) -> str:
        """Generate an internal reference number (编号 column H)."""
        if batch_id:
            return f"{batch_id}-{counter:03d}"
        # Default: IM + date prefix + counter
        date_field = ""
        for f in record.fields:
            if f.field_name == "date" and f.value:
                date_field = f.value.replace("-", "")[:6]  # e.g. "202602"
                break
        return f"IM{date_field}{counter:02d}"

    # ------------------------------------------------------------------
    # Excel I/O helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_field(record: CustomsRecord, field_name: str) -> str:
        """Get a field value from a record by name."""
        for f in record.fields:
            if f.field_name == field_name:
                return f.value
        return ""

    @staticmethod
    def _find_first_empty_row(ws, start: int = 3) -> int:
        """Find the first empty row in column A starting from `start`."""
        row = start
        while ws.cell(row=row, column=1).value is not None:
            row += 1
        return row

    @staticmethod
    def _write_row(ws, row: int, data: dict):
        """Write a row of data to the worksheet."""
        col_map = {"A": 1, "B": 2, "C": 3, "D": 4, "E": 5, "F": 6,
                   "G": 7, "H": 8, "I": 9, "K": 11, "L": 12}

        # Copy formatting from the row above if possible
        src_row = row - 1 if row > 3 else 3

        for col_letter, col_idx in col_map.items():
            value = data.get(col_letter)
            cell = ws.cell(row=row, column=col_idx, value=value)

            # Copy number format from source row
            src_cell = ws.cell(row=src_row, column=col_idx)
            if src_cell.number_format:
                cell.number_format = src_cell.number_format

        # Column J (供应商/备注) is always a formula: =C{row}
        ws.cell(row=row, column=10, value=f"=C{row}")
