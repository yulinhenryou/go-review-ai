//! Text to game trees, in one pass with an explicit stack.
//!
//! Grammar (FF\[4\]):
//!
//! ```text
//! Collection = GameTree { GameTree }
//! GameTree   = "(" Sequence { GameTree } ")"
//! Sequence   = Node { Node }
//! Node       = ";" { Property }
//! Property   = PropIdent PropValue { PropValue }
//! PropValue  = "[" raw text, "\" escapes the next character "]"
//! ```
//!
//! Each `(` pushes a frame that remembers the node the next `;` hangs from;
//! the subtrees of a sequence all hang from its last node. Every delimiter is
//! ASCII, so the parser scans bytes and slices values at byte offsets that are
//! always character boundaries.

use super::tree::{NodeId, Property, SgfTree, Value};
use super::{Collection, SgfError, SgfErrorKind, SgfWarning, SgfWarningKind, decode};

/// Upper bounds on the input. They are product settings, not SGF limits;
/// the API may pass stricter ones per request.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct ParseLimits {
    /// Bytes of input before decoding.
    pub max_bytes: usize,
    /// Nodes over all games of the collection.
    pub max_nodes: usize,
    /// Nesting of game trees, the top level counting as 1.
    pub max_depth: usize,
}

impl Default for ParseLimits {
    /// 16 MiB, one million nodes and depth 10 000: room for large collections
    /// and commentary files while bounding memory.
    fn default() -> Self {
        Self {
            max_bytes: 16 * 1024 * 1024,
            max_nodes: 1_000_000,
            max_depth: 10_000,
        }
    }
}

/// Decodes and parses SGF bytes with the default limits.
pub fn parse(bytes: &[u8]) -> Result<Collection, SgfError> {
    parse_with(bytes, &ParseLimits::default())
}

/// Decodes and parses SGF bytes.
pub fn parse_with(bytes: &[u8], limits: &ParseLimits) -> Result<Collection, SgfError> {
    if bytes.len() > limits.max_bytes {
        return Err(SgfError {
            kind: SgfErrorKind::TooLarge {
                limit: limits.max_bytes,
            },
            offset: limits.max_bytes,
        });
    }
    let decoded = decode(bytes);
    let mut collection = parse_text(&decoded.text, limits)?;
    collection.encoding = decoded.encoding;
    let mut warnings = decoded.warnings;
    warnings.append(&mut collection.warnings);
    collection.warnings = warnings;
    Ok(collection)
}

/// Parses SGF text that is already decoded. `limits.max_bytes` applies to the
/// text's UTF-8 length.
pub fn parse_text(text: &str, limits: &ParseLimits) -> Result<Collection, SgfError> {
    if text.len() > limits.max_bytes {
        return Err(SgfError {
            kind: SgfErrorKind::TooLarge {
                limit: limits.max_bytes,
            },
            offset: limits.max_bytes,
        });
    }
    Parser {
        text,
        bytes: text.as_bytes(),
        pos: 0,
        limits,
        games: Vec::new(),
        tree: None,
        stack: Vec::new(),
        nodes: 0,
        warnings: Vec::new(),
        in_junk: false,
    }
    .run()
}

/// One open game tree: `attach` is the node the next `;` hangs from.
struct Frame {
    attach: Option<NodeId>,
    has_node: bool,
    has_variation: bool,
}

struct Parser<'a> {
    text: &'a str,
    bytes: &'a [u8],
    pos: usize,
    limits: &'a ParseLimits,
    games: Vec<SgfTree>,
    /// The game being built; `None` until its first node.
    tree: Option<SgfTree>,
    stack: Vec<Frame>,
    nodes: usize,
    warnings: Vec<SgfWarning>,
    /// Inside a run of junk outside any tree, already reported.
    in_junk: bool,
}

impl Parser<'_> {
    fn run(mut self) -> Result<Collection, SgfError> {
        while let Some(&byte) = self.bytes.get(self.pos) {
            if self.stack.is_empty() && byte != b'(' && !byte.is_ascii_whitespace() {
                self.junk();
                continue;
            }
            match byte {
                b'(' => self.open()?,
                b')' => self.close(),
                b';' => self.node()?,
                b'[' => return Err(self.error(SgfErrorKind::ValueWithoutIdentifier)),
                b if b.is_ascii_alphabetic() => self.property()?,
                b if b.is_ascii_whitespace() => self.pos += 1,
                _ => {
                    let c = self.text[self.pos..].chars().next().unwrap_or('\u{fffd}');
                    return Err(self.error(SgfErrorKind::UnexpectedCharacter(c)));
                }
            }
        }
        if !self.stack.is_empty() {
            self.warn(SgfWarningKind::UnclosedTree, self.bytes.len());
            self.stack.clear();
            self.finish_game();
        }
        if self.games.is_empty() {
            return Err(self.error(SgfErrorKind::NoGame));
        }
        Ok(Collection {
            games: self.games,
            encoding: "UTF-8",
            warnings: self.warnings,
        })
    }

    fn error(&self, kind: SgfErrorKind) -> SgfError {
        SgfError {
            kind,
            offset: self.pos,
        }
    }

    fn warn(&mut self, kind: SgfWarningKind, offset: usize) {
        self.warnings.push(SgfWarning {
            kind,
            offset: Some(offset),
        });
    }

    /// Skips one character outside any tree, reporting each run once.
    fn junk(&mut self) {
        if !self.in_junk {
            self.in_junk = true;
            self.warn(SgfWarningKind::JunkOutsideTree, self.pos);
        }
        let width = self.text[self.pos..]
            .chars()
            .next()
            .map_or(1, char::len_utf8);
        self.pos += width;
    }

    fn open(&mut self) -> Result<(), SgfError> {
        self.in_junk = false;
        let attach = match self.stack.last_mut() {
            None => None,
            Some(frame) if !frame.has_node => {
                return Err(self.error(SgfErrorKind::VariationBeforeNode));
            }
            Some(frame) => {
                frame.has_variation = true;
                frame.attach
            }
        };
        if self.stack.len() >= self.limits.max_depth {
            return Err(self.error(SgfErrorKind::TooDeep {
                limit: self.limits.max_depth,
            }));
        }
        self.stack.push(Frame {
            attach,
            has_node: false,
            has_variation: false,
        });
        self.pos += 1;
        Ok(())
    }

    fn close(&mut self) {
        // `run` only calls this inside a tree, so a frame is always open.
        if let Some(frame) = self.stack.pop()
            && !frame.has_node
        {
            self.warn(SgfWarningKind::EmptyVariation, self.pos);
        }
        if self.stack.is_empty() {
            self.finish_game();
        }
        self.pos += 1;
    }

    fn finish_game(&mut self) {
        if let Some(tree) = self.tree.take() {
            self.games.push(tree);
        }
    }

    fn node(&mut self) -> Result<(), SgfError> {
        let error = |kind| SgfError {
            kind,
            offset: self.pos,
        };
        let Some(frame) = self.stack.last_mut() else {
            return Err(error(SgfErrorKind::NoGame));
        };
        if frame.has_variation {
            return Err(error(SgfErrorKind::ContentAfterVariation));
        }
        self.nodes += 1;
        if self.nodes > self.limits.max_nodes {
            return Err(error(SgfErrorKind::TooManyNodes {
                limit: self.limits.max_nodes,
            }));
        }
        let id = match (&mut self.tree, frame.attach) {
            (None, _) => {
                let tree = self.tree.insert(SgfTree::new(Vec::new()));
                tree.root()
            }
            (Some(tree), Some(parent)) => tree.push_child(parent),
            // A frame without `attach` is the top level before its first
            // node, when no tree exists yet.
            (Some(_), None) => return Err(error(SgfErrorKind::VariationBeforeNode)),
        };
        frame.attach = Some(id);
        frame.has_node = true;
        self.pos += 1;
        Ok(())
    }

    fn property(&mut self) -> Result<(), SgfError> {
        let start = self.pos;
        let node = match self.stack.last() {
            Some(frame) if frame.has_variation => {
                return Err(self.error(SgfErrorKind::ContentAfterVariation));
            }
            Some(Frame {
                attach: Some(node),
                has_node: true,
                ..
            }) => *node,
            _ => return Err(self.error(SgfErrorKind::PropertyOutsideNode)),
        };

        while self
            .bytes
            .get(self.pos)
            .is_some_and(|b| b.is_ascii_alphabetic())
        {
            self.pos += 1;
        }
        let written = &self.text[start..self.pos];
        let ident: String = written.chars().filter(char::is_ascii_uppercase).collect();
        if ident.is_empty() {
            return Err(SgfError {
                kind: SgfErrorKind::InvalidIdentifier(written.to_owned()),
                offset: start,
            });
        }
        if ident.len() != written.len() {
            let written = written.to_owned();
            self.warn(SgfWarningKind::LowercaseIdentifier { written }, start);
        }

        let mut values = Vec::new();
        loop {
            self.skip_whitespace();
            if self.bytes.get(self.pos) != Some(&b'[') {
                break;
            }
            values.push(self.value()?);
        }
        if values.is_empty() {
            return Err(self.error(SgfErrorKind::MissingValue));
        }
        if let Some(tree) = &mut self.tree {
            tree.push_property(node, Property::from_parsed(ident, values));
        }
        Ok(())
    }

    /// Reads `[...]` starting at the `[`.
    fn value(&mut self) -> Result<Value, SgfError> {
        let open = self.pos;
        let mut i = open + 1;
        while let Some(&byte) = self.bytes.get(i) {
            match byte {
                // Skips the escaped byte; an escaped multi-byte character's
                // remaining bytes are never delimiters.
                b'\\' => i += 2,
                b']' => {
                    let value = Value::from_parsed(&self.text[open + 1..i]);
                    self.pos = i + 1;
                    return Ok(value);
                }
                _ => i += 1,
            }
        }
        Err(SgfError {
            kind: SgfErrorKind::UnterminatedValue,
            offset: open,
        })
    }

    fn skip_whitespace(&mut self) {
        while self
            .bytes
            .get(self.pos)
            .is_some_and(|b| b.is_ascii_whitespace())
        {
            self.pos += 1;
        }
    }
}
