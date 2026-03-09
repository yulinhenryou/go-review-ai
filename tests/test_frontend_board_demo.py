from pathlib import Path


def test_frontend_board_demo_contains_review_jump_controls() -> None:
    html = Path("frontend/index.html").read_text(encoding="utf-8")

    assert 'id="latestBtn"' in html
    assert 'id="reviewStatus"' in html
    assert 'id="analysisViewSwitch"' in html
    assert 'data-analysis-view="current"' in html
    assert 'data-analysis-view="review"' in html
    assert "function buildReviewTargets(data)" in html
    assert 'var analysisView = "current";' in html
    assert "function setAnalysisView(view)" in html
    assert 'data-review-id=\\"' in html
    assert "function createBoardSnapshot(uptoMoveCount)" in html
    assert "function drawRecommendedMoveMarker(move)" in html
