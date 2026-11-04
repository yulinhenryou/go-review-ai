//! Deterministic 128-bit Zobrist hashing.
//!
//! Every `(x, y, color)` on a 25x25 grid, the side to move, every simple-ko
//! point, and every width and height gets a random key. A position's hash is
//! the XOR of the keys that apply to it. XOR is its own inverse, so adding or
//! removing a stone updates a hash with one XOR.
//!
//! Keys are indexed by `(x, y)` rather than by flat point index, because the
//! same index names different intersections on boards of different widths.
//! They are generated at compile time by SplitMix64 from [`SEED`], in this
//! order: for each grid cell `y * 25 + x`, the black then the white key; the
//! white-to-move key; one ko key per grid cell; one key per width `1..=25`;
//! one key per height `1..=25`. Each key takes two outputs, high half first.
//! Changing any of this changes every stored hash, so it requires a new
//! [`ZOBRIST_VERSION`] and a data migration.

use std::fmt;

use crate::board::{Board, Color};
use crate::coord::{BoardSize, MAX_BOARD_SIZE, Point};

/// Version of the key generation scheme; stored next to every persisted hash.
pub const ZOBRIST_VERSION: u32 = 1;

/// SplitMix64 seed: the ASCII bytes of `weiqi-z1`.
pub const SEED: u64 = 0x7765_6971_692d_7a31;

const SIDE: usize = MAX_BOARD_SIZE as usize;
const GRID: usize = SIDE * SIDE;

/// A 128-bit position hash. Formatted as 32 lowercase hex digits, which is
/// also how it crosses into JavaScript, whose numbers cannot hold it.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct Hash128(pub u128);

impl Hash128 {
    /// The hash as 32 lowercase hex digits.
    pub fn to_hex(self) -> String {
        format!("{:032x}", self.0)
    }

    /// Parses 32 hex digits, as written by [`Hash128::to_hex`].
    pub fn from_hex(text: &str) -> Option<Self> {
        if text.len() != 32 || !text.bytes().all(|b| b.is_ascii_hexdigit()) {
            return None;
        }
        u128::from_str_radix(text, 16).ok().map(Self)
    }
}

impl fmt::Display for Hash128 {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{:032x}", self.0)
    }
}

/// One step of SplitMix64 (Steele, Lea and Flood, 2014).
const fn splitmix64(state: &mut u64) -> u64 {
    *state = state.wrapping_add(0x9e37_79b9_7f4a_7c15);
    let mut z = *state;
    z = (z ^ (z >> 30)).wrapping_mul(0xbf58_476d_1ce4_e5b9);
    z = (z ^ (z >> 27)).wrapping_mul(0x94d0_49bb_1331_11eb);
    z ^ (z >> 31)
}

const fn next_key(state: &mut u64) -> u128 {
    let high = splitmix64(state) as u128;
    let low = splitmix64(state) as u128;
    (high << 64) | low
}

struct Keys {
    stones: [[u128; 2]; GRID],
    white_to_move: u128,
    ko: [u128; GRID],
    width: [u128; SIDE],
    height: [u128; SIDE],
}

impl Keys {
    const fn generate(seed: u64) -> Self {
        let mut state = seed;
        let mut keys = Self {
            stones: [[0; 2]; GRID],
            white_to_move: 0,
            ko: [0; GRID],
            width: [0; SIDE],
            height: [0; SIDE],
        };
        // `for` loops are not allowed in `const fn`, hence `while`.
        let mut i = 0;
        while i < GRID {
            keys.stones[i][0] = next_key(&mut state);
            keys.stones[i][1] = next_key(&mut state);
            i += 1;
        }
        keys.white_to_move = next_key(&mut state);
        i = 0;
        while i < GRID {
            keys.ko[i] = next_key(&mut state);
            i += 1;
        }
        i = 0;
        while i < SIDE {
            keys.width[i] = next_key(&mut state);
            i += 1;
        }
        i = 0;
        while i < SIDE {
            keys.height[i] = next_key(&mut state);
            i += 1;
        }
        keys
    }
}

/// Computed by the compiler; at run time this is read-only data.
static KEYS: Keys = Keys::generate(SEED);

fn grid_index(size: BoardSize, point: Point) -> usize {
    // Callers pass points on the board; off-board points fall back to cell 0
    // rather than panic, and never occur in practice.
    let (x, y) = size.xy(point).unwrap_or_default();
    usize::from(y) * SIDE + usize::from(x)
}

/// Key for a `color` stone on `point`.
pub(crate) fn stone_key(size: BoardSize, point: Point, color: Color) -> u128 {
    let side = match color {
        Color::Black => 0,
        Color::White => 1,
    };
    KEYS.stones[grid_index(size, point)][side]
}

/// Key XORed in when White is to move.
pub(crate) fn white_to_move_key() -> u128 {
    KEYS.white_to_move
}

/// Key for a simple-ko ban on `point`.
pub(crate) fn ko_key(size: BoardSize, point: Point) -> u128 {
    KEYS.ko[grid_index(size, point)]
}

/// Key for the board dimensions; the hash of an empty board.
pub(crate) fn size_key(size: BoardSize) -> u128 {
    KEYS.width[usize::from(size.width()) - 1] ^ KEYS.height[usize::from(size.height()) - 1]
}

/// The stones hash of `board`, computed from scratch.
pub fn stones_hash(board: &Board) -> Hash128 {
    let size = board.size();
    let hash = size
        .points()
        .zip(board.cells())
        .fold(size_key(size), |hash, (point, &cell)| match cell.color() {
            Some(color) => hash ^ stone_key(size, point, color),
            None => hash,
        });
    Hash128(hash)
}

/// The situation hash: stones plus side to move plus simple-ko ban.
pub fn situation_hash(
    stones: Hash128,
    size: BoardSize,
    to_play: Color,
    ko_ban: Option<Point>,
) -> Hash128 {
    let mut hash = stones.0;
    if to_play == Color::White {
        hash ^= white_to_move_key();
    }
    if let Some(point) = ko_ban {
        hash ^= ko_key(size, point);
    }
    Hash128(hash)
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Reference outputs of SplitMix64 seeded with 0 (Vigna's `splitmix64.c`).
    #[test]
    fn splitmix64_matches_the_reference_sequence() {
        let mut state = 0;
        assert_eq!(splitmix64(&mut state), 0xe220_a839_7b1d_cdaf);
        assert_eq!(splitmix64(&mut state), 0x6e78_9e6a_a1b9_65f4);
        assert_eq!(splitmix64(&mut state), 0x06c4_5d18_8009_454f);
    }

    #[test]
    fn keys_follow_the_documented_order() {
        let mut state = SEED;
        assert_eq!(KEYS.stones[0][0], next_key(&mut state));
        assert_eq!(KEYS.stones[0][1], next_key(&mut state));
        let mut state = SEED;
        for _ in 0..GRID * 2 {
            next_key(&mut state);
        }
        assert_eq!(KEYS.white_to_move, next_key(&mut state));
    }

    #[test]
    fn keys_are_distinct() {
        let mut all: Vec<u128> = KEYS.stones.iter().flatten().copied().collect();
        all.push(KEYS.white_to_move);
        all.extend(KEYS.ko);
        all.extend(KEYS.width);
        all.extend(KEYS.height);
        let count = all.len();
        all.sort_unstable();
        all.dedup();
        assert_eq!(all.len(), count);
    }

    #[test]
    fn same_intersection_has_the_same_key_on_every_board_size() {
        let small = BoardSize::square(9).unwrap();
        let large = BoardSize::square(19).unwrap();
        let a = small.point(3, 2).unwrap();
        let b = large.point(3, 2).unwrap();
        assert_ne!(a.index(), b.index());
        assert_eq!(
            stone_key(small, a, Color::Black),
            stone_key(large, b, Color::Black)
        );
        assert_ne!(
            stones_hash(&Board::new(small)),
            stones_hash(&Board::new(large))
        );
    }

    #[test]
    fn hex_round_trips() {
        let hash = Hash128(0x0123_4567_89ab_cdef_0011_2233_4455_6677);
        let text = hash.to_hex();
        assert_eq!(text, "0123456789abcdef0011223344556677");
        assert_eq!(hash.to_string(), text);
        assert_eq!(Hash128::from_hex(&text), Some(hash));
        assert_eq!(Hash128::from_hex("+123456789abcdef0011223344556677"), None);
        assert_eq!(Hash128::from_hex("abc"), None);
    }
}
