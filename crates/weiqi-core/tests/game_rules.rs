//! Game-level rule cases. Tests named `prototype_*` are ported from
//! `legacy/tests/test_game_input.py` (MIGRATION G02).

use weiqi_core::zobrist;
use weiqi_core::{
    BoardSize, Cell, Color, Game, IllegalMove, Komi, Move, Point, ReplayError, ReplayMode,
    ReplayWarning, RuleViolation, Rules, Setup, SetupError, WarningKind,
};

/// The prototype's ko sequence; Black's last move `cb` takes the stone on `bb`.
const KO_MOVES: &str = "ba bb ab ca bc cc ss db cb";

fn size19() -> BoardSize {
    BoardSize::square(19).unwrap()
}

fn game(rules: Rules) -> Game {
    Game::new(size19(), rules, Komi::new(6.5).unwrap())
}

fn point(sgf: &str) -> Point {
    size19().parse_sgf_point(sgf).unwrap()
}

/// Alternating moves from Black; `-` is a pass.
fn moves(text: &str) -> Vec<(Color, Move)> {
    let mut color = Color::Black;
    text.split_whitespace()
        .map(|token| {
            let mv = if token == "-" {
                Move::Pass
            } else {
                Move::Play(point(token))
            };
            let entry = (color, mv);
            color = color.opponent();
            entry
        })
        .collect()
}

fn cell(game: &Game, sgf: &str) -> Cell {
    game.board().get(point(sgf)).unwrap()
}

fn warning(move_number: usize, kind: WarningKind) -> ReplayWarning {
    ReplayWarning { move_number, kind }
}

#[test]
fn prototype_positions_follow_captures_and_passes() {
    for rules in [Rules::japanese(), Rules::chinese()] {
        let replay = game(rules)
            .replay(&moves("ba aa ab - ss"), ReplayMode::Strict)
            .unwrap();
        let positions = &replay.positions;
        assert_eq!(positions.len(), 6);
        // Move 3 captures White's `aa`; the pass at move 4 changes no stones.
        assert_eq!(positions[3].cells[point("aa").index()], Cell::Empty);
        assert_eq!(positions[3].cells, positions[4].cells);
        assert_eq!(positions[5].to_play, Color::White);
        assert!(replay.warnings.is_empty());
    }
}

#[test]
fn prototype_simple_ko_and_legal_recapture_after_intervening_moves() {
    for rules in [Rules::japanese(), Rules::chinese()] {
        let error = game(rules)
            .replay(&moves(&format!("{KO_MOVES} bb")), ReplayMode::Strict)
            .unwrap_err();
        assert_eq!(
            error,
            ReplayError {
                move_number: 10,
                error: RuleViolation::Ko.into()
            }
        );
        assert_eq!(error.error.code(), "ko_violation");

        let replay = game(rules)
            .replay(&moves(&format!("{KO_MOVES} rr qq bb")), ReplayMode::Strict)
            .unwrap();
        assert_eq!(cell(&replay.game, "bb"), Cell::White);
        assert_eq!(cell(&replay.game, "cb"), Cell::Empty);
    }
}

#[test]
fn ko_capture_sets_the_ban_and_the_situation_hash() {
    let mut game = game(Rules::japanese());
    for (_, mv) in moves(KO_MOVES) {
        game.play(mv).unwrap();
    }
    let position = game.position();
    assert_eq!(position.ko_ban, Some(point("bb")));
    let without_ban =
        zobrist::situation_hash(position.stones_hash, position.size, position.to_play, None);
    assert_ne!(position.situation_hash, without_ban);
    // A pass lifts the ban.
    game.play(Move::Pass).unwrap();
    assert_eq!(game.position().ko_ban, None);
}

#[test]
fn immediate_ko_recapture_is_superko_under_superko_rules() {
    for rules in [
        Rules::chinese_superko(),
        Rules::aga(),
        Rules::tromp_taylor(),
    ] {
        let error = game(rules)
            .replay(&moves(&format!("{KO_MOVES} bb")), ReplayMode::Strict)
            .unwrap_err();
        assert_eq!(
            error,
            ReplayError {
                move_number: 10,
                error: RuleViolation::Superko.into()
            }
        );
    }
}

#[test]
fn recapture_after_two_passes_repeats_the_position() {
    let sequence = moves(&format!("{KO_MOVES} - - bb"));
    // Simple ko: legal, because passes lift the ban, but the arrangement before
    // move 9 returns, which a long game would record as a cycle.
    let replay = game(Rules::japanese())
        .replay(&sequence, ReplayMode::Strict)
        .unwrap();
    assert_eq!(
        replay.warnings,
        [warning(12, WarningKind::RepeatedPosition)]
    );
    assert_eq!(
        replay.positions[12].stones_hash,
        replay.positions[8].stones_hash
    );

    // Superko rules forbid it; the same arrangement had Black to move.
    for rules in [Rules::chinese_superko(), Rules::aga()] {
        let error = game(rules)
            .replay(&sequence, ReplayMode::Strict)
            .unwrap_err();
        assert_eq!(error.move_number, 12);
        assert_eq!(error.error, RuleViolation::Superko.into());
    }
}

/// The prototype rejected any move after two passes; the core now only counts
/// passes and leaves that policy to the product layer.
#[test]
fn prototype_two_passes_do_not_end_the_game_in_the_core() {
    let mut game = game(Rules::japanese());
    let replay = game
        .clone()
        .replay(&moves("aa - -"), ReplayMode::Strict)
        .unwrap();
    assert_eq!(replay.positions[3].cells, replay.positions[1].cells);
    assert_eq!(replay.positions[3].to_play, Color::White);
    assert_eq!(replay.game.consecutive_passes(), 2);

    for (_, mv) in moves("aa - - bb") {
        game.play(mv).unwrap();
    }
    assert_eq!(game.consecutive_passes(), 0);
}

#[test]
fn undo_restores_every_earlier_position() {
    let mut game = game(Rules::japanese());
    let mut seen = vec![game.position()];
    for (_, mv) in moves(&format!("{KO_MOVES} - - bb")) {
        game.play(mv).unwrap();
        seen.push(game.position());
    }
    while let Some(expected) = seen.pop() {
        assert_eq!(game.position(), expected);
        let undone = game.undo();
        assert_eq!(undone.is_some(), !seen.is_empty());
    }
    assert_eq!(game.move_count(), 0);
}

#[test]
fn incremental_hash_matches_the_recomputed_hash() {
    let sequences = [
        (Rules::japanese(), format!("{KO_MOVES} - - bb")),
        // Multi-stone suicide at move 6 under Tromp-Taylor.
        (Rules::tromp_taylor(), "ca aa bb ab ac ba".to_owned()),
    ];
    for (rules, text) in sequences {
        let mut game = game(rules);
        for (_, mv) in moves(&text) {
            game.play(mv).unwrap();
            assert_eq!(game.stones_hash(), zobrist::stones_hash(game.board()));
        }
    }
}

#[test]
fn record_mode_applies_violations_and_reports_them() {
    // Two black moves in a row.
    let out_of_turn = [
        (Color::Black, Move::Play(point("aa"))),
        (Color::Black, Move::Play(point("bb"))),
    ];
    let error = game(Rules::japanese())
        .replay(&out_of_turn, ReplayMode::Strict)
        .unwrap_err();
    assert_eq!(error.error, RuleViolation::OutOfTurn.into());
    let replay = game(Rules::japanese())
        .replay(&out_of_turn, ReplayMode::Record)
        .unwrap();
    assert_eq!(
        replay.warnings,
        [warning(2, WarningKind::Violation(RuleViolation::OutOfTurn))]
    );
    assert_eq!(replay.game.to_play(), Color::White);

    // Ko recapture applied as recorded.
    let replay = game(Rules::japanese())
        .replay(&moves(&format!("{KO_MOVES} bb")), ReplayMode::Record)
        .unwrap();
    assert_eq!(
        replay.warnings,
        [warning(10, WarningKind::Violation(RuleViolation::Ko))]
    );
    assert_eq!(cell(&replay.game, "bb"), Cell::White);
    assert_eq!(cell(&replay.game, "cb"), Cell::Empty);

    // Single-stone suicide applied as recorded removes the stone.
    let replay = game(Rules::japanese())
        .replay(&moves("ba ss ab aa"), ReplayMode::Record)
        .unwrap();
    assert_eq!(
        replay.warnings,
        [warning(4, WarningKind::Violation(RuleViolation::Suicide))]
    );
    assert_eq!(cell(&replay.game, "aa"), Cell::Empty);
    assert_eq!(replay.game.position().captures.white, 1);
}

#[test]
fn occupied_points_fail_in_both_modes() {
    for mode in [ReplayMode::Strict, ReplayMode::Record] {
        let error = game(Rules::chinese())
            .replay(&moves("aa aa"), mode)
            .unwrap_err();
        assert_eq!(
            error,
            ReplayError {
                move_number: 2,
                error: IllegalMove::Occupied
            }
        );
    }
}

#[test]
fn strict_errors_leave_the_game_unchanged() {
    let mut game = game(Rules::chinese_superko());
    for (_, mv) in moves(KO_MOVES) {
        game.play(mv).unwrap();
    }
    let before = game.position();
    assert_eq!(
        game.play(Move::Play(point("bb"))),
        Err(RuleViolation::Superko.into())
    );
    assert_eq!(game.position(), before);
    assert_eq!(game.move_count(), 9);
}

#[test]
fn setup_stones_form_the_starting_position() {
    let komi = Komi::new(0.5).unwrap();
    let setup = Setup {
        black: vec![point("pd"), point("dp"), point("pd")],
        white: vec![],
        to_play: Color::White,
    };
    let game = Game::with_setup(size19(), Rules::chinese(), komi, setup).unwrap();
    assert_eq!(game.to_play(), Color::White);
    assert_eq!(game.board().count(Cell::Black), 2);
    assert_eq!(game.stones_hash(), zobrist::stones_hash(game.board()));
    assert_eq!(game.move_count(), 0);

    let conflict = Setup {
        black: vec![point("aa")],
        white: vec![point("aa")],
        ..Setup::default()
    };
    assert_eq!(
        Game::with_setup(size19(), Rules::chinese(), komi, conflict).unwrap_err(),
        SetupError::Conflict(point("aa"))
    );

    let nine = BoardSize::square(9).unwrap();
    let off_board = Setup {
        black: vec![point("ss")],
        ..Setup::default()
    };
    assert_eq!(
        Game::with_setup(nine, Rules::chinese(), komi, off_board).unwrap_err(),
        SetupError::OffBoard(point("ss"))
    );

    let one = BoardSize::square(1).unwrap();
    let full = Setup {
        black: vec![one.point(0, 0).unwrap()],
        ..Setup::default()
    };
    assert!(matches!(
        Game::with_setup(one, Rules::chinese(), komi, full),
        Err(SetupError::NoLiberties(_))
    ));
}

/// Pins the published hash values. If this fails, the key scheme changed:
/// bump `ZOBRIST_VERSION` and plan a migration of stored hashes.
#[test]
fn hash_values_are_pinned() {
    let mut game = game(Rules::chinese());
    let empty = game.position();
    game.play(Move::Play(point("pd"))).unwrap();
    let after = game.position();
    assert_eq!(weiqi_core::ZOBRIST_VERSION, 1);
    let pinned = [
        empty.stones_hash.to_hex(),
        empty.situation_hash.to_hex(),
        after.stones_hash.to_hex(),
        after.situation_hash.to_hex(),
    ];
    assert_eq!(pinned, PINNED);
}

/// Empty 19x19 board (stones, situation), then after Black `pd` (stones, situation).
const PINNED: [&str; 4] = [
    "b1f9f9b3a299fccd959395b699c7053c",
    "b1f9f9b3a299fccd959395b699c7053c",
    "62c6ccfbe409c4f860fddbea1761847b",
    "983a2fe36a8429440c9db88974f2da51",
];
