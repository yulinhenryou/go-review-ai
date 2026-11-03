from pathlib import Path
from html.parser import HTMLParser


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids, self.assets = [], []

    def handle_starttag(self, tag, attributes):
        attributes = dict(attributes)
        if "id" in attributes:
            self.ids.append(attributes["id"])
        for key in ("src", "href"):
            if attributes.get(key, "").startswith("./"):
                self.assets.append(attributes[key])


def test_frontend_entrypoint_wires_local_modules_and_controls():
    html = Path("frontend/index.html").read_text()
    page = Page()
    page.feed(html)
    assert len(page.ids) == len(set(page.ids))
    for name in ["passBtn", "confirmBtn", "inputPreview", "jobPanel", "jobProgress",
                 "cancelJobBtn", "retryJobBtn", "boardCanvas", "editBtn"]:
        assert name in page.ids
    assert '<script type="module" src="./app.mjs"></script>' in html
    assert 'name="api-base" content=""' in html
    assert "function " not in html
    assert all((Path("frontend") / asset).is_file() for asset in page.assets)
