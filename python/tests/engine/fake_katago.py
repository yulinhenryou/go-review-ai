"""A stand-in for `katago analysis` that speaks its JSON-lines protocol.

Test double only (MIGRATION E10): every number it reports is a fixed
placeholder, never Go analysis. The first argument picks a misbehaviour so
each test can provoke one protocol situation; in every mode a query whose id
starts with "hang" is not answered until it is terminated, and the action
"fake_stats" reports what the fake has seen.

Run as `python fake_katago.py MODE`.
"""

from __future__ import annotations

import json
import os
import sys

MODE = sys.argv[1] if len(sys.argv) > 1 else "normal"
terminated: list[str] = []
hanging: dict[str, list[int]] = {}


def send(message: object) -> None:
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


def player(query: dict[str, object], turn: int) -> str:
    """Who is to move at `turn`: the opponent of the last mover."""
    moves = query.get("moves")
    if turn == 0 or not isinstance(moves, list):
        return str(query.get("initialPlayer", "B"))
    return "W" if moves[turn - 1][0] == "B" else "B"


def final(query: dict[str, object], turn: int) -> dict[str, object]:
    return {
        "id": query["id"],
        "turnNumber": turn,
        "isDuringSearch": False,
        "rootInfo": {"currentPlayer": player(query, turn), "visits": 8, "winrate": 0.5},
        "moveInfos": [{"move": "pass", "order": 0, "visits": 8, "pv": ["pass"]}],
    }


def analyse(query: dict[str, object]) -> None:
    query_id = str(query["id"])
    turns = [int(t) for t in query.get("analyzeTurns", [])]  # type: ignore[attr-defined]
    if query_id.startswith("hang"):
        hanging[query_id] = turns
        return
    match MODE:
        case "crash":
            sys.exit(3)
        case "garbage":
            sys.stdout.write("this is not json\n")
            sys.stdout.flush()
            return
        case "unknown_id":
            send(final({**query, "id": "someone-else"}, turns[0]))
            return
        case "bad_turn":
            send({**final(query, turns[0]), "turnNumber": 99})
            return
        case "error":
            send({"error": "bad value", "field": "rules", "id": query_id})
            return
        case "warn_rules":
            send({"warning": "unknown rules", "field": "rules", "id": query_id})
        case "warn_other":
            send({"warning": "odd value", "field": "boardXSize", "id": query_id})
        case "missing_marker":
            reply = final(query, turns[0])
            del reply["isDuringSearch"]
            send(reply)
            return
        case "no_results":
            send(
                {"id": query_id, "turnNumber": turns[0], "isDuringSearch": False, "noResults": True}
            )
            return
        case "nan":
            sys.stdout.write(f'{{"id": "{query_id}", "turnNumber": 0, "x": NaN}}\n')
            sys.stdout.flush()
            return
        case "long_line":
            send({**final(query, turns[0]), "padding": "x" * 4096})
            return
        case "stderr_flood":
            # Far more than a pipe buffer: a reader that ignores stderr would deadlock.
            sys.stderr.write("diagnostic /private/path " * 100_000)
            sys.stderr.flush()
    for turn in reversed(turns):  # out of order on purpose
        if MODE == "during_search":
            send({**final(query, turn), "isDuringSearch": True})
        send(final(query, turn))
        if MODE == "duplicate":
            send(final(query, turn))


def main() -> None:
    for line in sys.stdin:
        query = json.loads(line)
        action = query.get("action")
        if action == "query_version":
            send({**query, "version": "1.16.4", "git_hash": "<omitted>"})
        elif action == "query_models":
            send({**query, "models": [{"name": "fake.bin.gz", "internalName": "fake-model"}]})
        elif action == "fake_stats":
            send({**query, "terminated": terminated, "cwd": os.getcwd()})
        elif action == "terminate":
            target = str(query["terminateId"])
            terminated.append(target)
            for turn in hanging.pop(target, []):
                send({"id": target, "turnNumber": turn, "isDuringSearch": False, "noResults": True})
            send(query)
        else:
            analyse(query)


if __name__ == "__main__":
    main()
