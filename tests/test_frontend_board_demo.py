from pathlib import Path


def test_frontend_board_demo_contains_review_jump_controls() -> None:
    html = Path("frontend/index.html").read_text(encoding="utf-8")

    assert 'id="sgfFileInput"' in html
    assert '选择 SGF 文件' in html
    assert '上传并分析' in html
    assert 'id="uploadStatus"' in html
    assert "function setUploadStatus(message, isError)" in html
    assert "function rebuildBoardFromTimeline(timeline)" in html
    assert 'fetch("http://127.0.0.1:8000/api/v1/analyze-sgf"' in html
    assert '已完成 SGF 分析，并载入终局棋盘。' in html
    assert '上传分析失败：' in html
    assert 'id="latestBtn"' in html
    assert 'id="reviewStatus"' in html
    assert 'id="analysisViewSwitch"' in html
    assert 'data-analysis-view="current"' in html
    assert 'data-analysis-view="review"' in html
    assert 'class="board-column"' in html
    assert 'class="board-meta"' in html
    assert "position: sticky;" in html
    assert "overflow: auto;" in html
    assert "function buildReviewTargets(data)" in html
    assert 'var analysisView = "current";' in html
    assert "function setAnalysisView(view)" in html
    assert 'data-review-id=\\"' in html
    assert "没有接上前面的思路" in html
    assert "脱离主战场" in html
    assert "function moveRefLabel(color, moveNumber)" in html
    assert "function buildPositiveReviewTargets(data)" in html
    assert "亮点手" in html
    assert "关键好手" in html
    assert "胜负手" in html
    assert "目数变化不大。" in html
    assert "胜率提升约" in html
    assert "胜率下滑约" in html
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
