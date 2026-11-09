//! A game: turn order, ko and superko, passes, setup stones, undo and replay.
//!
//! [`Game::play`] is strict: a move that breaks a rule is rejected and the game
//! is unchanged. [`Game::play_as`] with [`ReplayMode::Record`] applies a move as
//! a game record wrote it and reports the rules it broke, so that real-world
//! records with quirks stay reviewable. Only off-board and occupied points
//! cannot be applied in either mode.
//!
//! Two consecutive passes do not end the game here: the core only counts them
//! ([`Game::consecutive_passes`]) and the product layer decides what follows.

use crate::board::{Board, Cell, Chain, Color, IllegalPlacement, Placement};
use crate::coord::{BoardSize, Move, Point};
use crate::rules::{KoRule, Komi, Rules};
use crate::zobrist::{self, Hash128};

/// A rule that a move broke.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, thiserror::Error)]
pub enum RuleViolation {
    /// The other player was to move.
    #[error("move played out of turn")]
    OutOfTurn,
    /// Immediate recapture of a single-stone ko.
    #[error("immediate recapture of a ko")]
    Ko,
    /// The placement recreates a forbidden earlier position.
    #[error("move repeats an earlier position (superko)")]
    Superko,
    /// The placement leaves its own chain without liberties.
    #[error("move would be suicide")]
    Suicide,
}

impl RuleViolation {
    /// Stable machine-readable code.
    pub const fn code(self) -> &'static str {
        match self {
            Self::OutOfTurn => "out_of_turn",
            Self::Ko => "ko_violation",
            Self::Superko => "superko_violation",
            Self::Suicide => "suicide",
        }
    }
}

/// Why a move was not applied.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, thiserror::Error)]
pub enum IllegalMove {
    /// The point does not belong to this board.
    #[error("point is not on the board")]
    OffBoard,
    /// A stone is already there.
    #[error("point is occupied")]
    Occupied,
    /// A rule was broken (strict play only).
    #[error(transparent)]
    Rule(#[from] RuleViolation),
}

impl IllegalMove {
    /// Stable machine-readable code.
    pub const fn code(self) -> &'static str {
        match self {
            Self::OffBoard => "off_board",
            Self::Occupied => "occupied",
            Self::Rule(violation) => violation.code(),
        }
    }
}

/// How rule violations are treated.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum ReplayMode {
    /// Reject moves that break a rule (manual entry).
    Strict,
    /// Apply moves as recorded and report broken rules (imported records).
    Record,
}

/// Stones of each color removed from the board by captures or suicide.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Hash)]
pub struct Captures {
    /// Black stones removed.
    pub black: u32,
    /// White stones removed.
    pub white: u32,
}

impl Captures {
    fn slot(&mut self, color: Color) -> &mut u32 {
        match color {
            Color::Black => &mut self.black,
            Color::White => &mut self.white,
        }
    }
}

/// What an applied move changed.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct MoveEffect {
    /// Opponent stones captured.
    pub captured: Vec<Point>,
    /// Own stones removed by suicide, the new stone included.
    pub suicided: Vec<Point>,
    /// The placement broke no rule but recreated an earlier arrangement of
    /// stones, for example a long cycle under simple ko.
    pub repeated_position: bool,
    /// Rules broken by a move applied in [`ReplayMode::Record`].
    pub violations: Vec<RuleViolation>,
}

/// Stones present before the first move (handicap or SGF `AB`/`AW`), and who
/// moves first.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Setup {
    /// Black stones.
    pub black: Vec<Point>,
    /// White stones.
    pub white: Vec<Point>,
    /// The player to move first.
    pub to_play: Color,
}

impl Default for Setup {
    fn default() -> Self {
        Self {
            black: Vec::new(),
            white: Vec::new(),
            to_play: Color::Black,
        }
    }
}

/// An invalid [`Setup`].
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, thiserror::Error)]
pub enum SetupError {
    /// A setup point is not on the board.
    #[error("setup point {0:?} is not on the board")]
    OffBoard(Point),
    /// A point is listed for both colors.
    #[error("setup point {0:?} is listed for both colors")]
    Conflict(Point),
    /// A setup chain has no liberties.
    #[error("setup chain at {0:?} has no liberties")]
    NoLiberties(Point),
}

impl SetupError {
    /// Stable machine-readable code.
    pub const fn code(self) -> &'static str {
        match self {
            Self::OffBoard(_) => "setup_off_board",
            Self::Conflict(_) => "setup_conflict",
            Self::NoLiberties(_) => "setup_no_liberties",
        }
    }
}

/// An owned snapshot of a game position.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Position {
    /// Board dimensions.
    pub size: BoardSize,
    /// Every point's content, in index order.
    pub cells: Vec<Cell>,
    /// The player to move.
    pub to_play: Color,
    /// The point `to_play` may not play because of simple ko. Always `None`
    /// under superko rules, where the history decides instead.
    pub ko_ban: Option<Point>,
    /// Stones removed so far.
    pub captures: Captures,
    /// Passes since the last placement.
    pub consecutive_passes: u32,
    /// Hash of the stones (and board size) only.
    pub stones_hash: Hash128,
    /// Hash of stones, player to move and ko ban.
    pub situation_hash: Hash128,
}

/// A warning raised while replaying moves.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum WarningKind {
    /// The move broke a rule and was applied as recorded.
    Violation(RuleViolation),
    /// The move legally recreated an earlier arrangement of stones.
    RepeatedPosition,
}

impl WarningKind {
    /// Stable machine-readable code.
    pub const fn code(self) -> &'static str {
        match self {
            Self::Violation(violation) => violation.code(),
            Self::RepeatedPosition => "repeated_position",
        }
    }
}

/// A warning and the move that raised it.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub struct ReplayWarning {
    /// 1-based index into the replayed moves.
    pub move_number: usize,
    /// What happened.
    pub kind: WarningKind,
}

/// A move that could not be applied during replay.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, thiserror::Error)]
#[error("move {move_number}: {error}")]
pub struct ReplayError {
    /// 1-based index into the replayed moves.
    pub move_number: usize,
    /// Why it failed.
    pub error: IllegalMove,
}

/// The result of [`Game::replay`].
#[derive(Clone, Debug)]
pub struct Replay {
    /// The game after the last move.
    pub game: Game,
    /// The starting position followed by the position after each move.
    pub positions: Vec<Position>,
    /// Warnings in move order.
    pub warnings: Vec<ReplayWarning>,
}

/// Everything needed to take back one move.
#[derive(Clone, Debug)]
struct Undo {
    color: Color,
    mv: Move,
    placement: Placement,
    to_play: Color,
    ko_ban: Option<Point>,
    passes: u32,
    stones_hash: Hash128,
}

/// Whether recreating `stones` with `next` to move breaks `rule`, given the
/// positions so far.
fn breaks_superko(
    rule: KoRule,
    history: &[(Hash128, Color)],
    stones: Hash128,
    next: Color,
) -> bool {
    match rule {
        KoRule::Simple => false,
        KoRule::Positional => history.iter().any(|&(seen, _)| seen == stones),
        KoRule::Situational => history.contains(&(stones, next)),
    }
}

/// A game in progress.
#[derive(Clone, Debug)]
pub struct Game {
    rules: Rules,
    komi: Komi,
    setup: Setup,
    board: Board,
    to_play: Color,
    ko_ban: Option<Point>,
    captures: Captures,
    passes: u32,
    stones_hash: Hash128,
    /// Stones hash and player to move of every position so far, the start included.
    history: Vec<(Hash128, Color)>,
    undo: Vec<Undo>,
}

impl Game {
    /// A game on an empty board with Black to move.
    pub fn new(size: BoardSize, rules: Rules, komi: Komi) -> Self {
        let board = Board::new(size);
        let stones_hash = zobrist::stones_hash(&board);
        Self {
            rules,
            komi,
            setup: Setup::default(),
            board,
            to_play: Color::Black,
            ko_ban: None,
            captures: Captures::default(),
            passes: 0,
            stones_hash,
            history: vec![(stones_hash, Color::Black)],
            undo: Vec::new(),
        }
    }

    /// A game starting from setup stones. Duplicates within one color are
    /// accepted; every chain must keep a liberty.
    pub fn with_setup(
        size: BoardSize,
        rules: Rules,
        komi: Komi,
        setup: Setup,
    ) -> Result<Self, SetupError> {
        let mut board = Board::new(size);
        for (points, cell) in [(&setup.black, Cell::Black), (&setup.white, Cell::White)] {
            for &point in points {
                match board.get(point) {
                    None => return Err(SetupError::OffBoard(point)),
                    Some(Cell::Empty) => board
                        .set(point, cell)
                        .map_err(|_| SetupError::OffBoard(point))?,
                    Some(existing) if existing == cell => {}
                    Some(_) => return Err(SetupError::Conflict(point)),
                }
            }
        }
        let mut checked = vec![false; size.area()];
        for point in size.points() {
            if checked[point.index()] {
                continue;
            }
            if let Some(chain) = board.chain(point) {
                if chain.liberties.is_empty() {
                    return Err(SetupError::NoLiberties(point));
                }
                for stone in chain.stones {
                    checked[stone.index()] = true;
                }
            }
        }
        let stones_hash = zobrist::stones_hash(&board);
        let to_play = setup.to_play;
        Ok(Self {
            history: vec![(stones_hash, to_play)],
            to_play,
            stones_hash,
            board,
            setup,
            ..Self::new(size, rules, komi)
        })
    }

    /// The rule set.
    pub fn rules(&self) -> Rules {
        self.rules
    }

    /// Komi.
    pub fn komi(&self) -> Komi {
        self.komi
    }

    /// The starting stones and first player.
    pub fn setup(&self) -> &Setup {
        &self.setup
    }

    /// Every chain in the current position; see [`Board::chains`].
    pub fn chains(&self) -> Vec<Chain> {
        self.board.chains()
    }

    /// The current board.
    pub fn board(&self) -> &Board {
        &self.board
    }

    /// The player to move.
    pub fn to_play(&self) -> Color {
        self.to_play
    }

    /// Stones removed so far.
    pub fn captures(&self) -> Captures {
        self.captures
    }

    /// Passes since the last placement.
    pub fn consecutive_passes(&self) -> u32 {
        self.passes
    }

    /// Number of moves played, passes included.
    pub fn move_count(&self) -> usize {
        self.undo.len()
    }

    /// The moves played so far, in order.
    pub fn moves(&self) -> Vec<(Color, Move)> {
        self.undo
            .iter()
            .map(|record| (record.color, record.mv))
            .collect()
    }

    /// Hash of the current stones.
    pub fn stones_hash(&self) -> Hash128 {
        self.stones_hash
    }

    /// A snapshot of the current position.
    pub fn position(&self) -> Position {
        let size = self.board.size();
        Position {
            size,
            cells: self.board.cells().to_vec(),
            to_play: self.to_play,
            ko_ban: self.ko_ban,
            captures: self.captures,
            consecutive_passes: self.passes,
            stones_hash: self.stones_hash,
            situation_hash: zobrist::situation_hash(
                self.stones_hash,
                size,
                self.to_play,
                self.ko_ban,
            ),
        }
    }

    /// Plays `mv` for the player to move, rejecting any rule violation.
    pub fn play(&mut self, mv: Move) -> Result<MoveEffect, IllegalMove> {
        self.play_as(self.to_play, mv, ReplayMode::Strict)
    }

    /// Plays `mv` for `color`. In [`ReplayMode::Strict`] a broken rule is an
    /// error and nothing changes; in [`ReplayMode::Record`] the move is applied
    /// and the broken rules are listed in the effect.
    pub fn play_as(
        &mut self,
        color: Color,
        mv: Move,
        mode: ReplayMode,
    ) -> Result<MoveEffect, IllegalMove> {
        let mut violations = Vec::new();
        // Strict mode stops at the first violation; Record mode collects them.
        let mut note = |violation: RuleViolation| match mode {
            ReplayMode::Strict => Err(IllegalMove::Rule(violation)),
            ReplayMode::Record => {
                violations.push(violation);
                Ok(())
            }
        };
        if color != self.to_play {
            note(RuleViolation::OutOfTurn)?;
        }

        let Move::Play(point) = mv else {
            self.commit(color, mv, Placement::default(), self.stones_hash);
            return Ok(MoveEffect {
                violations,
                ..MoveEffect::default()
            });
        };

        // The ban only binds the player it was created against.
        if self.ko_ban == Some(point) && color == self.to_play {
            note(RuleViolation::Ko)?;
        }
        let placement = match self.board.place(color, point, self.rules.suicide) {
            Ok(placement) => placement,
            Err(IllegalPlacement::OffBoard) => return Err(IllegalMove::OffBoard),
            Err(IllegalPlacement::Occupied) => return Err(IllegalMove::Occupied),
            Err(IllegalPlacement::Suicide) => {
                note(RuleViolation::Suicide)?;
                // Same point, now known to be empty and on the board.
                self.board
                    .place_as_recorded(color, point)
                    .map_err(|_| IllegalMove::Occupied)?
            }
        };

        let size = self.board.size();
        let mut stones = self.stones_hash.0 ^ zobrist::stone_key(size, point, color);
        for &stone in &placement.captured {
            stones ^= zobrist::stone_key(size, stone, color.opponent());
        }
        // The suicided stones include the new one, which cancels its key.
        for &stone in &placement.suicided {
            stones ^= zobrist::stone_key(size, stone, color);
        }
        let stones = Hash128(stones);

        let superko = breaks_superko(self.rules.ko, &self.history, stones, color.opponent());
        if superko && let Err(error) = note(RuleViolation::Superko) {
            self.board.revert(color, point, &placement);
            return Err(error);
        }
        // Only legal moves are flagged: a broken rule is already reported, and
        // a recorded single-stone suicide trivially repeats the last position.
        let repeated_position =
            violations.is_empty() && self.history.iter().any(|&(seen, _)| seen == stones);

        let effect = MoveEffect {
            captured: placement.captured.clone(),
            suicided: placement.suicided.clone(),
            repeated_position,
            violations,
        };
        self.commit(color, mv, placement, stones);
        Ok(effect)
    }

    /// Records an applied move and advances the turn.
    fn commit(&mut self, color: Color, mv: Move, placement: Placement, stones: Hash128) {
        // At most 625 stones per move, so the counts fit in `u32`.
        *self.captures.slot(color.opponent()) += placement.captured.len() as u32;
        *self.captures.slot(color) += placement.suicided.len() as u32;
        let ko_ban = match self.rules.ko {
            KoRule::Simple => placement.ko_point,
            KoRule::Positional | KoRule::Situational => None,
        };
        self.undo.push(Undo {
            color,
            mv,
            placement,
            to_play: self.to_play,
            ko_ban: self.ko_ban,
            passes: self.passes,
            stones_hash: self.stones_hash,
        });
        self.passes = if mv == Move::Pass { self.passes + 1 } else { 0 };
        self.ko_ban = ko_ban;
        self.stones_hash = stones;
        self.to_play = color.opponent();
        self.history.push((stones, self.to_play));
    }

    /// Takes back the last move and returns it, or `None` at the start.
    pub fn undo(&mut self) -> Option<(Color, Move)> {
        let record = self.undo.pop()?;
        if let Move::Play(point) = record.mv {
            self.board.revert(record.color, point, &record.placement);
        }
        *self.captures.slot(record.color.opponent()) -= record.placement.captured.len() as u32;
        *self.captures.slot(record.color) -= record.placement.suicided.len() as u32;
        self.to_play = record.to_play;
        self.ko_ban = record.ko_ban;
        self.passes = record.passes;
        self.stones_hash = record.stones_hash;
        self.history.pop();
        Some((record.color, record.mv))
    }

    /// Plays `moves` from this game and returns every position along the way.
    ///
    /// Consumes the game: the result owns the final state.
    pub fn replay(
        mut self,
        moves: &[(Color, Move)],
        mode: ReplayMode,
    ) -> Result<Replay, ReplayError> {
        let mut positions = Vec::with_capacity(moves.len() + 1);
        positions.push(self.position());
        let mut warnings = Vec::new();
        for (index, &(color, mv)) in moves.iter().enumerate() {
            let move_number = index + 1;
            let effect = self
                .play_as(color, mv, mode)
                .map_err(|error| ReplayError { move_number, error })?;
            let kinds = effect.violations.iter().map(|&v| WarningKind::Violation(v));
            let repeated = effect
                .repeated_position
                .then_some(WarningKind::RepeatedPosition);
            warnings.extend(
                kinds
                    .chain(repeated)
                    .map(|kind| ReplayWarning { move_number, kind }),
            );
            positions.push(self.position());
        }
        Ok(Replay {
            game: self,
            positions,
            warnings,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn superko_rules_differ_only_in_the_player_to_move() {
        let a = Hash128(1);
        let b = Hash128(2);
        let history = [(a, Color::Black), (b, Color::White)];
        // `a` returns with White to move: same stones, other player.
        assert!(!breaks_superko(KoRule::Simple, &history, a, Color::White));
        assert!(breaks_superko(
            KoRule::Positional,
            &history,
            a,
            Color::White
        ));
        assert!(!breaks_superko(
            KoRule::Situational,
            &history,
            a,
            Color::White
        ));
        assert!(breaks_superko(
            KoRule::Situational,
            &history,
            a,
            Color::Black
        ));
        assert!(!breaks_superko(
            KoRule::Positional,
            &history,
            Hash128(3),
            Color::Black
        ));
    }

    #[test]
    fn violation_codes_are_stable() {
        assert_eq!(IllegalMove::Rule(RuleViolation::Ko).code(), "ko_violation");
        assert_eq!(IllegalMove::from(RuleViolation::Suicide).code(), "suicide");
        assert_eq!(IllegalMove::Occupied.code(), "occupied");
        assert_eq!(WarningKind::RepeatedPosition.code(), "repeated_position");
    }
}
