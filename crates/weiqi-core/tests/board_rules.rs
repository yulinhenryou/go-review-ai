//! Board-level rule cases. Sequences marked "prototype" are ported from
//! `legacy/tests/test_game_input.py` (MIGRATION G02); turn order and ko bans
//! belong to the game layer and are tested there.

use weiqi_core::{Board, BoardSize, Cell, Color, IllegalPlacement, Placement, Point, SuicideRule};

const BOTH_RULES: [SuicideRule; 2] = [SuicideRule::Forbidden, SuicideRule::MultiStoneAllowed];

fn point(board: &Board, sgf: &str) -> Point {
    board.size().parse_sgf_point(sgf).unwrap()
}

/// Plays `moves` alternately from Black and returns the last result.
fn play_sequence(
    board: &mut Board,
    moves: &str,
    rule: SuicideRule,
) -> Result<Placement, IllegalPlacement> {
    let mut color = Color::Black;
    let mut last = Ok(Placement::default());
    for sgf in moves.split_whitespace() {
        let p = point(board, sgf);
        last = board.place(color, p, rule);
        color = color.opponent();
    }
    last
}

fn nineteen() -> Board {
    Board::new(BoardSize::square(19).unwrap())
}

#[test]
fn prototype_ko_capture_marks_the_ko_point() {
    for rule in BOTH_RULES {
        let mut board = nineteen();
        let placement = play_sequence(&mut board, "ba bb ab ca bc cc ss db cb", rule).unwrap();
        let bb = point(&board, "bb");
        assert_eq!(placement.captured, [bb]);
        assert_eq!(placement.ko_point, Some(bb));
        assert_eq!(board.get(bb), Some(Cell::Empty));
    }
}

#[test]
fn prototype_single_and_multi_stone_suicide_are_rejected() {
    for moves in ["ba ss ab aa", "ca aa bb ab ac ba"] {
        let mut board = nineteen();
        let result = play_sequence(&mut board, moves, SuicideRule::Forbidden);
        assert_eq!(result, Err(IllegalPlacement::Suicide), "{moves}");
    }
}

#[test]
fn rejected_suicide_leaves_the_board_unchanged() {
    let mut board = nineteen();
    play_sequence(&mut board, "ca aa bb ab ac", SuicideRule::Forbidden).unwrap();
    let before = board.clone();
    let ba = point(&board, "ba");
    assert_eq!(
        board.place(Color::White, ba, SuicideRule::Forbidden),
        Err(IllegalPlacement::Suicide)
    );
    assert_eq!(board, before);
}

#[test]
fn single_stone_suicide_is_illegal_even_when_suicide_is_allowed() {
    let mut board = nineteen();
    let result = play_sequence(&mut board, "ba ss ab aa", SuicideRule::MultiStoneAllowed);
    assert_eq!(result, Err(IllegalPlacement::Suicide));
}

#[test]
fn allowed_multi_stone_suicide_removes_the_own_chain() {
    let mut board = nineteen();
    let placement = play_sequence(
        &mut board,
        "ca aa bb ab ac ba",
        SuicideRule::MultiStoneAllowed,
    )
    .unwrap();
    let mut removed = placement.suicided.clone();
    removed.sort_unstable();
    let mut expected = ["aa", "ab", "ba"].map(|p| point(&board, p));
    expected.sort_unstable();
    assert_eq!(removed, expected);
    assert!(placement.captured.is_empty());
    assert_eq!(board.count(Cell::White), 0);
    assert_eq!(board.count(Cell::Black), 3);
}

#[test]
fn a_one_by_one_board_has_no_legal_placement() {
    let mut board = Board::new(BoardSize::square(1).unwrap());
    let only = board.size().point(0, 0).unwrap();
    for rule in BOTH_RULES {
        assert_eq!(
            board.place(Color::Black, only, rule),
            Err(IllegalPlacement::Suicide)
        );
    }
}

#[test]
fn occupied_and_off_board_points_are_rejected() {
    let mut board = Board::new(BoardSize::square(9).unwrap());
    let centre = board.size().point(4, 4).unwrap();
    board
        .place(Color::Black, centre, SuicideRule::Forbidden)
        .unwrap();
    for color in [Color::Black, Color::White] {
        assert_eq!(
            board.place(color, centre, SuicideRule::Forbidden),
            Err(IllegalPlacement::Occupied)
        );
    }
    // A point from a larger board is not on this one.
    let far = BoardSize::square(19).unwrap().point(18, 18).unwrap();
    assert_eq!(
        board.place(Color::Black, far, SuicideRule::Forbidden),
        Err(IllegalPlacement::OffBoard)
    );
}

#[test]
fn capturing_restores_a_suicide_point_into_a_legal_move() {
    // `cb` has no empty neighbor, but playing there captures White's `bb`
    // first, so it is legal and creates a ko.
    let mut board = Board::from_diagram(
        "
        .XO.
        XO.O
        .XO.
        ....
        ",
    )
    .unwrap();
    let c = point(&board, "cb");
    let placement = board
        .place(Color::Black, c, SuicideRule::Forbidden)
        .unwrap();
    assert_eq!(placement.captured, [point(&board, "bb")]);
    assert_eq!(placement.ko_point, Some(point(&board, "bb")));
}

#[test]
fn one_move_can_capture_several_chains() {
    // Black's three stones are separate chains whose last liberty is `bc`.
    let mut board = Board::from_diagram(
        "
        .O.
        OXO
        X.X
        ",
    )
    .unwrap();
    let placement = board
        .place(Color::White, point(&board, "bc"), SuicideRule::Forbidden)
        .unwrap();
    // Neighbors are visited up, left, right, down.
    assert_eq!(
        placement.captured,
        ["bb", "ac", "cc"].map(|p| point(&board, p))
    );
    assert_eq!(placement.ko_point, None);
    assert_eq!(board.count(Cell::Black), 0);
}

#[test]
fn capturing_one_stone_with_a_connected_stone_is_not_ko() {
    let mut board = Board::from_diagram(
        "
        .XO.
        XO.O
        .XO.
        .X..
        ",
    )
    .unwrap();
    // Make `cc` black so the capturing stone joins a chain.
    board.set(point(&board, "cc"), Cell::Black).unwrap();
    let placement = board
        .place(Color::Black, point(&board, "cb"), SuicideRule::Forbidden)
        .unwrap();
    assert_eq!(placement.captured, [point(&board, "bb")]);
    assert_eq!(placement.ko_point, None);
}

#[test]
fn capturing_one_stone_that_leaves_two_liberties_is_not_ko() {
    let mut board = Board::from_diagram(
        "
        .X..
        XO..
        .X..
        ....
        ",
    )
    .unwrap();
    let placement = board
        .place(Color::Black, point(&board, "cb"), SuicideRule::Forbidden)
        .unwrap();
    assert_eq!(placement.captured, [point(&board, "bb")]);
    assert_eq!(placement.ko_point, None);
}

#[test]
fn chain_reports_stones_and_unique_liberties() {
    let board = Board::from_diagram(
        "
        XX.
        X.O
        ...
        ",
    )
    .unwrap();
    let chain = board.chain(point(&board, "aa")).unwrap();
    assert_eq!(chain.color, Color::Black);
    assert_eq!(chain.stones, ["aa", "ba", "ab"].map(|p| point(&board, p)));
    // `bb` touches two black stones but is one liberty.
    assert_eq!(
        chain.liberties,
        ["ca", "bb", "ac"].map(|p| point(&board, p))
    );
    assert_eq!(board.chain(point(&board, "cc")), None);
}

#[test]
fn chains_partition_the_stones_in_index_order() {
    let board = Board::from_diagram(
        "
        XX.O
        X.OO
        .X..
        O..X
        ",
    )
    .unwrap();
    let chains = board.chains();
    let stones: Vec<Vec<&str>> = vec![
        vec!["aa", "ba", "ab"],
        vec!["da", "cb", "db"],
        vec!["bc"],
        vec!["ad"],
        vec!["dd"],
    ];
    assert_eq!(chains.len(), stones.len());
    for (chain, expected) in chains.iter().zip(&stones) {
        let expected: Vec<Point> = expected.iter().map(|p| point(&board, p)).collect();
        assert_eq!(chain.stones, expected);
        // Each listed chain is exactly what `chain` finds from its first stone.
        assert_eq!(Some(chain), board.chain(chain.stones[0]).as_ref());
    }
    assert_eq!(chains[1].color, Color::White);
    assert!(
        Board::new(BoardSize::square(9).unwrap())
            .chains()
            .is_empty()
    );
}

#[test]
fn rectangular_boards_capture_along_both_edges() {
    let mut board = Board::new(BoardSize::new(5, 2).unwrap());
    let rule = SuicideRule::Forbidden;
    let size = board.size();
    let at = |x, y| size.point(x, y).unwrap();
    board.place(Color::White, at(0, 0), rule).unwrap();
    board.place(Color::White, at(0, 1), rule).unwrap();
    board.place(Color::Black, at(1, 0), rule).unwrap();
    let placement = board.place(Color::Black, at(1, 1), rule).unwrap();
    assert_eq!(placement.captured.len(), 2);
    assert_eq!(board.to_string(), ".X...\n.X...\n");
}
