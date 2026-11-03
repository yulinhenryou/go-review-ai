import test from "node:test";
import assert from "node:assert/strict";
import { createApi, ApiError, validateApiBase } from "../../frontend/api.mjs";
import { createInputState, gamePayload } from "../../frontend/input-state.mjs";
import { createJobClient } from "../../frontend/job-client.mjs";

const deferred = () => { let resolve, reject; const promise = new Promise((a, b) => { resolve = a; reject = b; }); return { promise, resolve, reject }; };
const preview = (moves = [{ color: "B", sgf: "aa" }]) => ({ game: {
  board_size: 19, rules: "chinese", komi: 7.5, players: null, result: null, moves
}, warnings: [], positions: Array.from({ length: moves.length + 1 }, (_, i) => ({ next_player: i % 2 ? "W" : "B", stones: [] })) });
const success = (id = "one") => ({ id, state: "succeeded", result: { game: id } });
function harness(api) {
  const states = [], results = [], errors = [], saved = [], inputs = [];
  const client = createJobClient({ api, interval: 0, onState: (v) => states.push(v),
    onResult: (v) => results.push(v), onError: (e, retry) => errors.push({ e, retry }),
    onInput: (v) => inputs.push(v), save: (v) => saved.push(v) });
  return { client, states, results, errors, saved, inputs };
}

test("API defaults to same origin and only accepts explicit remote HTTPS origins", () => {
  assert.equal(validateApiBase(""), "");
  assert.equal(validateApiBase("https://api.example.org/"), "https://api.example.org");
  for (const url of ["http://api.example.org", "https://user@api.example.org", "https://api.example.org/path", "https://api.example.org?key=x", "https://*"]) {
    assert.throws(() => validateApiBase(url));
  }
});

test("API sends canonical JSON without credentials and parses structured queue errors", async () => {
  const calls = [];
  const api = createApi({ fetcher: async (url, options) => {
    calls.push({ url, options });
    return { ok: false, status: 429, json: async () => ({ error: { code: "queue_full" } }) };
  } });
  await assert.rejects(api.submit({ moves: [] }), (e) => e.code === "queue_full" && e.message.includes("队列已满"));
  assert.equal(calls[0].url, "/api/v1/jobs");
  assert.equal(calls[0].options.credentials, "omit");
  assert.equal(calls[0].options.body, '{"moves":[]}');
});

test("API handles non-JSON, offline and request timeouts", async () => {
  const invalid = createApi({ fetcher: async () => ({ json: async () => { throw Error(); }, status: 502 }) });
  await assert.rejects(invalid.get("x"), (e) => e.code === "invalid_response");
  const offline = createApi({ fetcher: async () => { throw Error("offline"); } });
  await assert.rejects(offline.get("x"), (e) => e.code === "network_error");
  const timeout = createApi({ timeout: 1, fetcher: (_url, { signal }) => new Promise((_resolve, reject) => {
    signal.addEventListener("abort", () => reject(Error("aborted")));
  }) });
  await assert.rejects(timeout.get("x"), (e) => e.code === "network_error");
});

test("manual pass and undo use accepted server positions without client rules", async () => {
  const sent = [];
  const input = createInputState(async (game) => { sent.push(game); return preview(game.moves); });
  await input.place("aa", { rules: "chinese", komi: 7.5 });
  await input.place(null, { rules: "chinese", komi: 7.5 });
  assert.deepEqual(sent[1].moves, [{ color: "B", sgf: "aa" }, { color: "W", sgf: null }]);
  input.undo();
  assert.equal(input.get().positions.length, 2);
  assert.equal(input.get().positions.at(-1).next_player, "W");
  input.clear();
  assert.equal(input.get().game.moves.length, 0);
});

test("invalid manual placement preserves the last accepted board", async () => {
  const input = createInputState(async () => { throw new ApiError("ko_violation", "ko"); });
  input.replace(preview());
  const before = structuredClone(input.get());
  await assert.rejects(input.place("aa", {}));
  assert.deepEqual(input.get(), before);
});

test("clear or a new upload invalidates an in-flight manual validation", async () => {
  const request = deferred();
  const input = createInputState(() => request.promise);
  const pending = input.place("aa", {});
  input.clear();
  request.resolve(preview());
  assert.equal(await pending, false);
  assert.equal(input.get().game.moves.length, 0);
});

test("canonical payload excludes preview-only fields and is a stable copy", () => {
  const game = { ...preview().game, record_status: "unfinished_or_unknown" };
  const payload = gamePayload(game);
  game.moves[0].sgf = "bb";
  assert.equal(payload.moves[0].sgf, "aa");
  assert.equal(payload.record_status, undefined);
});

test("job polling exposes actual progress and completes once", async () => {
  const h = harness({ submit: async () => ({ id: "one", state: "running", progress: { completed: 0, total: 2 } }),
    get: async () => success(), cancel: async () => {} });
  await h.client.submit({ moves: [] });
  assert.deepEqual(h.states.map((s) => s.state), ["submitting", "running", "succeeded"]);
  assert.deepEqual(h.results, [{ game: "one" }]);
  assert.equal(h.client.id, null);
  assert.equal(h.saved.at(-1), "one");
});

test("late submission is cancelled and cannot overwrite a newer input", async () => {
  const pending = deferred(), cancelled = [];
  const h = harness({ submit: () => pending.promise, cancel: async (id) => cancelled.push(id) });
  const running = h.client.submit({ moves: [] });
  h.client.abandon();
  pending.resolve(success("old"));
  await running;
  assert.deepEqual(cancelled, ["old"]);
  assert.deepEqual(h.results, []);
});

test("late result from an abandoned job is discarded", async () => {
  const response = deferred(), started = deferred();
  const h = harness({ submit: async () => ({ id: "one", state: "running" }),
    get: () => { started.resolve(); return response.promise; }, cancel: async () => {} });
  const pending = h.client.submit({ moves: [] });
  await started.promise;
  h.client.abandon();
  response.resolve(success());
  await pending;
  assert.deepEqual(h.results, []);
});

test("network failure retains job ID and resume restores its input before result", async () => {
  let offline = true;
  const h = harness({ submit: async () => ({ id: "one", state: "running" }),
    get: async () => { if (offline) throw new ApiError("network_error", "offline"); return success(); },
    input: async () => preview(), cancel: async () => {} });
  await h.client.submit({ moves: [] });
  assert.equal(h.client.id, "one");
  assert.equal(h.errors[0].retry, true);
  offline = false;
  await h.client.resume("one");
  assert.equal(h.inputs.length, 1);
  assert.equal(h.results.length, 1);
});

test("expired or restarted jobs clear the remembered ID", async () => {
  const h = harness({ input: async () => { throw new ApiError("job_unavailable", "expired"); } });
  await h.client.resume("old");
  assert.equal(h.client.id, null);
  assert.equal(h.saved.at(-1), null);
  assert.equal(h.errors[0].retry, false);
});

test("cancel after a failed poll still reaches terminal state and releases UI lock", async () => {
  const h = harness({ submit: async () => ({ id: "one", state: "running" }),
    get: async () => { throw new ApiError("network_error", "offline"); },
    cancel: async () => ({ id: "one", state: "cancelled" }) });
  await h.client.submit({ moves: [] });
  await h.client.cancel();
  assert.equal(h.client.id, null);
  assert.equal(h.states.at(-1).state, "cancelled");
});

test("failed or partial results never become fabricated complete reports", async () => {
  const failed = harness({ submit: async () => ({ id: "one", state: "failed", error: { code: "engine_unavailable" } }) });
  await failed.client.submit({});
  assert.equal(failed.results.length, 0);
  assert.equal(failed.errors[0].e.code, "engine_unavailable");
  const partial = { status: "partial", timeline: [{ score_loss: null }] };
  const h = harness({ submit: async () => ({ id: "one", state: "succeeded", result: partial }) });
  await h.client.submit({});
  assert.deepEqual(h.results, [partial]);
});
