"""Where KataGo and its files are, and how long to wait for it.

There is no fallback (MIGRATION E07, DECISIONS ADR-007): without a model the
engine is unavailable, never replaced by a mock.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from weiqi.engine.errors import EngineUnavailableError

# python/src/weiqi/engine/settings.py -> the repository root is four levels up.
DEFAULT_CONFIG = Path(__file__).resolve().parents[4] / "config" / "katago" / "analysis.cfg"


@dataclass(frozen=True, slots=True)
class EngineSettings:
    model_path: Path
    config_path: Path = DEFAULT_CONFIG
    katago_path: str = "katago"
    max_in_flight: int = 2
    """Analysis queries sent at once; each may hold many turns."""
    turn_timeout: float = 60.0
    """Seconds allowed per analysed turn before a query is terminated."""
    startup_timeout: float = 120.0
    """Seconds allowed to start the process and check readiness."""
    restart_base_delay: float = 0.5
    restart_max_delay: float = 8.0

    @classmethod
    def from_environment(cls, environ: Mapping[str, str] = os.environ) -> EngineSettings:
        """Reads `KATAGO_MODEL_PATH` (required), `KATAGO_CONFIG_PATH` and `KATAGO_PATH`."""
        model = environ.get("KATAGO_MODEL_PATH")
        if not model:
            raise EngineUnavailableError(
                "engine_not_configured", "set KATAGO_MODEL_PATH; there is no fallback engine"
            )
        config = environ.get("KATAGO_CONFIG_PATH")
        return cls(
            model_path=Path(model),
            config_path=Path(config) if config else DEFAULT_CONFIG,
            katago_path=environ.get("KATAGO_PATH") or "katago",
        )


def restart_delay(failures: int, base: float, cap: float) -> float:
    """Seconds to wait before the next start after `failures` failed starts:
    none at first, then doubling from `base` up to `cap`."""
    if failures <= 0:
        return 0.0
    return min(base * 2.0 ** (failures - 1), cap)
