export function escapeHtml(value) {
  return String(value).replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

export function renderQualityNotes(item) {
  const notes = item && Array.isArray(item.quality_notes) ? item.quality_notes : [];
  return notes.length ? `<ul class="quality-notes">${notes.map(note => `<li>${escapeHtml(note)}</li>`).join("")}</ul>` : "";
}

export function renderReportOverview(data) {
  const game = data.game_summary;
  const coverage = data.coverage;
  const method = data.method;
  const evidence = data.current_position.evidence;
  const record = game.record_status === "result_recorded"
    ? `记录结果：${game.result}。结果记录不保证着手完整。`
    : "未完或结果未知，仅分析已记录的着手。";
  const missing = coverage.missing_move_numbers.length
    ? `<p>目损证据不足：第 ${escapeHtml(coverage.missing_move_numbers.join("、"))} 手。</p>` : "";
  const missingWinrate = coverage.missing_winrate_move_numbers.length
    ? `<p>胜率变化不可用：第 ${escapeHtml(coverage.missing_winrate_move_numbers.join("、"))} 手。</p>` : "";
  const provenance = evidence && data.engine_source === "katago"
    ? `<p>KataGo ${escapeHtml(evidence.engine_version)} · ${escapeHtml(evidence.model_id)} · maxVisits ${escapeHtml(evidence.max_visits)}</p>
       <details><summary>引擎标识</summary><p>模型 SHA-256：${escapeHtml(evidence.model_sha256)}</p><p>配置 SHA-256：${escapeHtml(evidence.config_sha256)}</p></details>`
    : "<p>非真实引擎结果，仅用于测试。</p>";
  return `<section class="analysis-section report-overview" aria-label="对局简报">
    <h2>对局简报${data.status === "partial" ? " · 不完整" : ""}</h2>
    <p>${escapeHtml(game.players.black)}（黑） / ${escapeHtml(game.players.white)}（白）</p>
    <p>${game.board_size}x${game.board_size} · ${game.rules === "chinese" ? "中国规则" : "日韩规则"} · 贴目 ${escapeHtml(game.komi)}</p>
    <p>${escapeHtml(record)}</p>
    ${(game.input_warnings || []).includes("first_variation_only") ? "<p>棋谱包含变化分支，本次仅分析第一条主线。</p>" : ""}
    <p class="report-status" role="status">${escapeHtml(data.summary)}</p>
    <p>目损覆盖 ${coverage.moves_evaluated}/${coverage.moves_total} 手；胜率变化覆盖 ${coverage.moves_with_winrate}/${coverage.moves_total} 手。</p>
    ${missing}${missingWinrate}${coverage.current_position_evaluated ? "" : "<p>记录末尾局面评估不完整。</p>"}
    ${renderQualityNotes(data)}
    <details><summary>评估依据与引擎信息</summary>
      <p>明显失误 ≥ ${escapeHtml(method.loss_threshold)} 目；严重失误 ≥ ${escapeHtml(method.severe_threshold)} 目；摘要最多 ${method.top_limit} 手。</p>
      <p>${escapeHtml(method.note)}</p>${provenance}
    </details>
  </section>`;
}

export function renderMistakeMarkers(data) {
  const items = data.timeline.filter(item => item.is_mistake || item.is_mistake === null);
  const empty = data.status === "partial" ? "可用证据中暂无明显失误；报告不完整。" : "当前阈值下未发现明显失误。";
  return `<section class="analysis-section"><h3>逐手标记</h3>${items.length
    ? `<div class="mistake-markers">${items.map(item => `<button type="button" data-review-move="${item.move_number}" class="mistake-marker ${item.is_mistake === null ? "unavailable" : item.severity}">第 ${item.move_number} 手 · ${escapeHtml(item.severity_label || "未评估")}</button>`).join("")}</div>`
    : `<p>${empty}</p>`}</section>`;
}

export function trendPath(points) {
  return points.map((point, index) => `${index && point.moveNumber === points[index - 1].moveNumber + 1 ? "L" : "M"}${point.x} ${point.y}`).join(" ");
}
