import test from "node:test";
import assert from "node:assert/strict";
import { buildBoardMarkers, markerDescription, pointLabel } from "../../frontend/board-markers.mjs";

const best = { x: 15, y: 3 };
const played = { x: 0, y: 0 };
const candidates = [{ ...best, rank: 1 }, { x: 3, y: 3, rank: 2 }, { x: 15, y: 15, rank: 3 }];

test("mistake, recommendation and other candidates have distinct semantics", () => {
  const result = buildBoardMarkers({ candidates, played, recommended: best, isMistake: true });
  assert.deepEqual(result.map(m => m.kind), ["recommended", "candidate", "candidate", "mistake"]);
  assert.deepEqual(result.map(m => m.label), ["1", "2", "3", "!"]);
  assert.equal(result.filter(m => m.selected).length, 1);
  assert.equal(markerDescription(result[3]), "失误 A19");
});

test("actual equals best produces one combined marker, never stacked symbols", () => {
  const result = buildBoardMarkers({ candidates, played: best, recommended: best });
  assert.equal(result.length, 3);
  assert.equal(result[0].kind, "combined");
  assert.equal(result[0].label, "=");
  assert.ok(markerDescription(result[0]).includes("实战与推荐重合"));
});

test("actual equals another candidate keeps the actual marker and selectable rank", () => {
  const result = buildBoardMarkers({ candidates, played: candidates[1], recommended: best, isMistake: true, selectedRank: 2 });
  assert.equal(result.length, 3);
  assert.equal(result[1].kind, "mistake");
  assert.equal(result[1].rank, 2);
  assert.equal(result[1].selected, true);
  assert.ok(markerDescription(result[1]).includes("候选 2"));
});

test("a played move below threshold or without evidence is not marked as a mistake", () => {
  for (const isMistake of [false, null, undefined]) {
    const result = buildBoardMarkers({ played, isMistake });
    assert.equal(result[0].kind, "played");
    assert.equal(result[0].label, "实");
  }
});

test("hiding candidates retains recommendation and played evidence", () => {
  const result = buildBoardMarkers({ candidates, played, recommended: best, showCandidates: false });
  assert.deepEqual(result.map(m => m.kind), ["recommended", "played"]);
  assert.equal(buildBoardMarkers({ candidates, showCandidates: false }).length, 0);
});

test("pass or unavailable points do not create a phantom intersection", () => {
  assert.deepEqual(buildBoardMarkers({ played: null, recommended: null }), []);
  assert.deepEqual(buildBoardMarkers({ played: {x:-1,y:2}, recommended: {x:19,y:0} }), []);
});

test("ranks survive a passing candidate and duplicate points collapse", () => {
  const result = buildBoardMarkers({ candidates: [{...best,rank:2}, {...best,rank:3}], recommended:best, selectedRank:2 });
  assert.equal(result.length, 1);
  assert.equal(result[0].rank, 2);
  assert.equal(result[0].label, "2");
  assert.equal(result[0].selected, true);
});

test("board coordinates skip I and reverse row numbering", () => {
  assert.equal(pointLabel({x:0,y:0}), "A19");
  assert.equal(pointLabel({x:8,y:18}), "J1");
  assert.equal(pointLabel({x:18,y:18}), "T1");
});

test("the supplied recommendation, not an assumed candidate rank, defines the green marker", () => {
  const result = buildBoardMarkers({ candidates, recommended:candidates[1] });
  assert.equal(result[0].kind, "candidate");
  assert.equal(result[1].kind, "recommended");
});
