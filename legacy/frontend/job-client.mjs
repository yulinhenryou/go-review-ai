import { jobError } from "./api.mjs";

function pause(ms, signal) {
  return new Promise((resolve) => {
    const finish = () => { clearTimeout(timer); signal.removeEventListener("abort", finish); resolve(); };
    const timer = setTimeout(finish, ms);
    signal.addEventListener("abort", finish, { once: true });
    if (signal.aborted) finish();
  });
}

export function createJobClient({ api, onState, onResult, onInput, onError, save = () => {}, interval = 600 }) {
  let version = 0, id = null, controller = new AbortController();
  const current = (token) => token === version;
  function abandon() {
    version++;
    controller.abort();
    controller = new AbortController();
    const previous = id;
    id = null;
    save(null);
    if (previous) void api.cancel(previous).catch(() => {});
    return version;
  }
  function fail(error, token) {
    if (!current(token)) return;
    if (error.code === "job_unavailable") { id = null; save(null); }
    onError(error, Boolean(id));
  }
  async function poll(job, token) {
    try {
      while (current(token)) {
        if (["succeeded", "failed", "cancelled"].includes(job.state)) {
          id = null;
          save(job.state === "succeeded" ? job.id : null);
          onState(job);
          if (job.state === "succeeded") onResult(job.result);
          if (job.state === "failed") onError(jobError(job.error), false);
          return;
        }
        onState(job);
        await pause(interval, controller.signal);
        if (!current(token)) return;
        job = await api.get(id, controller.signal);
      }
    } catch (error) { fail(error, token); }
  }
  return {
    abandon,
    get id() { return id; },
    async submit(payload) {
      const token = abandon();
      onState({ state: "submitting" });
      try {
        const job = await api.submit(structuredClone(payload));
        if (!current(token)) { await api.cancel(job.id).catch(() => {}); return; }
        id = job.id;
        save(id);
        await poll(job, token);
      } catch (error) { fail(error, token); }
    },
    async resume(jobId) {
      controller.abort();
      controller = new AbortController();
      const token = ++version;
      id = jobId;
      save(id);
      onState({ state: "reconnecting" });
      try {
        const input = await api.input(id, controller.signal);
        if (!current(token)) return;
        onInput(input);
        const job = await api.get(id, controller.signal);
        await poll(job, token);
      } catch (error) { fail(error, token); }
    },
    async cancel() {
      if (!id) { abandon(); onState({ state: "cancelled" }); return; }
      const token = version;
      try {
        const job = await api.cancel(id);
        if (current(token)) {
          controller.abort();
          controller = new AbortController();
          await poll(job, ++version);
        }
      } catch (error) { fail(error, token); }
    }
  };
}
