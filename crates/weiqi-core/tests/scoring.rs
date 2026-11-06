//! Scoring of hand-checked final positions. Every expected count is worked
//! out in the comment above it.

use weiqi_core::{
    Board, BoardSize, Captures, Color, Game, GameResult, Komi, LifeAndDeath, Move, Point, Rules,
    ScoreError, Setup, Tally, Terms, score,
};

fn board(diagram: &str) -> Board {
    Board::from_diagram(diagram).unwrap()
}

fn at(board: &Board, x: u8, y: u8) -> Point {
    board.size().point(x, y).unwrap()
}

fn terms(rules: Rules, komi: f64) -> Terms {
    Terms {
        rules,
        komi: Komi::new(komi).unwrap(),
        handicap: 0,
        button: None,
    }
}

fn tally(stones: u32, territory: u32, prisoners: u32) -> Tally {
    Tally {
        stones,
        territory,
        prisoners,
    }
}

const WALLS: &str = "
    .XO..
    .XO..
    .XO..
    .XO..
    .XO..
";

#[test]
fn area_and_territory_on_a_settled_board() {
    let board = board(WALLS);
    let captures = Captures { black: 2, white: 1 };

    // Area: Black 5 stones + 5 = 10; White 5 stones + 10 + 7.5 = 22.5.
    let area = score(
        &board,
        captures,
        &LifeAndDeath::default(),
        &terms(Rules::chinese(), 7.5),
    )
    .unwrap();
    assert_eq!(area.black, tally(5, 5, 1));
    assert_eq!(area.white, tally(5, 10, 2));
    assert_eq!(area.neutral, 0);
    assert_eq!(area.total(Color::Black), 10.0);
    assert_eq!(area.total(Color::White), 22.5);
    assert_eq!(area.result().to_sgf(), "W+12.5");

    // Territory: Black 5 + 1 prisoner = 6; White 10 + 2 prisoners + 6.5 = 18.5.
    let territory = score(
        &board,
        captures,
        &LifeAndDeath::default(),
        &terms(Rules::japanese(), 6.5),
    )
    .unwrap();
    assert_eq!(territory.total(Color::Black), 6.0);
    assert_eq!(territory.total(Color::White), 18.5);
    assert_eq!(territory.result().to_sgf(), "W+12.5");
    assert_eq!(
        territory.owners[at(&board, 0, 0).index()],
        Some(Color::Black)
    );
    assert_eq!(territory.owners[at(&board, 1, 0).index()], None);
}

const INVADER: &str = "
    .XO..
    .XO.X
    .XO.X
    .XO..
    .XO..
";

#[test]
fn dead_stones_become_territory_and_prisoners() {
    let board = board(INVADER);
    // One stone marks the whole two-stone chain.
    let marks = LifeAndDeath {
        dead: vec![at(&board, 4, 1)],
        seki: vec![],
    };

    // Area: Black 5 + 5 = 10; White 5 + 10 (dead points included) + 7.5 = 22.5.
    let area = score(
        &board,
        Captures::default(),
        &marks,
        &terms(Rules::chinese(), 7.5),
    )
    .unwrap();
    assert_eq!(area.dead, [at(&board, 4, 1), at(&board, 4, 2)]);
    assert_eq!(area.black, tally(5, 5, 0));
    assert_eq!(area.white, tally(5, 10, 2));
    assert_eq!(area.owners[at(&board, 4, 2).index()], Some(Color::White));
    assert_eq!(area.result().to_sgf(), "W+12.5");

    // Territory: Black 5; White 10 + 2 dead prisoners + 6.5 = 18.5.
    let territory = score(
        &board,
        Captures::default(),
        &marks,
        &terms(Rules::japanese(), 6.5),
    )
    .unwrap();
    assert_eq!(territory.result().to_sgf(), "W+13.5");
}

#[test]
fn unmarked_dead_stones_count_as_alive() {
    let board = board(INVADER);
    // The 8 empty points on the right touch both colors and become neutral.
    // Area: Black 7 stones + 5 = 12; White 5 + 0 + 7.5 = 12.5.
    let area = score(
        &board,
        Captures::default(),
        &LifeAndDeath::default(),
        &terms(Rules::chinese(), 7.5),
    )
    .unwrap();
    assert_eq!(area.neutral, 8);
    assert_eq!(area.black, tally(7, 5, 0));
    assert_eq!(area.white, tally(5, 0, 0));
    assert_eq!(area.result().to_sgf(), "W+0.5");
}

/// A seki with one eye each and one shared liberty. Whoever fills `(2, 0)`
/// leaves their own chain with one liberty and is captured through their eye;
/// neither eye can be entered, since the stone would have no liberty and
/// capture nothing.
const SEKI: &str = "
    .X.O.
    XXOOO
";

#[test]
fn seki_eyes_count_under_area_but_not_under_territory() {
    let board = board(SEKI);
    let marks = LifeAndDeath {
        dead: vec![],
        seki: vec![at(&board, 1, 0), at(&board, 3, 0)],
    };

    // Area, no tax: Black 3 stones + eye = 4; White 4 stones + eye = 5.
    let area = score(
        &board,
        Captures::default(),
        &marks,
        &terms(Rules::chinese(), 0.0),
    )
    .unwrap();
    assert_eq!(area.seki.len(), 7);
    assert_eq!(area.black, tally(3, 1, 0));
    assert_eq!(area.white, tally(4, 1, 0));
    assert_eq!(area.neutral, 1);
    assert_eq!(
        area.result(),
        GameResult::Points {
            winner: Color::White,
            half_points: 2
        }
    );

    // Territory with the seki tax: both eyes and the dame are neutral.
    let territory = score(
        &board,
        Captures::default(),
        &marks,
        &terms(Rules::japanese(), 0.0),
    )
    .unwrap();
    assert_eq!(territory.black, tally(3, 0, 0));
    assert_eq!(territory.white, tally(4, 0, 0));
    assert_eq!(territory.neutral, 3);
    assert_eq!(territory.owners[at(&board, 0, 0).index()], None);
    assert_eq!(territory.result(), GameResult::Draw);
    assert_eq!(territory.result().to_sgf(), "0");

    // Without the seki mark, each eye would count as one point of territory.
    let unmarked = score(
        &board,
        Captures::default(),
        &LifeAndDeath::default(),
        &terms(Rules::japanese(), 0.0),
    )
    .unwrap();
    assert_eq!(unmarked.black.territory, 1);
    assert_eq!(unmarked.white.territory, 1);
}

#[test]
fn game_score_uses_its_captures() {
    let size = BoardSize::square(5).unwrap();
    let point = |x, y| Move::Play(size.point(x, y).unwrap());
    let moves = [
        point(1, 0),
        point(0, 0),
        point(0, 1), // Captures White's (0, 0).
        point(4, 4),
        Move::Pass,
        Move::Pass,
    ];
    let marks = LifeAndDeath {
        dead: vec![size.point(4, 4).unwrap()],
        seki: vec![],
    };
    for (rules, komi, expected) in [
        // Territory: 22 empty + 1 dead point = 23, + 1 captured + 1 dead = 25.
        (Rules::japanese(), 6.5, "B+18.5"),
        // Area: 2 stones + 23 = 25.
        (Rules::chinese(), 7.5, "B+17.5"),
    ] {
        let mut game = Game::new(size, rules, Komi::new(komi).unwrap());
        for mv in moves {
            game.play(mv).unwrap();
        }
        let score = game.score(&marks).unwrap();
        assert_eq!(score.black.prisoners, 2);
        assert_eq!(score.black.territory, 23);
        assert_eq!(score.result().to_sgf(), expected);
    }
}

#[test]
fn handicap_bonus_depends_on_the_rules() {
    let size = BoardSize::square(5).unwrap();
    let komi = Komi::new(0.5).unwrap();
    let handicap = Setup {
        black: vec![size.point(1, 1).unwrap(), size.point(3, 3).unwrap()],
        white: vec![],
        to_play: Color::White,
    };
    // Area: Black 2 stones + 23 = 25; territory: Black 23.
    // White: 0.5 komi + bonus.
    for (rules, bonus, expected) in [
        (Rules::chinese(), 2, "B+22.5"),
        (Rules::aga(), 1, "B+23.5"),
        (Rules::japanese(), 0, "B+22.5"),
    ] {
        let game = Game::with_setup(size, rules, komi, handicap.clone()).unwrap();
        assert_eq!(game.terms().handicap, 2);
        let score = game.score(&LifeAndDeath::default()).unwrap();
        assert_eq!(score.handicap_bonus, bonus);
        assert_eq!(score.result().to_sgf(), expected);
    }

    // White setup stones make it a non-handicap game, as in KataGo.
    let mixed = Setup {
        white: vec![size.point(2, 2).unwrap()],
        ..handicap
    };
    let game = Game::with_setup(size, Rules::chinese(), komi, mixed).unwrap();
    assert_eq!(game.terms().handicap, 0);
}

#[test]
fn button_goes_to_the_first_player_to_pass() {
    let size = BoardSize::square(5).unwrap();
    let moves = [
        Move::Play(size.point(2, 2).unwrap()),
        Move::Pass,
        Move::Pass,
    ];
    // Black: 1 stone + 24 = 25. White: 0.5 komi, + 0.5 for the button.
    for (rules, button, expected) in [
        (Rules::aga_button(), Some(Color::White), "B+24"),
        (Rules::aga(), None, "B+24.5"),
    ] {
        let mut game = Game::new(size, rules, Komi::new(0.5).unwrap());
        for mv in moves {
            game.play(mv).unwrap();
        }
        let score = game.score(&LifeAndDeath::default()).unwrap();
        assert_eq!(score.button, button);
        assert_eq!(score.result().to_sgf(), expected);
    }
}

#[test]
fn invalid_marks_and_rules_are_errors() {
    let board = board(SEKI);
    let chinese = terms(Rules::chinese(), 7.5);
    let check = |marks: LifeAndDeath, terms: &Terms| {
        score(&board, Captures::default(), &marks, terms).unwrap_err()
    };

    let empty = at(&board, 0, 0);
    let error = check(
        LifeAndDeath {
            dead: vec![empty],
            seki: vec![],
        },
        &chinese,
    );
    assert_eq!(error, ScoreError::EmptyMark(empty));
    assert_eq!(error.code(), "empty_mark");

    // Two stones of the same chain, one marked dead and one in seki.
    let error = check(
        LifeAndDeath {
            dead: vec![at(&board, 1, 0)],
            seki: vec![at(&board, 0, 1)],
        },
        &chinese,
    );
    assert_eq!(error, ScoreError::ConflictingMarks(at(&board, 0, 1)));
    assert_eq!(error.code(), "conflicting_marks");

    let far = BoardSize::square(19).unwrap().point(18, 18).unwrap();
    let error = check(
        LifeAndDeath {
            dead: vec![far],
            seki: vec![],
        },
        &chinese,
    );
    assert_eq!(error.code(), "off_board");

    let error = check(LifeAndDeath::default(), &terms(Rules::stone_scoring(), 0.0));
    assert_eq!(error.code(), "unsupported_rule");
}

#[test]
fn sgf_results_round_trip() {
    for text in ["B+0.5", "W+12", "B+R", "W+T", "B+F", "W+", "0", "Void", "?"] {
        let result = GameResult::parse_sgf(text).unwrap();
        assert_eq!(result.to_sgf(), text);
    }
    let lenient = [
        ("B+Resign", "B+R"),
        ("w+time", "W+T"),
        ("Draw", "0"),
        (" W+7.0 ", "W+7"),
        ("B+Forfeit", "B+F"),
    ];
    for (text, canonical) in lenient {
        assert_eq!(GameResult::parse_sgf(text).unwrap().to_sgf(), canonical);
    }
    for bad in ["", "B", "B+0", "X+3", "B+3.25", "W+-2", "黑中盘胜"] {
        let error = GameResult::parse_sgf(bad).unwrap_err();
        assert_eq!(error.code(), "malformed_result", "{bad}");
    }
}
