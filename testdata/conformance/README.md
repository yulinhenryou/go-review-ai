# Conformance cases

One set of inputs that the Rust core, the Python binding and the WASM binding
all run. Each produces a transcript per case, and every transcript must equal
the one in `expected.json` (ROADMAP M2 acceptance 1, ARCHITECTURE §4).

| File | Written by | Content |
| --- | --- | --- |
| `games.json` | Hand | Move sequences on small boards, with hand-checked expectations |
| `sgf.json` | Hand | SGF inputs (corpus files from `../sgf/` or inline text), with hand-checked expectations |
| `expected.json` | Generated | Transcripts of every case, keyed by case name |

The Rust runner is `crates/weiqi-core/tests/conformance.rs`. It verifies the
hand-written `expect` and `final` fields first and fails before writing
anything if one disagrees. After a deliberate change in behavior, regenerate
the transcripts and review the diff:

```bash
UPDATE_CONFORMANCE=1 cargo test -p weiqi-core --test conformance
```

The hashes depend on `zobrist_version` (top of `expected.json`). Changing the
hash scheme means a new version and regenerated transcripts.

## Text forms

| Value | Form |
| --- | --- |
| Color | `"B"` or `"W"` |
| Point | SGF letters, column then row from the top left: `"aa"`, `"pd"` |
| Move | Color, space, point or `pass`: `"B pd"`, `"W pass"` |
| Board | One string per row from the top; `.` empty, `X` black, `O` white |
| Hash | 32 lowercase hex digits (128 bits) |
| Komi | Points as a JSON number, e.g. `6.5` |
| Code | The core's stable machine-readable code, e.g. `"ko_violation"` |

## `games.json` cases

```text
name, size [width, height], rules (KataGo name), komi, mode ("strict" | "record"),
setup? { black: [point], white: [point], to_play: color },
moves: [ move | { play: move, expect: "ok" | code, captured?, suicided?, violations?, repeated_position? } ],
final?: a subset of the position fields below
```

Each move is played with `play_as(color, move, mode)`. A rejected move leaves
the game unchanged and play continues with the next move.

Transcript:

```text
{
  start: position,
  steps: [ { move, result: "ok", captured: [point], suicided: [point],
             violations: [code], repeated_position: bool, position }
         | { move, result: code } ],
  undo:  [ { undone: move, situation_hash } ]   // undo until nothing is left
}
position = { board, to_play, ko_ban: point | null,
             captures: { black, white },        // stones of that color removed
             consecutive_passes, stones_hash, situation_hash }
```

## `sgf.json` cases

```text
name, file (in ../sgf/) | text, rules (KataGo name), komi,
expect: { error? | encoding?, sgf_warnings? [code], same_moves_as? name,
          games? [ { extract_error? | extract_warnings? [code], moves? count,
                     black_player?, white_player?, replay_error? | replay_warnings? [[move_number, code]] } ] }
```

`rules` and `komi` stand for the values a user confirmed, and are used to
replay every game in the file, in `Record` mode, from its setup. Hand-checked
warning lists are compared without regard to order; transcripts keep the
order the core reports.

Transcript:

```text
{ error: { code, offset } }                     // the bytes are not SGF
| {
    encoding,                                   // e.g. "UTF-8", "gb18030"
    sgf_warnings: [ { code, offset: number | null } ],
    games: [
      { extract_error: { code, node } }
      | {
          record: { size: [w, h], rules: rules | null, rules_text, komi, handicap,
                    setup: { black, white, to_play }, moves: [move],
                    info: { black_player, white_player, black_rank, white_rank, date,
                            event, round, place, name, result_text } },
          extract_warnings: [ { code, node: number | null } ],
          replay: { warnings: [ { move_number, code } ],
                    situation_hashes: [hash],   // start, then after each move
                    final: position }
                | { error: { code, move_number: number | null } }
        }
    ]
  }
rules = { ko: "simple" | "positional" | "situational", scoring: "area" | "territory",
          tax: "none" | "seki" | "all", suicide: "forbidden" | "multi_stone_allowed",
          button: bool, white_handicap_bonus: "0" | "N" | "N-1", friendly_pass_ok: bool }
```

Absent optional values are `null`. Text values are compared exactly, so
decoding differences show up: the UTF-8 Ke Jie file keeps its double-encoded
`GN` as found (see `../sgf/PROVENANCE.md`).
