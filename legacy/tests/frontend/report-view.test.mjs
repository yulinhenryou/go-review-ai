import test from "node:test";
import assert from "node:assert/strict";
import { renderReportOverview, renderMistakeMarkers, renderQualityNotes, trendPath } from "../../frontend/report-view.mjs";

function result() {
  return {
    status: "complete", engine_source: "katago", summary: "未发现明显失误。", quality_notes: [],
    game_summary: { board_size: 19, rules: "chinese", komi: 7.5, record_status: "unfinished_or_unknown", players: { black: "A", white: "B" } },
    coverage: { moves_total: 7, moves_evaluated: 7, moves_with_winrate: 7, missing_move_numbers: [], missing_winrate_move_numbers: [], current_position_evaluated: true },
    method: { loss_threshold: 3, severe_threshold: 5, top_limit: 5, note: "搜索估计" },
    current_position: { evidence: { engine_version: "1.16.4", model_id: "test-model", max_visits: 64, model_sha256: "a".repeat(64), config_sha256: "b".repeat(64) } },
    timeline: []
  };
}

test("report overview shows metadata, incomplete record notice, coverage and method", () => {
  const html = renderReportOverview(result());
  for (const text of ["未完或结果未知", "目损覆盖 7/7", "明显失误 ≥ 3", "严重失误 ≥ 5", "maxVisits 64", "模型 SHA-256"]) assert.ok(html.includes(text));
  for (const text of ["主战场", "阶段判断", "训练建议"]) assert.ok(!html.includes(text));
});

test("partial evidence is visible without opening raw JSON", () => {
  const data = result();
  data.status = "partial";
  data.summary = "报告不完整";
  data.coverage.moves_evaluated = 6;
  data.coverage.missing_move_numbers = [3];
  data.coverage.missing_winrate_move_numbers = [4];
  data.coverage.current_position_evaluated = false;
  const html = renderReportOverview(data);
  for (const text of ["对局简报 · 不完整", "目损覆盖 6/7", "目损证据不足：第 3 手", "胜率变化不可用：第 4 手", "记录末尾局面评估不完整"]) assert.ok(html.includes(text));
  assert.ok(renderMistakeMarkers(data).includes("报告不完整"));
});

test("all chronological markers survive beyond the top-five summary", () => {
  const data = result();
  data.timeline = Array.from({ length: 7 }, (_, i) => ({ move_number: i + 1, is_mistake: true, severity: "mistake", severity_label: "明显失误" }));
  data.timeline[2] = { move_number: 3, is_mistake: null };
  const html = renderMistakeMarkers(data);
  assert.equal((html.match(/data-review-move=/g) || []).length, 7);
  assert.ok(html.includes('data-review-move="7"'));
  assert.ok(html.includes("第 3 手 · 未评估"));
});

test("all external strings are escaped including names, result and engine provenance", () => {
  const data = result();
  const attack = '<img src=x onerror="alert(1)">';
  data.game_summary.players.black = attack;
  data.game_summary.record_status = "result_recorded";
  data.game_summary.result = attack;
  data.current_position.evidence.model_id = attack;
  data.quality_notes = [attack];
  const html = renderReportOverview(data);
  assert.ok(!html.includes("<img"));
  assert.ok(html.includes("&lt;img"));
  assert.ok(!renderQualityNotes(data).includes("<img"));
});

test("missing provenance is not called a verified real engine", () => {
  const data = result();
  data.current_position.evidence = null;
  assert.ok(renderReportOverview(data).includes("非真实引擎结果"));
  data.current_position.evidence = result().current_position.evidence;
  data.engine_source = "unverified_test_double";
  assert.ok(renderReportOverview(data).includes("非真实引擎结果"));
});

test("trend paths break at missing move numbers instead of interpolating evidence", () => {
  assert.equal(trendPath([{moveNumber:1,x:0,y:1},{moveNumber:2,x:1,y:2},{moveNumber:4,x:3,y:4}]), "M0 1 L1 2 M3 4");
  assert.equal(trendPath([]), "");
});
