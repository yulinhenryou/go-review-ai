"""Build the explicit read-only GitHub Pages showcase."""
from __future__ import annotations

import argparse
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
PAGE_FILES = (
    "board-markers.mjs",
    "board-view.mjs",
    "coordinates.mjs",
    "demo-app.mjs",
    "demo-data.json",
    "index.html",
    "report-view.mjs",
    "review-controller.mjs",
    "review-navigation.mjs",
    "styles.css",
)


def build(output: Path) -> None:
    source = ROOT / "frontend"
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    for name in PAGE_FILES:
        shutil.copy2(source / name, output / name)
    shutil.copytree(source / "icons", output / "icons")

    index = (output / "index.html").read_text()
    index = index.replace(
        "<title>围棋复盘 · 本地工作台</title>",
        "<title>围棋复盘 · KataGo 示例报告</title>",
    ).replace(
        "<body>",
        '<body class="demo-mode">',
    ).replace(
        '<span class="workspace-label">本地工作台</span>',
        '<span class="workspace-label">GitHub Pages · 只读示例</span>',
    ).replace(
        '<script type="module" src="./app.mjs"></script>',
        '<script type="module" src="./demo-app.mjs"></script>',
    )
    (output / "index.html").write_text(index)
    (output / ".nojekyll").write_text("")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path, nargs="?", default=ROOT / "dist" / "pages")
    args = parser.parse_args()
    build(args.output.resolve())
    print(args.output.resolve())


if __name__ == "__main__":
    main()
