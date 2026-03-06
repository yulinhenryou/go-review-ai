from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ParsedMove:
    color: str
    point: str | None


@dataclass(frozen=True)
class ParsedGame:
    board_size: int
    komi: float | None
    black_player: str | None
    white_player: str | None
    result: str | None
    moves: list[ParsedMove]


@dataclass
class _GameTree:
    sequence: list[dict[str, list[str]]]
    children: list["_GameTree"]


class _SGFParser:
    def __init__(self, text: str) -> None:
        self.text = text
        self.i = 0
        self.n = len(text)

    def parse(self) -> _GameTree:
        self._skip_ws()
        tree = self._parse_game_tree()
        self._skip_ws()
        if self.i != self.n:
            raise ValueError("Unexpected trailing SGF content")
        return tree

    def _parse_game_tree(self) -> _GameTree:
        self._expect("(")
        self._skip_ws()
        sequence = self._parse_sequence()
        children: list[_GameTree] = []
        self._skip_ws()
        while self._peek() == "(":
            children.append(self._parse_game_tree())
            self._skip_ws()
        self._expect(")")
        return _GameTree(sequence=sequence, children=children)

    def _parse_sequence(self) -> list[dict[str, list[str]]]:
        nodes: list[dict[str, list[str]]] = []
        self._skip_ws()
        while self._peek() == ";":
            nodes.append(self._parse_node())
            self._skip_ws()
        if not nodes:
            raise ValueError("SGF game tree has no nodes")
        return nodes

    def _parse_node(self) -> dict[str, list[str]]:
        self._expect(";")
        props: dict[str, list[str]] = {}
        self._skip_ws()
        while True:
            c = self._peek()
            if c is None or c in ";()":
                break
            ident = self._parse_prop_ident()
            values = self._parse_prop_values()
            props.setdefault(ident, []).extend(values)
            self._skip_ws()
        return props

    def _parse_prop_ident(self) -> str:
        start = self.i
        while True:
            c = self._peek()
            if c is None or not c.isalpha() or not c.isupper():
                break
            self.i += 1
        ident = self.text[start:self.i]
        if not ident:
            raise ValueError(f"Expected property identifier at index {self.i}")
        return ident

    def _parse_prop_values(self) -> list[str]:
        values: list[str] = []
        self._skip_ws()
        while self._peek() == "[":
            values.append(self._parse_prop_value())
            self._skip_ws()
        if not values:
            raise ValueError(f"Property missing value at index {self.i}")
        return values

    def _parse_prop_value(self) -> str:
        self._expect("[")
        out: list[str] = []
        while True:
            c = self._peek()
            if c is None:
                raise ValueError("Unterminated SGF property value")
            if c == "]":
                self.i += 1
                return "".join(out)
            if c == "\\":
                self.i += 1
                escaped = self._peek()
                if escaped is None:
                    raise ValueError("Unterminated SGF escape sequence")
                out.append(escaped)
                self.i += 1
                continue
            out.append(c)
            self.i += 1

    def _skip_ws(self) -> None:
        while self.i < self.n and self.text[self.i] in " \t\r\n":
            self.i += 1

    def _peek(self) -> str | None:
        if self.i >= self.n:
            return None
        return self.text[self.i]

    def _expect(self, char: str) -> None:
        got = self._peek()
        if got != char:
            raise ValueError(f"Expected '{char}' at index {self.i}, got '{got}'")
        self.i += 1


def parse_sgf_file(path: str | Path) -> ParsedGame:
    sgf_path = Path(path)
    return parse_sgf(sgf_path.read_text(encoding="utf-8"))


def parse_sgf(text: str) -> ParsedGame:
    tree = _SGFParser(text).parse()
    nodes = _main_line_nodes(tree)

    root = nodes[0]
    board_size_raw = _first_value(root, "SZ")
    if board_size_raw is None:
        raise ValueError("Missing required SGF board size property: SZ")

    try:
        board_size = int(board_size_raw)
    except ValueError as exc:
        raise ValueError(f"Invalid board size SZ[{board_size_raw}]") from exc

    komi_raw = _first_value(root, "KM")
    komi = float(komi_raw) if komi_raw is not None else None

    moves: list[ParsedMove] = []
    for node in nodes[1:]:
        if "B" in node:
            point = node["B"][0] or None
            moves.append(ParsedMove(color="B", point=point))
        elif "W" in node:
            point = node["W"][0] or None
            moves.append(ParsedMove(color="W", point=point))

    return ParsedGame(
        board_size=board_size,
        komi=komi,
        black_player=_first_value(root, "PB"),
        white_player=_first_value(root, "PW"),
        result=_first_value(root, "RE"),
        moves=moves,
    )


def _first_value(node: dict[str, list[str]], key: str) -> str | None:
    values = node.get(key)
    if not values:
        return None
    return values[0]


def _main_line_nodes(tree: _GameTree) -> list[dict[str, list[str]]]:
    nodes: list[dict[str, list[str]]] = list(tree.sequence)
    current = tree
    while current.children:
        current = current.children[0]
        nodes.extend(current.sequence)
    return nodes
