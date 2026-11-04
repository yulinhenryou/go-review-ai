//! Go (Weiqi / Baduk) rules core: the single authoritative implementation of
//! board rules, SGF parsing, position hashing and scoring for this project.
//!
//! Layers, from the bottom up:
//!
//! - [`coord`]: board sizes, points, SGF and GTP coordinates.
//! - [`board`]: stones, chains, captures and suicide, without turns or history.
//! - [`rules`]: KataGo-compatible rule sets and komi.
//! - [`zobrist`]: deterministic 128-bit position hashes.
//! - [`game`]: turns, ko and superko, setup stones, undo and replay.
//! - [`scoring`]: area and territory counts with explicit dead stones and
//!   seki, and SGF `RE` results.

pub mod board;
pub mod coord;
pub mod game;
pub mod rules;
pub mod scoring;
pub mod zobrist;

pub use board::{Board, Cell, Chain, Color, IllegalPlacement, Placement, SuicideRule};
pub use coord::{BoardSize, CoordError, MAX_BOARD_SIZE, Move, Point};
pub use game::{
    Captures, Game, IllegalMove, MoveEffect, Position, Replay, ReplayError, ReplayMode,
    ReplayWarning, RuleViolation, Setup, SetupError, WarningKind,
};
pub use rules::{InvalidKomi, KoRule, Komi, Rules, ScoringRule, TaxRule, WhiteHandicapBonus};
pub use scoring::{
    GameResult, LifeAndDeath, MalformedResult, Score, ScoreError, Tally, Terms, score,
};
pub use zobrist::{Hash128, ZOBRIST_VERSION};
