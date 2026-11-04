//! Property tests (ROADMAP M1 acceptance 2): invariants that must hold for
//! every random move sequence and every random SGF tree, not just hand-picked
//! cases.

use std::collections::HashSet;

use proptest::prelude::*;
use weiqi_core::sgf::{self, ParseLimits, Property, SgfTree, Value};
use weiqi_core::zobrist;
use weiqi_core::{BoardSize, Cell, Color, Game, KoRule, Komi, Move, Position, ReplayMode, Rules};

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

/// Mostly small boards, where captures, ko and suicide are frequent, plus 19x19.
fn board_size() -> impl Strategy<Value = BoardSize> {
    prop_oneof![
        4 => (1u8..=7, 1u8..=7),
        1 => Just((19, 19)),
    ]
    .prop_map(|(width, height)| BoardSize::new(width, height).unwrap())
}

/// A raw move: the color (used only in record mode) and a number mapped onto
/// the board's points, with one extra value meaning pass.
fn raw_moves() -> impl Strategy<Value = Vec<(bool, u16)>> {
    prop::collection::vec((any::<bool>(), any::<u16>()), 0..300)
}

fn to_move(size: BoardSize, raw: u16) -> Move {
    let area = size.area();
    let index = usize::from(raw) % (area + 1);
    match size.points().nth(index) {
        Some(point) => Move::Play(point),
        None => Move::Pass,
    }
}

/// Plays every raw move that is applicable and checks the per-move invariants.
/// Returns the game and the position before each applied move.
fn play_checked(
    size: BoardSize,
    rules: Rules,
    raw: &[(bool, u16)],
    mode: ReplayMode,
) -> Result<(Game, Vec<Position>), TestCaseError> {
    let mut game = Game::new(size, rules, Komi::new(7.5).unwrap());
    let mut before = Vec::new();
    // Stones placed by each color: [black, white].
    let mut placed = [0usize; 2];
    let mut seen: HashSet<(Vec<Cell>, Option<Color>)> = HashSet::new();
    let superko_key = |position: &Position| match rules.ko {
        KoRule::Simple => None,
        KoRule::Positional => Some((position.cells.clone(), None)),
        KoRule::Situational => Some((position.cells.clone(), Some(position.to_play))),
    };
    let start = game.position();
    seen.extend(superko_key(&start));

    for &(white, value) in raw {
        let color = match mode {
            ReplayMode::Strict => game.to_play(),
            ReplayMode::Record if white => Color::White,
            ReplayMode::Record => Color::Black,
        };
        let mv = to_move(size, value);
        let previous = game.position();
        if game.play_as(color, mv, mode).is_err() {
            // A rejected move changes nothing.
            prop_assert_eq!(game.position(), previous);
            continue;
        }
        let now = game.position();

        // The incrementally updated hash equals one computed from scratch.
        prop_assert_eq!(game.stones_hash(), zobrist::stones_hash(game.board()));

        // Stones on the board = stones placed - stones removed.
        if let Move::Play(_) = mv {
            placed[usize::from(color == Color::White)] += 1;
        }
        let board = game.board();
        prop_assert_eq!(
            board.count(Cell::Black),
            placed[0] - now.captures.black as usize
        );
        prop_assert_eq!(
            board.count(Cell::White),
            placed[1] - now.captures.white as usize
        );

        // Under superko no legal placement recreates an earlier position.
        // This compares the cells themselves, so it does not rely on hashing.
        if let Some(key) = superko_key(&now) {
            let new = seen.insert(key);
            if mode == ReplayMode::Strict && matches!(mv, Move::Play(_)) {
                prop_assert!(new, "superko allowed a repeated position");
            }
        }
        before.push(previous);
    }
    Ok((game, before))
}

proptest! {
    #[test]
    fn strict_play_keeps_invariants_and_undo_restores_every_position(
        size in board_size(),
        rules in prop::sample::select(&PRESETS[..]),
        raw in raw_moves(),
    ) {
        let (mut game, before) = play_checked(size, rules, &raw, ReplayMode::Strict)?;

        // Replaying the applied moves from scratch visits the same positions.
        let replay = Game::new(size, rules, Komi::new(7.5).unwrap())
            .replay(&game.moves(), ReplayMode::Strict)
            .unwrap();
        prop_assert_eq!(&replay.positions[..before.len()], &before[..]);
        prop_assert_eq!(replay.positions.last(), Some(&game.position()));
        prop_assert!(replay.warnings.iter().all(|w| w.kind.code() == "repeated_position"));

        for expected in before.into_iter().rev() {
            prop_assert!(game.undo().is_some());
            prop_assert_eq!(game.position(), expected);
        }
        prop_assert_eq!(game.undo(), None);
    }

    #[test]
    fn record_play_keeps_invariants_and_undo_restores_every_position(
        size in board_size(),
        rules in prop::sample::select(&PRESETS[..]),
        raw in raw_moves(),
    ) {
        let (mut game, before) = play_checked(size, rules, &raw, ReplayMode::Record)?;
        for expected in before.into_iter().rev() {
            prop_assert!(game.undo().is_some());
            prop_assert_eq!(game.position(), expected);
        }
        prop_assert_eq!(game.undo(), None);
    }
}

/// Raw value text built from plain characters and escape pairs, so it is
/// always valid between brackets but covers every escape.
fn raw_value() -> impl Strategy<Value = Value> {
    let piece = prop_oneof![
        any::<char>()
            .prop_filter("needs escaping", |&c| c != ']' && c != '\\')
            .prop_map(String::from),
        any::<char>().prop_map(|c| format!("\\{c}")),
    ];
    prop::collection::vec(piece, 0..6).prop_map(|pieces| Value::from_raw(pieces.concat()).unwrap())
}

fn property() -> impl Strategy<Value = Property> {
    (
        prop::collection::vec(b'A'..=b'Z', 1..=3),
        prop::collection::vec(raw_value(), 1..=3),
    )
        .prop_map(|(ident, values)| {
            Property::new(String::from_utf8(ident).unwrap(), values).unwrap()
        })
}

/// A tree of up to 40 nodes; node `i` hangs under an earlier node picked by
/// the generated number, so every shape (long lines, wide fans) can occur.
fn tree() -> impl Strategy<Value = SgfTree> {
    let node = (any::<usize>(), prop::collection::vec(property(), 0..4));
    (
        prop::collection::vec(property(), 0..4),
        prop::collection::vec(node, 0..40),
    )
        .prop_map(|(root, nodes)| {
            let mut tree = SgfTree::new(root);
            let mut ids = vec![tree.root()];
            for (pick, properties) in nodes {
                let parent = ids[pick % ids.len()];
                ids.push(tree.add_child(parent, properties).unwrap());
            }
            tree
        })
}

/// Bytes drawn mostly from SGF syntax, so random input reaches deep into the
/// parser and extractor instead of failing at the first character.
fn sgf_like_bytes() -> impl Strategy<Value = Vec<u8>> {
    let alphabet = b"();[]\\:ABWSZKMHAPLEtsadpq019 \n\xe6\xa3\x8b".to_vec();
    prop::collection::vec(
        prop_oneof![9 => prop::sample::select(alphabet), 1 => any::<u8>()],
        0..400,
    )
}

/// The writer's output reads back as the same tree with no warnings, and
/// writing that again gives the same text.
fn check_round_trip(tree: &SgfTree) -> Result<(), TestCaseError> {
    let text = tree.to_sgf();
    let parsed = sgf::parse_text(&text, &ParseLimits::default())
        .map_err(|error| TestCaseError::fail(format!("{error} in {text:?}")))?;
    prop_assert!(parsed.warnings.is_empty(), "{:?}", parsed.warnings);
    prop_assert_eq!(parsed.games.len(), 1);
    prop_assert_eq!(&parsed.games[0], tree);
    prop_assert_eq!(parsed.games[0].to_sgf(), text);
    Ok(())
}

proptest! {
    #[test]
    fn parse_of_write_is_the_same_tree(tree in tree()) {
        check_round_trip(&tree)?;
    }

    #[test]
    fn any_input_parses_extracts_and_replays_without_panicking(bytes in sgf_like_bytes()) {
        // Errors are fine; panics are not. Every tree that parses must also
        // survive the writer round trip.
        if let Ok(collection) = sgf::parse(&bytes) {
            for tree in &collection.games {
                check_round_trip(tree)?;
                if let Ok(record) = sgf::extract(tree) {
                    let komi = Komi::new(7.5).unwrap();
                    let _ = record.replay(Rules::chinese(), komi);
                }
            }
        }
    }
}
