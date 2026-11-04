//! Parsing, extracting and replaying arbitrary bytes never panics.

#![no_main]

use libfuzzer_sys::fuzz_target;
use weiqi_core::sgf;
use weiqi_core::{Komi, Rules};

fuzz_target!(|bytes: &[u8]| {
    let Ok(collection) = sgf::parse(bytes) else {
        return;
    };
    for tree in &collection.games {
        let Ok(record) = sgf::extract(tree) else {
            continue;
        };
        let komi = Komi::new(7.5).unwrap();
        let _ = record.replay(Rules::chinese(), komi);
        let _ = record.replay(Rules::japanese(), komi);
    }
});
