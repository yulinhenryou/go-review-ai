//! Area and territory scoring of a final position, and SGF `RE` results.
//!
//! Dead stones and seki cannot be decided by the rules alone, so the caller
//! marks them ([`LifeAndDeath`]) and the scorer only counts. Dead stones count
//! as empty. Each empty region belongs to the one color whose live stones
//! border it, or to nobody when both or neither do. Under [`TaxRule::Seki`] a
//! region that borders a chain in seki belongs to nobody.
//!
//! - Area: live stones plus territory.
//! - Territory: territory plus prisoners, where prisoners are the opponent's
//!   captured stones plus the opponent's dead stones.
//!
//! White then adds komi and the handicap bonus, and the button adds half a
//! point to whoever took it, as in KataGo's `BoardHistory::endAndScoreGameNow`.

use std::cmp::Ordering;
use std::fmt;

use crate::board::{Board, Color};
use crate::coord::{Move, Point};
use crate::game::{Captures, Game, Setup};
use crate::rules::{Komi, Rules, ScoringRule, TaxRule, WhiteHandicapBonus};

/// Chains marked by the caller. Any stone of a chain marks the whole chain.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct LifeAndDeath {
    /// Stones of dead chains.
    pub dead: Vec<Point>,
    /// Stones of chains in seki.
    pub seki: Vec<Point>,
}

/// Everything besides the board that the count depends on.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Terms {
    /// The rule set.
    pub rules: Rules,
    /// Komi, added to White.
    pub komi: Komi,
    /// Handicap stones. 0 and 1 both mean no handicap, as in KataGo.
    pub handicap: u32,
    /// Who took the button; only read under rules with [`Rules::button`].
    pub button: Option<Color>,
}

/// One player's count.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Hash)]
pub struct Tally {
    /// Live stones on the board, seki included.
    pub stones: u32,
    /// Points in regions this player owns, points of dead stones included.
    pub territory: u32,
    /// Opponent stones captured during the game or marked dead.
    pub prisoners: u32,
}

/// The count of a position.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Score {
    /// Which parts of a [`Tally`] count.
    pub scoring: ScoringRule,
    /// Black's count.
    pub black: Tally,
    /// White's count.
    pub white: Tally,
    /// Points in regions nobody owns (dame, and seki eyes under
    /// [`TaxRule::Seki`]), points of dead stones included.
    pub neutral: u32,
    /// Komi, added to White.
    pub komi: Komi,
    /// Points added to White for the handicap.
    pub handicap_bonus: u32,
    /// Who receives half a point for the button.
    pub button: Option<Color>,
    /// Every dead stone, in index order.
    pub dead: Vec<Point>,
    /// Every stone in seki, in index order.
    pub seki: Vec<Point>,
    /// For every point in index order: the owner of the region it lies in, or
    /// `None` for live stones and neutral points.
    pub owners: Vec<Option<Color>>,
}

/// Marks or rules the scorer cannot use.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, thiserror::Error)]
pub enum ScoreError {
    /// A marked point is not on the board.
    #[error("marked point {0:?} is not on the board")]
    OffBoard(Point),
    /// A marked point has no stone.
    #[error("marked point {0:?} has no stone")]
    EmptyMark(Point),
    /// A chain is marked both dead and in seki.
    #[error("chain at {0:?} is marked both dead and in seki")]
    ConflictingMarks(Point),
    /// The tax rule cannot be computed from explicit marks.
    #[error("tax rule {0:?} is not supported")]
    UnsupportedTax(TaxRule),
}

impl ScoreError {
    /// Stable machine-readable code.
    pub fn code(&self) -> &'static str {
        match self {
            Self::OffBoard(_) => "off_board",
            Self::EmptyMark(_) => "empty_mark",
            Self::ConflictingMarks(_) => "conflicting_marks",
            Self::UnsupportedTax(_) => "unsupported_rule",
        }
    }
}

#[derive(Clone, Copy, PartialEq, Eq)]
enum Status {
    Alive,
    Dead,
    Seki,
}

const fn side(color: Color) -> usize {
    match color {
        Color::Black => 0,
        Color::White => 1,
    }
}

/// Counts `board` with the given marks and terms. `captures` are the stones
/// removed during the game.
pub fn score(
    board: &Board,
    captures: Captures,
    marks: &LifeAndDeath,
    terms: &Terms,
) -> Result<Score, ScoreError> {
    if terms.rules.tax == TaxRule::All {
        // KataGo taxes two points per "independent life region", found by its
        // own pass-alive analysis; explicit marks do not define those regions.
        return Err(ScoreError::UnsupportedTax(TaxRule::All));
    }
    let size = board.size();
    let mut status = vec![Status::Alive; size.area()];
    mark(board, &marks.dead, Status::Dead, &mut status)?;
    mark(board, &marks.seki, Status::Seki, &mut status)?;

    let mut tallies = [Tally::default(); 2];
    let mut neutral = 0;
    let mut owners = vec![None; size.area()];
    let mut visited = vec![false; size.area()];
    let mut region = Vec::new();
    for start in size.points() {
        if visited[start.index()] || live_color(board, &status, start).is_some() {
            continue;
        }
        // Breadth-first fill over empty and dead points; `region` doubles as
        // the queue, as in `Board`'s chain fill.
        region.clear();
        region.push(start);
        visited[start.index()] = true;
        let mut borders = [false; 2];
        let mut borders_seki = false;
        let mut next = 0;
        while let Some(&point) = region.get(next) {
            next += 1;
            for &neighbor in board.neighbors(point) {
                if let Some(color) = live_color(board, &status, neighbor) {
                    borders[side(color)] = true;
                    borders_seki |= status[neighbor.index()] == Status::Seki;
                } else if !visited[neighbor.index()] {
                    visited[neighbor.index()] = true;
                    region.push(neighbor);
                }
            }
        }
        let owner = match borders {
            [true, false] => Some(Color::Black),
            [false, true] => Some(Color::White),
            _ => None,
        }
        .filter(|_| !(terms.rules.tax == TaxRule::Seki && borders_seki));
        // A board has at most 625 points, so the count fits.
        let count = region.len() as u32;
        match owner {
            Some(color) => tallies[side(color)].territory += count,
            None => neutral += count,
        }
        for point in &region {
            owners[point.index()] = owner;
        }
    }

    let mut dead = Vec::new();
    let mut seki = Vec::new();
    for (point, cell) in size.points().zip(board.cells()) {
        let Some(color) = cell.color() else {
            continue;
        };
        match status[point.index()] {
            Status::Dead => {
                dead.push(point);
                tallies[side(color.opponent())].prisoners += 1;
            }
            Status::Seki => {
                seki.push(point);
                tallies[side(color)].stones += 1;
            }
            Status::Alive => tallies[side(color)].stones += 1,
        }
    }
    tallies[side(Color::Black)].prisoners += captures.white;
    tallies[side(Color::White)].prisoners += captures.black;

    let [black, white] = tallies;
    Ok(Score {
        scoring: terms.rules.scoring,
        black,
        white,
        neutral,
        komi: terms.komi,
        handicap_bonus: handicap_bonus(terms.rules.white_handicap_bonus, terms.handicap),
        button: terms.button.filter(|_| terms.rules.button),
        dead,
        seki,
        owners,
    })
}

/// Sets every stone of each marked chain to `marked`.
fn mark(
    board: &Board,
    points: &[Point],
    marked: Status,
    status: &mut [Status],
) -> Result<(), ScoreError> {
    for &point in points {
        if board.get(point).is_none() {
            return Err(ScoreError::OffBoard(point));
        }
        let chain = board.chain(point).ok_or(ScoreError::EmptyMark(point))?;
        for stone in chain.stones {
            let slot = &mut status[stone.index()];
            if *slot != Status::Alive && *slot != marked {
                return Err(ScoreError::ConflictingMarks(point));
            }
            *slot = marked;
        }
    }
    Ok(())
}

/// The color of a stone on `point` that is not marked dead.
fn live_color(board: &Board, status: &[Status], point: Point) -> Option<Color> {
    board
        .get(point)?
        .color()
        .filter(|_| status[point.index()] != Status::Dead)
}

/// KataGo's `computeWhiteHandicapBonus`.
fn handicap_bonus(rule: WhiteHandicapBonus, handicap: u32) -> u32 {
    let stones = if handicap > 1 { handicap } else { 0 };
    match rule {
        WhiteHandicapBonus::Zero => 0,
        WhiteHandicapBonus::N => stones,
        WhiteHandicapBonus::NMinusOne => stones.saturating_sub(1),
    }
}

impl Score {
    /// One player's count.
    pub fn tally(&self, color: Color) -> Tally {
        match color {
            Color::Black => self.black,
            Color::White => self.white,
        }
    }

    /// Points from the board under the scoring rule, before komi, handicap
    /// bonus and button.
    pub fn board_points(&self, color: Color) -> u32 {
        let tally = self.tally(color);
        match self.scoring {
            ScoringRule::Area => tally.stones + tally.territory,
            ScoringRule::Territory => tally.territory + tally.prisoners,
        }
    }

    /// The final total in half points, exact.
    pub fn total_half_points(&self, color: Color) -> i32 {
        // Every count is bounded by the 625 points of a board, so the casts fit.
        let mut total = 2 * self.board_points(color) as i32;
        if color == Color::White {
            total += i32::from(self.komi.half_points()) + 2 * self.handicap_bonus as i32;
        }
        if self.button == Some(color) {
            total += 1;
        }
        total
    }

    /// The final total in points.
    pub fn total(&self, color: Color) -> f64 {
        f64::from(self.total_half_points(color)) / 2.0
    }

    /// The winner and margin.
    pub fn result(&self) -> GameResult {
        let margin = self.total_half_points(Color::Black) - self.total_half_points(Color::White);
        let winner = match margin.cmp(&0) {
            Ordering::Greater => Color::Black,
            Ordering::Less => Color::White,
            Ordering::Equal => return GameResult::Draw,
        };
        GameResult::Points {
            winner,
            half_points: margin.unsigned_abs(),
        }
    }
}

impl Game {
    /// The scoring terms of this game. The handicap is the number of distinct
    /// black setup stones when there are no white ones, as in KataGo; opening
    /// black moves are not counted (KataGo counts them only under its
    /// `assumeMultipleStartingBlackMovesAreHandicap` option). The button goes
    /// to the player who passed first.
    pub fn terms(&self) -> Terms {
        let rules = self.rules();
        let button = if rules.button {
            self.moves()
                .into_iter()
                .find(|&(_, mv)| mv == Move::Pass)
                .map(|(color, _)| color)
        } else {
            None
        };
        Terms {
            rules,
            komi: self.komi(),
            handicap: setup_handicap(self.setup()),
            button,
        }
    }

    /// Counts the current position with this game's terms. Scoring does not
    /// require the game to be over.
    pub fn score(&self, marks: &LifeAndDeath) -> Result<Score, ScoreError> {
        score(self.board(), self.captures(), marks, &self.terms())
    }
}

fn setup_handicap(setup: &Setup) -> u32 {
    if !setup.white.is_empty() {
        return 0;
    }
    let mut black = setup.black.clone();
    black.sort_unstable();
    black.dedup();
    // Setup points are on the board, so at most 625.
    let stones = black.len() as u32;
    if stones > 1 { stones } else { 0 }
}

/// A game result in SGF `RE` form (FF\[4\]).
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum GameResult {
    /// Won on the count by a margin in half points, at least 1.
    Points {
        /// The winner.
        winner: Color,
        /// The margin in half points.
        half_points: u32,
    },
    /// Jigo, written `0`.
    Draw,
    /// Won by resignation, written `B+R`.
    Resign(Color),
    /// Won on time, written `B+T`.
    Time(Color),
    /// Won by forfeit, written `B+F`.
    Forfeit(Color),
    /// Won without a recorded reason, written `B+`.
    Win(Color),
    /// No result, written `Void`.
    Void,
    /// Unknown result, written `?`.
    Unknown,
}

/// An `RE` value that is not in SGF form.
#[derive(Clone, Debug, PartialEq, Eq, thiserror::Error)]
#[error("malformed game result {0:?}")]
pub struct MalformedResult(pub String);

impl MalformedResult {
    /// Stable machine-readable code.
    pub fn code(&self) -> &'static str {
        "malformed_result"
    }
}

impl GameResult {
    /// Parses an SGF `RE` value. Accepts `Draw` for `0` and the long reason
    /// words (`B+Resign`, `W+Time`, `B+Forfeit`), all case-insensitively.
    pub fn parse_sgf(text: &str) -> Result<Self, MalformedResult> {
        let malformed = || MalformedResult(text.to_owned());
        let trimmed = text.trim();
        match trimmed.to_ascii_lowercase().as_str() {
            "0" | "draw" => return Ok(Self::Draw),
            "void" => return Ok(Self::Void),
            "?" => return Ok(Self::Unknown),
            _ => {}
        }
        let (who, reason) = trimmed.split_once('+').ok_or_else(malformed)?;
        let winner = match who {
            "B" | "b" => Color::Black,
            "W" | "w" => Color::White,
            _ => return Err(malformed()),
        };
        let result = match reason.to_ascii_lowercase().as_str() {
            "" => Self::Win(winner),
            "r" | "resign" => Self::Resign(winner),
            "t" | "time" => Self::Time(winner),
            "f" | "forfeit" => Self::Forfeit(winner),
            margin => Self::Points {
                winner,
                half_points: parse_margin(margin).ok_or_else(malformed)?,
            },
        };
        Ok(result)
    }

    /// The canonical SGF `RE` value.
    pub fn to_sgf(self) -> String {
        self.to_string()
    }
}

/// A positive margin such as `12`, `12.0` or `12.5`, in half points.
fn parse_margin(text: &str) -> Option<u32> {
    let (whole, half) = match text.split_once('.') {
        None => (text, 0),
        Some((whole, "0")) => (whole, 0),
        Some((whole, "5")) => (whole, 1),
        Some(_) => return None,
    };
    if whole.is_empty() || !whole.bytes().all(|b| b.is_ascii_digit()) {
        return None;
    }
    let points: u32 = whole.parse().ok()?;
    let half_points = points.checked_mul(2)?.checked_add(half)?;
    (half_points > 0).then_some(half_points)
}

impl fmt::Display for GameResult {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        let letter = |color: Color| match color {
            Color::Black => 'B',
            Color::White => 'W',
        };
        match *self {
            Self::Points {
                winner,
                half_points,
            } => {
                write!(f, "{}+{}", letter(winner), half_points / 2)?;
                if half_points % 2 == 1 {
                    f.write_str(".5")?;
                }
                Ok(())
            }
            Self::Draw => f.write_str("0"),
            Self::Resign(winner) => write!(f, "{}+R", letter(winner)),
            Self::Time(winner) => write!(f, "{}+T", letter(winner)),
            Self::Forfeit(winner) => write!(f, "{}+F", letter(winner)),
            Self::Win(winner) => write!(f, "{}+", letter(winner)),
            Self::Void => f.write_str("Void"),
            Self::Unknown => f.write_str("?"),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn handicap_bonus_follows_katago() {
        for handicap in [0, 1] {
            assert_eq!(handicap_bonus(WhiteHandicapBonus::N, handicap), 0);
            assert_eq!(handicap_bonus(WhiteHandicapBonus::NMinusOne, handicap), 0);
        }
        assert_eq!(handicap_bonus(WhiteHandicapBonus::N, 4), 4);
        assert_eq!(handicap_bonus(WhiteHandicapBonus::NMinusOne, 4), 3);
        assert_eq!(handicap_bonus(WhiteHandicapBonus::NMinusOne, 2), 1);
        assert_eq!(handicap_bonus(WhiteHandicapBonus::Zero, 9), 0);
    }

    #[test]
    fn margins_parse_in_half_points() {
        assert_eq!(parse_margin("12"), Some(24));
        assert_eq!(parse_margin("12.0"), Some(24));
        assert_eq!(parse_margin("0.5"), Some(1));
        for bad in ["0", "0.0", "", ".5", "1.25", "1.", "-3", "+3", "1e3", "x"] {
            assert_eq!(parse_margin(bad), None, "{bad}");
        }
    }
}
