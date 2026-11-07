//! Golden conformance cases (ROADMAP M2 acceptance 1): the Rust side.
//!
//! Each case in `testdata/conformance/{games,sgf}.json` is run into a
//! transcript; the Python and WASM bindings produce the same transcripts from
//! the same inputs and compare them with `expected.json`. Hand-written checks
//! in the cases (`expect`, `final`) are verified first, so a transcript is
//! never recorded unless it agrees with them.
//!
//! Regenerate `expected.json` after a deliberate change with
//! `UPDATE_CONFORMANCE=1 cargo test -p weiqi-core --test conformance`.

use std::path::PathBuf;

use serde_json::{Map, Value, json};
use weiqi_core::sgf::{self, GameRecord};
use weiqi_core::{
    BoardSize, Cell, Color, Game, KoRule, Komi, Move, Point, Position, ReplayMode, Rules,
    ScoringRule, Setup, SuicideRule, TaxRule, WhiteHandicapBonus, ZOBRIST_VERSION,
};

fn dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../testdata/conformance")
}

fn load(name: &str) -> Value {
    let path = dir().join(name);
    let text = std::fs::read_to_string(&path).unwrap_or_else(|e| panic!("{path:?}: {e}"));
    serde_json::from_str(&text).unwrap_or_else(|e| panic!("{path:?}: {e}"))
}

// --- Text forms shared by every binding (README.md) ---

fn color_text(color: Color) -> &'static str {
    match color {
        Color::Black => "B",
        Color::White => "W",
    }
}

fn point_text(size: BoardSize, point: Point) -> String {
    size.to_sgf(point).expect("point on this board")
}

fn move_text(size: BoardSize, color: Color, mv: Move) -> String {
    match mv {
        Move::Play(point) => format!("{} {}", color_text(color), point_text(size, point)),
        Move::Pass => format!("{} pass", color_text(color)),
    }
}

fn parse_color(text: &str) -> Color {
    match text {
        "B" => Color::Black,
        "W" => Color::White,
        _ => panic!("bad color {text:?}"),
    }
}

/// `"B cd"` or `"W pass"`.
fn parse_move(size: BoardSize, text: &str) -> (Color, Move) {
    let (color, point) = text.split_once(' ').expect("move like \"B cd\"");
    let mv = match point {
        "pass" => Move::Pass,
        _ => Move::Play(size.parse_sgf_point(point).expect("SGF point")),
    };
    (parse_color(color), mv)
}

fn points_text(size: BoardSize, points: &[Point]) -> Vec<String> {
    points.iter().map(|&p| point_text(size, p)).collect()
}

/// Rows from top to bottom, `.` empty, `X` black, `O` white.
fn board_rows(position: &Position) -> Vec<String> {
    let size = position.size;
    let symbol = |x, y| match position.cells[size.point(x, y).unwrap().index()] {
        Cell::Empty => '.',
        Cell::Black => 'X',
        Cell::White => 'O',
    };
    (0..size.height())
        .map(|y| (0..size.width()).map(|x| symbol(x, y)).collect())
        .collect()
}

fn position_json(position: &Position) -> Value {
    json!({
        "board": board_rows(position),
        "to_play": color_text(position.to_play),
        "ko_ban": position.ko_ban.map(|p| point_text(position.size, p)),
        "captures": { "black": position.captures.black, "white": position.captures.white },
        "consecutive_passes": position.consecutive_passes,
        "stones_hash": position.stones_hash.to_hex(),
        "situation_hash": position.situation_hash.to_hex(),
    })
}

fn rules_json(rules: Rules) -> Value {
    json!({
        "ko": match rules.ko {
            KoRule::Simple => "simple",
            KoRule::Positional => "positional",
            KoRule::Situational => "situational",
        },
        "scoring": match rules.scoring {
            ScoringRule::Area => "area",
            ScoringRule::Territory => "territory",
        },
        "tax": match rules.tax {
            TaxRule::None => "none",
            TaxRule::Seki => "seki",
            TaxRule::All => "all",
        },
        "suicide": match rules.suicide {
            SuicideRule::Forbidden => "forbidden",
            SuicideRule::MultiStoneAllowed => "multi_stone_allowed",
        },
        "button": rules.button,
        // KataGo's names for its whiteHandicapBonus values.
        "white_handicap_bonus": match rules.white_handicap_bonus {
            WhiteHandicapBonus::Zero => "0",
            WhiteHandicapBonus::N => "N",
            WhiteHandicapBonus::NMinusOne => "N-1",
        },
        "friendly_pass_ok": rules.friendly_pass_ok,
    })
}

fn case_rules(case: &Value) -> (Rules, Komi) {
    let name = case["rules"].as_str().expect("rules");
    let rules = Rules::from_name(name).unwrap_or_else(|| panic!("unknown rules {name}"));
    let komi = Komi::new(case["komi"].as_f64().expect("komi")).expect("valid komi");
    (rules, komi)
}

// --- Game cases ---

fn run_game(case: &Value) -> Value {
    let size = &case["size"];
    let size = BoardSize::new(
        size[0].as_u64().unwrap() as u8,
        size[1].as_u64().unwrap() as u8,
    )
    .unwrap();
    let (rules, komi) = case_rules(case);
    let mode = match case["mode"].as_str() {
        Some("strict") => ReplayMode::Strict,
        Some("record") => ReplayMode::Record,
        other => panic!("bad mode {other:?}"),
    };
    let mut game = match case.get("setup") {
        None => Game::new(size, rules, komi),
        Some(setup) => {
            let points = |key: &str| -> Vec<Point> {
                setup[key]
                    .as_array()
                    .unwrap()
                    .iter()
                    .map(|p| size.parse_sgf_point(p.as_str().unwrap()).unwrap())
                    .collect()
            };
            let setup = Setup {
                black: points("black"),
                white: points("white"),
                to_play: parse_color(setup["to_play"].as_str().unwrap()),
            };
            Game::with_setup(size, rules, komi, setup).unwrap()
        }
    };

    let start = position_json(&game.position());
    let mut steps = Vec::new();
    for entry in case["moves"].as_array().unwrap() {
        let text = entry.as_str().or(entry["play"].as_str()).unwrap();
        let (color, mv) = parse_move(size, text);
        let step = match game.play_as(color, mv, mode) {
            Ok(effect) => json!({
                "move": text,
                "result": "ok",
                "captured": points_text(size, &effect.captured),
                "suicided": points_text(size, &effect.suicided),
                "violations": effect.violations.iter().map(|v| v.code()).collect::<Vec<_>>(),
                "repeated_position": effect.repeated_position,
                "position": position_json(&game.position()),
            }),
            Err(error) => json!({ "move": text, "result": error.code() }),
        };
        steps.push(step);
    }

    // Take back every applied move; each step names the move and the
    // position it returns to.
    let mut undo = Vec::new();
    while let Some((color, mv)) = game.undo() {
        undo.push(json!({
            "undone": move_text(size, color, mv),
            "situation_hash": game.position().situation_hash.to_hex(),
        }));
    }
    json!({ "start": start, "steps": steps, "undo": undo })
}

fn sorted(value: &Value) -> Vec<String> {
    let mut items: Vec<String> = value
        .as_array()
        .unwrap()
        .iter()
        .map(|v| v.as_str().unwrap().to_owned())
        .collect();
    items.sort();
    items
}

fn check_game(case: &Value, transcript: &Value, failures: &mut Vec<String>) {
    let name = case["name"].as_str().unwrap();
    let steps = transcript["steps"].as_array().unwrap();
    for (entry, step) in case["moves"].as_array().unwrap().iter().zip(steps) {
        if entry.is_string() {
            continue;
        }
        let text = entry["play"].as_str().unwrap();
        let mut check = |what: &str, expected: Value, actual: Value| {
            if expected != actual {
                failures.push(format!(
                    "{name}, {text}: {what} expected {expected}, got {actual}"
                ));
            }
        };
        check("result", entry["expect"].clone(), step["result"].clone());
        for key in ["captured", "suicided", "violations"] {
            if let Some(expected) = entry.get(key) {
                let actual = step.get(key).map_or(Value::Null, |v| json!(sorted(v)));
                check(key, json!(sorted(expected)), actual);
            }
        }
        if let Some(expected) = entry.get("repeated_position") {
            check(
                "repeated_position",
                expected.clone(),
                step["repeated_position"].clone(),
            );
        }
    }
    if let Some(expected) = case.get("final").and_then(Value::as_object) {
        let last = steps
            .iter()
            .rev()
            .find_map(|s| s.get("position"))
            .unwrap_or(&transcript["start"]);
        for (key, value) in expected {
            if &last[key] != value {
                failures.push(format!(
                    "{name}: final {key} expected {value}, got {}",
                    last[key]
                ));
            }
        }
    }
}

// --- SGF cases ---

fn record_json(record: &GameRecord) -> Value {
    let size = record.size;
    let info = &record.info;
    json!({
        "size": [size.width(), size.height()],
        "rules": record.rules.map(rules_json),
        "rules_text": record.rules_text,
        "komi": record.komi.map(Komi::points),
        "handicap": record.handicap,
        "setup": {
            "black": points_text(size, &record.setup.black),
            "white": points_text(size, &record.setup.white),
            "to_play": color_text(record.setup.to_play),
        },
        "moves": record
            .moves
            .iter()
            .map(|&(color, mv)| move_text(size, color, mv))
            .collect::<Vec<_>>(),
        "info": {
            "black_player": info.black_player,
            "white_player": info.white_player,
            "black_rank": info.black_rank,
            "white_rank": info.white_rank,
            "date": info.date,
            "event": info.event,
            "round": info.round,
            "place": info.place,
            "name": info.name,
            "result_text": info.result_text,
        },
    })
}

fn sgf_game_json(tree: &sgf::SgfTree, rules: Rules, komi: Komi) -> Value {
    let record = match sgf::extract(tree) {
        Ok(record) => record,
        Err(error) => {
            return json!({ "extract_error": { "code": error.code(), "node": error.node } });
        }
    };
    let warnings: Vec<Value> = record
        .warnings
        .iter()
        .map(|w| json!({ "code": w.code(), "node": w.node }))
        .collect();
    let replay = match record.replay(rules, komi) {
        Ok(replay) => json!({
            "warnings": replay
                .warnings
                .iter()
                .map(|w| json!({ "move_number": w.move_number, "code": w.kind.code() }))
                .collect::<Vec<_>>(),
            "situation_hashes": replay
                .positions
                .iter()
                .map(|p| p.situation_hash.to_hex())
                .collect::<Vec<_>>(),
            "final": position_json(replay.positions.last().unwrap()),
        }),
        Err(error) => {
            let move_number = match error {
                sgf::RecordReplayError::Replay(e) => Some(e.move_number),
                sgf::RecordReplayError::Setup(_) => None,
            };
            json!({ "error": { "code": error.code(), "move_number": move_number } })
        }
    };
    json!({ "record": record_json(&record), "extract_warnings": warnings, "replay": replay })
}

fn run_sgf(case: &Value) -> Value {
    let bytes = match (case["file"].as_str(), case["text"].as_str()) {
        (Some(file), None) => {
            let path = dir().join("../sgf").join(file);
            std::fs::read(&path).unwrap_or_else(|e| panic!("{path:?}: {e}"))
        }
        (None, Some(text)) => text.as_bytes().to_vec(),
        _ => panic!("a case has either file or text"),
    };
    let (rules, komi) = case_rules(case);
    match sgf::parse(&bytes) {
        Err(error) => json!({ "error": { "code": error.code(), "offset": error.offset } }),
        Ok(collection) => json!({
            "encoding": collection.encoding,
            "sgf_warnings": collection
                .warnings
                .iter()
                .map(|w| json!({ "code": w.code(), "offset": w.offset }))
                .collect::<Vec<_>>(),
            "games": collection
                .games
                .iter()
                .map(|tree| sgf_game_json(tree, rules, komi))
                .collect::<Vec<_>>(),
        }),
    }
}

fn codes(items: &Value) -> Value {
    let mut codes: Vec<&str> = items
        .as_array()
        .unwrap()
        .iter()
        .map(|w| w["code"].as_str().unwrap())
        .collect();
    codes.sort_unstable();
    json!(codes)
}

fn check_sgf(
    case: &Value,
    transcript: &Value,
    all: &Map<String, Value>,
    failures: &mut Vec<String>,
) {
    let name = case["name"].as_str().unwrap();
    let expect = &case["expect"];
    let mut check = |what: &str, expected: &Value, actual: Value| {
        if *expected != actual {
            failures.push(format!("{name}: {what} expected {expected}, got {actual}"));
        }
    };
    if let Some(code) = expect.get("error") {
        check("error", code, transcript["error"]["code"].clone());
        return;
    }
    if let Some(encoding) = expect.get("encoding") {
        check("encoding", encoding, transcript["encoding"].clone());
    }
    if let Some(warnings) = expect.get("sgf_warnings") {
        check(
            "sgf_warnings",
            &json!(sorted(warnings)),
            codes(&transcript["sgf_warnings"]),
        );
    }
    if let Some(other) = expect.get("same_moves_as").and_then(Value::as_str) {
        let moves = |t: &Value| -> Vec<Value> {
            t["games"]
                .as_array()
                .unwrap()
                .iter()
                .map(|g| json!([g["record"]["moves"], g["replay"]]))
                .collect()
        };
        check(
            &format!("moves and replay of {other}"),
            &json!(moves(&all[other])),
            json!(moves(transcript)),
        );
    }
    let Some(games) = expect.get("games").and_then(Value::as_array) else {
        return;
    };
    let actual_games = transcript["games"].as_array().unwrap();
    check("game count", &json!(games.len()), json!(actual_games.len()));
    for (index, (expected, actual)) in games.iter().zip(actual_games).enumerate() {
        let what = |key: &str| format!("game {index} {key}");
        if let Some(code) = expected.get("extract_error") {
            check(
                &what("extract_error"),
                code,
                actual["extract_error"]["code"].clone(),
            );
        }
        if let Some(warnings) = expected.get("extract_warnings") {
            check(
                &what("extract_warnings"),
                &json!(sorted(warnings)),
                codes(&actual["extract_warnings"]),
            );
        }
        if let Some(count) = expected.get("moves") {
            let moves = &actual["record"]["moves"];
            check(&what("moves"), count, json!(moves.as_array().map(Vec::len)));
        }
        for key in ["black_player", "white_player"] {
            if let Some(player) = expected.get(key) {
                check(&what(key), player, actual["record"]["info"][key].clone());
            }
        }
        if let Some(code) = expected.get("replay_error") {
            check(
                &what("replay_error"),
                code,
                actual["replay"]["error"]["code"].clone(),
            );
        }
        if let Some(warnings) = expected.get("replay_warnings") {
            let actual_warnings: Vec<Value> = actual["replay"]["warnings"]
                .as_array()
                .map(|ws| {
                    ws.iter()
                        .map(|w| json!([w["move_number"], w["code"]]))
                        .collect()
                })
                .unwrap_or_default();
            check(&what("replay_warnings"), warnings, json!(actual_warnings));
        }
    }
}

// --- The test ---

/// The path of the first difference between two JSON values.
fn first_difference(path: &str, expected: &Value, actual: &Value) -> Option<String> {
    match (expected, actual) {
        (Value::Object(e), Value::Object(a)) => {
            for key in e.keys().chain(a.keys()) {
                let (Some(ev), Some(av)) = (e.get(key), a.get(key)) else {
                    return Some(format!("{path}.{key}: present on one side only"));
                };
                if let Some(diff) = first_difference(&format!("{path}.{key}"), ev, av) {
                    return Some(diff);
                }
            }
            None
        }
        (Value::Array(e), Value::Array(a)) if e.len() == a.len() => e
            .iter()
            .zip(a)
            .enumerate()
            .find_map(|(i, (ev, av))| first_difference(&format!("{path}[{i}]"), ev, av)),
        _ if expected == actual => None,
        _ => Some(format!("{path}: expected {expected}, got {actual}")),
    }
}

#[test]
fn transcripts_pass_hand_checks_and_match_the_golden_file() {
    let mut failures = Vec::new();

    let mut games = Map::new();
    for case in load("games.json")["cases"].as_array().unwrap() {
        let transcript = run_game(case);
        check_game(case, &transcript, &mut failures);
        games.insert(case["name"].as_str().unwrap().to_owned(), transcript);
    }

    let mut sgf_cases = Map::new();
    for case in load("sgf.json")["cases"].as_array().unwrap() {
        let transcript = run_sgf(case);
        check_sgf(case, &transcript, &sgf_cases, &mut failures);
        sgf_cases.insert(case["name"].as_str().unwrap().to_owned(), transcript);
    }

    assert!(
        failures.is_empty(),
        "hand-written checks failed:\n{}",
        failures.join("\n")
    );

    let actual = json!({
        "zobrist_version": ZOBRIST_VERSION,
        "games": games,
        "sgf": sgf_cases,
    });
    let path = dir().join("expected.json");
    if std::env::var_os("UPDATE_CONFORMANCE").is_some() {
        let text = serde_json::to_string_pretty(&actual).unwrap() + "\n";
        std::fs::write(&path, text).unwrap();
        return;
    }
    let expected = load("expected.json");
    if let Some(diff) = first_difference("", &expected, &actual) {
        panic!("transcript differs from expected.json at {diff}");
    }
}
