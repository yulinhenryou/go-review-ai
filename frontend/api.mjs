const MESSAGES = {
  queue_full: "分析队列已满，请稍后重试。",
  job_unavailable: "任务已过期或服务已重启，请重新提交棋谱。",
  engine_unavailable: "KataGo 暂不可用，未生成模拟报告。",
  analysis_timeout: "分析超时，请缩短棋谱后重试。",
  analysis_failed: "分析失败，未生成完整报告，请重试。",
  service_stopping: "服务正在关闭，请稍后重试。",
  missing_metadata: "请补全棋谱的规则和贴目。",
  occupied_point: "此处已有棋子。",
  ko_violation: "不能立即回提劫。",
  suicide: "此处为自杀落子，不能落下。",
  unsupported_resumption: "连续两次停一手后，暂不支持继续落子。",
  invalid_move_count: "棋谱须包含 1 至 500 手。",
  invalid_komi: "贴目须为 -150 至 150 之间的整数或半目。",
  invalid_turn: "黑白落子顺序不正确。",
  unsupported_board_size: "目前仅支持 19 路棋盘。",
  unsupported_rules: "目前仅支持中国或日韩计分规则。",
  input_too_large: "棋谱文件不能超过 1 MiB。",
  invalid_request: "提交内容有误，请检查棋谱信息。"
};

export class ApiError extends Error {
  constructor(code, message, status = 0) {
    super(message);
    this.code = code;
    this.status = status;
  }
}

export function validateApiBase(value = "") {
  if (!value) return "";
  const url = new URL(value);
  if (url.protocol !== "https:" || url.username || url.password || url.search || url.hash ||
      url.pathname !== "/" || value.includes("*")) {
    throw new Error("远程 API 必须是明确的 HTTPS 来源地址。");
  }
  return url.origin;
}

export function createApi({ base = "", fetcher = globalThis.fetch, timeout = 20000 } = {}) {
  base = validateApiBase(base);
  async function request(path, { method = "GET", json, body, signal } = {}) {
    const controller = new AbortController();
    const abort = () => controller.abort();
    if (signal?.aborted) abort();
    signal?.addEventListener("abort", abort, { once: true });
    const timer = setTimeout(abort, timeout);
    try {
      const response = await fetcher(base + path, {
        method, signal: controller.signal, cache: "no-store", credentials: "omit",
        headers: json ? { "Content-Type": "application/json" } : undefined,
        body: json ? JSON.stringify(json) : body
      });
      let data;
      try { data = await response.json(); }
      catch { throw new ApiError("invalid_response", "服务返回格式异常，请检查 API 地址。", response.status); }
      if (!response.ok) {
        const error = data.error || {};
        const message = MESSAGES[error.code] || "棋谱无法处理：" + (error.message || data.detail || "未知错误");
        throw new ApiError(error.code || "request_failed", message +
          (error.move_number ? `（第 ${error.move_number} 手）` : ""), response.status);
      }
      return data;
    } catch (error) {
      if (error instanceof ApiError || signal?.aborted) throw error;
      throw new ApiError("network_error", "无法连接分析服务，请检查服务后重试。");
    } finally {
      clearTimeout(timer);
      signal?.removeEventListener("abort", abort);
    }
  }
  return {
    replay: (game, signal) => request("/api/v1/replay-moves", { method: "POST", json: game, signal }),
    parse: (file, signal) => {
      const body = new FormData();
      body.append("file", file);
      return request("/api/v1/parse-sgf", { method: "POST", body, signal });
    },
    submit: (game) => request("/api/v1/jobs", { method: "POST", json: game }),
    get: (id, signal) => request(`/api/v1/jobs/${encodeURIComponent(id)}`, { signal }),
    input: (id, signal) => request(`/api/v1/jobs/${encodeURIComponent(id)}/input`, { signal }),
    cancel: (id) => request(`/api/v1/jobs/${encodeURIComponent(id)}`, { method: "DELETE" })
  };
}

export function jobError(error) {
  return new ApiError(error?.code, MESSAGES[error?.code] || "分析失败，请重试。");
}
