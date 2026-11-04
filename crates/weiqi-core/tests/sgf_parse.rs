//! SGF decoding, parsing and writing. Tests named `prototype_*` port the
//! structural cases of `legacy/tests/test_game_input.py` (MIGRATION G08);
//! property-level checks of the same file follow with game extraction.

use encoding_rs::GBK;
use weiqi_core::sgf::{
    self, Collection, ParseLimits, Property, SgfError, SgfTree, SgfWarningKind, Value,
    write_collection,
};

fn parse(text: &str) -> Result<Collection, SgfError> {
    sgf::parse(text.as_bytes())
}

fn codes(collection: &Collection) -> Vec<&'static str> {
    collection.warnings.iter().map(|w| w.code()).collect()
}

/// The text of the first `ident` on node `index` of the main line.
fn main_text(tree: &SgfTree, index: usize, ident: &str) -> Option<String> {
    let id = *tree.main_line().get(index)?;
    Some(tree.node(id)?.get(ident)?.values()[0].text())
}

const VARIATIONS: &str = "(;FF[4]GM[1]SZ[19];B[pd];W[dd](;B[pp])(;B[dp];W[pp]))";

#[test]
fn variations_hang_from_the_last_node_of_a_sequence() {
    let collection = parse(VARIATIONS).unwrap();
    assert!(collection.warnings.is_empty());
    let [tree] = collection.games.as_slice() else {
        panic!("one game expected");
    };
    assert_eq!(tree.len(), 6);
    let line = tree.main_line();
    assert_eq!(line.len(), 4);
    let white = tree.node(line[2]).unwrap();
    assert_eq!(white.children().len(), 2);
    assert_eq!(main_text(tree, 3, "B").as_deref(), Some("pp"));
    let second = tree.node(white.children()[1]).unwrap();
    assert_eq!(second.get("B").unwrap().values()[0].raw(), "dp");
    assert_eq!(second.parent(), Some(line[2]));
}

#[test]
fn writer_is_canonical_and_round_trips() {
    let tree = &parse(VARIATIONS).unwrap().games[0];
    let text = tree.to_sgf();
    assert_eq!(
        text,
        "(;FF[4]GM[1]SZ[19]\n;B[pd]\n;W[dd]\n(;B[pp])\n(;B[dp]\n;W[pp]))\n"
    );
    let again = parse(&text).unwrap();
    assert_eq!(&again.games[0], tree);
    assert_eq!(again.games[0].to_sgf(), text);
}

#[test]
fn unknown_properties_and_escapes_round_trip_unchanged() {
    let source = "(;GM[1]XQ[a\\]b\\\\][second]C[line\\\none];XYZ[ ])";
    let tree = &parse(source).unwrap().games[0];
    let root = tree.node(tree.root()).unwrap();
    let raws: Vec<&str> = root
        .get("XQ")
        .unwrap()
        .values()
        .iter()
        .map(Value::raw)
        .collect();
    assert_eq!(raws, ["a\\]b\\\\", "second"]);
    assert_eq!(main_text(tree, 0, "C").as_deref(), Some("lineone"));
    assert_eq!(&parse(&tree.to_sgf()).unwrap().games[0], tree);
}

#[test]
fn collections_write_and_read_back() {
    let mut first = SgfTree::new(vec![
        Property::new("GM", vec![Value::from_text("1")]).unwrap(),
    ]);
    let comment = Property::new("C", vec![Value::from_text("A]B \\ 棋")]).unwrap();
    first.add_child(first.root(), vec![comment]).unwrap();
    let second = parse("(;GM[1];B[aa])").unwrap().games.remove(0);
    let games = vec![first, second];
    let back = parse(&write_collection(&games)).unwrap();
    assert_eq!(back.games, games);
    assert_eq!(
        main_text(&back.games[0], 1, "C").as_deref(),
        Some("A]B \\ 棋")
    );
}

#[test]
fn prototype_bom_and_escaped_utf8_metadata() {
    let mut data = b"\xef\xbb\xbf".to_vec();
    data.extend_from_slice(
        "(;FF[4]SZ[19]CA[UTF-8]RU[Chinese]KM[7.5]PB[A\\]B]PW[棋手]B[as];W[sa])".as_bytes(),
    );
    let collection = sgf::parse(&data).unwrap();
    assert_eq!(collection.encoding, "UTF-8");
    assert!(collection.warnings.is_empty());
    let tree = &collection.games[0];
    assert_eq!(main_text(tree, 0, "PB").as_deref(), Some("A]B"));
    assert_eq!(main_text(tree, 0, "PW").as_deref(), Some("棋手"));
    assert_eq!(main_text(tree, 0, "B").as_deref(), Some("as"));
    assert_eq!(main_text(tree, 1, "W").as_deref(), Some("sa"));
}

/// Inputs the prototype rejected that are now accepted with a warning or as
/// a collection (changed expectations, listed in the M1 PR).
#[test]
fn prototype_structural_leniency_is_reported() {
    let cases: [(&str, &[&str], usize); 4] = [
        ("junk (;SZ[19];B[aa])", &["junk_outside_tree"], 1),
        ("(;SZ[19];B[aa]) junk", &["junk_outside_tree"], 1),
        ("(;SZ[19];B[aa])(;SZ[19];B[bb])", &[], 2),
        ("(;SZ[19];B[aa]", &["unclosed_tree"], 1),
    ];
    for (text, expected, games) in cases {
        let collection = parse(text).unwrap();
        assert_eq!(codes(&collection), expected, "{text}");
        assert_eq!(collection.games.len(), games, "{text}");
    }
    let junk = &parse("junk (;SZ[19];B[aa])").unwrap().warnings[0];
    assert_eq!(junk.offset, Some(0));
}

/// Structural errors the prototype also rejected.
#[test]
fn prototype_structural_errors_are_rejected() {
    let cases = [
        ("((;SZ[19];B[aa])", "variation_before_node", 1),
        ("(junk(;SZ[19];B[aa])", "property_outside_node", 1),
        ("(;SZ[19];B)", "missing_value", 10),
        ("(;SZ[19]", "unclosed_tree", 0),
    ];
    for (text, code, offset) in &cases[..3] {
        let error = parse(text).unwrap_err();
        assert_eq!((error.code(), error.offset), (*code, *offset), "{text}");
    }
    // A truncated root still yields a game, with a warning.
    let (text, code, _) = cases[3];
    assert_eq!(codes(&parse(text).unwrap()), [code]);
}

/// The prototype rejected these on property rules, which game extraction
/// checks; the tree level keeps them as written.
#[test]
fn prototype_property_cases_parse_as_trees() {
    for text in [
        "(;SZ[19];B[aa][bb])",
        "(;SZ[19];B[aa]B[bb])",
        "(;SZ[19];B[aa]W[bb])",
        "(;SZ[19]KM[6.5]KM[7.5];B[aa])",
    ] {
        let collection = parse(text).unwrap();
        assert!(collection.warnings.is_empty(), "{text}");
    }
    let tree = &parse("(;SZ[19];B[aa]B[bb])").unwrap().games[0];
    let node = tree.node(tree.main_line()[1]).unwrap();
    assert_eq!(node.properties().len(), 2);
}

#[test]
fn other_structural_errors_have_codes_and_offsets() {
    let cases = [
        ("", "no_game", 0),
        ("no tree here", "no_game", 12),
        ("(;C[abc", "unterminated_value", 3),
        ("(;C[abc\\])", "unterminated_value", 3),
        ("(;[aa])", "value_without_identifier", 2),
        ("(;B[aa](;W[bb]);B[cc])", "content_after_variation", 15),
        ("(;B[aa](;W[bb])C[x])", "content_after_variation", 15),
        ("(;B[aa]#)", "unexpected_character", 7),
        ("(;B[aa]棋)", "unexpected_character", 7),
        ("(;add[x])", "invalid_identifier", 2),
    ];
    for (text, code, offset) in cases {
        let error = parse(text).unwrap_err();
        assert_eq!((error.code(), error.offset), (code, offset), "{text}");
    }
    let error = parse("()").unwrap_err();
    assert_eq!(error.code(), "no_game");
}

#[test]
fn ff3_lowercase_identifiers_and_empty_variations_are_tolerated() {
    let collection = parse("(;FF[3]AddBlack[aa]Comment[hi](;B[bb])())").unwrap();
    assert_eq!(
        codes(&collection),
        [
            "lowercase_identifier",
            "lowercase_identifier",
            "empty_variation"
        ]
    );
    assert_eq!(
        collection.warnings[0].kind,
        SgfWarningKind::LowercaseIdentifier {
            written: "AddBlack".to_owned()
        }
    );
    let tree = &collection.games[0];
    let root = tree.node(tree.root()).unwrap();
    let idents: Vec<&str> = root.properties().iter().map(Property::ident).collect();
    assert_eq!(idents, ["FF", "AB", "C"]);
    assert_eq!(root.children().len(), 1);
}

#[test]
fn prototype_byte_and_node_limits() {
    // The prototype's limits, passed explicitly; the defaults are larger.
    let limits = ParseLimits {
        max_bytes: 1024 * 1024,
        max_nodes: 5000,
        ..ParseLimits::default()
    };
    let mut big = b"(;SZ[19];B[aa])".to_vec();
    big.resize(big.len() + limits.max_bytes, b' ');
    let error = sgf::parse_with(&big, &limits).unwrap_err();
    assert_eq!(error.code(), "too_large");

    let many = format!("(;SZ[19];B[aa]{})", ";C[n]".repeat(5000));
    let error = sgf::parse_with(many.as_bytes(), &limits).unwrap_err();
    assert_eq!(error.code(), "too_many_nodes");
    assert_eq!(parse(&many).unwrap().games[0].len(), 5002);
}

#[test]
fn deep_nesting_needs_no_recursion() {
    let depth = ParseLimits::default().max_depth;
    let nested = format!("{}{}", "(;C[x]".repeat(depth), ")".repeat(depth));
    let collection = parse(&nested).unwrap();
    let tree = &collection.games[0];
    assert_eq!(tree.len(), depth);
    assert_eq!(&parse(&tree.to_sgf()).unwrap().games[0], tree);

    let deeper = format!("(;{nested})");
    assert_eq!(parse(&deeper).unwrap_err().code(), "too_deep");
}

fn gbk(text: &str) -> Vec<u8> {
    let (bytes, _, unmappable) = GBK.encode(text);
    assert!(!unmappable);
    bytes.into_owned()
}

#[test]
fn gbk_without_charset_is_guessed_and_reported() {
    let collection = sgf::parse(&gbk("(;GM[1]PB[柯洁]PW[古力])")).unwrap();
    assert_eq!(collection.encoding, "gb18030");
    assert_eq!(codes(&collection), ["encoding_guessed"]);
    assert_eq!(
        main_text(&collection.games[0], 0, "PB").as_deref(),
        Some("柯洁")
    );
}

#[test]
fn gbk_trail_bytes_that_look_like_delimiters_stay_inside_values() {
    // Characters whose second GBK byte is `]` or `\` would end or escape a
    // value if the parser read raw bytes.
    let find = |trail: u8| {
        ('\u{4e00}'..='\u{9fa5}')
            .find(|&c| gbk(&c.to_string()).get(1) == Some(&trail))
            .unwrap()
    };
    let text: String = [find(b']'), find(b'\\')].iter().collect();
    let collection = sgf::parse(&gbk(&format!("(;CA[GBK]C[{text}])"))).unwrap();
    assert_eq!(collection.encoding, "GBK");
    assert!(collection.warnings.is_empty());
    assert_eq!(main_text(&collection.games[0], 0, "C"), Some(text));
}

#[test]
fn declared_charsets_are_honoured_or_reported() {
    let cases: [(Vec<u8>, &str, &[&str], &str); 5] = [
        // Declared and correct.
        (gbk("(;CA[gb2312]PB[柯洁])"), "GBK", &[], "柯洁"),
        // Declared UTF-8, but the bytes are GBK.
        (
            gbk("(;CA[UTF-8]PB[柯洁])"),
            "gb18030",
            &["charset_mismatch"],
            "柯洁",
        ),
        // Declared Latin-1 over UTF-8 Chinese text.
        (
            "(;CA[ISO-8859-1]PB[柯洁])".as_bytes().to_vec(),
            "UTF-8",
            &["charset_mismatch"],
            "柯洁",
        ),
        // Declared Latin-1 over genuine Latin-1 bytes.
        (
            b"(;CA[ISO-8859-1]PB[Ren\xe9])".to_vec(),
            "windows-1252",
            &[],
            "René",
        ),
        // A label no encoding answers to.
        (
            "(;CA[klingon]PB[柯洁])".as_bytes().to_vec(),
            "UTF-8",
            &["unknown_charset"],
            "柯洁",
        ),
    ];
    for (bytes, encoding, warnings, name) in cases {
        let collection = sgf::parse(&bytes).unwrap();
        assert_eq!(collection.encoding, encoding, "{name}");
        assert_eq!(codes(&collection), warnings, "{encoding}");
        assert_eq!(
            main_text(&collection.games[0], 0, "PB").as_deref(),
            Some(name)
        );
    }
    let mismatch = &sgf::parse(&gbk("(;CA[UTF-8]PB[柯洁])")).unwrap().warnings[0];
    assert_eq!(
        mismatch.kind,
        SgfWarningKind::CharsetMismatch {
            declared: "UTF-8".to_owned(),
            used: "gb18030"
        }
    );
}

#[test]
fn undecodable_bytes_are_replaced_and_reported() {
    let collection = sgf::parse(b"(;C[\xff\xff];B[aa])").unwrap();
    assert_eq!(codes(&collection), ["lossy_decode"]);
    assert_eq!(collection.warnings[0].offset, None);
    assert_eq!(
        main_text(&collection.games[0], 0, "C").as_deref(),
        Some("\u{fffd}\u{fffd}")
    );
    assert_eq!(
        main_text(&collection.games[0], 1, "B").as_deref(),
        Some("aa")
    );
}
