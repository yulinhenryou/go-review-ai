// One visual per intersection: engine candidates never obscure the played move.
export function buildBoardMarkers({ candidates = [], played = null, recommended = null,
  isMistake = false, selectedRank = 1, showCandidates = true } = {}) {
  const points = new Map();
  const valid = point => point && Number.isInteger(point.x) && Number.isInteger(point.y)
    && point.x >= 0 && point.x < 19 && point.y >= 0 && point.y < 19;
  const get = point => {
    if (!valid(point)) return null;
    const key = point.x + "," + point.y;
    if (!points.has(key)) points.set(key, { x: point.x, y: point.y, rank: null });
    return points.get(key);
  };
  for (const candidate of candidates) {
    const point = get(candidate);
    if (point && point.rank === null) point.rank = candidate.rank;
  }
  const best = get(recommended);
  if (best) best.recommended = true;
  const actual = get(played);
  if (actual) actual.played = true;
  return [...points.values()].filter(point => showCandidates || point.recommended || point.played)
    .map(point => ({
      ...point,
      kind: point.played && point.recommended ? "combined"
        : point.played ? (isMistake ? "mistake" : "played")
          : point.recommended ? "recommended" : "candidate",
      selected: point.rank === selectedRank,
      label: point.played && point.recommended ? "="
        : point.played ? (isMistake ? "!" : "实") : String(point.rank || 1),
    }));
}

export function pointLabel(point) {
  return "ABCDEFGHJKLMNOPQRST"[point.x] + (19 - point.y);
}

export function markerDescription(marker) {
  const names = { combined: "实战与推荐重合", played: "实战", mistake: "失误",
    recommended: "推荐", candidate: "候选" };
  return names[marker.kind] + " " + pointLabel(marker)
    + (marker.rank ? " · 候选 " + marker.rank : "");
}
