//! Python bindings for `weiqi-core`, imported as `weiqi_core`.
//!
//! The boundary copies: every value handed to Python is an owned snapshot
//! (a `#[pyclass]` that owns its Rust data, or plain lists, tuples and
//! strings), so no Python object ever borrows from a Rust game. The one
//! mutable object is [`game::PyGame`], which owns its [`weiqi::Game`]; PyO3
//! checks its borrows at run time. The other classes are `frozen` (read-only
//! after creation), so PyO3 needs no borrow checks for them.
//!
//! Text forms follow `testdata/conformance/README.md` where Python has no
//! better native type: colors are `"B"`/`"W"`, a point is an `(x, y)` tuple
//! from the top left, a move is a point or `"pass"`, and hashes are Python
//! ints (128 bits fit exactly). The stub `weiqi_core.pyi` documents the API.

use std::fmt::Display;

use pyo3::create_exception;
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::{PyInt, PyString};
use pyo3::{PyTypeInfo, intern};
use weiqi::{BoardSize, Color, Move, Point};

mod game;
mod sgf;

create_exception!(
    weiqi_core,
    CoreError,
    PyValueError,
    "Invalid input; `code` is the core's stable machine-readable code."
);
create_exception!(
    weiqi_core,
    IllegalMoveError,
    CoreError,
    "A move that was not applied."
);
create_exception!(weiqi_core, SgfError, CoreError, "Bytes that are not SGF.");
create_exception!(
    weiqi_core,
    ExtractError,
    CoreError,
    "An SGF game tree that is not a playable game record."
);
create_exception!(
    weiqi_core,
    ReplayError,
    CoreError,
    "A game record whose setup or moves cannot be replayed."
);

/// An exception of type `E` carrying `code` and the named extra attributes.
fn coded<E: PyTypeInfo>(
    py: Python<'_>,
    code: &str,
    message: impl Display,
    extras: &[(&str, Option<usize>)],
) -> PyErr {
    let error = PyErr::new::<E, _>(message.to_string());
    let value = error.value(py);
    // A fresh exception instance has a `__dict__`, so these cannot fail.
    value
        .setattr(intern!(py, "code"), code)
        .expect("exception attribute");
    for &(name, extra) in extras {
        value.setattr(name, extra).expect("exception attribute");
    }
    error
}

/// A [`CoreError`] with only a code.
fn core_error(py: Python<'_>, code: &str, message: impl Display) -> PyErr {
    coded::<CoreError>(py, code, message, &[])
}

// --- Text forms ---

fn color_text(color: Color) -> &'static str {
    match color {
        Color::Black => "B",
        Color::White => "W",
    }
}

fn parse_color(py: Python<'_>, text: &str) -> PyResult<Color> {
    match text {
        "B" => Ok(Color::Black),
        "W" => Ok(Color::White),
        _ => Err(core_error(
            py,
            "malformed_color",
            format!("color must be \"B\" or \"W\", not {text:?}"),
        )),
    }
}

/// A board size from Python ints, which may be out of `u8` range.
fn board_size(py: Python<'_>, width: i64, height: i64) -> PyResult<BoardSize> {
    // Ints outside `u8` become 0, which the core rejects like any bad size.
    let side = |n: i64| u8::try_from(n).unwrap_or(0);
    BoardSize::new(side(width), side(height)).map_err(|error| {
        core_error(
            py,
            error.code(),
            format!(
                "unsupported board size {width}x{height} (each side must be 1..={})",
                weiqi::MAX_BOARD_SIZE
            ),
        )
    })
}

/// The point at `(x, y)` on this board, if there is one.
fn point_at(size: BoardSize, (x, y): (i64, i64)) -> Option<Point> {
    size.point(u8::try_from(x).ok()?, u8::try_from(y).ok()?)
}

/// `(x, y)` of a point on this board.
fn point_xy(size: BoardSize, point: Point) -> (u8, u8) {
    size.xy(point).expect("point belongs to this board")
}

fn points_xy(size: BoardSize, points: &[Point]) -> Vec<(u8, u8)> {
    points.iter().map(|&p| point_xy(size, p)).collect()
}

/// A move from Python: an `(x, y)` tuple or `"pass"`. Points off this board
/// raise [`IllegalMoveError`] with the core's `off_board` code.
fn parse_move(size: BoardSize, value: &Bound<'_, PyAny>) -> PyResult<Move> {
    let py = value.py();
    if let Ok(text) = value.cast::<PyString>() {
        return match text.to_str()? {
            "pass" => Ok(Move::Pass),
            other => Err(core_error(
                py,
                "malformed_move",
                format!("a move is an (x, y) tuple or \"pass\", not {other:?}"),
            )),
        };
    }
    let malformed = || {
        core_error(
            py,
            "malformed_move",
            "a move is an (x, y) tuple of ints or \"pass\"",
        )
    };
    let (x, y): (Bound<'_, PyAny>, Bound<'_, PyAny>) = value.extract().map_err(|_| malformed())?;
    // Any int is a coordinate; one too large for i64 is off every board.
    let coordinate = |c: &Bound<'_, PyAny>| -> PyResult<i64> {
        let int = c.cast::<PyInt>().map_err(|_| malformed())?;
        Ok(int.extract::<i64>().unwrap_or(i64::MAX))
    };
    let xy = (coordinate(&x)?, coordinate(&y)?);
    point_at(size, xy).map(Move::Play).ok_or_else(|| {
        let error = weiqi::IllegalMove::OffBoard;
        coded::<IllegalMoveError>(py, error.code(), format!("({x}, {y}): {error}"), &[])
    })
}

/// A move as Python sees it: `(x, y)` or `"pass"`.
fn move_object<'py>(py: Python<'py>, size: BoardSize, mv: Move) -> PyResult<Bound<'py, PyAny>> {
    Ok(match mv {
        Move::Play(point) => point_xy(size, point).into_pyobject(py)?.into_any(),
        Move::Pass => intern!(py, "pass").clone().into_any(),
    })
}

/// `[(color, move)]` for Python.
fn moves_object<'py>(
    py: Python<'py>,
    size: BoardSize,
    moves: &[(Color, Move)],
) -> PyResult<Vec<(&'static str, Bound<'py, PyAny>)>> {
    moves
        .iter()
        .map(|&(color, mv)| Ok((color_text(color), move_object(py, size, mv)?)))
        .collect()
}

// --- GTP vertices (the notation KataGo speaks) ---

/// Formats a move as a GTP vertex such as `"Q16"`, or `"pass"`.
///
/// Raises `CoreError` for a bad board size or a malformed move, and
/// `IllegalMoveError` (`off_board`) for a point outside the board.
#[pyfunction]
fn to_gtp(move_: &Bound<'_, PyAny>, width: i64, height: i64) -> PyResult<String> {
    let size = board_size(move_.py(), width, height)?;
    let mv = parse_move(size, move_)?;
    // `parse_move` only returns points on `size`, so formatting cannot fail.
    Ok(size.to_gtp(mv).expect("move is on this board"))
}

/// Parses a GTP vertex such as `"Q16"` or `"pass"` (any letter case).
///
/// Raises `CoreError` with `malformed_coordinate` or
/// `coordinate_out_of_range`.
#[pyfunction]
fn from_gtp<'py>(
    py: Python<'py>,
    vertex: &str,
    width: i64,
    height: i64,
) -> PyResult<Bound<'py, PyAny>> {
    let size = board_size(py, width, height)?;
    let mv = size
        .parse_gtp(vertex)
        .map_err(|error| core_error(py, error.code(), error))?;
    move_object(py, size, mv)
}

/// The `weiqi_core` module.
#[pymodule]
fn weiqi_core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    let py = m.py();
    m.add("ZOBRIST_VERSION", weiqi::ZOBRIST_VERSION)?;
    m.add("MAX_BOARD_SIZE", weiqi::MAX_BOARD_SIZE)?;
    m.add("CoreError", py.get_type::<CoreError>())?;
    m.add("IllegalMoveError", py.get_type::<IllegalMoveError>())?;
    m.add("SgfError", py.get_type::<SgfError>())?;
    m.add("ExtractError", py.get_type::<ExtractError>())?;
    m.add("ReplayError", py.get_type::<ReplayError>())?;
    m.add_function(wrap_pyfunction!(to_gtp, m)?)?;
    m.add_function(wrap_pyfunction!(from_gtp, m)?)?;
    game::register(m)?;
    sgf::register(m)?;
    Ok(())
}
