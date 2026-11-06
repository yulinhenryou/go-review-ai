//! Board sizes, points and coordinate notations (SGF and GTP).
//!
//! A [`Point`] is an index into a flat board array: `index = y * width + x`,
//! with `(0, 0)` at the top-left corner, the same orientation as SGF. A point
//! only has meaning together with the [`BoardSize`] that produced it.

/// Largest supported width or height.
///
/// SGF allows up to 52, but KataGo's default build stops at 19 and nothing in
/// the product needs more than 25, which is also the number of GTP columns.
pub const MAX_BOARD_SIZE: u8 = 25;

/// GTP column letters: `A`..`Z` without `I`, which gives exactly 25 columns.
const GTP_COLUMNS: &[u8; 25] = b"ABCDEFGHJKLMNOPQRSTUVWXYZ";

/// Board dimensions, `1..=25` in each direction.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub struct BoardSize {
    width: u8,
    height: u8,
}

/// A point on a board, as a flat index.
#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct Point(pub(crate) u16);

/// A move: a stone on a point, or a pass.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum Move {
    /// Place a stone on the point.
    Play(Point),
    /// Pass.
    Pass,
}

/// Errors from board sizes and coordinate parsing.
#[derive(Clone, Debug, PartialEq, Eq, thiserror::Error)]
pub enum CoordError {
    /// Width or height outside `1..=25`.
    #[error("unsupported board size {width}x{height} (each side must be 1..={MAX_BOARD_SIZE})")]
    UnsupportedSize {
        /// Requested width.
        width: u8,
        /// Requested height.
        height: u8,
    },
    /// The text is not a coordinate in the expected notation.
    #[error("malformed coordinate {0:?}")]
    Malformed(String),
    /// The coordinate is well formed but lies outside the board.
    #[error("coordinate {0:?} is outside the board")]
    OutOfRange(String),
}

impl Point {
    /// The flat index of this point.
    pub const fn index(self) -> usize {
        self.0 as usize
    }
}

impl BoardSize {
    /// A `width x height` board.
    pub fn new(width: u8, height: u8) -> Result<Self, CoordError> {
        let valid = 1..=MAX_BOARD_SIZE;
        if valid.contains(&width) && valid.contains(&height) {
            Ok(Self { width, height })
        } else {
            Err(CoordError::UnsupportedSize { width, height })
        }
    }

    /// An `n x n` board.
    pub fn square(n: u8) -> Result<Self, CoordError> {
        Self::new(n, n)
    }

    /// Number of columns.
    pub const fn width(self) -> u8 {
        self.width
    }

    /// Number of rows.
    pub const fn height(self) -> u8 {
        self.height
    }

    /// Number of points on the board.
    pub const fn area(self) -> usize {
        self.width as usize * self.height as usize
    }

    /// Whether `point` is an index on this board.
    pub const fn contains(self, point: Point) -> bool {
        point.index() < self.area()
    }

    /// The point at column `x` and row `y`, counted from the top-left.
    pub fn point(self, x: u8, y: u8) -> Option<Point> {
        (x < self.width && y < self.height)
            .then(|| Point(u16::from(y) * u16::from(self.width) + u16::from(x)))
    }

    /// Column and row of `point`, counted from the top-left.
    pub fn xy(self, point: Point) -> Option<(u8, u8)> {
        if !self.contains(point) {
            return None;
        }
        let width = u16::from(self.width);
        // Both values are below 25 because the point is on the board.
        Some(((point.0 % width) as u8, (point.0 / width) as u8))
    }

    /// Every point on the board in index order.
    pub fn points(self) -> impl Iterator<Item = Point> {
        // `area()` is at most 625, so the cast cannot truncate.
        (0..self.area() as u16).map(Point)
    }

    /// Parses an SGF point such as `"pd"`. Letters are lowercase `a`..`y`.
    ///
    /// Pass (`""` or `"tt"`) is not a point; the SGF layer decides how to read it.
    pub fn parse_sgf_point(self, text: &str) -> Result<Point, CoordError> {
        let &[column, row] = text.as_bytes() else {
            return Err(CoordError::Malformed(text.to_owned()));
        };
        if !column.is_ascii_lowercase() || !row.is_ascii_lowercase() {
            return Err(CoordError::Malformed(text.to_owned()));
        }
        self.point(column - b'a', row - b'a')
            .ok_or_else(|| CoordError::OutOfRange(text.to_owned()))
    }

    /// Formats `point` in SGF notation, or `None` if it is not on this board.
    pub fn to_sgf(self, point: Point) -> Option<String> {
        let (x, y) = self.xy(point)?;
        Some(
            [char::from(b'a' + x), char::from(b'a' + y)]
                .iter()
                .collect(),
        )
    }

    /// Parses a GTP vertex such as `"Q16"` or `"pass"`, ignoring letter case.
    ///
    /// Columns skip `I`; rows count from the bottom, starting at 1.
    pub fn parse_gtp(self, text: &str) -> Result<Move, CoordError> {
        if text.eq_ignore_ascii_case("pass") {
            return Ok(Move::Pass);
        }
        let malformed = || CoordError::Malformed(text.to_owned());
        let (&letter, digits) = text.as_bytes().split_first().ok_or_else(malformed)?;
        let x = GTP_COLUMNS
            .iter()
            .position(|&c| c == letter.to_ascii_uppercase())
            .ok_or_else(malformed)?;
        // Plain decimal digits without a sign or leading zero, at most two of them.
        let well_formed = matches!(digits.len(), 1 | 2)
            && digits.iter().all(u8::is_ascii_digit)
            && digits[0] != b'0';
        if !well_formed {
            return Err(malformed());
        }
        let row = digits.iter().fold(0u8, |acc, d| acc * 10 + (d - b'0'));
        let out_of_range = || CoordError::OutOfRange(text.to_owned());
        if row > self.height {
            return Err(out_of_range());
        }
        // `x` is below 25, so it fits in a `u8`.
        self.point(x as u8, self.height - row)
            .map(Move::Play)
            .ok_or_else(out_of_range)
    }

    /// Formats `mv` as a GTP vertex, or `None` if the point is not on this board.
    pub fn to_gtp(self, mv: Move) -> Option<String> {
        match mv {
            Move::Pass => Some("pass".to_owned()),
            Move::Play(point) => {
                let (x, y) = self.xy(point)?;
                let column = char::from(GTP_COLUMNS[usize::from(x)]);
                Some(format!("{column}{}", self.height - y))
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn nineteen() -> BoardSize {
        BoardSize::square(19).unwrap()
    }

    #[test]
    fn sizes_are_bounded() {
        assert!(BoardSize::square(1).is_ok());
        assert!(BoardSize::new(25, 7).is_ok());
        assert!(BoardSize::square(0).is_err());
        assert!(BoardSize::new(19, 26).is_err());
    }

    #[test]
    fn points_are_row_major_from_the_top_left() {
        let size = BoardSize::new(3, 2).unwrap();
        assert_eq!(size.point(0, 0).map(Point::index), Some(0));
        assert_eq!(size.point(2, 1).map(Point::index), Some(5));
        assert_eq!(size.point(3, 0), None);
        assert_eq!(size.points().count(), 6);
        let last = size.point(2, 1).unwrap();
        assert_eq!(size.xy(last), Some((2, 1)));
        assert_eq!(size.xy(Point(6)), None);
    }

    #[test]
    fn sgf_points_round_trip() {
        let size = nineteen();
        for point in size.points() {
            let text = size.to_sgf(point).unwrap();
            assert_eq!(size.parse_sgf_point(&text), Ok(point));
        }
    }

    #[test]
    fn sgf_points_reject_bad_text() {
        let size = nineteen();
        for text in ["", "a", "abc", "AA", "a1", "\u{e9}a"] {
            assert!(matches!(
                size.parse_sgf_point(text),
                Err(CoordError::Malformed(_))
            ));
        }
        // `tt` is pass in FF[3]; as a point it is off a 19x19 board.
        assert!(matches!(
            size.parse_sgf_point("tt"),
            Err(CoordError::OutOfRange(_))
        ));
    }

    /// Ported from the prototype's `test_coordinate_mapping` (MIGRATION G10).
    #[test]
    fn gtp_matches_the_prototype_mapping() {
        let size = nineteen();
        for (gtp, sgf) in [("A19", "aa"), ("T1", "ss"), ("Q16", "pd")] {
            let point = size.parse_sgf_point(sgf).unwrap();
            assert_eq!(size.parse_gtp(gtp), Ok(Move::Play(point)));
            assert_eq!(size.to_gtp(Move::Play(point)).as_deref(), Some(gtp));
        }
        assert_eq!(size.parse_gtp("pass"), Ok(Move::Pass));
        assert_eq!(size.parse_gtp("PASS"), Ok(Move::Pass));
        assert_eq!(size.to_gtp(Move::Pass).as_deref(), Some("pass"));
    }

    #[test]
    fn gtp_skips_column_i_and_is_case_insensitive() {
        let size = nineteen();
        let h = size.parse_sgf_point("ha").unwrap();
        let j = size.parse_sgf_point("ia").unwrap();
        assert_eq!(size.to_gtp(Move::Play(h)).as_deref(), Some("H19"));
        assert_eq!(size.to_gtp(Move::Play(j)).as_deref(), Some("J19"));
        assert_eq!(size.parse_gtp("j19"), Ok(Move::Play(j)));
        assert!(matches!(
            size.parse_gtp("I19"),
            Err(CoordError::Malformed(_))
        ));
    }

    #[test]
    fn gtp_rejects_bad_vertices() {
        let size = nineteen();
        for text in ["", "A", "A0", "A019", "A+1", "A1 ", "Q160", "?5"] {
            assert!(
                matches!(size.parse_gtp(text), Err(CoordError::Malformed(_))),
                "{text}"
            );
        }
        for text in ["A20", "U1"] {
            assert!(
                matches!(size.parse_gtp(text), Err(CoordError::OutOfRange(_))),
                "{text}"
            );
        }
    }

    #[test]
    fn gtp_rows_count_from_the_bottom_on_rectangular_boards() {
        let size = BoardSize::new(25, 3).unwrap();
        let top_right = size.point(24, 0).unwrap();
        assert_eq!(size.to_gtp(Move::Play(top_right)).as_deref(), Some("Z3"));
        assert_eq!(
            size.parse_gtp("A1"),
            Ok(Move::Play(size.point(0, 2).unwrap()))
        );
    }
}
