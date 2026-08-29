import { createReviewController } from "./review-controller.mjs";

const byId = (id) => document.getElementById(id);

async function loadDemo() {
  const response = await fetch("./demo-data.json", { cache: "no-store" });
  if (!response.ok) throw new Error("示例报告加载失败。");
  const bundle = await response.json();
  if (bundle.report?.engine_source !== "katago") {
    throw new Error("示例报告缺少真实 KataGo 来源标记。");
  }

  document.body.classList.add("demo-mode");
  document.querySelector(".workspace-label").textContent = "GitHub Pages · 只读示例";
  byId("uploadStatus").textContent = "真实 KataGo 示例报告 · 上传与分析在本地版运行";
  byId("analysisViewSwitch").hidden = false;
  document.querySelector(".raw-data").hidden = false;

  const input = { ...bundle.input, source: "sgf" };
  const review = createReviewController(() => input);
  review.setReport(bundle.report);
}

loadDemo().catch((error) => {
  const summary = byId("analysisSummary");
  summary.textContent = error.message;
  summary.classList.add("error-message");
});
