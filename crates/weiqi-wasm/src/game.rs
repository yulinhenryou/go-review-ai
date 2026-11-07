//! Positions, rules and the `Game` handle.

use serde::{Deserialize, Serialize};
use wasm_bindgen::prelude::*;
use weiqi::{
    BoardSize, Cell, Game, KoRule, Position, ReplayMode, Rules, ScoringRule, Setup, SuicideRule,
    TaxRule, WhiteHandicapBonus,
};

use crate::{
    ErrorClass, PlayedMove, XY, XYIn, board_size, coded, color_text, core_error, parse_color,
    parse_komi, parse_move, parse_rules, played_moves, point_at, point_xy, points_xy, to_js,
};

#[derive(Serialize)]
struct CapturesDto {
    black: u32,
    white: u32,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct PositionDto {
    width: u8,
    height: u8,
    cells: Vec<Option<&'static str>>,
    to_play: &'static str,
    ko_ban: Option<XY>,
    captures: CapturesDto,
    consecutive_passes: u32,
    stones_hash: String,
    situation_hash: String,
}

impl PositionDto {
    pub(crate) fn new(position: &Position) -> Self {
        let size = position.size;
        Self {
            width: size.width(),
            height: size.height(),
            // The core stores cells in index order, which is row-major.
            cells: position
                .cells
                .iter()
                .map(|cell| match cell {
                    Cell::Empty => None,
                    Cell::Black => Some("B"),
                    Cell::White => Some("W"),
                })
                .collect(),
            to_play: color_text(position.to_play),
            ko_ban: position.ko_ban.map(|p| point_xy(size, p)),
            captures: CapturesDto {
                black: position.captures.black,
                white: position.captures.white,
            },
            consecutive_passes: position.consecutive_passes,
            stones_hash: position.stones_hash.to_hex(),
            situation_hash: position.situation_hash.to_hex(),
        }
    }
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct RulesDto {
    ko: &'static str,
    scoring: &'static str,
    tax: &'static str,
    suicide: &'static str,
    button: bool,
    white_handicap_bonus: &'static str,
    friendly_pass_ok: bool,
}

impl RulesDto {
    pub(crate) fn new(rules: Rules) -> Self {
        Self {
            ko: match rules.ko {
                KoRule::Simple => "simple",
                KoRule::Positional => "positional",
                KoRule::Situational => "situational",
            },
            scoring: match rules.scoring {
                ScoringRule::Area => "area",
                ScoringRule::Territory => "territory",
            },
            tax: match rules.tax {
                TaxRule::None => "none",
                TaxRule::Seki => "seki",
                TaxRule::All => "all",
            },
            suicide: match rules.suicide {
                SuicideRule::Forbidden => "forbidden",
                SuicideRule::MultiStoneAllowed => "multi_stone_allowed",
            },
            button: rules.button,
            // KataGo's names for its whiteHandicapBonus values.
            white_handicap_bonus: match rules.white_handicap_bonus {
                WhiteHandicapBonus::Zero => "0",
                WhiteHandicapBonus::N => "N",
                WhiteHandicapBonus::NMinusOne => "N-1",
            },
            friendly_pass_ok: rules.friendly_pass_ok,
        }
    }
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct SetupDto {
    black: Vec<XY>,
    white: Vec<XY>,
    to_play: &'static str,
}

impl SetupDto {
    pub(crate) fn new(size: BoardSize, setup: &Setup) -> Self {
        Self {
            black: points_xy(size, &setup.black),
            white: points_xy(size, &setup.white),
            to_play: color_text(setup.to_play),
        }
    }
}

/// A setup from JS, before it is checked against a board.
#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
struct SetupIn {
    black: Vec<XYIn>,
    white: Vec<XYIn>,
    to_play: String,
}

impl SetupIn {
    fn into_core(self, size: BoardSize) -> Result<Setup, JsValue> {
        let points = |xys: &[XYIn]| {
            xys.iter()
                .map(|xy| {
                    point_at(size, xy).ok_or_else(|| {
                        core_error(
                            "setup_off_board",
                            format!("setup point ({}, {}) is not on the board", xy.x, xy.y),
                        )
                    })
                })
                .collect::<Result<Vec<_>, _>>()
        };
        Ok(Setup {
            black: points(&self.black)?,
            white: points(&self.white)?,
            to_play: parse_color(&self.to_play)?,
        })
    }
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct MoveEffectDto {
    captured: Vec<XY>,
    suicided: Vec<XY>,
    repeated_position: bool,
    violations: Vec<&'static str>,
}

fn parse_mode(text: &str) -> Result<ReplayMode, JsValue> {
    match text {
        "strict" => Ok(ReplayMode::Strict),
        "record" => Ok(ReplayMode::Record),
        other => Err(core_error(
            "malformed_mode",
            format!("mode must be \"strict\" or \"record\", not {other:?}"),
        )),
    }
}

/// A game in progress. It lives in WASM memory: call `free()` (or declare it
/// with `using`) when done.
#[wasm_bindgen(js_name = Game)]
pub struct WasmGame {
    inner: Game,
}

#[wasm_bindgen(js_class = Game)]
impl WasmGame {
    /// A game on an empty board with Black to move; `rules` is a KataGo
    /// rules name such as "japanese" or "tromp-taylor".
    #[wasm_bindgen(constructor)]
    pub fn new(width: u32, height: u32, rules: &str, komi: f64) -> Result<WasmGame, JsValue> {
        let size = board_size(width, height)?;
        let inner = Game::new(size, parse_rules(rules)?, parse_komi(komi)?);
        Ok(Self { inner })
    }

    /// A game starting from setup stones (handicap or SGF `AB`/`AW`).
    #[wasm_bindgen(js_name = withSetup)]
    pub fn with_setup(
        width: u32,
        height: u32,
        rules: &str,
        komi: f64,
        #[wasm_bindgen(unchecked_param_type = "Setup")] setup: JsValue,
    ) -> Result<WasmGame, JsValue> {
        let size = board_size(width, height)?;
        let setup: SetupIn = serde_wasm_bindgen::from_value(setup)
            .map_err(|error| core_error("malformed_setup", format!("invalid setup: {error}")))?;
        let inner = Game::with_setup(
            size,
            parse_rules(rules)?,
            parse_komi(komi)?,
            setup.into_core(size)?,
        )
        .map_err(|error| core_error(error.code(), error))?;
        Ok(Self { inner })
    }

    #[wasm_bindgen(getter)]
    pub fn width(&self) -> u8 {
        self.inner.board().size().width()
    }

    #[wasm_bindgen(getter)]
    pub fn height(&self) -> u8 {
        self.inner.board().size().height()
    }

    #[wasm_bindgen(getter, unchecked_return_type = "Rules")]
    pub fn rules(&self) -> JsValue {
        to_js(&RulesDto::new(self.inner.rules()))
    }

    #[wasm_bindgen(getter)]
    pub fn komi(&self) -> f64 {
        self.inner.komi().points()
    }

    #[wasm_bindgen(getter, js_name = toPlay, unchecked_return_type = "Color")]
    pub fn to_play(&self) -> String {
        color_text(self.inner.to_play()).to_owned()
    }

    #[wasm_bindgen(getter, js_name = moveCount)]
    pub fn move_count(&self) -> usize {
        self.inner.move_count()
    }

    /// The moves played so far.
    #[wasm_bindgen(unchecked_return_type = "PlayedMove[]")]
    pub fn moves(&self) -> JsValue {
        to_js(&played_moves(
            self.inner.board().size(),
            &self.inner.moves(),
        ))
    }

    /// A snapshot of the current position.
    #[wasm_bindgen(unchecked_return_type = "Position")]
    pub fn position(&self) -> JsValue {
        to_js(&PositionDto::new(&self.inner.position()))
    }

    /// Plays `move` for the player to move, rejecting any rule violation.
    #[wasm_bindgen(unchecked_return_type = "MoveEffect")]
    pub fn play(
        &mut self,
        #[wasm_bindgen(js_name = move, unchecked_param_type = "Move")] mv: JsValue,
    ) -> Result<JsValue, JsValue> {
        let color = color_text(self.inner.to_play()).to_owned();
        self.play_as(&color, mv, "strict")
    }

    /// Plays `move` for `color`. In "strict" mode a broken rule throws and
    /// nothing changes; in "record" mode the move is applied and
    /// the broken rules are listed in `violations`.
    #[wasm_bindgen(js_name = playAs, unchecked_return_type = "MoveEffect")]
    pub fn play_as(
        &mut self,
        #[wasm_bindgen(unchecked_param_type = "Color")] color: &str,
        #[wasm_bindgen(js_name = move, unchecked_param_type = "Move")] mv: JsValue,
        #[wasm_bindgen(unchecked_param_type = "Mode")] mode: &str,
    ) -> Result<JsValue, JsValue> {
        let size = self.inner.board().size();
        let color = parse_color(color)?;
        let mv = parse_move(size, mv)?;
        let mode = parse_mode(mode)?;
        let effect = self
            .inner
            .play_as(color, mv, mode)
            .map_err(|error| coded(ErrorClass::IllegalMove, error.code(), error, &[]))?;
        Ok(to_js(&MoveEffectDto {
            captured: points_xy(size, &effect.captured),
            suicided: points_xy(size, &effect.suicided),
            repeated_position: effect.repeated_position,
            violations: effect.violations.iter().map(|v| v.code()).collect(),
        }))
    }

    /// Takes back the last move and returns it, or `null` at the start.
    #[wasm_bindgen(unchecked_return_type = "PlayedMove | null")]
    pub fn undo(&mut self) -> JsValue {
        let size = self.inner.board().size();
        match self.inner.undo() {
            Some((color, mv)) => to_js(&PlayedMove::new(size, color, mv)),
            None => JsValue::NULL,
        }
    }
}
