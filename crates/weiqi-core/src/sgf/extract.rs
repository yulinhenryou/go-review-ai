//! A parsed tree to a typed game record.
//!
//! Extraction reads the main line (the root and each first child) and
//! translates properties; it does not replay moves, because legality depends
//! on rules the record may lack. [`GameRecord::replay`] replays in
//! [`ReplayMode::Record`] with rules and komi the caller has confirmed.
//!
//! Missing or unreadable metadata stays `None` with a warning and is never
//! replaced by a default. Structural contradictions are errors.

use crate::board::Color;
use crate::coord::{BoardSize, Move, Point};
use crate::game::{Game, Replay, ReplayError, ReplayMode, Setup, SetupError};
use crate::rules::{Komi, Rules};
use crate::scoring::GameResult;

use super::tree::{Property, SgfTree, Value};

/// Root properties: only allowed in the root node.
const ROOT: [&str; 6] = ["FF", "GM", "SZ", "CA", "AP", "ST"];

/// Game-info properties read into the record.
const INFO: [&str; 13] = [
    "RU", "KM", "HA", "PB", "PW", "BR", "WR", "DT", "EV", "RO", "PC", "GN", "RE",
];

/// Move and setup properties.
const PLAY: [&str; 6] = ["B", "W", "AB", "AW", "AE", "PL"];

/// Descriptive game information, as SimpleText.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct GameInfo {
    /// `PB`.
    pub black_player: Option<String>,
    /// `PW`.
    pub white_player: Option<String>,
    /// `BR`.
    pub black_rank: Option<String>,
    /// `WR`.
    pub white_rank: Option<String>,
    /// `DT`.
    pub date: Option<String>,
    /// `EV`.
    pub event: Option<String>,
    /// `RO`.
    pub round: Option<String>,
    /// `PC`.
    pub place: Option<String>,
    /// `GN`.
    pub name: Option<String>,
    /// `RE` as written. A stored result is metadata, not proof that the
    /// record is complete (MIGRATION G05).
    pub result_text: Option<String>,
    /// `RE` when it is in SGF form.
    pub result: Option<GameResult>,
}

/// One game read from an SGF tree.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct GameRecord {
    /// `SZ`, or 19x19 when absent (the FF\[4\] default for Go).
    pub size: BoardSize,
    /// `RU` when it names a known rule set.
    pub rules: Option<Rules>,
    /// `RU` as written.
    pub rules_text: Option<String>,
    /// `KM` when valid.
    pub komi: Option<Komi>,
    /// `HA` when it is a number.
    pub handicap: Option<u32>,
    /// Stones and player to move before the first move.
    pub setup: Setup,
    /// The main line's moves.
    pub moves: Vec<(Color, Move)>,
    /// Descriptive information.
    pub info: GameInfo,
    /// Tolerated irregularities.
    pub warnings: Vec<ExtractWarning>,
}

/// A tolerated irregularity in a game.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ExtractWarning {
    /// What was tolerated.
    pub kind: ExtractWarningKind,
    /// Index on the main line (0 is the root), when it concerns one node.
    pub node: Option<usize>,
}

/// The kinds of [`ExtractWarning`].
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum ExtractWarningKind {
    /// No `FF`.
    MissingFileFormat,
    /// No `GM`; Go is assumed.
    MissingGameType,
    /// No `SZ`; 19x19, the FF\[4\] default, is used.
    MissingSize,
    /// No `RU`; rules must be confirmed.
    MissingRules,
    /// `RU` names no known rule set; rules must be confirmed.
    UnknownRules(String),
    /// No `KM`; komi must be confirmed.
    MissingKomi,
    /// `KM` is not a valid komi; komi must be confirmed.
    InvalidKomi(String),
    /// `HA` is not a number.
    MalformedHandicap(String),
    /// `HA` disagrees with the number of black setup stones.
    HandicapMismatch {
        /// `HA`.
        declared: u32,
        /// Distinct black setup stones.
        stones: usize,
    },
    /// `RE` is not in SGF form; it is kept as text.
    MalformedResult(String),
    /// A game-info property outside the root.
    GameInfoOutsideRoot(String),
    /// Setup and a move in the same node; the setup is applied first.
    MixedSetupAndMove,
    /// `tt` read as a pass (FF\[3\] convention on boards up to 19x19).
    TtPass,
    /// The tree has variations; only the main line was read.
    FirstVariationOnly,
}

impl ExtractWarning {
    /// Stable machine-readable code.
    pub fn code(&self) -> &'static str {
        match self.kind {
            ExtractWarningKind::MissingFileFormat => "missing_ff",
            ExtractWarningKind::MissingGameType => "missing_gm",
            ExtractWarningKind::MissingSize => "missing_size",
            ExtractWarningKind::MissingRules => "missing_rules",
            ExtractWarningKind::UnknownRules(_) => "unknown_rules",
            ExtractWarningKind::MissingKomi => "missing_komi",
            ExtractWarningKind::InvalidKomi(_) => "invalid_komi",
            ExtractWarningKind::MalformedHandicap(_) => "malformed_handicap",
            ExtractWarningKind::HandicapMismatch { .. } => "handicap_mismatch",
            ExtractWarningKind::MalformedResult(_) => "malformed_result",
            ExtractWarningKind::GameInfoOutsideRoot(_) => "game_info_outside_root",
            ExtractWarningKind::MixedSetupAndMove => "mixed_setup_and_move",
            ExtractWarningKind::TtPass => "tt_pass",
            ExtractWarningKind::FirstVariationOnly => "first_variation_only",
        }
    }
}

/// A tree that cannot be read as one Go game.
#[derive(Clone, Debug, PartialEq, Eq, thiserror::Error)]
#[error("main-line node {node}: {kind}")]
pub struct ExtractError {
    /// What went wrong.
    pub kind: ExtractErrorKind,
    /// Index on the main line (0 is the root).
    pub node: usize,
}

/// The kinds of [`ExtractError`].
#[derive(Clone, Debug, PartialEq, Eq, thiserror::Error)]
pub enum ExtractErrorKind {
    /// `GM` is not 1.
    #[error("GM[{0}] is not Go")]
    NotGo(String),
    /// `SZ` is not `n` or `w:h`.
    #[error("malformed board size {0:?}")]
    MalformedSize(String),
    /// `SZ` is outside `1..=25`.
    #[error("unsupported board size {0:?}")]
    UnsupportedSize(String),
    /// A property appears twice in a node, or a root or game-info property
    /// appears in two nodes of the main line.
    #[error("duplicate property {0}")]
    DuplicateProperty(String),
    /// A single-valued property has several values.
    #[error("property {0} has several values")]
    MultiValued(String),
    /// `B` and `W` in one node.
    #[error("two moves in one node")]
    TwoMoves,
    /// A move, point or player that cannot be read.
    #[error("malformed {ident}[{value}]")]
    MalformedValue {
        /// The property.
        ident: String,
        /// Its raw value.
        value: String,
    },
    /// Setup after the first move, which the game model does not support.
    #[error("setup property {0} after the first move")]
    SetupAfterMoves(String),
    /// A root property outside the root.
    #[error("root property {0} outside the root")]
    RootPropertyOutsideRoot(String),
}

impl ExtractError {
    /// Stable machine-readable code.
    pub fn code(&self) -> &'static str {
        match self.kind {
            ExtractErrorKind::NotGo(_) => "not_go",
            ExtractErrorKind::MalformedSize(_) => "malformed_size",
            ExtractErrorKind::UnsupportedSize(_) => "unsupported_size",
            ExtractErrorKind::DuplicateProperty(_) => "duplicate_property",
            ExtractErrorKind::MultiValued(_) => "multi_valued_property",
            ExtractErrorKind::TwoMoves => "two_moves_in_node",
            ExtractErrorKind::MalformedValue { .. } => "malformed_value",
            ExtractErrorKind::SetupAfterMoves(_) => "setup_after_moves",
            ExtractErrorKind::RootPropertyOutsideRoot(_) => "root_property_outside_root",
        }
    }
}

/// Why [`GameRecord::replay`] failed.
#[derive(Clone, Copy, Debug, PartialEq, Eq, thiserror::Error)]
pub enum RecordReplayError {
    /// The setup stones are invalid.
    #[error(transparent)]
    Setup(#[from] SetupError),
    /// A move could not be applied even as recorded.
    #[error(transparent)]
    Replay(#[from] ReplayError),
}

impl RecordReplayError {
    /// Stable machine-readable code.
    pub fn code(&self) -> &'static str {
        match self {
            Self::Setup(error) => error.code(),
            Self::Replay(error) => error.error.code(),
        }
    }
}

impl GameRecord {
    /// Replays the main line as recorded with confirmed `rules` and `komi`;
    /// broken rules become warnings of the returned [`Replay`].
    pub fn replay(&self, rules: Rules, komi: Komi) -> Result<Replay, RecordReplayError> {
        let game = Game::with_setup(self.size, rules, komi, self.setup.clone())?;
        Ok(game.replay(&self.moves, ReplayMode::Record)?)
    }
}

/// A root or game-info property found on the main line.
struct Found<'t> {
    ident: &'static str,
    node: usize,
    property: &'t Property,
}

/// Reads the main line of `tree` as a game.
pub fn extract(tree: &SgfTree) -> Result<GameRecord, ExtractError> {
    let line: Vec<_> = tree
        .main_line()
        .into_iter()
        .filter_map(|id| tree.node(id))
        .collect();
    let mut warnings = Vec::new();
    let mut warn = |kind, node| warnings.push(ExtractWarning { kind, node });

    // Root and game-info properties, each at most once on the main line.
    let mut found: Vec<Found<'_>> = Vec::new();
    for (index, node) in line.iter().enumerate() {
        let properties = node.properties();
        for (i, property) in properties.iter().enumerate() {
            let ident = property.ident();
            let known = ROOT.iter().chain(&INFO).chain(&PLAY).find(|&&k| k == ident);
            let Some(&known) = known else { continue };
            let error = |kind| ExtractError { kind, node: index };
            if properties[..i].iter().any(|p| p.ident() == ident) {
                return Err(error(ExtractErrorKind::DuplicateProperty(ident.to_owned())));
            }
            if PLAY.contains(&known) {
                continue;
            }
            if index > 0 && ROOT.contains(&known) {
                return Err(error(ExtractErrorKind::RootPropertyOutsideRoot(
                    ident.to_owned(),
                )));
            }
            if found.iter().any(|f| f.ident == known) {
                return Err(error(ExtractErrorKind::DuplicateProperty(ident.to_owned())));
            }
            if index > 0 {
                warn(
                    ExtractWarningKind::GameInfoOutsideRoot(ident.to_owned()),
                    Some(index),
                );
            }
            found.push(Found {
                ident: known,
                node: index,
                property,
            });
        }
    }
    let text = |ident: &str| -> Result<Option<(usize, String)>, ExtractError> {
        match found.iter().find(|f| f.ident == ident) {
            None => Ok(None),
            Some(f) => Ok(Some((f.node, single(f.property, f.node)?.simple_text()))),
        }
    };

    match text("GM")? {
        None => warn(ExtractWarningKind::MissingGameType, None),
        Some((node, gm)) if gm.trim() != "1" => {
            return Err(ExtractError {
                kind: ExtractErrorKind::NotGo(gm),
                node,
            });
        }
        Some(_) => {}
    }
    if text("FF")?.is_none() {
        warn(ExtractWarningKind::MissingFileFormat, None);
    }
    let size = match text("SZ")? {
        None => {
            warn(ExtractWarningKind::MissingSize, None);
            BoardSize::square(19).unwrap_or_else(|_| unreachable!("19 is a valid size"))
        }
        Some((node, sz)) => parse_size(&sz).map_err(|kind| ExtractError { kind, node })?,
    };

    let rules_text = text("RU")?.map(|(_, ru)| ru);
    let rules = match &rules_text {
        None => {
            warn(ExtractWarningKind::MissingRules, None);
            None
        }
        Some(ru) => {
            let rules = Rules::from_name(ru.trim());
            if rules.is_none() {
                warn(ExtractWarningKind::UnknownRules(ru.clone()), None);
            }
            rules
        }
    };
    let komi = match text("KM")? {
        None => {
            warn(ExtractWarningKind::MissingKomi, None);
            None
        }
        Some((node, km)) => {
            let komi = km.trim().parse().ok().and_then(|p| Komi::new(p).ok());
            if komi.is_none() {
                warn(ExtractWarningKind::InvalidKomi(km), Some(node));
            }
            komi
        }
    };
    let handicap = match text("HA")? {
        None => None,
        Some((node, ha)) => {
            let handicap = ha.trim().parse().ok();
            if handicap.is_none() {
                warn(ExtractWarningKind::MalformedHandicap(ha), Some(node));
            }
            handicap
        }
    };
    let result_text = text("RE")?.map(|(_, re)| re);
    let result = result_text.as_deref().and_then(|re| {
        let result = GameResult::parse_sgf(re).ok();
        if result.is_none() {
            warn(ExtractWarningKind::MalformedResult(re.to_owned()), None);
        }
        result
    });
    let info = GameInfo {
        black_player: text("PB")?.map(|(_, v)| v),
        white_player: text("PW")?.map(|(_, v)| v),
        black_rank: text("BR")?.map(|(_, v)| v),
        white_rank: text("WR")?.map(|(_, v)| v),
        date: text("DT")?.map(|(_, v)| v),
        event: text("EV")?.map(|(_, v)| v),
        round: text("RO")?.map(|(_, v)| v),
        place: text("PC")?.map(|(_, v)| v),
        name: text("GN")?.map(|(_, v)| v),
        result_text,
        result,
    };

    // Moves and setup.
    let mut setup = Setup::default();
    let mut player = None;
    let mut moves = Vec::new();
    for (index, node) in line.iter().enumerate() {
        let error = |kind| ExtractError { kind, node: index };
        let mut mv = None;
        let mut has_setup = false;
        for property in node.properties() {
            let ident = property.ident();
            if matches!(ident, "AB" | "AW" | "AE" | "PL") {
                if !moves.is_empty() {
                    return Err(error(ExtractErrorKind::SetupAfterMoves(ident.to_owned())));
                }
                has_setup = true;
            }
            match ident {
                "B" | "W" => {
                    if mv.is_some() {
                        return Err(error(ExtractErrorKind::TwoMoves));
                    }
                    let color = if ident == "B" {
                        Color::Black
                    } else {
                        Color::White
                    };
                    let value = single(property, index)?;
                    let played = parse_move(size, value)
                        .ok_or_else(|| malformed(property, value))
                        .map_err(error)?;
                    if played.1 {
                        warn(ExtractWarningKind::TtPass, Some(index));
                    }
                    mv = Some((color, played.0));
                }
                "AB" | "AW" | "AE" => {
                    let mut points = Vec::new();
                    for value in property.values() {
                        let list = parse_points(size, value)
                            .ok_or_else(|| malformed(property, value))
                            .map_err(error)?;
                        points.extend(list);
                    }
                    // A point listed again replaces what was there, as on a board.
                    setup.black.retain(|p| !points.contains(p));
                    setup.white.retain(|p| !points.contains(p));
                    match ident {
                        "AB" => setup.black.extend(points),
                        "AW" => setup.white.extend(points),
                        _ => {}
                    }
                }
                "PL" => {
                    let value = single(property, index)?;
                    let color = match value.simple_text().trim() {
                        "B" | "b" => Color::Black,
                        "W" | "w" => Color::White,
                        _ => return Err(error(malformed(property, value))),
                    };
                    player = Some(color);
                }
                _ => {}
            }
        }
        if let Some(mv) = mv {
            if has_setup {
                warn(ExtractWarningKind::MixedSetupAndMove, Some(index));
            }
            moves.push(mv);
        }
    }
    setup.to_play = player
        .or_else(|| moves.first().map(|&(color, _)| color))
        .unwrap_or(Color::Black);

    if let Some(declared) = handicap.filter(|&h| h >= 2) {
        let mut stones = setup.black.clone();
        stones.sort_unstable();
        stones.dedup();
        if stones.len() != declared as usize || !setup.white.is_empty() {
            let stones = stones.len();
            warn(
                ExtractWarningKind::HandicapMismatch { declared, stones },
                None,
            );
        }
    }
    if tree.nodes().iter().any(|node| node.children().len() > 1) {
        warn(ExtractWarningKind::FirstVariationOnly, None);
    }

    Ok(GameRecord {
        size,
        rules,
        rules_text,
        komi,
        handicap,
        setup,
        moves,
        info,
        warnings,
    })
}

/// The only value of a single-valued property.
fn single(property: &Property, node: usize) -> Result<&Value, ExtractError> {
    match property.values() {
        [value] => Ok(value),
        _ => Err(ExtractError {
            kind: ExtractErrorKind::MultiValued(property.ident().to_owned()),
            node,
        }),
    }
}

fn malformed(property: &Property, value: &Value) -> ExtractErrorKind {
    ExtractErrorKind::MalformedValue {
        ident: property.ident().to_owned(),
        value: value.raw().to_owned(),
    }
}

/// `n` or `w:h`.
fn parse_size(text: &str) -> Result<BoardSize, ExtractErrorKind> {
    let malformed = || ExtractErrorKind::MalformedSize(text.to_owned());
    let number = |part: &str| part.trim().parse::<u8>().map_err(|_| malformed());
    let (width, height) = match text.split_once(':') {
        None => {
            let n = number(text)?;
            (n, n)
        }
        Some((w, h)) => (number(w)?, number(h)?),
    };
    BoardSize::new(width, height).map_err(|_| ExtractErrorKind::UnsupportedSize(text.to_owned()))
}

/// A move, and whether it was a `tt` pass.
fn parse_move(size: BoardSize, value: &Value) -> Option<(Move, bool)> {
    let raw = value.raw();
    if raw.is_empty() {
        return Some((Move::Pass, false));
    }
    if raw == "tt" && size.width() <= 19 && size.height() <= 19 {
        return Some((Move::Pass, true));
    }
    let point = size.parse_sgf_point(raw).ok()?;
    Some((Move::Play(point), false))
}

/// A point, or a compressed rectangle `ul:lr` (corners in either order).
fn parse_points(size: BoardSize, value: &Value) -> Option<Vec<Point>> {
    let raw = value.raw();
    let Some((first, second)) = raw.split_once(':') else {
        return size.parse_sgf_point(raw).ok().map(|point| vec![point]);
    };
    let (x1, y1) = size.xy(size.parse_sgf_point(first).ok()?)?;
    let (x2, y2) = size.xy(size.parse_sgf_point(second).ok()?)?;
    let mut points = Vec::new();
    for y in y1.min(y2)..=y1.max(y2) {
        for x in x1.min(x2)..=x1.max(x2) {
            points.push(size.point(x, y)?);
        }
    }
    Some(points)
}
