from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import shutil
import time
import uuid

from src.engine_protocol import candidates, candidate, optional_visits, sgf_to_gtp, validate_position
from src.engine_types import (
    AnalysisEvidence, CandidateMove, EngineClient, EngineProtocolError,
    KataGoUnavailableError, PositionAnalysis, PositionInput,
)
from src.katago_process import JsonlProcess


class KataGoClient:
    """Real analysis only. One loaded process per game, bounded batches of turns."""

    def __init__(
        self, *, model_path: str | Path, config_path: str | Path,
        katago_path: str = "katago", candidate_count: int = 3,
        max_visits: int = 200, timeout_seconds: float = 60.0,
    ) -> None:
        if type(candidate_count) is not int or not 1 <= candidate_count <= 20:
            raise ValueError("candidate_count must be between 1 and 20")
        if type(max_visits) is not int or not 1 <= max_visits <= 100000:
            raise ValueError("max_visits must be between 1 and 100000")
        if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float)) or not 0 < timeout_seconds <= 3600:
            raise ValueError("timeout_seconds must be finite and between 0 and 3600")
        self._model_path = Path(model_path)
        self._config_path = Path(config_path)
        self._katago_path = katago_path
        self._candidate_count = candidate_count
        self._max_visits = max_visits
        self._timeout_seconds = timeout_seconds
        self._session = None
        self._version = ""
        self._model_id = ""
        self._model_hash = ""
        self._config_hash = ""
        self._control = None

    def configure_control(self, control):
        if self._session is not None:
            raise RuntimeError("Cannot change control for an active engine")
        self._control = control

    def _checkpoint(self):
        if self._control is not None:
            self._control.checkpoint()

    @classmethod
    def from_environment(cls, **options) -> "KataGoClient":
        model = os.environ.get("KATAGO_MODEL_PATH")
        config = os.environ.get("KATAGO_CONFIG_PATH")
        if not model or not config:
            raise KataGoUnavailableError("Set KATAGO_MODEL_PATH and KATAGO_CONFIG_PATH; no mock fallback is available")
        options.setdefault("katago_path", os.environ.get("KATAGO_PATH", "katago"))
        options.setdefault("max_visits", int(os.environ.get("KATAGO_MAX_VISITS", "200")))
        return cls(model_path=model, config_path=config, **options)

    def __enter__(self):
        self._checkpoint()
        if self._session is not None:
            raise RuntimeError("Engine context is already open")
        binary = shutil.which(self._katago_path)
        if binary is None:
            raise KataGoUnavailableError("Configured KataGo binary not found")
        try:
            for path in (self._model_path, self._config_path):
                if not path.is_file() or path.stat().st_size == 0:
                    raise KataGoUnavailableError("Configured model/config file is missing or empty")
                with path.open("rb") as source:
                    source.read(1)
            self._model_hash = self._hash_file(self._model_path)
            self._config_hash = self._hash_file(self._config_path)
        except OSError as exc:
            raise KataGoUnavailableError("Configured model/config is not readable") from exc
        self._session = JsonlProcess([
            binary, "analysis", "-model", str(self._model_path.resolve()),
            "-config", str(self._config_path.resolve()), "-override-config",
            "reportAnalysisWinratesAs=BLACK,logAllRequests=false,logAllResponses=false,"
            "logErrorsAndWarnings=false,logToStderr=false",
        ])
        self._session.control = self._control
        try:
            version_id, models_id = self._new_id(), self._new_id()
            responses, _ = self._session.exchange(
                [{"id": version_id, "action": "query_version"},
                 {"id": models_id, "action": "query_models"}],
                {(version_id, None), (models_id, None)}, self._timeout_seconds,
            )
            version = responses[(version_id, None)].get("version")
            models = responses[(models_id, None)].get("models")
            if not isinstance(version, str) or not re.fullmatch(r"[0-9A-Za-z._+-]{1,80}", version):
                raise EngineProtocolError("Engine did not report a valid version")
            if not isinstance(models, list) or len(models) != 1 or not isinstance(models[0], dict):
                raise EngineProtocolError("Expected one loaded analysis model")
            model_id = models[0].get("internalName")
            if not isinstance(model_id, str) or not re.fullmatch(r"[0-9A-Za-z._+-]{1,200}", model_id):
                raise EngineProtocolError("Engine did not report a valid model identifier")
            self._version, self._model_id = version, model_id
            return self
        except BaseException:
            self.close()
            raise

    def _hash_file(self, path):
        digest = hashlib.sha256()
        with path.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                self._checkpoint()
                digest.update(chunk)
        return digest.hexdigest()

    def __exit__(self, *_exc) -> None:
        self.close()

    def close(self) -> None:
        if self._session is not None:
            self._session.close()
            self._session = None

    def readiness(self) -> dict:
        with self:
            return {"status": "ready", "engine": "KataGo", "version": self._version,
                    "model_id": self._model_id, "model_sha256": self._model_hash}

    @staticmethod
    def _new_id() -> str:
        return uuid.uuid4().hex

    def _build_query(self, position: PositionInput) -> dict:
        return {
            "id": self._new_id(), "boardXSize": position.board_size,
            "boardYSize": position.board_size, "rules": position.rules,
            "komi": float(position.komi), "maxVisits": self._max_visits,
            "moves": [[c, sgf_to_gtp(m, position.board_size)] for c, m in position.moves],
            "initialPlayer": position.to_play if len(position.moves) % 2 == 0
                else ("W" if position.to_play == "B" else "B"),
            "analyzeTurns": [len(position.moves)], "analysisPVLen": 8,
            "overrideSettings": {"playoutDoublingAdvantage": 0, "antiMirror": False},
        }

    def analyze_position(self, position: PositionInput) -> PositionAnalysis:
        return self.analyze_positions([position])[0]

    def analyze_positions(self, positions: list[PositionInput]) -> list[PositionAnalysis]:
        if not positions:
            return []
        for position in positions:
            validate_position(position)
        if self._session is None:
            with self:
                return self.analyze_positions(positions)
        result = []
        for start in range(0, len(positions), 16):
            self._checkpoint()
            batch = positions[start:start + 16]
            result.extend(self._analyze_batch(batch))
            if self._control is not None:
                self._control.advance(len(result), len(positions))
        return result

    def _analyze_batch(self, positions: list[PositionInput]) -> list[PositionAnalysis]:
        started = time.monotonic()
        reference = positions[-1]
        for p in positions:
            if (p.board_size, p.rules, p.komi) != (reference.board_size, reference.rules, reference.komi):
                raise ValueError("Batch metadata differs")
            if p.moves != reference.moves[:len(p.moves)]:
                raise ValueError("Batch histories must be prefixes of the same game")
            expected_player = reference.to_play if (len(reference.moves) - len(p.moves)) % 2 == 0 else (
                "W" if reference.to_play == "B" else "B")
            if p.to_play != expected_player:
                raise ValueError("Batch player order differs")
        query = self._build_query(reference)
        turns = [len(p.moves) for p in positions]
        if len(set(turns)) != len(turns):
            raise ValueError("Duplicate turns in batch")
        query["analyzeTurns"] = turns
        responses, warnings = self._session.exchange(
            [query], {(query["id"], turn) for turn in turns},
            self._timeout_seconds * len(positions),
        )
        parsed = [candidates(responses[(query["id"], turn)], p) for p, turn in zip(positions, turns)]
        forced_queries, forced_by_turn = [], {}
        for p, choices in zip(positions, parsed):
            if p.analysis_kind != "played_move":
                continue
            actual = p.played_move or "pass"
            found = next((c for c in choices if c.move == actual), None)
            if found is None or found.score_estimate is None or found.visits in (None, 0):
                forced = self._build_query(p)
                forced["allowMoves"] = [{
                    "player": p.to_play, "moves": [sgf_to_gtp(actual, p.board_size)], "untilDepth": 1,
                }]
                forced_queries.append(forced)
                forced_by_turn[len(p.moves)] = forced["id"]
        forced_responses = {}
        if forced_queries:
            forced_responses, forced_warnings = self._session.exchange(
                forced_queries, {(q["id"], q["analyzeTurns"][0]) for q in forced_queries},
                self._timeout_seconds * len(forced_queries),
            )
            warnings = tuple(sorted(set(warnings + forced_warnings)))
        elapsed = time.monotonic() - started
        analyses = []
        for p, choices, turn in zip(positions, parsed, turns):
            payload = responses[(query["id"], turn)]
            played = None
            played_id = None
            source = "not_applicable"
            flags = list(warnings)
            if p.analysis_kind == "played_move":
                actual = p.played_move or "pass"
                played = next((c for c in choices if c.move == actual), None)
                source, played_id = "candidate", query["id"]
                if turn in forced_by_turn:
                    played_id = forced_by_turn[turn]
                    forced_choices = candidates(forced_responses[(played_id, turn)], p)
                    played = next((c for c in forced_choices if c.move == actual), None)
                    source = "forced_root"
                    flags.append("separate_search")
                if played is None or played.visits == 0:
                    flags.append("played_evaluation_unavailable")
                    played = None
            best = choices[0] if choices else None
            if best is None and p.analysis_kind == "played_move":
                flags.append("recommendation_unavailable")
            value = best
            if value is None and p.analysis_kind == "current_position":
                value = candidate({**payload["rootInfo"], "move": "pass"}, p)
                flags.append("no_candidate_moves")
            loss = None
            if best and played and best.score_estimate is not None and played.score_estimate is not None:
                loss = best.score_estimate - played.score_estimate
                if loss < 0:
                    flags.append("negative_difference_search_noise")
            for choice in (best, played):
                if choice is not None and (choice.visits is None or choice.visits < min(16, self._max_visits)):
                    flags.append("low_visits")
            if value is None or value.score_estimate is None or value.winrate is None:
                flags.append("missing_value")
            if p.analysis_kind == "played_move" and (played is None or played.score_estimate is None or played.winrate is None):
                flags.append("missing_played_value")
            analyses.append(PositionAnalysis(
                best_move=best.move if best else None, played_move=p.played_move,
                estimated_loss=max(0.0, loss) if loss is not None else None,
                score_estimate=value.score_estimate if value else None,
                winrate=value.winrate if value else None,
                played_score_estimate=played.score_estimate if played else None,
                played_winrate=played.winrate if played else None,
                top_candidates=choices[:self._candidate_count],
                pv_summary=" -> ".join(f"{s.color} {s.move}" for s in best.pv) if best else "",
                raw_score_loss=loss,
                score_black=value.score_black if value else None,
                winrate_black=value.winrate_black if value else None,
                played_score_black=played.score_black if played else None,
                played_winrate_black=played.winrate_black if played else None,
                played_candidate=played,
                evidence=AnalysisEvidence(
                    engine_version=self._version, model_sha256=self._model_hash, model_id=self._model_id,
                    rules=p.rules, komi=p.komi, max_visits=self._max_visits,
                    request_id=query["id"], turn_number=turn,
                    root_visits=optional_visits(payload["rootInfo"].get("visits")),
                    config_sha256=self._config_hash,
                    elapsed_seconds=elapsed, played_source=source, played_request_id=played_id,
                    warnings=tuple(sorted(set(flags))),
                ),
            ))
        return analyses
