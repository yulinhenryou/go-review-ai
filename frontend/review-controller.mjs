import { renderReportOverview, renderMistakeMarkers, renderQualityNotes, trendPath } from "./report-view.mjs";
import { buildBoardMarkers, markerDescription } from "./board-markers.mjs";
import { BOARD_SIZE, DISPLAY_COLUMNS, colorName, fromSgf, fromDisplayCoord } from "./coordinates.mjs";
import { createBoardView } from "./board-view.mjs";

export function createReviewController(getInput) {
  const byId = (id) => document.getElementById(id);
  const canvas = byId("boardCanvas"), boardElement = byId("board");
  const board = createBoardView(boardElement, canvas);
  const showCandidates = byId("showCandidates"), showMoveNumbers = byId("showMoveNumbers");
  const pointSummary = byId("boardPointSummary"), summary = byId("analysisSummary");
  const output = byId("analysisOutput"), status = byId("status"), reviewStatus = byId("reviewStatus");
  const latestBtn = byId("latestBtn"), prevReviewBtn = byId("prevReviewBtn"), nextReviewBtn = byId("nextReviewBtn");
  const analysisViewSwitch = byId("analysisViewSwitch");
  let visibleMarkers = [], moves = [], currentColor = "B", isBusy = false;
  let candidateMarkers = [], chartMetric = "winrate", analysisData = null, reviewFocus = null;
  let viewedMoveNumber = null, reviewTargets = [], analysisView = "current", selectedCandidateRank = 1;
  function updateStatus() {
    updateReviewStatus();
  }

  function updateReviewStatus() {
    var active = getActiveContext(analysisData);
    var reviewing = active && active.kind !== "current_position";
    var detail = reviewing ? findTimelineItem(analysisData, active.moveNumber) : null;
    document.getElementById("moveCounter").textContent =
      (reviewing ? active.moveNumber : moves.length) + " / " + moves.length;
    status.textContent = analysisData ? "复盘 · " + moves.length + " 手" :
      "下一手：" + colorName(currentColor) + " | 手数：" + moves.length;
    if (!analysisData || !active) {
      reviewStatus.innerHTML = '<span class="review-badge">' +
        (getInput().source === "sgf" ? "棋谱预览" : "手动录入") +
        '</span><span class="meta">19 路棋盘</span>';
      latestBtn.disabled = true;
      return;
    }
    if (!reviewing) {
      reviewStatus.innerHTML = '<span class="review-badge">记录末尾</span><span>下一手 ' +
        escapeHtml(colorName(active.nextPlayer)) + ' · 推荐 ' +
        escapeHtml(formatCoord(active.recommendedMove)) + '</span>';
      latestBtn.disabled = true;
      return;
    }
    var loss = detail && typeof detail.score_loss === "number"
      ? detail.score_loss.toFixed(2) + " 目" : "未评估";
    reviewStatus.innerHTML = '<span class="review-badge">' +
      escapeHtml(moveRefLabel(active.color, active.moveNumber)) + ' · 落子前</span>' +
      '<span class="' + (detail && detail.is_mistake ? "focus-loss" : "meta") + '">' +
      escapeHtml(detail && detail.severity_label || "目损") + ' ' + escapeHtml(loss) + '</span>' +
      '<span>实战 ' + escapeHtml(formatCoord(active.playedMove)) + ' / 推荐 ' +
      escapeHtml(formatCoord(active.recommendedMove)) + '</span>';
    latestBtn.disabled = false;
  }

  function getTimelineMoveBounds() {
    var timeline = analysisData && Array.isArray(analysisData.timeline) ? analysisData.timeline : [];

    if (!timeline.length) {
      return null;
    }

    return {
      first: typeof timeline[0].move_number === "number" ? timeline[0].move_number : 1,
      last: typeof timeline[timeline.length - 1].move_number === "number"
        ? timeline[timeline.length - 1].move_number
        : timeline.length
    };
  }

  function updateReviewNavigationControls() {
    if (isBusy) {
      prevReviewBtn.disabled = true;
      nextReviewBtn.disabled = true;
      latestBtn.disabled = true;
      return;
    }
    var bounds = getTimelineMoveBounds();
    var currentMoveNumber = getViewedMoveNumber();
    var canNavigate = Boolean(bounds && typeof currentMoveNumber === "number");

    prevReviewBtn.disabled = !canNavigate || currentMoveNumber <= bounds.first;
    nextReviewBtn.disabled = !canNavigate || currentMoveNumber >= bounds.last;
  }

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function formatCoord(coord) {
    if (!coord) return "暂无";
    if (typeof coord === "string") return coord;
    if (coord.display) return coord.display;
    if (coord.sgf) return coord.sgf;
    return "暂无";
  }

  function extractCoordPoint(coord) {
    if (!coord) return null;

    if (typeof coord === "string") {
      return fromSgf(coord) || fromDisplayCoord(coord);
    }

    return fromSgf(coord.sgf) || fromDisplayCoord(coord.display);
  }

  function getCurrentCandidateMarkers(data) {
    return getCandidateMarkersFromCandidates(getActiveCandidates(data));
  }

  function latestTimelineMoveNumber() {
    var bounds = getTimelineMoveBounds();
    return bounds ? bounds.last : null;
  }

  function getViewedMoveNumber() {
    if (typeof viewedMoveNumber === "number") {
      return viewedMoveNumber;
    }

    return latestTimelineMoveNumber();
  }

  function isViewingLatestMove() {
    var latestMove = latestTimelineMoveNumber();
    return typeof latestMove === "number" && getViewedMoveNumber() === latestMove;
  }

  function nextPlayerAfterMoveNumber(moveNumber) {
    if (typeof moveNumber !== "number") return null;
    return moveNumber % 2 === 0 ? "B" : "W";
  }

  function buildLatestPositionContext(data) {
    var current = data && data.current_position ? data.current_position : {};
    var latestMove = latestTimelineMoveNumber();
    var latestTimelineItem = findTimelineItem(data, latestMove) || {};

    return {
      id: "current-position",
      kind: "current_position",
      title: "最新局面",
      summary: current.short_explanation || "暂无说明。",
      moveNumber: latestMove,
      color: latestTimelineItem.color || null,
      label: "当前局面",
      playedMove: latestTimelineItem.played_move || null,
      recommendedMove: current.best_move || null,
      topCandidates: Array.isArray(current.top_candidates) ? current.top_candidates.slice(0, 3) : [],
      pvSummary: current.pv_summary || "",
      nextPlayer: current.next_player || nextPlayerAfterMoveNumber(latestMove),
      winrateOwnerColor: current.next_player || "B"
    };
  }

  function getActiveContext(data) {
    var currentMoveNumber;

    if (!data || typeof data !== "object") return null;

    currentMoveNumber = getViewedMoveNumber();
    if (reviewFocus && reviewFocus.moveNumber === currentMoveNumber) {
      return reviewFocus;
    }

    if (isViewingLatestMove()) {
      return buildLatestPositionContext(data);
    }

    return buildTimelineReviewTarget(data, currentMoveNumber);
  }

  function getCandidateMarkersFromCandidates(candidates) {
    if (!Array.isArray(candidates)) return [];

    return candidates
      .slice(0, 3)
      .map(function (candidate, index) {
        var point = extractCoordPoint(candidate && candidate.move);

        if (!point) return null;

        return {
          x: point.x,
          y: point.y,
          rank: index + 1,
          move: candidate.move
        };
      })
      .filter(Boolean);
  }

  function getActiveCandidates(data) {
    var activeContext = getActiveContext(data);
    return activeContext && Array.isArray(activeContext.topCandidates) ? activeContext.topCandidates.slice(0, 3) : [];
  }

  function candidateRankLabel(rank) {
    if (rank === 1) return "第1选择";
    if (rank === 2) return "第2选择";
    if (rank === 3) return "第3选择";
    return "候选点";
  }

  function currentCandidateContextKey() {
    var activeContext = getActiveContext(analysisData);
    return activeContext ? activeContext.kind + ":" + activeContext.id : "current";
  }

  function getSelectedCandidate(data) {
    var candidates = getActiveCandidates(data);
    var index = Math.max(0, selectedCandidateRank - 1);

    if (!candidates.length) return null;
    if (index >= candidates.length) index = 0;

    return {
      rank: index + 1,
      candidate: candidates[index]
    };
  }

  function resetSelectedCandidate(data) {
    selectedCandidateRank = getActiveCandidates(data).length ? 1 : 0;
  }

  function ensureSelectedCandidate(data) {
    var candidates = getActiveCandidates(data);

    if (!candidates.length) {
      selectedCandidateRank = 0;
      return;
    }

    if (selectedCandidateRank < 1 || selectedCandidateRank > candidates.length) {
      selectedCandidateRank = 1;
    }
  }

  function playerLabel(color) {
    if (color === "B") return "黑棋";
    if (color === "W") return "白棋";
    return color || "未知";
  }

  function moveRefLabel(color, moveNumber) {
    var shortColor = color === "B" ? "黑" : (color === "W" ? "白" : "");
    if (!shortColor) return "第" + String(moveNumber) + "手";
    return shortColor + "第" + String(moveNumber) + "手";
  }



  function renderRawJson(data) {
    output.textContent = typeof data === "string" ? data : JSON.stringify(data, null, 2);
  }


  function renderErrorState(message) {
    summary.innerHTML = "<div class=\"error-message\">" + escapeHtml(message) + "</div>";
  }

  function clearAnalysisState() {
    analysisData = null;
    reviewFocus = null;
    viewedMoveNumber = null;
    reviewTargets = [];
    candidateMarkers = [];
    selectedCandidateRank = 1;
    chartMetric = "winrate";
    summary.textContent = "暂无分析结果。";
    output.textContent = "暂无分析数据。";
    updateReviewStatus();
    updateReviewNavigationControls();
  }


  function applyAnalysisResult(data) {
    if (data.schema_version !== "3.0") throw new Error("报告版本不兼容，请更新后端后重新分析。");
    analysisData = data;
    reviewTargets = buildReviewTargets(data);
    reviewFocus = reviewTargets[0] || null;
    viewedMoveNumber = reviewFocus ? reviewFocus.moveNumber : latestTimelineMoveNumber();
    resetSelectedCandidate(data);
    candidateMarkers = getCurrentCandidateMarkers(data);
    chartMetric = "winrate";
    drawBoard();
    updateStatus();
    updateReviewStatus();
    updateReviewNavigationControls();
    renderAnalysisSummary(data);
    renderRawJson(data);
  }

  function syncAnalysisViewButtons() {
    Array.prototype.forEach.call(analysisViewSwitch.querySelectorAll("[data-analysis-view]"), function (button) {
      var isActive = button.getAttribute("data-analysis-view") === analysisView;
      button.classList.toggle("active", isActive);
      button.setAttribute("aria-pressed", isActive ? "true" : "false");
    });
  }

  function setAnalysisView(view) {
    if (isBusy) return;
    analysisView = view === "review" ? "review" : "current";
    syncAnalysisViewButtons();

    if (analysisData) {
      renderAnalysisSummary(analysisData);
    }
  }

  function findTimelineItem(data, moveNumber) {
    var timeline = data && Array.isArray(data.timeline) ? data.timeline : [];

    for (var i = 0; i < timeline.length; i++) {
      if (timeline[i] && timeline[i].move_number === moveNumber) {
        return timeline[i];
      }
    }

    return null;
  }

  function findReviewMistake(data, moveNumber) {
    var selected = data && data.review && Array.isArray(data.review.mistakes_above_threshold)
      ? data.review.mistakes_above_threshold
      : [];

    for (var i = 0; i < selected.length; i++) {
      if (selected[i] && selected[i].move_number === moveNumber) {
        return selected[i];
      }
    }

    return null;
  }

  function buildReviewTarget(data, config) {
    var detail = findReviewMistake(data, config.moveNumber) || findTimelineItem(data, config.moveNumber) || {};
    var topCandidates = Array.isArray(detail.top_candidates) ? detail.top_candidates : [];

    return {
      id: config.id,
      kind: config.kind,
      title: config.title,
      summary: config.summary,
      moveNumber: config.moveNumber,
      color: config.color || detail.color || null,
      label: config.label,
      playedMove: detail.played_move || config.playedMove || null,
      recommendedMove: detail.recommended_move || detail.best_move || config.recommendedMove || null,
      topCandidates: topCandidates,
      pvSummary: detail.pv_summary || "",
      nextPlayer: config.color || detail.color,
      winrateOwnerColor: config.color || detail.color || null
    };
  }

  function buildTimelineReviewSummary(detail) {
    return detail && detail.summary || "该手证据不可用。";
  }

  function buildTimelineReviewTarget(data, moveNumber) {
    var detail = findTimelineItem(data, moveNumber);
    var mistake = findReviewMistake(data, moveNumber) || {};
    if (!detail) return null;
    var topCandidates = Array.isArray(mistake.top_candidates)
      ? mistake.top_candidates
      : (Array.isArray(detail.top_candidates) ? detail.top_candidates : []);

    if (!detail || typeof detail.move_number !== "number") {
      return null;
    }

    return {
      id: "timeline-" + detail.move_number,
      kind: "timeline_point",
      title: "走势定位",
      summary: buildTimelineReviewSummary(detail),
      moveNumber: detail.move_number,
      color: detail.color || null,
      label: detail.severity_label || (detail.is_mistake === null ? "未评估" : "未达失误阈值"),
      playedMove: detail.played_move || null,
      recommendedMove: mistake.recommended_move || detail.recommended_move || null,
      topCandidates: topCandidates,
      pvSummary: mistake.pv_summary || detail.pv_summary || "",
      nextPlayer: detail.color,
      winrateOwnerColor: detail.color || null
    };
  }

  function buildReviewTargets(data) {
    return (data.selected_mistakes || []).map(function (item) {
      return buildReviewTarget(data, {
        id: "mistake-" + item.move_number,
        kind: "mistake",
        title: item.severity_label,
        summary: item.summary,
        moveNumber: item.move_number,
        color: item.color,
        label: (item.quality_notes || []).join(" ")
      });
    });
  }

  function renderReviewTargetList(items, emptyText) {
    if (!items.length) {
      return "<div>" + escapeHtml(emptyText) + "</div>";
    }

    return "<ul>" + items.map(function (item) {
      var isActive = reviewFocus && reviewFocus.id === item.id;

      return [
        "<li>",
        "<button type=\"button\" class=\"review-item-button" + (isActive ? " active" : "") + "\" data-review-id=\"" + escapeHtml(item.id) + "\">",
        "<strong>" + escapeHtml(item.title) + " · " + escapeHtml(moveRefLabel(item.color, item.moveNumber)) + "</strong>",
        "<span>" + escapeHtml(item.summary) + "</span>",
        "<span class=\"review-item-meta\">",
        "实战 " + escapeHtml(formatCoord(item.playedMove)) +
        " | 推荐 " + escapeHtml(formatCoord(item.recommendedMove)) +
        (item.label ? " | " + escapeHtml(item.label) : ""),
        "</span>",
        "</button>",
        "</li>"
      ].join("");
    }).join("") + "</ul>";
  }

  function activateReviewTargetById(targetId) {
    var target = null;

    for (var i = 0; i < reviewTargets.length; i++) {
      if (reviewTargets[i].id === targetId) {
        target = reviewTargets[i];
        break;
      }
    }

    if (!target) return;

    reviewFocus = target;
    viewedMoveNumber = target.moveNumber;
    resetSelectedCandidate(analysisData);
    candidateMarkers = getCandidateMarkersFromCandidates(target.topCandidates);
    drawBoard();
    updateReviewStatus();
    updateReviewNavigationControls();
    renderAnalysisSummary(analysisData);
  }

  function activateTimelineMove(moveNumber) {
    var target;
    var latestMove;

    if (!analysisData) return;
    latestMove = latestTimelineMoveNumber();
    if (typeof latestMove !== "number") return;
    if (moveNumber < 1 || moveNumber > latestMove) return;

    viewedMoveNumber = moveNumber;
    target = buildTimelineReviewTarget(analysisData, moveNumber);
    reviewFocus = target;
    resetSelectedCandidate(analysisData);
    candidateMarkers = target ? getCandidateMarkersFromCandidates(target.topCandidates) : [];
    drawBoard();
    updateReviewStatus();
    updateReviewNavigationControls();
    renderAnalysisSummary(analysisData);
  }

  function returnToLatestBoardState() {
    reviewFocus = null;
    viewedMoveNumber = latestTimelineMoveNumber();
    resetSelectedCandidate(analysisData);
    candidateMarkers = getCurrentCandidateMarkers(analysisData);
    drawBoard();
    updateReviewStatus();
    updateReviewNavigationControls();
    renderAnalysisSummary(analysisData);
  }

  function stepReviewPosition(offset) {
    var nextMoveNumber;

    if (!analysisData || !offset) return;

    nextMoveNumber = getViewedMoveNumber() + offset;
    activateTimelineMove(nextMoveNumber);
  }

  function shouldIgnoreReviewKeydown(event) {
    var target = event.target;
    var tagName;

    if (!target) return false;

    tagName = target.tagName;
    return target.isContentEditable || tagName === "INPUT" || tagName === "TEXTAREA" || tagName === "SELECT";
  }

  function candidateDeltaText(activeCandidates, rank, candidate) {
    var best = activeCandidates && activeCandidates[0];
    if (rank === 1) return "引擎第 1 推荐。";
    if (!best) return "对比证据不可用。";
    var parts = [];
    if (typeof best.score_estimate === "number" && typeof candidate.score_estimate === "number") {
      parts.push("相对第 1 推荐目差变化 " + (candidate.score_estimate - best.score_estimate).toFixed(2) + " 目");
    }
    if (typeof best.winrate === "number" && typeof candidate.winrate === "number") {
      parts.push("胜率变化 " + ((candidate.winrate - best.winrate) * 100).toFixed(2) + " 个百分点");
    }
    return parts.length ? parts.join("；") + "。搜索估计可能存在噪声。" : "对比证据不可用。";
  }

  function buildCandidateExplanation(data) {
    var selected = getSelectedCandidate(data);
    var activeCandidates = getActiveCandidates(data);
    var activeContext = getActiveContext(data);
    var candidate;
    var rankLabel;
    var scoreText;
    var winrateText;
    var pvText;
    var winrateLabel = winrateLabelForColor(activeContext && activeContext.winrateOwnerColor);

    if (!selected) {
      return "<div>暂无候选点说明。</div>";
    }

    candidate = selected.candidate;
    rankLabel = candidateRankLabel(selected.rank);
    scoreText = typeof candidate.score_estimate === "number"
      ? candidate.score_estimate.toFixed(2) + "目"
      : "暂无目差";
    winrateText = typeof candidate.winrate === "number"
      ? (candidate.winrate * 100).toFixed(1) + "%"
      : "暂无胜率";

    if (Array.isArray(candidate.pv) && candidate.pv.length) {
      pvText = candidate.pv.map(function (step) {
        var point = fromSgf(step.move);
        var coord = point ? DISPLAY_COLUMNS.charAt(point.x) + String(BOARD_SIZE - point.y) : step.move;
        return (step.color === "B" ? "黑" : "白") + coord;
      }).join(" -> ");
    } else {
      pvText = "暂无完整PV，只展示候选点本身的胜率与目差。";
    }

    return [
      "<div class=\"candidate-detail-panel\" data-candidate-context=\"" + escapeHtml(currentCandidateContextKey()) + "\">",
      "<div class=\"candidate-detail-title\">",
      "<span class=\"candidate-rank-badge\">" + escapeHtml(rankLabel) + "</span>",
      "<strong>" + escapeHtml(formatCoord(candidate.move)) + "</strong>",
      "</div>",
      "<p>" + escapeHtml(winrateLabel) + "：" + escapeHtml(winrateText) + "；" + escapeHtml(playerLabel(activeContext && activeContext.winrateOwnerColor)) + "目差：" + escapeHtml(scoreText) + "。</p>",
      "<p>" + escapeHtml(candidateDeltaText(activeCandidates, selected.rank, candidate)) + "</p>",
      "<p>变化参考：" + escapeHtml(pvText) + "</p>",
      "</div>"
    ].join("");
  }

  function renderCandidateChoiceList(activeCandidates) {
    var activeContext = getActiveContext(analysisData);
    var winrateLabel = winrateLabelForColor(activeContext && activeContext.winrateOwnerColor);

    if (!activeCandidates.length) {
      return "<div>暂无候选点。</div>";
    }

    return [
      "<div class=\"candidate-choice-list\">",
      activeCandidates.map(function (candidate, index) {
        var rank = index + 1;
        var isActive = rank === selectedCandidateRank;

        return [
          "<button type=\"button\" class=\"candidate-choice-button" + (isActive ? " active" : "") + "\" data-candidate-rank=\"" + rank + "\">",
          "<span class=\"candidate-choice-rank\">" + escapeHtml(candidateRankLabel(rank)) + "</span>",
          "<strong>" + escapeHtml(formatCoord(candidate.move)) + "</strong>",
          "<span class=\"candidate-choice-meta\">" + escapeHtml(winrateLabel) + "约" +
            escapeHtml(typeof candidate.winrate === "number" ? (candidate.winrate * 100).toFixed(1) : "暂无") +
            "%，目差约" +
            escapeHtml(typeof candidate.score_estimate === "number" ? String(Math.round(candidate.score_estimate * 10) / 10) : "暂无") +
            "</span>",
          "</button>"
        ].join("");
      }).join(""),
      "</div>"
    ].join("");
  }

  function hasTrendMetric(timeline, metric) {
    if (!timeline || !timeline.length) return false;

    return timeline.some(function (item) {
      return item && typeof item[metric] === "number";
    });
  }

  function buildTrendSeries(timeline, metric) {
    if (!timeline || !timeline.length) return [];

    return timeline
      .map(function (item) {
        if (!item || typeof item.move_number !== "number" || typeof item[metric] !== "number") {
          return null;
        }

        return {
          moveNumber: item.move_number,
          value: item[metric]
        };
      })
      .filter(Boolean);
  }

  function formatTrendValue(metric, value) {
    if (metric === "winrate") {
      return (value * 100).toFixed(1) + "%";
    }

    var rounded = Math.round(value * 10) / 10;
    return String(rounded);
  }

  function perspectiveWinrate(item, perspectiveColor) {
    if (item && typeof item.winrate_black_after === "number") {
      return perspectiveColor === "B" ? item.winrate_black_after : 1 - item.winrate_black_after;
    }
    if (!item || typeof item.winrate_after !== "number") return null;
    if (item.color === perspectiveColor) return item.winrate_after;
    return 1 - item.winrate_after;
  }

  function winrateLabelForColor(color) {
    return color === "W" ? "白棋胜率" : "黑棋胜率";
  }


  function winrateIndicatorHtml(color) {
    var normalized = color === "W" ? "W" : "B";
    return [
      "<span class=\"winrate-indicator\">",
      "<span class=\"winrate-indicator-dot " + (normalized === "W" ? "white" : "black") + "\" aria-hidden=\"true\"></span>",
      escapeHtml(winrateLabelForColor(normalized)),
      "</span>"
    ].join("");
  }


  function linePath(points) {
    return trendPath(points);
  }

  function renderTrendChart(timeline) {
    var container = document.getElementById("trendChartSection");
    if (!container) return;

    var hasWinrate = hasTrendMetric(timeline, "winrate_after");
    var hasScore = hasTrendMetric(timeline, "score_black_after");
    var activeMetric = chartMetric;
    var series;
    var minValue;
    var maxValue;
    var width;
    var height;
    var padding;
    var points;
    var path;
    var axisLabels;
    var firstPoint;
    var lastPoint;
    var selectedMoveNumber = getViewedMoveNumber();
    var winratePerspectiveColor = "B";
    var winrateTitle = winrateLabelForColor(winratePerspectiveColor);

    if (!hasWinrate && !hasScore) {
      container.innerHTML = "<div>暂无可绘制的走势数据。</div>";
      return;
    }

    if (activeMetric === "winrate" && !hasWinrate) activeMetric = "score";
    if (activeMetric === "score" && !hasScore) activeMetric = "winrate";
    chartMetric = activeMetric;

    series = activeMetric === "winrate"
      ? timeline
          .map(function (item) {
            var value = perspectiveWinrate(item, winratePerspectiveColor);

            if (!item || typeof item.move_number !== "number" || typeof value !== "number") {
              return null;
            }

            return {
              moveNumber: item.move_number,
              value: value
            };
          })
          .filter(Boolean)
      : buildTrendSeries(timeline, "score_black_after");
    if (!series.length) {
      container.innerHTML = "<div>暂无可绘制的走势数据。</div>";
      return;
    }

    minValue = series[0].value;
    maxValue = series[0].value;
    for (var i = 1; i < series.length; i++) {
      minValue = Math.min(minValue, series[i].value);
      maxValue = Math.max(maxValue, series[i].value);
    }

    if (minValue === maxValue) {
      minValue -= activeMetric === "winrate" ? 0.02 : 1;
      maxValue += activeMetric === "winrate" ? 0.02 : 1;
    }

    width = 300;
    height = 160;
    padding = { top: 12, right: 12, bottom: 28, left: 36 };
    points = series.map(function (item, index) {
      var x;
      var y;
      var xSpan = Math.max(1, timeline.length - 1);
      var ySpan = maxValue - minValue;

      x = padding.left + ((width - padding.left - padding.right) * (item.moveNumber - 1)) / xSpan;
      y = padding.top + ((height - padding.top - padding.bottom) * (maxValue - item.value)) / ySpan;

      return {
        x: Math.round(x * 10) / 10,
        y: Math.round(y * 10) / 10,
        moveNumber: item.moveNumber,
        value: item.value,
        isSelected: item.moveNumber === selectedMoveNumber
      };
    });
    path = linePath(points);
    axisLabels = [
      formatTrendValue(activeMetric, maxValue),
      formatTrendValue(activeMetric, (minValue + maxValue) / 2),
      formatTrendValue(activeMetric, minValue)
    ];
    firstPoint = points[0];
    lastPoint = points[points.length - 1];

    container.innerHTML = [
      "<div class=\"chart-controls\">",
      hasWinrate ? "<button type=\"button\" data-chart-metric=\"winrate\" class=\"" + (activeMetric === "winrate" ? "active" : "") + "\">胜率</button>" : "",
      hasScore ? "<button type=\"button\" data-chart-metric=\"score\" class=\"" + (activeMetric === "score" ? "active" : "") + "\">目差</button>" : "",
      "</div>",
      "<div class=\"section-title-row\">",
      "<strong>" + escapeHtml(activeMetric === "winrate" ? "胜率走势" : "目差走势") + "</strong>",
      (activeMetric === "winrate" ? winrateIndicatorHtml(winratePerspectiveColor) : ""),
      "</div>",
      "<div class=\"trend-chart\">",
      "<svg viewBox=\"0 0 " + width + " " + height + "\" role=\"img\" aria-label=\"走势折线图\">",
      "<line x1=\"" + padding.left + "\" y1=\"" + padding.top + "\" x2=\"" + padding.left + "\" y2=\"" + (height - padding.bottom) + "\" stroke=\"#999\" stroke-width=\"1\" />",
      "<line x1=\"" + padding.left + "\" y1=\"" + (height - padding.bottom) + "\" x2=\"" + (width - padding.right) + "\" y2=\"" + (height - padding.bottom) + "\" stroke=\"#999\" stroke-width=\"1\" />",
      "<line x1=\"" + padding.left + "\" y1=\"" + (padding.top + (height - padding.top - padding.bottom) / 2) + "\" x2=\"" + (width - padding.right) + "\" y2=\"" + (padding.top + (height - padding.top - padding.bottom) / 2) + "\" stroke=\"#ddd\" stroke-width=\"1\" />",
      "<path d=\"" + path + "\" fill=\"none\" stroke=\"#2f6db3\" stroke-width=\"2\" />",
      points.map(function (point) {
        return [
          "<circle",
          " cx=\"" + point.x + "\"",
          " cy=\"" + point.y + "\"",
          " r=\"" + (point.isSelected ? "7" : "5") + "\"",
          " fill=\"" + (point.isSelected ? "#c74b16" : "#ffffff") + "\"",
          " stroke=\"" + (point.isSelected ? "#c74b16" : "#2f6db3") + "\"",
          " stroke-width=\"" + (point.isSelected ? "3" : "2") + "\"",
          " data-chart-move=\"" + point.moveNumber + "\"",
          " tabindex=\"0\"",
          " role=\"button\"",
          " aria-label=\"跳转到第" + point.moveNumber + "手\"",
          " style=\"cursor:pointer\"",
          "><title>第" + point.moveNumber + "手: " + formatTrendValue(activeMetric, point.value) + (point.isSelected ? "（当前选中）" : "") + "</title></circle>"
        ].join("");
      }).join(""),
      "<text x=\"6\" y=\"" + (padding.top + 4) + "\" font-size=\"10\" fill=\"#555\">" + escapeHtml(axisLabels[0]) + "</text>",
      "<text x=\"6\" y=\"" + (padding.top + (height - padding.top - padding.bottom) / 2 + 4) + "\" font-size=\"10\" fill=\"#555\">" + escapeHtml(axisLabels[1]) + "</text>",
      "<text x=\"6\" y=\"" + (height - padding.bottom + 4) + "\" font-size=\"10\" fill=\"#555\">" + escapeHtml(axisLabels[2]) + "</text>",
      "<text x=\"" + firstPoint.x + "\" y=\"" + (height - 8) + "\" text-anchor=\"middle\" font-size=\"10\" fill=\"#555\">第" + firstPoint.moveNumber + "手</text>",
      (lastPoint.moveNumber !== firstPoint.moveNumber
        ? "<text x=\"" + lastPoint.x + "\" y=\"" + (height - 8) + "\" text-anchor=\"middle\" font-size=\"10\" fill=\"#555\">第" + lastPoint.moveNumber + "手</text>"
        : ""),
      "</svg>",
      "</div>",
      "<div class=\"chart-meta\">",
      escapeHtml(activeMetric === "winrate" ? "显示每手实战后的" + winrateTitle + "走势。" : "每手实战后目差（正数为黑棋领先）。"),
      " 共 " + escapeHtml(String(series.length)) + " 个点。",
      typeof selectedMoveNumber === "number" ? " 当前选中第" + escapeHtml(String(selectedMoveNumber)) + "手。" : " 当前显示最新局面。",
      "</div>",
      "<div class=\"chart-note\">缺失评估处断线；目差为引擎估计。</div>"
    ].join("");

    Array.prototype.forEach.call(container.querySelectorAll("[data-chart-metric]"), function (button) {
      button.addEventListener("click", function () {
        chartMetric = this.getAttribute("data-chart-metric");
        renderTrendChart(timeline);
      });
    });

    Array.prototype.forEach.call(container.querySelectorAll("[data-chart-move]"), function (pointButton) {
      function activatePoint() {
        activateTimelineMove(Number(pointButton.getAttribute("data-chart-move")));
      }

      pointButton.addEventListener("click", activatePoint);
      pointButton.addEventListener("keydown", function (event) {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          activatePoint();
        }
      });
    });
  }

  function renderAnalysisSummary(data) {
    if (!data || data.schema_version !== "3.0") {
      renderErrorState("报告版本不兼容，请更新后端后重新分析。");
      return;
    }
    var active = getActiveContext(data);
    var candidates = getActiveCandidates(data);
    var timeline = data.timeline;
    var detail = active && active.kind !== "current_position"
      ? findTimelineItem(data, active.moveNumber) : data.current_position;
    ensureSelectedCandidate(data);
    var overview = renderReportOverview(data);
    var empty = data.status === "partial" ? "可用证据中暂无明显失误；不能据此判断整盘无失误。" : "当前阈值下未发现明显失误。";
    var top = '<section class="analysis-section"><h3>重点失误</h3>' +
      renderReviewTargetList(reviewTargets, empty) + '</section>';
    var position = '<section class="analysis-section"><h3>' +
      escapeHtml(active && active.kind !== "current_position" ? moveRefLabel(active.color, active.moveNumber) + " · 落子前" : "记录末尾局面") +
      '</h3><p>' + escapeHtml(active ? active.summary : "证据不可用。") + '</p>' +
      '<p>' + (active && active.kind !== "current_position" ? '实战：' + escapeHtml(formatCoord(active.playedMove)) + '；' : '') +
      '推荐：' + escapeHtml(formatCoord(active && active.recommendedMove)) + '</p>' +
      renderQualityNotes(detail) + '</section>' +
      '<section class="analysis-section"><div class="section-title-row"><h3>候选点</h3>' +
      winrateIndicatorHtml(active && active.winrateOwnerColor) + '</div>' +
      renderCandidateChoiceList(candidates) + buildCandidateExplanation(data) + '</section>';
    var trend = '<section class="analysis-section"><h3>黑棋评估走势</h3><div id="trendChartSection"></div></section>';
    summary.innerHTML = overview + (analysisView === "review"
      ? top + renderMistakeMarkers(data) + position + trend
      : position + top + renderMistakeMarkers(data) + trend);
    renderTrendChart(timeline);
    Array.prototype.forEach.call(summary.querySelectorAll("[data-review-id]"), function (button) {
      button.addEventListener("click", function () {
        activateReviewTargetById(this.getAttribute("data-review-id"));
        revealBoardOnMobile();
      });
    });
    Array.prototype.forEach.call(summary.querySelectorAll("[data-review-move]"), function (button) {
      button.addEventListener("click", function () {
        activateTimelineMove(Number(this.getAttribute("data-review-move")));
        revealBoardOnMobile();
      });
    });
    Array.prototype.forEach.call(summary.querySelectorAll("[data-candidate-rank]"), function (button) {
      button.addEventListener("click", function () {
        selectedCandidateRank = Number(this.getAttribute("data-candidate-rank")) || 1;
        if (selectedCandidateRank > 1) showCandidates.checked = true;
        drawBoard();
        renderAnalysisSummary(data);
      });
    });
  }

  function revealBoardOnMobile() {
    if (window.matchMedia("(max-width: 900px)").matches) {
      document.querySelector(".board-column").scrollIntoView({ block: "start" });
    }
  }


  function trySelectCandidateAtPoint(point) {
    for (var i = 0; i < visibleMarkers.length; i++) {
      if (visibleMarkers[i].rank && visibleMarkers[i].x === point.x && visibleMarkers[i].y === point.y) {
        selectedCandidateRank = visibleMarkers[i].rank;
        drawBoard();
        renderAnalysisSummary(analysisData);
        return true;
      }
    }

    return false;
  }


  function updatePointSummary() {
    var active = getActiveContext(analysisData);
    var selected = visibleMarkers.find(function (marker) { return marker.selected; });
    var descriptions = visibleMarkers.filter(function (marker) {
      return marker.played || marker.recommended || marker === selected;
    }).map(markerDescription);
    if (active && !extractCoordPoint(active.recommendedMove)) {
      descriptions.push("推荐 " + formatCoord(active.recommendedMove));
    }
    if (active && active.kind !== "current_position" && !extractCoordPoint(active.playedMove)) {
      descriptions.push("实战 " + formatCoord(active.playedMove));
    }
    pointSummary.textContent = descriptions.join("  /  ");
    canvas.setAttribute("aria-label", "围棋棋盘" + (descriptions.length ? "：" + descriptions.join("；") : ""));
  }


  function drawBoard() {
    const input = getInput();
    const active = getActiveContext(analysisData);
    const reviewing = active && active.kind !== "current_position";
    const count = reviewing ? active.moveNumber - 1 : input.game.moves.length;
    const detail = reviewing ? findTimelineItem(analysisData, active.moveNumber) : null;
    visibleMarkers = buildBoardMarkers({
      candidates: candidateMarkers, played: reviewing ? extractCoordPoint(active.playedMove) : null,
      recommended: extractCoordPoint(active?.recommendedMove), isMistake: detail?.is_mistake === true,
      selectedRank: selectedCandidateRank, showCandidates: showCandidates.checked
    });
    board.draw({ position: input.positions[count], moveCount: count,
      markers: visibleMarkers, showNumbers: showMoveNumbers.checked });
    updatePointSummary();
  }
  function refresh() {
    moves = getInput().game.moves;
    currentColor = getInput().positions.at(-1).next_player;
    drawBoard();
    updateStatus();
    updateReviewNavigationControls();
  }
  showCandidates.addEventListener("change", () => {
    if (!showCandidates.checked) selectedCandidateRank = 1;
    drawBoard();
    if (analysisData) renderAnalysisSummary(analysisData);
  });
  showMoveNumbers.addEventListener("change", drawBoard);
  canvas.addEventListener("mousemove", (event) => {
    const point = board.pointAt(event);
    const marker = point && visibleMarkers.find((m) => m.x === point.x && m.y === point.y);
    canvas.title = marker ? markerDescription(marker) : "";
  });
  latestBtn.addEventListener("click", returnToLatestBoardState);
  prevReviewBtn.addEventListener("click", () => stepReviewPosition(-1));
  nextReviewBtn.addEventListener("click", () => stepReviewPosition(1));
  analysisViewSwitch.querySelectorAll("[data-analysis-view]").forEach((button) => {
    button.addEventListener("click", () => setAnalysisView(button.dataset.analysisView));
  });
  document.addEventListener("keydown", (event) => {
    if (isBusy || shouldIgnoreReviewKeydown(event) || !analysisData) return;
    if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
      event.preventDefault();
      stepReviewPosition(event.key === "ArrowLeft" ? -1 : 1);
    }
  });
  refresh();
  syncAnalysisViewButtons();
  return {
    refresh,
    clear: () => { clearAnalysisState(); refresh(); },
    setReport: applyAnalysisResult,
    setBusy: (value) => { isBusy = value; updateReviewNavigationControls(); },
    get hasReport() { return Boolean(analysisData); },
    pointAt: board.pointAt,
    selectCandidate: (point) => analysisData && trySelectCandidateAtPoint(point)
  };
}
