//! WebAssembly bindings for `weiqi-core`, for the browser and Node.
//!
//! The boundary copies, as in the Python binding: every value handed to
//! JavaScript is a plain object built from serializable DTOs, so it needs no
//! `free()` and never borrows from Rust memory. The one handle is
//! [`game::WasmGame`] (`Game` in JS), which owns its [`weiqi::Game`] in WASM
//! memory and must be freed (or released with `using`).
//!
//! Text forms: colors `"B"`/`"W"`, points `{ x, y }` from the top left, a
//! move is a point or `"pass"`, and hashes are 32-digit lowercase hex strings
//! because a JS `number` cannot hold 128 bits. Errors are JS `Error`s whose
//! `name` is the error class and whose `code` is the core's stable code.

use std::fmt::Display;

use js_sys::{Error, Reflect};
use serde::{Deserialize, Serialize};
use wasm_bindgen::prelude::*;
use weiqi::{BoardSize, Color, Komi, Move, Point, Rules};

mod game;
mod sgf;

#[wasm_bindgen(typescript_custom_section)]
const TYPES: &str = r#"
export type Color = "B" | "W";
/** Zero-based from the top left. */
export interface Point { x: number; y: number }
export type Move = Point | "pass";
export type Mode = "strict" | "record";
export interface PlayedMove { color: Color; move: Move }
export interface Setup { black: Point[]; white: Point[]; toPlay: Color }
export interface Captures { black: number; white: number }
export interface Position {
  width: number;
  height: number;
  /** Row-major from the top left: `cells[y * width + x]`. */
  cells: (Color | null)[];
  toPlay: Color;
  /** The point `toPlay` may not play because of simple ko. */
  koBan: Point | null;
  captures: Captures;
  consecutivePasses: number;
  /** 128-bit hash of the stones and board size, as 32 hex digits. */
  stonesHash: string;
  /** 128-bit hash of the stones, player to move and ko ban. */
  situationHash: string;
}
export interface MoveEffect {
  captured: Point[];
  suicided: Point[];
  repeatedPosition: boolean;
  /** Rules broken by a move applied in "record" mode. */
  violations: string[];
}
export interface Rules {
  ko: "simple" | "positional" | "situational";
  scoring: "area" | "territory";
  tax: "none" | "seki" | "all";
  suicide: "forbidden" | "multi_stone_allowed";
  button: boolean;
  whiteHandicapBonus: "0" | "N" | "N-1";
  friendlyPassOk: boolean;
}
export interface SgfWarning { code: string; offset: number | null }
export interface ExtractWarning { code: string; node: number | null }
export interface ExtractFailure { code: string; node: number }
export interface GameInfo {
  blackPlayer: string | null;
  whitePlayer: string | null;
  blackRank: string | null;
  whiteRank: string | null;
  date: string | null;
  event: string | null;
  round: string | null;
  place: string | null;
  name: string | null;
  resultText: string | null;
}
export interface GameRecord {
  width: number;
  height: number;
  /** `null` when `RU` is missing or not recognized (see `rulesText`). */
  rules: Rules | null;
  rulesText: string | null;
  /** `null` when `KM` is missing or invalid. */
  komi: number | null;
  handicap: number | null;
  setup: Setup;
  moves: PlayedMove[];
  info: GameInfo;
  warnings: ExtractWarning[];
}
/** Exactly one of `record` and `extractError` is set. */
export interface SgfGame { record: GameRecord | null; extractError: ExtractFailure | null }
export interface SgfCollection { encoding: string; warnings: SgfWarning[]; games: SgfGame[] }
export interface ReplayWarning { moveNumber: number; code: string }
export interface Replay {
  /** The starting position, then the position after each move. */
  positions: Position[];
  warnings: ReplayWarning[];
}
/** What every function and method of this module throws. */
export interface CoreError extends Error {
  name: "CoreError" | "IllegalMoveError" | "SgfError" | "ExtractError" | "ReplayError";
  code: string;
  /** SgfError only: byte offset in the decoded text. */
  offset?: number;
  /** ExtractError only. */
  node?: number;
  /** ReplayError only: 1-based, `null` when the setup is invalid. */
  moveNumber?: number | null;
}
"#;

/// The Zobrist key version that hashes depend on.
#[wasm_bindgen(js_name = zobristVersion)]
pub fn zobrist_version() -> u32 {
    weiqi::ZOBRIST_VERSION
}

// --- Errors ---

/// The error classes of the TypeScript `CoreError` interface.
#[derive(Clone, Copy)]
enum ErrorClass {
    Core,
    IllegalMove,
    Sgf,
    Extract,
    Replay,
}

/// A JS `Error` named after `class`, with `code` and the extra properties.
fn coded(
    class: ErrorClass,
    code: &str,
    message: impl Display,
    extras: &[(&str, Option<usize>)],
) -> JsValue {
    let error = Error::new(&message.to_string());
    error.set_name(match class {
        ErrorClass::Core => "CoreError",
        ErrorClass::IllegalMove => "IllegalMoveError",
        ErrorClass::Sgf => "SgfError",
        ErrorClass::Extract => "ExtractError",
        ErrorClass::Replay => "ReplayError",
    });
    let set = |key: &str, value: JsValue| {
        // Setting a property on a fresh Error object cannot fail.
        Reflect::set(&error, &JsValue::from_str(key), &value).expect("error property");
    };
    set("code", JsValue::from_str(code));
    for &(key, value) in extras {
        set(
            key,
            value.map_or(JsValue::NULL, |n| JsValue::from(n as f64)),
        );
    }
    error.into()
}

fn core_error(code: &str, message: impl Display) -> JsValue {
    coded(ErrorClass::Core, code, message, &[])
}

// --- Plain objects ---

/// Converts a DTO into a plain JS object; `None` becomes `null`.
fn to_js<T: Serialize>(value: &T) -> JsValue {
    let serializer = serde_wasm_bindgen::Serializer::new().serialize_missing_as_null(true);
    // The DTOs hold only strings, numbers, booleans, options and vectors,
    // which always serialize.
    value.serialize(&serializer).expect("DTO serializes")
}

/// A point as JS sees it.
#[derive(Clone, Copy, Serialize)]
struct XY {
    x: u8,
    y: u8,
}

fn color_text(color: Color) -> &'static str {
    match color {
        Color::Black => "B",
        Color::White => "W",
    }
}

fn parse_color(text: &str) -> Result<Color, JsValue> {
    match text {
        "B" => Ok(Color::Black),
        "W" => Ok(Color::White),
        _ => Err(core_error(
            "malformed_color",
            format!("color must be \"B\" or \"W\", not {text:?}"),
        )),
    }
}

fn parse_rules(name: &str) -> Result<Rules, JsValue> {
    Rules::from_name(name)
        .ok_or_else(|| core_error("unknown_rules", format!("unknown rules {name:?}")))
}

fn parse_komi(points: f64) -> Result<Komi, JsValue> {
    Komi::new(points).map_err(|error| core_error(error.code(), error))
}

fn board_size(width: u32, height: u32) -> Result<BoardSize, JsValue> {
    // Numbers outside `u8` become 0, which the core rejects like any bad size.
    let side = |n: u32| u8::try_from(n).unwrap_or(0);
    BoardSize::new(side(width), side(height)).map_err(|error| {
        core_error(
            error.code(),
            format!(
                "unsupported board size {width}x{height} (each side must be 1..={})",
                weiqi::MAX_BOARD_SIZE
            ),
        )
    })
}

fn point_xy(size: BoardSize, point: Point) -> XY {
    let (x, y) = size.xy(point).expect("point belongs to this board");
    XY { x, y }
}

fn points_xy(size: BoardSize, points: &[Point]) -> Vec<XY> {
    points.iter().map(|&p| point_xy(size, p)).collect()
}

/// A point from JS, before it is checked against a board.
#[derive(Deserialize)]
struct XYIn {
    x: f64,
    y: f64,
}

/// The point at `(x, y)` on this board; `None` when the coordinates are not
/// integers on the board.
fn point_at(size: BoardSize, xy: &XYIn) -> Option<Point> {
    let coordinate = |c: f64| {
        let valid = c.fract() == 0.0 && (0.0..=f64::from(u8::MAX)).contains(&c);
        // In range and integral, so the cast is exact.
        valid.then_some(c as u8)
    };
    size.point(coordinate(xy.x)?, coordinate(xy.y)?)
}

/// A move from JS: `{ x, y }` or `"pass"`. Points off this board throw an
/// `IllegalMoveError` with the core's `off_board` code.
fn parse_move(size: BoardSize, value: JsValue) -> Result<Move, JsValue> {
    let malformed = || core_error("malformed_move", "a move is { x, y } or \"pass\"");
    if let Some(text) = value.as_string() {
        return match text.as_str() {
            "pass" => Ok(Move::Pass),
            _ => Err(malformed()),
        };
    }
    let xy: XYIn = serde_wasm_bindgen::from_value(value).map_err(|_| malformed())?;
    if !(xy.x.is_finite() && xy.y.is_finite() && xy.x.fract() == 0.0 && xy.y.fract() == 0.0) {
        return Err(malformed());
    }
    point_at(size, &xy).map(Move::Play).ok_or_else(|| {
        let error = weiqi::IllegalMove::OffBoard;
        coded(
            ErrorClass::IllegalMove,
            error.code(),
            format!("({}, {}): {error}", xy.x, xy.y),
            &[],
        )
    })
}

/// A move as JS sees it: `{ x, y }` or `"pass"`.
#[derive(Serialize)]
#[serde(untagged)]
enum MoveOut {
    Point(XY),
    Pass(&'static str),
}

/// `{ color, move }`.
#[derive(Serialize)]
struct PlayedMove {
    color: &'static str,
    #[serde(rename = "move")]
    mv: MoveOut,
}

impl PlayedMove {
    fn new(size: BoardSize, color: Color, mv: Move) -> Self {
        Self {
            color: color_text(color),
            mv: match mv {
                Move::Play(point) => MoveOut::Point(point_xy(size, point)),
                Move::Pass => MoveOut::Pass("pass"),
            },
        }
    }
}

fn played_moves(size: BoardSize, moves: &[(Color, Move)]) -> Vec<PlayedMove> {
    moves
        .iter()
        .map(|&(color, mv)| PlayedMove::new(size, color, mv))
        .collect()
}
