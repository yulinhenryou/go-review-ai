from pathlib import Path


def test_frontend_board_demo_contains_review_jump_controls() -> None:
    html = Path("frontend/index.html").read_text(encoding="utf-8")
    css = Path("frontend/styles.css").read_text(encoding="utf-8")

    assert 'id="sgfFileInput"' in html
    assert '选择 SGF 文件' in html
    assert '上传并分析' in html
    assert 'id="uploadStatus"' in html
    assert "function setUploadStatus(message, isError)" in html
    assert "function rebuildBoardFromTimeline(timeline)" in html
    assert 'fetch("/api/v1/analyze-sgf?"' in html
    assert 'fetch("/api/v1/analyze-moves"' in html
    assert '已载入 ' in html
    assert 'id="rulesInput"' in html
    assert 'id="komiInput"' in html
    assert '<option value="custom">自定义</option>' in html
    assert '<option value="japanese">日韩规则</option>' in html
    assert 'id="customRulesInput"' in html
    assert 'import { createGameSettings } from "./game-settings.mjs"' in html
    assert 'rules: settings.rules' in html
    assert 'komi: settings.komi' in html
    assert 'first_variation_only' in html
    assert '上传分析失败：' in html
    assert 'id="latestBtn"' in html
    assert 'id="reviewStatus"' in html
    assert 'id="analysisViewSwitch"' in html
    assert 'data-analysis-view="current"' in html
    assert 'data-analysis-view="review"' in html
    assert 'class="board-column"' in html
    assert 'class="board-meta"' in html
    assert "position: sticky;" in css
    assert "overflow: auto;" in css
    assert "function buildReviewTargets(data)" in html
    assert 'var analysisView = "current";' in html
    assert "function setAnalysisView(view)" in html
    assert 'data-review-id=\\"' in html
    assert "没有接上前面的思路" not in html
    assert "脱离主战场" not in html
    assert "function moveRefLabel(color, moveNumber)" in html
    assert "function buildPositiveReviewTargets(data)" not in html
    assert "亮点手" not in html
    assert "关键好手" not in html
    assert "胜负手" not in html
    assert "个百分点" in html
    assert 'from "./report-view.mjs"' in html
    assert 'data.schema_version !== "3.0"' in html
    assert "function createBoardSnapshot(uptoMoveCount)" in html
    assert "function drawBoardMarker(marker)" in html
    assert 'from "./board-markers.mjs"' in html
    assert "var selectedCandidateRank = 1;" in html
    assert "function buildCandidateExplanation(data)" in html
    assert 'data-candidate-rank=\\"' in html
    assert "function trySelectCandidateAtPoint(point)" in html
    assert 'played: reviewing ? extractCoordPoint(activeContext.playedMove) : null' in html
    assert 'getCandidateMarkersFromCandidates(getActiveCandidates(data))' in html
    assert 'reviewFocus = reviewTargets[0] || null;' in html
    assert 'if (analysisData) return;' in html
    assert 'id="editBtn"' in html
    assert 'id="showCandidates"' in html
    assert 'id="showMoveNumbers"' in html
    assert "function buildTimelineReviewTarget(data, moveNumber)" in html
    assert "function activateTimelineMove(moveNumber)" in html
    assert "var viewedMoveNumber = null;" in html
    assert "function getActiveContext(data)" in html
    assert "function inferWinratePerspectiveColor(data)" not in html
    assert "黑棋胜率" in html
    assert "白棋胜率" in html
    assert "记录末尾" in html
    assert 'data-chart-move=\\"' in html
    assert '当前选中第' in html
    assert '缺失评估处断线' in html
