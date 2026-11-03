//! Go (Weiqi / Baduk) rules core: the single authoritative implementation of
//! board rules, SGF parsing, position hashing and scoring for this project.
//!
//! M0 contains only the board-size bound; the rules engine arrives in M1.

/// Largest board side length the core supports.
///
/// SGF allows up to 52, but KataGo's default build stops at 19 and nothing in
/// the product needs more than 25, so the core keeps its arrays small.
pub const MAX_BOARD_SIZE: u8 = 25;

/// Returns `true` when `size` is a side length the core can represent.
pub fn is_supported_board_size(size: u8) -> bool {
    (1..=MAX_BOARD_SIZE).contains(&size)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn accepts_common_sizes() {
        for size in [9, 13, 19] {
            assert!(is_supported_board_size(size));
        }
    }

    #[test]
    fn rejects_sizes_outside_the_bounds() {
        assert!(!is_supported_board_size(0));
        assert!(is_supported_board_size(MAX_BOARD_SIZE));
        assert!(!is_supported_board_size(MAX_BOARD_SIZE + 1));
    }
}
