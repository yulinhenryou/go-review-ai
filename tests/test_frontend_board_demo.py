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
    assert "var selectedCandidateRank = 1;" in html
    assert "function buildCandidateExplanation(data)" in html
    assert 'data-candidate-rank=\\"' in html
    assert "function trySelectCandidateAtPoint(point)" in html
    assert '点击棋盘上的 1 / 2 / 3 候选标记' in html
    assert "function buildTimelineReviewTarget(data, moveNumber)" in html
    assert "function activateTimelineMove(moveNumber)" in html
    assert 'data-chart-move=\\"' in html
    assert '当前选中第' in html
    assert '点击图上的点，可直接跳到对应手数' in html
