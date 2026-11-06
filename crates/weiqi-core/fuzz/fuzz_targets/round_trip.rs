//! Every tree that parses is written and read back unchanged: parse, write,
//! parse gives an equal tree with no warnings and the same text again.

#![no_main]

use libfuzzer_sys::fuzz_target;
use weiqi_core::sgf::{self, ParseLimits};

fuzz_target!(|bytes: &[u8]| {
    let Ok(collection) = sgf::parse(bytes) else {
        return;
    };
    for tree in &collection.games {
        let text = tree.to_sgf();
        let again = sgf::parse_text(&text, &ParseLimits::default()).expect("writer output parses");
        assert!(again.warnings.is_empty(), "{:?}", again.warnings);
        assert_eq!(again.games.len(), 1);
        assert!(again.games[0] == *tree);
        assert_eq!(again.games[0].to_sgf(), text);
    }
});
