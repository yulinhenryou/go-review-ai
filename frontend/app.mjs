import { createApi } from "./api.mjs";
import { createGameSettings } from "./game-settings.mjs";
import { createInputState, gamePayload } from "./input-state.mjs";
import { createJobClient } from "./job-client.mjs";
import { createReviewController } from "./review-controller.mjs";
import { toSgf } from "./coordinates.mjs";

const byId = (id) => document.getElementById(id);
const fields = { rulesInput: byId("rulesInput"), komiInput: byId("komiInput"),
  customRulesInput: byId("customRulesInput"), customRulesLabel: byId("customRulesLabel") };
const settings = createGameSettings(fields);
let api;
try { api = createApi({ base: document.querySelector('meta[name="api-base"]').content }); }
catch (error) { byId("uploadStatus").textContent = error.message; throw error; }
const input = createInputState(api.replay);
const review = createReviewController(input.get);
let preview = false, working = false, validating = false, action = 0;
const storageKey = "go-review-job:" + (document.querySelector('meta[name="api-base"]').content || location.origin);
const storeJob = (id) => {
  try { if (id) sessionStorage.setItem(storageKey, id); else sessionStorage.removeItem(storageKey); } catch {}
};
const jobs = createJobClient({ api, save: storeJob,
  onState: showJob,
  onInput: (data) => {
    input.replace(data, "restored");
    settings.apply(data.game);
    byId("blackPlayer").value = data.game.players?.black || "";
    byId("whitePlayer").value = data.game.players?.white || "";
    review.clear();
  },
  onResult: (data) => { working = false; review.setReport(data); controls(); },
  onError: (error, canResume) => {
    working = false;
    byId("jobPanel").hidden = false;
    byId("jobStatus").textContent = error.message;
    byId("jobStatus").classList.add("error-message");
    byId("cancelJobBtn").hidden = !canResume;
    byId("retryJobBtn").hidden = !canResume && input.get().game.moves.length === 0;
    byId("retryJobBtn").textContent = canResume ? "重新连接" : "重新提交";
    controls();
  }
});

function message(text = "", error = false) {
  byId("uploadStatus").textContent = text;
  byId("uploadStatus").classList.toggle("error-message", error);
}

function controls() {
  const locked = working || Boolean(jobs.id) || review.hasReport;
  const imported = preview && input.get().source === "sgf";
  const game = input.get().game;
  fields.rulesInput.disabled = locked || imported && game.rules !== null;
  fields.customRulesInput.disabled = fields.rulesInput.disabled || fields.rulesInput.value !== "custom";
  fields.komiInput.disabled = locked || imported && game.komi !== null;
  // A recorded komi is immutable even when choosing a missing rule changes the preset.
  if (imported && game.komi !== null) fields.komiInput.value = String(game.komi);
  byId("passBtn").disabled = validating || locked || preview;
  byId("undoBtn").disabled = validating || locked || !game.moves.length;
  byId("analyzeBtn").disabled = validating || locked || preview || !game.moves.length;
  byId("confirmBtn").disabled = validating || locked;
  byId("editBtn").hidden = !(locked || preview);
  byId("inputPreview").hidden = !preview;
  byId("analysisViewSwitch").hidden = !review.hasReport;
  document.querySelector(".raw-data").hidden = !review.hasReport;
  byId("analysisSummary").hidden = !review.hasReport && (preview || working || !byId("jobPanel").hidden);
  review.setBusy(working || validating);
}

function invalidate() {
  action++;
  input.invalidate();
  jobs.abandon();
  working = false;
  validating = false;
  preview = false;
  byId("jobPanel").hidden = true;
  review.clear();
  message();
  return action;
}

function showPreview() {
  preview = true;
  const { game: recorded, warnings, source } = input.get();
  const game = { ...recorded };
  try {
    const chosen = settings.read(false);
    if (source === "sgf") { game.rules ??= chosen.rules; game.komi ??= chosen.komi; }
    else Object.assign(game, chosen);
  } catch {}
  byId("playerFields").hidden = source !== "manual";
  const values = [["棋谱", `${game.moves.length} 手 / 19 路`],
    ["黑方", game.players?.black || "未记录"], ["白方", game.players?.white || "未记录"],
    ["规则", game.rules === "chinese" ? "中国规则" : game.rules === "japanese" ? "日韩规则" : "待补全"],
    ["贴目", game.komi === null ? "待补全" : `${game.komi} 目`],
    ["结果记录", game.result || "未记录，棋局可能尚未结束"]];
  byId("previewDetails").replaceChildren(...values.flatMap(([label, value]) => {
    const dt = document.createElement("dt"), dd = document.createElement("dd");
    dt.textContent = label; dd.textContent = value;
    return [dt, dd];
  }));
  byId("previewWarnings").textContent = warnings.includes("first_variation_only")
    ? "此棋谱含变化分支，本次仅分析第一条主线。" : "";
  controls();
}

function showJob(job) {
  working = ["submitting", "reconnecting", "queued", "running"].includes(job.state);
  byId("jobPanel").hidden = false;
  byId("jobStatus").classList.remove("error-message");
  const { completed = 0, total = 0 } = job.progress || {};
  const labels = {
    submitting: "正在提交棋谱", reconnecting: "正在恢复任务",
    queued: `排队中 · 第 ${job.queue_position} 位`,
    running: job.cancel_requested ? "正在取消并释放引擎" : `分析中 · 已完成 ${completed} / ${total} 个局面`,
    succeeded: `分析完成 · ${completed} / ${total} 个局面`, failed: "分析失败", cancelled: "分析已取消"
  };
  byId("jobStatus").textContent = labels[job.state];
  byId("jobProgress").max = total || 1;
  byId("jobProgress").value = completed;
  byId("jobProgress").hidden = !total || job.state === "cancelled";
  byId("cancelJobBtn").hidden = !working;
  byId("cancelJobBtn").disabled = Boolean(job.cancel_requested);
  byId("retryJobBtn").hidden = job.state !== "cancelled";
  byId("retryJobBtn").textContent = "重新提交";
  controls();
}

async function place(sgf) {
  if (validating || working || jobs.id || review.hasReport || preview) return;
  const token = ++action;
  validating = true;
  controls();
  try {
    const accepted = await input.place(sgf, settings.read(false));
    if (token !== action || !accepted) return;
    review.clear();
    message(sgf === null ? "已记录停一手。" : "");
  } catch (error) { if (token === action) message(error.message, true); }
  finally { if (token === action) { validating = false; controls(); } }
}

byId("boardCanvas").addEventListener("click", (event) => {
  const point = review.pointAt(event);
  if (!point || review.selectCandidate(point)) return;
  void place(toSgf(point.x, point.y));
});
byId("passBtn").addEventListener("click", () => void place(null));
byId("clearBtn").addEventListener("click", () => {
  invalidate(); input.clear(); byId("sgfFileInput").value = "";
  byId("blackPlayer").value = ""; byId("whitePlayer").value = "";
  review.refresh(); controls();
});
byId("undoBtn").addEventListener("click", () => {
  invalidate(); input.undo(); review.refresh(); controls();
});
function edit() {
  invalidate();
  const state = input.get();
  byId("blackPlayer").value = state.game.players?.black || "";
  byId("whitePlayer").value = state.game.players?.white || "";
  input.replace({ ...state, warnings: [], game: { ...state.game, result: null } });
  controls();
}
byId("editBtn").addEventListener("click", edit);
byId("backToInputBtn").addEventListener("click", edit);
byId("analyzeBtn").addEventListener("click", () => {
  byId("jobPanel").hidden = true;
  const state = input.get();
  try {
    input.replace({ ...state, game: { ...state.game, ...settings.read(false) } });
    showPreview();
    byId("inputPreview").scrollIntoView({ block: "nearest" });
  } catch (error) { message(error.message, true); }
});
byId("uploadAnalyzeBtn").addEventListener("click", async () => {
  const file = byId("sgfFileInput").files[0];
  if (!file) { message("请选择一个 SGF 文件。", true); return; }
  if (file.size > 1024 * 1024) { message("棋谱文件不能超过 1 MiB。", true); return; }
  const token = invalidate();
  validating = true; controls(); message("正在解析棋谱");
  try {
    const data = await api.parse(file);
    if (token !== action) return;
    input.replace(data, "sgf");
    byId("blackPlayer").value = data.game.players?.black || "";
    byId("whitePlayer").value = data.game.players?.white || "";
    if (data.game.rules) settings.apply(data.game);
    else if (data.game.komi !== null) fields.komiInput.value = String(data.game.komi);
    review.refresh(); showPreview();
    message(`已载入 ${file.name}，尚未开始分析。`);
    byId("inputPreview").scrollIntoView({ block: "nearest" });
  } catch (error) { if (token === action) message(error.message, true); }
  finally { if (token === action) { validating = false; controls(); } }
});
byId("confirmBtn").addEventListener("click", () => {
  try {
    const state = input.get(), chosen = settings.read(false);
    const game = gamePayload(state.game);
    if (state.source === "sgf") {
      game.rules ??= chosen.rules;
      game.komi ??= chosen.komi;
    } else {
      Object.assign(game, chosen);
      game.players = { black: byId("blackPlayer").value.trim() || null, white: byId("whitePlayer").value.trim() || null };
    }
    if (game.rules === null || game.komi === null) throw new Error("请补全规则和贴目后再分析。");
    input.replace({ ...state, game }, state.source);
    settings.apply(game);
    preview = false;
    review.clear(); message();
    void jobs.submit({ ...game, input_warnings: state.warnings || [] });
  } catch (error) { message(error.message, true); }
});
byId("cancelJobBtn").addEventListener("click", () => void jobs.cancel());
byId("retryJobBtn").addEventListener("click", () => {
  if (jobs.id) void jobs.resume(jobs.id);
  else { byId("jobPanel").hidden = true; showPreview(); }
});
for (const element of [fields.rulesInput, fields.customRulesInput, fields.komiInput]) {
  element.addEventListener("change", () => { controls(); if (preview) showPreview(); });
}
controls();
let saved;
try { saved = sessionStorage.getItem(storageKey); } catch {}
if (saved) void jobs.resume(saved);
