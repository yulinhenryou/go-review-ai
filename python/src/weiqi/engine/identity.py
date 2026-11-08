"""Which engine produced a result: the part of provenance that enters the cache key.

No field holds a file path, so provenance never reveals the local file system
(MIGRATION E05, E08).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from weiqi.engine.errors import InvalidRequestError
from weiqi.engine.request import JsonScalar, check_settings

_SHA256 = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True, slots=True)
class EngineIdentity:
    """A running engine as reported by itself and hashed from its files.

    `overrides` are the settings passed on the command line with
    `-override-config`, which change every result the process produces.
    """

    version: str
    model_name: str
    model_sha256: str
    config_sha256: str
    overrides: tuple[tuple[str, JsonScalar], ...] = ()

    def __post_init__(self) -> None:
        for name in ("model_sha256", "config_sha256"):
            if not _SHA256.fullmatch(getattr(self, name)):
                raise InvalidRequestError(
                    "invalid_identity", f"{name} must be a lowercase SHA-256 hex digest"
                )
        if not self.version or not self.model_name:
            raise InvalidRequestError("invalid_identity", "version and model name are required")
        object.__setattr__(self, "overrides", check_settings(self.overrides))

    def key_fields(self) -> dict[str, object]:
        """The fields that make two results comparable. The model is
        identified by its hash; its internal name is provenance only."""
        return {
            "version": self.version,
            "model_sha256": self.model_sha256,
            "config_sha256": self.config_sha256,
            "overrides": dict(self.overrides),
        }
