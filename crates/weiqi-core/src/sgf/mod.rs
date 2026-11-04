//! SGF (FF\[4\]) reading and writing.
//!
//! Pipeline: bytes → [`decode`] to UTF-8 → [`parse_text`] into one arena
//! [`SgfTree`] per game → [`SgfTree::to_sgf`]. Decoding comes first because
//! in GBK, Big5 and Shift_JIS the second byte of a character can be `\` or
//! `]`; after decoding, every SGF delimiter is a single ASCII byte that never
//! occurs inside a multi-byte UTF-8 character.
//!
//! Values are stored raw, escapes included, and interpreted on demand, so
//! unknown properties round-trip unchanged. Leniency is never silent: each
//! tolerated irregularity yields an [`SgfWarning`] with a stable code.

mod decode;
mod parse;
mod tree;
mod write;

pub use decode::{Decoded, decode};
pub use parse::{ParseLimits, parse, parse_text, parse_with};
pub use tree::{InvalidProperty, InvalidValue, Node, NodeId, Property, SgfTree, Value};
pub use write::write_collection;

/// The games of one SGF file.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Collection {
    /// One tree per top-level game tree, in file order.
    pub games: Vec<SgfTree>,
    /// Name of the encoding the text was decoded from (`UTF-8` when parsed
    /// from text).
    pub encoding: &'static str,
    /// Tolerated irregularities, in the order found.
    pub warnings: Vec<SgfWarning>,
}

/// A tolerated irregularity.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct SgfWarning {
    /// What was tolerated.
    pub kind: SgfWarningKind,
    /// Byte offset in the decoded text; `None` for decoding warnings.
    pub offset: Option<usize>,
}

/// The kinds of [`SgfWarning`].
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum SgfWarningKind {
    /// No byte-order mark or usable `CA`, and the text was not UTF-8; the
    /// first legacy encoding that decoded without errors was used.
    EncodingGuessed {
        /// The encoding used.
        encoding: &'static str,
    },
    /// The declared `CA` did not fit the bytes, so another encoding was used.
    CharsetMismatch {
        /// The `CA` value.
        declared: String,
        /// The encoding used.
        used: &'static str,
    },
    /// The `CA` value names no known encoding.
    UnknownCharset {
        /// The `CA` value.
        declared: String,
    },
    /// No encoding decoded without errors; invalid bytes became U+FFFD.
    LossyDecode {
        /// The encoding used.
        encoding: &'static str,
    },
    /// Text outside any game tree was skipped.
    JunkOutsideTree,
    /// An identifier had lowercase letters (FF\[1–3\] style); they were dropped.
    LowercaseIdentifier {
        /// The identifier as written.
        written: String,
    },
    /// A game tree or variation `()` without nodes was skipped.
    EmptyVariation,
    /// The input ended inside a game tree; what was read is kept.
    UnclosedTree,
}

impl SgfWarning {
    /// Stable machine-readable code.
    pub fn code(&self) -> &'static str {
        match self.kind {
            SgfWarningKind::EncodingGuessed { .. } => "encoding_guessed",
            SgfWarningKind::CharsetMismatch { .. } => "charset_mismatch",
            SgfWarningKind::UnknownCharset { .. } => "unknown_charset",
            SgfWarningKind::LossyDecode { .. } => "lossy_decode",
            SgfWarningKind::JunkOutsideTree => "junk_outside_tree",
            SgfWarningKind::LowercaseIdentifier { .. } => "lowercase_identifier",
            SgfWarningKind::EmptyVariation => "empty_variation",
            SgfWarningKind::UnclosedTree => "unclosed_tree",
        }
    }
}

/// Input that cannot be read as SGF.
#[derive(Clone, Debug, PartialEq, Eq, thiserror::Error)]
#[error("{kind} at byte {offset}")]
pub struct SgfError {
    /// What went wrong.
    pub kind: SgfErrorKind,
    /// Byte offset in the decoded text (in the input for [`SgfErrorKind::TooLarge`]).
    pub offset: usize,
}

/// The kinds of [`SgfError`].
#[derive(Clone, Debug, PartialEq, Eq, thiserror::Error)]
pub enum SgfErrorKind {
    /// The input exceeds [`ParseLimits::max_bytes`].
    #[error("input exceeds {limit} bytes")]
    TooLarge {
        /// The limit.
        limit: usize,
    },
    /// The collection exceeds [`ParseLimits::max_nodes`].
    #[error("more than {limit} nodes")]
    TooManyNodes {
        /// The limit.
        limit: usize,
    },
    /// Variations nest deeper than [`ParseLimits::max_depth`].
    #[error("variations nested deeper than {limit}")]
    TooDeep {
        /// The limit.
        limit: usize,
    },
    /// No game tree with a node was found.
    #[error("no game tree found")]
    NoGame,
    /// A character that cannot appear there inside a game tree.
    #[error("unexpected character {0:?}")]
    UnexpectedCharacter(char),
    /// A property before the first `;` of a game tree.
    #[error("property outside a node")]
    PropertyOutsideNode,
    /// A property identifier without a value.
    #[error("property without a value")]
    MissingValue,
    /// An identifier with no uppercase letter.
    #[error("invalid property identifier {0:?}")]
    InvalidIdentifier(String),
    /// A value without a property identifier.
    #[error("value without a property identifier")]
    ValueWithoutIdentifier,
    /// A value whose closing `]` is missing.
    #[error("unterminated property value")]
    UnterminatedValue,
    /// A variation `(` before the first node of its sequence.
    #[error("variation before the first node")]
    VariationBeforeNode,
    /// A node or property after a variation of the same sequence.
    #[error("content after a variation")]
    ContentAfterVariation,
}

impl SgfError {
    /// Stable machine-readable code.
    pub fn code(&self) -> &'static str {
        match self.kind {
            SgfErrorKind::TooLarge { .. } => "too_large",
            SgfErrorKind::TooManyNodes { .. } => "too_many_nodes",
            SgfErrorKind::TooDeep { .. } => "too_deep",
            SgfErrorKind::NoGame => "no_game",
            SgfErrorKind::UnexpectedCharacter(_) => "unexpected_character",
            SgfErrorKind::PropertyOutsideNode => "property_outside_node",
            SgfErrorKind::MissingValue => "missing_value",
            SgfErrorKind::InvalidIdentifier(_) => "invalid_identifier",
            SgfErrorKind::ValueWithoutIdentifier => "value_without_identifier",
            SgfErrorKind::UnterminatedValue => "unterminated_value",
            SgfErrorKind::VariationBeforeNode => "variation_before_node",
            SgfErrorKind::ContentAfterVariation => "content_after_variation",
        }
    }
}
