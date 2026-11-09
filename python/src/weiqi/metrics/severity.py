"""Severity from score loss through a calibration table (ARCHITECTURE §6.2).

Thresholds are product settings to calibrate, not Go truths (ADR-011). The
table is keyed by strength band; until M5 calibrates it, it holds one band,
the default of ADR-P17. Only a positive loss can be a mistake, and the
winrate change never affects severity.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final, Literal

from weiqi.metrics.errors import MetricInputError

type Severity = Literal["mistake", "severe"]


@dataclass(frozen=True, slots=True)
class SeverityBand:
    """Loss thresholds in points for one strength band."""

    name: str
    mistake: float
    """A loss at least this large is a mistake."""
    severe: float
    """A loss at least this large is severe; never below `mistake`."""

    def __post_init__(self) -> None:
        for field, value in (("mistake", self.mistake), ("severe", self.severe)):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value < 0
            ):
                raise MetricInputError(
                    "invalid_threshold", f"{field} must be a finite number of points >= 0"
                )
        if self.severe < self.mistake:
            raise MetricInputError("invalid_threshold", "severe must not be below mistake")
        if not self.name:
            raise MetricInputError("invalid_threshold", "a band needs a name")

    def classify(self, score_loss: float | None) -> Severity | None:
        """The severity of a loss; `None` for missing, zero or small losses."""
        if score_loss is None or score_loss <= 0 or score_loss < self.mistake:
            return None
        return "severe" if score_loss >= self.severe else "mistake"


@dataclass(frozen=True, slots=True)
class CalibrationTable:
    """Severity bands by name, under one version."""

    version: str
    bands: tuple[SeverityBand, ...]

    def __post_init__(self) -> None:
        names = [band.name for band in self.bands]
        if not names or len(set(names)) != len(names):
            raise MetricInputError("invalid_threshold", "band names must be present and unique")

    def band(self, name: str) -> SeverityBand:
        for band in self.bands:
            if band.name == name:
                return band
        raise MetricInputError("unknown_band", f"no severity band named {name!r}")


DEFAULT_BAND: Final = SeverityBand(name="default", mistake=4.0, severe=8.0)
DEFAULT_CALIBRATION: Final = CalibrationTable(version="severity.v1", bands=(DEFAULT_BAND,))
