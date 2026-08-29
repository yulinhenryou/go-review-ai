import { BOARD_SIZE, DISPLAY_COLUMNS, fromSgf } from "./coordinates.mjs";

export function createBoardView(boardElement, canvas) {
  const context = canvas.getContext("2d");
  const STAR_POINTS = [3, 9, 15];
  let boardMetrics = null, last = null;
  function syncCanvasSize() {
    var rect = boardElement.getBoundingClientRect();
    var size = Math.floor(rect.width || boardElement.clientWidth || 640);
    var ratio = window.devicePixelRatio || 1;
    canvas.width = size * ratio;
    canvas.height = size * ratio;
    canvas.style.width = size + "px";
    canvas.style.height = size + "px";
    context.setTransform(ratio, 0, 0, ratio, 0, 0);
    boardMetrics = {
      size: size,
      padding: size * 0.075,
      cell: (size - size * 0.15) / (BOARD_SIZE - 1)
    };
    if (last) draw(last);
  }

  function boardPoint(index) {
    return boardMetrics.padding + index * boardMetrics.cell;
  }

  function drawGrid() {
    context.strokeStyle = "#87704a";
    context.lineWidth = 1;

    for (var i = 0; i < BOARD_SIZE; i++) {
      var pos = boardPoint(i);
      var start = boardPoint(0);
      var end = boardPoint(BOARD_SIZE - 1);

      context.beginPath();
      context.moveTo(start, pos);
      context.lineTo(end, pos);
      context.stroke();

      context.beginPath();
      context.moveTo(pos, start);
      context.lineTo(pos, end);
      context.stroke();
    }
  }

  function drawStarPoints() {
    context.fillStyle = "#5d3c1a";

    for (var y = 0; y < STAR_POINTS.length; y++) {
      for (var x = 0; x < STAR_POINTS.length; x++) {
        context.beginPath();
        context.arc(boardPoint(STAR_POINTS[x]), boardPoint(STAR_POINTS[y]), Math.max(3, boardMetrics.cell * 0.1), 0, Math.PI * 2);
        context.fill();
      }
    }
  }

  function drawStone(move, moveNumber, isLatestMove) {
    var x = boardPoint(move.x);
    var y = boardPoint(move.y);
    var radius = boardMetrics.cell * 0.45;
    var gradient = context.createRadialGradient(x - radius * 0.35, y - radius * 0.35, radius * 0.1, x, y, radius);
    var label = String(moveNumber);

    if (move.color === "B") {
      gradient.addColorStop(0, "#666");
      gradient.addColorStop(1, "#111");
    } else {
      gradient.addColorStop(0, "#fff");
      gradient.addColorStop(1, "#d8d8d8");
    }

    context.fillStyle = gradient;
    context.beginPath();
    context.arc(x, y, radius, 0, Math.PI * 2);
    context.fill();
    context.strokeStyle = move.color === "B" ? "#000" : "#999";
    context.stroke();

    if (isLatestMove) {
      context.save();
      context.strokeStyle = move.color === "B" ? "#f5d36b" : "#b85c00";
      context.lineWidth = Math.max(2, boardMetrics.cell * 0.08);
      context.beginPath();
      context.arc(x, y, radius * 0.78, 0, Math.PI * 2);
      context.stroke();

      context.restore();
    }

    if (!last.showNumbers) return;
    context.save();
    context.fillStyle = move.color === "B" ? "#f4f4f4" : "#111";
    context.font = "bold " + Math.max(10, Math.floor(radius * (label.length > 2 ? 0.9 : 1.1))) + "px sans-serif";
    context.textAlign = "center";
    context.textBaseline = "middle";
    context.fillText(label, x, y + 0.5);
    context.restore();
  }

  function drawBoardMarker(marker) {
    var x = boardPoint(marker.x);
    var y = boardPoint(marker.y);
    var radius = boardMetrics.cell * 0.47;
    var isBest = marker.kind === "recommended" || marker.kind === "combined";
    var isPlayed = marker.kind === "played" || marker.kind === "mistake";
    var fill = isBest ? "#087557" : marker.kind === "mistake" ? "#bd3145"
      : isPlayed ? "#414c50" : "#1e63ad";
    context.save();
    context.translate(x, y);
    context.beginPath();
    if (isBest) {
      context.moveTo(0, -radius * 1.1);
      context.lineTo(radius, radius * 0.85);
      context.lineTo(-radius, radius * 0.85);
      context.closePath();
    } else if (isPlayed) {
      context.rect(-radius * 0.88, -radius * 0.88, radius * 1.76, radius * 1.76);
    } else {
      context.arc(0, 0, radius * 0.88, 0, Math.PI * 2);
    }
    context.fillStyle = fill;
    context.fill();
    context.strokeStyle = "#fff";
    context.lineWidth = marker.selected ? 3 : 2;
    context.stroke();
    if (marker.selected) {
      context.strokeStyle = "#172f31";
      context.lineWidth = 1.5;
      context.stroke();
    }
    context.fillStyle = "#fff";
    context.font = "700 " + Math.max(9, Math.floor(boardMetrics.cell * 0.47)) + "px sans-serif";
    context.textAlign = "center";
    context.textBaseline = "middle";
    context.fillText(marker.label, 0, isBest ? radius * 0.23 : 0.5);
    context.restore();
  }

  function drawCoordinates() {
    context.save();
    context.font = Math.max(9, Math.min(12, boardMetrics.cell * 0.36)) + "px sans-serif";
    context.textAlign = "center";
    context.textBaseline = "middle";
    context.fillStyle = "#635134";
    const edge = boardMetrics.padding * 0.38;
    for (let i = 0; i < BOARD_SIZE; i++) {
      context.fillText(DISPLAY_COLUMNS[i], boardPoint(i), edge);
      context.fillText(DISPLAY_COLUMNS[i], boardPoint(i), boardMetrics.size - edge);
      context.fillText(String(BOARD_SIZE - i), edge, boardPoint(i));
      context.fillText(String(BOARD_SIZE - i), boardMetrics.size - edge, boardPoint(i));
    }
    context.restore();
  }

  function clickToPoint(event) {
    var rect = canvas.getBoundingClientRect();
    var x = event.clientX - rect.left;
    var y = event.clientY - rect.top;
    var gridX = Math.round((x - boardMetrics.padding) / boardMetrics.cell);
    var gridY = Math.round((y - boardMetrics.padding) / boardMetrics.cell);

    if (gridX < 0 || gridY < 0 || gridX >= BOARD_SIZE || gridY >= BOARD_SIZE) return null;

    var snappedX = boardPoint(gridX);
    var snappedY = boardPoint(gridY);
    var tolerance = boardMetrics.cell * 0.45;

    if (Math.abs(x - snappedX) > tolerance || Math.abs(y - snappedY) > tolerance) return null;

    return { x: gridX, y: gridY };
  }

  function draw(options) {
    last = options;
    if (!boardMetrics) return;
    const { position, moveCount, markers } = options;
    context.clearRect(0, 0, boardMetrics.size, boardMetrics.size);
    context.fillStyle = "#e7c990";
    context.fillRect(0, 0, boardMetrics.size, boardMetrics.size);
    drawGrid();
    drawStarPoints();
    drawCoordinates();
    for (const stone of position.stones) {
      drawStone({ ...fromSgf(stone.sgf), color: stone.color }, stone.move_number, stone.move_number === moveCount);
    }
    markers.forEach(drawBoardMarker);
  }
  window.addEventListener("resize", syncCanvasSize);
  syncCanvasSize();
  return { draw, pointAt: clickToPoint };
}
