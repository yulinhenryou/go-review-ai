//! SGF parsing, extraction and replay: bytes, then `SgfTree`, then
//! `GameRecord`, then `Replay`, with rules and komi confirmed in between.

use pyo3::prelude::*;
use weiqi::sgf::{self, GameInfo, GameRecord, RecordReplayError, SgfTree};

use crate::game::{PyPosition, PyRules, PySetup, komi};
use crate::{ExtractError, ReplayError, SgfError, coded, moves_object};

pub(crate) fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<PySgfWarning>()?;
    m.add_class::<PySgfTree>()?;
    m.add_class::<PyCollection>()?;
    m.add_class::<PyGameInfo>()?;
    m.add_class::<PyExtractWarning>()?;
    m.add_class::<PyGameRecord>()?;
    m.add_class::<PyReplayWarning>()?;
    m.add_class::<PyReplay>()?;
    m.add_function(wrap_pyfunction!(parse_sgf, m)?)?;
    m.add_function(wrap_pyfunction!(extract, m)?)?;
    Ok(())
}

/// A lenient reading reported by the decoder or parser.
#[pyclass(name = "SgfWarning", module = "weiqi_core", frozen, get_all)]
#[derive(Clone)]
struct PySgfWarning {
    code: &'static str,
    /// Byte offset in the decoded text, when there is one.
    offset: Option<usize>,
}

/// One parsed game tree, kept as the core's arena; it is not copied into
/// Python objects.
#[pyclass(name = "SgfTree", module = "weiqi_core", frozen)]
struct PySgfTree {
    inner: SgfTree,
}

#[pymethods]
impl PySgfTree {
    /// Canonical SGF text for this tree.
    fn to_sgf(&self) -> String {
        self.inner.to_sgf()
    }

    /// The number of nodes.
    fn __len__(&self) -> usize {
        self.inner.len()
    }
}

/// The games in an SGF file, with its decoding and warnings.
#[pyclass(name = "Collection", module = "weiqi_core", frozen)]
struct PyCollection {
    games: Vec<Py<PySgfTree>>,
    #[pyo3(get)]
    encoding: &'static str,
    #[pyo3(get)]
    warnings: Vec<PySgfWarning>,
}

#[pymethods]
impl PyCollection {
    #[getter]
    fn games(&self, py: Python<'_>) -> Vec<Py<PySgfTree>> {
        // New references to the same tree objects; the trees are not copied.
        self.games.iter().map(|tree| tree.clone_ref(py)).collect()
    }
}

/// Parses SGF bytes in any supported encoding. The parse runs without the
/// GIL, so other Python threads keep running.
#[pyfunction]
fn parse_sgf(py: Python<'_>, data: &[u8]) -> PyResult<PyCollection> {
    // `data` borrows the immutable `bytes` object for the length of this
    // call; no Python object is touched while the GIL is released.
    let collection = py.detach(|| sgf::parse(data)).map_err(|error| {
        coded::<SgfError>(py, error.code(), &error, &[("offset", Some(error.offset))])
    })?;
    let games = collection
        .games
        .into_iter()
        .map(|inner| Py::new(py, PySgfTree { inner }))
        .collect::<PyResult<_>>()?;
    Ok(PyCollection {
        games,
        encoding: collection.encoding,
        warnings: collection
            .warnings
            .iter()
            .map(|w| PySgfWarning {
                code: w.code(),
                offset: w.offset,
            })
            .collect(),
    })
}

/// Reads the main line of `tree` into a game record.
#[pyfunction]
fn extract(py: Python<'_>, tree: &Bound<'_, PySgfTree>) -> PyResult<PyGameRecord> {
    // `get` reads a frozen object without a run-time borrow check.
    sgf::extract(&tree.get().inner)
        .map(|inner| PyGameRecord { inner })
        .map_err(|error| {
            coded::<ExtractError>(py, error.code(), &error, &[("node", Some(error.node))])
        })
}

/// Game information from the root node.
#[pyclass(name = "GameInfo", module = "weiqi_core", frozen, get_all)]
struct PyGameInfo {
    black_player: Option<String>,
    white_player: Option<String>,
    black_rank: Option<String>,
    white_rank: Option<String>,
    date: Option<String>,
    event: Option<String>,
    round: Option<String>,
    place: Option<String>,
    name: Option<String>,
    result_text: Option<String>,
}

impl PyGameInfo {
    fn from_core(info: &GameInfo) -> Self {
        Self {
            black_player: info.black_player.clone(),
            white_player: info.white_player.clone(),
            black_rank: info.black_rank.clone(),
            white_rank: info.white_rank.clone(),
            date: info.date.clone(),
            event: info.event.clone(),
            round: info.round.clone(),
            place: info.place.clone(),
            name: info.name.clone(),
            result_text: info.result_text.clone(),
        }
    }
}

/// A lenient reading reported by extraction.
#[pyclass(name = "ExtractWarning", module = "weiqi_core", frozen, get_all)]
#[derive(Clone)]
struct PyExtractWarning {
    code: &'static str,
    /// Index of the node it concerns, when there is one.
    node: Option<usize>,
}

/// The main line of a game tree. Each attribute access builds new Python
/// values from the record it owns.
#[pyclass(name = "GameRecord", module = "weiqi_core", frozen)]
struct PyGameRecord {
    inner: GameRecord,
}

#[pymethods]
impl PyGameRecord {
    #[getter]
    fn width(&self) -> u8 {
        self.inner.size.width()
    }

    #[getter]
    fn height(&self) -> u8 {
        self.inner.size.height()
    }

    /// `None` when `RU` is missing or not recognized (see `rules_text`).
    #[getter]
    fn rules(&self) -> Option<PyRules> {
        self.inner.rules.map(|inner| PyRules { inner })
    }

    #[getter]
    fn rules_text(&self) -> Option<String> {
        self.inner.rules_text.clone()
    }

    /// `None` when `KM` is missing or invalid.
    #[getter]
    fn komi(&self) -> Option<f64> {
        self.inner.komi.map(weiqi::Komi::points)
    }

    #[getter]
    fn handicap(&self) -> Option<u32> {
        self.inner.handicap
    }

    #[getter]
    fn setup(&self) -> PySetup {
        PySetup::from_core(self.inner.size, &self.inner.setup)
    }

    #[getter]
    fn moves<'py>(&self, py: Python<'py>) -> PyResult<Vec<(&'static str, Bound<'py, PyAny>)>> {
        moves_object(py, self.inner.size, &self.inner.moves)
    }

    #[getter]
    fn info(&self) -> PyGameInfo {
        PyGameInfo::from_core(&self.inner.info)
    }

    #[getter]
    fn warnings(&self) -> Vec<PyExtractWarning> {
        self.inner
            .warnings
            .iter()
            .map(|w| PyExtractWarning {
                code: w.code(),
                node: w.node,
            })
            .collect()
    }

    /// Replays the record from its setup in "record" mode, with the rules
    /// and komi a user confirmed.
    fn replay(&self, py: Python<'_>, rules: PyRef<'_, PyRules>, komi: f64) -> PyResult<PyReplay> {
        let komi = self::komi(py, komi)?;
        let replay = self.inner.replay(rules.inner, komi).map_err(|error| {
            let move_number = match error {
                RecordReplayError::Replay(e) => Some(e.move_number),
                RecordReplayError::Setup(_) => None,
            };
            coded::<ReplayError>(py, error.code(), &error, &[("move_number", move_number)])
        })?;
        let positions = replay
            .positions
            .iter()
            .map(|p| Py::new(py, PyPosition::from_core(p)))
            .collect::<PyResult<_>>()?;
        Ok(PyReplay {
            positions,
            warnings: replay
                .warnings
                .iter()
                .map(|w| PyReplayWarning {
                    move_number: w.move_number,
                    code: w.kind.code(),
                })
                .collect(),
        })
    }
}

/// A rule broken by a recorded move, or a repeated position.
#[pyclass(name = "ReplayWarning", module = "weiqi_core", frozen, get_all)]
#[derive(Clone)]
struct PyReplayWarning {
    /// 1-based.
    move_number: usize,
    code: &'static str,
}

/// Every position of a replayed record and its warnings.
#[pyclass(name = "Replay", module = "weiqi_core", frozen)]
struct PyReplay {
    /// Built once: a long game has hundreds of positions.
    positions: Vec<Py<PyPosition>>,
    #[pyo3(get)]
    warnings: Vec<PyReplayWarning>,
}

#[pymethods]
impl PyReplay {
    /// The starting position, then the position after each move.
    #[getter]
    fn positions(&self, py: Python<'_>) -> Vec<Py<PyPosition>> {
        self.positions.iter().map(|p| p.clone_ref(py)).collect()
    }
}
