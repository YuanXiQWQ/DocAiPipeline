"""Export pipeline results to Excel, CSV, and JSON."""

from __future__ import annotations

import json
from pathlib import Path
from typing import List

import pandas as pd
from loguru import logger

from app.schemas import PipelineResult, CustomsRecord


class Exporter:
    """Exports structured customs records to various formats."""

    def __init__(self, output_dir: str = "output"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def export_all(self, result: PipelineResult) -> dict[str, str]:
        """Export to all formats. Returns dict of format → file path."""
        stem = Path(result.filename).stem
        paths = {}
        paths["json"] = str(self.to_json(result, stem))
        paths["csv"] = str(self.to_csv(result, stem))
        paths["excel"] = str(self.to_excel(result, stem))
        logger.info(f"Exported {result.total_documents_detected} records for '{result.filename}'")
        return paths

    def to_json(self, result: PipelineResult, stem: str) -> Path:
        out_path = self.output_dir / f"{stem}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result.model_dump(), f, ensure_ascii=False, indent=2)
        return out_path

    def to_csv(self, result: PipelineResult, stem: str) -> Path:
        df = self._records_to_dataframe(result.records)
        out_path = self.output_dir / f"{stem}.csv"
        df.to_csv(out_path, index=False, encoding="utf-8-sig")
        return out_path

    def to_excel(self, result: PipelineResult, stem: str) -> Path:
        df = self._records_to_dataframe(result.records)
        out_path = self.output_dir / f"{stem}.xlsx"
        df.to_excel(out_path, index=False, engine="openpyxl")
        return out_path

    @staticmethod
    def _records_to_dataframe(records: List[CustomsRecord]) -> pd.DataFrame:
        """Flatten records into a DataFrame with one row per document."""
        rows = []
        for record in records:
            row = {"record_index": record.record_index, "source_page": record.source_page}
            for field in record.fields:
                row[field.field_name] = field.value
                if field.needs_review:
                    row[f"{field.field_name}_review"] = field.review_reason or "needs review"
            rows.append(row)
        return pd.DataFrame(rows)
