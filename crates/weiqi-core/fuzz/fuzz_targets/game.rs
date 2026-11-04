//! Arbitrary move sequences on arbitrary boards: the incremental hash always
//! equals the recomputed one, rejected moves change nothing, and undoing every
//! move restores each earlier position.

#![no_main]

use libfuzzer_sys::fuzz_target;
use weiqi_core::zobrist;
use weiqi_core::{BoardSize, Color, Game, Komi, Move, ReplayMode, Rules};

const PRESETS: [Rules; 9] = [
    Rules::japanese(),
    Rules::korean(),
    Rules::chinese(),
    Rules::chinese_superko(),
    Rules::aga(),
    Rules::aga_button(),
    Rules::new_zealand(),
    Rules::tromp_taylor(),
    Rules::stone_scoring(),
];

fuzz_target!(|bytes: &[u8]| {
    // Header: width, height, rules and mode; then two bytes per move.
    let [width, height, rules, moves @ ..] = bytes else {
        return;
    };
    let size = BoardSize::new(1 + width % 25, 1 + height % 25).unwrap();
    let preset = PRESETS[usize::from(rules % 16) % PRESETS.len()];
    let mode = if rules & 0x80 == 0 {
        ReplayMode::Strict
    } else {
        ReplayMode::Record
    };

    let mut game = Game::new(size, preset, Komi::new(7.5).unwrap());
    let mut before = Vec::new();
    let (pairs, _) = moves.as_chunks::<2>();
    for &pair in pairs {
        let value = u16::from_le_bytes(pair);
        // The top bit picks the color in record mode; the rest picks a point
        // or, one past the last point, a pass.
        let color = match mode {
            ReplayMode::Strict => game.to_play(),
            ReplayMode::Record if value & 0x8000 != 0 => Color::White,
            ReplayMode::Record => Color::Black,
        };
        let index = usize::from(value & 0x7fff) % (size.area() + 1);
        let mv = size.points().nth(index).map_or(Move::Pass, Move::Play);

        let previous = game.position();
        if game.play_as(color, mv, mode).is_err() {
            assert_eq!(game.position(), previous);
            continue;
        }
        assert_eq!(game.stones_hash(), zobrist::stones_hash(game.board()));
        before.push(previous);
    }
    for expected in before.into_iter().rev() {
        assert!(game.undo().is_some());
        assert_eq!(game.position(), expected);
    }
    assert_eq!(game.undo(), None);
});
