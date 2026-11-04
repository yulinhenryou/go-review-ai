//! Game extraction from SGF trees. Tests named `prototype_*` port
//! `legacy/tests/test_game_input.py` and `legacy/tests/test_sgf_parser.py`
//! (MIGRATION G02, G08); where the expected outcome changed, the test says so.

use weiqi_core::sgf::{self, ExtractError, GameRecord, extract};
use weiqi_core::{
    BoardSize, Color, Game, GameResult, Komi, Move, ReplayError, ReplayMode, ReplayWarning,
    RuleViolation, Rules, WarningKind,
};

fn record(text: &str) -> Result<GameRecord, ExtractError> {
    extract(&sgf::parse(text.as_bytes()).unwrap().games[0])
}

fn codes(record: &GameRecord) -> Vec<&'static str> {
    record.warnings.iter().map(|w| w.code()).collect()
}

fn point(size: BoardSize, sgf: &str) -> Move {
    Move::Play(size.parse_sgf_point(sgf).unwrap())
}

const FULL: &str = "(;FF[4]GM[1]SZ[19]";

#[test]
fn prototype_sgf_and_manual_inputs_give_identical_positions() {
    let points = ["pd", "dp", "pp", "dd", "fc", "cf"];
    let size = BoardSize::square(19).unwrap();
    for (name, rules) in [
        ("Japanese", Rules::japanese()),
        ("Chinese", Rules::chinese()),
    ] {
        let colors = [Color::Black, Color::White].into_iter().cycle();
        let body: String = colors
            .clone()
            .zip(points)
            .map(|(color, p)| format!(";{}[{p}]", if color == Color::Black { 'B' } else { 'W' }))
            .collect();
        let record = record(&format!("{FULL}RU[{name}]KM[6.5]{body})")).unwrap();
        assert!(record.warnings.is_empty(), "{:?}", record.warnings);
        assert_eq!(record.rules, Some(rules));
        let komi = record.komi.unwrap();
        let from_sgf = record.replay(rules, komi).unwrap();

        let manual: Vec<(Color, Move)> = colors
            .zip(points)
            .map(|(c, p)| (c, point(size, p)))
            .collect();
        assert_eq!(record.moves, manual);
        let from_manual = Game::new(size, rules, komi)
            .replay(&manual, ReplayMode::Strict)
            .unwrap();
        assert_eq!(from_sgf.positions, from_manual.positions);
    }
}

#[test]
fn prototype_metadata_and_main_line_moves() {
    let record = record(
        "(;FF[4]GM[1]SZ[19]RU[Japanese]KM[6.5]PB[Black]PW[White]RE[W+R]DT[2026-01-02]\
         ;B[pd];W[dd];B[];W[tt])",
    )
    .unwrap();
    let size = record.size;
    assert_eq!(record.info.black_player.as_deref(), Some("Black"));
    assert_eq!(record.info.white_player.as_deref(), Some("White"));
    assert_eq!(record.info.result, Some(GameResult::Resign(Color::White)));
    assert_eq!(record.info.date.as_deref(), Some("2026-01-02"));
    assert_eq!(
        record.moves,
        [
            (Color::Black, point(size, "pd")),
            (Color::White, point(size, "dd")),
            (Color::Black, Move::Pass),
            (Color::White, Move::Pass),
        ]
    );
    assert_eq!(codes(&record), ["tt_pass"]);
    assert_eq!(record.warnings[0].node, Some(4));
}

#[test]
fn prototype_missing_metadata_stays_missing() {
    let record = record("(;SZ[19];B[aa])").unwrap();
    assert_eq!(record.rules, None);
    assert_eq!(record.komi, None);
    assert_eq!(
        codes(&record),
        ["missing_gm", "missing_ff", "missing_rules", "missing_komi"]
    );
    // Confirmed values are passed to replay; nothing is filled in silently.
    let replay = record
        .replay(Rules::chinese(), Komi::new(7.5).unwrap())
        .unwrap();
    assert_eq!(replay.positions.len(), 2);
}

#[test]
fn prototype_first_variation_only_has_an_explicit_warning() {
    let record = record(&format!("{FULL}RU[Japanese]KM[6.5];B[aa](;W[bb])(;W[cc]))")).unwrap();
    assert_eq!(
        record.moves.last(),
        Some(&(Color::White, point(record.size, "bb")))
    );
    assert_eq!(codes(&record), ["first_variation_only"]);
}

/// Inputs the prototype rejected that are still errors.
#[test]
fn prototype_contradictions_are_errors() {
    let cases = [
        ("(;SZ[19];B[aa][bb])", "multi_valued_property", 1),
        ("(;SZ[19];B[aa]B[bb])", "duplicate_property", 1),
        ("(;SZ[19];B[aa]W[bb])", "two_moves_in_node", 1),
        ("(;SZ[19]KM[6.5]KM[7.5];B[aa])", "duplicate_property", 0),
        ("(;SZ[19];B[AA])", "malformed_value", 1),
        ("(;SZ[19];B[\u{e9}a])", "malformed_value", 1),
        ("(;SZ[19];B[aaa])", "malformed_value", 1),
        ("(;SZ[19];B[aa];AW[bb])", "setup_after_moves", 2),
        ("(;SZ[19];B[aa];AE[aa])", "setup_after_moves", 2),
        ("(;SZ[19]GM[2];B[aa])", "not_go", 0),
    ];
    for (text, code, node) in cases {
        let error = record(text).unwrap_err();
        assert_eq!((error.code(), error.node), (code, node), "{text}");
    }
    // An occupied point is caught by replay, in both replay modes.
    let record = record("(;SZ[19];B[aa];W[aa])").unwrap();
    let error = record
        .replay(Rules::chinese(), Komi::new(7.5).unwrap())
        .unwrap_err();
    assert_eq!(error.code(), "occupied");
}

/// Inputs the prototype rejected that are now supported (changed
/// expectations, listed in the M1 PR).
#[test]
fn prototype_unsupported_inputs_are_now_read() {
    let size19 = BoardSize::square(19).unwrap();
    let komi = Komi::new(7.5).unwrap();

    let record_of = |text: &str| record(text).unwrap();
    assert_eq!(
        record_of("(;SZ[13];B[aa])").size,
        BoardSize::square(13).unwrap()
    );
    assert_eq!(record_of("(;SZ[19:19];B[aa])").size, size19);
    assert_eq!(
        record_of("(;SZ[19]RU[AGA];B[aa])").rules,
        Some(Rules::aga())
    );
    for text in [
        "(;SZ[19]FF[3];B[aa])",
        "(;SZ[19]CA[GBK];B[aa])",
        "(;SZ[19];B[aa]KO[])",
    ] {
        assert_eq!(record_of(text).moves.len(), 1, "{text}");
    }
    assert!(record_of("(;SZ[19])").moves.is_empty());

    let tt = record_of("(;SZ[19];B[tt])");
    assert_eq!(tt.moves, [(Color::Black, Move::Pass)]);
    assert!(codes(&tt).contains(&"tt_pass"));

    let handicap = record_of("(;SZ[19]AB[aa];W[bb])");
    assert_eq!(
        handicap.setup.black,
        [size19.parse_sgf_point("aa").unwrap()]
    );
    assert_eq!(handicap.setup.to_play, Color::White);
    assert!(
        handicap
            .replay(Rules::chinese(), komi)
            .unwrap()
            .warnings
            .is_empty()
    );

    assert_eq!(
        record_of("(;SZ[19]PL[W];W[bb])").setup.to_play,
        Color::White
    );
    let white_first = record_of("(;SZ[19];W[aa])");
    assert!(
        white_first
            .replay(Rules::chinese(), komi)
            .unwrap()
            .warnings
            .is_empty()
    );

    let declared = record_of("(;SZ[19]HA[2];B[aa])");
    assert_eq!(declared.handicap, Some(2));
    assert!(codes(&declared).contains(&"handicap_mismatch"));

    let late = record_of("(;SZ[19];B[aa];KM[7.5]W[bb])");
    assert_eq!(late.komi, Some(komi));
    let warning = late
        .warnings
        .iter()
        .find(|w| w.code() == "game_info_outside_root");
    assert_eq!(warning.and_then(|w| w.node), Some(2));

    // Two black moves in a row: replayed as recorded, with a warning.
    let replay = record_of("(;SZ[19];B[aa];B[bb])")
        .replay(Rules::chinese(), komi)
        .unwrap();
    assert_eq!(
        replay.warnings,
        [ReplayWarning {
            move_number: 2,
            kind: WarningKind::Violation(RuleViolation::OutOfTurn)
        }]
    );
}

/// Invalid komi no longer rejects the file; komi must then be confirmed.
#[test]
fn prototype_invalid_komi_must_be_confirmed() {
    for km in ["NaN", "Infinity", "0.25", "151"] {
        let record = record(&format!("(;SZ[19]KM[{km}];B[aa])")).unwrap();
        assert_eq!(record.komi, None, "{km}");
        assert!(codes(&record).contains(&"invalid_komi"), "{km}");
    }
}

#[test]
fn compressed_point_lists_and_setup_replacement() {
    let record = record(&format!("{FULL}AB[aa:cb][ee]AW[ss];AE[ss]AW[ba])")).unwrap();
    let size = record.size;
    let points = |list: &[&str]| -> Vec<_> {
        list.iter()
            .map(|p| size.parse_sgf_point(p).unwrap())
            .collect()
    };
    // `aa:cb` is the rectangle of columns a..c and rows a..b; `ba` moves to White.
    assert_eq!(
        record.setup.black,
        points(&["aa", "ca", "ab", "bb", "cb", "ee"])
    );
    assert_eq!(record.setup.white, points(&["ba"]));
}

#[test]
fn other_contradictions_have_codes() {
    let cases = [
        ("(;GM[1];SZ[19])", "root_property_outside_root", 1),
        ("(;SZ[0])", "unsupported_size", 0),
        ("(;SZ[26])", "unsupported_size", 0),
        ("(;SZ[x])", "malformed_size", 0),
        ("(;SZ[19];PL[X])", "malformed_value", 1),
        ("(;SZ[19]AB[aa:zz])", "malformed_value", 0),
        ("(;RU[Chinese];RU[Japanese])", "duplicate_property", 1),
    ];
    for (text, code, node) in cases {
        let error = record(text).unwrap_err();
        assert_eq!((error.code(), error.node), (code, node), "{text}");
    }
    let mixed = record("(;AB[aa]B[bb])").unwrap();
    assert!(codes(&mixed).contains(&"mixed_setup_and_move"));
    let unknown = record("(;RU[GOE])").unwrap();
    assert_eq!(unknown.rules, None);
    assert_eq!(unknown.rules_text.as_deref(), Some("GOE"));
    assert!(codes(&unknown).contains(&"unknown_rules"));
    let replay_error = record("(;SZ[1]AB[aa])")
        .unwrap()
        .replay(Rules::chinese(), Komi::new(0.0).unwrap())
        .unwrap_err();
    assert_eq!(replay_error.code(), "setup_no_liberties");
}

// --- Public corpus (testdata/sgf, see PROVENANCE.md) ---

fn corpus(name: &str) -> Vec<u8> {
    let path = format!("{}/../../testdata/sgf/{name}", env!("CARGO_MANIFEST_DIR"));
    std::fs::read(&path).unwrap_or_else(|e| panic!("{path}: {e}"))
}

#[test]
fn corpus_ke_jie_commentary_with_110_variations() {
    let collection = sgf::parse(&corpus("kejie-2025-11-27.sgf")).unwrap();
    assert_eq!(collection.encoding, "UTF-8");
    assert!(collection.warnings.is_empty());
    let tree = &collection.games[0];
    assert_eq!(tree.len(), 1212);
    let branch_points = tree.nodes().iter().filter(|n| n.children().len() > 1);
    assert_eq!(branch_points.count(), 110);

    let record = extract(tree).unwrap();
    assert_eq!(record.info.black_player.as_deref(), Some("柯洁"));
    assert_eq!(record.info.white_player.as_deref(), Some("王泽锦"));
    assert_eq!(record.rules, Some(Rules::chinese()));
    assert_eq!(record.komi, Komi::new(7.5).ok());
    assert_eq!(record.handicap, Some(0));
    // `RE[黑胜白]` ("Black beats White") is not SGF form and stays text.
    assert_eq!(record.info.result_text.as_deref(), Some("黑胜白"));
    assert_eq!(record.info.result, None);
    assert_eq!(codes(&record), ["malformed_result", "first_variation_only"]);
    assert_eq!(record.moves.len(), 111);
    assert_eq!(record.moves[0], (Color::Black, point(record.size, "pd")));
    assert_eq!(record.moves[110], (Color::Black, point(record.size, "ij")));

    let replay = record
        .replay(Rules::chinese(), record.komi.unwrap())
        .unwrap();
    assert!(replay.warnings.is_empty());

    // The writer keeps all 110 variations.
    assert_eq!(
        &sgf::parse(tree.to_sgf().as_bytes()).unwrap().games[0],
        tree
    );
}

#[test]
fn corpus_gbk_copy_reads_like_the_utf8_original() {
    let collection = sgf::parse(&corpus("kejie-2025-11-27-gbk.sgf")).unwrap();
    assert_eq!(collection.encoding, "gb18030");
    let codes: Vec<_> = collection.warnings.iter().map(|w| w.code()).collect();
    assert_eq!(codes, ["encoding_guessed"]);
    let gbk = extract(&collection.games[0]).unwrap();
    let original = extract(&sgf::parse(&corpus("kejie-2025-11-27.sgf")).unwrap().games[0]).unwrap();
    assert_eq!(gbk.moves, original.moves);
    assert_eq!(gbk.info.black_player, original.info.black_player);
    assert_eq!(
        gbk.info.name.as_deref(),
        Some("第27届中国围甲联赛第11轮 深圳龙华VS河南丰博<绝艺讲解>")
    );
}

#[test]
fn corpus_maruyama_ito_1976() {
    let collection = sgf::parse(&corpus("maruyama-ito-1976.sgf")).unwrap();
    let record = extract(&collection.games[0]).unwrap();
    assert_eq!(codes(&record), ["missing_gm"]);
    assert_eq!(record.moves.len(), 235);
    assert_eq!(record.rules, Some(Rules::japanese()));
    assert_eq!(record.komi, Komi::new(5.5).ok());
    assert_eq!(
        record.info.result,
        Some(GameResult::Points {
            winner: Color::White,
            half_points: 13
        })
    );
    let replay = record
        .replay(Rules::japanese(), record.komi.unwrap())
        .unwrap();
    assert!(replay.warnings.is_empty());
    assert_eq!(replay.positions.len(), 236);
}

#[test]
fn replay_errors_name_the_move() {
    let record = record("(;SZ[19];B[aa];W[bb];B[bb])").unwrap();
    let error = record
        .replay(Rules::japanese(), Komi::new(6.5).unwrap())
        .unwrap_err();
    assert_eq!(
        error,
        weiqi_core::sgf::RecordReplayError::Replay(ReplayError {
            move_number: 3,
            error: weiqi_core::IllegalMove::Occupied
        })
    );
}
