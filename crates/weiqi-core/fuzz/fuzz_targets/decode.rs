//! Decoding arbitrary bytes never panics, and valid UTF-8 without a charset
//! hint or BOM decodes to itself.

#![no_main]

use libfuzzer_sys::fuzz_target;
use weiqi_core::sgf;

fuzz_target!(|bytes: &[u8]| {
    let decoded = sgf::decode(bytes);
    if decoded.encoding == "UTF-8"
        && decoded.warnings.is_empty()
        && let Ok(text) = std::str::from_utf8(bytes)
    {
        assert_eq!(decoded.text, text.strip_prefix('\u{feff}').unwrap_or(text));
    }
});
