# M1 Input Contract

Approved scope: one 19x19 Go game, at most 500 moves. This contract is implemented
locally; it does not certify the real-engine evaluation or report prose.

## Shared Record

`src/game.py` defines immutable `GameRecord`, `GameMove` and `BoardSnapshot` types.
Move sequences are tuples; external lists cannot mutate a saved game snapshot.
The parser's old `ParsedGame` / `ParsedMove` imports are compatibility aliases.

| Field | Meaning |
| --- | --- |
| `board_size` | Integer 19, not a string or boolean |
| `rules` | `japanese` or `chinese`; null only during preview |
| `komi` | Finite integer/half-integer from -150 to 150; null only during preview |
| `players.black`, `players.white` | Optional text, at most 256 characters each |
| `result` | Optional source metadata, at most 256 characters; never computed by M1 |
| `record_status` | `result_recorded` or `unfinished_or_unknown`; a stored result does not prove a complete move list |
| `moves` | 1-500 ordered moves, each with explicit `color` and `sgf` |
| `color` | `B` / `W`, starting with Black and strictly alternating |
| `sgf` | Two lowercase ASCII letters a-s, or explicit JSON null for pass |

`aa` is the upper-left intersection; `ss` is the lower-right. Coordinate mapping
to sgfmill's bottom-origin row/column representation is kept in the adapters.
An omitted manual `sgf` field is invalid, not an accidental pass.

## Supported Replay

Both SGF and manual input call `validate_game`, as do direct analysis entry points.
It returns the initial board and every post-move snapshot. Capture logic comes
from [sgfmill Board](https://github.com/mattheww/sgfmill/blob/master/sgfmill/boards.py),
not a second custom flood-fill implementation. The wrapper rejects occupied
points, wrong turns, out-of-range moves, single/multi-stone suicide and immediate
ko recapture. Pass changes the player and clears the immediate ko restriction.

The accepted names deliberately match KataGo's `japanese` and `chinese` presets:
both use simple ko and forbid suicide. `chinese-ogs`/`chinese-kgs` are different
presets and are not silently mapped to `chinese`. See
[KataGo's rules definitions](https://github.com/lightvector/KataGo/blob/master/cpp/game/rules.cpp).
M1 does not adjudicate superko variants, long-cycle no-results, scoring or disputes.

Two passes may end the recorded sequence, but additional moves after two
consecutive passes are rejected as unsupported resumption. No result or finished
game is inferred from pass count. This boundary avoids pretending to implement
Japanese encore/dispute phases.

## SGF Adapter

- UTF-8 with optional BOM; an explicit CA property must identify UTF-8.
- One SGF FF[4] game, explicit SZ[19]. GM, if present, must be 1.
- Root-node moves are included. Only the first variation is replayed; the
  response includes warning code `first_variation_only` when alternatives exist.
- Unknown comments/annotations may be ignored. Setup (`AB/AW/AE`), turn overrides
  (`PL`), ko overrides (`KO`) and nonzero handicap (`HA`) are rejected on any branch.
- Rules, komi, names and result are supported on the root only. Duplicate
  singleton properties, B and W in one node, malformed syntax, trailing junk and
  multiple games are rejected rather than silently repaired.
- Empty move values mean pass. The legacy `tt` pass alias is rejected.
- File bytes are bounded at 1 MiB before decoding, including whitespace/BOM.
  Total SGF nodes across all variations are limited to 5000.
- Missing rules/komi are preserved in previews. Analysis requires both.
  Query parameters `rules` and `komi` fill missing fields only; recorded values
  take precedence. Invalid/unsupported recorded values are never overwritten.

## HTTP Contract

| Endpoint | Input | Output |
| --- | --- | --- |
| `POST /api/v1/parse-sgf` | Multipart file; optional rules/komi query parameters | Validated input preview, no engine created |
| `POST /api/v1/validate-moves` | Game JSON, metadata may be missing | Same preview shape, no engine created |
| `POST /api/v1/analyze-sgf` | Same upload, plus loss_threshold/limit query parameters | Review schema 2.1 |
| `POST /api/v1/analyze-moves` | Complete Game JSON, plus loss_threshold/limit fields | Review schema 2.1 |

Manual JSON is strict: no type coercion, NaN/infinity, extra fields, or omitted
move coordinates. Missing metadata is allowed for preview, not analysis.
Both analysis endpoints validate the game and review options before calling the
engine factory. `loss_threshold` is finite, from 0 to 361; `limit` is an integer
from 1 to 500. Prototype defaults remain 1.0 and 3 until M3 calibrates them.

All POST/PUT/PATCH bodies have a 1 MiB + 64 KiB byte cap before JSON or multipart
parsing. The extra allowance is for multipart overhead, not a larger SGF file.
Chunked bodies are counted rather than trusting Content-Length.

Preview schema 1.0 contains `game`, `status`, `missing_fields`, `warnings` and
`final_position`. Status is `ready` or `needs_metadata`. The final position
contains `next_player` and a list of stones, each with `color` and `sgf`.

## Errors and Compatibility

Domain errors return HTTP 400; size limits return 413; invalid request fields
return 422. Responses contain an `error` object with `code`, `message`, `field`
and optional `move_number`, plus a legacy `detail` string. Request validation
also includes sanitized `issues`. Raw payloads and private engine paths are not
echoed. Engine runtime errors return a generic 503 `analysis_failed` response.

Review schema 2.1 retains the 2.0 fields and adds `rules`, `record_status` and
`input_warnings` to `game_summary`. The bundled frontend sends explicit manual
metadata, supplies optional SGF fallbacks, displays input failures and warns
about ignored variations. Full preview/confirmation UX is still M4 work.

The engine input now carries rules and `analysis_kind`. A null played move in
`played_move` mode is a pass; `current_position` mode means no move is being
evaluated. An unevaluated real-engine pass fails rather than inheriting the best
candidate score. Other missing-candidate score/PV fixes remain M2 work.
