"""Breed-, sex-, and age-specific broiler performance reference handling."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd


REFERENCE_WORKBOOK_FILENAME = "Arbor_Acres_Plus_Broiler_Performance.xlsx"


class PerformanceStandardError(ValueError):
    """Raised when a record cannot be matched to an approved growth standard."""


def _normalise(value: Any) -> str:
    return " ".join(str(value or "").strip().casefold().replace("_", " ").replace("-", " ").split())


def _canonical_breed(value: Any) -> str:
    name = _normalise(value)
    if not name:
        raise PerformanceStandardError("missing_breed")
    if name in {"arbor acres", "arbor acres plus", "arboracres", "arboracres plus"}:
        return "arbor_acres_plus"
    return name.replace(" ", "_")


def _canonical_sex(value: Any) -> str:
    name = _normalise(value)
    aliases = {
        "as hatched": "as_hatched", "mixed": "as_hatched", "mixed sex": "as_hatched", "unsexed": "as_hatched",
        "รวมเพศ": "as_hatched", "male": "male", "m": "male", "เพศผู้": "male",
        "female": "female", "f": "female", "เพศเมีย": "female",
    }
    if name in aliases:
        return aliases[name]
    raise PerformanceStandardError(f"unsupported_sex:{value}")


@dataclass(frozen=True)
class GrowthReference:
    breed: str
    sex: str
    age_days: int
    standard_weight_g: float
    standard_adg_g_per_day: float
    standard_fcr: float


class PerformanceStandard:
    """Loads the approved Aviagen workbook and resolves its daily objectives."""

    _SHEETS = {
        "as_hatched": "As-Hatched (รวมเพศ)",
        "male": "Male (เพศผู้)",
        "female": "Female (เพศเมีย)",
    }

    def __init__(self, workbook_path: str | Path):
        self.workbook_path = Path(workbook_path)
        if not self.workbook_path.is_file():
            raise PerformanceStandardError(f"performance_standard_not_found:{self.workbook_path}")
        self._references = self._load(self.workbook_path)

    @staticmethod
    @lru_cache(maxsize=8)
    def _load(workbook_path: Path) -> dict[tuple[str, str, int], GrowthReference]:
        workbook = pd.ExcelFile(workbook_path)
        if "Standards" in workbook.sheet_names:
            return PerformanceStandard._load_normalized_template(workbook)
        references: dict[tuple[str, str, int], GrowthReference] = {}
        for sex, sheet in PerformanceStandard._SHEETS.items():
            frame = pd.read_excel(workbook_path, sheet_name=sheet, header=3)
            for _, source in frame.iterrows():
                try:
                    age_days = int(source.iloc[0])
                    weight_g = float(source.iloc[1])
                    adg_g_per_day = float(source.iloc[3])
                    fcr = float(source.iloc[6])
                except (TypeError, ValueError):
                    # Day 0 deliberately has no ADG/FCR and cannot be a prediction input.
                    continue
                reference = GrowthReference("arbor_acres_plus", sex, age_days, weight_g, adg_g_per_day, fcr)
                references[(reference.breed, reference.sex, age_days)] = reference
        if not references:
            raise PerformanceStandardError("performance_standard_has_no_usable_daily_rows")
        return references

    @staticmethod
    def _load_normalized_template(workbook: pd.ExcelFile) -> dict[tuple[str, str, int], GrowthReference]:
        frame = pd.read_excel(workbook, sheet_name="Standards", header=4)
        required = {"breed", "sex", "age_days", "body_weight_g", "adg_g_per_day", "fcr", "status"}
        missing = required - set(frame.columns)
        if missing:
            raise PerformanceStandardError(f"performance_standard_missing_columns:{','.join(sorted(missing))}")
        references: dict[tuple[str, str, int], GrowthReference] = {}
        for _, source in frame.iterrows():
            if _normalise(source.get("status")) != "approved":
                continue
            try:
                breed = _canonical_breed(source["breed"])
                sex = _canonical_sex(source["sex"])
                age_days = int(float(source["age_days"]))
                if float(source["age_days"]) != age_days or age_days < 1:
                    raise ValueError("age_days")
                reference = GrowthReference(breed, sex, age_days, float(source["body_weight_g"]), float(source["adg_g_per_day"]), float(source["fcr"]))
            except (TypeError, ValueError) as error:
                raise PerformanceStandardError(f"invalid_approved_standard_row:{error}") from None
            key = (breed, sex, age_days)
            if key in references:
                raise PerformanceStandardError(f"duplicate_performance_standard:{breed}:{sex}:{age_days}")
            references[key] = reference
        if not references:
            raise PerformanceStandardError("performance_standard_has_no_approved_rows")
        return references

    def lookup(self, breed: Any, sex: Any, age_days: Any) -> GrowthReference:
        try:
            age = int(float(age_days))
        except (TypeError, ValueError):
            raise PerformanceStandardError(f"invalid_age_days:{age_days}") from None
        if float(age_days) != age or age < 1:
            raise PerformanceStandardError(f"invalid_age_days:{age_days}")
        key = (_canonical_breed(breed), _canonical_sex(sex), age)
        try:
            return self._references[key]
        except KeyError:
            raise PerformanceStandardError(f"age_not_covered_by_performance_standard:{age}") from None

    def add_features(self, record: dict[str, Any]) -> dict[str, Any]:
        reference = self.lookup(record.get("breed"), record.get("sex"), record.get("age_days"))
        enriched = dict(record)
        enriched.update({
            "age_days": reference.age_days,
            "standard_weight_g": reference.standard_weight_g,
            "standard_adg_g_per_day": reference.standard_adg_g_per_day,
            "standard_fcr": reference.standard_fcr,
        })
        return enriched

    def coverage(self) -> dict[str, Any]:
        return {
            "supported_breeds": sorted({reference.breed for reference in self._references.values()}),
            "supported_sex": sorted({reference.sex for reference in self._references.values()}),
            "age_days": [min(key[2] for key in self._references), max(key[2] for key in self._references)],
        }
