//! Canonical serialisation.
//!
//! One node per line, and each variation opens on a new line:
//!
//! ```text
//! (;GM[1]
//! ;B[pd]
//! (;W[dd]
//! ;B[pp])
//! (;W[dp]))
//! ```
//!
//! Values are written raw, so reading the output back yields an equal tree.
//! The walk uses an explicit stack, like the parser.

use super::tree::{NodeId, SgfTree};

enum Step {
    Open,
    Node(NodeId),
    Close,
}

impl SgfTree {
    /// The tree as SGF text, ending in a newline. The text is UTF-8; a root
    /// `CA` property is written as stored, so set it to `UTF-8` when the tree
    /// was read from another encoding.
    pub fn to_sgf(&self) -> String {
        let mut out = String::new();
        let mut steps = vec![Step::Close, Step::Node(self.root()), Step::Open];
        let mut after_open = false;
        while let Some(step) = steps.pop() {
            match step {
                Step::Open => {
                    if !out.is_empty() {
                        out.push('\n');
                    }
                    out.push('(');
                    after_open = true;
                }
                Step::Close => out.push(')'),
                Step::Node(id) => {
                    let Some(node) = self.node(id) else { continue };
                    if !after_open {
                        out.push('\n');
                    }
                    after_open = false;
                    out.push(';');
                    for property in node.properties() {
                        out.push_str(property.ident());
                        for value in property.values() {
                            out.push('[');
                            out.push_str(value.raw());
                            out.push(']');
                        }
                    }
                    match node.children() {
                        [] => {}
                        [only] => steps.push(Step::Node(*only)),
                        children => {
                            // Pushed in reverse so the first variation pops first.
                            for &child in children.iter().rev() {
                                steps.extend([Step::Close, Step::Node(child), Step::Open]);
                            }
                        }
                    }
                }
            }
        }
        out.push('\n');
        out
    }
}

/// Several games as one collection, each tree on its own lines.
pub fn write_collection(games: &[SgfTree]) -> String {
    games.iter().map(SgfTree::to_sgf).collect()
}
