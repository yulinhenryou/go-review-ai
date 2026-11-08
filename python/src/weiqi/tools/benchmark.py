"""Measures whole-game analysis with the real engine (MIGRATION E12, ROADMAP M3 acceptance 5).

For each visit count it measures two scenarios, each in a fresh worker
process so that peak memory is measured per scenario:

- **cold:** the clock starts before the KataGo process is launched, so it
  includes loading the model and the readiness check;
- **warm:** KataGo is started and has answered one warm-up query first. The
  warm-up position (one black stone on the centre point) is not in any game
  that starts from an empty board, so KataGo's own evaluation cache cannot
  answer the timed game from the warm-up.

The warm worker then stores the game in a temporary SQLite database and
times a second, fully cached analysis (`cache_seconds`).

Peak memory is the operating system's maximum resident set size of the
KataGo process (`getrusage(RUSAGE_CHILDREN)` after it has exited). On Apple
silicon, memory that the Metal backend allocates on the GPU side may not be
counted in it. The report holds no local paths and names the game only if it
is a public record in `testdata/sgf/`.

    KATAGO_MODEL_PATH=... uv run python -m weiqi.tools.benchmark \\
        ../testdata/sgf/maruyama-ito-1976.sgf --visits 32 200 --output report.json
"""

from __future__ import annotations

import argparse
import asyncio
import datetime
import hashlib
import json
import platform
import resource
import subprocess
import sys
import tempfile
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Literal

from weiqi.engine import (
    AnalysisRequest,
    CachedAnalyzer,
    EngineSettings,
    KataGoEngine,
)
from weiqi.tools.record_engine import check_public, load_record, request_for_record

type Mode = Literal["cold", "warm"]


def _peak_rss_bytes(who: int) -> int:
    peak = resource.getrusage(who).ru_maxrss
    return peak if sys.platform == "darwin" else peak * 1024  # Linux reports KiB


def warmup_request(width: int, height: int, rules: str, komi: float) -> AnalysisRequest:
    """One black stone on the centre point, White to move: not a position of
    a game that starts from an empty board."""
    return AnalysisRequest(
        width=width,
        height=height,
        rules=rules,
        komi=komi,
        moves=(),
        analyze_turns=(0,),
        max_visits=8,
        initial_black=((width // 2, height // 2),),
        initial_player="W",
    )


async def measure(
    settings: EngineSettings, request: AnalysisRequest, mode: Mode
) -> dict[str, object]:
    """One scenario in this process; see the module documentation."""
    report: dict[str, object] = {"mode": mode, "visits": request.max_visits}
    started = time.monotonic()
    async with KataGoEngine(settings) as engine:
        ready = time.monotonic()
        if mode == "warm":
            await engine.analyze(
                warmup_request(request.width, request.height, request.rules, request.komi)
            )
        before = time.monotonic()
        analysis = await engine.analyze(request)
        after = time.monotonic()
        report["identity"] = {
            "version": analysis.identity.version,
            "model_name": analysis.identity.model_name,
            "model_sha256": analysis.identity.model_sha256,
            "config_sha256": analysis.identity.config_sha256,
        }
        report["positions"] = len(analysis.results)
        report["root_visits_min"] = min(r.analysis.root.visits or 0 for r in analysis.results)
        if mode == "cold":
            report["startup_seconds"] = ready - started
            report["total_seconds"] = after - started
        report["analysis_seconds"] = after - before
        if mode == "warm":
            report["cache_seconds"] = await _cached_pass(engine, analysis.request)
    # The engine has exited and been waited for, so it counts as a child now.
    report["engine_peak_rss_bytes"] = _peak_rss_bytes(resource.RUSAGE_CHILDREN)
    report["worker_peak_rss_bytes"] = _peak_rss_bytes(resource.RUSAGE_SELF)
    return report


async def _cached_pass(engine: KataGoEngine, request: AnalysisRequest) -> float:
    """Seconds for a second analysis answered wholly from a new SQLite store."""
    from weiqi.storage.database import connect
    from weiqi.storage.migrate import upgrade
    from weiqi.storage.results import SqlResultStore

    with tempfile.TemporaryDirectory(prefix="weiqi-benchmark-") as directory:
        database = connect(f"sqlite:///{Path(directory) / 'cache.db'}")
        try:
            upgrade(database)
            analyzer = CachedAnalyzer(engine, SqlResultStore(database))
            await analyzer.analyze(request)
            queries = engine.queries
            started = time.monotonic()
            await analyzer.analyze(request)
            elapsed = time.monotonic() - started
            if engine.queries != queries or analyzer.hits != len(request.analyze_turns):
                raise RuntimeError("the cached pass asked the engine")
            return elapsed
        finally:
            database.dispose()


def _request(sgf: Path, visits: int, rules: str | None, komi: float | None) -> AnalysisRequest:
    record = load_record(sgf)
    rules = rules or (record.rules_text or "").lower()
    komi = komi if komi is not None else record.komi
    if not rules or komi is None:
        raise SystemExit("the record has no usable RU or KM; pass --rules and --komi")
    return request_for_record(record, rules=rules, komi=komi, max_visits=visits)


def _sysctl(name: str) -> str | None:
    if sys.platform != "darwin":
        return None
    result = subprocess.run(["sysctl", "-n", name], capture_output=True, text=True, check=False)
    value = result.stdout.strip()
    return value if result.returncode == 0 and value else None


def machine() -> dict[str, object]:
    memory = _sysctl("hw.memsize")
    return {
        "system": f"{platform.system()} {platform.release()}",
        "machine": platform.machine(),
        "cpu": _sysctl("machdep.cpu.brand_string") or platform.processor() or "unknown",
        "memory_bytes": int(memory) if memory and memory.isdigit() else None,
        "python": platform.python_version(),
    }


def _game(sgf: Path) -> dict[str, object]:
    try:
        name: str | None = check_public(sgf)
    except ValueError:
        name = None  # a private record is identified by its hash only
    return {"sgf": name, "sgf_sha256": hashlib.sha256(sgf.read_bytes()).hexdigest()}


def _worker(args: argparse.Namespace) -> int:
    request = _request(args.sgf, args.visits[0], args.rules, args.komi)
    report = asyncio.run(measure(EngineSettings.from_environment(), request, args.worker))
    print(json.dumps(report))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Benchmark whole-game engine analysis.")
    parser.add_argument("sgf", type=Path)
    parser.add_argument("--visits", type=int, nargs="+", default=[32])
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--rules", help="KataGo rules name (default: the record's RU, lowercased)")
    parser.add_argument("--komi", type=float, help="default: the record's KM")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--worker", choices=["cold", "warm"], help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.worker:
        return _worker(args)

    runs: list[dict[str, object]] = []
    for visits in args.visits:
        for repeat in range(1, args.repeats + 1):
            for mode in ("cold", "warm"):
                command = [sys.executable, "-m", "weiqi.tools.benchmark", str(args.sgf)]
                command += ["--visits", str(visits), "--worker", mode]
                if args.rules:
                    command += ["--rules", args.rules]
                if args.komi is not None:
                    command += ["--komi", str(args.komi)]
                done = subprocess.run(command, capture_output=True, text=True, check=False)
                if done.returncode != 0:
                    sys.stderr.write(done.stderr)
                    return done.returncode
                run = json.loads(done.stdout.strip().splitlines()[-1])
                run["repeat"] = repeat
                runs.append(run)
                print(json.dumps(run), file=sys.stderr)
    report = {
        "format": 1,
        "date": datetime.datetime.now(datetime.UTC).date().isoformat(),
        "machine": machine(),
        "game": _game(args.sgf),
        "runs": runs,
    }
    text = json.dumps(report, indent=1) + "\n"
    if args.output:
        args.output.write_text(text)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
