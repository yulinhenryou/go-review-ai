//! Go (Weiqi / Baduk) rules core: the single authoritative implementation of
//! board rules, SGF parsing, position hashing and scoring for this project.
//!
//! Layers, from the bottom up:
//!
//! - [`coord`]: board sizes, points, SGF and GTP coordinates.
//! - [`board`]: stones, chains, captures and suicide, without turns or history.

pub mod board;
pub mod coord;

pub use board::{Board, Cell, Chain, Color, IllegalPlacement, Placement, SuicideRule};
pub use coord::{BoardSize, CoordError, MAX_BOARD_SIZE, Move, Point};
