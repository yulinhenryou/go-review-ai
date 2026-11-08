"""Records a real KataGo exchange as a public test fixture (ARCHITECTURE §5.4, MIGRATION E09).

Only public game records may be recorded: the input must be a file in
`testdata/sgf/` that `testdata/sgf/PROVENANCE.md` lists. The fixture keeps
every message sent and received, in order, with query ids renumbered and the
loaded model's file name reduced to its base name, and it is refused if any
local path is left in it. Next to the exchange it stores the engine identity
and the normalised result of every turn, which replay tests must reproduce.

Run from `python/` with the engine configured as for `EngineSettings`:

    KATAGO_MODEL_PATH=... uv run python -m weiqi.tools.record_engine \\
        ../testdata/sgf/synthetic-short.sgf --visits 32 --ownership \\
        --output ../testdata/engine/short-game.json
"""

from __future__ import annotations

import argparse
import asyncio
import datetime
import hashlib
import json
import platform
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Final, Literal

import weiqi_core

from weiqi.engine import AnalysisRequest, EngineIdentity, EngineSettings, KataGoEngine

REPO_ROOT: Final = Path(__file__).resolve().parents[4]
PUBLIC_SGF_DIR: Final = REPO_ROOT / "testdata" / "sgf"
FIXTURE_FORMAT: Final = 1

_PATH_MARKERS: Final = ("/Users/", "/home/", "/opt/", "/private/", "/tmp/", "/var/", ":\\")
"""Text that suggests a local absolute path; none may appear in a fixture."""


def load_record(path: Path) -> weiqi_core.GameRecord:
    """The main line of the only game in an SGF file."""
    collection = weiqi_core.parse_sgf(path.read_bytes())
    if len(collection.games) != 1:
        raise ValueError("expected exactly one game in the SGF file")
    return weiqi_core.extract(collection.games[0])


def request_for_record(
    record: weiqi_core.GameRecord,
    *,
    rules: str,
    komi: float,
    max_visits: int,
    pv_length: int = 8,
    include_ownership: bool = False,
    analyze_turns: Sequence[int] | None = None,
) -> AnalysisRequest:
    """An analysis of `record`'s main line; every turn unless `analyze_turns` is given."""
    moves = tuple(record.moves)
    setup = record.setup
    return AnalysisRequest(
        width=record.width,
        height=record.height,
        rules=rules,
        komi=komi,
        moves=moves,
        analyze_turns=tuple(range(len(moves) + 1) if analyze_turns is None else analyze_turns),
        max_visits=max_visits,
        pv_length=pv_length,
        include_ownership=include_ownership,
        initial_black=tuple(setup.black),
        initial_white=tuple(setup.white),
        initial_player=setup.to_play,
    )


def check_public(path: Path) -> str:
    """The repository-relative name of `path` if it is a listed public record."""
    resolved = path.resolve()
    if resolved.parent != PUBLIC_SGF_DIR:
        raise ValueError("only records in testdata/sgf/ may be recorded")
    provenance = (PUBLIC_SGF_DIR / "PROVENANCE.md").read_text(encoding="utf-8")
    if f"`{resolved.name}`" not in provenance:
        raise ValueError("the record is not listed in testdata/sgf/PROVENANCE.md")
    return resolved.relative_to(REPO_ROOT).as_posix()


def identity_document(identity: EngineIdentity) -> dict[str, object]:
    return asdict(identity)


def identity_from_document(document: Mapping[str, object]) -> EngineIdentity:
    overrides = document["overrides"]
    assert isinstance(overrides, list)
    return EngineIdentity(
        version=str(document["version"]),
        model_name=str(document["model_name"]),
        model_sha256=str(document["model_sha256"]),
        config_sha256=str(document["config_sha256"]),
        overrides=tuple((str(name), value) for name, value in overrides),
    )


def jsonable(value: object) -> object:
    """A dataclass as plain JSON values (tuples become lists)."""
    return json.loads(json.dumps(asdict(value)))  # type: ignore[call-overload]


class Recorder:
    """Collects a transcript with ids renumbered in order of first use."""

    def __init__(self) -> None:
        self.exchange: list[dict[str, object]] = []
        self._ids: dict[str, str] = {}

    def _renumber(self, value: object) -> object:
        if not isinstance(value, str):
            return value
        return self._ids.setdefault(value, f"id-{len(self._ids) + 1}")

    def __call__(
        self, direction: Literal["sent", "received"], message: Mapping[str, object]
    ) -> None:
        copy = json.loads(json.dumps(message))
        for key in ("id", "terminateId"):
            if key in copy:
                copy[key] = self._renumber(copy[key])
        models = copy.get("models")
        if isinstance(models, list):
            for model in models:
                if isinstance(model, dict) and isinstance(model.get("name"), str):
                    # KataGo reports the model path it was given; keep the file name only.
                    model["name"] = model["name"].replace("\\", "/").rsplit("/", 1)[-1]
        self.exchange.append({"direction": direction, "message": copy})


def _cpu() -> str:
    if sys.platform == "darwin":
        result = subprocess.run(
            ["sysctl", "-n", "machdep.cpu.brand_string"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    return platform.processor() or "unknown"


async def record(
    path: Path,
    settings: EngineSettings,
    *,
    rules: str,
    komi: float,
    max_visits: int,
    pv_length: int,
    include_ownership: bool,
) -> dict[str, object]:
    """Analyses a public record with the real engine and returns the fixture."""
    name = check_public(path)
    request = request_for_record(
        load_record(path),
        rules=rules,
        komi=komi,
        max_visits=max_visits,
        pv_length=pv_length,
        include_ownership=include_ownership,
    )
    recorder = Recorder()
    async with KataGoEngine(settings, transcript=recorder) as engine:
        analysis = await engine.analyze(request)
    fixture: dict[str, object] = {
        "format": FIXTURE_FORMAT,
        "input": {
            "sgf": name,
            "sgf_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "rules": rules,
            "komi": komi,
            "max_visits": max_visits,
            "pv_length": pv_length,
            "include_ownership": include_ownership,
            "analyze_turns": list(request.analyze_turns),
        },
        "recorded": {
            "date": datetime.datetime.now(datetime.UTC).date().isoformat(),
            "system": f"{platform.system()} {platform.release()}",
            "machine": platform.machine(),
            "cpu": _cpu(),
        },
        "identity": identity_document(analysis.identity),
        "exchange": recorder.exchange,
        "results": [
            {
                "turn": result.analysis.turn,
                "query_key": result.query_key,
                "engine_warnings": list(result.engine_warnings),
                "analysis": jsonable(result.analysis),
            }
            for result in analysis.results
        ],
    }
    text = json.dumps(fixture)
    secrets = (str(settings.model_path.resolve()), str(settings.config_path.resolve()))
    if any(marker in text for marker in (*_PATH_MARKERS, *secrets)):
        raise ValueError("the fixture still contains a local path; nothing was written")
    return fixture


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("sgf", type=Path, help="a public record in testdata/sgf/")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--visits", type=int, required=True)
    parser.add_argument("--pv-length", type=int, default=8)
    parser.add_argument("--ownership", action="store_true")
    parser.add_argument("--rules", help="KataGo rules name (default: the record's RU, lowercased)")
    parser.add_argument("--komi", type=float, help="default: the record's KM")
    args = parser.parse_args(argv)

    source = load_record(args.sgf)
    rules = args.rules or (source.rules_text or "").lower()
    komi = args.komi if args.komi is not None else source.komi
    if not rules or komi is None:
        parser.error("the record has no usable RU or KM; pass --rules and --komi")
    fixture = asyncio.run(
        record(
            args.sgf,
            EngineSettings.from_environment(),
            rules=rules,
            komi=komi,
            max_visits=args.visits,
            pv_length=args.pv_length,
            include_ownership=args.ownership,
        )
    )
    args.output.write_text(json.dumps(fixture, indent=1, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
