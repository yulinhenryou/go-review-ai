//! Bytes to UTF-8 text.
//!
//! Order: a byte-order mark; else the declared `CA`; else the first of UTF-8,
//! GB18030, Big5, Shift_JIS and EUC-KR that decodes without errors; else
//! UTF-8 with replacement characters. Each departure from a clean decode adds
//! a warning.

use encoding_rs::{BIG5, EUC_KR, Encoding, GB18030, SHIFT_JIS, UTF_8, WINDOWS_1252};

use super::{SgfWarning, SgfWarningKind};

/// Encodings tried, in order, when nothing declares one. GB18030 comes first
/// among the legacy encodings because Chinese server exports in GBK (a
/// subset) are the common case for this project's users.
const CANDIDATES: [&Encoding; 5] = [UTF_8, GB18030, BIG5, SHIFT_JIS, EUC_KR];

/// Decoded text.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Decoded {
    /// The text.
    pub text: String,
    /// Name of the encoding used.
    pub encoding: &'static str,
    /// Decoding warnings.
    pub warnings: Vec<SgfWarning>,
}

/// Decodes SGF bytes; never fails.
pub fn decode(bytes: &[u8]) -> Decoded {
    let mut warnings = Vec::new();
    let mut warn = |kind| warnings.push(SgfWarning { kind, offset: None });

    if let Some((encoding, bom)) = Encoding::for_bom(bytes) {
        let body = &bytes[bom..];
        let text = strict(encoding, body).unwrap_or_else(|| {
            warn(SgfWarningKind::LossyDecode {
                encoding: encoding.name(),
            });
            encoding.decode_without_bom_handling(body).0.into_owned()
        });
        return finish(text, encoding, warnings);
    }

    let mut declared = None;
    if let Some(label) = declared_charset(bytes) {
        match Encoding::for_label(label.as_bytes()) {
            None => warn(SgfWarningKind::UnknownCharset { declared: label }),
            Some(encoding) => {
                // Latin-1 decodes any bytes, and many programs write
                // `CA[ISO-8859-1]` regardless of content; valid UTF-8 with
                // non-ASCII characters is then far more likely what was meant.
                if encoding == WINDOWS_1252
                    && !bytes.is_ascii()
                    && let Ok(text) = std::str::from_utf8(bytes)
                {
                    let used = UTF_8.name();
                    warn(SgfWarningKind::CharsetMismatch {
                        declared: label,
                        used,
                    });
                    return finish(text.to_owned(), UTF_8, warnings);
                }
                if let Some(text) = strict(encoding, bytes) {
                    return finish(text, encoding, warnings);
                }
                declared = Some(label);
            }
        }
    }

    for encoding in CANDIDATES {
        if let Some(text) = strict(encoding, bytes) {
            let used = encoding.name();
            match declared {
                Some(declared) => warn(SgfWarningKind::CharsetMismatch { declared, used }),
                None if encoding != UTF_8 => {
                    warn(SgfWarningKind::EncodingGuessed { encoding: used })
                }
                None => {}
            }
            return finish(text, encoding, warnings);
        }
    }
    warn(SgfWarningKind::LossyDecode {
        encoding: UTF_8.name(),
    });
    let text = String::from_utf8_lossy(bytes).into_owned();
    finish(text, UTF_8, warnings)
}

fn finish(text: String, encoding: &'static Encoding, warnings: Vec<SgfWarning>) -> Decoded {
    Decoded {
        text,
        encoding: encoding.name(),
        warnings,
    }
}

fn strict(encoding: &'static Encoding, bytes: &[u8]) -> Option<String> {
    encoding
        .decode_without_bom_handling_and_without_replacement(bytes)
        .map(|text| text.into_owned())
}

/// The value of the first `CA[...]` in the raw bytes. The value is ASCII in
/// every encoding we accept, so it can be found before decoding; requiring a
/// non-letter before `CA` skips identifiers such as `PCA`.
fn declared_charset(bytes: &[u8]) -> Option<String> {
    let mut from = 0;
    while let Some(found) = find(&bytes[from..], b"CA") {
        let start = from + found;
        from = start + 2;
        if start > 0 && bytes[start - 1].is_ascii_alphabetic() {
            continue;
        }
        let rest = &bytes[from..];
        let open = rest.iter().position(|b| !b.is_ascii_whitespace())?;
        if rest[open] != b'[' {
            continue;
        }
        let value = &rest[open + 1..];
        let close = value.iter().position(|&b| b == b']')?;
        return std::str::from_utf8(&value[..close])
            .ok()
            .map(|label| label.trim().to_owned());
    }
    None
}

fn find(haystack: &[u8], needle: &[u8]) -> Option<usize> {
    haystack
        .windows(needle.len())
        .position(|window| window == needle)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn declared_charset_skips_longer_identifiers() {
        assert_eq!(
            declared_charset(b"(;PCA[x]CA [GB2312];)"),
            Some("GB2312".to_owned())
        );
        assert_eq!(declared_charset(b"(;C[CA]"), None);
        assert_eq!(declared_charset(b"(;CA[UTF-8"), None);
    }
}
