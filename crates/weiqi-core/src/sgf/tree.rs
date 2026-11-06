//! The arena game tree.
//!
//! Nodes live in one `Vec` and refer to each other by [`NodeId`] index, so the
//! tree has a single owner and needs no reference counting or interior
//! mutability.

/// A node's index in its [`SgfTree`].
#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct NodeId(u32);

impl NodeId {
    /// The index into the tree's node list.
    pub fn index(self) -> usize {
        self.0 as usize
    }
}

/// A property value exactly as written between `[` and `]`, escapes included.
///
/// Every `]` in it is escaped and it does not end in an unpaired `\`, so
/// writing it back between brackets always reads back the same value.
#[derive(Clone, Debug, PartialEq, Eq, Hash)]
pub struct Value(String);

/// Raw text that would not survive being written between brackets.
#[derive(Clone, Debug, PartialEq, Eq, thiserror::Error)]
#[error("raw SGF value {0:?} has an unescaped ']' or a trailing '\\'")]
pub struct InvalidValue(pub String);

impl Value {
    /// A value from raw SGF text, escapes included.
    pub fn from_raw(raw: impl Into<String>) -> Result<Self, InvalidValue> {
        let raw = raw.into();
        let mut escaped = false;
        for c in raw.chars() {
            match (escaped, c) {
                (true, _) => escaped = false,
                (false, '\\') => escaped = true,
                (false, ']') => return Err(InvalidValue(raw)),
                (false, _) => {}
            }
        }
        if escaped {
            return Err(InvalidValue(raw));
        }
        Ok(Self(raw))
    }

    /// Raw text known to be valid: the parser's own slices.
    pub(crate) fn from_parsed(raw: &str) -> Self {
        Self(raw.to_owned())
    }

    /// A value holding `text`, escaping `\` and `]`.
    pub fn from_text(text: &str) -> Self {
        let mut raw = String::with_capacity(text.len());
        for c in text.chars() {
            if matches!(c, '\\' | ']') {
                raw.push('\\');
            }
            raw.push(c);
        }
        Self(raw)
    }

    /// The raw text, escapes included.
    pub fn raw(&self) -> &str {
        &self.0
    }

    /// The value read as SGF Text: escapes resolved, soft line breaks (`\`
    /// before a line break) removed, line breaks kept as `\n`, and other
    /// whitespace turned into spaces.
    pub fn text(&self) -> String {
        unescape(&self.0, false)
    }

    /// The value read as SGF SimpleText: like [`Value::text`], but line breaks
    /// also become spaces.
    pub fn simple_text(&self) -> String {
        unescape(&self.0, true)
    }
}

fn unescape(raw: &str, simple: bool) -> String {
    let mut out = String::with_capacity(raw.len());
    let mut chars = raw.chars().peekable();
    while let Some(c) = chars.next() {
        let (c, escaped) = match c {
            '\\' => match chars.next() {
                Some(next) => (next, true),
                None => break,
            },
            c => (c, false),
        };
        match c {
            '\n' | '\r' => {
                // "\r\n" and "\n\r" are one line break.
                let pair = if c == '\n' { '\r' } else { '\n' };
                if chars.peek() == Some(&pair) {
                    chars.next();
                }
                if !escaped {
                    out.push(if simple { ' ' } else { '\n' });
                }
            }
            '\t' | '\x0b' | '\x0c' => out.push(' '),
            c => out.push(c),
        }
    }
    out
}

/// A property: an identifier of uppercase ASCII letters and at least one value.
#[derive(Clone, Debug, PartialEq, Eq, Hash)]
pub struct Property {
    ident: String,
    values: Vec<Value>,
}

/// A property identifier that is not uppercase ASCII letters, or no values.
#[derive(Clone, Debug, PartialEq, Eq, thiserror::Error)]
#[error("property {ident:?} needs an uppercase identifier and at least one value")]
pub struct InvalidProperty {
    /// The identifier given.
    pub ident: String,
}

impl Property {
    /// A property; the identifier must be uppercase ASCII letters.
    pub fn new(ident: impl Into<String>, values: Vec<Value>) -> Result<Self, InvalidProperty> {
        let ident = ident.into();
        let valid = !ident.is_empty() && ident.bytes().all(|b| b.is_ascii_uppercase());
        if !valid || values.is_empty() {
            return Err(InvalidProperty { ident });
        }
        Ok(Self { ident, values })
    }

    /// A property from the parser, which has already checked both parts.
    pub(crate) fn from_parsed(ident: String, values: Vec<Value>) -> Self {
        Self { ident, values }
    }

    /// The identifier, such as `B` or `SZ`.
    pub fn ident(&self) -> &str {
        &self.ident
    }

    /// The values, at least one.
    pub fn values(&self) -> &[Value] {
        &self.values
    }
}

/// A node: its properties in file order, and its place in the tree.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct Node {
    properties: Vec<Property>,
    parent: Option<NodeId>,
    children: Vec<NodeId>,
}

impl Node {
    /// The properties, in file order; an identifier may repeat.
    pub fn properties(&self) -> &[Property] {
        &self.properties
    }

    /// The first property named `ident`.
    pub fn get(&self, ident: &str) -> Option<&Property> {
        self.properties.iter().find(|p| p.ident == ident)
    }

    /// The parent, `None` for the root.
    pub fn parent(&self) -> Option<NodeId> {
        self.parent
    }

    /// The children; the first is the main line.
    pub fn children(&self) -> &[NodeId] {
        &self.children
    }
}

/// One game: a tree of nodes rooted at [`SgfTree::root`].
///
/// Equality compares structure and properties, not node numbering, so trees
/// built in different orders compare equal when they serialise the same.
#[derive(Clone, Debug)]
pub struct SgfTree {
    nodes: Vec<Node>,
}

impl SgfTree {
    /// A tree holding only a root with `properties`.
    pub fn new(properties: Vec<Property>) -> Self {
        Self {
            nodes: vec![Node {
                properties,
                ..Node::default()
            }],
        }
    }

    /// The root node's id.
    pub fn root(&self) -> NodeId {
        NodeId(0)
    }

    /// The node `id`, or `None` if it belongs to no node of this tree.
    pub fn node(&self, id: NodeId) -> Option<&Node> {
        self.nodes.get(id.index())
    }

    /// Every node; a node's position is its [`NodeId::index`].
    pub fn nodes(&self) -> &[Node] {
        &self.nodes
    }

    /// Number of nodes.
    pub fn len(&self) -> usize {
        self.nodes.len()
    }

    /// Always false: a tree has a root.
    pub fn is_empty(&self) -> bool {
        self.nodes.is_empty()
    }

    /// Appends a child with `properties` after `parent`'s existing children.
    /// Returns `None` if `parent` is not in this tree.
    pub fn add_child(&mut self, parent: NodeId, properties: Vec<Property>) -> Option<NodeId> {
        self.node(parent)?;
        let id = self.push_child(parent);
        self.nodes[id.index()].properties = properties;
        Some(id)
    }

    /// Replaces the first property with the same identifier on node `id`, or
    /// appends it. Returns `false` if `id` is not in this tree.
    pub fn set_property(&mut self, id: NodeId, property: Property) -> bool {
        let Some(node) = self.nodes.get_mut(id.index()) else {
            return false;
        };
        match node
            .properties
            .iter_mut()
            .find(|p| p.ident == property.ident)
        {
            Some(slot) => *slot = property,
            None => node.properties.push(property),
        }
        true
    }

    /// The root followed by each first child: the main line.
    pub fn main_line(&self) -> Vec<NodeId> {
        let mut line = vec![self.root()];
        let mut node = &self.nodes[0];
        while let Some(&child) = node.children.first() {
            line.push(child);
            node = &self.nodes[child.index()];
        }
        line
    }

    /// Adds an empty child of `parent`, which must be in this tree.
    pub(crate) fn push_child(&mut self, parent: NodeId) -> NodeId {
        // The parser enforces a node limit far below `u32::MAX`.
        let id = NodeId(self.nodes.len() as u32);
        self.nodes.push(Node {
            parent: Some(parent),
            ..Node::default()
        });
        self.nodes[parent.index()].children.push(id);
        id
    }

    /// Appends a property to node `id`, which must be in this tree.
    pub(crate) fn push_property(&mut self, id: NodeId, property: Property) {
        self.nodes[id.index()].properties.push(property);
    }
}

impl PartialEq for SgfTree {
    fn eq(&self, other: &Self) -> bool {
        // Walk both trees in step with an explicit stack; deep trees cannot
        // overflow the call stack.
        let mut pending = vec![(self.root(), other.root())];
        while let Some((a, b)) = pending.pop() {
            let (a, b) = (&self.nodes[a.index()], &other.nodes[b.index()]);
            if a.properties != b.properties || a.children.len() != b.children.len() {
                return false;
            }
            pending.extend(a.children.iter().copied().zip(b.children.iter().copied()));
        }
        true
    }
}

impl Eq for SgfTree {}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn raw_values_must_survive_brackets() {
        assert!(Value::from_raw(r"A\]B").is_ok());
        assert!(Value::from_raw(r"A\\").is_ok());
        assert!(Value::from_raw("A]B").is_err());
        assert!(Value::from_raw(r"A\").is_err());
        assert!(Value::from_raw(r"A\\]").is_err());
    }

    #[test]
    fn text_follows_the_sgf_text_rules() {
        let value = Value::from_raw("a\\]b\\\\c\td\\\r\ne\n\rf").unwrap();
        assert_eq!(value.text(), "a]b\\c de\nf");
        assert_eq!(value.simple_text(), "a]b\\c de f");
        // An escaped tab is still whitespace.
        assert_eq!(Value::from_raw("x\\\ty").unwrap().text(), "x y");
    }

    #[test]
    fn text_round_trips_through_escaping() {
        let text = "A]B \\ 棋手\nline";
        let value = Value::from_text(text);
        assert_eq!(value.raw(), "A\\]B \\\\ 棋手\nline");
        assert_eq!(value.text(), text);
    }

    #[test]
    fn identifiers_are_uppercase_letters() {
        let value = || vec![Value::from_text("x")];
        assert!(Property::new("SZ", value()).is_ok());
        assert!(Property::new("Sz", value()).is_err());
        assert!(Property::new("", value()).is_err());
        assert!(Property::new("B2", value()).is_err());
        assert!(Property::new("B", vec![]).is_err());
    }

    #[test]
    fn equality_ignores_node_numbering() {
        let prop = |id: &str| Property::new(id, vec![Value::from_text("")]).unwrap();
        // Root with children C1 (child G) and C2, built in two orders.
        let mut a = SgfTree::new(vec![]);
        let c1 = a.add_child(a.root(), vec![prop("A")]).unwrap();
        a.add_child(a.root(), vec![prop("B")]).unwrap();
        a.add_child(c1, vec![prop("C")]).unwrap();
        let mut b = SgfTree::new(vec![]);
        let c1 = b.add_child(b.root(), vec![prop("A")]).unwrap();
        b.add_child(c1, vec![prop("C")]).unwrap();
        b.add_child(b.root(), vec![prop("B")]).unwrap();
        assert_eq!(a, b);
        assert_ne!(a.nodes, b.nodes);
        assert!(b.set_property(c1, prop("D")));
        assert_ne!(a, b);
    }
}
