//! Stones on a board: chains, liberties, captures and suicide.
//!
//! This layer knows nothing about turns, ko bans or history. It places a stone,
//! resolves captures and reports the simple-ko point the placement creates; the
//! game layer decides which placements are allowed.

use std::fmt;

use crate::coord::{BoardSize, Point};

/// A player's color.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum Color {
    /// Black, who moves first in an even game.
    Black,
    /// White.
    White,
}

impl Color {
    /// The other color.
    pub const fn opponent(self) -> Self {
        match self {
            Self::Black => Self::White,
            Self::White => Self::Black,
        }
    }
}

/// The content of one point.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Hash)]
pub enum Cell {
    /// No stone.
    #[default]
    Empty,
    /// A black stone.
    Black,
    /// A white stone.
    White,
}

impl Cell {
    /// The color of the stone here, if any.
    pub const fn color(self) -> Option<Color> {
        match self {
            Self::Empty => None,
            Self::Black => Some(Color::Black),
            Self::White => Some(Color::White),
        }
    }
}

impl From<Color> for Cell {
    fn from(color: Color) -> Self {
        match color {
            Color::Black => Self::Black,
            Color::White => Self::White,
        }
    }
}

/// Whether a placement may remove its own chain.
///
/// Mirrors KataGo's `multiStoneSuicideLegal`: a lone stone with no liberties is
/// never legal, because it would only remove itself.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum SuicideRule {
    /// Any placement that leaves its own chain without liberties is illegal.
    Forbidden,
    /// A placement may capture its own chain of two or more stones.
    MultiStoneAllowed,
}

/// Why a stone cannot be placed.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, thiserror::Error)]
pub enum IllegalPlacement {
    /// The point does not belong to this board.
    #[error("point is not on the board")]
    OffBoard,
    /// A stone is already there.
    #[error("point is occupied")]
    Occupied,
    /// The stone's own chain would have no liberties.
    #[error("move would be suicide")]
    Suicide,
}

/// What a successful placement changed.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct Placement {
    /// Opponent stones removed, in the order they were found.
    pub captured: Vec<Point>,
    /// Own stones removed by an allowed multi-stone suicide, the new stone included.
    pub suicided: Vec<Point>,
    /// The point where an immediate recapture would repeat the position (simple ko).
    pub ko_point: Option<Point>,
}

/// A connected group of same-colored stones.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Chain {
    /// The chain's color.
    pub color: Color,
    /// Stones in index order.
    pub stones: Vec<Point>,
    /// Empty points adjacent to the chain, in index order.
    pub liberties: Vec<Point>,
}

/// Errors from [`Board::from_diagram`].
#[derive(Clone, Debug, PartialEq, Eq, thiserror::Error)]
pub enum DiagramError {
    /// The rows are empty, ragged or too large.
    #[error("diagram rows are empty, ragged or too large")]
    BadShape,
    /// A character other than `.`, `X` or `O`.
    #[error("unexpected diagram character {0:?}")]
    BadCell(char),
}

/// Up to four orthogonal neighbors of a point.
#[derive(Clone, Copy, Debug)]
struct Adjacent {
    points: [Point; 4],
    len: u8,
}

impl Adjacent {
    fn as_slice(&self) -> &[Point] {
        &self.points[..usize::from(self.len)]
    }
}

/// Neighbor table, computed once per board size.
#[derive(Clone, Debug)]
struct Topology {
    size: BoardSize,
    adjacent: Vec<Adjacent>,
}

impl Topology {
    fn new(size: BoardSize) -> Self {
        let adjacent = size
            .points()
            .map(|point| {
                // Every point is on the board, so `xy` succeeds.
                let (x, y) = size.xy(point).unwrap_or_default();
                let candidates = [
                    y.checked_sub(1).and_then(|y| size.point(x, y)),
                    x.checked_sub(1).and_then(|x| size.point(x, y)),
                    size.point(x + 1, y),
                    size.point(x, y + 1),
                ];
                let mut adjacent = Adjacent {
                    points: [point; 4],
                    len: 0,
                };
                for neighbor in candidates.into_iter().flatten() {
                    adjacent.points[usize::from(adjacent.len)] = neighbor;
                    adjacent.len += 1;
                }
                adjacent
            })
            .collect();
        Self { size, adjacent }
    }

    fn neighbors(&self, point: Point) -> &[Point] {
        self.adjacent[point.index()].as_slice()
    }
}

/// Reusable flood-fill state, so the hot path does not allocate a visited set.
///
/// A point counts as visited when its stamp equals the current generation.
/// Starting a new search only increments the generation; the stamps are
/// cleared only when the counter wraps around.
#[derive(Clone, Debug)]
struct Scratch {
    stamps: Vec<u32>,
    generation: u32,
}

impl Scratch {
    fn new(area: usize) -> Self {
        Self {
            stamps: vec![0; area],
            generation: 0,
        }
    }

    fn begin(&mut self) {
        self.generation = self.generation.wrapping_add(1);
        if self.generation == 0 {
            self.stamps.fill(0);
            self.generation = 1;
        }
    }

    /// Marks `point` as visited; returns `false` if it already was.
    fn visit(&mut self, point: Point) -> bool {
        let stamp = &mut self.stamps[point.index()];
        let fresh = *stamp != self.generation;
        *stamp = self.generation;
        fresh
    }
}

/// Collects the chain containing `start` into `stones` and returns its
/// liberty count.
///
/// A free function rather than a method: it borrows the board's fields
/// separately (topology and cells shared, scratch mutable), which a `&mut self`
/// method could not do while also handing out `&self.topology`.
fn flood_chain(
    topology: &Topology,
    cells: &[Cell],
    scratch: &mut Scratch,
    start: Point,
    stones: &mut Vec<Point>,
) -> usize {
    let color = cells[start.index()];
    stones.clear();
    scratch.begin();
    scratch.visit(start);
    stones.push(start);
    let mut liberties = 0;
    // `stones` doubles as the work queue: everything before `next` is expanded.
    let mut next = 0;
    while let Some(&point) = stones.get(next) {
        next += 1;
        for &neighbor in topology.neighbors(point) {
            let cell = cells[neighbor.index()];
            if cell == color {
                if scratch.visit(neighbor) {
                    stones.push(neighbor);
                }
            } else if cell == Cell::Empty && scratch.visit(neighbor) {
                liberties += 1;
            }
        }
    }
    liberties
}

/// Stones on a rectangular board.
#[derive(Clone, Debug)]
pub struct Board {
    topology: Topology,
    cells: Vec<Cell>,
    scratch: Scratch,
}

impl PartialEq for Board {
    /// Boards are equal when they have the same size and stones; scratch state
    /// is ignored.
    fn eq(&self, other: &Self) -> bool {
        self.size() == other.size() && self.cells == other.cells
    }
}

impl Eq for Board {}

impl Board {
    /// An empty board.
    pub fn new(size: BoardSize) -> Self {
        Self {
            topology: Topology::new(size),
            cells: vec![Cell::Empty; size.area()],
            scratch: Scratch::new(size.area()),
        }
    }

    /// Builds a board from rows of `.` (empty), `X` (black) and `O` (white).
    ///
    /// Blank lines and surrounding whitespace are ignored. Stones are set as
    /// written, without resolving captures. [`Board`]'s `Display` writes this
    /// format.
    pub fn from_diagram(diagram: &str) -> Result<Self, DiagramError> {
        let rows: Vec<&str> = diagram
            .lines()
            .map(str::trim)
            .filter(|r| !r.is_empty())
            .collect();
        let width = rows.first().map_or(0, |row| row.chars().count());
        if rows.iter().any(|row| row.chars().count() != width) {
            return Err(DiagramError::BadShape);
        }
        let size = u8::try_from(width)
            .ok()
            .zip(u8::try_from(rows.len()).ok())
            .and_then(|(w, h)| BoardSize::new(w, h).ok())
            .ok_or(DiagramError::BadShape)?;
        let mut board = Self::new(size);
        for (cell, c) in board
            .cells
            .iter_mut()
            .zip(rows.iter().flat_map(|row| row.chars()))
        {
            *cell = match c {
                '.' => Cell::Empty,
                'X' => Cell::Black,
                'O' => Cell::White,
                other => return Err(DiagramError::BadCell(other)),
            };
        }
        Ok(board)
    }

    /// The board's dimensions.
    pub fn size(&self) -> BoardSize {
        self.topology.size
    }

    /// Every point's content, in index order.
    pub fn cells(&self) -> &[Cell] {
        &self.cells
    }

    /// The content of `point`, or `None` if it is not on this board.
    pub fn get(&self, point: Point) -> Option<Cell> {
        self.cells.get(point.index()).copied()
    }

    /// The orthogonal neighbors of `point` (empty if it is not on this board).
    pub fn neighbors(&self, point: Point) -> &[Point] {
        if self.size().contains(point) {
            self.topology.neighbors(point)
        } else {
            &[]
        }
    }

    /// Number of points holding `cell`.
    pub fn count(&self, cell: Cell) -> usize {
        self.cells.iter().filter(|&&c| c == cell).count()
    }

    /// Sets a point directly, as SGF setup properties (`AB`, `AW`, `AE`) do.
    ///
    /// No captures are resolved, so a setup position may contain chains
    /// without liberties; replay reports those.
    pub fn set(&mut self, point: Point, cell: Cell) -> Result<(), IllegalPlacement> {
        let slot = self
            .cells
            .get_mut(point.index())
            .ok_or(IllegalPlacement::OffBoard)?;
        *slot = cell;
        Ok(())
    }

    /// The chain containing `point`, or `None` if the point is empty or off the board.
    pub fn chain(&self, point: Point) -> Option<Chain> {
        let color = self.get(point)?.color()?;
        // Read-only queries use their own scratch so that `&self` suffices.
        let mut scratch = Scratch::new(self.cells.len());
        let mut stones = Vec::new();
        flood_chain(
            &self.topology,
            &self.cells,
            &mut scratch,
            point,
            &mut stones,
        );
        scratch.begin();
        let mut liberties = Vec::new();
        for &stone in &stones {
            for &neighbor in self.topology.neighbors(stone) {
                if self.cells[neighbor.index()] == Cell::Empty && scratch.visit(neighbor) {
                    liberties.push(neighbor);
                }
            }
        }
        stones.sort_unstable();
        liberties.sort_unstable();
        Some(Chain {
            color,
            stones,
            liberties,
        })
    }

    /// Places a `color` stone on `point` and removes captured chains.
    ///
    /// Opponent chains left without liberties are captured first; only then is
    /// the new stone's own chain checked for suicide. On error the board is
    /// unchanged.
    pub fn place(
        &mut self,
        color: Color,
        point: Point,
        suicide: SuicideRule,
    ) -> Result<Placement, IllegalPlacement> {
        match self.get(point) {
            None => return Err(IllegalPlacement::OffBoard),
            Some(Cell::Empty) => {}
            Some(_) => return Err(IllegalPlacement::Occupied),
        }
        self.cells[point.index()] = color.into();

        let opponent = Cell::from(color.opponent());
        let mut placement = Placement::default();
        let mut chain = Vec::new();
        for &neighbor in self.topology.neighbors(point) {
            // A chain captured through an earlier neighbor is already empty here.
            if self.cells[neighbor.index()] != opponent {
                continue;
            }
            let liberties = flood_chain(
                &self.topology,
                &self.cells,
                &mut self.scratch,
                neighbor,
                &mut chain,
            );
            if liberties == 0 {
                for &stone in &chain {
                    self.cells[stone.index()] = Cell::Empty;
                }
                placement.captured.extend_from_slice(&chain);
            }
        }

        let liberties = flood_chain(
            &self.topology,
            &self.cells,
            &mut self.scratch,
            point,
            &mut chain,
        );
        if liberties == 0 {
            // A capture always frees a liberty, so nothing was captured here
            // and undoing the placement restores the board exactly.
            debug_assert!(placement.captured.is_empty());
            if chain.len() == 1 || suicide == SuicideRule::Forbidden {
                self.cells[point.index()] = Cell::Empty;
                return Err(IllegalPlacement::Suicide);
            }
            for &stone in &chain {
                self.cells[stone.index()] = Cell::Empty;
            }
            placement.suicided = chain;
        } else if liberties == 1 && chain.len() == 1 && placement.captured.len() == 1 {
            // A lone stone took exactly one stone and sits in atari: an
            // immediate recapture would restore the previous position.
            placement.ko_point = placement.captured.first().copied();
        }
        Ok(placement)
    }
}

impl fmt::Display for Board {
    /// Writes the diagram format read by [`Board::from_diagram`].
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        let width = usize::from(self.size().width());
        for row in self.cells.chunks(width) {
            for cell in row {
                f.write_str(match cell {
                    Cell::Empty => ".",
                    Cell::Black => "X",
                    Cell::White => "O",
                })?;
            }
            f.write_str("\n")?;
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn corners_edges_and_centre_have_two_three_and_four_neighbors() {
        let board = Board::new(BoardSize::new(3, 2).unwrap());
        let size = board.size();
        let counts: Vec<usize> = size.points().map(|p| board.neighbors(p).len()).collect();
        assert_eq!(counts, [2, 3, 2, 2, 3, 2]);
        let single = Board::new(BoardSize::square(1).unwrap());
        assert!(single.neighbors(size.point(0, 0).unwrap()).is_empty());
    }

    #[test]
    fn scratch_clears_stamps_when_the_generation_wraps() {
        let mut scratch = Scratch::new(2);
        scratch.generation = u32::MAX - 1;
        scratch.begin();
        assert!(scratch.visit(Point(0)));
        scratch.begin();
        // Generation wrapped to 1 after clearing, so point 0 is unvisited again.
        assert_eq!(scratch.generation, 1);
        assert!(scratch.visit(Point(0)));
        assert!(!scratch.visit(Point(0)));
    }

    #[test]
    fn diagram_round_trips_and_rejects_bad_input() {
        let text = "X.O\n.OX\n";
        let board = Board::from_diagram(text).unwrap();
        assert_eq!(board.to_string(), text);
        assert_eq!(Board::from_diagram("X.\nX"), Err(DiagramError::BadShape));
        assert_eq!(Board::from_diagram(""), Err(DiagramError::BadShape));
        assert_eq!(Board::from_diagram("X#"), Err(DiagramError::BadCell('#')));
    }
}
