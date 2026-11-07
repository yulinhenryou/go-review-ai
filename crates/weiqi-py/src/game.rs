//! Rules, positions and the mutable `Game`.

use pyo3::prelude::*;
use weiqi::{
    BoardSize, Cell, Game, KoRule, Komi, Position, ReplayMode, Rules, ScoringRule, Setup,
    SuicideRule, TaxRule, WhiteHandicapBonus,
};

use crate::{
    IllegalMoveError, board_size, coded, color_text, core_error, move_object, moves_object,
    parse_color, parse_move, point_at, point_xy, points_xy,
};

pub(crate) fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<PyRules>()?;
    m.add_class::<PySetup>()?;
    m.add_class::<PyCaptures>()?;
    m.add_class::<PyPosition>()?;
    m.add_class::<PyMoveEffect>()?;
    m.add_class::<PyGame>()?;
    Ok(())
}

pub(crate) fn komi(py: Python<'_>, points: f64) -> PyResult<Komi> {
    Komi::new(points).map_err(|error| core_error(py, error.code(), error))
}

/// A rule set; build one with `Rules.from_name`.
#[pyclass(name = "Rules", module = "weiqi_core", frozen, eq)]
#[derive(Clone, Copy, PartialEq)]
pub(crate) struct PyRules {
    pub(crate) inner: Rules,
}

#[pymethods]
impl PyRules {
    /// The rule set KataGo calls `name`, e.g. "japanese" or "tromp-taylor".
    #[staticmethod]
    fn from_name(py: Python<'_>, name: &str) -> PyResult<Self> {
        Rules::from_name(name)
            .map(|inner| Self { inner })
            .ok_or_else(|| core_error(py, "unknown_rules", format!("unknown rules {name:?}")))
    }

    #[getter]
    fn ko(&self) -> &'static str {
        match self.inner.ko {
            KoRule::Simple => "simple",
            KoRule::Positional => "positional",
            KoRule::Situational => "situational",
        }
    }

    #[getter]
    fn scoring(&self) -> &'static str {
        match self.inner.scoring {
            ScoringRule::Area => "area",
            ScoringRule::Territory => "territory",
        }
    }

    #[getter]
    fn tax(&self) -> &'static str {
        match self.inner.tax {
            TaxRule::None => "none",
            TaxRule::Seki => "seki",
            TaxRule::All => "all",
        }
    }

    #[getter]
    fn suicide(&self) -> &'static str {
        match self.inner.suicide {
            SuicideRule::Forbidden => "forbidden",
            SuicideRule::MultiStoneAllowed => "multi_stone_allowed",
        }
    }

    #[getter]
    fn button(&self) -> bool {
        self.inner.button
    }

    /// KataGo's names for its `whiteHandicapBonus` values.
    #[getter]
    fn white_handicap_bonus(&self) -> &'static str {
        match self.inner.white_handicap_bonus {
            WhiteHandicapBonus::Zero => "0",
            WhiteHandicapBonus::N => "N",
            WhiteHandicapBonus::NMinusOne => "N-1",
        }
    }

    #[getter]
    fn friendly_pass_ok(&self) -> bool {
        self.inner.friendly_pass_ok
    }

    fn __repr__(&self) -> String {
        let python_bool = |b: bool| if b { "True" } else { "False" };
        format!(
            "Rules(ko={:?}, scoring={:?}, tax={:?}, suicide={:?}, button={}, \
             white_handicap_bonus={:?}, friendly_pass_ok={})",
            self.ko(),
            self.scoring(),
            self.tax(),
            self.suicide(),
            python_bool(self.button()),
            self.white_handicap_bonus(),
            python_bool(self.friendly_pass_ok()),
        )
    }
}

/// Stones before the first move and who moves first.
#[pyclass(name = "Setup", module = "weiqi_core", frozen, get_all)]
#[derive(Clone)]
pub(crate) struct PySetup {
    black: Vec<(i64, i64)>,
    white: Vec<(i64, i64)>,
    to_play: &'static str,
}

#[pymethods]
impl PySetup {
    #[new]
    #[pyo3(signature = (black = Vec::new(), white = Vec::new(), to_play = "B"))]
    fn new(
        py: Python<'_>,
        black: Vec<(i64, i64)>,
        white: Vec<(i64, i64)>,
        to_play: &str,
    ) -> PyResult<Self> {
        let to_play = color_text(parse_color(py, to_play)?);
        Ok(Self {
            black,
            white,
            to_play,
        })
    }
}

impl PySetup {
    pub(crate) fn from_core(size: BoardSize, setup: &Setup) -> Self {
        let xy = |points: &[weiqi::Point]| {
            points_xy(size, points)
                .into_iter()
                .map(|(x, y)| (i64::from(x), i64::from(y)))
                .collect()
        };
        Self {
            black: xy(&setup.black),
            white: xy(&setup.white),
            to_play: color_text(setup.to_play),
        }
    }

    /// The core setup on this board. Points off the board raise the core's
    /// `setup_off_board` code.
    fn to_core(&self, py: Python<'_>, size: BoardSize) -> PyResult<Setup> {
        let points = |xys: &[(i64, i64)]| {
            xys.iter()
                .map(|&xy| {
                    point_at(size, xy).ok_or_else(|| {
                        core_error(
                            py,
                            "setup_off_board",
                            format!("setup point {xy:?} is not on the board"),
                        )
                    })
                })
                .collect::<PyResult<Vec<_>>>()
        };
        Ok(Setup {
            black: points(&self.black)?,
            white: points(&self.white)?,
            to_play: parse_color(py, self.to_play)?,
        })
    }
}

/// Stones of each color removed from the board.
#[pyclass(name = "Captures", module = "weiqi_core", frozen, get_all, eq)]
#[derive(Clone, PartialEq)]
pub(crate) struct PyCaptures {
    black: u32,
    white: u32,
}

/// An owned snapshot of a position.
#[pyclass(name = "Position", module = "weiqi_core", frozen, get_all)]
#[derive(Clone)]
pub(crate) struct PyPosition {
    width: u8,
    height: u8,
    /// Row-major from the top left: `cells[y * width + x]`.
    cells: Vec<Option<&'static str>>,
    to_play: &'static str,
    ko_ban: Option<(u8, u8)>,
    captures: PyCaptures,
    consecutive_passes: u32,
    stones_hash: u128,
    situation_hash: u128,
}

impl PyPosition {
    pub(crate) fn from_core(position: &Position) -> Self {
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
            captures: PyCaptures {
                black: position.captures.black,
                white: position.captures.white,
            },
            consecutive_passes: position.consecutive_passes,
            stones_hash: position.stones_hash.0,
            situation_hash: position.situation_hash.0,
        }
    }
}

/// What an applied move changed.
#[pyclass(name = "MoveEffect", module = "weiqi_core", frozen, get_all)]
pub(crate) struct PyMoveEffect {
    captured: Vec<(u8, u8)>,
    suicided: Vec<(u8, u8)>,
    repeated_position: bool,
    violations: Vec<&'static str>,
}

fn parse_mode(py: Python<'_>, text: &str) -> PyResult<ReplayMode> {
    match text {
        "strict" => Ok(ReplayMode::Strict),
        "record" => Ok(ReplayMode::Record),
        _ => Err(core_error(
            py,
            "malformed_mode",
            format!("mode must be \"strict\" or \"record\", not {text:?}"),
        )),
    }
}

/// A game in progress. It owns its Rust `Game`; methods borrow it.
#[pyclass(name = "Game", module = "weiqi_core")]
pub(crate) struct PyGame {
    inner: Game,
}

#[pymethods]
impl PyGame {
    #[new]
    #[pyo3(signature = (width, height, rules, komi, setup = None))]
    fn new(
        py: Python<'_>,
        width: i64,
        height: i64,
        rules: PyRef<'_, PyRules>,
        komi: f64,
        setup: Option<PyRef<'_, PySetup>>,
    ) -> PyResult<Self> {
        let size = board_size(py, width, height)?;
        let komi = self::komi(py, komi)?;
        let inner = match setup {
            None => Game::new(size, rules.inner, komi),
            Some(setup) => {
                let setup = setup.to_core(py, size)?;
                Game::with_setup(size, rules.inner, komi, setup)
                    .map_err(|error| core_error(py, error.code(), error))?
            }
        };
        Ok(Self { inner })
    }

    #[getter]
    fn width(&self) -> u8 {
        self.inner.board().size().width()
    }

    #[getter]
    fn height(&self) -> u8 {
        self.inner.board().size().height()
    }

    #[getter]
    fn rules(&self) -> PyRules {
        PyRules {
            inner: self.inner.rules(),
        }
    }

    #[getter]
    fn komi(&self) -> f64 {
        self.inner.komi().points()
    }

    #[getter]
    fn to_play(&self) -> &'static str {
        color_text(self.inner.to_play())
    }

    #[getter]
    fn move_count(&self) -> usize {
        self.inner.move_count()
    }

    /// The moves played so far, as `(color, move)` pairs.
    fn moves<'py>(&self, py: Python<'py>) -> PyResult<Vec<(&'static str, Bound<'py, PyAny>)>> {
        moves_object(py, self.inner.board().size(), &self.inner.moves())
    }

    /// A snapshot of the current position.
    fn position(&self) -> PyPosition {
        PyPosition::from_core(&self.inner.position())
    }

    /// Plays `move` for the player to move, rejecting any rule violation.
    fn play(&mut self, r#move: &Bound<'_, PyAny>) -> PyResult<PyMoveEffect> {
        let color = color_text(self.inner.to_play());
        self.play_as(color, r#move, "strict")
    }

    /// Plays `move` for `color`. In "strict" mode a broken rule raises and
    /// nothing changes; in "record" mode the move is applied and the broken
    /// rules are listed in `violations`.
    #[pyo3(signature = (color, r#move, mode = "strict"))]
    fn play_as(
        &mut self,
        color: &str,
        r#move: &Bound<'_, PyAny>,
        mode: &str,
    ) -> PyResult<PyMoveEffect> {
        let py = r#move.py();
        let size = self.inner.board().size();
        let color = parse_color(py, color)?;
        let mv = parse_move(size, r#move)?;
        let mode = parse_mode(py, mode)?;
        let effect = self
            .inner
            .play_as(color, mv, mode)
            .map_err(|error| coded::<IllegalMoveError>(py, error.code(), error, &[]))?;
        Ok(PyMoveEffect {
            captured: points_xy(size, &effect.captured),
            suicided: points_xy(size, &effect.suicided),
            repeated_position: effect.repeated_position,
            violations: effect.violations.iter().map(|v| v.code()).collect(),
        })
    }

    /// Takes back the last move and returns it, or `None` at the start.
    fn undo<'py>(
        &mut self,
        py: Python<'py>,
    ) -> PyResult<Option<(&'static str, Bound<'py, PyAny>)>> {
        let size = self.inner.board().size();
        self.inner
            .undo()
            .map(|(color, mv)| Ok((color_text(color), move_object(py, size, mv)?)))
            .transpose()
    }
}
